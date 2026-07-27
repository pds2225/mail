# -*- coding: utf-8 -*-
"""W0: Run SUCCESS/FAILED/send_hold, detector_config, source_run_ledger 계약 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations import coverage_alert as ca  # noqa: E402
from mail_core.operations import detector_config as dc  # noqa: E402
from mail_core.operations import source_run_ledger as ledger  # noqa: E402


def _row(**kw) -> dict:
    base = dict(
        site_id="nipa", site_name="NIPA", url="https://nipa.kr/list",
        enabled=True, collector_fn="fetch_html_generic",
        fetch_success=True, fetch_error="",
        item_count=24, posted_parsed_count=24, date_unknown_count=0,
        detail_link_ok_count=24,
        valid_record_count=24, suspicious_content_count=0,
    )
    base.update(kw)
    return base


def _history(count: int = 24, n: int = 7) -> list[dict]:
    return [{"date": f"2026-07-{10 + i:02d}", "item_count": count} for i in range(n)]


def test_normalize_ok_alias_is_success():
    assert ca.normalize_run_status("OK") == ca.RUN_STATUS_SUCCESS
    assert ca.normalize_run_status("SUCCESS") == ca.RUN_STATUS_SUCCESS
    assert ca.normalize_run_status("DEGRADED") == ca.RUN_STATUS_DEGRADED


def test_summary_success_when_all_healthy():
    reports = ca.classify_sources([_row(site_id="a")], {"a": _history()})
    summary = ca.summarize_run_status(reports, {"ok": True, "active_expected": 1, "executed": 1})
    assert summary["status"] == ca.RUN_STATUS_SUCCESS
    assert summary["send_hold"] is False
    assert summary["p0_count"] == 0


def test_summary_degraded_on_source_p0_without_mass_missing():
    """수집 급감 P0 이지만 실행대장은 완전 → DEGRADED, hold 아님."""
    reports = ca.classify_sources(
        [_row(site_id="a"), _row(site_id="b", item_count=0)],
        {"a": _history(), "b": _history()},
    )
    check = {
        "ok": True, "active_expected": 2, "executed": 2,
        "missing_site_ids": [], "missing_sources": [],
    }
    summary = ca.summarize_run_status(reports, check)
    assert summary["status"] == ca.RUN_STATUS_DEGRADED
    assert summary["send_hold"] is False
    assert summary["p0_count"] >= 1


def test_summary_failed_when_missing_ratio_high():
    """활성 2 중 1 미실행(50%≥30%) → FAILED + send_hold."""
    sites = [{"id": "a", "enabled": True}, {"id": "gone", "enabled": True}]
    rows = [_row(site_id="a")]
    check = ca.verify_source_execution(sites, rows)
    summary = ca.summarize_run_status(
        ca.classify_sources(rows, {"a": _history()}), check)
    assert check["ok"] is False
    assert summary["status"] == ca.RUN_STATUS_FAILED
    assert summary["send_hold"] is True
    assert summary["send_hold_reason"] == "RUN_FAILED"
    assert "gone" in summary["recheck_site_ids"]


def test_summary_failed_when_missing_abs_ge_five():
    sites = [{"id": f"s{i}", "enabled": True} for i in range(10)]
    rows = [_row(site_id="s0"), _row(site_id="s1")]  # 8 missing
    check = ca.verify_source_execution(sites, rows)
    summary = ca.summarize_run_status(ca.classify_sources(rows, {}), check)
    assert len(check["missing_site_ids"]) >= 5
    assert summary["status"] == ca.RUN_STATUS_FAILED
    assert summary["send_hold"] is True


def test_is_run_failed_skipped_exec_check_is_safe():
    assert ca.is_run_failed({"skipped": True, "active_expected": 0}) is False
    assert ca.is_run_failed({"ok": True, "active_expected": 0, "missing_site_ids": []}) is False


def test_payload_includes_send_hold_on_failed():
    sites = [{"id": "a", "enabled": True}, {"id": "b", "enabled": True}]
    rows = [_row(site_id="a")]
    reports = ca.classify_sources(rows, {"a": _history()})
    check = ca.verify_source_execution(sites, rows)
    summary = ca.summarize_run_status(reports, check)
    payload = ca.build_coverage_payload(rows, reports, summary, exec_check=check)
    assert payload["run_status"] == ca.RUN_STATUS_FAILED
    assert payload["send_hold"] is True
    md = ca.render_coverage_markdown(payload)
    assert "FAILED" in md and "send_hold" in md


def test_detector_config_loads_pilots():
    cfg = dc.load_detector_config()
    assert "bizinfo" in cfg["sites"]
    assert "nipa" in cfg["sites"]
    assert "itp" in cfg["sites"]
    assert dc.zero_item_policy_for_site(cfg, "itp") == "warning"
    assert dc.zero_item_policy_for_site(cfg, "bizinfo") == "p0_if_baseline"
    th_biz = dc.thresholds_for_site(cfg, "bizinfo")
    th_default = dc.thresholds_for_site(cfg, "unknown_site_xyz")
    assert th_biz["drop_ratio_p0"] == pytest.approx(0.35)
    assert "drop_ratio_p0" in th_default  # defaults


def test_thresholds_drop_threshold_converts_to_ratio():
    cfg = {"defaults": {"drop_threshold": 0.8}, "sites": {}}
    th = dc.thresholds_for_site(cfg, "any")
    assert th["drop_ratio_p0"] == pytest.approx(0.2)


def test_ledger_baseline_eligible_and_append(tmp_path):
    path = tmp_path / "source_run_ledger.jsonl"
    ok_report = {
        "site_id": "nipa", "site_name": "NIPA", "status": "SUCCESS",
        "risk_level": "", "reason_codes": [], "item_count": 24,
        "baseline_median": 24,
    }
    bad_report = {
        "site_id": "x", "status": "ZERO_SUSPICIOUS", "risk_level": "P0",
        "reason_codes": ["ZERO_ITEMS_WITH_BASELINE"], "item_count": 0,
        "baseline_median": 24,
    }
    assert ledger.baseline_eligible(ok_report) is True
    assert ledger.baseline_eligible(bad_report) is False

    run_id = ledger.new_run_id()
    recs = [
        ledger.build_ledger_record(run_id=run_id, source_report=ok_report),
        ledger.build_ledger_record(run_id=run_id, source_report=bad_report),
    ]
    assert ledger.append_source_runs(recs, path=path) == 2
    rows = list(ledger.iter_runs(path=path))
    assert len(rows) == 2
    assert rows[0]["baseline_eligible"] is True
    assert rows[1]["baseline_eligible"] is False
    assert "reason_codes" in rows[0]
