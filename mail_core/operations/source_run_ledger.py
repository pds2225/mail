"""실행별 소스 판정 이력 JSONL (git-ignore 대상, 30일 롤링 권장).

W0: append/iter/baseline_eligible 헬퍼만. monitor 배선은 최소 훅(후속).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from mail_core.paths import STATE_DIR

SOURCE_RUN_LEDGER_PATH = STATE_DIR / "source_run_ledger.jsonl"

# classify 소스 상태 중 baseline 에 넣어도 되는 것
_BASELINE_OK_STATUS = "SUCCESS"


def baseline_eligible(source_report: dict[str, Any] | None) -> bool:
    """SUCCESS 이고 risk 가 없을 때만 True (ADR §6)."""
    if not isinstance(source_report, dict):
        return False
    if source_report.get("status") != _BASELINE_OK_STATUS:
        return False
    if source_report.get("risk_level"):
        return False
    return True


def build_ledger_record(
    *,
    run_id: str,
    source_report: dict[str, Any],
    page_stat: dict[str, Any] | None = None,
    extraction_rates: dict[str, Any] | None = None,
    retry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """source_run JSONL 1행 스키마."""
    report = source_report if isinstance(source_report, dict) else {}
    return {
        "run_id": run_id,
        "site_id": report.get("site_id", ""),
        "site_name": report.get("site_name", ""),
        "status": report.get("status", ""),
        "risk_level": report.get("risk_level", ""),
        "reason_codes": list(report.get("reason_codes") or []),
        "item_count": int(report.get("item_count", 0) or 0),
        "baseline_median": report.get("baseline_median"),
        "page_stat": page_stat if isinstance(page_stat, dict) else (report.get("detail") or {}).get("page_stat"),
        "extraction_rates": extraction_rates,
        "retry": retry if retry is not None else {"attempt": 0, "max": 2},
        "baseline_eligible": baseline_eligible(report),
    }


def new_run_id(when: datetime | None = None) -> str:
    """UTC run_id: YYYYMMDDTHHMMSSZ."""
    moment = when or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def append_source_run(
    record: dict[str, Any],
    path: Path | None = None,
) -> bool:
    """JSONL 한 줄 append. 실패해도 본수집을 막지 않도록 False 반환."""
    target = path or SOURCE_RUN_LEDGER_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except Exception:
        return False


def append_source_runs(
    records: list[dict[str, Any]],
    path: Path | None = None,
) -> int:
    """여러 행 append. 성공한 행 수 반환."""
    ok = 0
    for record in records or []:
        if append_source_run(record, path=path):
            ok += 1
    return ok


def iter_runs(path: Path | None = None) -> Iterator[dict[str, Any]]:
    """ledger 를 앞에서부터 순회. 깨진 줄은 건너뛴다."""
    target = path or SOURCE_RUN_LEDGER_PATH
    if not target.exists():
        return
        yield  # pragma: no cover — generator 타입 유지
    try:
        text = target.read_text(encoding="utf-8")
    except Exception:
        return
        yield  # pragma: no cover
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            yield row
