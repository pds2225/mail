"""P0 regression gates for confidential config, crash-safe state, and factual output."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")
os.environ.setdefault("NTFY_TOPIC", "x")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mail_core.delivery import outbox  # noqa: E402
import monitor as m  # noqa: E402
from mail_core.security import private_config as pc  # noqa: E402
from mail_core.operations import run_lock  # noqa: E402
from mail_core.storage import secure_store  # noqa: E402
from mail_core.storage import state_store  # noqa: E402


def test_private_payload_removes_plaintext_pii_and_enforces_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", tmp_path / "mail.key")
    groups = [{"id": "g-a", "tenant_id": "tenant-a", "recipients": ["a@example.test"]}]
    settings = {"tenant_id": "tenant-a", "raw_all_recipients": ["raw@example.test"]}
    watchlist = {"tenant_id": "tenant-a", "recipients": ["watch@example.test"]}
    companies = [{"id": "c-a", "tenant_id": "tenant-a", "email": "company@example.test"}]
    public_groups, public_settings, public_watchlist, public_companies, payload = pc.split_public_private(
        groups, settings, watchlist, companies,
    )
    assert "@" not in repr((public_groups, public_settings, public_watchlist, public_companies))
    db = tmp_path / "private.sqlite3"
    pc.save_private_payload(payload, db)
    loaded = pc.load_private_payload(db)
    merged = pc.merge_groups(public_groups, loaded)
    assert merged[0]["recipients"] == ["a@example.test"]
    assert pc.allowed_recipients(merged[0], ["a@example.test"], loaded) == ["a@example.test"]
    foreign = {**merged[0], "tenant_id": "tenant-b"}
    assert pc.allowed_recipients(foreign, ["a@example.test"], loaded) == []


def test_public_recipient_fields_fail_closed_without_private_payload(tmp_path, monkeypatch):
    groups_path = tmp_path / "groups.json"
    settings_path = tmp_path / "settings.json"
    groups_path.write_text('[{"id":"g","recipients":["leak@example.test"]}]', encoding="utf-8")
    settings_path.write_text('{"raw_all_recipients":["leak@example.test"]}', encoding="utf-8")
    monkeypatch.setattr(m, "GROUPS_PATH", groups_path)
    monkeypatch.setattr(m, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(m.private_config, "load_private_payload", lambda: {})
    monkeypatch.delenv("MAIL_GROUPS_JSON", raising=False)
    assert m.load_groups()[0]["recipients"] == []
    assert m.load_settings()["raw_all_recipients"] == []


def test_state_recovery_and_lock_keep_last_valid_data(tmp_path):
    path = tmp_path / "state.json"
    state_store.atomic_write_json(path, {"version": 1})
    state_store.atomic_write_json(path, {"version": 2})
    path.write_text("{broken", encoding="utf-8")
    assert state_store.load_json_with_recovery(path, {}) == {"version": 1}

    first = state_store.FileLock(path.with_name("state.json.lock"), timeout_seconds=0)
    first.acquire()
    try:
        with pytest.raises(state_store.LockBusyError):
            state_store.FileLock(path.with_name("state.json.lock"), timeout_seconds=0).acquire()
    finally:
        first.release()


def test_encrypted_outbox_retries_partial_then_waits_for_seen_ack(tmp_path, monkeypatch):
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", tmp_path / "mail.key")
    secure_store.ensure_local_key(tmp_path / "mail.key")
    path = tmp_path / "outbox.enc"
    entry = outbox.upsert(
        date="2026-07-23", tenant="t", group="g", subject="s", body="b",
        recipients=["a@example.test", "b@example.test"], notice_ids=["n1"], path=path,
    )
    assert b"a@example.test" not in path.read_bytes()
    complete, ids = outbox.settle(entry["id"], {"a@example.test"}, path=path)
    assert complete is False and ids == []
    assert outbox.pending(path)[0]["recipients"] == ["b@example.test"]
    complete, ids = outbox.settle(entry["id"], {"b@example.test"}, path=path)
    assert complete is True and ids == ["n1"]
    assert len(outbox.completed(path)) == 1
    outbox.acknowledge_completed({entry["id"]}, path=path)
    assert outbox.pending(path) == [] and outbox.completed(path) == []


def test_encrypted_outbox_recovers_last_decryptable_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", tmp_path / "mail.key")
    secure_store.ensure_local_key(tmp_path / "mail.key")
    path = tmp_path / "outbox.enc"
    outbox.save({"version": 1, "entries": [{"id": "backup", "recipients": []}]}, path)
    outbox.save({"version": 1, "entries": [{"id": "new", "recipients": []}]}, path)
    path.write_bytes(b"not-encrypted")
    assert outbox.load(path)["entries"][0]["id"] == "backup"


def test_local_run_lock_allows_only_one_active_sender(tmp_path):
    path = tmp_path / "monitor.run.lock"
    first = run_lock.MonitorRunLock(path)
    second = run_lock.MonitorRunLock(path)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_digest_never_uses_model_and_always_uses_collected_facts(monkeypatch):
    monkeypatch.setenv("MAIL_ALLOW_LLM_DIGEST", "1")
    items = [{
        "title": "지원금 500만원 공고", "author": "기관", "description": "원문 지원 내용",
        "deadline": "2026-08-01", "posted_date": "2026-07-23", "source": "테스트",
        "link": "https://example.test/notice", "_types": ["지원금/바우처"],
    }]
    body = m.claude_summarize(items, {"id": "g"})
    assert "500만원" in body and "2026-08-01" in body and "https://example.test/notice" in body


def test_unsigned_feedback_links_are_hidden(monkeypatch):
    monkeypatch.delenv("MAIL_FEEDBACK_SECRET", raising=False)
    assert m._feedback_links_enabled() is False


def test_daily_workflow_wires_encrypted_delivery_secrets_and_state():
    workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "monitor.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "MAIL_PRIVATE_CONFIG_JSON", "MAIL_PRIVATE_CONFIG_KEY", "MAIL_DELIVERY_STATE_SECRET",
        "MAIL_FEEDBACK_SECRET", "delivery_outbox.enc", "--send --persist-seen",
    ):
        assert required in workflow
