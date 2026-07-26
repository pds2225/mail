# -*- coding: utf-8 -*-
"""W1: 사이트별 detector 정책 — 동일 0건이라도 A=P0 / B=warning 분기."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations import coverage_alert as ca  # noqa: E402
from mail_core.operations import detector_config as dc  # noqa: E402


def _row(**kw) -> dict:
    base = dict(
        site_id="nipa", site_name="NIPA", url="https://nipa.kr/list",
        enabled=True, collector_fn="fetch_html_generic",
        fetch_success=True, fetch_error="",
        item_count=0, posted_parsed_count=0, date_unknown_count=0,
        detail_link_ok_count=0,
        valid_record_count=0, suspicious_content_count=0,
    )
    base.update(kw)
    return base


def _history(count: int = 24, n: int = 7) -> list[dict]:
    return [{"date": f"2026-07-{10 + i:02d}", "item_count": count} for i in range(n)]


def test_same_zero_items_p0_vs_warning_by_policy():
    """동일 0건·동일 기준선 — policy 만 다르면 등급이 갈린다."""
    history = _history()
    row = _row(site_id="x")

    p0 = ca.classify_source_status(
        row, history, zero_item_policy="p0_if_baseline")
    warn = ca.classify_source_status(
        row, history, zero_item_policy="warning")
    ignore = ca.classify_source_status(
        row, history, zero_item_policy="ignore_zero")

    assert p0["risk_level"] == "P0"
    assert ca.REASON_ZERO_ITEMS_WITH_BASELINE in p0["reason_codes"]

    assert warn["risk_level"] == "P1"
    assert ca.REASON_BASELINE_INSUFFICIENT in warn["reason_codes"]
    assert warn["detail"].get("zero_warning") is True

    assert ignore["status"] == ca.COLLECT_STATUS_SUCCESS
    assert ignore["risk_level"] == ""
    assert ignore["reason_codes"] == []


def test_classify_sources_applies_detector_cfg_per_site():
    """bizinfo=p0, itp=warning — 둘 다 0건이어도 등급이 다르다."""
    cfg = {
        "defaults": {"zero_item_policy": "p0_if_baseline", "drop_ratio_p0": 0.2},
        "sites": {
            "bizinfo": {"zero_item_policy": "p0_if_baseline"},
            "itp": {"zero_item_policy": "warning"},
        },
    }
    rows = [
        _row(site_id="bizinfo", site_name="기업마당"),
        _row(site_id="itp", site_name="인천TP"),
    ]
    baseline = {"bizinfo": _history(), "itp": _history()}
    reports = ca.classify_sources(rows, baseline, detector_cfg=cfg)
    by_id = {r["site_id"]: r for r in reports}

    assert by_id["bizinfo"]["risk_level"] == "P0"
    assert by_id["itp"]["risk_level"] == "P1"


def test_real_detector_sites_json_pilots_diverge():
    """실파일 기준: bizinfo 엄격, itp warning."""
    cfg = dc.load_detector_config()
    assert dc.zero_item_policy_for_site(cfg, "bizinfo") == "p0_if_baseline"
    assert dc.zero_item_policy_for_site(cfg, "itp") == "warning"

    rows = [
        _row(site_id="bizinfo", site_name="기업마당"),
        _row(site_id="itp", site_name="인천TP"),
    ]
    baseline = {"bizinfo": _history(30), "itp": _history(5)}
    reports = ca.classify_sources(rows, baseline, detector_cfg=cfg)
    by_id = {r["site_id"]: r for r in reports}
    assert by_id["bizinfo"]["risk_level"] == "P0"
    assert by_id["itp"]["risk_level"] == "P1"


def test_site_drop_ratio_override_changes_grade():
    """drop_ratio_p0 오버라이드로 같은 급감이 P0/통과로 갈린다."""
    history = _history(count=100)
    # 오늘 40건 → 잔존 0.4
    row = _row(site_id="s", item_count=40, posted_parsed_count=40,
               detail_link_ok_count=40, valid_record_count=40, date_unknown_count=0)

    strict = ca.classify_source_status(
        row, history, thresholds={"drop_ratio_p0": 0.5, "drop_ratio_p1": 0.7})
    # 0.4 < 0.5 → P0
    assert ca.REASON_COLLECTION_DROP_HIGH in strict["reason_codes"]
    assert strict["risk_level"] == "P0"

    loose = ca.classify_source_status(
        row, history, thresholds={"drop_ratio_p0": 0.2, "drop_ratio_p1": 0.35})
    # 0.4 >= 0.35 → 급감 아님
    assert ca.REASON_COLLECTION_DROP_HIGH not in loose["reason_codes"]
