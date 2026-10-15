"""MAIL-041: 실제 그룹 판정·기업 매칭·daily review 경로(외부 발송 없음)."""
from datetime import date, datetime, timedelta
import json

import pytest

import monitor as mon
from mail_core.matching import company_match as cm
from mail_core.matching.region_context import region_exclusions
from mail_core.operations import daily_review as dr
from mail_core.security import private_config


def item(description, **extra):
    return {"id": "mail041", "title": "제조기업 성장지원 사업 신청접수",
            "description": description, "deadline": "2026-12-31",
            "posted_date": "2026-10-16", "is_aggregator": False,
            "application_period": {"start": "2026-10-01", "end": "2026-12-31"},
            **extra}


def group(city):
    return {"id": "test", "applicant_region_city": city, "applicant_region_label": city,
            "or_keywords": [], "and_keyword_groups": [], "exclude_keywords": [],
            "required_conditions": {}, "score_threshold": 1}


def company(city, **extra):
    return {"id": "fixture", "email": "fixture@example.test", "region": {"city": city},
            "match_threshold": 0, "industry_keywords": ["제조기업", "지원", "성장"], **extra}


@pytest.mark.parametrize("city", ["인천", "서울", "경기", "부산"])
@pytest.mark.parametrize("description", [
    "주관기관: 인천테크노파크 / 지원대상: 전국 중소기업",
    "주소: 인천광역시 남동구 / 지원대상: 전국 중소기업",
    "주소 인천광역시 남동구 / 지원대상: 전국 중소기업",
    "지원대상: 전국 중소기업\n담당부서: 인천광역시청",
])
def test_nationwide_agency_is_not_a_restriction(city, description):
    notice = item(description, author="인천테크노파크")
    assert mon._resolve_applicant_region_scope(notice)["nationwide"]
    assert mon.classify_region_for_group(notice, group(city))["region_status"] == "eligible"
    assert cm.compute_match_score(notice, company(city))["breakdown"]["region_status"] == "nationwide"
    evaluated = mon.evaluate_notice(notice, group(city), date(2026, 10, 16))
    assert "REGION_NOT_ELIGIBLE" not in evaluated["exclude_reason_codes"]


@pytest.mark.parametrize("suffix", ["인천 제외", "인천 소재 기업 제외", "인천 기업은 제외",
                                   "인천을 제외한", "인천광역시를 제외한"])
def test_explicit_exclusion_has_priority_over_nationwide_and_title(suffix):
    notice = item(f"지원대상: 전국 중소기업({suffix})", title="[인천] 제조기업 성장지원")
    assert mon._resolve_applicant_region_scope(notice)["excluded_regions"] == ["인천"]
    assert mon.classify_region(notice)["region_status"] == "not_eligible"
    assert mon.classify_region_for_group(notice, group("인천"))["region_status"] == "not_eligible"
    assert mon.classify_region_for_group(notice, group("부산"))["region_status"] == "eligible"
    # 점수가 충분해도 제외된 기업은 추천하지 않는다.
    assert not cm.match_for_company([notice], company("인천"))["matched"]
    assert cm.match_for_company([notice], company("부산"))["matched"]


def test_seoul_gyeonggi_targets_exclude_incheon():
    notice = item("지원대상: 서울·경기 소재 기업(인천 제외)")
    scope = mon._resolve_applicant_region_scope(notice)
    assert set(scope["regions"]) == {"서울", "경기"}
    for city in ["서울", "경기", "인천"]:
        expected = "not_eligible" if city == "인천" else "eligible"
        assert mon.classify_region_for_group(notice, group(city))["region_status"] == expected
        ev = mon.evaluate_notice(notice, group(city), date(2026, 10, 16))
        assert ("REGION_NOT_ELIGIBLE" in ev["exclude_reason_codes"]) == (city == "인천")


@pytest.mark.parametrize("phrase", ["도서 제외", "도서지역 제외", "도서지역을 제외한"])
def test_islands_are_a_flag_not_a_positive_region(phrase):
    notice = item(f"지원대상: 전국 중소기업({phrase})")
    scope = mon._resolve_applicant_region_scope(notice)
    assert scope == {"regions": [], "nationwide": True, "excluded_regions": [], "island_excluded": True}
    for city in ["인천", "서울", "부산"]:
        assert mon.classify_region_for_group(notice, group(city))["region_status"] == "eligible"
    assert mon.classify_region(notice)["island_excluded"]


