"""period_gate — MAIL-P1A-02(TASK-032): 접수상태를 7종 표준 상태로 통합 판정한다.

open / upcoming / closing_soon / closed / always_open / budget_based / date_unknown.

기존 monitor.classify_deadline_status()(마감 판정 엔진, 이미 다수 회귀 테스트로 검증됨)와
monitor.is_imminent()가 쓰는 "마감임박 0~7일" 윈도를 그대로 재사용한다. 이 모듈은
① classify_deadline_status의 원시 상태를 표준 어휘로 매핑하고
② "open" 중 마감이 0~7일 이내인 것만 closing_soon으로 세분화하는 얇은 레이어일 뿐,
날짜 파싱 로직 자체는 재구현하지 않는다(monitor.py의 _parse_date_candidates 재사용).

FORBIDDEN 준수: date_unknown을 이 모듈이 자동 제외(excluded) 처리하지 않는다 — 분류만
하고, 실제 제외 여부는 호출자(mail_core/matching/company_match.py의 _hard_excluded 등)
책임이다. 그 쪽은 이미 "closed"만 하드제외하므로(기존 동작 그대로), date_unknown은
자동으로 통과되어 review 대상처럼 다음 단계(점수 판정)로 넘어간다.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from monitor import (  # noqa: E402 — 기존 마감판정 엔진 재사용(재구현 금지)
    KST,
    NON_APPLICATION_PERIOD_LABELS,
    _notice_body_text,
    _parse_date_candidates,
    _posted_date,
    classify_deadline_status,
    extract_application_period,
)

OPEN = "open"
UPCOMING = "upcoming"
CLOSING_SOON = "closing_soon"
CLOSED = "closed"
ALWAYS_OPEN = "always_open"
BUDGET_BASED = "budget_based"
DATE_UNKNOWN = "date_unknown"

CANONICAL_STATUSES = (
    OPEN, UPCOMING, CLOSING_SOON, CLOSED, ALWAYS_OPEN, BUDGET_BASED, DATE_UNKNOWN,
)

# is_imminent()과 동일한 마감임박 윈도(기존 메일 상단 '⚠️ 마감 임박' 안내와 기준을
# 통일한다 — 여기서만 다른 값을 쓰면 같은 공고가 화면마다 다르게 보인다).
CLOSING_SOON_WINDOW_DAYS = 7

# classify_deadline_status의 원시 상태 → 이 모듈의 표준 7종 어휘.
# "extended"(마감연장, P0-15)는 다시 접수 중이라는 뜻이라 open으로 합친다(별도
# 표준 상태를 신설하지 않음 — 스펙이 정한 7종 밖).
_RAW_TO_CANONICAL = {
    "open": OPEN,
    "upcoming": UPCOMING,
    "closed": CLOSED,
    "always_open": ALWAYS_OPEN,
    "until_budget_exhausted": BUDGET_BASED,
    "extended": OPEN,
    "unknown": DATE_UNKNOWN,
}


def _resolve_end_date(item: dict, today: date):
    """closing_soon 판정용 마감일(date)을 찾는다(없으면 None).
    classify_deadline_status가 "open"을 판정할 때 실제로 쓰는 것과 동일한 소스·순서
    (구조화된 application_period → 라벨 스크러빙한 본문 날짜 → deadline 필드)를
    그대로 재사용해, "open으로 판정된 이유"와 "closing_soon 판정 근거"가 서로 다른
    날짜를 보는 일이 없게 한다(날짜 파싱 로직 자체는 재구현하지 않음)."""
    body_text = _notice_body_text(item)
    period = item.get("application_period") or extract_application_period(body_text, _posted_date(item))
    if period.get("end"):
        try:
            return datetime.strptime(period["end"], "%Y-%m-%d").date()
        except ValueError:
            pass
    scrubbed = body_text
    for lbl in NON_APPLICATION_PERIOD_LABELS:
        scrubbed = re.sub(
            rf"{re.escape(lbl.lower())}\s*[:：]?\s*[^\nㅇ]+",
            "",
            scrubbed,
            flags=re.IGNORECASE,
        )
    dates = [parsed for _, parsed in _parse_date_candidates(scrubbed, today.year)]
    if not dates:
        raw_deadline = (item.get("deadline") or "").strip()
        if raw_deadline:
            dates = [parsed for _, parsed in _parse_date_candidates(raw_deadline, today.year)]
    return max(dates) if dates else None


def _is_closing_soon(end_date, today: date) -> bool:
    if end_date is None:
        return False
    return 0 <= (end_date - today).days <= CLOSING_SOON_WINDOW_DAYS


def classify_period_status(item: dict, today: date | None = None) -> str:
    """공고 1건의 접수상태를 표준 7종 상태 중 하나로 반환한다.

    Asia/Seoul(KST) 기준. today를 넘기지 않으면 monitor.classify_deadline_status와
    동일한 "오늘"을 쓰도록 이 함수에서 한 번만 계산해 두 곳에 동일하게 넘긴다
    (마감시간은 날짜 단위로 보존 — 마감일 당일은 아직 open/closing_soon이고,
    다음 날부터 closed. 즉 마감은 그 날짜의 23:59:59 KST까지 유효한 것으로 다룬다.
    이는 기존 classify_deadline_status의 동작을 그대로 물려받은 것으로, 새 시각
    단위 비교를 도입하지 않는다 — AI가 추정 시각을 확정하지 않는다는 FORBIDDEN과도
    맞다)."""
    resolved_today = today if today is not None else datetime.now(KST).date()
    raw = classify_deadline_status(item, resolved_today)
    canonical = _RAW_TO_CANONICAL.get(raw, DATE_UNKNOWN)
    if canonical == OPEN:
        end_date = _resolve_end_date(item, resolved_today)
        if _is_closing_soon(end_date, resolved_today):
            return CLOSING_SOON
    return canonical


def period_needs_review(status: str) -> bool:
    """date_unknown은 자동 배제도, 자동 확정 포함도 아니고 사람 검토 대상이라는
    신호만 준다(FORBIDDEN: 날짜불명 자동제외 금지). 실제 배제/포함 결정은 호출자
    책임 — 이 함수는 "검토 목록에 얹을지" 판단에만 쓴다."""
    return status == DATE_UNKNOWN
