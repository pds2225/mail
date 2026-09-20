#!/usr/bin/env python3
"""feedback_token — O/X 피드백 토큰 HMAC 서명·만료 검증 (Risk #132).

토큰 형식:
    <issued_at_unix>.<16-hex HMAC>

서명 대상은 verdict, notice_id, issued_at 이며 기본 유효기간은 14일이다.
키가 없거나 TTL 설정이 잘못됐거나 토큰이 위조/만료/과도한 미래시각이면 fail-closed 한다.

보안 원칙:
- MAIL_FEEDBACK_SECRET 은 환경변수/Secret 으로만 주입한다.
- 과거 timestamp 없는 16-hex 토큰은 기본적으로 거부한다. 만료를 검증할 수 없기 때문이다.
- hmac.compare_digest 로 서명을 비교한다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time

_SIG_LEN = 16
_DEFAULT_TTL_SECONDS = 14 * 24 * 60 * 60
_MAX_FUTURE_SKEW_SECONDS = 5 * 60
_TOKEN_RE = re.compile(r"^(?P<issued_at>[0-9]{9,12})\.(?P<sig>[0-9a-f]{%d})$" % _SIG_LEN)


def _secret() -> str:
    return os.environ.get("MAIL_FEEDBACK_SECRET", "").strip()


def _ttl_seconds() -> int:
    raw = os.environ.get("MAIL_FEEDBACK_TOKEN_TTL_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def enabled() -> bool:
    """서명키와 유효한 TTL이 모두 있어 서명·검증이 활성인가."""
    return bool(_secret()) and _ttl_seconds() > 0


def _signature(verdict: str, notice_id: str, issued_at: int) -> str:
    s = _secret()
    msg = (
        f"{str(verdict).strip().upper()}|{str(notice_id).strip()}|{int(issued_at)}"
    ).encode("utf-8")
    return hmac.new(s.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:_SIG_LEN]


def sign(verdict: str, notice_id: str, *, issued_at: int | None = None) -> str:
    """서명+발급시각 토큰. 비활성 상태면 빈 문자열."""
    if not enabled():
        return ""
    ts = int(time.time()) if issued_at is None else int(issued_at)
    return f"{ts}.{_signature(verdict, notice_id, ts)}"


def verify(
    verdict: str,
    notice_id: str,
    token: str | None,
    *,
    now: int | None = None,
) -> bool:
    """토큰 HMAC·발급시각·만료를 검증한다."""
    if not enabled():
        return False
    token = (token or "").strip().lower()
    match = _TOKEN_RE.fullmatch(token)
    if not match:
        return False

    issued_at = int(match.group("issued_at"))
    current = int(time.time()) if now is None else int(now)
    if issued_at > current + _MAX_FUTURE_SKEW_SECONDS:
        return False
    if current - issued_at > _ttl_seconds():
        return False

    expected = _signature(verdict, notice_id, issued_at)
    return hmac.compare_digest(expected, match.group("sig"))
