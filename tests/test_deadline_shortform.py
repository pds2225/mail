"""축약 마감표기(~M/D) 추출 회귀 가드.

한국 공고 제목에 흔한 '(~7/7)'·'(접수 6/24~7/7)' 축약 마감을 extract_application_period 가
게시일 기준 연도추론(마감≥게시일)으로 안전 복구하는지 확인. 오'마감'(false-past)=누락 방지가 핵심.
단독 foreground: python -m pytest test_deadline_shortform.py -q
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monitor  # noqa: E402


def _p(item):
    return monitor.extract_application_period(monitor._notice_body_text(item), monitor._posted_date(item))


def test_shortform_single_tilde_open():
    """~M/D 미래 마감 → open, 시작=게시일(upcoming 오분류 방지)."""
    it = {"title": "예비창업가 지원 (~8/2)", "posted_date": "2026-07-01", "description": ""}
    p = _p(it)
    assert p.get("end") == "2026-08-02"
    assert p.get("start") == "2026-07-01"  # 게시일


def test_shortform_range_with_trailing_time():
    """M/D~M/D 뒤에 '18시' 가 붙어도 범위 추출."""
    it = {"title": "설명회 (접수기간 : 6/24~7/7 18시까지)", "posted_date": "2026-06-20", "description": ""}
    p = _p(it)
    assert p.get("start") == "2026-06-24"
    assert p.get("end") == "2026-07-07"


def test_shortform_year_inference_deadline_ge_posted():
    """마감(월/일)이 게시일보다 앞서면 +1년(마감≥게시 규칙) — false-past 방지."""
    it = {"title": "공고(~2/27)", "posted_date": "2025-12-20", "description": ""}
    p = _p(it)
    assert p.get("end") == "2026-02-27"  # 2/27 < 12/20 → 다음해


def test_shortform_month_day_korean():
    """~M월D일 형식."""
    it = {"title": "모집 ~ 7월 31일 마감", "posted_date": "2026-07-01", "description": ""}
    p = _p(it)
    assert p.get("end") == "2026-07-31"


def test_full_date_label_not_broken():
    """라벨+완전날짜(2026.07.01~2026.08.02)는 기존대로 정확 — 축약 폴백이 훼손 안 함."""
    it = {"title": "사업", "posted_date": "2026-06-01",
          "description": "신청기간 : 2026.07.01 ~ 2026.08.02"}
    p = _p(it)
    assert p.get("end") == "2026-08-02"


def test_no_date_stays_empty():
    """마감 단서 전무 → {} (unknown 유지, recall-safe로 surface)."""
    it = {"title": "상시 모집 안내", "posted_date": "2026-07-01", "description": "관심 있는 기업의 참여 바랍니다."}
    assert _p(it) == {}


def test_status_open_closed_by_today():
    """게시일 기준 복구된 마감으로 open/closed 판정이 정상."""
    future = {"title": "(~12/31)", "posted_date": "2026-07-01", "description": ""}
    assert monitor.classify_deadline_status(future) == "open"
    past = {"title": "(~1/5)", "posted_date": "2026-01-02", "description": ""}
    assert monitor.classify_deadline_status(past) == "closed"
