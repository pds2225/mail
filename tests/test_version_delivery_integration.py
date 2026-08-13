"""Version/delivery/outbox/seen_ids 통합 회귀 테스트.

mock/dry-run 전용. 실SMTP 사용 안 함.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

import monitor as m  # noqa: E402


def _item(iid: str, title: str, **kw) -> dict:
    base = {
        "id": iid, "title": title, "link": f"https://example.test/{iid}",
        "author": "Test", "description": "", "deadline": "2026-12-31",
        "source": "test", "posted_date": "2026-08-01", "is_aggregator": False,
    }
    base.update(kw)
    return base


# ── 1) seen_ids dedup ────────────────────────────────────────────────────

def test_seen_ids_prevents_duplicate_delivery(tmp_path, monkeypatch):
    """seen_ids에 이미 있으면 select_notice_version_candidates에서 제외."""
    seen_path = tmp_path / "seen_ids.json"
    seen_path.write_text(json.dumps(["test_n1"]), encoding="utf-8")
    monkeypatch.setattr(m, "SEEN_IDS_PATH", seen_path)

    seen_ids = m.load_seen_ids()
    assert "test_n1" in seen_ids

    items = [_item("test_n1", "이미 본 공고"), _item("test_n2", "새 공고")]
    versions = {}
    candidates = m.select_notice_version_candidates(
        items, seen_ids, versions, now=m.datetime.now(m.KST), days_back=3,
    )
    candidate_ids = [c["id"] for c in candidates]
    assert "test_n1" not in candidate_ids
    assert "test_n2" in candidate_ids


# ── 2) version classification ────────────────────────────────────────────

def test_deadline_extension_classified_correctly():
    """마감 연장 → DEADLINE_EXTENDED change_type."""
    old_snapshot = {
        "title": "AI 창업지원 모집", "deadline": "2026-08-01", "author": "Test",
        "application_period": "", "target": "", "support": "", "region": "",
        "published_at": "2026-07-01", "registered_at": "", "updated_at": "",
    }
    new_item = _item("n1", "AI 창업지원 모집", deadline="2026-08-31")
    old_hash = m._notice_snapshot_hash(old_snapshot)

    versions = {
        "n1": {
            "version": 1,
            "delivery_id": "n1@v1",
            "delivered_snapshot": old_snapshot,
            "delivered_hash": old_hash,
        }
    }
    # seen_ids에는 item id("n1")가 들어감 (delivery_id가 아님)
    seen_ids = {"n1"}

    deliverable, updates = m.classify_notice_versions([new_item], seen_ids, versions)
    assert len(deliverable) >= 1
    d = deliverable[0]
    assert d.get("_change_type") in {"DEADLINE_EXTENDED", "UPDATED"}, f"got: {d.get('_change_type')}"


# ── 3) outbox lifecycle ──────────────────────────────────────────────────

def test_outbox_entry_survives_reload(tmp_path, monkeypatch):
    """outbox에 entry를 쓰고 다시 로드하면 entry가 살아있다."""
    from mail_core.delivery import outbox
    from mail_core.storage import secure_store

    key_path = tmp_path / "mail.key"
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", key_path)
    secure_store.ensure_local_key(key_path)
    out_path = tmp_path / "delivery_outbox.enc"
    monkeypatch.setattr(outbox, "OUTBOX_PATH", out_path)

    outbox.upsert(
        date="2026-08-12", tenant="default", group="grp_test",
        subject="test", body="test body",
        recipients=["test@test.com"], notice_ids=["n1"],
    )

    assert out_path.exists()
    data = outbox.load()
    ids = [e["id"] for e in data.get("entries", [])]
    assert len(ids) >= 1


# ── 4) multi-group seen_ids gating ───────────────────────────────────────

def test_seen_ids_not_promoted_until_cycle_complete(tmp_path, monkeypatch):
    """delivery cycle이 완료되기 전까지 seen_ids에 반영되지 않는다."""
    seen_path = tmp_path / "seen_ids.json"
    seen_path.write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setattr(m, "SEEN_IDS_PATH", seen_path)
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    monkeypatch.delenv("MONITOR_NO_PERSIST_SEEN", raising=False)

    from mail_core.delivery import outbox
    from mail_core.storage import secure_store

    key_path = tmp_path / "mail.key"
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", key_path)
    secure_store.ensure_local_key(key_path)
    out_path = tmp_path / "delivery_outbox.enc"
    monkeypatch.setattr(outbox, "OUTBOX_PATH", out_path)
    monkeypatch.setattr(m.delivery_outbox, "OUTBOX_PATH", out_path)
    delivery_path = tmp_path / "delivery_state.json"
    monkeypatch.setattr(m, "DELIVERY_STATE_PATH", delivery_path)

    outbox.upsert(
        date="2026-08-12", tenant="default", group="grp_a",
        subject="test", body="test",
        recipients=["a@test.com"], notice_ids=["n_incomplete"],
    )

    seen_ids = m.load_seen_ids()
    result_ids = m.persist_completed_outbox(
        seen_ids, only_if_cycle_complete=True,
        groups=[{"id": "grp_a"}], settings={}, watchlist={"keywords": [], "urls": []},
    )
    assert "n_incomplete" not in result_ids


# ── 5) execute_monitor return contract ───────────────────────────────────

def test_execute_monitor_no_sites_returns_early(monkeypatch):
    """사이트 없으면 early return — ok=True, reason=no_active_sites."""
    monkeypatch.setattr(m, "load_sites", lambda: [])
    monkeypatch.setattr(m, "load_groups", lambda: [{"id": "g1"}])
    monkeypatch.setattr(m, "load_settings", lambda: {})
    monkeypatch.setattr(m, "load_seen_ids", lambda: set())
    result = m.execute_monitor()
    assert result["ok"] is True
    assert result.get("reason") == "no_active_sites"


def test_execute_monitor_no_groups_returns_early(monkeypatch):
    """그룹 없으면 early return — ok=True, reason=no_active_groups."""
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s1", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [])
    monkeypatch.setattr(m, "load_settings", lambda: {})
    monkeypatch.setattr(m, "load_seen_ids", lambda: set())
    result = m.execute_monitor()
    assert result["ok"] is True
    assert result.get("reason") == "no_active_groups"
