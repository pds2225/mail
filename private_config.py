"""Encrypted private configuration and tenant delivery boundaries.

Tracked JSON files contain matching rules only. Recipient addresses and company email
addresses live either in GitHub's encrypted secret ``MAIL_PRIVATE_CONFIG_JSON`` or in
an encrypted local SQLite store under the ignored ``secrets`` directory.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from secure_store import BASE_DIR, encrypt_json, decrypt_json, get_fernet


PRIVATE_DB_PATH = BASE_DIR / "secrets" / "mail_private.sqlite3"
PRIVATE_ENV = "MAIL_PRIVATE_CONFIG_JSON"
_TENANT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def normalize_tenant_id(value: Any) -> str:
    tenant = str(value or "default").strip() or "default"
    if not _TENANT_RE.fullmatch(tenant):
        raise ValueError("tenant_id must contain only letters, digits, dot, underscore, or dash")
    return tenant


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "version": int(value.get("version") or 1),
        "tenants": dict(value.get("tenants") or {}),
        "groups": dict(value.get("groups") or {}),
        "settings": dict(value.get("settings") or {}),
        "watchlist": dict(value.get("watchlist") or {}),
        "companies": dict(value.get("companies") or {}),
    }


def load_private_payload(path: str | os.PathLike[str] = PRIVATE_DB_PATH) -> dict[str, Any]:
    raw = os.environ.get(PRIVATE_ENV, "").strip()
    if raw:
        try:
            return _payload(json.loads(raw))
        except json.JSONDecodeError:
            return {}
    db_path = Path(path)
    if not db_path.exists() or get_fernet(create_local_key=False) is None:
        return {}
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT ciphertext FROM private_config WHERE namespace = ?", ("mail",)
            ).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    return _payload(decrypt_json(bytes(row[0]), {}))


def save_private_payload(
    value: dict[str, Any],
    path: str | os.PathLike[str] = PRIVATE_DB_PATH,
) -> None:
    """Store PII in a SQLite transaction whose value column is Fernet encrypted."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    token = encrypt_json(_payload(value), create_local_key=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS private_config ("
            "namespace TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO private_config(namespace, ciphertext, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(namespace) DO UPDATE SET ciphertext=excluded.ciphertext, updated_at=excluded.updated_at",
            ("mail", token, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def _clean_recipients(values: Any) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values or []:
        email = str(value or "").strip()
        key = email.lower()
        if email and key not in seen:
            seen.add(key)
            cleaned.append(email)
    return cleaned


def _company_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("companies", [])
    return [dict(v) for v in value or [] if isinstance(v, dict)]


def split_public_private(
    groups: list[dict[str, Any]],
    settings: dict[str, Any],
    watchlist: dict[str, Any],
    companies: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], Any, dict[str, Any]]:
    """Return PII-free public config plus a private payload without exposing values."""
    payload: dict[str, Any] = {
        "version": 1,
        "tenants": {},
        "groups": {},
        "settings": {},
        "watchlist": {},
        "companies": {},
    }
    public_groups: list[dict[str, Any]] = []
    for original in groups or []:
        group = copy.deepcopy(original)
        group_id = str(group.get("id") or "")
        tenant = normalize_tenant_id(group.get("tenant_id"))
        recipients = _clean_recipients(group.get("recipients"))
        group["tenant_id"] = tenant
        group["recipients"] = []
        if group_id:
            payload["groups"][group_id] = {"tenant_id": tenant, "recipients": recipients}
            payload["tenants"].setdefault(tenant, {"recipients": []})["recipients"].extend(recipients)
        public_groups.append(group)

    public_settings = copy.deepcopy(settings or {})
    raw_recipients = _clean_recipients(public_settings.get("raw_all_recipients"))
    public_settings["raw_all_recipients"] = []
    public_settings.setdefault("tenant_id", "default")
    payload["settings"] = {
        "tenant_id": normalize_tenant_id(public_settings.get("tenant_id")),
        "raw_all_recipients": raw_recipients,
    }
    payload["tenants"].setdefault(payload["settings"]["tenant_id"], {"recipients": []})["recipients"].extend(raw_recipients)

    public_watchlist = copy.deepcopy(watchlist or {})
    watch_recipients = _clean_recipients(public_watchlist.get("recipients"))
    public_watchlist["recipients"] = []
    public_watchlist.setdefault("tenant_id", "default")
    payload["watchlist"] = {
        "tenant_id": normalize_tenant_id(public_watchlist.get("tenant_id")),
        "recipients": watch_recipients,
    }
    payload["tenants"].setdefault(payload["watchlist"]["tenant_id"], {"recipients": []})["recipients"].extend(watch_recipients)

    original_companies = _company_list(companies)
    public_company_list: list[dict[str, Any]] = []
    for original in original_companies:
        company = copy.deepcopy(original)
        company_id = str(company.get("id") or "")
        tenant = normalize_tenant_id(company.get("tenant_id"))
        email = str(company.get("email") or "").strip()
        company["tenant_id"] = tenant
        company.pop("email", None)
        if company_id:
            payload["companies"][company_id] = {"tenant_id": tenant, "email": email}
        public_company_list.append(company)
    public_companies: Any = {"companies": public_company_list} if isinstance(companies, dict) else public_company_list

    for tenant, data in payload["tenants"].items():
        data["recipients"] = _clean_recipients(data.get("recipients"))
    return public_groups, public_settings, public_watchlist, public_companies, _payload(payload)


