"""선택적 공고별 기업 상한. 기본 off이며 검수에는 비식별 집계만 남긴다."""
from __future__ import annotations

import hashlib
from pathlib import Path

from mail_core.storage.state_store import atomic_write_json


class CompanyMatchFanout:
    def __init__(self, limit=None, *, report_path: Path | None = None):
        try:
            self.limit = max(0, int(limit or 0))
        except (TypeError, ValueError):
            self.limit = 0
        self.report_path = report_path
        self.accepted: dict[str, set[str]] = {}
        self.exceeded: set[str] = set()
        self.excess_matches = 0
        if report_path and (self.limit or report_path.exists()):
            self.write_report()

    def apply(self, items: list[dict], company: dict) -> tuple[list[dict], list[dict]]:
        if not self.limit:
            return items, []
        kept, rejected = [], []
        tenant = str(company.get("tenant_id") or "default")
        company_id = str(company.get("id") or "")
        for item in items:
            identity = str(item.get("id") or item.get("link") or item.get("title") or "")
            if not identity:
                kept.append(item)
                continue
            key = hashlib.sha256(f"{tenant}|{identity}".encode()).hexdigest()
            companies = self.accepted.setdefault(key, set())
            if company_id in companies or len(companies) < self.limit:
                companies.add(company_id)
                kept.append(item)
            else:
                rejected.append({**item, "_match_reason": "MATCH_FANOUT_HIGH"})
                self.exceeded.add(key)
                self.excess_matches += 1
        if rejected and self.report_path:
            self.write_report()
        return kept, rejected

    def write_report(self):
        if self.report_path:
            atomic_write_json(self.report_path, {
                "code": "MATCH_FANOUT_HIGH", "limit": self.limit,
                "exceeded_notices": len(self.exceeded), "excess_matches": self.excess_matches,
            })
