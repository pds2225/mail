"""MAIL-016 — 기업별 업력 Hard Gate 회귀 테스트.

그룹 정책(monitor.business_years_status/group.business_years)과 완전히 분리된
기업 개별 업력 비교(company_match.company_business_years_status)를 검증한다.
Run: python -m pytest tests/test_company_match_business_years.py -v
네트워크/환경변수 불필요 (monitor 는 지연 import 로만 사용).
"""
from __future__ import annotations

from datetime import date, timedelta

from mail_core.matching import company_match

TODAY = date(2026, 9, 18)


def _iso(years_ago: float) -> str:
    return (TODAY - timedelta(days=int(years_ago * 365.25))).isoformat()


def _company(**ov):
    c = {
        "id": "cmp_biz",
        "name": "업력테스트 기업",
        "email": company_match.TEST_RECIPIENT,
        "active": True,
        "region": {"city": "인천", "district": "남동구"},
        "industry_keywords": ["화장품", "뷰티", "제조"],
        "interest_keywords": ["수출", "스마트공장"],
        "match_threshold": 40,
    }
    c.update(ov)
    return company_match._normalize_company(c)


def _item(title="", description="", **ov):
    it = {"title": title, "description": description}
    it.update(ov)
    return it


# ── 1. 기업 업력 충족 → eligible/통과 ────────────────────────────────────────

def test_established_company_within_requirement_is_eligible():
    company = _company(founded_date=_iso(2))  # 업력 2년
    item = _item("인천 남동구 제조 창업기업 지원", "창업 3년 이내 기업 대상. 인천 남동구 제조업.")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "eligible"


def test_established_company_within_requirement_is_matched():
    company = _company(founded_date=_iso(2))
    item = _item(
        "인천 남동구 화장품 제조 창업기업 수출바우처",
        "창업 3년 이내 기업 대상. 인천 남동구 소재 화장품 제조업. 수출 스마트공장.",
        _types=["지원금/바우처"],
    )
    out = company_match.match_for_company([item], company)
    assert out["audit"][0]["decision"] == "matched"


# ── 2. 기업 업력 명백한 미충족 → Hard Exclude ────────────────────────────────

def test_established_company_over_limit_is_ineligible():
    company = _company(founded_date=_iso(5))  # 업력 5년
    item = _item("창업 3년 이내 지원", "창업 3년 이내 기업만 신청 가능.")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "ineligible"


def test_business_years_ineligible_hard_excludes_even_with_strong_keywords():
    """업력 부적격 + 기업 키워드 강한 매칭 → 승격 금지(하드 제외가 스코어링보다 우선)."""
    company = _company(founded_date=_iso(5))
    item = _item(
        "인천 남동구 화장품 뷰티 제조 창업 3년 이내 기업 수출바우처 스마트공장",
        "창업 3년 이내 기업만 신청 가능. 인천 남동구 화장품 뷰티 제조업 수출 스마트공장 전부 일치.",
        _types=["지원금/바우처"],
    )
    out = company_match.match_for_company([item], company)
    assert out["audit"][0]["decision"] == "rejected_hard"
    assert "COMPANY_BUSINESS_YEARS_NOT_ELIGIBLE" in out["audit"][0]["reason"]
    assert all(it is not item for it in out["matched"])


# ── 3. 기업 업력 unknown → 탈락 금지 ─────────────────────────────────────────

def test_company_without_business_info_is_unknown_not_hard_excluded():
    company = _company()  # founded_date/business_stage 미기재
    item = _item("창업 3년 이내 지원", "창업 3년 이내 기업만 신청 가능.")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "unknown"
    out = company_match.match_for_company([item], company)
    assert out["audit"][0]["decision"] != "rejected_hard"


# ── 4. 공고 업력조건 unknown → 탈락 금지 ─────────────────────────────────────

def test_notice_without_business_year_requirement_is_unknown_not_hard_excluded():
    company = _company(founded_date=_iso(5))
    item = _item("인천 남동구 제조 지원", "업력 제한 확인 불가. 인천 남동구 제조업.")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "unknown"
    out = company_match.match_for_company([item], company)
    assert out["audit"][0]["decision"] != "rejected_hard"


