"""Single-active-run guard for local/manual monitor executions."""
from __future__ import annotations

from pathlib import Path

from mail_core.paths import STATE_DIR
from mail_core.storage.state_store import FileLock, LockBusyError


RUN_LOCK_PATH = STATE_DIR / "monitor.run.lock"


class MonitorRunLock:
    """A long-lived lock with stale recovery for the actual delivery path."""

    def __init__(self, path: str | Path = RUN_LOCK_PATH) -> None:
        self._lock = FileLock(path, timeout_seconds=0, stale_after_seconds=8 * 60 * 60)

    def acquire(self) -> bool:
        try:
            self._lock.acquire()
            return True
        except LockBusyError:
            return False

    def release(self) -> None:
        self._lock.release()
