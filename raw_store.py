"""공고 원문·메타 로컬 저장 — 누락 재현·재파싱·디버깅용.

설계: docs/RAW_STORE.md
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

KST = __import__("datetime").timezone(timedelta(hours=9), name="KST")

DEFAULT_ROOT = Path(__file__).resolve().parent / "data" / "raw"
_SAFE_ID_RE = re.compile(r"[^\w.\-]+", re.UNICODE)


def safe_notice_dirname(notice_id: str) -> str:
    s = _SAFE_ID_RE.sub("_", (notice_id or "unknown").strip())[:160]
    return s or "unknown"


class RawStore:
    """하루(KST) 단위 폴더에 신규 공고 메타 + 상세 HTML(선택) 저장."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        run_day: date | None = None,
        retention_days: int = 30,
        max_detail_bytes: int = 800_000,
        gzip_detail: bool = True,
    ) -> None:
        self.root = Path(root or DEFAULT_ROOT)
        self.run_day = run_day or datetime.now(KST).date()
        self.retention_days = max(1, int(retention_days))
        self.max_detail_bytes = max(10_000, int(max_detail_bytes))
        self.gzip_detail = gzip_detail
        self.day_dir = self.root / self.run_day.isoformat()
        self.notices_dir = self.day_dir / "notices"
        self._meta_saved = 0
        self._detail_saved = 0

    @classmethod
    def from_settings(cls, settings: dict, *, run_day: date | None = None) -> RawStore | None:
        if not settings.get("raw_store_enabled"):
            return None
        root = settings.get("raw_store_dir")
        return cls(
            root=Path(root) if root else None,
            run_day=run_day,
            retention_days=int(settings.get("raw_store_retention_days", 30)),
            max_detail_bytes=int(settings.get("raw_store_max_detail_bytes", 800_000)),
            gzip_detail=bool(settings.get("raw_store_gzip_detail", True)),
        )

    def begin_run(self, *, collected: int = 0, deduped: int = 0, new_items: int = 0) -> None:
        self.prune_old()
        self.notices_dir.mkdir(parents=True, exist_ok=True)
        run_path = self.day_dir / "run.json"
        payload = {
            "run_day": self.run_day.isoformat(),
            "started_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "collected": collected,
            "deduped": deduped,
            "new_items": new_items,
        }
        if run_path.exists():
            try:
                prev = json.loads(run_path.read_text(encoding="utf-8"))
                if isinstance(prev, list):
                    runs = prev
                else:
                    runs = [prev]
            except (json.JSONDecodeError, TypeError):
                runs = []
            runs.append(payload)
            run_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            run_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("원문 저장 시작: %s", self.day_dir)

    def prune_old(self) -> int:
        if not self.root.exists():
            return 0
        cutoff = (self.run_day - timedelta(days=self.retention_days))
        removed = 0
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            try:
                d = date.fromisoformat(child.name)
            except ValueError:
                continue
            if d < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        if removed:
            log.info("원문 저장 보관 만료: %d일 폴더 삭제 (보관 %d일)", removed, self.retention_days)
        return removed

    def notice_path(self, notice_id: str) -> Path:
        return self.notices_dir / safe_notice_dirname(notice_id)

    def save_item_meta(self, item: dict) -> Path | None:
        nid = (item.get("id") or "").strip()
        if not nid:
            return None
        p = self.notice_path(nid)
        p.mkdir(parents=True, exist_ok=True)
        meta = {
            "saved_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "notice_id": nid,
            "title": item.get("title"),
            "link": item.get("link"),
            "source": item.get("source"),
            "author": item.get("author"),
            "description": item.get("description"),
            "deadline": item.get("deadline"),
            "posted_date": item.get("posted_date"),
            "is_aggregator": item.get("is_aggregator"),
            "region_field": item.get("region_field"),
            "application_period": item.get("application_period"),
            "detail_enriched": item.get("detail_enriched"),
            "detail_extraction": item.get("detail_extraction"),
            "detail_tables": item.get("detail_tables"),
        }
        for k in (
            "business_age_text", "target_field", "target_age_field",
            "organizer_field", "exclude_target_field", "support_field",
        ):
            if item.get(k):
                meta[k] = item[k]
        out = p / "meta.json"
        out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self._meta_saved += 1
        return out

    def save_detail_html(self, notice_id: str, url: str, html_text: str) -> Path | None:
        nid = (notice_id or "").strip()
        if not nid or not html_text:
            return None
        raw = html_text.encode("utf-8", errors="replace")
        if len(raw) > self.max_detail_bytes:
            raw = raw[: self.max_detail_bytes]
        p = self.notice_path(nid)
        p.mkdir(parents=True, exist_ok=True)
        sidecar = {
            "saved_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "bytes": len(raw),
            "truncated": len(html_text.encode("utf-8", errors="replace")) > len(raw),
        }
        (p / "detail.meta.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        if self.gzip_detail:
            out = p / "detail.html.gz"
            out.write_bytes(gzip.compress(raw))
        else:
            out = p / "detail.html"
            out.write_bytes(raw)
        self._detail_saved += 1
        return out

    def update_meta_after_enrich(self, item: dict) -> None:
        """상세 보강 후 메타 갱신(본문·지역 필드 반영)."""
        self.save_item_meta(item)

    def summary(self) -> dict[str, Any]:
        return {
            "raw_store_dir": str(self.day_dir),
            "raw_store_meta_saved": self._meta_saved,
            "raw_store_detail_saved": self._detail_saved,
        }

    @staticmethod
    def load_meta(notice_id: str, *, root: Path | None = None, run_day: date | None = None) -> dict | None:
        """특정 일자 또는 최신 폴더에서 meta.json 로드."""
        base = Path(root or DEFAULT_ROOT)
        if run_day:
            path = base / run_day.isoformat() / "notices" / safe_notice_dirname(notice_id) / "meta.json"
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        days = sorted(
            (d for d in base.iterdir() if d.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for d in days:
            path = d / "notices" / safe_notice_dirname(notice_id) / "meta.json"
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return None

    @staticmethod
    def load_detail_html(notice_id: str, *, root: Path | None = None, run_day: date | None = None) -> str | None:
        base = Path(root or DEFAULT_ROOT)
        dirs = [base / run_day.isoformat()] if run_day else sorted(
            (d for d in base.iterdir() if d.is_dir()), key=lambda p: p.name, reverse=True,
        )
        for day in dirs:
            p = day / "notices" / safe_notice_dirname(notice_id)
            gz = p / "detail.html.gz"
            plain = p / "detail.html"
            if gz.exists():
                return gzip.decompress(gz.read_bytes()).decode("utf-8", errors="replace")
            if plain.exists():
                return plain.read_text(encoding="utf-8", errors="replace")
        return None
