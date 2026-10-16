import json
from datetime import datetime

import pytest

import monitor as mon
from mail_core.matching import company_match as cm
from mail_core.matching.company_fanout import CompanyMatchFanout
from mail_core.operations import daily_review as dr


def company(cid="a", name="에이아이랩"):
    return {"id": cid, "name": name, "email": "fixture@example.test",
            "industry_keywords": ["에이아이랩", "AI"], "match_threshold": 0,
            "region": {"city": "서울"}}


def notice(text="전국 AI 제조기업 지원"):
    return {"id": "notice", "title": text, "description": "전국 기업 대상"}


@pytest.mark.parametrize("name", ["에이아이랩", "(주)에이아이랩", "주식회사 에이아이랩", "에이 아이 랩(주)"])
def test_company_name_is_not_matching_evidence(name):
    profile = company(name=name)
    result = cm.match_for_company([notice("에이아이랩 선정 소식")], profile)
    assert not result["matched"]
    assert "COMPANY_NAME_ONLY" in result["rejected"][0]["_match_reason"]
    assert cm.match_for_company([notice("전국 AI 제조기업 지원")], profile)["matched"]
    normalized = cm._normalize_company(profile)
    assert normalized["industry_keywords"] == ["AI"]
    assert cm._normalize_company(normalized) == normalized


@pytest.mark.parametrize("limit", [None, 0, "", "invalid"])
def test_default_cap_off_preserves_results(limit):
    fanout = CompanyMatchFanout(limit)
    for cid in range(30):
        result = cm.match_for_company([notice()], company(str(cid)))
        kept, rejected = fanout.apply(result["matched"], company(str(cid)))
        assert kept == result["matched"] and not rejected


def test_monitor_company_cutoff_caps_unique_companies_and_daily_review_warns(tmp_path):
    path = tmp_path / "fanout.json"
    fanout = CompanyMatchFanout(1, report_path=path)
    settings = {"company_match_enabled": True, "max_companies_per_notice": 1}
    profiles = {cid: company(cid) for cid in ["a", "b"]}
    group = {"company_id": "a"}
    kept, _ = mon.refine_included_by_company([notice()], group, settings, profiles, fanout=fanout)
    assert len(kept) == 1
    # 같은 기업의 다른 그룹은 상한을 두 번 차지하지 않는다.
    assert mon.refine_included_by_company([notice()], group, settings, profiles, fanout=fanout)[0]
    kept, capped = mon.refine_included_by_company([notice()], {"company_id": "b"}, settings, profiles, fanout=fanout)
    assert not kept and capped[0]["_match_reason"] == "MATCH_FANOUT_HIGH"
    report, paths = dr.run_daily_review(when=datetime(2026, 10, 16, tzinfo=dr.KST),
        companies=[], fanout_report_path=path, logs_dir=tmp_path, require_coverage=False,
        reviews_root=tmp_path / "reviews", append_context=False)
    warnings = [c for c in report.checks if c.id == "MATCH_FANOUT_HIGH"]
    assert len(warnings) == 1 and warnings[0].status == "WARN"
    assert "MATCH_FANOUT_HIGH" in paths["md"].read_text(encoding="utf-8")
    aggregate = json.loads(path.read_text(encoding="utf-8"))
    assert aggregate["exceeded_notices"] == 1
    assert "fixture@example.test" not in path.read_text(encoding="utf-8")
    # 같은 날 상한을 껐으면 이전 경고를 재사용하지 않는다.
    CompanyMatchFanout(None, report_path=path)
    assert not json.loads(path.read_text(encoding="utf-8"))["exceeded_notices"]


def test_preference_fields_cannot_raise_eligibility_score():
    baseline = company()
    assert cm.compute_match_score(notice(), baseline) == cm.compute_match_score(
        notice(), {**baseline, "preference": ["AI"], "owner_interest": ["AI"]})


def test_dry_run_cli_applies_settings_cap(tmp_path, monkeypatch):
    import scripts.run_company_match as cli
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text(json.dumps({"max_companies_per_notice": 1}), encoding="utf-8")
    profiles = [{**company(cid), "email": cm.TEST_RECIPIENT} for cid in ["a", "b"]]
    profiles_path = tmp_path / "companies.json"
    profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
    notices_path = tmp_path / "notices.json"
    applicant_notice = {**notice("전국 AI 제조기업 성장지원 사업 신청접수"),
        "description": "전국 중소기업 대상 AI 제작비 지원. 참여기업 모집 신청접수.",
        "deadline": "2026-12-31", "posted_date": "2026-10-16",
        "application_period": {"start": "2026-10-01", "end": "2026-12-31"}}
    notices_path.write_text(json.dumps([applicant_notice]), encoding="utf-8")
    monkeypatch.setattr(cli, "BASE_DIR", tmp_path)
    assert cli.main(["--input", str(notices_path), "--companies", str(profiles_path),
                     "--output-dir", str(tmp_path / "reports")]) == 0
    report = next((tmp_path / "reports").glob("fanout_*.json"))
    assert json.loads(report.read_text(encoding="utf-8"))["exceeded_notices"] == 1


def test_forced_monitor_slot_and_review_clock_share_report(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITOR_DELIVERY_SLOT", "am")
    monkeypatch.setattr(dr, "VAR_DIR", tmp_path)
    path = tmp_path / "reports" / "company_match" / "fanout_2026-10-16.json"
    fanout = CompanyMatchFanout(1, report_path=path)
    fanout.apply([notice()], company("a"))
    fanout.apply([notice()], company("b"))
    report = dr.build_review(when=datetime(2026, 10, 16, 18, tzinfo=dr.KST),
        companies=[], require_coverage=False, logs_dir=tmp_path)
    assert report.slot == "pm"
    assert len([c for c in report.checks if c.id == "MATCH_FANOUT_HIGH"]) == 1
