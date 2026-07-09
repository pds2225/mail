"""초안(Gmail Drafts) 모드 스모크 테스트 — 오프라인·결정적, 네트워크/SMTP 없음.

목적 고정: `--draft` 전달 경로(_DRAFT_MODE=True)가 공고 digest 를 실제로 '발송'하지 않고
Gmail Drafts 특수폴더에 IMAP APPEND(=초안)만 한다.

증명 2가지:
  1) 초안 경로가 IMAP `append` 를 Drafts 폴더에 정확히 1회 호출한다(초안 생성됨).
  2) 실제 발송(smtplib.SMTP_SSL)은 0회다("실발송 0" 근거).

실네트워크/실계정 접속 0: imaplib.IMAP4_SSL·smtplib.SMTP_SSL 을 monkeypatch 로 가짜 주입.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import monitor  # noqa: E402


class _FakeIMAP:
    """imaplib.IMAP4_SSL 대체 — 실접속 없이 append 호출만 기록."""

    appends: list[tuple] = []
    logged_in = False

    def __init__(self, host=None, port=None):
        self.host, self.port = host, port

    def login(self, user, pw):
        type(self).logged_in = True
        return ("OK", [b"authenticated"])

    def list(self, directory='""', pattern="*"):
        # 한국어 계정에서도 \Drafts 플래그로 폴더를 찾는 경로를 대표.
        return ("OK", [b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"'])

    def append(self, folder, flags, date, message):
        type(self).appends.append((folder, flags, date, message))
        return ("OK", [b"[APPENDUID 1 1] (Success)"])

    def logout(self):
        return ("BYE", [b"logout"])


class _FakeSMTP:
    """smtplib.SMTP_SSL 대체 — 인스턴스화(=실발송 시도)되면 즉시 실패시켜 사고를 드러낸다."""

    instantiated = 0

    def __init__(self, *a, **k):
        type(self).instantiated += 1
        raise AssertionError("초안 모드인데 SMTP_SSL 이 호출됨 — 실발송 사고")


def test_draft_mode_appends_to_drafts_and_no_smtp_send(monkeypatch):
    _FakeIMAP.appends = []
    _FakeIMAP.logged_in = False
    _FakeSMTP.instantiated = 0

    monkeypatch.setattr(monitor.imaplib, "IMAP4_SSL", _FakeIMAP)
    monkeypatch.setattr(monitor.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(monitor, "GMAIL_ADDRESS", "test@test.com")
    monkeypatch.setattr(monitor, "GMAIL_APP_PASSWORD", "test_pass")
    monkeypatch.setattr(monitor, "_ONLY_TO", "")
    monkeypatch.setattr(monitor, "_DRAFT_MODE", True)
    monkeypatch.setattr(monitor, "_DRAFT_OK", 0)
    monkeypatch.setattr(monitor, "_DRAFT_FAIL", 0)

    # 발송 공용 진입점 send_to_list 가 초안 모드에서 draft_to_list 로 우회하는지 검증.
    monitor.send_to_list(
        "[테스트그룹] 공고 digest (2026-07-09)",
        "오늘 매칭된 공고 목록...\n- 예시 공고 A\n- 예시 공고 B\n",
        ["someone@example.com"],
    )

    # 1) 초안이 Drafts 폴더에 정확히 1회 생성됐다.
    assert len(_FakeIMAP.appends) == 1, f"append 호출 {len(_FakeIMAP.appends)}회 (기대 1)"
    folder, flags, _date, message = _FakeIMAP.appends[0]
    assert "Drafts" in folder, f"초안 폴더가 Drafts 계열이 아님: {folder!r}"
    assert flags == r"(\Draft)", f"초안 플래그 아님: {flags!r}"
    assert isinstance(message, (bytes, bytearray)) and b"someone@example.com" in message
    assert _FakeIMAP.logged_in is True

    # 2) 실제 발송(SMTP)은 0회 — "실발송 0" 근거.
    assert _FakeSMTP.instantiated == 0
    assert monitor._DRAFT_OK == 1 and monitor._DRAFT_FAIL == 0
