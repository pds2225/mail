"""processed_files.json — 동일 파일(내용 해시) 중복 처리 방지."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from customer_intake.config import PROCESSED_FILES_JSON

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


@dataclass
class ProcessedEntry:
    sha256: str
    original_name: str
    status: str  # done | failed
    processed_at: str
    report_path: str = ""
    note: str = ""


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ProcessedStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self.path = store_path or PROCESSED_FILES_JSON
        self._entries: dict[str, ProcessedEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._entries = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("entries", raw) if isinstance(raw, dict) else {}
            self._entries = {}
            for key, val in items.items():
                if isinstance(val, dict):
                    self._entries[key] = ProcessedEntry(**val)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            log.warning("processed_files.json 읽기 실패, 새로 시작: %s", e)
            self._entries = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": {k: asdict(v) for k, v in self._entries.items()},
            "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def is_processed(self, file_path: Path) -> ProcessedEntry | None:
        digest = _file_sha256(file_path)
        return self._entries.get(digest)

    def mark(
        self,
        file_path: Path,
        *,
        status: str,
        report_path: str = "",
        note: str = "",
    ) -> str:
        digest = _file_sha256(file_path)
        entry = ProcessedEntry(
            sha256=digest,
            original_name=file_path.name,
            status=status,
            processed_at=datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            report_path=report_path,
            note=note,
        )
        self._entries[digest] = entry
        self.save()
        return digest
