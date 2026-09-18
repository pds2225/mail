"""notice_pipeline_trace — MAIL-P0D-01: 공고별 파이프라인 단계 추적.

각 공고가 Fetch→Enrich→Normalize→Evaluate→Company Match→Summarize 중
어디까지·어떤 결과로 갔는지 run_id+notice_id 기준으로 기록한다.

이 모듈은 실행을 절대 막지 않는 best-effort 부가 기록 계층이다
(source_run_ledger.py·filter_trace.py와 동일한 원칙: 예외를 삼키고 상위로
전파하지 않는다). 메일 원문·개인정보·토큰은 기록하지 않는다 — notice_id·
stage·status·error_code·group_id·timestamp만 남긴다.

NORMALIZE 단계는 별도 함수가 없다(공고 필드 정규화는 수집·enrich 파서에
접혀 있음) — FETCH가 SUCCESS면 NORMALIZE도 함께 SUCCESS로 기록한다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mail_core.paths import LOGS_DIR

STAGES = ("FETCH", "NORMALIZE", "ENRICH", "EVALUATE", "COMPANY_MATCH", "SUMMARIZE")
STATUSES = ("SUCCESS", "PARTIAL", "FAILED", "SKIPPED")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_stage(
    trace: dict[str, dict[str, dict]],
    notice_id: str,
    stage: str,
    status: str,
    *,
    error_code: str = "",
    group_id: str = "",
) -> None:
    """진행 중인 run의 in-memory trace(dict)에 한 단계 기록을 남긴다.

    group_id 가 있으면(Evaluate/Company Match/Summarize 는 그룹별로 결과가
    다를 수 있다) stage 키에 붙여 그룹별로 구분해 기록한다. 알 수 없는
    stage/status 는 조용히 무시한다(오타로 인한 크래시 방지).
    """
    nid = str(notice_id or "").strip()
    if not nid or stage not in STAGES or status not in STATUSES:
        return
    key = f"{stage}:{group_id}" if group_id else stage
    trace.setdefault(nid, {})[key] = {
        "status": status,
        "error_code": str(error_code or "")[:80],
        "at": _utc_now(),
    }


def flatten_records(run_id: str, trace: dict[str, dict[str, dict]]) -> list[dict[str, Any]]:
    """저장용 평탄화: run_id+notice_id 기준 1행(stages 는 그 공고의 전체 단계이력)."""
    return [
        {"run_id": run_id, "notice_id": notice_id, "recorded_at": _utc_now(), "stages": stages}
        for notice_id, stages in trace.items()
    ]


def notice_trace_path(day: str | None = None) -> Path:
    d = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    return LOGS_DIR / f"notice_stage_trace_{d}.jsonl"


def append_notice_traces(rows: list[dict[str, Any]], path: Path | None = None) -> Path | None:
    """best-effort JSONL append. 쓰기 실패는 절대 예외로 상위(발송 흐름)에 전파하지 않는다."""
    if not rows:
        return None
    target = path or notice_trace_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return target
    except Exception:
        return None


def iter_notice_traces(path: Path):
    """저장된 trace를 읽어들인다(진단·리포트용). 손상된 줄은 건너뛴다."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return
