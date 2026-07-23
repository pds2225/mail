"""Encrypted local state primitives used for PII and delivery recovery."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from state_store import atomic_write_bytes


BASE_DIR = Path(__file__).resolve().parent
SECRETS_DIR = BASE_DIR / "secrets"
DEFAULT_KEY_PATH = SECRETS_DIR / "mail_private.key"
KEY_ENV = "MAIL_PRIVATE_CONFIG_KEY"


class SecureStoreUnavailable(RuntimeError):
    """Raised when sensitive state would be persisted without an encryption key."""


def ensure_local_key(path: str | os.PathLike[str] = DEFAULT_KEY_PATH) -> bytes:
    """Return the local Fernet key, creating it in the ignored secrets directory."""
    target = Path(path)
    raw = os.environ.get(KEY_ENV, "").strip()
    if raw:
        Fernet(raw.encode("utf-8"))
        return raw.encode("utf-8")
    if target.exists():
        key = target.read_bytes().strip()
        Fernet(key)
        return key
    target.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".mail_private.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(key + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return key


def get_fernet(*, create_local_key: bool = False) -> Fernet | None:
    raw = os.environ.get(KEY_ENV, "").strip()
    if raw:
        return Fernet(raw.encode("utf-8"))
    if DEFAULT_KEY_PATH.exists():
        return Fernet(DEFAULT_KEY_PATH.read_bytes().strip())
    if create_local_key:
        return Fernet(ensure_local_key(DEFAULT_KEY_PATH))
    return None


def encrypt_json(data: Any, *, create_local_key: bool = False) -> bytes:
    fernet = get_fernet(create_local_key=create_local_key)
    if fernet is None:
        raise SecureStoreUnavailable("MAIL_PRIVATE_CONFIG_KEY or ignored local key is required")
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return fernet.encrypt(plain)


def decrypt_json(token: bytes, default: Any = None) -> Any:
    fernet = get_fernet(create_local_key=False)
    if fernet is None:
        return default
    try:
        return json.loads(fernet.decrypt(token).decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
        return default


def save_encrypted_json(
    path: str | os.PathLike[str],
    data: Any,
    *,
    create_local_key: bool = False,
) -> bool:
    return atomic_write_bytes(
        path,
        encrypt_json(data, create_local_key=create_local_key),
        backup=True,
    )


def load_encrypted_json(path: str | os.PathLike[str], default: Any = None) -> Any:
    """Load encrypted state, recovering the newest decryptable rolling backup if needed."""
    target = Path(path)
    candidates = [target]
    backup_dir = target.parent / "state_backups"
    if backup_dir.exists():
        candidates.extend(sorted(
            backup_dir.glob(f"{target.name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True,
        ))
    missing = object()
    for candidate in candidates:
        try:
            token = candidate.read_bytes()
        except OSError:
            continue
        value = decrypt_json(token, missing)
        if value is not missing:
            return value
    return default
