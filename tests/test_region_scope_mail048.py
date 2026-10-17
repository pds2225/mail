"""MAIL-048 지역기준·컨소시엄·이전조건 및 지역미상 경고 회귀."""
from __future__ import annotations

import json
from datetime import datetime

import monitor as mon
from mail_core.matching import company_match as cm
from mail_core.matching.region_context import applicant_region_text, notice_region_metadata
from mail_core.operations import daily_review as dr


def _company(city: str, **extra):
    return {"id": "fixture", "email": "fixture@example.test",
            "region": {"city": city}, "industry_keywords": ["제조"],
            "match_threshold": 0, **extra}


def test_nationwide_and_applicant_local_restriction_specific_region_wins():
    item = {"title": "전국 제조 지원", "description": "지원대상: 전국 중소기업 중 서울특별시 소재 기업"}
    scope = mon._resolve_applicant_region_scope(item)
    assert "서울" in scope["regions"]
    assert scope["nationwide"] is False


def test_business_site_basis_matches_any_site_but_headquarters_uses_hq_only():
    company = _company("서울", sites=[{"city": "부산", "district": "해운대구"}])
    site_notice = {"title": "부산 사업장 지원", "description": "지원대상: 사업장 소재지가 부산광역시인 제조기업"}
    hq_notice = {"title": "부산 본사 지원", "description": "지원대상: 본사 소재지가 부산광역시인 제조기업"}

    site_result = cm.compute_match_score(site_notice, company)
    hq_result = cm.compute_match_score(hq_notice, company)
    assert site_result["breakdown"]["region_status"] == "city"
    assert site_result["breakdown"]["region_basis"] == "business_site"
    assert hq_result["breakdown"]["region_status"] == "other_only"
    assert hq_result["breakdown"]["region_basis"] == "headquarters"


def test_relocation_requirement_keeps_other_region_company_conditional():
    item = {"title": "서울 이전 기업 제조 지원",
            "description": "지원대상: 서울특별시 소재 기업 및 서울로 이전 예정인 기업"}
    result = cm.compute_match_score(item, _company("부산"))
    assert result["breakdown"]["relocation_required"] is True
    assert result["breakdown"]["conditional_eligibility"] is True
    assert result["breakdown"]["region_status"] == "relocation_conditional"


def test_group_region_gate_keeps_relocation_notice_as_conditional():
    item = {"title": "서울 이전 제조기업 지원",
            "description": "지원대상: 서울특별시 소재 기업 및 서울로 이전 예정인 기업"}
    result = mon.classify_region_for_group(item, {
        "applicant_region_city": "부산", "applicant_region_label": "부산",
    })
    assert result["region_status"] == "eligible"
    assert result["eligible_regions"] == ["부산"]
    assert result["conditional_eligibility"] is True
    assert result["relocation_required"] is True


def test_consortium_participant_region_is_reference_not_applicant_scope():
    text = "지원대상: 서울특별시 주관기관 기준. 참여기관 소재지는 부산광역시(참고)"
    meta = notice_region_metadata(text)
    applicant = applicant_region_text(text)
    scope = mon._resolve_applicant_region_scope({"title": "공동사업", "description": text})
    assert meta["participating_regions"] == ["부산"]
    assert "부산" not in applicant
    assert "서울" in applicant
    assert "부산" not in scope["regions"]
    assert "서울" in scope["regions"]
    assert scope["participating_regions"] == ["부산"]


def test_daily_review_warns_when_region_unknown_exceeds_thirty_percent(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "region_scope_stats_20261017.json").write_text(
        json.dumps({"total": 10, "unknown": 4}), encoding="utf-8")
    report, _ = dr.run_daily_review(
        date_s="2026-10-17", slot="am", delivery_state_path=tmp_path / "missing.json",
        logs_dir=logs, reviews_root=tmp_path / "reviews", append_context=False,
        require_coverage=False,
    )
    warning = next(check for check in report.checks if check.id == "REGION_UNKNOWN_HIGH")
    assert warning.status == "WARN"
    assert "4/10" in warning.detail


def test_daily_review_does_not_warn_at_exactly_thirty_percent(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "region_scope_stats_20261017.json").write_text(
        json.dumps({"total": 10, "unknown": 3}), encoding="utf-8")
    report, _ = dr.run_daily_review(
        date_s="2026-10-17", slot="am", delivery_state_path=tmp_path / "missing.json",
        logs_dir=logs, reviews_root=tmp_path / "reviews", append_context=False,
        require_coverage=False,
    )
    assert all(check.id != "REGION_UNKNOWN_HIGH" for check in report.checks)


def test_region_unknown_report_counts_only_unscoped_notices(monkeypatch, tmp_path):
    monkeypatch.setattr(mon, "LOGS_DIR", tmp_path)
    path = mon.write_region_scope_stats_report([
        {"title": "지역 미정", "description": "일반 지원"},
        {"title": "전국 사업", "description": "전국 대상"},
        {"title": "서울 사업", "description": "서울 소재 기업"},
    ], run_at=datetime(2026, 10, 17, tzinfo=mon.KST))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {"total": 3, "unknown": 1, "ratio": 0.333333}
