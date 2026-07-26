# -*- coding: utf-8 -*-
"""오늘(2026-07-26) 메일 리뷰 후속 — P0 노이즈·워치캡·멱등스킵·기준선 부족."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.delivery import state as delivery_state  # noqa: E402
from mail_core.delivery.skip_gate import (  # noqa: E402
    planned_delivery_units,
    should_skip_fetch_already_delivered,
)
from mail_core.matching.watchlist_select import select_watchlist_hits  # noqa: E402
from mail_core.operations import coverage_alert as ca  # noqa: E402
from mail_core.operations import detector_config as dc  # noqa: E402


def _row(**kw) -> dict:
    base = dict(
        site_id="x", site_name="X", url="https://x",
        enabled=True, collector_fn="fetch_html_generic",
        fetch_success=True, fetch_error="",
        item_count=0, posted_parsed_count=0, date_unknown_count=0,
        detail_link_ok_count=0,
        valid_record_count=0, suspicious_content_count=0,
    )
    base.update(kw)
    return base


def test_insufficient_baseline_zero_is_not_suspicious():
    """기준선 부족 0건은 ZERO_SUSPICIOUS/P1 이 아니라 판정 보류(SUCCESS)."""
    report = ca.classify_source_status(_row(), [])
    assert report["status"] == ca.COLLECT_STATUS_SUCCESS
    assert report["risk_level"] == ""
    assert report["reason_codes"] == []
    assert report["detail"].get("baseline_insufficient") is True


def test_fetch_failed_risk_p1_for_non_core():
    """defaults fetch_failed_risk=P1 — imp 급 접속실패는 P1."""
    cfg = {
        "defaults": {"fetch_failed_risk": "P1"},
        "sites": {"bizinfo": {"fetch_failed_risk": "P0"}},
    }
    rows = [
        _row(site_id="imp_abc", fetch_success=False, fetch_error="timeout"),
        _row(site_id="bizinfo", fetch_success=False, fetch_error="timeout"),
    ]
    reports = ca.classify_sources(rows, {}, detector_cfg=cfg)
    by_id = {r["site_id"]: r for r in reports}
    assert by_id["imp_abc"]["reason_codes"] == [ca.REASON_FETCH_FAILED]
    assert by_id["imp_abc"]["risk_level"] == "P1"
    assert by_id["bizinfo"]["risk_level"] == "P0"


def test_real_detector_json_core_stays_p0_on_fetch_fail():
    cfg = dc.load_detector_config()
    assert dc.fetch_failed_risk_for_site(cfg, "bizinfo") == "P0"
    assert dc.fetch_failed_risk_for_site(cfg, "imp_dead") == "P1"


def test_p0_alert_digest_collapses_imp_prefix():
    sources = [
        {"site_id": "mss", "site_name": "중기부", "status": "FAILED",
         "risk_level": "P0", "reason_codes": [ca.REASON_FETCH_FAILED], "detail": {}},
    ] + [
        {"site_id": f"imp_{i}", "site_name": f"imp{i}", "status": "FAILED",
         "risk_level": "P0", "reason_codes": [ca.REASON_FETCH_FAILED], "detail": {}}
        for i in range(30)
    ]
    payload = {
        "active_expected": 200,
        "sources": sources,
        "run_status": "DEGRADED",
        "recheck_site_ids": [s["site_id"] for s in sources],
    }
    md = ca.render_p0_alert_markdown(payload)
    assert "중기부" in md
    assert "imp_* 접속실패 30건" in md
    assert md.count("\n- ") < 20  # 37줄 나열 없음
    msg = ca.format_p0_alert_message(payload)
    assert "imp_*" in msg


def test_watchlist_select_caps_old_url_board_hits():
    today = date(2026, 7, 26)
    items = []
    for i in range(50):
        items.append({
            "id": f"old{i}",
            "title": f"old {i}",
            "posted_date": "2025-01-01",
            "link": "https://pms.ripc.org/pms/biz/smallBusiness/x",
        })
    for i in range(5):
        items.append({
            "id": f"new{i}",
            "title": f"new {i}",
            "posted_date": "2026-07-20",
            "link": "https://pms.ripc.org/pms/biz/smallBusiness/y",
        })
    items.append({
        "id": "kw1",
        "title": "지식재산 활용 지원",
        "posted_date": "2025-01-01",
        "link": "https://other.kr/1",
    })

    def kind(it: dict) -> str:
        if "지식재산 활용" in it["title"]:
            return "keyword"
        if "ripc.org" in it["link"]:
            return "url"
        return ""

    selected = select_watchlist_hits(
        items, match_kind=kind, max_items=20, url_max_age_days=14, today=today,
    )
    ids = {it["id"] for it in selected}
    assert "kw1" in ids
    assert all(not iid.startswith("old") for iid in ids)
    assert len(selected) <= 20
    assert len([i for i in selected if i["id"].startswith("new")]) == 5


def test_skip_gate_when_all_units_delivered(tmp_path):
    groups = [{
        "id": "grp_a", "active": True, "tenant_id": "default",
        "recipients": ["a@example.com"],
    }]
    settings = {"tenant_id": "default", "raw_all_enabled": False}
    path = tmp_path / "delivery_state.json"
    key = delivery_state.key("2026-07-24", "grp_a", "a@example.com", tenant="default")
    delivery_state.save(path, {key})

    units = planned_delivery_units(
        target_date="2026-07-24", groups=groups, settings=settings,
    )
    assert len(units) == 1

    result = should_skip_fetch_already_delivered(
        target_date="2026-07-24",
        groups=groups,
        settings=settings,
        delivery_path=path,
        enabled=True,
    )
    assert result["skip"] is True
    assert result["reason"] == "already_delivered"

    result2 = should_skip_fetch_already_delivered(
        target_date="2026-07-24",
        groups=groups,
        settings=settings,
        delivery_path=path,
        enabled=False,
    )
    assert result2["skip"] is False
