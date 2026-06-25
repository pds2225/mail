"""dry-run·커버리지·수신자 검증 테스트 (네트워크/SMTP 없음)."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

from monitor import (  # noqa: E402
    KST,
    SEEN_IDS_PATH,
    assess_date_unknown_risk,
    build_date_review_queue,
    dedup_items,
    execute_monitor,
    partition_posted_dates,
    previous_business_day,
    run_dry_run,
    save_seen_ids,
    send_to_list,
    stable_id,
    validate_recipients,
    write_review_queue_report,
)

def _item(iid, title, posted="", link="https://example.com/1"):
    return {
        "id": iid,
        "title": title,
        "link": link,
        "author": "기관",
        "description": "전국 중소기업 대상 신청접수",
        "deadline": "2099-12-31",
        "source": "테스트",
        "posted_date": posted,
        "is_aggregator": False,
    }


def test_partition_posted_dates_splits_unknown_and_excluded():
    target = previous_business_day(days_back=1)
    items = [
        _item("a", "오늘", target.strftime("%Y-%m-%d")),
        _item("b", "어제", "2020-01-01"),
        _item("c", "불명", ""),
    ]
    matched, unknown, excluded = partition_posted_dates(items, days_back=1)
    assert len(matched) == 1 and matched[0]["id"] == "a"
    assert len(unknown) == 1 and unknown[0]["id"] == "c"
    assert len(excluded) == 1 and excluded[0]["id"] == "b"


def test_date_unknown_goes_to_review_queue():
    unknown = [_item("u1", "수출바우처 모집", "", "https://www.exportvoucher.com/x")]
    queue = build_date_review_queue(unknown)
    assert len(queue) == 1
    assert queue[0]["review_reason"] == "posted_date_missing_or_unparsed"
    assert queue[0]["date_unknown_risk"] in ("낮음", "중간", "높음")


def test_validate_recipients_dedupes_and_rejects():
    result = validate_recipients([
        "Valid.User@Example.com",
        "valid.user@example.com",
        "not-an-email",
        "",
    ])
    assert result["valid"] == ["Valid.User@Example.com"]
    assert result["rejected"] == ["not-an-email"]
    assert "@" in result["masked"][0] and "not-an-email" in result["rejected"]


def test_send_to_list_skips_smtp_when_allow_send_false():
    with patch("monitor.send_email") as mock_send:
        import monitor
        monitor._ALLOW_SMTP_SEND = False
        send_to_list("subj", "body", ["test@example.com"])
        mock_send.assert_not_called()


def test_send_to_list_only_to_overrides_all_recipients(monkeypatch):
    import monitor

    sent_to = []
    monkeypatch.setattr(monitor, "_ALLOW_SMTP_SEND", True)
    monkeypatch.setattr(monitor, "_ONLY_TO", "safe@example.com")
    monkeypatch.setattr(
        monitor,
        "send_email",
        lambda subject, body, to: sent_to.append(to),
    )

    send_to_list(
        "subj",
        "body",
        ["original-1@example.com", "original-2@example.com"],
    )

    assert sent_to == ["safe@example.com"]


def test_send_email_only_to_overrides_envelope_and_header(monkeypatch):
    import monitor

    sent_messages = []

    class FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, address, password):
            self.login_args = (address, password)

        def sendmail(self, from_addr, to_addrs, message):
            sent_messages.append((from_addr, to_addrs, message))

    monkeypatch.setattr(monitor, "_ALLOW_SMTP_SEND", True)
    monkeypatch.setattr(monitor, "_ONLY_TO", "safe@example.com")
    monkeypatch.setattr(monitor.smtplib, "SMTP_SSL", lambda host, port: FakeSMTP())

    monitor.send_email("subj", "body", "original@example.com")

    assert len(sent_messages) == 1
    _, envelope_to, message = sent_messages[0]
    assert envelope_to == "safe@example.com"
    assert "To: safe@example.com" in message
    assert "original@example.com" not in message


def test_send_email_skips_smtp_when_allow_send_false(monkeypatch):
    """_ALLOW_SMTP_SEND=False면 send_email() 직접 호출도 SMTP_SSL을 절대 열지 않는다."""
    import monitor

    smtp_calls = []
    monkeypatch.setattr(monitor, "_ALLOW_SMTP_SEND", False)
    monkeypatch.setattr(
        monitor.smtplib,
        "SMTP_SSL",
        lambda *args, **kwargs: smtp_calls.append((args, kwargs)),
    )

    monitor.send_email("subj", "body", "original@example.com")

    assert smtp_calls == []


def test_save_seen_ids_skipped_when_persist_disabled():
    import monitor
    monitor._ALLOW_PERSIST_SEEN = False
    before = SEEN_IDS_PATH.read_text(encoding="utf-8") if SEEN_IDS_PATH.exists() else None
    save_seen_ids({"test_id_should_not_persist"})
    after = SEEN_IDS_PATH.read_text(encoding="utf-8") if SEEN_IDS_PATH.exists() else None
    assert before == after


def test_dedup_does_not_merge_clearly_different_titles():
    a = _item("id_a", "2026년 인천 화장품 수출바우처 지원사업 모집")
    b = _item("id_b", "2026년 부산 로봇 해외전시회 참가지원")
    out = dedup_items([a, b])
    assert len(out) == 2


def test_stable_id_changes_when_link_changes():
    t = "동일 제목 공고"
    assert stable_id(t + "https://a.example/1") != stable_id(t + "https://b.example/2")


def test_execute_monitor_dry_run_flags(monkeypatch):
    monkeypatch.setattr(
        "monitor.fetch_all",
        lambda sites: [_item("n1", "테스트", previous_business_day(days_back=1).strftime("%Y-%m-%d"))],
    )
    monkeypatch.setattr("monitor.enrich_items", lambda items: items)
    result = execute_monitor(allow_send=False, persist_seen=False)
    assert result["mail_sent"] is False
    assert result["seen_ids_persisted"] is False


def test_run_dry_run_writes_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("monitor.BASE_DIR", tmp_path)
    monkeypatch.setattr("monitor.SEEN_IDS_PATH", tmp_path / "seen_ids.json")
    monkeypatch.setattr("monitor.fetch_site_coverage", lambda sites=None, **kw: [])
    monkeypatch.setattr(
        "monitor.execute_monitor",
        lambda **kw: {
            "collected": 1,
            "date_matched_count": 0,
            "date_review_queue_count": 1,
            "date_review_queue": build_date_review_queue([_item("x", "모집", "")]),
            "date_excluded_count": 0,
            "mail_sent": False,
            "seen_ids_persisted": False,
        },
    )
    monkeypatch.setattr("monitor.load_groups", lambda: [])
    monkeypatch.setattr("monitor.load_settings", lambda: {"raw_all_recipients": []})
    summary = run_dry_run(fetch_coverage=False)
    assert (tmp_path / "logs" / "today_notice_missing_risk_report.md").exists()
    assert summary["mail_sent"] is False


def test_write_review_queue_report(tmp_path):
    q = build_date_review_queue([_item("r1", "신규 가능 모집공고", "")])
    path = write_review_queue_report(q, tmp_path / "logs" / "review_queue_20260528.md")
    assert path.exists()
    assert "Review queue" in path.read_text(encoding="utf-8")
