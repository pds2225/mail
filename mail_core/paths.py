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
