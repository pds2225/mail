"""고정 inbox 폴더 감시·1회 처리: OCR → Sheets → 파일 이동."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from customer_intake.clova_ocr_client import ClovaOcrClient
from customer_intake.config import (
    REPO_ROOT,
    FILE_STABLE_RETRIES,
    FILE_STABLE_WAIT_SEC,
    done_dir,
    ensure_directories,
    failed_dir,
    inbox_dir,
    reports_dir,
)
from customer_intake.inbox_watch import run_watch_loop
from customer_intake.env_check import (
    ResolvedRunMode,
    get_ocr_mode,
    print_startup_banner,
    resolve_run_mode,
)
from customer_intake.extractor import extract_from_ocr
from customer_intake.file_scanner import ScannedFile, scan_inbox
from customer_intake.processed_store import ProcessedStore
from customer_intake.report import RunSummary, save_report
from customer_intake.sheets_writer import SheetsWriter

log = logging.getLogger("customer_intake.watcher")


@dataclass
class FileProcessResult:
    file_path: Path
    success: bool
    skipped: bool = False
    error: str = ""
    report_path: str = ""


def _wait_file_stable(path: Path) -> bool:
    last_size = -1
    for _ in range(FILE_STABLE_RETRIES):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last_size and size > 0:
            return True
        last_size = size
        time.sleep(FILE_STABLE_WAIT_SEC)
    try:
        return path.stat().st_size == last_size and last_size > 0
    except OSError:
        return False


def _unique_destination(folder: Path, name: str) -> Path:
    dest = folder / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 1
    while True:
        candidate = folder / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _move_file(src: Path, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    dest = _unique_destination(folder, src.name)
    shutil.move(str(src), str(dest))
    return dest


def process_single_file(
    sf: ScannedFile,
    *,
    run_mode: ResolvedRunMode,
    ocr_client: ClovaOcrClient,
    writer: SheetsWriter,
    store: ProcessedStore,
) -> FileProcessResult:
    path = sf.path.resolve()
    prior = store.is_processed(path)
    if prior:
        log.info(
            "이미 처리됨(스킵): 파일=%s 상태=%s",
            path.name,
            prior.status,
        )
        if path.exists():
            dest = done_dir() if prior.status == "done" else failed_dir()
            moved = _move_file(path, dest)
            log.info("중복 스킵 -> %s: %s", dest.name, moved.name)
        return FileProcessResult(file_path=path, success=True, skipped=True)

    if not _wait_file_stable(path):
        return FileProcessResult(
            file_path=path,
            success=False,
            error="파일 안정화 대기 실패(복사 중이거나 접근 불가)",
        )

    errors: list[str] = list(run_mode.env_gaps)
    try:
        ocr = ocr_client.recognize(path)
        rec = extract_from_ocr(
            ocr,
            file_path=path,
            doc_type=sf.doc_type_hint,
        )
        write_result = writer.write_batch(
            [rec],
            input_path=str(inbox_dir()),
            report_path="",
            errors=errors,
        )

        ocr_info = get_ocr_mode()
        summary = RunSummary(
            input_path=str(path),
            dry_run=run_mode.dry_run,
            files_processed=1,
            records=[rec],
            write_result=write_result,
            errors=[e for e in errors if e not in run_mode.env_gaps],
            used_mock_ocr=ocr_client.use_mock,
            ocr_mode_label=ocr_info.label,
            env_gaps=run_mode.env_gaps,
        )
        report_file = save_report(summary, reports_root=reports_dir())
        report_path = str(report_file)

        store.mark(path, status="done", report_path=report_path)
        moved = _move_file(path, done_dir())
        log.info("처리 완료 -> done: %s", moved.name)
        return FileProcessResult(
            file_path=path,
            success=True,
            report_path=report_path,
        )
    except Exception as e:
        err = str(e)
        log.error("처리 실패: %s", path.name)
        try:
            if path.exists():
                store.mark(path, status="failed", note=err[:200])
                moved = _move_file(path, failed_dir())
                log.info("처리 실패 -> failed: %s", moved.name)
        except OSError as move_err:
            log.error("failed 폴더 이동 실패: %s", move_err)
        return FileProcessResult(
            file_path=path,
            success=False,
            error=err,
        )


def run_once(*, run_mode: ResolvedRunMode) -> int:
    ensure_directories()
    log.info("작업 디렉터리: %s", REPO_ROOT)
    store = ProcessedStore()
    ocr_client = ClovaOcrClient()
    writer = SheetsWriter(dry_run=run_mode.dry_run)

    try:
        scanned = scan_inbox()
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1

    if not scanned:
        log.info("inbox에 처리할 파일 없음: %s", inbox_dir())
        return 0

    log.info("inbox 파일 %d건", len(scanned))
    failures = 0
    for sf in scanned:
        result = process_single_file(
            sf,
            run_mode=run_mode,
            ocr_client=ocr_client,
            writer=writer,
            store=store,
        )
        if not result.success and not result.skipped:
            failures += 1

    return 1 if failures else 0


def _process_inbox_batch(
    *,
    run_mode: ResolvedRunMode,
    store: ProcessedStore,
    ocr_client: ClovaOcrClient,
    writer: SheetsWriter,
) -> None:
    try:
        scanned = scan_inbox()
    except FileNotFoundError:
        ensure_directories()
        return
    if not scanned:
        return
    log.info("inbox 처리 시작: %d건", len(scanned))
    for sf in scanned:
        process_single_file(
            sf,
            run_mode=run_mode,
            ocr_client=ocr_client,
            writer=writer,
            store=store,
        )


def run_watch(*, run_mode: ResolvedRunMode) -> None:
    ensure_directories()
    log.info(
        "inbox 감시: %s (파일 변경 시에만 처리, dry_run=%s)",
        inbox_dir(),
        run_mode.dry_run,
    )
    store = ProcessedStore()
    ocr_client = ClovaOcrClient()
    writer = SheetsWriter(dry_run=run_mode.dry_run)

    def on_change() -> None:
        _process_inbox_batch(
            run_mode=run_mode,
            store=store,
            ocr_client=ocr_client,
            writer=writer,
        )

    # 기동 시 대기 중인 파일 1회 처리
    on_change()

    try:
        run_watch_loop(on_change)
    except KeyboardInterrupt:
        log.info("감시 종료")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="고객사 서류 inbox 자동 처리 (경로 입력 불필요)"
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="inbox 1회 처리")
    mode.add_argument("--watch", action="store_true", help="inbox 계속 감시")
    p.add_argument(
        "--dry-run",
        default="auto",
        help="auto(기본): .env 있으면 Sheets 기록 | true | false",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = build_parser().parse_args(argv)
    run_mode = resolve_run_mode(args.dry_run)
    print_startup_banner(run_mode)

    if args.watch:
        run_watch(run_mode=run_mode)
        sys.exit(0)

    code = run_once(run_mode=run_mode)
    sys.exit(code)


if __name__ == "__main__":
    main()
