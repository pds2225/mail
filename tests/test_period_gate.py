"""TASK-032(MAIL-P1A-02) 기간 Hard Gate 표준 상태 판정 테스트.

7종 표준 상태(open/upcoming/closing_soon/closed/always_open/budget_based/
date_unknown)를 실제 공고 형태의 fixture로 검증한다. 기존 monitor.py
classify_deadline_status/is_imminent 를 재사용하므로, 여기서는 "표준 어휘로
잘 매핑되는지"와 "closing_soon 세분화가 정확한지"만 확인한다.
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

from mail_core.operations.period_gate import (  # noqa: E402
    ALWAYS_OPEN,
    BUDGET_BASED,
    CLOSED,
    CLOSING_SOON,
    DATE_UNKNOWN,
    OPEN,
    UPCOMING,
    classify_period_status,
    period_needs_review,
)

TODAY = date(2026, 6, 17)


def _it(title="공고", desc="", deadline=""):
    return {"id": "x", "title": title, "description": desc, "author": "기관", "deadline": deadline}


def _iso(offset_days: int) -> str:
    return (TODAY + timedelta(days=offset_days)).isoformat()


# ── 7종 상태 — 최소 1건씩 ────────────────────────────────────────────
def test_open_far_future_deadline():
    it = _it("지원 공고", f"마감 {_iso(30)} 까지 접수.")
    assert classify_period_status(it, TODAY) == OPEN


def test_upcoming_future_range():
    it = _it("예정 공고", f"예정 {_iso(20)} 부터 {_iso(40)} 까지 접수 예정.")
    assert classify_period_status(it, TODAY) == UPCOMING


def test_closing_soon_within_window():
    it = _it("마감임박 공고", f"마감 {_iso(3)} 까지 접수.")
    assert classify_period_status(it, TODAY) == CLOSING_SOON


def test_closed_past_deadline():
    it = _it("종료 공고", f"접수 {_iso(-10)} ~ {_iso(-1)} 로 종료.")
    assert classify_period_status(it, TODAY) == CLOSED


def test_always_open_term():
    it = _it("상시접수 공고", "상시접수 중")
    assert classify_period_status(it, TODAY) == ALWAYS_OPEN


def test_budget_based_term():
    it = _it("예산소진 공고", "예산 소진 시까지 접수")
    assert classify_period_status(it, TODAY) == BUDGET_BASED


def test_date_unknown_no_dates():
    it = _it("공고", "날짜 정보 없음")
    assert classify_period_status(it, TODAY) == DATE_UNKNOWN


# ── closing_soon 경계값(0일·7일 포함, 8일·과거는 제외) ──────────────────
def test_closing_soon_boundary_today_is_closing_soon():
    it = _it("공고", f"마감 {_iso(0)} 까지 접수.")
    assert classify_period_status(it, TODAY) == CLOSING_SOON


def test_closing_soon_boundary_7days_is_closing_soon():
    it = _it("공고", f"마감 {_iso(7)} 까지 접수.")
    assert classify_period_status(it, TODAY) == CLOSING_SOON


def test_closing_soon_boundary_8days_is_open_not_closing_soon():
    it = _it("공고", f"마감 {_iso(8)} 까지 접수.")
    assert classify_period_status(it, TODAY) == OPEN


# ── 마감시각 경계(날짜 단위 보존 — 마감일 당일=아직 유효, 다음날=마감) ──────
def test_deadline_day_itself_is_not_closed():
    """마감일 당일(오늘=마감일)은 아직 지나지 않았다 — 23:59:59 KST까지 유효."""
    it = _it("공고", f"마감 {_iso(0)} 까지 접수.")
    status = classify_period_status(it, TODAY)
    assert status != CLOSED


def test_day_after_deadline_is_closed():
    """마감일 다음날 00:00:00 KST부터는 지난 것으로 본다."""
    it = _it("공고", f"마감 {_iso(-1)} 까지 접수.")
    assert classify_period_status(it, TODAY) == CLOSED


# ── ACCEPTANCE_CRITERIA: closed 자동포함 0건 / date_unknown 자동제외 0건 ──
def test_closed_never_reported_as_open_family():
    """closed로 판정된 공고가 open/upcoming/closing_soon/always_open/budget_based
    어느 것으로도 새지 않는다(과잉 포함 방지)."""
    it = _it("공고", f"접수 {_iso(-30)} ~ {_iso(-1)} 로 종료.")
    assert classify_period_status(it, TODAY) == CLOSED


def test_date_unknown_needs_review_not_auto_excluded_or_included():
    """date_unknown은 review 대상 신호만 준다 — 이 모듈 자체가 제외/포함을
    결정하지 않는다(FORBIDDEN: 날짜불명 자동제외 금지)."""
    it = _it("공고", "신청 접수 안내")  # 날짜 토큰 없음
    status = classify_period_status(it, TODAY)
    assert status == DATE_UNKNOWN
    assert period_needs_review(status) is True


def test_non_date_unknown_does_not_need_review():
    it = _it("공고", f"마감 {_iso(30)} 까지 접수.")
    status = classify_period_status(it, TODAY)
    assert status != DATE_UNKNOWN
    assert period_needs_review(status) is False


# ── today=None 기본값 회귀(예외 없이 동작하는지만 확인 — 실시각 의존) ──────
def test_classify_period_status_default_today_does_not_raise():
    it = _it("공고", "상시접수 중")
    assert classify_period_status(it) == ALWAYS_OPEN
