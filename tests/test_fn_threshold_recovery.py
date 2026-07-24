# -*- coding: utf-8 -*-
"""FN 회복(임계 38) 회귀 테스트 — own지역+업종공고 매칭 회복, 지역차단·제외어는 불변.

배경: 골든 라벨 확대(PR #148)로 드러난 fn_weaklabel_own 96건을 triage 한 결과,
"자기 지역 + 업종 키워드 1~2건" 공고(제조DX멘토단·경영안정자금·AI훈련센터 등)가
임계(45~50) 근접 미달로 구조적으로 누락됨을 확인(s3_fn.json, real_miss_suspect 17건).
match_threshold 를 38로 조정해 14건을 회복하되, 지역차단·제외어 방어는 그대로임을 고정한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mail_core.matching import company_match  # noqa: E402


def _company():
    return {
        "id": "cmp_t", "name": "t", "active": True,
        "region": {"city": "인천", "district": "남동구"},
        "industry_keywords": ["제조", "화장품"],
        "interest_keywords": ["수출", "바우처"],
        "exclude_keywords": ["설명회"],
        "has_factory": False, "export_focus": False,
        "support_type_prefs": [],
        "match_threshold": 38,
    }


def _score(item, comp):
    return company_match.compute_match_score(item, comp)


def test_threshold_38_loaded_from_config():
    """companies.json 의 3사 임계가 38로 설정돼 있다(회복 조정 반영)."""
    comps = company_match.load_companies()
    assert comps, "companies.json 로드 실패"
    assert all(c["match_threshold"] == 38 for c in comps), \
        [c.get("match_threshold") for c in comps]


def test_own_region_industry_notice_recovers():
    """own 지역 + 업종/관심 키워드 공고가 임계 38에서 matched 로 회복된다."""
    comp = _company()
    item = {"title": "[인천] 2026년 제조기업 수출 지원사업 참여기업 모집",
            "description": "인천 소재 제조 중소기업의 수출 지원"}
    res = _score(item, comp)
    assert res["score"] >= 38, res  # 산업(제조)+관심(수출)+인천 가점
    out = company_match.match_for_company([item], comp)
    assert len(out["matched"]) == 1, out["rejected"]


def test_other_region_still_blocked():
    """타지역 한정 공고는 임계와 무관하게 여전히 차단(감점)된다."""
    comp = _company()
    item = {"title": "2026년 제조기업 수출 지원사업",
            "description": "신청자격: 부산광역시 소재 기업만 신청 가능"}
    res = _score(item, comp)
    out = company_match.match_for_company([item], comp)
    assert len(out["matched"]) == 0, (res["score"], res.get("mismatches"))


def test_exclude_keyword_still_blocked():
    """제외 키워드(설명회) 공고는 임계 인하 후에도 차단된다."""
    comp = _company()
    item = {"title": "[인천] 제조 수출 지원사업 설명회 안내",
            "description": "인천 기업 대상 설명회"}
    out = company_match.match_for_company([item], comp)
    assert len(out["matched"]) == 0


def test_irrelevant_notice_still_rejected():
    """업종 무관 공고(키워드 0건)는 own 지역이어도 여전히 거절된다(무관 유입 방지)."""
    comp = _company()
    item = {"title": "[인천] 2026년 시민 문화강좌 수강생 모집",
            "description": "인천 시민 대상 문화강좌"}
    res = _score(item, comp)
    out = company_match.match_for_company([item], comp)
    assert len(out["matched"]) == 0, (res["score"], res["reasons"])


def test_grayzone_generic_keyword_excluded():
    """회색지대(architect 후속조건): generic 관심키워드(박람회)만 히트하는 산업무관
    공고(로컬푸드)는 임계 38에서도 exclude 로 차단된다 — 실누출 사례 고정."""
    comp = _company()
    comp["interest_keywords"] = ["수출", "바우처", "박람회"]
    comp["exclude_keywords"] = ["설명회", "로컬푸드"]
    item = {"title": "2026년 전국 8도 로컬푸드 단체박람회 참가기업 모집 공고",
            "description": "지역 농특산물 로컬푸드 판매 박람회"}
    out = company_match.match_for_company([item], comp)
    assert len(out["matched"]) == 0


def test_grayzone_exclude_in_real_config():
    """실제 companies.json 의 제조 2사(bnco·incheon_mfg)에 로컬푸드 exclude 가 반영돼 있다."""
    comps = {c["id"]: c for c in company_match.load_companies()}
    for cid in ("cmp_bnco", "cmp_incheon_mfg"):
        assert "로컬푸드" in comps[cid]["exclude_keywords"], cid
