"""커버리지 이상탐지 알림을 폰(ntfy)→PC(이메일)로 전환한 것 회귀 테스트.

핵심:
- alert_email 은 announcement 발송 게이트(_ALLOW_SMTP_SEND)와 무관하게 발송(dry-run 스케줄에서도
  헬스 알림은 나가야 함).
- run_coverage_anomaly_check 는 high 이상 시 alert_email(PC) 을 호출하고 alert_ntfy(폰) 은 안 부른다.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "me@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monitor as m  # noqa: E402
import coverage_alert as ca  # noqa: E402


class _FakeSMTP:
    last = {}

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def sendmail(self, frm, to, body):
        _FakeSMTP.last = {"frm": frm, "to": to, "len": len(body)}


def test_alert_email_sends_even_in_dry_run(monkeypatch):
    """dry-run(_ALLOW_SMTP_SEND=False)에도 헬스 알림 이메일은 발송된다."""
    monkeypatch.setattr(m.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(m, "_ALLOW_SMTP_SEND", False)
    _FakeSMTP.last = {}
    m.alert_email("테스트 알림", "평소 10 → 오늘 0건")
    assert _FakeSMTP.last.get("to") == m.GMAIL_ADDRESS   # 수신=자기 자신
    assert _FakeSMTP.last.get("len", 0) > 0


def test_alert_email_graceful_without_credentials(monkeypatch):
    monkeypatch.setattr(m, "GMAIL_ADDRESS", "")
    # 자격 없으면 조용히 생략(예외 없음)
    m.alert_email("x", "y")


def test_coverage_anomaly_alerts_pc_not_phone(monkeypatch):
    """평소 10건이 오늘 0건 → alert_email(PC) 호출, alert_ntfy(폰) 미호출."""
    calls = {"email": 0, "ntfy": 0}
    monkeypatch.setattr(m, "alert_email", lambda *a, **k: calls.__setitem__("email", calls["email"] + 1))
    monkeypatch.setattr(m, "alert_ntfy", lambda *a, **k: calls.__setitem__("ntfy", calls["ntfy"] + 1))
    base = {}
    row_ok = {"site_id": "a", "site_name": "A", "item_count": 10, "fetch_success": True, "enabled": True}
    for _ in range(3):
        base = ca.update_coverage_baseline(base, [row_ok])
    monkeypatch.setattr(ca, "load_coverage_baseline", lambda *a, **k: base)
    monkeypatch.setattr(ca, "save_coverage_baseline", lambda *a, **k: None)

    row_zero = {"site_id": "a", "site_name": "A", "item_count": 0, "fetch_success": True, "enabled": True}
    m.run_coverage_anomaly_check([row_zero], allow_alert=True)
    assert calls["email"] == 1
    assert calls["ntfy"] == 0


def test_coverage_no_alert_when_disabled(monkeypatch):
    calls = {"email": 0}
    monkeypatch.setattr(m, "alert_email", lambda *a, **k: calls.__setitem__("email", calls["email"] + 1))
    base = {}
    row_ok = {"site_id": "a", "site_name": "A", "item_count": 10, "fetch_success": True, "enabled": True}
    for _ in range(3):
        base = ca.update_coverage_baseline(base, [row_ok])
    monkeypatch.setattr(ca, "load_coverage_baseline", lambda *a, **k: base)
    monkeypatch.setattr(ca, "save_coverage_baseline", lambda *a, **k: None)
    m.run_coverage_anomaly_check(
        [{"site_id": "a", "site_name": "A", "item_count": 0, "fetch_success": True, "enabled": True}],
        allow_alert=False)
    assert calls["email"] == 0  # allow_alert=False 면 알림 안 함
