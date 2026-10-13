"""digest_lint — 발송 직전 그룹 메일(제목+본문) 형식 검사(MAIL-035).

run #263/#264 실메일에서 나온 유형을 렌더 결과물 기준으로 다시 잡는다(입력 데이터가 아닌
'실제로 나갈 글자' 를 본다). 부작용 없음 — 고치는 것은 호출측(monitor)이 한다.

검사 코드
  EXPIRED          카드 마감이 지난 날짜(D+N)
  JUNK_SUPPORT     💰 줄이 게시판 잡텍스트(is_support_junk)
  SUBJECT_COUNT    제목 'N건' ≠ 카드 수
  HEADER_COUNT     헤더 '그룹 매칭 N건' ≠ 카드 수
  SECTION_COUNT    '■ 섹션 (N건)' ≠ 그 섹션 카드 수
  FOOTER_AS_CARD   구분선·🙋 줄이 카드로 파싱됨
  UNKNOWN_SHARE    마감 '확인필요' 비율이 임계 이상(경고)
"""
from __future__ import annotations

import os
import re
from typing import Callable

from mail_core.delivery.digest_table import HEADER_LINE, _SECTION_RE, parse_plain_table

_SUBJECT_COUNT_RE = re.compile(r"\]\s*(\d+)건")
_HEADER_COUNT_RE = re.compile(r"그룹 매칭\s*(\d+)건")
_PAST_RE = re.compile(r"\(D\+\d+\)")
_FOOTER_TITLE_RE = re.compile(r"^\s*(?:[─━—=_\-]{5,}|🙋|ⓘ)")
UNKNOWN_SHARE_LIMIT = 0.5
FIXABLE = {"EXPIRED", "JUNK_SUPPORT", "SUBJECT_COUNT", "HEADER_COUNT", "SECTION_COUNT", "FOOTER_AS_CARD"}


def lint_enabled() -> bool:
    return os.environ.get("MAIL_DIGEST_LINT", "1").strip() not in ("0", "false", "False")


def lint_blocking() -> bool:
    """MAIL_DIGEST_LINT_BLOCKING=1 이면 자동수정 후에도 남은 오류가 있는 그룹은 발송 보류(기본 off)."""
    return os.environ.get("MAIL_DIGEST_LINT_BLOCKING", "").strip() in ("1", "true", "True")


def lint_digest(subject: str, body: str, *, is_junk: Callable[[str], bool] | None = None) -> dict:
    issues: list[dict] = []
    _before, rows, _after = parse_plain_table(body or "")
    rows = rows or []
    cards = len(rows)

    def add(code, detail, title=""):
        issues.append({"code": code, "detail": detail, **({"title": title[:80]} if title else {})})

    for r in rows:
        title = str(r.get("공고") or "")
        if _FOOTER_TITLE_RE.match(title):
            add("FOOTER_AS_CARD", "꼬리말 줄이 카드로 파싱됨", title)
            continue
        dl = str(r.get("마감") or "")
        if _PAST_RE.search(dl):
            add("EXPIRED", f"지난 마감 {dl}", title)
        sup = str(r.get("지원내용") or "").rstrip("…")
        if sup and is_junk and is_junk(sup):
            add("JUNK_SUPPORT", f"💰 잡텍스트: {sup[:40]}", title)

    m = _SUBJECT_COUNT_RE.search(subject or "")
    if m and HEADER_LINE in (body or "") and int(m.group(1)) != cards:
        add("SUBJECT_COUNT", f"제목 {m.group(1)}건 ≠ 카드 {cards}건")
    m = _HEADER_COUNT_RE.search(body or "")
    if m and HEADER_LINE in (body or "") and int(m.group(1)) != cards:
        add("HEADER_COUNT", f"헤더 {m.group(1)}건 ≠ 카드 {cards}건")

    # 섹션 헤더 숫자 vs 그 섹션 카드 수(본문 원문 기준)
    declared: dict[str, int] = {}
    for line in (body or "").split("\n"):
        sm = _SECTION_RE.match(line)
        if sm:
            declared[sm.group("name")] = int(sm.group("n"))
    actual: dict[str, int] = {}
    for r in rows:
        actual[r.get("지원") or ""] = actual.get(r.get("지원") or "", 0) + 1
    for name, n in declared.items():
        if actual.get(name, 0) != n:
            add("SECTION_COUNT", f"■ {name} ({n}건) ≠ 카드 {actual.get(name, 0)}건")

    unknown = sum(1 for r in rows if str(r.get("마감") or "") == "확인필요")
    share = (unknown / cards) if cards else 0.0
    if cards >= 3 and share >= UNKNOWN_SHARE_LIMIT:
        add("UNKNOWN_SHARE", f"마감 확인필요 {unknown}/{cards}건({share:.0%})")

    return {
        "ok": not any(i["code"] in FIXABLE for i in issues),
        "cards": cards,
        "unknown_deadline": unknown,
        "issues": issues,
        "codes": sorted({i["code"] for i in issues}),
    }


def strip_junk_support_lines(body: str, is_junk: Callable[[str], bool]) -> str:
    """본문에서 잡텍스트 💰 줄만 지운다(카드·건수는 그대로)."""
    out = []
    for line in (body or "").split("\n"):
        s = line.strip()
        if s.startswith("💰 ") and is_junk(s[2:].strip().rstrip("…")):
            continue
        out.append(line)
    return "\n".join(out)


_MAILTO_RE = re.compile(r"mailto:[^\s\"'<>)]+", re.I)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_FB_TOKEN_RE = re.compile(r"\[MAIL-FB\][^\n<\"]*|%5BMAIL-FB%5D[^\s\"'<>]*", re.I)


def redact(text: str) -> str:
    """기록용: 피드백 mailto·토큰·이메일 주소를 지운다(수신자·토큰이 아티팩트에 남지 않게)."""
    t = _MAILTO_RE.sub("mailto:<redacted>", str(text or ""))
    t = _FB_TOKEN_RE.sub("<fb-redacted>", t)
    return _EMAIL_RE.sub("<email>", t)
