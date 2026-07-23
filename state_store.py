"""Crash-safe JSON state storage with per-file locks and rolling backups."""
from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_LOCK_TIMEOUT_SECONDS = 15.0
DEFAULT_STALE_LOCK_SECONDS = 6 * 60 * 60
DEFAULT_MAX_BACKUPS = 14


class LockBusyError(RuntimeError):
    """Raised when another live process still owns a state file lock."""


class FileLock:
    """Small cross-process lock built on atomic file creation.

    It deliberately avoids a platform-specific dependency. A stale lock is removed only
    after a generous timeout, so a crashed run does not block the next scheduled run.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        stale_after_seconds: float = DEFAULT_STALE_LOCK_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self.stale_after_seconds = stale_after_seconds
        self.acquired = False

    def _is_stale(self) -> bool:
        try:
            return (time.time() - self.path.stat().st_mtime) > self.stale_after_seconds
        except OSError:
            return False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        payload = f"pid={os.getpid()}\ncreated_at={datetime.now(timezone.utc).isoformat()}\n"
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                self.acquired = True
                return
            except FileExistsError:
                if self._is_stale():
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise LockBusyError(f"state lock busy: {self.path.name}")
                time.sleep(0.1)

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.release()


@contextmanager
def locked_path(
    target: str | os.PathLike[str],
    *,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    stale_after_seconds: float = DEFAULT_STALE_LOCK_SECONDS,
) -> Iterator[None]:
    path = Path(target)
    with FileLock(
        path.with_name(path.name + ".lock"),
        timeout_seconds=timeout_seconds,
        stale_after_seconds=stale_after_seconds,
    ):
        yield


def _backup_dir(path: Path) -> Path:
    return path.parent / "state_backups"


def _backup_existing(path: Path, data: bytes, *, max_backups: int) -> None:
    if not data:
        return
    directory = _backup_dir(path)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = directory / f"{path.name}.{stamp}.bak"
    backup.write_bytes(data)
    backups = sorted(directory.glob(f"{path.name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[max_backups:]:
        try:
            old.unlink()
        except OSError:
            pass


def _atomic_write_bytes_unlocked(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    backup: bool = True,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> bool:
    """Write bytes atomically while the caller owns this path's lock."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = target.read_bytes()
    except FileNotFoundError:
        previous = b""
    if previous == data:
        return False
    if backup and previous:
        _backup_existing(target, previous, max_backups=max_backups)
    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return True


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    backup: bool = True,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> bool:
    """Write bytes atomically under a per-file process lock."""
    with locked_path(path):
        return _atomic_write_bytes_unlocked(path, data, backup=backup, max_backups=max_backups)


def atomic_write_bytes_while_locked(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    backup: bool = True,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> bool:
    """Atomic replacement for a caller already holding ``locked_path(path)``."""
    return _atomic_write_bytes_unlocked(path, data, backup=backup, max_backups=max_backups)


def atomic_write_json(
    path: str | os.PathLike[str],
    data: Any,
    *,
    indent: int = 2,
    backup: bool = True,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> bool:
    encoded = json.dumps(data, ensure_ascii=False, indent=indent).encode("utf-8")
    return atomic_write_bytes(path, encoded, backup=backup, max_backups=max_backups)


def load_json_with_recovery(path: str | os.PathLike[str], default: Any) -> Any:
    """Load JSON, recovering the newest valid backup after a damaged write."""
    target = Path(path)
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        directory = _backup_dir(target)
        candidates = sorted(
            directory.glob(f"{target.name}.*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ) if directory.exists() else []
        for backup in candidates:
            try:
                return json.loads(backup.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
        return default
