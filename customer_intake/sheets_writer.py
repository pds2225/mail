"""Google Sheets 고객사_마스터DB / 제출서류DB / 실행로그 기록."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from customer_intake.config import google_service_account_path
from customer_intake.extractor import ExtractedRecord
from customer_intake.privacy import (
    mask_business_number,
    mask_company_name,
    mask_person_name,
)

log = logging.getLogger(__name__)

SHEET_MASTER = "고객사_마스터DB"
SHEET_DOCUMENTS = "제출서류DB"
SHEET_RUN_LOG = "실행로그"

MASTER_HEADERS = [
    "고객사명",
    "대표자명",
    "사업자등록번호",
    "법인등록번호",
    "사업장주소",
    "개업일",
    "업태",
    "종목",
    "과세유형",
    "확인상태",
    "확인필요사항",
    "추출일시",
]

DOCUMENT_HEADERS = [
    "고객사명",
    "사업자등록번호",
    "서류종류",
    "파일명",
    "파일경로",
    "추출일시",
    "확인상태",
    "확인필요사항",
]

RUN_LOG_HEADERS = [
    "실행일시",
    "입력경로",
    "dry_run",
    "처리파일수",
    "마스터신규",
    "마스터스킵",
    "서류기록수",
    "오류수",
    "보고서경로",
    "비고",
]


@dataclass
class WritePreview:
    master_rows: list[list[str]] = field(default_factory=list)
    document_rows: list[list[str]] = field(default_factory=list)
    run_log_row: list[str] = field(default_factory=list)
    skipped_master_biz_nos: list[str] = field(default_factory=list)


@dataclass
class WriteResult:
    dry_run: bool
    master_inserted: int = 0
    master_skipped: int = 0
    documents_inserted: int = 0
    preview: WritePreview | None = None


def _normalize_biz_key(biz_no: str) -> str:
    return re.sub(r"\D", "", biz_no)


def _load_service_account_info() -> dict[str, Any]:
    sa_file = google_service_account_path()
    if sa_file is not None:
        with sa_file.open(encoding="utf-8") as f:
            return json.load(f)

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise EnvironmentError(
            "Google 서비스 계정 JSON을 찾을 수 없습니다.\n"
            "  GOOGLE_SERVICE_ACCOUNT_JSON_PATH=D:\\mail\\secrets\\google_service_account.json\n"
            "  또는 GOOGLE_SERVICE_ACCOUNT_JSON 에 파일 경로를 설정하세요.\n"
            "  자세히: D:\\mail\\docs\\CUSTOMER_INTAKE.md"
        )
    path = Path(raw)
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_JSON 이 유효한 JSON 파일 경로/문자열이 아닙니다."
        ) from e


def _open_workbook(sheet_id: str):
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        _load_service_account_info(),
        scopes=scopes,
    )
    gc = gspread.authorize(creds)
    try:
        return gc.open_by_key(sheet_id)
    except Exception as e:
        raise EnvironmentError(
            f"스프레드시트를 열 수 없습니다 (GOOGLE_SHEET_ID={sheet_id[:8]}...).\n"
            "  - ID가 맞는지 확인\n"
            "  - 서비스 계정 이메일에 스프레드시트 편집 권한이 있는지 확인\n"
            f"  - 원인: {e}"
        ) from e


def _get_or_create_worksheet(wb, title: str, headers: list[str]):
    import gspread

    try:
        ws = wb.worksheet(title)
    except gspread.WorksheetNotFound:
        log.info("시트 '%s' 없음 → 자동 생성", title)
        ws = wb.add_worksheet(title=title, rows=1000, cols=max(len(headers), 12))
    _ensure_headers(ws, headers)
    return ws


def _ensure_headers(ws, headers: list[str]) -> None:
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(headers, value_input_option="USER_ENTERED")
    elif existing != headers:
        log.warning("시트 '%s' 헤더가 기대와 다릅니다 (기존 유지)", ws.title)


def _existing_biz_numbers(ws) -> set[str]:
    rows = ws.get_all_values()
    if len(rows) < 2:
        return set()
    try:
        idx = rows[0].index("사업자등록번호")
    except ValueError:
        idx = 2
    keys: set[str] = set()
    for row in rows[1:]:
        if len(row) > idx and row[idx] and row[idx] != "확인필요":
            keys.add(_normalize_biz_key(row[idx]))
    return keys


class SheetsWriter:
    def __init__(
        self,
        *,
        dry_run: bool = True,
        sheet_id: str | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.sheet_id = (sheet_id or os.environ.get("GOOGLE_SHEET_ID", "")).strip()

    def write_batch(
        self,
        records: list[ExtractedRecord],
        *,
        input_path: str,
        report_path: str,
        errors: list[str],
    ) -> WriteResult:
        preview = WritePreview()
        existing: set[str] = set()

        if not self.dry_run:
            if not self.sheet_id:
                raise EnvironmentError(
                    "GOOGLE_SHEET_ID 미설정\n"
                    "  .env 예: GOOGLE_SHEET_ID=스프레드시트URL의ID부분\n"
                    "  자세히: D:\\mail\\docs\\CUSTOMER_INTAKE.md"
                )
            wb = _open_workbook(self.sheet_id)
            master_ws = _get_or_create_worksheet(wb, SHEET_MASTER, MASTER_HEADERS)
            doc_ws = _get_or_create_worksheet(wb, SHEET_DOCUMENTS, DOCUMENT_HEADERS)
            log_ws = _get_or_create_worksheet(wb, SHEET_RUN_LOG, RUN_LOG_HEADERS)
            existing = _existing_biz_numbers(master_ws)
        else:
            log.info("dry_run: Google Sheets 쓰기 생략 (미리보기만)")

        master_inserted = 0
        master_skipped = 0

        for rec in records:
            preview.document_rows.append(rec.as_document_row())
            biz_key = _normalize_biz_key(rec.사업자등록번호)
            if biz_key and biz_key != "확인필요" and biz_key in existing:
                master_skipped += 1
                preview.skipped_master_biz_nos.append(rec.사업자등록번호)
                log.info(
                    "마스터 스킵(중복): 사업자번호=%s 고객사=%s",
                    mask_business_number(rec.사업자등록번호),
                    mask_company_name(rec.고객사명),
                )
                continue
            if biz_key and biz_key != "확인필요":
                existing.add(biz_key)
            preview.master_rows.append(rec.as_master_row())
            master_inserted += 1
            log.info(
                "마스터 예정: 고객사=%s 대표=%s 사업자=%s",
                mask_company_name(rec.고객사명),
                mask_person_name(rec.대표자명),
                mask_business_number(rec.사업자등록번호),
            )

        run_log = [
            records[0].추출일시 if records else "",
            input_path,
            str(self.dry_run).lower(),
            str(len(records)),
            str(master_inserted),
            str(master_skipped),
            str(len(records)),
            str(len(errors)),
            report_path,
            "; ".join(errors[:3]) if errors else "",
        ]
        preview.run_log_row = run_log

        if self.dry_run:
            return WriteResult(
                dry_run=True,
                master_inserted=master_inserted,
                master_skipped=master_skipped,
                documents_inserted=len(records),
                preview=preview,
            )

        for row in preview.master_rows:
            master_ws.append_row(row, value_input_option="USER_ENTERED")
        for row in preview.document_rows:
            doc_ws.append_row(row, value_input_option="USER_ENTERED")
        log_ws.append_row(run_log, value_input_option="USER_ENTERED")

        log.info(
            "Sheets 기록 완료: 마스터+%d 스킵%d 서류+%d",
            master_inserted,
            master_skipped,
            len(records),
        )
        return WriteResult(
            dry_run=False,
            master_inserted=master_inserted,
            master_skipped=master_skipped,
            documents_inserted=len(records),
            preview=preview,
        )

    def print_preview(self, preview: WritePreview) -> None:
        print("\n=== dry_run 미리보기: 고객사_마스터DB ===")
        print("\t".join(MASTER_HEADERS))
        for row in preview.master_rows:
            print("\t".join(row))

        print("\n=== dry_run 미리보기: 제출서류DB ===")
        print("\t".join(DOCUMENT_HEADERS))
        for row in preview.document_rows:
            print("\t".join(row))

        if preview.skipped_master_biz_nos:
            print("\n=== 중복 스킵 (사업자등록번호) ===")
            for b in preview.skipped_master_biz_nos:
                print(b)

        print("\n=== dry_run 미리보기: 실행로그 ===")
        print("\t".join(RUN_LOG_HEADERS))
        print("\t".join(preview.run_log_row))
