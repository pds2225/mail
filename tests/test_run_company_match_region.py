"""run_company_match 인천고정 버그 회귀 — 기업별 합성 group 으로 evaluate_notice 지역판정.

evaluate_notice 를 group 없이(인천 고정) 호출하면 비인천 기업(서울 등) 추천이 인천 기준으로
오염되던 버그(2026-06-29 수정)의 회귀. 기업 city 로 합성 group 을 만들어 각 기업 기준 판정.
네트워크/SMTP 없음 (self-contained).
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
import run_company_match as rcm  # noqa: E402

SEOUL_NOTICE = {"title": "서울 AI 사업화 지원", "description": "서울특별시 소재 인공지능 데이터 기업 대상."}
BUSAN_NOTICE = {"title": "부산 제조 물류 지원", "description": "부산광역시 소재 제조기업만 신청."}


def _comp(city, dist=""):
    return {"id": "t", "email": cm.TEST_RECIPIENT, "active": True,
            "region": {"city": city, "district": dist},
            "industry_keywords": ["제조", "AI", "인공지능"], "interest_keywords": ["사업화"],
            "exclude_keywords": [], "match_threshold": 50}


def test_synth_group_uses_company_city():
    sg = rcm._synth_group(_comp("서울"))
    assert sg["applicant_region_city"] == "서울"
    assert rcm._synth_group({"region": {}}) is None  # city 없으면 None


def test_seoul_company_keeps_seoul_notice():
    """★인천고정 버그 회귀: 서울 기업이 '서울 소재' 공고를 인천 기준으로 놓치지 않는다."""
    enriched = rcm._enrich_for_company([SEOUL_NOTICE], _comp("서울"))[0]
    assert cm._hard_excluded(enriched) is None  # 서울기업 기준 → 통과


def test_seoul_company_blocks_busan_notice():
    enriched = rcm._enrich_for_company([BUSAN_NOTICE], _comp("서울"))[0]
    assert cm._hard_excluded(enriched) is not None  # 서울기업 → 부산 한정 제외


def test_busan_company_keeps_busan_notice():
    enriched = rcm._enrich_for_company([BUSAN_NOTICE], _comp("부산"))[0]
    assert cm._hard_excluded(enriched) is None  # 부산기업 → 부산 공고 통과


def test_incheon_company_regression_unchanged():
    """인천 기업은 합성 group=인천 → 기존(인천고정)과 동일하게 타지역 공고 제외(회귀 무변)."""
    enriched = rcm._enrich_for_company([SEOUL_NOTICE], _comp("인천", "남동구"))[0]
    assert cm._hard_excluded(enriched) is not None  # 인천기업 → 서울 한정 제외(정상)
