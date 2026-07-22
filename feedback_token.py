#!/usr/bin/env python3
"""feedback_token — O/X 피드백 토큰 HMAC 서명·검증 (진단서 #132).

문제: 피드백 메일 제목 `[MAIL-FB] X <notice_id>` 에는 서명이 없어, 그 형식만 알면 누구나
  임의 공고에 O/X 를 위조해 골든(사람 정답)에 주입할 수 있다(collect_feedback 가 제목만 보고 축적).

이 모듈: (verdict, notice_id) 에 대한 짧은 HMAC-SHA256 태그를 만들고 검증한다.
  - 서명키는 환경변수 MAIL_FEEDBACK_SECRET.
  - **opt-in**: 키가 없으면 sign 은 빈 문자열, verify 는 항상 통과(종전 동작·하위호환).
    키가 있으면 제목에 서명이 붙고, 검증 실패(위조·미서명)한 피드백은 버려진다.
  - 상수시간 비교(hmac.compare_digest)로 타이밍 누출 방지.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

_SIG_LEN = 16                      # 제목에 붙는 16-hex (64bit) — 개인메일함 위조 방지엔 충분
_SIG_RE = re.compile(r"^[0-9a-f]{%d}$" % _SIG_LEN)


def _secret() -> str:
    return os.environ.get("MAIL_FEEDBACK_SECRET", "").strip()


def enabled() -> bool:
    """서명키가 설정돼 서명·검증이 활성인가."""
    return bool(_secret())


def sign(verdict: str, notice_id: str) -> str:
    """(verdict, notice_id) 의 서명 태그. 키 없으면 '' (서명 미부착)."""
    s = _secret()
    if not s:
        return ""
    msg = f"{str(verdict).strip().upper()}|{str(notice_id).strip()}".encode("utf-8")
    return hmac.new(s.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:_SIG_LEN]


def verify(verdict: str, notice_id: str, sig: str | None) -> bool:
    """서명 검증. 키 미설정이면 True(하위호환). 키 있으면 유효 서명만 True."""
    s = _secret()
    if not s:
        return True                # opt-in: 키 없으면 검증 안 함
    sig = (sig or "").strip().lower()
    if not _SIG_RE.match(sig):
        return False               # 미서명·형식오류 → 위조로 간주
    return hmac.compare_digest(sign(verdict, notice_id), sig)
