# -*- coding: utf-8 -*-
"""P0 산출물 writer·감사 진입점 배선 테스트.

LOGS_DIR를 tmp_path로 monkeypatch 해 실제 repo를 오염시키지 않는다.
메일 발송은 alert_email 을 가로채 캡처만 한다(실발송 0회).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations import coverage_alert as ca  # noqa: E402
import monitor as m  # noqa: E402


def _row(**kw) -> dict:
    base = dict(
        site_id="nipa", site_name="NIPA", url="https://nipa.kr/list",
        enabled=True, collector_fn="fetch_html_generic",
        fetch_success=True, fetch_error="",
        item_count=24, posted_parsed_count=24, date_unknown_count=0,
        detail_link_ok_count=24,
    )
    base.update(kw)
    return base


def _history(count: int = 24, n: int = 7) -> list[dict]:
    return [{"date": f"2026-07-{10 + i:02d}", "item_count": count} for i in range(n)]


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """로그·baseline 경로를 tmp 로 격리하고 메일을 가로챈다."""
    monkeypatch.setattr(m, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(ca, "COVERAGE_BASELINE_PATH", tmp_path / "coverage_baseline.json")
    sent: list[tuple] = []
    monkeypatch.setattr(m, "alert_email", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(
        ca, "load_coverage_baseline",
        lambda path=None: {"nipa": _history(), "b": _history()})
    monkeypatch.setattr(ca, "save_coverage_baseline", lambda *a, **k: None)
    return tmp_path, sent


def test_audit_writes_three_artifacts_and_alerts_on_p0(sandbox):
    tmp, sent = sandbox
    rows = [_row(item_count=0, posted_parsed_count=0, detail_link_ok_count=0)]
    sites = [{"id": "nipa", "name": "NIPA", "enabled": True}]

    result = m.run_source_coverage_audit(rows, sites, allow_alert=True)

    assert result["status"] == "DEGRADED" and result["p0_count"] == 1
    day = m.datetime.now(m.KST).strftime("%Y%m%d")
    assert (tmp / "logs" / f"source_coverage_{day}.json").exists()
    assert (tmp / "logs" / f"source_coverage_{day}.md").exists()
    assert (tmp / "logs" / f"p0_collection_alert_{day}.md").exists()

    payload = json.loads((tmp / "logs" / f"source_coverage_{day}.json").read_text("utf-8"))
    assert payload["run_status"] == "DEGRADED"
    assert payload["sources"][0]["reason_codes"] == [ca.REASON_ZERO_ITEMS_WITH_BASELINE]

    assert len(sent) == 1
    assert "P0" in sent[0][0]


def test_audit_writes_no_p0_file_when_healthy(sandbox):
    tmp, sent = sandbox
    result = m.run_source_coverage_audit([_row()], [{"id": "nipa", "enabled": True}],
                                         allow_alert=True)
    assert result["status"] == "OK"
    day = m.datetime.now(m.KST).strftime("%Y%m%d")
    assert (tmp / "logs" / f"source_coverage_{day}.json").exists()
    assert not (tmp / "logs" / f"p0_collection_alert_{day}.md").exists()
    assert sent == []          # 정상일 때 알림 0회


def test_audit_respects_allow_alert_false(sandbox):
    _tmp, sent = sandbox
    m.run_source_coverage_audit([_row(item_count=0)], [{"id": "nipa", "enabled": True}],
                                allow_alert=False)
    assert sent == []


def test_audit_never_raises_even_when_internals_fail(sandbox, monkeypatch):
    """감사 실패가 수집·발송을 막지 않는다 — 예외 대신 안전한 기본값."""
    monkeypatch.setattr(ca, "classify_sources",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = m.run_source_coverage_audit([_row()], [{"id": "nipa", "enabled": True}])
    assert result["status"] == "OK"       # 실패해도 DEGRADED 로 오판하지 않는다
    assert result["p0_count"] == 0
    assert "audit_error" in result


def test_audit_can_skip_file_writing(sandbox):
    tmp, _sent = sandbox
    result = m.run_source_coverage_audit([_row()], None, allow_alert=False,
                                         write_files=False)
    assert result["files"] == {}
    assert not (tmp / "logs").exists()


# ── 계측(page stats) ────────────────────────────────────────────────────────
def test_page_stats_record_and_reset():
    m.reset_page_stats()
    m._page_stat("s1", stop_reason="MAX_PAGES_HIT", pages_fetched=4)
    m._page_stat("s1", duplicate_page=True)
    snap = m.page_stats_snapshot()
    assert snap["s1"]["stop_reason"] == "MAX_PAGES_HIT"
    assert snap["s1"]["duplicate_page"] is True
    assert snap["s1"]["pages_fetched"] == 4
    m.reset_page_stats()
    assert m.page_stats_snapshot() == {}


def test_page_stats_kill_switch(monkeypatch):
    m.reset_page_stats()
    monkeypatch.setenv("MONITOR_NO_PAGE_STATS", "1")
    m._page_stat("s1", stop_reason="MAX_PAGES_HIT")
    assert m.page_stats_snapshot() == {}


def test_page_stat_never_raises():
    m.reset_page_stats()
    m._page_stat("")            # 빈 site_id
    m._page_stat(None)          # type: ignore[arg-type]
    assert m.page_stats_snapshot() == {}


# ── coverage row 신규 필드 ──────────────────────────────────────────────────
def test_fetch_site_coverage_populates_new_fields(monkeypatch):
    """상세링크·중복·레코드 품질 지표가 실제로 집계된다."""
    site = {"id": "s", "name": "S", "type": "html_table",
            "url": "https://x.kr/list", "enabled": True}
    items = [
        {"id": "1", "title": "A", "link": "https://x.kr/view?id=1", "posted_date": ""},
        {"id": "2", "title": "B", "link": "https://x.kr/view?id=2", "posted_date": ""},
        {"id": "2", "title": "B", "link": "https://x.kr/view?id=2", "posted_date": ""},
        {"id": "3", "title": "C", "link": "https://x.kr/list", "posted_date": ""},
    ]
    monkeypatch.setitem(m.FETCHERS, "html_table", lambda s: items)

    rows = m.fetch_site_coverage([site])

    assert len(rows) == 1
    row = rows[0]
    assert row["item_count"] == 4
    assert row["detail_link_ok_count"] == 3   # 목록 URL 그대로인 1건 제외
    assert row["dedup_removed_estimate"] == 1  # 중복 id 1건
    assert row["valid_record_count"] == 4
    assert row["suspicious_content_count"] == 0
    for key in ("collect_status", "reason_codes", "risk_level"):
        assert key in row


def test_disabled_site_row_has_new_fields(monkeypatch):
    rows = m.fetch_site_coverage([{"id": "s", "name": "S", "type": "html_table",
                                   "url": "u", "enabled": False}])
    assert rows[0]["fetch_error"] == "disabled_in_config"
    assert rows[0]["detail_link_ok_count"] == 0
    assert rows[0]["valid_record_count"] == 0
    assert rows[0]["suspicious_content_count"] == 0
    report = ca.classify_source_status(rows[0], None)
    assert report["status"] == ca.COLLECT_STATUS_SKIPPED


def test_fetch_site_coverage_counts_invalid_and_suspicious_records(monkeypatch):
    site = {"id": "s", "name": "S", "type": "html_table",
            "url": "https://x.kr/list", "enabled": True}
    items = [
        {"id": "1", "title": "정상 공고", "link": "https://x.kr/1", "posted_date": ""},
        {"id": "2", "title": "로그인 후 이용해 주세요", "link": "https://x.kr/login",
         "description": "자동입력방지 CAPTCHA", "posted_date": ""},
        {"id": "", "title": "제목만 있음", "link": "", "posted_date": None},
        "unexpected raw text",
    ]
    monkeypatch.setitem(m.FETCHERS, "html_table", lambda s: items)

    row = m.fetch_site_coverage([site])[0]

    assert row["fetch_success"] is True
    assert row["item_count"] == 4
    assert row["valid_record_count"] == 2
    assert row["suspicious_content_count"] == 1
