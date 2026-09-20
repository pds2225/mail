"""MAIL-014 P0 risk evidence regressions.

No network calls and no real email are performed.
"""
from __future__ import annotations

import os

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

import monitor as m


def test_fetch_all_isolates_one_source_failure(monkeypatch):
    def good(site):
        return [{"id": "ok-1", "title": "정상 공고", "source": site["id"], "is_aggregator": False}]

    def bad(_site):
        raise RuntimeError("source boom")

    monkeypatch.setitem(m.FETCHERS, "risk-good", good)
    monkeypatch.setitem(m.FETCHERS, "risk-bad", bad)

    outcomes = {}
    got = m.fetch_all(
        [
            {"id": "good", "name": "good", "type": "risk-good"},
            {"id": "bad", "name": "bad", "type": "risk-bad"},
        ],
        max_workers=2,
        outcomes=outcomes,
    )

    assert [row["id"] for row in got] == ["ok-1"]
    assert outcomes["good"]["success"] is True
    assert outcomes["bad"]["success"] is False
    assert "source boom" in outcomes["bad"]["error"]


def test_send_to_list_builds_one_recipient_per_message(monkeypatch):
    messages = []
    monkeypatch.setattr(m, "_ALLOW_SMTP_SEND", True)
    monkeypatch.setattr(m, "_DRAFT_MODE", False)
    monkeypatch.setattr(m, "_ONLY_TO", "")

    def fake_send(subject, body, to):
        messages.append(m._build_mime_message(subject, body, to))

    monkeypatch.setattr(m, "send_email", fake_send)
    recipients = ["first@example.test", "second@example.test"]
    delivered = m.send_to_list("subject", "body", recipients)

    assert delivered == set(recipients)
    assert [msg["To"] for msg in messages] == recipients
    assert all(msg.get("Cc") is None for msg in messages)
    assert all("," not in str(msg["To"]) for msg in messages)
