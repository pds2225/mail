"""MAIL-P0D-01(TASK-026) — 공고별 파이프라인 단계 추적(notice_pipeline_trace) 회귀테스트."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

import monitor as m  # noqa: E402
from mail_core.operations import notice_pipeline_trace as npt  # noqa: E402


# ── 모듈 단위 테스트 ──────────────────────────────────────────────────────

def test_record_stage_writes_entry_keyed_by_notice_and_stage():
    trace: dict = {}
    npt.record_stage(trace, "n1", "FETCH", "SUCCESS")
    assert trace["n1"]["FETCH"]["status"] == "SUCCESS"
    assert trace["n1"]["FETCH"]["error_code"] == ""
    assert "at" in trace["n1"]["FETCH"]


def test_record_stage_with_group_id_keeps_stages_separate_per_group():
    trace: dict = {}
    npt.record_stage(trace, "n1", "EVALUATE", "SUCCESS", group_id="g1")
    npt.record_stage(trace, "n1", "EVALUATE", "FAILED", group_id="g2", error_code="REGION_NOT_ELIGIBLE")
    assert trace["n1"]["EVALUATE:g1"]["status"] == "SUCCESS"
    assert trace["n1"]["EVALUATE:g2"]["status"] == "FAILED"
    assert trace["n1"]["EVALUATE:g2"]["error_code"] == "REGION_NOT_ELIGIBLE"


def test_record_stage_ignores_unknown_stage_or_status():
    trace: dict = {}
    npt.record_stage(trace, "n1", "NOT_A_STAGE", "SUCCESS")
    npt.record_stage(trace, "n1", "FETCH", "NOT_A_STATUS")
    npt.record_stage(trace, "", "FETCH", "SUCCESS")
    assert trace == {}


def test_record_stage_never_logs_pii_or_full_body():
    """민감정보 로그 금지 — record_stage 는 notice_id/stage/status/error_code/시각만 받는다."""
    trace: dict = {}
    npt.record_stage(trace, "n1", "FETCH", "SUCCESS", error_code="x" * 200)
    entry = trace["n1"]["FETCH"]
    assert set(entry) == {"status", "error_code", "at"}
    assert len(entry["error_code"]) <= 80  # 과도한 원문 유입을 자르는 안전장치


def test_flatten_records_produces_one_row_per_notice():
    trace = {"n1": {"FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"}},
             "n2": {"FETCH": {"status": "FAILED", "error_code": "TIMEOUT", "at": "x"}}}
    rows = npt.flatten_records("run1", trace)
    by_id = {r["notice_id"]: r for r in rows}
    assert by_id["n1"]["run_id"] == "run1"
    assert by_id["n1"]["stages"]["FETCH"]["status"] == "SUCCESS"
    assert by_id["n2"]["stages"]["FETCH"]["error_code"] == "TIMEOUT"


def test_append_and_iter_notice_traces_roundtrip(tmp_path):
    path = tmp_path / "trace.jsonl"
    rows = [{"run_id": "r1", "notice_id": "n1", "recorded_at": "x", "stages": {"FETCH": {"status": "SUCCESS"}}}]
    written = npt.append_notice_traces(rows, path=path)
    assert written == path
    loaded = list(npt.iter_notice_traces(path))
    assert loaded == rows


def test_append_notice_traces_empty_rows_is_noop(tmp_path):
    path = tmp_path / "trace.jsonl"
    assert npt.append_notice_traces([], path=path) is None
    assert not path.exists()


def test_append_notice_traces_never_raises_on_bad_path(tmp_path):
    """best-effort — 쓰기 불가능한 경로여도 예외를 상위로 올리지 않는다(발송 흐름 차단 금지).

    Windows 전용 드라이브 경로(예: "Z:\\...")는 POSIX(CI=Ubuntu)에서 유효한 상대경로로
    취급돼 재현되지 않으므로, 두 OS에서 동일하게 실패하는 "파일을 디렉터리처럼 쓰기"로
    검증한다 — mkdir(parents=True)가 NotADirectoryError/FileExistsError를 낸다.
    """
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("x", encoding="utf-8")
    bad_path = blocking_file / "sub" / "trace.jsonl"
    result = npt.append_notice_traces([{"notice_id": "n1"}], path=bad_path)
    assert result is None  # 실패해도 조용히 None


def test_iter_notice_traces_skips_corrupt_lines(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text('{"notice_id": "ok"}\nnot-json\n{"notice_id": "ok2"}\n', encoding="utf-8")
    rows = list(npt.iter_notice_traces(path))
    assert [r["notice_id"] for r in rows] == ["ok", "ok2"]


def test_iter_notice_traces_missing_file_yields_nothing(tmp_path):
    assert list(npt.iter_notice_traces(tmp_path / "nope.jsonl")) == []


# ── execute_monitor 파이프라인 통합 테스트 ───────────────────────────────

def test_execute_monitor_records_stage_trace_across_pipeline(monkeypatch):
    """MAIL-P0D-01: 공고 1건이 FETCH→NORMALIZE→ENRICH→EVALUATE→COMPANY_MATCH→SUMMARIZE
    를 거치며 각 단계 기록을 남기는지 확인한다(디스크 flush 는 persist_seen 게이트라
    여기서는 record_stage 호출 자체를 캡처해 검증한다 — 실제 발송·저장 없음)."""
    calls: list[tuple] = []
    real_record = npt.record_stage

    def _capture(trace, notice_id, stage, status, **kw):
        calls.append((str(notice_id), stage, status, kw.get("group_id", ""), kw.get("error_code", "")))
        return real_record(trace, notice_id, stage, status, **kw)

    monkeypatch.setattr(npt, "record_stage", _capture)

    items = [
        {"id": "trace1", "title": "지식재산 활용 지원사업 공고", "description": "", "link": "https://x/1",
         "author": "기관", "deadline": "2099-12-31", "source": "RIPC", "posted_date": "2000-01-01",
         "is_aggregator": False, "detail_extraction": {"status": "SUCCESS"}},
    ]
    monkeypatch.setattr(m, "fetch_all", lambda sites, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{"id": "g", "name": "t", "active": True,
                                                    "or_keywords": ["지식재산"], "recipients": []}])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": True, "days_back": 1, "raw_all_enabled": False,
        "raw_all_recipients": [], "company_match_enabled": False,
    })
    monkeypatch.setattr(m, "load_watchlist", lambda: {
        "keywords": ["지식재산"], "urls": [], "recipients": ["test-recipient@example.test"]})
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: None)
    monkeypatch.setattr(m, "alert_ntfy", lambda *a, **k: None)

    m.execute_monitor(allow_send=True, include_raw_all=False, persist_seen=False)

    stages_for_trace1 = {(stage, status) for (nid, stage, status, gid, code) in calls if nid == "trace1"}
    # 워치리스트 강제포함 경로라 그룹 EVALUATE/COMPANY_MATCH/SUMMARIZE 는 거치지 않을 수
    # 있지만(별도 전용 메일 경로), 공통 파이프라인 단계(FETCH/NORMALIZE/ENRICH)는 반드시
    # 기록돼야 한다 — "모든 후보 단계이력 존재"의 최소 보장선.
    assert ("FETCH", "SUCCESS") in stages_for_trace1
    assert ("NORMALIZE", "SUCCESS") in stages_for_trace1
    assert ("ENRICH", "SUCCESS") in stages_for_trace1


def test_execute_monitor_records_evaluate_failure_reason_code(monkeypatch):
    """그룹 키워드에 안 맞아 제외된 공고는 EVALUATE=FAILED + reason_code 가 기록돼야 한다."""
    calls: list[tuple] = []
    real_record = npt.record_stage

    def _capture(trace, notice_id, stage, status, **kw):
        calls.append((str(notice_id), stage, status, kw.get("group_id", ""), kw.get("error_code", "")))
        return real_record(trace, notice_id, stage, status, **kw)

    monkeypatch.setattr(npt, "record_stage", _capture)

    items = [
        {"id": "nomatch1", "title": "관련없는 일반 공고", "description": "", "link": "https://x/2",
         "author": "기관", "deadline": "2099-12-31", "source": "s", "posted_date": "2000-01-01",
         "is_aggregator": False, "detail_extraction": {"status": "SUCCESS"}},
    ]
    monkeypatch.setattr(m, "fetch_all", lambda sites, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{"id": "g", "name": "t", "active": True,
                                                    "or_keywords": ["존재하지않는키워드zzz"], "recipients": []}])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": True, "days_back": 1, "raw_all_enabled": False,
        "raw_all_recipients": [], "company_match_enabled": False,
    })
    monkeypatch.setattr(m, "load_watchlist", lambda: {"keywords": [], "urls": [], "recipients": []})
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: None)

    m.execute_monitor(allow_send=False, include_raw_all=False, persist_seen=False)

    evaluate_entries = [c for c in calls if c[0] == "nomatch1" and c[1] == "EVALUATE"]
    assert evaluate_entries, "그룹 평가를 거친 공고는 EVALUATE 기록이 있어야 한다"
    assert evaluate_entries[0][2] == "FAILED"
    assert evaluate_entries[0][4]  # error_code(reason_code)가 비어있지 않아야 함
