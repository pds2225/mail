"""Encrypted recipient-level outbox for retrying partial announcement delivery."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mail_core.paths import OUTBOX_DIR
from mail_core.storage.secure_store import (
    SecureStoreUnavailable,
    get_fernet,
    load_encrypted_json,
    save_encrypted_json,
)


OUTBOX_PATH = OUTBOX_DIR / "delivery_outbox.enc"


def is_ready() -> bool:
    return get_fernet(create_local_key=False) is not None


def _outbox_path(path: str | Path | None) -> Path:
    """Resolve outbox path at call time so tests can monkeypatch OUTBOX_PATH."""
    return Path(path) if path is not None else Path(OUTBOX_PATH)


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"version": 1, "entries": []}
    entries = [dict(entry) for entry in value.get("entries", []) if isinstance(entry, dict)]
    return {"version": 1, "entries": entries}


def load(path: str | Path | None = None) -> dict[str, Any]:
    """Load outbox payload.

    Missing file → empty outbox. Existing ciphertext that will not decrypt with the
    active key raises SecureStoreDecryptError so callers cannot silently wipe retries.
    """
    return _payload(load_encrypted_json(_outbox_path(path), {"version": 1, "entries": []}))


def save(value: dict[str, Any], path: str | Path | None = None) -> None:
    if not is_ready():
        raise SecureStoreUnavailable("encrypted outbox requires MAIL_PRIVATE_CONFIG_KEY or local key")
    # Refuse to overwrite undecryptable ciphertext with a fresh empty/new payload.
    target = _outbox_path(path)
    if target.exists() and target.stat().st_size > 0:
        load(target)
    save_encrypted_json(target, _payload(value), create_local_key=False)


def entry_id(
    *,
    date: str,
    tenant: str,
    group: str,
    subject: str,
    body: str,
) -> str:
    raw = "\x1f".join((date, tenant, group, subject, body)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def upsert(
    *,
    date: str,
    tenant: str,
    group: str,
    subject: str,
    body: str,
    recipients: list[str],
    notice_ids: list[str],
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist a delivery before SMTP so a partial run can be retried safely."""
    target = _outbox_path(path)
    oid = entry_id(date=date, tenant=tenant, group=group, subject=subject, body=body)
    payload = load(target)
    for entry in payload["entries"]:
        if entry.get("id") == oid:
            pending = {str(x).strip().lower() for x in entry.get("recipients", [])}
            pending.update(str(x).strip().lower() for x in recipients if str(x).strip())
            entry["recipients"] = sorted(pending)
            entry["notice_ids"] = sorted({*entry.get("notice_ids", []), *notice_ids})
            save(payload, target)
            return dict(entry)
    entry = {
        "id": oid,
        "date": str(date),
        "tenant": str(tenant),
        "group": str(group),
        "subject": str(subject),
        "body": str(body),
        "recipients": sorted({str(x).strip().lower() for x in recipients if str(x).strip()}),
        "notice_ids": sorted({str(x) for x in notice_ids if str(x)}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["entries"].append(entry)
    save(payload, target)
    return dict(entry)


def settle(
    outbox_id: str,
    delivered_recipients: set[str],
    *,
    path: str | Path | None = None,
) -> tuple[bool, list[str]]:
    """Record recipient completion and return ``(complete, notice_ids)``.

    Fully delivered entries intentionally remain until ``acknowledge_completed`` runs after
    ``seen_ids`` has been committed. A crash in that narrow interval therefore retries only
    the state commit, never SMTP, which closes the #115 crash window.
    """
    target = _outbox_path(path)
    delivered = {str(x).strip().lower() for x in delivered_recipients}
    payload = load(target)
    complete = False
    notice_ids: list[str] = []
    for entry in payload["entries"]:
        if entry.get("id") != outbox_id:
            continue
        pending = [email for email in entry.get("recipients", []) if email.lower() not in delivered]
        if pending:
            entry["recipients"] = pending
        else:
            complete = True
            notice_ids = [str(x) for x in entry.get("notice_ids", []) if str(x)]
            entry["recipients"] = []
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
    save(payload, target)
    return complete, notice_ids


def pending(path: str | Path | None = None) -> list[dict[str, Any]]:
    return [dict(entry) for entry in load(path).get("entries", []) if not entry.get("completed_at")]


def completed(path: str | Path | None = None) -> list[dict[str, Any]]:
    return [dict(entry) for entry in load(path).get("entries", []) if entry.get("completed_at")]


def acknowledge_completed(ids: set[str], path: str | Path | None = None) -> None:
    """Delete only fully persisted completion records after their notice IDs reached seen_ids."""
    target = _outbox_path(path)
    payload = load(target)
    payload["entries"] = [
        entry for entry in payload["entries"]
        if not (entry.get("completed_at") and str(entry.get("id")) in ids)
    ]
    save(payload, target)
