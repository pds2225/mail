"""정확도 회귀 가드 — region_FP(타지역 오추천) = 0 을 매 PR 자동 검증 (CI 게이트).

대표 합성 공고셋 × 대표 지역 기업으로, '맞춤(matched)'된 공고가 그 기업의 타지역이면 실패.
인천고정 버그 수정(_enrich_for_company)·지역판정·권역 일반화의 통합 회귀를 한 번에 지킨다.
전수(raw store) 측정은 scripts/accuracy_eval.py 로 수동 실행. self-contained.
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
import accuracy_eval as ae  # noqa: E402
import company_match as cm  # noqa: E402
import run_company_match as rcm  # noqa: E402

# region_field(정답 지역)를 가진 합성 공고 — 명시 타지역 한정 + own + 전국 혼합
ITEMS = [
    {"title": "대구 제조 지원", "description": "대구광역시 소재 제조기업만 신청.", "region_field": "대구광역시"},
    {"title": "부산 물류 지원", "description": "부산광역시 소재 기업만 신청.", "region_field": "부산광역시"},
    {"title": "서울 AI 사업화", "description": "서울특별시 소재 인공지능 기업 대상.", "region_field": "서울특별시"},
    {"title": "광주 콘텐츠 지원", "description": "광주광역시 소재 기업만.", "region_field": "광주광역시"},
    {"title": "충북 제조 지원", "description": "충청북도 소재 제조기업 대상.", "region_field": "충청북도"},
    {"title": "전국 수출바우처", "description": "전국 중소 제조기업 대상.", "region_field": "전국"},
    {"title": "인천 남동구 스마트공장", "description": "인천 남동구 소재 제조기업 대상.", "region_field": "인천광역시"},
]


def _comp(city, dist=""):
    return {"id": "t", "email": cm.TEST_RECIPIENT, "active": True,
            "region": {"city": city, "district": dist},
            "industry_keywords": ["제조", "제조업", "AI", "인공지능"],
            "interest_keywords": ["수출", "사업화", "제조"],
            "exclude_keywords": [], "match_threshold": 50}


COMPANIES = {
    "인천": _comp("인천", "남동구"),
    "서울": _comp("서울"),
    "부산": _comp("부산"),
}


def test_region_fp_zero_on_synthetic_set():
    """대표 공고셋 × 대표 기업: matched 중 기업 타지역(region_field) 추천이 0건이어야 한다."""
    leaks = []
    for name, company in COMPANIES.items():
        city = company["region"]["city"]
        enriched = rcm._enrich_for_company(ITEMS, company)
        res = cm.match_for_company(enriched, company)
        for it in res["matched"]:
            rf = str(it.get("region_field") or "")
            if ae._is_region_fp(rf, city):
                leaks.append(f"{name}기업 ← [{rf}] {it.get('title')}")
    assert not leaks, "region_FP(타지역 오추천) 발생:\n  " + "\n  ".join(leaks)