def merge_groups(groups: list[dict[str, Any]], payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    private = _payload(payload if payload is not None else load_private_payload())
    result: list[dict[str, Any]] = []
    for original in groups or []:
        group = copy.deepcopy(original)
        tenant = normalize_tenant_id(group.get("tenant_id"))
        group["tenant_id"] = tenant
        record = private["groups"].get(str(group.get("id") or "")) or {}
        if record and normalize_tenant_id(record.get("tenant_id")) == tenant:
            group["recipients"] = _clean_recipients(record.get("recipients"))
        else:
            group["recipients"] = []
        result.append(group)
    return result


def merge_settings(settings: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    private = _payload(payload if payload is not None else load_private_payload())
    result = copy.deepcopy(settings or {})
    record = private["settings"]
    tenant = normalize_tenant_id(record.get("tenant_id") or result.get("tenant_id"))
    result["tenant_id"] = tenant
    result["raw_all_recipients"] = _clean_recipients(record.get("raw_all_recipients"))
    return result


def merge_watchlist(watchlist: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    private = _payload(payload if payload is not None else load_private_payload())
    result = copy.deepcopy(watchlist or {})
    record = private["watchlist"]
    tenant = normalize_tenant_id(record.get("tenant_id") or result.get("tenant_id"))
    result["tenant_id"] = tenant
    result["recipients"] = _clean_recipients(record.get("recipients"))
    return result


def merge_companies(companies: Any, payload: dict[str, Any] | None = None) -> Any:
    private = _payload(payload if payload is not None else load_private_payload())
    records = _company_list(companies)
    merged: list[dict[str, Any]] = []
    for original in records:
        company = copy.deepcopy(original)
        tenant = normalize_tenant_id(company.get("tenant_id"))
        company["tenant_id"] = tenant
        record = private["companies"].get(str(company.get("id") or "")) or {}
        if record and normalize_tenant_id(record.get("tenant_id")) == tenant:
            company["email"] = str(record.get("email") or "").strip()
        else:
            company["email"] = ""
        merged.append(company)
    return {"companies": merged} if isinstance(companies, dict) else merged


def allowed_recipients(group: dict[str, Any], recipients: list[str], payload: dict[str, Any] | None = None) -> list[str]:
    """Fail closed when a group has no matching tenant-scoped private recipient record."""
    private = _payload(payload if payload is not None else load_private_payload())
    group_id = str(group.get("id") or "")
    tenant = normalize_tenant_id(group.get("tenant_id"))
    record = private["groups"].get(group_id) or {}
    if not record or normalize_tenant_id(record.get("tenant_id")) != tenant:
        return []
    tenant_record = private["tenants"].get(tenant) or {}
    tenant_allowed = {email.lower() for email in _clean_recipients(tenant_record.get("recipients"))}
    group_allowed = {email.lower() for email in _clean_recipients(record.get("recipients"))}
    return [
        email for email in _clean_recipients(recipients)
        if email.lower() in group_allowed and email.lower() in tenant_allowed
    ]
