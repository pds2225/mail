"""명시된 접수 마감 시각·도착기준만 추출한다. 날짜 파서는 monitor를 재사용한다."""
from __future__ import annotations

import re
from datetime import datetime, time, timezone, timedelta

KST = timezone(timedelta(hours=9))
_CLOCK = re.compile(r"(?<!\d)(?:(오전|오후)\s*)?(\d{1,2})\s*(?::\s*(\d{2})|시(?:\s*(\d{1,2})\s*분)?)(?!\d)")
_DATE = re.compile(r"(?<!\d)(?:20\d{2}\s*[./-]\s*)?\d{1,2}\s*[./-]\s*\d{1,2}(?!\d)|(?:20\d{2}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일")


def extract_deadline_details(text: str) -> dict[str, str]:
    text = str(text or "")
    # 별도 행사·협약 시각은 접수 마감의 근거로 사용하지 않는다.
    segment = re.split(r"설명회|협약기간|사업기간|운영기간|문의처|문의\s*[:：]", text)[0]
    dates = list(_DATE.finditer(segment))
    if dates:
        segment = segment[dates[-1].end():]
    matches = list(_CLOCK.finditer(segment))
    value = ""
    if matches:
        match = matches[-1]
        ampm, hour, colon_minute, korean_minute = match.groups()
        hour, minute = int(hour), int(colon_minute or korean_minute or 0)
        if ampm and 1 <= hour <= 12:
            hour = hour % 12 + (12 if ampm == "오후" else 0)
        elif ampm:
            return {"deadline_time": "", "deadline_basis": "도착" if re.search(r"도착\s*(?:분|기준)|소인", text) else ""}
        if hour == 24 and minute == 0:
            value = "23:59"
        elif 0 <= hour <= 23 and 0 <= minute <= 59:
            value = f"{hour:02}:{minute:02}"
    basis = "도착" if re.search(r"도착\s*(?:분|기준)|소인", text) else ""
    return {"deadline_time": value, "deadline_basis": basis}


def deadline_has_passed(end, deadline_time: str, *, today, now=None) -> bool:
    if not re.fullmatch(r"\d{2}:\d{2}", deadline_time or ""):
        return False
    moment = now or (today if isinstance(today, datetime) else None)
    if moment is None:
        current = datetime.now(KST)
        # 日 단위로 주어진 과거/미래 테스트·재생은 그 날짜의 시작 시각으로 본다.
        moment = current if current.date() == today else datetime.combine(today, time.min, KST)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    moment = moment.astimezone(KST)
    try:
        cutoff = datetime.combine(end, time.fromisoformat(deadline_time), KST)
    except ValueError:
        return False
    return moment > cutoff


def deadline_time_label(value: str) -> str:
    hour, minute = value.split(":")
    return f"{int(hour)}시" if minute == "00" else f"{int(hour)}:{minute}"
