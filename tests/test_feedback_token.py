"""O/X 피드백 토큰 HMAC + expiry 회귀 테스트 (Risk #132).

핵심 성질:
- 키 미설정/잘못된 TTL → fail-closed
- 토큰은 issued_at.HMAC 형식
- 위조/미서명/legacy timestamp-less/만료/과도한 미래 토큰 거부
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mail_core.delivery import feedback_token as ft  # noqa: E402
from mail_core.delivery import feedback as fb  # noqa: E402

SECRET = "test-secret-abc123"
ISSUED_AT = 1_800_000_000


def _enable(monkeypatch, ttl: int = 3600):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    monkeypatch.setenv("MAIL_FEEDBACK_TOKEN_TTL_SECONDS", str(ttl))


def test_no_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("MAIL_FEEDBACK_SECRET", raising=False)
    monkeypatch.delenv("MAIL_FEEDBACK_TOKEN_TTL_SECONDS", raising=False)
    assert ft.enabled() is False
    assert ft.sign("O", "PBLN_1", issued_at=ISSUED_AT) == ""
    assert ft.verify("O", "PBLN_1", None, now=ISSUED_AT) is False
    assert ft.verify("X", "PBLN_1", "deadbeefdeadbeef", now=ISSUED_AT) is False


def test_invalid_ttl_fails_closed(monkeypatch):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    monkeypatch.setenv("MAIL_FEEDBACK_TOKEN_TTL_SECONDS", "not-a-number")
    assert ft.enabled() is False
    assert ft.sign("O", "PBLN_1", issued_at=ISSUED_AT) == ""


def test_sign_and_verify_roundtrip(monkeypatch):
    _enable(monkeypatch)
    token = ft.sign("O", "PBLN_000123", issued_at=ISSUED_AT)
    ts, sig = token.split(".", 1)
    assert ts == str(ISSUED_AT)
    assert len(sig) == 16 and all(c in "0123456789abcdef" for c in sig)
    assert ft.verify("O", "PBLN_000123", token, now=ISSUED_AT + 30) is True


def test_verify_rejects_forgery(monkeypatch):
    _enable(monkeypatch)
    token = ft.sign("O", "PBLN_000123", issued_at=ISSUED_AT)
    assert ft.verify("X", "PBLN_000123", token, now=ISSUED_AT) is False
    assert ft.verify("O", "PBLN_999999", token, now=ISSUED_AT) is False
    assert ft.verify("O", "PBLN_000123", None, now=ISSUED_AT) is False
    assert ft.verify("O", "PBLN_000123", f"{ISSUED_AT}." + "0" * 16, now=ISSUED_AT) is False


def test_expired_token_is_rejected(monkeypatch):
    _enable(monkeypatch, ttl=60)
    token = ft.sign("O", "PBLN_1", issued_at=ISSUED_AT)
    assert ft.verify("O", "PBLN_1", token, now=ISSUED_AT + 60) is True
    assert ft.verify("O", "PBLN_1", token, now=ISSUED_AT + 61) is False


def test_excessively_future_token_is_rejected(monkeypatch):
    _enable(monkeypatch)
    token = ft.sign("O", "PBLN_1", issued_at=ISSUED_AT + 301)
    assert ft.verify("O", "PBLN_1", token, now=ISSUED_AT) is False


def test_legacy_timestamp_less_token_is_rejected(monkeypatch):
    _enable(monkeypatch)
    assert ft.verify("O", "PBLN_1", "deadbeefdeadbeef", now=ISSUED_AT) is False


def test_secret_change_invalidates(monkeypatch):
    _enable(monkeypatch)
    token = ft.sign("O", "PBLN_1", issued_at=ISSUED_AT)
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", "different-secret")
    assert ft.verify("O", "PBLN_1", token, now=ISSUED_AT) is False


# ── feedback.py 통합 ──
def test_mailto_includes_timestamped_signature_when_enabled(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(ft.time, "time", lambda: ISSUED_AT)
    url = fb.feedback_mailto("me@x.com", "X", "PBLN_42")
    from urllib.parse import unquote
    subj = unquote(url)
    assert f"[MAIL-FB] X PBLN_42 {ISSUED_AT}." in subj
    token = subj.split("PBLN_42 ", 1)[1].strip()
    assert ft.verify("X", "PBLN_42", token, now=ISSUED_AT)


def test_parse_accepts_valid_and_rejects_forged(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(ft.time, "time", lambda: ISSUED_AT)
    token = ft.sign("O", "PBLN_7", issued_at=ISSUED_AT)
    assert fb.parse_feedback_subject(f"[MAIL-FB] O PBLN_7 {token}") == {"verdict": "O", "id": "PBLN_7"}
    assert fb.parse_feedback_subject("[MAIL-FB] O PBLN_7") is None
    assert fb.parse_feedback_subject(f"[MAIL-FB] O PBLN_7 {ISSUED_AT}." + "0" * 16) is None
    assert fb.parse_feedback_subject(f"[MAIL-FB] O PBLN_OTHER {token}") is None
    assert fb.parse_feedback_subject("[MAIL-FB] O PBLN_7 deadbeefdeadbeef") is None


def test_parse_rejects_expired_token(monkeypatch):
    _enable(monkeypatch, ttl=60)
    token = ft.sign("X", "PBLN_9", issued_at=ISSUED_AT)
    monkeypatch.setattr(ft.time, "time", lambda: ISSUED_AT + 61)
    assert fb.parse_feedback_subject(f"[MAIL-FB] X PBLN_9 {token}") is None


def test_parse_unsigned_rejected_without_secret(monkeypatch):
    monkeypatch.delenv("MAIL_FEEDBACK_SECRET", raising=False)
    monkeypatch.delenv("MAIL_FEEDBACK_TOKEN_TTL_SECONDS", raising=False)
    assert fb.parse_feedback_subject("[MAIL-FB] X PBLN_9") is None
