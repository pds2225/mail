"""고객사 intake 고정 폴더·환경변수 (.env 자동 로드)."""

from __future__ import annotations

import os
from pathlib import Path

# 레포 루트 (D:\mail)
REPO_ROOT = Path(__file__).resolve().parent.parent

# .env 자동 로드 (customer_intake import 시 1회)
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


_load_dotenv()

# 고정 기본 경로 (Windows)
DEFAULT_INBOX = Path(r"D:\customer_intake_inbox")
DEFAULT_DONE = Path(r"D:\customer_intake_done")
DEFAULT_FAILED = Path(r"D:\customer_intake_failed")
DEFAULT_REPORTS = Path(r"D:\customer_intake_reports")

# Google 서비스 계정 JSON 기본 위치 (예시·권장)
DEFAULT_GOOGLE_SA_PATH = REPO_ROOT / "secrets" / "google_service_account.json"

# 처리 이력 (레포 내 — gitignore)
PROCESSED_FILES_JSON = Path(__file__).resolve().parent / "processed_files.json"

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}

# legacy: 폴백 폴링 간격(초). watchdog 사용 시 거의 쓰이지 않음
WATCH_POLL_INTERVAL = float(os.environ.get("CUSTOMER_INTAKE_POLL_SEC", "60"))
WATCH_FALLBACK_POLL_SEC = float(
    os.environ.get("CUSTOMER_INTAKE_FALLBACK_POLL_SEC", "60")
)
# 파일 복사·연속 저장이 끝난 뒤 처리까지 대기(초)
WATCH_DEBOUNCE_SEC = float(os.environ.get("CUSTOMER_INTAKE_DEBOUNCE_SEC", "3"))
FILE_STABLE_WAIT_SEC = float(os.environ.get("CUSTOMER_INTAKE_STABLE_SEC", "1.5"))
FILE_STABLE_RETRIES = int(os.environ.get("CUSTOMER_INTAKE_STABLE_RETRIES", "3"))


def inbox_dir() -> Path:
    return Path(os.environ.get("CUSTOMER_INTAKE_INBOX", str(DEFAULT_INBOX)))


def done_dir() -> Path:
    return Path(os.environ.get("CUSTOMER_INTAKE_DONE", str(DEFAULT_DONE)))


def failed_dir() -> Path:
    return Path(os.environ.get("CUSTOMER_INTAKE_FAILED", str(DEFAULT_FAILED)))


def reports_dir() -> Path:
    return Path(os.environ.get("CUSTOMER_INTAKE_REPORTS", str(DEFAULT_REPORTS)))


def google_service_account_path() -> Path | None:
    """
    서비스 계정 JSON 파일 경로 (존재하는 경우만).
    우선순위: GOOGLE_SERVICE_ACCOUNT_JSON_PATH → GOOGLE_SERVICE_ACCOUNT_JSON(파일) → 기본 secrets 경로
    """
    path_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "").strip()
    if path_raw:
        p = Path(path_raw).expanduser()
        if p.is_file():
            return p.resolve()

    json_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_env:
        p = Path(json_env).expanduser()
        if p.is_file():
            return p.resolve()

    if DEFAULT_GOOGLE_SA_PATH.is_file():
        return DEFAULT_GOOGLE_SA_PATH.resolve()

    return None


def ensure_directories() -> None:
    """inbox / done / failed / reports / secrets 폴더가 없으면 생성."""
    for d in (inbox_dir(), done_dir(), failed_dir(), reports_dir()):
        d.mkdir(parents=True, exist_ok=True)
    secrets_dir = REPO_ROOT / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
