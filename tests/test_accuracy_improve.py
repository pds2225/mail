"""정확도 개선 회귀 테스트 (네트워크/SMTP 없음).

세 결함을 고정한다:
  #1 ASCII 키워드 부분문자열 오매칭 (evaluate_notice/keyword_match) — precision
  #2 주말 게시공고 영구 누락 (partition_posted_dates) — recall
  #3 MM.DD 비날짜 오탐 (_parse_date_candidates/extract_date_from_text) — precision
"""
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────
def _grp(or_kws, regions=("전국",), city="서울특별시", label="서울"):
    return {
        "name": "t",
        "or_keywords": list(or_kws),
        "required_conditions": {"regions": list(regions)},
        "applicant_region_city": city,
        "applicant_region_label": label,
    }


def _it(title, desc="전국 중소기업 대상 신청접수 모집공고"):
    return {
        "id": "x", "title": title, "description": desc, "author": "기관",
        "deadline": "2099-12-31", "is_aggregator": False,
    }


# ══════════════════════════════════════════════════════════════════
# #1 ASCII 키워드 단어경계
# ══════════════════════════════════════════════════════════════════
def test_ascii_keyword_no_substring_false_match():
    """'AI' 가 'retail'/'email'/'campaign' 의 부분문자열 'ai' 에 오매칭되면 안 된다."""
    for noise in ["retail 매장 지원", "email 마케팅 지원", "campaign 운영 지원"]:
        ev = m.evaluate_notice(_it(noise), _grp(["AI"]))
        assert "INDUSTRY_NOT_MATCHED" in ev["exclude_reason_codes"], noise


def test_ascii_keyword_real_match_preserved():
    """실제 'AI' 공고는 계속 통과."""
    ev = m.evaluate_notice(_it("AI 솔루션 도입 지원"), _grp(["AI"]))
    assert "INDUSTRY_NOT_MATCHED" not in ev["exclude_reason_codes"]


def test_ip_keyword_no_substring_false_match():
    """'IP' 가 'equipment'/'participation' 에 오매칭되면 안 된다(비앤코 그룹 키워드)."""
    ev = m.evaluate_notice(
        _it("equipment 도입 participation 지원"),
        _grp(["IP"], regions=["인천"], city="인천광역시", label="인천"),
    )
    assert "INDUSTRY_NOT_MATCHED" in ev["exclude_reason_codes"]


def test_ip_keyword_real_match_preserved():
    ev = m.evaluate_notice(
        _it("IP 나래 지식재산 지원"),
        _grp(["IP"], regions=["인천"], city="인천광역시", label="인천"),
    )
    assert "INDUSTRY_NOT_MATCHED" not in ev["exclude_reason_codes"]


def test_korean_keyword_substring_preserved():
    """한글 키워드는 합성어 부분문자열 매칭 유지: '데이터' ⊂ '빅데이터'."""
    ev = m.evaluate_notice(_it("빅데이터 플랫폼 지원"), _grp(["데이터"]))
    assert "INDUSTRY_NOT_MATCHED" not in ev["exclude_reason_codes"]


def test_keyword_match_ascii_boundary():
    assert m.keyword_match({"title": "retail 매장", "description": "", "author": ""},
                           {"keywords": ["AI"]}) is False
    assert m.keyword_match({"title": "AI 사업", "description": "", "author": ""},
                           {"keywords": ["AI"]}) is True
    assert m.keyword_match({"title": "빅데이터 사업", "description": "", "author": ""},
                           {"keywords": ["데이터"]}) is True


# ══════════════════════════════════════════════════════════════════
# #2 주말 게시공고 recall
# ══════════════════════════════════════════════════════════════════
def test_weekend_postings_caught_on_monday():
    """월요일 실행: 직전 금요일 + 그 뒤 토·일 게시공고를 모두 잡아야 한다."""
    monday = datetime(2026, 6, 15, 8, 0, tzinfo=m.KST)  # 월요일
    items = [
        {"id": "fri", "title": "금", "posted_date": "2026-06-12", "is_aggregator": False},
        {"id": "sat", "title": "토", "posted_date": "2026-06-13", "is_aggregator": False},
        {"id": "sun", "title": "일", "posted_date": "2026-06-14", "is_aggregator": False},
        {"id": "thu", "title": "목", "posted_date": "2026-06-11", "is_aggregator": False},
    ]
    matched, unknown, excluded = m.partition_posted_dates(items, days_back=1, now_dt=monday)
    assert {i["id"] for i in matched} == {"fri", "sat", "sun"}
    assert {i["id"] for i in excluded} == {"thu"}
    assert unknown == []


def test_weekday_single_day_unchanged():
    """평일 실행: 직전 영업일 하루치만(기존 동작 보존)."""
    tue = datetime(2026, 6, 16, 8, 0, tzinfo=m.KST)  # 화요일
    items = [
        {"id": "mon", "title": "월", "posted_date": "2026-06-15", "is_aggregator": False},
        {"id": "fri", "title": "금", "posted_date": "2026-06-12", "is_aggregator": False},
    ]
    matched, unknown, excluded = m.partition_posted_dates(items, days_back=1, now_dt=tue)
    assert {i["id"] for i in matched} == {"mon"}
    assert {i["id"] for i in excluded} == {"fri"}


def test_sunday_run_catches_saturday():
    """일요일 실행도 토요일 게시물을 잡는다."""
    sunday = datetime(2026, 6, 14, 8, 0, tzinfo=m.KST)  # 일요일
    items = [
        {"id": "sat", "title": "토", "posted_date": "2026-06-13", "is_aggregator": False},
        {"id": "fri", "title": "금", "posted_date": "2026-06-12", "is_aggregator": False},
    ]
    matched, _u, _e = m.partition_posted_dates(items, days_back=1, now_dt=sunday)
    assert {i["id"] for i in matched} == {"fri", "sat"}


# ══════════════════════════════════════════════════════════════════
# #3 MM.DD 비날짜 오탐
# ══════════════════════════════════════════════════════════════════
def test_mmdd_unit_suffix_not_parsed_as_date():
    """퍼센트·금액·배수는 날짜가 아니다."""
    assert m.extract_date_from_text("2.5% 할인 행사") == ""
    assert m.extract_date_from_text("3.4억원 지원") == ""
    assert m.extract_date_from_text("최대 1.5배 우대") == ""


def test_mmdd_real_bare_date_still_parsed():
    """연도 없는 실제 날짜는 계속 인식한다."""
    got = m.extract_date_from_text("접수마감 6.13 까지")
    assert got.endswith("-06-13"), got


def test_full_date_unaffected():
    """완전한 날짜(YYYY.MM.DD)는 영향 없음."""
    assert m.extract_date_from_text("신청기간 2026.06.13 까지") == "2026-06-13"
