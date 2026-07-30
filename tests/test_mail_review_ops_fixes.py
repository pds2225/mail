# -*- coding: utf-8 -*-
"""오늘(2026-07-26) 메일 리뷰 후속 — P0 노이즈·워치캡·멱등스킵·기준선 부족."""
from __future__ import annotations

import sys
from datetime import date, datetime
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


# ── 2026-07-30 발송 누락 사고 회귀 (days_back 1→3 → 멱등 오판으로 이틀 미발송) ──────────
#   증상: 07-28·07-29 클라우드 run 이 2분 44초에 끝나며 "기준일 2026-07-24 발송 단위 6개
#   멱등 완료 — 커버리지·수집·발송 생략" 로그만 남기고 digest 를 보내지 않았다.
#   원인: 발송 멱등 키의 기준일이 재조회창의 가장 오래된 날이라, days_back 을 1→3 으로
#   늘린 순간(2026-07-25) 기준일이 이미 발송 완료된 과거 날짜로 후퇴했다.

def test_delivery_cycle_date_does_not_regress_when_days_back_grows():
    """기준값은 실행 당일 회차 — days_back 을 늘려도 과거로 후퇴하지 않는다."""
    import monitor

    now = datetime(2026, 7, 29, 9, 0, tzinfo=monitor.KST)

    assert monitor.delivery_cycle_date(now) == "2026-07-29#am"
    # 사고 당시 기준일 계산식은 days_back 에 따라 과거로 밀렸다(07-28 → 07-24).
    assert monitor.previous_business_day(now, 3) == date(2026, 7, 24)
    for days_back in (1, 2, 3, 5, 10):
        assert monitor.delivery_cycle_date(now) == "2026-07-29#am", days_back


# ── 하루 2회 발송(07:30·18:30 KST, 2026-07-30 사용자 지정) ────────────────────────────

def test_am_and_pm_runs_have_separate_cycles():
    """오전·오후 실행은 다른 회차 키를 쓰고, 예약 지연에도 회차가 흔들리지 않는다."""
    import monitor

    def cycle(hour: int, minute: int = 30) -> str:
        return monitor.delivery_cycle_date(
            datetime(2026, 7, 30, hour, minute, tzinfo=monitor.KST)
        )

    assert cycle(7) == "2026-07-30#am"      # 예약 07:30
    assert cycle(18) == "2026-07-30#pm"     # 예약 18:30
    assert cycle(7) != cycle(18)
    # GitHub 예약 지연 흡수: 오전분이 최대 6시간 늦어도 am, 오후분은 항상 pm
    assert cycle(13, 59) == "2026-07-30#am"
    assert cycle(14) == "2026-07-30#pm"
    assert cycle(23, 59) == "2026-07-30#pm"


def test_pm_run_not_skipped_after_am_delivered(tmp_path):
    """오전 발송 완료 뒤 오후 실행이 '이미 보냄'으로 스킵되지 않는다(2회 발송 핵심)."""
    import monitor

    groups = [{
        "id": "grp_a", "active": True, "tenant_id": "default",
        "recipients": ["a@example.com"],
    }]
    settings = {"tenant_id": "default", "raw_all_enabled": False, "days_back": 3}
    path = tmp_path / "delivery_state.json"

    am = monitor.delivery_cycle_date(datetime(2026, 7, 30, 7, 30, tzinfo=monitor.KST))
    pm = monitor.delivery_cycle_date(datetime(2026, 7, 30, 18, 30, tzinfo=monitor.KST))
    delivery_state.save(
        path, {delivery_state.key(am, "grp_a", "a@example.com", tenant="default")},
    )

    am_again = should_skip_fetch_already_delivered(
        target_date=am, groups=groups, settings=settings,
        delivery_path=path, enabled=True,
    )
    assert am_again["skip"] is True  # 같은 회차 재실행은 계속 막는다

    pm_run = should_skip_fetch_already_delivered(
        target_date=pm, groups=groups, settings=settings,
        delivery_path=path, enabled=True,
    )
    assert pm_run["skip"] is False
    assert pm_run["reason"] == "pending_units"


def test_delivery_state_prune_keeps_thirty_days_of_two_cycles():
    """하루 2회차여도 약 30일치 발송기록이 남는다(회차 도입으로 반토막 방지)."""
    from mail_core.delivery import state as st

    assert st.MAX_KEEP_DATES >= 60
    keys = {
        st.key(f"2026-06-{day:02d}#{slot}", "grp_a", "a@example.com")
        for day in range(1, 31) for slot in ("am", "pm")
    }
    assert st._prune(set(keys)) == keys  # 30일 × 2회차는 전부 보존


def test_days_back_increase_does_not_skip_today_send(tmp_path):
    """옛 기준일(07-23·07-24)이 발송 완료여도 오늘(07-29) 발송은 스킵되지 않는다."""
    import monitor

    groups = [{
        "id": "grp_a", "active": True, "tenant_id": "default",
        "recipients": ["a@example.com"],
    }]
    settings = {"tenant_id": "default", "raw_all_enabled": False, "days_back": 3}
    path = tmp_path / "delivery_state.json"
    delivered = {
        delivery_state.key(old, "grp_a", "a@example.com", tenant="default")
        for old in ("2026-07-23", "2026-07-24")
    }
    delivery_state.save(path, delivered)

    now = datetime(2026, 7, 29, 9, 0, tzinfo=monitor.KST)
    result = should_skip_fetch_already_delivered(
        target_date=monitor.delivery_cycle_date(now),
        groups=groups,
        settings=settings,
        delivery_path=path,
        enabled=True,
    )
    assert result["skip"] is False
    assert result["reason"] == "pending_units"
    assert result["target_date"] == "2026-07-29#am"


def test_same_day_rerun_still_skips(tmp_path):
    """같은 날 재실행은 계속 멱등으로 막는다(주말 재실행 2h+ 낭비 방지 의도 유지)."""
    import monitor

    groups = [{
        "id": "grp_a", "active": True, "tenant_id": "default",
        "recipients": ["a@example.com"],
    }]
    settings = {"tenant_id": "default", "raw_all_enabled": False, "days_back": 3}
    path = tmp_path / "delivery_state.json"
    now = datetime(2026, 7, 29, 9, 0, tzinfo=monitor.KST)
    today_key = delivery_state.key(
        str(monitor.delivery_cycle_date(now)), "grp_a", "a@example.com", tenant="default",
    )
    delivery_state.save(path, {today_key})

    result = should_skip_fetch_already_delivered(
        target_date=str(monitor.delivery_cycle_date(now)),
        groups=groups,
        settings=settings,
        delivery_path=path,
        enabled=True,
    )
    assert result["skip"] is True
    assert result["reason"] == "already_delivered"


def test_send_path_uses_run_day_for_delivery_key():
    """실발송 경로(execute_monitor)가 재조회창 끝이 아닌 실행 당일을 멱등 키로 쓴다."""
    import inspect

    import monitor

    src = inspect.getsource(monitor.execute_monitor)
    assert "target_date = delivery_cycle_date(now)" in src
    assert "target_date = recheck_dates[0]" not in src
