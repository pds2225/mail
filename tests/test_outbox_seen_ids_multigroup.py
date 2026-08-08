"""Regression: partial multi-group outbox must not poison shared seen_ids.

Concrete trigger:
  1. Group A finishes SMTP + outbox settle for shared notice n1.
  2. Process dies before group B's deliver_with_outbox runs (no B outbox row).
  3. Next run's start-of-run persist_completed_outbox used to union A's notice_ids
     into global seen_ids → classify_notice_versions drops n1 as seed_only →
     group B permanently misses the notice.

Fix: start-of-run promotion is gated on full delivery-cycle checkpoint.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mail_core.delivery import outbox  # noqa: E402
from mail_core.delivery import state as delivery_state  # noqa: E402
from mail_core.storage import secure_store  # noqa: E402
import monitor as m  # noqa: E402


def _groups_two_overlap() -> list[dict]:
    return [
        {
            "id": "grp_a",
            "name": "A",
            "active": True,
            "tenant_id": "default",
            "recipients": ["a@example.test"],
        },
        {
            "id": "grp_b",
            "name": "B",
            "active": True,
            "tenant_id": "default",
            "recipients": ["b@example.test"],
        },
    ]


@pytest.fixture()
def outbox_env(tmp_path, monkeypatch):
    key_path = tmp_path / "mail.key"
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", key_path)
    secure_store.ensure_local_key(key_path)
    path = tmp_path / "delivery_outbox.enc"
    monkeypatch.setattr(outbox, "OUTBOX_PATH", path)
    monkeypatch.setattr(m.delivery_outbox, "OUTBOX_PATH", path)
    delivery_path = tmp_path / "delivery_state.json"
    monkeypatch.setattr(m, "DELIVERY_STATE_PATH", delivery_path)
    seen_path = tmp_path / "seen_ids.json"
    monkeypatch.setattr(m, "SEEN_IDS_PATH", seen_path)
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    monkeypatch.delenv("MONITOR_NO_PERSIST_SEEN", raising=False)
    return {
        "outbox": path,
        "delivery": delivery_path,
        "seen": seen_path,
        "groups": _groups_two_overlap(),
        "settings": {"tenant_id": "default"},
        "watchlist": {"keywords": [], "urls": []},
    }


def test_start_of_run_persist_does_not_poison_shared_seen_ids(outbox_env):
    """Group A completed + cycle incomplete → n1 must stay out of seen_ids."""
    date = "2026-08-03#am"
    entry = outbox.upsert(
        date=date,
        tenant="default",
        group="grp_a",
        subject="[A] 1건",
        body="body-a",
        recipients=["a@example.test"],
        notice_ids=["n1", "n2"],
    )
    complete, ids = outbox.settle(entry["id"], {"a@example.test"})
    assert complete is True and set(ids) == {"n1", "n2"}

    # Only group A recipient checkpointed — group B still owed mail for n1.
    delivery_state.mark(
        outbox_env["delivery"],
        delivery_state.key(date, "grp_a", "a@example.test"),
    )

    seen = m.persist_completed_outbox(
        set(),
        only_if_cycle_complete=True,
        groups=outbox_env["groups"],
        settings=outbox_env["settings"],
        watchlist=outbox_env["watchlist"],
    )
    assert seen == set()
    assert "n1" not in m.load_seen_ids()
    # Completed outbox row kept for a later safe flush.
    assert len(outbox.completed()) == 1

    # Unconditional end-of-run persist (all groups finished in-process) still works.
    seen = m.persist_completed_outbox(set())
    assert seen == {"n1", "n2"}
    assert outbox.completed() == []


def test_start_of_run_persist_promotes_when_cycle_complete(outbox_env):
    date = "2026-08-03#pm"
    entry_a = outbox.upsert(
        date=date,
        tenant="default",
        group="grp_a",
        subject="[A] 1건",
        body="body-a",
        recipients=["a@example.test"],
        notice_ids=["n1"],
    )
    entry_b = outbox.upsert(
        date=date,
        tenant="default",
        group="grp_b",
        subject="[B] 1건",
        body="body-b",
        recipients=["b@example.test"],
        notice_ids=["n1", "n3"],
    )
    outbox.settle(entry_a["id"], {"a@example.test"})
    outbox.settle(entry_b["id"], {"b@example.test"})
    delivery_state.mark(
        outbox_env["delivery"],
        delivery_state.key(date, "grp_a", "a@example.test"),
    )
    delivery_state.mark(
        outbox_env["delivery"],
        delivery_state.key(date, "grp_b", "b@example.test"),
    )

    seen = m.persist_completed_outbox(
        set(),
        only_if_cycle_complete=True,
        groups=outbox_env["groups"],
        settings=outbox_env["settings"],
        watchlist=outbox_env["watchlist"],
    )
    assert seen == {"n1", "n3"}
    assert outbox.completed() == []


def test_partial_group_a_complete_keeps_n1_deliverable_for_group_b(outbox_env):
    """End-to-end classify: after gated persist, n1 remains NEW for group B."""
    date = "2026-08-03#am"
    entry = outbox.upsert(
        date=date,
        tenant="default",
        group="grp_a",
        subject="[A] 1건",
        body="body-a",
        recipients=["a@example.test"],
        notice_ids=["n1"],
    )
    outbox.settle(entry["id"], {"a@example.test"})
    delivery_state.mark(
        outbox_env["delivery"],
        delivery_state.key(date, "grp_a", "a@example.test"),
    )

    seen = m.persist_completed_outbox(
        set(),
        only_if_cycle_complete=True,
        groups=outbox_env["groups"],
        settings=outbox_env["settings"],
        watchlist=outbox_env["watchlist"],
    )
    item = {
        "id": "n1",
        "title": "AI 지원사업",
        "url": "https://example.test/n1",
        "posted_date": "2026-08-01",
        "deadline": "2026-08-20",
        "application_period": {"display": "2026-08-20"},
    }
    deliverable, _updates = m.classify_notice_versions([item], seen, {})
    assert len(deliverable) == 1
    assert deliverable[0]["_change_type"] == "NEW"
    assert deliverable[0]["id"] == "n1"
