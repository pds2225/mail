# -*- coding: utf-8 -*-
"""P0 수집누락 탐지 — 필수 실패 시나리오와 판정 계약 테스트.

순수 판정부(coverage_alert)는 네트워크·파일 없이 검증하고, 산출물/알림 배선은
monkeypatch 로 격리한다. 실제 메일 발송은 어떤 경로로도 일어나지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import coverage_alert as ca  # noqa: E402


def _row(**kw) -> dict:
    """정상 수집된 coverage row 기본형."""
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


# ── §5-1. 활성 사이트가 수집 루프에서 누락된 경우 ────────────────────────────
def test_active_site_missing_from_ledger_is_p0():
    sites = [{"id": "a", "name": "A", "enabled": True},
             {"id": "b", "name": "B", "enabled": True}]
    rows = [_row(site_id="a", site_name="A")]  # b 가 실행대장에 없다

    check = ca.verify_source_execution(sites, rows)

    assert check["ok"] is False
    assert check["missing_site_ids"] == ["b"]
    assert check["active_expected"] == 2 and check["executed"] == 1
    missing = check["missing_sources"][0]
    assert missing["risk_level"] == "P0"
    assert missing["reason_codes"] == [ca.REASON_SOURCE_NOT_EXECUTED]


def test_execution_check_skipped_when_sites_unknown():
    """sites 를 모르면 근거 없이 P0 을 만들지 않는다."""
    check = ca.verify_source_execution(None, [_row()])
    assert check["skipped"] is True and check["ok"] is True
    assert check["missing_sources"] == []


def test_disabled_site_is_not_counted_as_missing():
    sites = [{"id": "a", "name": "A", "enabled": True},
             {"id": "z", "name": "Z", "enabled": False}]
    check = ca.verify_source_execution(sites, [_row(site_id="a")])
    assert check["ok"] is True and check["active_expected"] == 1


# ── §5-2. HTTP 200 이지만 오류페이지 / §5-3. 파서 0건 ────────────────────────
def test_http_ok_but_zero_items_with_baseline_is_p0():
    """접속은 됐는데 0건 — 평소 수집되던 소스라면 사고다."""
    report = ca.classify_source_status(_row(item_count=0, posted_parsed_count=0,
                                            detail_link_ok_count=0), _history())
    assert report["status"] == ca.COLLECT_STATUS_ZERO_SUSPICIOUS
    assert report["risk_level"] == "P0"
    assert ca.REASON_ZERO_ITEMS_WITH_BASELINE in report["reason_codes"]
    assert report["drop_rate"] == 1.0


def test_http_ok_but_login_or_captcha_items_are_p0():
    """HTTP 200이어도 로그인·캡차 화면을 공고로 읽었으면 정상 수집이 아니다."""
    report = ca.classify_source_status(
        _row(item_count=4, valid_record_count=4, suspicious_content_count=3),
        _history(count=4),
    )
    assert report["status"] == ca.COLLECT_STATUS_PARTIAL
    assert report["risk_level"] == "P0"
    assert ca.REASON_CONTENT_VALIDATION_FAILED in report["reason_codes"]
    assert report["detail"]["suspicious_content_rate"] == 0.75


def test_one_legitimate_maintenance_notice_does_not_trigger_content_failure():
    """실제 점검 공고 1건 때문에 사이트 전체를 오류 화면으로 오인하지 않는다."""
    report = ca.classify_source_status(
        _row(item_count=20, valid_record_count=20, suspicious_content_count=1,
             posted_parsed_count=20, detail_link_ok_count=20),
        _history(count=20),
    )
    assert ca.REASON_CONTENT_VALIDATION_FAILED not in report["reason_codes"]


def test_http_ok_but_most_records_missing_required_fields_is_p0():
    report = ca.classify_source_status(
        _row(item_count=10, valid_record_count=3, suspicious_content_count=0,
             posted_parsed_count=3, date_unknown_count=7, detail_link_ok_count=3),
        _history(count=10),
    )
    assert report["risk_level"] == "P0"
    assert ca.REASON_SCHEMA_VALIDATION_FAILED in report["reason_codes"]
    assert report["detail"]["valid_record_rate"] == 0.3


def test_parser_error_is_classified_as_parser_failed():
    report = ca.classify_source_status(
        _row(fetch_success=False, fetch_error="AttributeError: 'NoneType' object"),
        _history())
    assert report["status"] == ca.COLLECT_STATUS_FAILED
    assert report["risk_level"] == "P0"
    assert report["reason_codes"] == [ca.REASON_PARSER_FAILED]


def test_network_error_is_classified_as_fetch_failed():
    report = ca.classify_source_status(
        _row(fetch_success=False, fetch_error="SSL handshake failure"), _history())
    assert report["reason_codes"] == [ca.REASON_FETCH_FAILED]
    assert report["risk_level"] == "P0"


def test_unknown_collector_type_is_source_not_executed():
    report = ca.classify_source_status(
        _row(collector_fn="", fetch_error="unknown_type:pw_table"), _history())
    assert report["reason_codes"] == [ca.REASON_SOURCE_NOT_EXECUTED]
    assert report["risk_level"] == "P0"


# ── §5-4. 평소 30건인데 2건만 수집(급감) ────────────────────────────────────
def test_severe_drop_is_p0():
    """30건 평소 → 2건: 93% 급감 → P0."""
    report = ca.classify_source_status(
        _row(item_count=2, posted_parsed_count=2, detail_link_ok_count=2),
        _history(count=30))
    assert report["status"] == ca.COLLECT_STATUS_PARTIAL
    assert report["risk_level"] == "P0"
    assert ca.REASON_COLLECTION_DROP_HIGH in report["reason_codes"]
    assert report["drop_rate"] == pytest.approx(1 - 2 / 30, abs=1e-4)


def test_moderate_drop_is_p1_not_p0():
    """24건 평소 → 10건: 58% 급감(50~79%) → 같은 사유코드지만 등급은 P1."""
    report = ca.classify_source_status(
        _row(item_count=10, posted_parsed_count=10, detail_link_ok_count=10),
        _history(count=24))
    assert report["risk_level"] == "P1"
    assert ca.REASON_COLLECTION_DROP_HIGH in report["reason_codes"]


def test_mild_drop_is_not_flagged():
    """24 → 20건(17% 감소)은 정상 변동."""
    report = ca.classify_source_status(
        _row(item_count=20, posted_parsed_count=20, detail_link_ok_count=20),
        _history(count=24))
    assert report["status"] == ca.COLLECT_STATUS_SUCCESS
    assert report["risk_level"] == ""


def test_abnormal_collection_spike_is_p1():
    """평소 20건 → 70건은 과거 전체목록 유입 가능성이 있어 검토 대상이다."""
    report = ca.classify_source_status(
        _row(item_count=70, posted_parsed_count=70, detail_link_ok_count=70,
             valid_record_count=70),
        _history(count=20),
    )
    assert report["status"] == ca.COLLECT_STATUS_PARTIAL
    assert report["risk_level"] == "P1"
    assert ca.REASON_COLLECTION_SPIKE_HIGH in report["reason_codes"]
    assert report["detail"]["spike_ratio"] == 3.5


def test_small_absolute_increase_is_not_spike():
    """1건 → 3건은 배수만 크고 절대 증가량은 작으므로 정상 변동이다."""
    report = ca.classify_source_status(
        _row(item_count=3, posted_parsed_count=3, detail_link_ok_count=3,
             valid_record_count=3),
        _history(count=1),
    )
    assert ca.REASON_COLLECTION_SPIKE_HIGH not in report["reason_codes"]


# ── §5-5. 첫 페이지와 다음 페이지가 반복 ─────────────────────────────────────
def test_duplicate_page_loop_is_p0():
    report = ca.classify_source_status(
        _row(), _history(),
        page_stat={"stop_reason": "MAX_PAGES_HIT", "duplicate_page": True,
                   "pages_fetched": 4})
    assert report["risk_level"] == "P0"
    assert ca.REASON_DUPLICATE_PAGE_LOOP in report["reason_codes"]


def test_max_pages_hit_without_duplicate_is_pagination_incomplete_p1():
    report = ca.classify_source_status(
        _row(), _history(),
        page_stat={"stop_reason": "MAX_PAGES_HIT", "duplicate_page": False})
    assert report["risk_level"] == "P1"
    assert ca.REASON_PAGINATION_INCOMPLETE in report["reason_codes"]


def test_normal_pagination_end_is_not_flagged():
    for stop in ("EMPTY_PAGE", "LAST_PAGE", "SINGLE_PAGE"):
        report = ca.classify_source_status(
            _row(), _history(), page_stat={"stop_reason": stop})
        assert report["risk_level"] == "", stop


def test_missing_page_stat_never_flags_pagination():
    """계측이 없는 소스를 페이지네이션 이상으로 몰지 않는다(오탐 폭발 방지)."""
    report = ca.classify_source_status(_row(), _history(), page_stat=None)
    assert ca.REASON_PAGINATION_INCOMPLETE not in report["reason_codes"]
    assert ca.REASON_DUPLICATE_PAGE_LOOP not in report["reason_codes"]


# ── §5-6. 게시일 파싱률 90% → 20% 하락 ──────────────────────────────────────
def test_date_parse_rate_below_half_is_p0_reason():
    """24건 중 19건이 날짜 미상 → 파싱률 21%."""
    report = ca.classify_source_status(
        _row(posted_parsed_count=0, date_unknown_count=19), _history())
    assert ca.REASON_DATE_PARSE_RATE_LOW in report["reason_codes"]
    assert report["posted_date_parse_rate"] == pytest.approx(5 / 24, abs=1e-4)


def test_date_parse_rate_uses_unknown_count_not_today_matches():
    """posted_parsed_count 는 '직전영업일 게시분'이라 파싱 성공 수가 아니다.

    오늘 새 공고가 0건이어도(=posted_parsed_count 0) 날짜를 다 읽었으면 파싱률 100%.
    이걸 혼동하면 정상 사이트가 매일 P1 로 잡힌다(실사용 검증에서 발견).
    """
    report = ca.classify_source_status(
        _row(posted_parsed_count=0, date_unknown_count=0), _history())
    assert report["posted_date_parse_rate"] == 1.0
    assert ca.REASON_DATE_PARSE_RATE_LOW not in report["reason_codes"]
    assert report["risk_level"] == ""


def test_date_parse_rate_drop_30pp_is_flagged():
    """파싱률 자체는 50% 이상이지만 평소 대비 30%p 이상 하락하면 P1."""
    report = ca.classify_source_status(
        _row(posted_parsed_count=0, date_unknown_count=10), _history(),
        baseline_date_rate=0.95)
    assert ca.REASON_DATE_PARSE_RATE_LOW in report["reason_codes"]
    assert report["risk_level"] == "P1"


# ── §5-7. 한 사이트 실패 후 다른 사이트 수집 계속 ────────────────────────────
def test_one_failure_does_not_stop_other_classifications():
    rows = [
        _row(site_id="a", site_name="A"),
        _row(site_id="b", site_name="B", fetch_success=False, fetch_error="boom"),
        _row(site_id="c", site_name="C"),
    ]
    reports = ca.classify_sources(rows, {k: _history() for k in "abc"})
    assert len(reports) == 3
    assert [r["site_id"] for r in reports] == ["a", "b", "c"]
    assert reports[0]["status"] == ca.COLLECT_STATUS_SUCCESS
    assert reports[2]["status"] == ca.COLLECT_STATUS_SUCCESS


def test_classify_error_becomes_p0_row_not_exception():
    """판정 중 예외가 나도 리스트 전체가 죽지 않는다."""
    bad = {"site_id": "x", "item_count": "not-a-number", "enabled": True,
           "collector_fn": "f", "fetch_success": True}
    reports = ca.classify_sources([bad], {})
    assert len(reports) == 1 and reports[0]["risk_level"] == "P0"


# ── §5-8. 기준선 없는 신규 사이트 / §5-9. 실제 0건인 정상 상황 ───────────────
def test_new_site_zero_items_is_p1_baseline_insufficient():
    report = ca.classify_source_status(
        _row(item_count=0, posted_parsed_count=0, detail_link_ok_count=0), [])
    assert report["status"] == ca.COLLECT_STATUS_ZERO_SUSPICIOUS
    assert report["risk_level"] == "P1"
    assert report["reason_codes"] == [ca.REASON_BASELINE_INSUFFICIENT]


def test_baseline_with_two_runs_is_insufficient():
    report = ca.classify_source_status(
        _row(item_count=0, posted_parsed_count=0, detail_link_ok_count=0),
        _history(n=2))
    assert report["reason_codes"] == [ca.REASON_BASELINE_INSUFFICIENT]
    assert report["baseline_n"] == 2


def test_baseline_uses_last_seven_runs_median():
    history = [{"date": f"2026-07-{i:02d}", "item_count": c}
               for i, c in enumerate([100, 100, 100, 10, 10, 10, 10, 10, 10, 10], start=1)]
    stats = ca.baseline_stats(history)
    assert stats["n"] == 7          # 최근 7회만
    assert stats["median"] == 10.0  # 오래된 100 은 창 밖
    assert stats["sufficient"] is True


def test_disabled_source_is_skipped_not_risky():
    report = ca.classify_source_status(
        _row(enabled=False, fetch_error="disabled_in_config"), _history())
    assert report["status"] == ca.COLLECT_STATUS_SKIPPED
    assert report["risk_level"] == "" and report["reason_codes"] == []


# ── §5-10. 재실행 시 판정 안정성(동일 입력 → 동일 결과 3회) ──────────────────
def test_repeated_classification_is_deterministic():
    rows = [_row(site_id="a"), _row(site_id="b", item_count=0),
            _row(site_id="c", fetch_success=False, fetch_error="timeout")]
    baseline = {k: _history() for k in "abc"}
    results = [
        json.dumps(ca.classify_sources(rows, baseline), sort_keys=True, ensure_ascii=False)
        for _ in range(3)
    ]
    assert results[0] == results[1] == results[2]


# ── 상세링크 추출률 ──────────────────────────────────────────────────────────
def test_detail_link_rate_low_is_p1():
    report = ca.classify_source_status(
        _row(detail_link_ok_count=5), _history())  # 5/24 = 21%
    assert ca.REASON_DETAIL_LINK_RATE_LOW in report["reason_codes"]
    assert report["risk_level"] == "P1"


# ── 실행 요약·DEGRADED ───────────────────────────────────────────────────────
def test_summary_is_degraded_when_any_p0():
    reports = ca.classify_sources(
        [_row(site_id="a"), _row(site_id="b", item_count=0)],
        {"a": _history(), "b": _history()})
    summary = ca.summarize_run_status(reports, {})
    assert summary["status"] == "DEGRADED" and summary["p0_count"] == 1
    assert summary["recheck_site_ids"] == ["b"]


def test_summary_is_ok_when_all_healthy():
    reports = ca.classify_sources([_row(site_id="a")], {"a": _history()})
    summary = ca.summarize_run_status(reports, {})
    assert summary["status"] == "OK"
    assert summary["p0_count"] == 0 and summary["p1_count"] == 0


def test_summary_includes_missing_sources_from_exec_check():
    sites = [{"id": "a", "enabled": True}, {"id": "gone", "enabled": True}]
    rows = [_row(site_id="a")]
    check = ca.verify_source_execution(sites, rows)
    summary = ca.summarize_run_status(ca.classify_sources(rows, {"a": _history()}), check)
    assert summary["status"] == "DEGRADED"
    assert "gone" in summary["recheck_site_ids"]


# ── 산출물 렌더링 ────────────────────────────────────────────────────────────
def test_payload_and_markdown_contain_required_fields():
    sites = [{"id": "a", "name": "A", "enabled": True},
             {"id": "gone", "name": "사라진소스", "enabled": True}]
    rows = [_row(site_id="a", site_name="A", item_count=0,
                 posted_parsed_count=0, detail_link_ok_count=0)]
    baseline = {"a": _history()}
    reports = ca.classify_sources(rows, baseline)
    check = ca.verify_source_execution(sites, rows)
    summary = ca.summarize_run_status(reports, check)
    payload = ca.build_coverage_payload(rows, reports, summary, exec_check=check,
                                        generated_at="2026-07-23 08:00 KST")

    assert payload["run_status"] == "DEGRADED"
    assert payload["active_expected"] == 2 and payload["executed"] == 1
    assert payload["execution_complete"] is False
    source = next(s for s in payload["sources"] if s["site_id"] == "a")
    for key in ("status", "item_count", "baseline_median", "drop_rate",
                "posted_date_parse_rate", "risk_level", "reason_codes"):
        assert key in source

    md = ca.render_coverage_markdown(payload)
    assert "DEGRADED" in md and "누락위험" in md
    assert "사라진소스" in md          # 미실행 소스도 보고서에 나타난다
    assert "P0" in md

    alert = ca.render_p0_alert_markdown(payload)
    assert "P0 수집 누락 위험" in alert
    assert "정상 수집 공고 발송은 계속 진행됨" in alert


def test_p0_alert_message_omits_meaningless_count_for_failed_source():
    """수집 자체가 실패한 소스에 '금일 N건'을 쓰면 오해를 준다."""
    reports = ca.classify_sources(
        [_row(site_id="b", site_name="인천TP", fetch_success=False,
              fetch_error="AttributeError: NoneType")],
        {"b": _history()})
    payload = ca.build_coverage_payload([], reports,
                                        ca.summarize_run_status(reports, {}))
    msg = ca.format_p0_alert_message(payload)
    assert "파싱 실패" in msg
    assert "금일" not in msg


def test_no_p0_renders_empty_alert():
    reports = ca.classify_sources([_row(site_id="a")], {"a": _history()})
    payload = ca.build_coverage_payload([], reports,
                                        ca.summarize_run_status(reports, {}))
    assert "해당 없음" in ca.render_p0_alert_markdown(payload)
    assert ca.format_p0_alert_message(payload) == "P0 수집 누락 위험 없음"


# ── 기존 계약 불변 (회귀 방지) ───────────────────────────────────────────────
def test_existing_detect_anomalies_untouched_by_new_logic():
    """신규 판정이 기존 알림 볼륨을 흔들지 않는다 — 신규 사이트는 여전히 무알림."""
    rows = [_row(site_id="new_site", item_count=0)]
    assert ca.detect_coverage_anomalies(rows, {}) == []


def test_existing_severity_values_unchanged():
    rows = [_row(site_id="a", item_count=0)]
    anomalies = ca.detect_coverage_anomalies(rows, {"a": _history()})
    assert anomalies and anomalies[0]["severity"] == "high"
    assert anomalies[0]["reason"] == "0건 급락"
