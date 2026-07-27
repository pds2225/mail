"""filter_trace — 공고×그룹 필터 단계 기록 (로컬 JSONL + 시트 행 변환).

Google Sheets 적립은 mail_core.storage.filter_trace_sheet 가 담당.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mail_core.paths import LOGS_DIR

# 시트/CSV 공통 헤더 (누적 적립용 평탄화)
SHEET_HEADERS = [
    "recorded_at",
    "run_id",
    "notice_id",
    "group_id",
    "site_id",
    "core",
    "bucket",
    "extract_status",
    "hard_ok",
    "region_status",
    "keyword_status",
    "track_status",
    "reasons",
    "context",
    "title",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stage_status(stages: list[dict[str, Any]] | None, step: str) -> str:
    for st in stages or []:
        if st.get("step") == step:
            return str(st.get("status") or ("ok" if st.get("ok") else "fail"))
    return ""


def stage_ok(stages: list[dict[str, Any]] | None, step: str) -> str:
    for st in stages or []:
        if st.get("step") == step:
            return "TRUE" if st.get("ok") else "FALSE"
    return ""


def all_reasons(stages: list[dict[str, Any]] | None) -> str:
    codes: list[str] = []
    for st in stages or []:
        for r in st.get("reasons") or []:
            s = str(r).strip()
            if s and s not in codes:
                codes.append(s)
    return "|".join(codes)


def context_one_liner(trace: dict[str, Any]) -> str:
    """검수·시트용 한 줄 컨텍스트."""
    src = trace.get("source") or {}
    core = "Core" if src.get("core") else "Non-core"
    site = src.get("site_id") or "?"
    stages = trace.get("stages") or []
    extract = stage_status(stages, "extract") or "?"
    region = stage_status(stages, "region") or "-"
    keyword = stage_status(stages, "keyword") or "-"
    track = stage_status(stages, "track") or "-"
    bucket = trace.get("bucket") or "?"
    return (
        f"{core}/{site} · extract={extract} · region={region} · "
        f"kw={keyword} · track={track} · bucket={bucket}"
    )


def build_trace(
    *,
    notice_id: str,
    group_id: str,
    site_id: str = "",
    core: bool = False,
    stages: list[dict[str, Any]] | None = None,
    bucket: str = "",
    run_id: str = "",
    title: str = "",
    recorded_at: str = "",
) -> dict[str, Any]:
    stages = list(stages or [])
    trace = {
        "notice_id": notice_id,
        "run_id": run_id or _utc_now().replace("-", "").replace(":", ""),
        "group_id": group_id,
        "source": {"site_id": site_id, "core": bool(core)},
        "stages": stages,
        "bucket": bucket,
        "title": (title or "")[:120],
        "recorded_at": recorded_at or _utc_now(),
    }
    trace["context"] = context_one_liner(trace)
    return trace


def flatten_for_sheet(trace: dict[str, Any]) -> dict[str, str]:
    """시트 1행 dict (헤더 키)."""
    stages = trace.get("stages") or []
    src = trace.get("source") or {}
    return {
        "recorded_at": str(trace.get("recorded_at") or _utc_now()),
        "run_id": str(trace.get("run_id") or ""),
        "notice_id": str(trace.get("notice_id") or ""),
        "group_id": str(trace.get("group_id") or ""),
        "site_id": str(src.get("site_id") or ""),
        "core": "TRUE" if src.get("core") else "FALSE",
        "bucket": str(trace.get("bucket") or ""),
        "extract_status": stage_status(stages, "extract"),
        "hard_ok": stage_ok(stages, "hard_exclude"),
        "region_status": stage_status(stages, "region"),
        "keyword_status": stage_status(stages, "keyword"),
        "track_status": stage_status(stages, "track"),
        "reasons": all_reasons(stages),
        "context": str(trace.get("context") or context_one_liner(trace)),
        "title": str(trace.get("title") or "")[:120],
    }


def append_jsonl(traces: list[dict[str, Any]], path: Path | None = None) -> Path:
    """로컬 누적 (git-ignore)."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    target = path or (LOGS_DIR / f"filter_trace_{day}.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        for tr in traces:
            fh.write(json.dumps(tr, ensure_ascii=False, sort_keys=True) + "\n")
    return target
