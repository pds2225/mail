"""Canonical repository, configuration, and runtime paths.

Environment overrides are primarily used by serverless deployments that copy
configuration into a writable temporary workspace.
"""
from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


CONFIG_DIR = _path_from_env("MAIL_CONFIG_DIR", REPO_ROOT / "config")
VAR_DIR = _path_from_env("MAIL_VAR_DIR", REPO_ROOT / "var")
STATE_DIR = VAR_DIR / "state"
OUTBOX_DIR = VAR_DIR / "outbox"
LOGS_DIR = VAR_DIR / "logs"
REPORTS_DIR = VAR_DIR / "reports"
RAW_DIR = VAR_DIR / "raw"
DATA_DIR = REPO_ROOT / "data"
SECRETS_DIR = REPO_ROOT / "secrets"

# raw store 구 경로. var/ 구조로 이사하기 전 수집분이 남아 있을 수 있다.
LEGACY_RAW_DIR = REPO_ROOT / "data" / "raw"


def _has_notices(root: Path) -> bool:
    """root 아래에 공고 meta.json 이 하나라도 있으면 True (첫 매치에서 중단)."""
    try:
        return next(root.glob("*/notices/*/meta.json"), None) is not None
    except OSError:
        return False


def resolve_raw_root() -> Path:
    """수집 원본(raw store)이 실제로 들어 있는 디렉터리를 고른다.

    정본은 ``var/raw``. 다만 구 경로(``data/raw``)에만 수집분이 남은 저장소에서
    측정 스크립트가 조용히 0건으로 도는 것을 막기 위해, 정본이 비어 있고
    구 경로에 공고가 있으면 구 경로를 쓴다.
    """
    if _has_notices(RAW_DIR):
        return RAW_DIR
    if _has_notices(LEGACY_RAW_DIR):
        return LEGACY_RAW_DIR
    return RAW_DIR
