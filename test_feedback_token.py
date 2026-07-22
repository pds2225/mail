"""O/X 피드백 토큰 HMAC 서명·검증 회귀 테스트 (진단서 #132).

핵심 성질:
  · 키 미설정 → 서명 없음·검증 통과(하위호환)
  · 키 설정 → 제목에 서명 부착, 위조/미서명 피드백은 parse 단계에서 버려짐
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import feedback_token as ft  # noqa: E402
import feedback as fb  # noqa: E402

SECRET = "test-secret-abc123"


def test_no_secret_is_backward_compatible(monkeypatch):
    monkeypatch.delenv("MAIL_FEEDBACK_SECRET", raising=False)
    assert ft.enabled() is False
    assert ft.sign("O", "PBLN_1") == ""          # 서명 미부착
    assert ft.verify("O", "PBLN_1", None) is True  # 검증 안 함(통과)
    assert ft.verify("X", "PBLN_1", "deadbeefdeadbeef") is True


def test_sign_and_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    sig = ft.sign("O", "PBLN_000123")
    assert len(sig) == 16 and all(c in "0123456789abcdef" for c in sig)
    assert ft.verify("O", "PBLN_000123", sig) is True


def test_verify_rejects_forgery(monkeypatch):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    sig = ft.sign("O", "PBLN_000123")
    assert ft.verify("X", "PBLN_000123", sig) is False   # verdict 바꿔치기
    assert ft.verify("O", "PBLN_999999", sig) is False   # id 바꿔치기
    assert ft.verify("O", "PBLN_000123", None) is False  # 미서명
    assert ft.verify("O", "PBLN_000123", "0" * 16) is False  # 임의 서명


def test_secret_change_invalidates(monkeypatch):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    sig = ft.sign("O", "PBLN_1")
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", "different-secret")
    assert ft.verify("O", "PBLN_1", sig) is False


# ── feedback.py 통합 ──
def test_mailto_includes_signature_when_enabled(monkeypatch):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    url = fb.feedback_mailto("me@x.com", "X", "PBLN_42")
    from urllib.parse import unquote
    subj = unquote(url)
    assert "[MAIL-FB] X PBLN_42 " in subj
    sig = subj.split("PBLN_42 ", 1)[1].strip()
    assert ft.verify("X", "PBLN_42", sig)


def test_parse_accepts_valid_and_rejects_forged(monkeypatch):
    monkeypatch.setenv("MAIL_FEEDBACK_SECRET", SECRET)
    sig = ft.sign("O", "PBLN_7")
    assert fb.parse_feedback_subject(f"[MAIL-FB] O PBLN_7 {sig}") == {"verdict": "O", "id": "PBLN_7"}
    # 위조: 서명 없음 → 거부
    assert fb.parse_feedback_subject("[MAIL-FB] O PBLN_7") is None
    # 위조: 틀린 서명 → 거부
    assert fb.parse_feedback_subject("[MAIL-FB] O PBLN_7 " + "0" * 16) is None
    # 위조: 다른 id 를 유효 서명에 갖다붙임 → 거부
    assert fb.parse_feedback_subject(f"[MAIL-FB] O PBLN_OTHER {sig}") is None


def test_parse_unsigned_ok_without_secret(monkeypatch):
    monkeypatch.delenv("MAIL_FEEDBACK_SECRET", raising=False)
    assert fb.parse_feedback_subject("[MAIL-FB] X PBLN_9") == {"verdict": "X", "id": "PBLN_9"}
