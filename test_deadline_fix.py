"""마감 과잉거름 수정 회귀 테스트.

버그: classify_deadline_status 의 본문 날짜 폴백이 위치순 마지막 날짜(dates[-1])를 마감으로 봐서,
본문 뒤쪽 과거 참조일(작년 실적·문의일 등) 때문에 살아있는 공고를 '마감됨'으로 오판했다.
수정: 마감 = max(dates)(가장 늦은 날짜) → 모든 날짜가 과거일 때만 closed.
"""
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402

TODAY = date(2026, 6, 17)


def _it(title="공고", desc="", deadline=""):
    return {"id": "x", "title": title, "description": desc, "author": "기관", "deadline": deadline}


def test_future_deadline_with_trailing_past_date_is_open():
    """본문폴백: 미래 마감(6.30)이 앞·과거 참조일(2025.1.1)이 뒤 → 예전 closed(오판) → 이제 open."""
    it = _it("AI 바우처 지원 공고", "접수 2026.06.30까지. 작년 2025.01.01 대비 개선 지원.")
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_all_past_dates_still_closed():
    """모든 날짜가 과거면 여전히 마감(과잉 포함 방지)."""
    it = _it("옛 지원사업 공고", "접수 2025.01.01 ~ 2025.02.01 로 종료.")
    assert m.classify_deadline_status(it, TODAY) == "closed"


def test_single_future_date_open():
    it = _it("지원 공고", "마감 2026.12.31 까지 접수.")
    assert m.classify_deadline_status(it, TODAY) == "open"


def test_future_only_range_upcoming():
    """모든 날짜가 미래인 2개 이상 구간 → 예정(upcoming)."""
    it = _it("예정 공고", "예정 2026.08.01 부터 2026.08.31 까지 접수 예정.")
    assert m.classify_deadline_status(it, TODAY) == "upcoming"


def test_application_period_label_path_unchanged():
    """신청기간 라벨 경로(내 수정과 무관)는 그대로."""
    assert m.classify_deadline_status(_it("공고", "신청기간: 2025.01.01 ~ 2025.02.01"), TODAY) == "closed"
    assert m.classify_deadline_status(_it("공고", "신청기간: 2026.06.01 ~ 2026.06.30"), TODAY) == "open"


def test_open_deadline_terms_unchanged():
    assert m.classify_deadline_status(_it("상시접수 공고", "상시접수 중"), TODAY) == "open"
    assert m.classify_deadline_status(_it("수시접수 공고", "수시접수"), TODAY) == "open"


def test_no_dates_unknown():
    assert m.classify_deadline_status(_it("공고", "날짜 정보 없음"), TODAY) == "unknown"
