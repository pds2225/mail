"""mail targeting precision 테스트.

검증 대상(신규):
- refine_included_by_company: evaluate_notice 통과분에 기업 프로필 2차 컷오프
  · 비활성/미연결 시 하위호환(원본 그대로)
  · 활성+연결 시 점수 미달(타지역·안내성)은 검토 강등
- partition_posted_dates(max_age_days): '옛날 공고' 강제 제외 노브
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 환경변수 mock — monitor 임포트 전에 설정
os.environ.setdefault("BIZINFO_API_KEY",    "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY",  "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS",      "test@test.com")

from monitor import refine_included_by_company, partition_posted_dates, previous_business_day


def _company():
    return {
        "id": "cmp_test",
        "name": "테스트 인천 화장품 제조",
        "email": "ekth3691@gmail.com",
        "active": True,
        "region": {"city": "인천", "district": "남동구"},
        "industry_keywords": ["화장품", "제조"],
        "interest_keywords": ["수출바우처", "수출"],
        "exclude_keywords": ["설명회"],
        "has_factory": True,
        "export_focus": True,
        "support_type_prefs": ["지원금/바우처"],
        "match_threshold": 50,
    }


HIGH = {"title": "인천 남동구 화장품 제조기업 수출바우처 지원사업 신청 접수"}
LOW = {"title": "부산 소상공인 교육 설명회 안내"}  # 타지역 + 제외(설명회)


def test_disabled_passthrough():
    """company_match_enabled=False → 원본 그대로, 강등 없음 (하위호환)."""
    kept, demoted = refine_included_by_company(
        [HIGH, LOW], {"company_id": "cmp_test"},
        {"company_match_enabled": False}, {"cmp_test": _company()},
    )
    assert kept == [HIGH, LOW]
    assert demoted == []


def test_no_company_id_passthrough():
    """그룹에 company_id 미연결 → 원본 그대로 (하위호환)."""
    kept, demoted = refine_included_by_company(
        [HIGH, LOW], {},  # company_id 없음
        {"company_match_enabled": True}, {"cmp_test": _company()},
    )
    assert kept == [HIGH, LOW]
    assert demoted == []


def test_enabled_cutoff():
    """활성+연결 → 적합 공고만 통과, 타지역·안내성은 검토 강등."""
    kept, demoted = refine_included_by_company(
        [HIGH, LOW], {"company_id": "cmp_test"},
        {"company_match_enabled": True}, {"cmp_test": _company()},
    )
    kept_titles = [it.get("title") for it in kept]
    demoted_titles = [it.get("title") for it in demoted]
    assert HIGH["title"] in kept_titles
    assert LOW["title"] in demoted_titles
    # 통과분에는 매칭 점수가 부여된다
    assert all("_match_score" in it for it in kept)


def test_max_posted_age_excludes_old():
    """max_age_days 지정 시 오래된 게시일 공고는 too_old 로 제외."""
    target = previous_business_day(days_back=1)
    fresh = {"id": "f", "title": "신규 공고", "posted_date": target.strftime("%Y-%m-%d")}
    old = {"id": "o", "title": "옛날 공고", "posted_date": "2000-01-01"}
    matched, unknown, excluded = partition_posted_dates([fresh, old], days_back=1, max_age_days=7)
    matched_ids = [it["id"] for it in matched]
    excluded_reasons = [it.get("_excluded_reason") for it in excluded]
    assert "f" in matched_ids
    assert "o" not in matched_ids
    assert "too_old" in excluded_reasons


def test_max_posted_age_none_keeps_default():
    """max_age_days=None(기본) → 기존 '직전영업일 정확일치' 동작 유지."""
    target = previous_business_day(days_back=1)
    fresh = {"id": "f", "title": "신규", "posted_date": target.strftime("%Y-%m-%d")}
    matched, unknown, excluded = partition_posted_dates([fresh], days_back=1, max_age_days=None)
    assert [it["id"] for it in matched] == ["f"]
