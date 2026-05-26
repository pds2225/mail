"""inbox 폴더 변경 감지 (watchdog 우선, 없으면 스냅샷 폴링)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from customer_intake.config import SUPPORTED_SUFFIXES, inbox_dir

log = logging.getLogger(__name__)


def _is_supported(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def inbox_snapshot(root: Path | None = None) -> tuple[tuple[str, int, int], ...]:
    """파일명·크기·mtime 스냅샷 (변경 여부 비교용)."""
    root = (root or inbox_dir()).resolve()
    if not root.is_dir():
        return ()
    items: list[tuple[str, int, int]] = []
    for p in root.iterdir():
        if _is_supported(p):
            st = p.stat()
            items.append((p.name, st.st_size, int(st.st_mtime)))
    return tuple(sorted(items))


class DebouncedCallback:
    """연속 이벤트를 모아 delay 초 후 1회만 실행."""

    def __init__(self, delay_sec: float, callback: Callable[[], None]) -> None:
        self.delay_sec = delay_sec
        self.callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        # Prevents two timer threads from executing the callback concurrently.
        # Without this, a slow OCR+Sheets run (>debounce delay) can overlap with
        # a second fire, causing duplicate Google Sheets rows for the same file.
        self._exec_lock = threading.Lock()

    def trigger(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay_sec, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._exec_lock:
            try:
                self.callback()
            except Exception:
                log.exception("inbox 처리 콜백 실패")


def run_watch_loop(on_change: Callable[[], None], *, stop_event: threading.Event | None = None) -> None:
    """
    inbox 변경 시에만 on_change 호출.
    - watchdog 설치됨: OS 파일 이벤트 + debounce
    - 없음: 스냅샷 비교 폴링 (기본 60초, 변경 시에만 on_change)
    """
    from customer_intake.config import (
        WATCH_DEBOUNCE_SEC,
        WATCH_FALLBACK_POLL_SEC,
    )

    root = inbox_dir()
    debounced = DebouncedCallback(WATCH_DEBOUNCE_SEC, on_change)

    try:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        log.info(
            "watchdog 미설치 -> 폴더 스냅샷 비교 (%.0fs마다 확인, 변경 시만 처리). "
            "pip install watchdog 권장",
            WATCH_FALLBACK_POLL_SEC,
        )
        last = inbox_snapshot(root)
        while not (stop_event and stop_event.is_set()):
            time.sleep(WATCH_FALLBACK_POLL_SEC)
            current = inbox_snapshot(root)
            if current != last:
                last = current
                if current:
                    log.info("inbox 변경 감지 (파일 %d건)", len(current))
                debounced.trigger()
        return

    class Handler(FileSystemEventHandler):
        def _maybe(self, event: FileSystemEvent) -> None:
            if event.is_directory:
                return
            p = Path(event.src_path)
            if _is_supported(p):
                log.debug("inbox 이벤트: %s", p.name)
                debounced.trigger()

        def on_created(self, event: FileSystemEvent) -> None:
            self._maybe(event)

        def on_modified(self, event: FileSystemEvent) -> None:
            self._maybe(event)

        def on_moved(self, event: FileSystemEvent) -> None:
            dest = getattr(event, "dest_path", None) or event.src_path
            if event.is_directory:
                return
            p = Path(dest)
            if _is_supported(p):
                debounced.trigger()

    observer = Observer()
    observer.schedule(Handler(), str(root), recursive=False)
    observer.start()
    log.info(
        "inbox 파일 이벤트 감시 (변경 후 %.1fs 대기 후 처리): %s",
        WATCH_DEBOUNCE_SEC,
        root,
    )
    try:
        while not (stop_event and stop_event.is_set()):
            time.sleep(1)
    finally:
        observer.stop()
        observer.join(timeout=5)
