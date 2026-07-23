"""Encrypted recipient-level outbox for retrying partial announcement delivery."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secure_store import BASE_DIR, SecureStoreUnavailable, get_fernet, load_encrypted_json, save_encrypted_json


OUTBOX_PATH = BASE_DIR / "delivery_outbox.enc"


def is_ready() -> bool:
    return get_fernet(create_local_key=False) is not None


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"version": 1, "entries": []}
    entries = [dict(entry) for entry in value.get("entries", []) if isinstance(entry, dict)]
    return {"version": 1, "entries": entries}


def load(path: str | Path = OUTBOX_PATH) -> dict[str, Any]:
    return _payload(load_encrypted_json(path, {"version": 1, "entries": []}))


def save(value: dict[str, Any], path: str | Path = OUTBOX_PATH) -> None:
    if not is_ready():
        raise SecureStoreUnavailable("encrypted outbox requires MAIL_PRIVATE_CONFIG_KEY or local key")
    save_encrypted_json(path, _payload(value), create_local_key=False)


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
    path: str | Path = OUTBOX_PATH,
) -> dict[str, Any]:
    """Persist a delivery before SMTP so a partial run can be retried safely."""
    oid = entry_id(date=date, tenant=tenant, group=group, subject=subject, body=body)
    payload = load(path)
    for entry in payload["entries"]:
        if entry.get("id") == oid:
            pending = {str(x).strip().lower() for x in entry.get("recipients", [])}
            pending.update(str(x).strip().lower() for x in recipients if str(x).strip())
            entry["recipients"] = sorted(pending)
            entry["notice_ids"] = sorted({*entry.get("notice_ids", []), *notice_ids})
            save(payload, path)
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
    save(payload, path)
    return dict(entry)


def settle(
    outbox_id: str,
    delivered_recipients: set[str],
    *,
    path: str | Path = OUTBOX_PATH,
) -> tuple[bool, list[str]]:
    """Record recipient completion and return ``(complete, notice_ids)``.

    Fully delivered entries intentionally remain until ``acknowledge_completed`` runs after
    ``seen_ids`` has been committed. A crash in that narrow interval therefore retries only
    the state commit, never SMTP, which closes the #115 crash window.
    """
    delivered = {str(x).strip().lower() for x in delivered_recipients}
    payload = load(path)
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
    save(payload, path)
    return complete, notice_ids


def pending(path: str | Path = OUTBOX_PATH) -> list[dict[str, Any]]:
    return [dict(entry) for entry in load(path).get("entries", []) if not entry.get("completed_at")]


def completed(path: str | Path = OUTBOX_PATH) -> list[dict[str, Any]]:
    return [dict(entry) for entry in load(path).get("entries", []) if entry.get("completed_at")]


def acknowledge_completed(ids: set[str], path: str | Path = OUTBOX_PATH) -> None:
    """Delete only fully persisted completion records after their notice IDs reached seen_ids."""
    payload = load(path)
    payload["entries"] = [
        entry for entry in payload["entries"]
        if not (entry.get("completed_at") and str(entry.get("id")) in ids)
    ]
    save(payload, path)
