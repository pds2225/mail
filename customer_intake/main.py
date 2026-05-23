"""CLI 호환: 경로 지정 실행은 watcher inbox 방식을 권장합니다."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from customer_intake.clova_ocr_client import ClovaOcrClient
from customer_intake.config import ensure_directories, inbox_dir
from customer_intake.extractor import extract_from_ocr
from customer_intake.file_scanner import scan_input
from customer_intake.report import RunSummary, save_report
from customer_intake.sheets_writer import SheetsWriter
from customer_intake.watcher import _parse_bool, main as watcher_main

log = logging.getLogger("customer_intake")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="고객사 서류 OCR → Google Sheets (inbox 감시는 watcher 사용)"
    )
    p.add_argument(
        "--path",
        help="(선택) 로컬 폴더 또는 단일 파일 — 미지정 시 watcher와 동일",
    )
    p.add_argument("--once", action="store_true", help="inbox 1회 처리")
    p.add_argument("--watch", action="store_true", help="inbox 감시")
    p.add_argument(
        "--dry-run",
        default="true",
        help="true: Sheets 미기록·미리보기만 (기본 true)",
    )
    return p


def run_path(path: str, *, dry_run: bool = True) -> int:
    """레거시: --path 로 폴더/파일 직접 지정."""
    errors: list[str] = []
    records = []
    ocr_client = ClovaOcrClient()
    try:
        scanned = scan_input(path)
    except (FileNotFoundError, ValueError) as e:
        log.error("%s", e)
        return 1

    primary = scanned[0]
    for sf in scanned:
        if sf.doc_type_hint == "사업자등록증":
            primary = sf
            break
    process_order = [primary] + [s for s in scanned if s.path != primary.path]
    master_biz_no: str | None = None

    for sf in process_order:
        try:
            ocr = ocr_client.recognize(sf.path)
            rec = extract_from_ocr(
                ocr,
                file_path=sf.path,
                doc_type=sf.doc_type_hint,
            )
            if master_biz_no and rec.사업자등록번호 == "확인필요":
                rec.사업자등록번호 = master_biz_no
            if rec.사업자등록번호 != "확인필요" and sf is primary:
                master_biz_no = rec.사업자등록번호
            records.append(rec)
            log.info(
                "추출 완료: 파일=%s 서류=%s 상태=%s",
                sf.path.name,
                rec.서류종류,
                rec.확인상태,
            )
        except Exception as e:
            errors.append(f"{sf.path.name}: {e}")
            log.error("처리 실패: %s", sf.path.name)

    if not records:
        log.error("추출된 레코드 없음")
        return 1

    writer = SheetsWriter(dry_run=dry_run)
    try:
        write_result = writer.write_batch(
            records,
            input_path=str(Path(path).resolve()),
            report_path="",
            errors=errors,
        )
        if dry_run and write_result.preview:
            writer.print_preview(write_result.preview)
    except EnvironmentError as e:
        log.error("%s", e)
        return 1

    summary = RunSummary(
        input_path=path,
        dry_run=dry_run,
        files_processed=len(scanned),
        records=records,
        write_result=write_result,
        errors=errors,
        used_mock_ocr=ocr_client.use_mock,
    )
    report_file = save_report(summary)
    print(f"\n보고서: {report_file}")
    return 0 if not errors else 2


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = build_parser().parse_args(argv)
    dry_run = _parse_bool(args.dry_run)

    if args.once or args.watch:
        wargv = ["--once" if args.once else "--watch", "--dry-run", args.dry_run]
        watcher_main(wargv)
        return

    if args.path:
        sys.exit(run_path(args.path, dry_run=dry_run))

    ensure_directories()
    log.info("경로 미지정 — inbox 1회 처리 (%s)", inbox_dir())
    wargv = ["--once", "--dry-run", args.dry_run]
    watcher_main(wargv)


if __name__ == "__main__":
    main()