# ── 5. 지역 부적격 + 업력 적격 → 탈락 유지 ───────────────────────────────────

def test_region_ineligible_with_business_years_eligible_still_rejected():
    company = _company(founded_date=_iso(2))
    item = _item("부산 전용 창업 3년 이내 지원", "부산광역시 소재 기업만 신청 가능. 창업 3년 이내.")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "eligible"
    out = company_match.match_for_company([item], company)
    assert out["audit"][0]["decision"] != "matched"


# ── 6. (위 test_business_years_ineligible_hard_excludes_even_with_strong_keywords 참조) ──


# ── 7. 그룹의 BUSINESS_YEARS_NOT_ELIGIBLE 이 기업 판정에 전파되지 않음 ────────

def test_group_business_years_reason_code_does_not_leak_into_company_verdict():
    """item 에 그룹 evaluate_notice 의 BUSINESS_YEARS_NOT_ELIGIBLE 흔적이 있어도,
    기업 자신의 업력이 적격이면 회사 판정은 이를 무시하고 eligible/matched 로 본다."""
    company = _company(founded_date=_iso(2))  # 기업 실제 업력은 적격
    item = _item(
        "인천 남동구 화장품 제조 창업 3년 이내 기업 수출바우처",
        "창업 3년 이내 기업 대상. 인천 남동구 화장품 제조업 수출.",
        _types=["지원금/바우처"],
        # 다른(더 엄격한) 그룹 정책에서 유래한 하드 제외 흔적 — HARD_EXCLUDE_CODES 밖이라
        # company_match 는 이 코드 자체로 하드 제외하지 않는다.
        exclude_reason_codes=["BUSINESS_YEARS_NOT_ELIGIBLE"],
        reason_codes=["BUSINESS_YEARS_NOT_ELIGIBLE"],
    )
    assert company_match.company_business_years_status(item, company, today=TODAY) == "eligible"
    out = company_match.match_for_company([item], company)
    assert out["audit"][0]["decision"] == "matched"


# ── 8. 기존 지역 판정 회귀 없음 ───────────────────────────────────────────────

def test_region_scoring_unaffected_by_business_years_addition():
    """업력 필드가 전혀 없는 기존 기업/공고 조합은 지역 판정 결과가 그대로 유지된다."""
    company = _company()  # founded_date 없음(unknown) — 회귀 대상은 지역 판정
    item = _item("인천 남동구 제조 지원", "남동구 소재 제조업.")
    score = company_match.compute_match_score(item, company)
    assert score["breakdown"]["region_status"] == "district"


# ── K-Startup 버킷 필드(business_age_text) 경로 — 예비창업자 판정 원칙 예시 ───

def test_prefounding_company_eligible_for_prefounding_only_kstartup_bucket():
    company = _company(business_stage="예비창업자")
    item = _item("예비창업패키지 모집", "예비창업자 대상.", business_age_text="예비창업자")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "eligible"


def test_established_company_ineligible_for_prefounding_only_kstartup_bucket():
    company = _company(founded_date=_iso(3))
    item = _item("예비창업패키지 모집", "예비창업자 대상.", business_age_text="예비창업자")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "ineligible"


def test_prefounding_company_eligible_for_prefounding_only_free_text():
    """판정 원칙 예시: 기업=예비창업자, 공고='예비창업자만 가능' → eligible."""
    company = _company(business_stage="예비창업자")
    item = _item("창업지원 공고", "예비창업자만 가능. 창업 지원.")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "eligible"


def test_kstartup_bucket_union_eligible_for_established_company():
    company = _company(founded_date=_iso(3))  # 업력 3년
    item = _item("K-Startup 공고", "지원", business_age_text="1년미만,5년미만,10년미만")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "eligible"


def test_kstartup_bucket_all_ineligible_for_older_company():
    company = _company(founded_date=_iso(12))  # 업력 12년
    item = _item("K-Startup 공고", "지원", business_age_text="1년미만,5년미만,10년미만")
    assert company_match.company_business_years_status(item, company, today=TODAY) == "ineligible"
