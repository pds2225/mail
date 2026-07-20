"""다지역 태그/나열 own 오차단(titletag_own_blocked) 회귀 가드.

`[서울ㆍ인천ㆍ경기ㆍ강원]` 제목 태그나 '서울ㆍ인천ㆍ강원 소재 기업' 본문에서 own 광역이
명시됐는데도 파서가 마지막 토큰만 잡아 '타지역 한정'으로 오차단하던 누락(recall 위반)을 막는다.
정확도 하네스(fn-hunter)가 실데이터에서 발굴 → S4 최소수정으로 확립.
단독 foreground: python -m pytest test_titletag_multiregion_recall.py -q
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import company_match as cm  # noqa: E402
import monitor  # noqa: E402
import run_company_match as rcm  # noqa: E402


def _comp(city):
    return {"id": "t", "email": cm.TEST_RECIPIENT, "active": True,
            "region": {"city": city, "district": ""},
            "industry_keywords": ["AI", "인공지능", "제조", "디자인"],
            "interest_keywords": ["AI", "디자인"],
            "exclude_keywords": [], "match_threshold": 50}


def _region_status(item, city):
    enr = rcm._enrich_for_company([item], _comp(city))[0]
    return cm.compute_match_score(enr, _comp(city))["breakdown"]["region_status"]


def test_title_multiregion_tag_own_eligible():
    """제목 [서울ㆍ인천ㆍ경기ㆍ강원] — 태그에 든 광역 기업은 지역차단 아님(적격)."""
    item = {"title": "[서울ㆍ인천ㆍ경기ㆍ강원] 2026년 중소기업 AI훈련확산센터 참여기업 모집 공고",
            "description": "AI 도입 어려움을 겪는 중소기업 대상 컨설팅."}
    for city in ("서울", "인천", "경기"):
        assert _region_status(item, city) != "other_only", f"{city} 오차단(누락)"
    # 태그 밖 광역(부산)은 정상 차단(precision)
    assert _region_status(item, "부산") == "other_only"


def test_body_multiregion_restricted_own_eligible():
    """본문 '서울ㆍ인천ㆍ강원 소재 기업' — 나열된 광역 기업은 적격, 밖은 차단."""
    item = {"title": "2026년 상시 디자인 컨설팅 지원 공고",
            "description": "☞ 서울ㆍ인천ㆍ강원 소재 중소기업 대상 디자인 컨설팅 지원."}
    for city in ("서울", "인천", "강원"):
        assert _region_status(item, city) != "other_only", f"{city} 오차단(누락)"
    assert _region_status(item, "부산") == "other_only"


def test_applicant_restricted_regions_multiregion_list():
    """강신호 파서: ㆍ/및/, 로 이어진 다지역 나열을 전부 잡는다."""
    assert monitor._applicant_restricted_regions("서울, 인천 및 경기 지역 중소기업") == {"서울", "인천", "경기"}
    assert monitor._applicant_restricted_regions("부산 소재 기업만") == {"부산"}


def test_inline_multiregion_own_eligible():
    """인라인 '서울·인천 권역'(대괄호 없는 가운뎃점 나열) — own 광역은 적격, 밖은 차단."""
    item = {"title": "2026년 소셜 벤더 운영 사업(성장 지원형 – 서울·인천 권역) 참여 기업 모집",
            "description": ""}
    for city in ("서울", "인천"):
        assert _region_status(item, city) != "other_only", f"{city} 오차단(누락)"
    assert _region_status(item, "부산") == "other_only"


def test_detect_inline_region_list_scope():
    """인라인 가운뎃점 나열이 _resolve_applicant_region_scope.regions 에 전부 반영."""
    item = {"title": "성장 지원형 – 서울·인천 권역 모집", "description": ""}
    regions = set(monitor._resolve_applicant_region_scope(item)["regions"])
    assert {"서울", "인천"}.issubset(regions), regions


def test_title_region_tags_scope_symmetry():
    """제목 다지역 태그가 _resolve_applicant_region_scope.regions 에 전부 반영(대칭)."""
    item = {"title": "[서울ㆍ인천ㆍ경기ㆍ강원] 2026년 공고", "description": ""}
    regions = set(monitor._resolve_applicant_region_scope(item)["regions"])
    assert {"서울", "인천", "경기", "강원"}.issubset(regions), regions