@pytest.mark.parametrize("agency", ["주관기관: 서울시청", "서울테크노파크", "주소: 서울특별시 강남구"])
def test_busan_target_beats_seoul_agency(agency):
    notice = item(f"{agency}\n지원대상: 부산광역시 소재 기업", author="서울시청")
    assert mon.classify_region_for_group(notice, group("부산"))["region_status"] == "eligible"
    assert mon.classify_region_for_group(notice, group("서울"))["region_status"] == "not_eligible"
    assert mon._applicant_restricted_regions(notice["description"]) == {"부산"}


@pytest.mark.parametrize("agency", ["서울시청", "부산테크노파크"])
def test_agency_alone_cannot_hard_exclude(agency):
    notice = item(agency, author=agency)
    scope = mon._resolve_applicant_region_scope(notice)
    assert not scope["regions"] and scope["agency_regions"]
    assert mon.classify_region(notice)["region_status"] != "not_eligible"
    assert mon.classify_region_for_group(notice, group("인천"))["region_status"] != "not_eligible"


def test_contact_exclusions_are_not_applicant_exclusions():
    assert region_exclusions("문의처: 인천 제외\n지원대상: 전국 중소기업")["excluded_regions"] == []


def test_exclusions_work_without_monitor_and_with_long_company_city(monkeypatch):
    notice = item("지원대상: 전국 중소기업(인천 제외)")
    monkeypatch.setattr(cm, "_region_signals", lambda _: None)
    assert cm.compute_match_score(notice, company("인천광역시"))["breakdown"]["region_status"] == "other_only"
    assert not cm.match_for_company([notice], company("인천광역시"))["matched"]
    assert cm.match_for_company([notice], company("서울특별시"))["matched"]


def test_wrong_tenant_cannot_override_region_update_date():
    public = [company("서울", tenant_id="a", region_updated_at="2026-10-16")]
    result = private_config.merge_companies(public, {"companies": {
        "fixture": {"tenant_id": "b", "region_updated_at": "2020-01-01"}}})
    assert result[0]["region_updated_at"] == "2026-10-16"


def test_private_company_date_reaches_daily_review_only(tmp_path, monkeypatch):
    path = tmp_path / "companies.json"
    path.write_text(json.dumps([company("서울")]), encoding="utf-8")
    monkeypatch.setattr(cm, "COMPANIES_PATH", path)
    monkeypatch.setattr(private_config, "load_private_payload", lambda: {
        "companies": {"fixture": {"tenant_id": "default", "email": "fixture@example.test",
                                  "region_updated_at": "2025-10-15"}}})
    loaded = cm.load_companies()
    assert loaded[0]["region_updated_at"] == "2025-10-15"
    notice = item("지원대상: 전국 중소기업")
    assert cm.match_for_company([notice], loaded[0]) == cm.match_for_company([notice], company("서울"))
    report, paths = dr.run_daily_review(
        when=datetime(2026, 10, 16, tzinfo=dr.KST), require_coverage=False,
        delivery_state_path=tmp_path / "missing.json", logs_dir=tmp_path / "logs",
        reviews_root=tmp_path / "reviews", append_context=False,
    )
    warnings = [c for c in report.checks if c.id == "MDR-006"]
    assert len(warnings) == 1 and warnings[0].status == "WARN"
    assert "366일" in warnings[0].detail
    rendered = paths["md"].read_text(encoding="utf-8")
    assert "[WARN]" in rendered and "fixture@example.test" not in rendered
    assert "MDR-006" in paths["json"].read_text(encoding="utf-8")


@pytest.mark.parametrize("age", [0, 365, 366])
def test_staleness_boundary_is_warning_only(tmp_path, age):
    moment = datetime(2026, 10, 16, tzinfo=dr.KST)
    companies = [company("서울", region_updated_at=(moment - timedelta(days=age)).isoformat())]
    kwargs = dict(when=moment, require_coverage=False, logs_dir=tmp_path,
                  delivery_state_path=tmp_path / "missing.json")
    baseline = dr.build_review(companies=[], **kwargs)
    report = dr.build_review(companies=companies, **kwargs)
    assert len([c for c in report.checks if c.id == "MDR-006"]) == int(age > 365)
    assert report.overall == baseline.overall


@pytest.mark.parametrize("value", ["", "invalid", "2099-01-01"])
def test_missing_invalid_future_dates_do_not_warn(tmp_path, value):
    report = dr.build_review(when=datetime(2026, 10, 16, tzinfo=dr.KST),
                             require_coverage=False, logs_dir=tmp_path,
                             companies=[company("서울", region_updated_at=value)])
    assert not [c for c in report.checks if c.id == "MDR-006"]
