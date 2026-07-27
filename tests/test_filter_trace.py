# -*- coding: utf-8 -*-
"""filter_trace 스키마·시트 평탄화 단위 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations.filter_trace import (  # noqa: E402
    SHEET_HEADERS,
    append_jsonl,
    build_trace,
    flatten_for_sheet,
)
from mail_core.storage import filter_trace_sheet as sheet  # noqa: E402


def test_build_trace_context_and_flatten():
    tr = build_trace(
        notice_id="n1",
        group_id="grp_ai_saas",
        site_id="bizinfo",
        core=True,
        bucket="included",
        title="AI SaaS",
        stages=[
            {"step": "extract", "ok": True, "status": "SUCCESS", "reasons": []},
            {"step": "hard_exclude", "ok": True, "reasons": []},
            {"step": "region", "ok": True, "status": "NOT_SPECIFIED", "reasons": ["APPLICANT_SCOPE_UNSTATED"]},
            {"step": "keyword", "ok": True, "status": "STRONG", "reasons": ["OR_HIT:AI"]},
            {"step": "track", "ok": True, "status": "MAIN", "reasons": ["CORE_STRONG_UNSPECIFIED"]},
        ],
    )
    assert "Core/bizinfo" in tr["context"]
    assert "bucket=included" in tr["context"]
    row = flatten_for_sheet(tr)
    assert list(row.keys()) == SHEET_HEADERS
    assert row["keyword_status"] == "STRONG"
    assert "OR_HIT:AI" in row["reasons"]


def test_append_jsonl(tmp_path):
    tr = build_trace(
        notice_id="n2",
        group_id="g",
        bucket="review",
        stages=[{"step": "extract", "ok": False, "status": "DETAIL_FETCH_FAILED", "reasons": ["http_no_response"]}],
    )
    path = tmp_path / "t.jsonl"
    append_jsonl([tr], path=path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["bucket"] == "review"


def test_sheet_not_configured_returns_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    monkeypatch.delenv("FILTER_TRACE_SHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", raising=False)
    monkeypatch.setattr(sheet, "_service_account_info", lambda: None)
    out = sheet.append_traces_to_sheet([{"notice_id": "x", "stages": [], "source": {}}])
    assert out["ok"] is False
    assert out["error"] == "sheet_not_configured"
    # 시트 ID는 설정/기본값으로 잡혀 있어도 SA 없으면 configured=False
    assert out["sheet_id"]
    assert "1e95jsQ0UfILu6GvUrR3G1E0HNBv3aXOGCsc32YCbh1E" in sheet.sheet_url()


def test_default_sheet_id_resolves():
    assert sheet._sheet_id() == "1e95jsQ0UfILu6GvUrR3G1E0HNBv3aXOGCsc32YCbh1E"
    assert sheet._tab_name() == "filter_trace"
