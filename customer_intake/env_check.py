"""환경변수 확인·자동 mock/dry-run 폴백 (중단 없음)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from customer_intake.config import (
    DEFAULT_GOOGLE_SA_PATH,
    google_service_account_path,
)


@dataclass
class OcrModeInfo:
    mode: str  # mock | clova
    label: str
    detail: str


@dataclass
class ResolvedRunMode:
    """실제 적용될 실행 모드."""

    dry_run: bool
    env_gaps: list[str] = field(default_factory=list)
    sheets_ready: bool = False
    clova_ready: bool = False


def _sheet_id() -> str:
    return os.environ.get("GOOGLE_SHEET_ID", "").strip()


def sheets_credentials_ready() -> bool:
    if not _sheet_id():
        return False
    sa = google_service_account_path()
    if sa is not None and sa.is_file():
        return True
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return False
    from pathlib import Path

    p = Path(raw)
    if p.is_file():
        return True
    return raw.startswith("{")


def clova_credentials_ready() -> bool:
    url = os.environ.get("CLOVA_OCR_URL", "").strip()
    secret = os.environ.get("CLOVA_OCR_SECRET", "").strip()
    return bool(url and secret)


def collect_env_gaps(*, want_real_sheets: bool) -> list[str]:
    gaps: list[str] = []
    url = os.environ.get("CLOVA_OCR_URL", "").strip()
    secret = os.environ.get("CLOVA_OCR_SECRET", "").strip()
    if not clova_credentials_ready():
        if url or secret:
            gaps.append(
                "CLOVA OCR 일부만 설정됨 -> Mock OCR 사용 "
                "(D:\\mail\\.env 에 CLOVA_OCR_URL·CLOVA_OCR_SECRET 둘 다)"
            )
        else:
            gaps.append(
                "CLOVA OCR 미설정 (CLOVA_OCR_URL, CLOVA_OCR_SECRET) -> Mock OCR 사용"
            )

    if want_real_sheets and not sheets_credentials_ready():
        if not _sheet_id():
            gaps.append("GOOGLE_SHEET_ID 미설정 -> dry_run (시트 미기록)")
        else:
            gaps.append(
                "Google 서비스 계정 JSON 없음 -> dry_run (시트 미기록). "
                f"기대 경로: {DEFAULT_GOOGLE_SA_PATH}"
            )
    return gaps


def resolve_run_mode(dry_run_arg: str) -> ResolvedRunMode:
    """
    dry_run_arg: true | false | auto
    - auto: .env에 Sheets 설정이 있으면 실제 기록, 없으면 dry_run
    - 환경 부족 시 종료하지 않고 mock/dry_run으로 폴백
    """
    arg = dry_run_arg.strip().lower()
    if arg == "auto":
        want_real_sheets = True
    else:
        want_real_sheets = arg in ("0", "false", "no", "n", "off")

    sheets_ok = sheets_credentials_ready()
    clova_ok = clova_credentials_ready()
    gaps = collect_env_gaps(want_real_sheets=want_real_sheets)

    if want_real_sheets and sheets_ok:
        effective_dry_run = False
    else:
        effective_dry_run = True
        if want_real_sheets and not sheets_ok and arg != "auto":
            if "GOOGLE_SHEET_ID" not in str(gaps):
                gaps.append("Sheets 기록 불가 -> dry_run 으로 계속 처리")

    return ResolvedRunMode(
        dry_run=effective_dry_run,
        env_gaps=gaps,
        sheets_ready=sheets_ok,
        clova_ready=clova_ok,
    )


def get_ocr_mode() -> OcrModeInfo:
    if clova_credentials_ready():
        return OcrModeInfo(
            mode="clova",
            label="실제 CLOVA OCR",
            detail="CLOVA_OCR_URL + CLOVA_OCR_SECRET (.env)",
        )
    missing = []
    if not os.environ.get("CLOVA_OCR_URL", "").strip():
        missing.append("CLOVA_OCR_URL")
    if not os.environ.get("CLOVA_OCR_SECRET", "").strip():
        missing.append("CLOVA_OCR_SECRET")
    return OcrModeInfo(
        mode="mock",
        label="Mock OCR",
        detail=f"미설정({', '.join(missing) or '일부만 설정'}) -> mock_ocr_result.json",
    )


def print_startup_banner(mode: ResolvedRunMode) -> None:
    ocr = get_ocr_mode()
    sheets_line = (
        "[Sheets] 실제 기록 (dry_run=false)"
        if not mode.dry_run
        else "[Sheets] 미기록 (dry_run=true)"
    )
    print("=" * 60, flush=True)
    print("고객사 서류 intake - inbox 자동 처리", flush=True)
    print(f"[OCR] {ocr.label} - {ocr.detail}", flush=True)
    print(sheets_line, flush=True)
    if mode.env_gaps:
        print("[.env] 아래 항목 미설정 (처리는 계속됩니다)", flush=True)
        for g in mode.env_gaps:
            print(f"  - {g}", flush=True)
    print("=" * 60, flush=True)
