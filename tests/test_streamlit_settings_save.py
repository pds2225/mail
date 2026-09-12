"""Streamlit settings save must not clobber non-UI policy keys.

Bug: 설정 저장 built a 5-key dict and ``_save_private_bundle`` wrote it as the
entire ``settings.json``. Production ``date_unknown_policy=recall`` became
missing → monitor fell back to ``strict`` → date-unknown notices permanently
left the digest. Separate from private-config key-mismatch wipe (#284).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("GMAIL_ADDRESS", "x@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "x")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.security import private_config as pc  # noqa: E402
from mail_core.storage import secure_store  # noqa: E402


POLICY_KEYS = (
    "date_unknown_policy",
    "date_unknown_max_age_days",
    "include_date_unknown",
    "company_match_enabled",
    "notice_versioning_enabled",
    "raw_store_enabled",
    "raw_store_retention_days",
    "region_unknown_mail_limit",
    "filter_trace_sheet_id",
    "filter_trace_sheet_tab",
    "max_posted_age_days",
)


@pytest.fixture()
def streamlit_save_env(tmp_path, monkeypatch):
    """Isolated config paths + Fernet key so save_settings_config can run."""
    monkeypatch.setattr(secure_store, "DEFAULT_KEY_PATH", tmp_path / "mail.key")
    secure_store.ensure_local_key(tmp_path / "mail.key")
    monkeypatch.delenv("MAIL_PRIVATE_CONFIG_JSON", raising=False)
    monkeypatch.delenv("MAIL_PRIVATE_CONFIG_KEY", raising=False)

    groups_path = tmp_path / "groups.json"
    settings_path = tmp_path / "settings.json"
    watchlist_path = tmp_path / "watchlist.json"
    companies_path = tmp_path / "companies.json"
    sites_path = tmp_path / "sites.json"
    private_db = tmp_path / "mail_private.sqlite3"

    full_settings = {
        "date_filter_enabled": True,
        "days_back": 3,
        "include_date_unknown": False,
        "raw_all_enabled": True,
        "raw_all_recipients": [],
        "company_match_enabled": True,
        "max_posted_age_days": None,
        "date_unknown_policy": "recall",
        "date_unknown_max_age_days": 40,
        "raw_store_enabled": True,
        "raw_store_retention_days": 30,
        "raw_store_max_detail_bytes": 800000,
        "raw_store_gzip_detail": True,
        "tenant_id": "default",
        "region_unknown_mail_limit": 10,
        "notice_versioning_enabled": True,
        "filter_trace_sheet_id": "sheet-id",
        "filter_trace_sheet_tab": "filter_trace",
    }
    groups = [{"id": "g1", "name": "t", "active": True, "tenant_id": "default", "recipients": []}]
    settings_path.write_text(json.dumps(full_settings, ensure_ascii=False), encoding="utf-8")
    groups_path.write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
    watchlist_path.write_text("{}", encoding="utf-8")
    companies_path.write_text("[]", encoding="utf-8")
    sites_path.write_text("[]", encoding="utf-8")

    # Seed encrypted recipients so _config_bundle has a truthy private payload.
    _, _, _, _, payload = pc.split_public_private(
        [{"id": "g1", "tenant_id": "default", "recipients": ["ops@example.test"]}],
        {"tenant_id": "default", "raw_all_recipients": ["raw@example.test"]},
        {"tenant_id": "default", "recipients": []},
        [],
    )
    pc.save_private_payload(payload, private_db)

    import streamlit_app as app

    monkeypatch.setattr(app, "GROUPS_PATH", groups_path)
    monkeypatch.setattr(app, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(app, "WATCHLIST_PATH", watchlist_path)
    monkeypatch.setattr(app, "COMPANIES_PATH", companies_path)
    monkeypatch.setattr(app, "SITES_PATH", sites_path)
    monkeypatch.setattr(pc, "PRIVATE_DB_PATH", private_db)
    monkeypatch.setattr(app.private_config, "PRIVATE_DB_PATH", private_db)
    return app, settings_path, full_settings


def test_settings_save_preserves_non_ui_policy_keys(streamlit_save_env):
    app, settings_path, before = streamlit_save_env

    # Mimic the Settings-tab form: only the editable fields are in the update.
    partial = {
        "date_filter_enabled": True,
        "days_back": 2,
        "raw_all_enabled": True,
        "tenant_id": "default",
        "raw_all_recipients": ["raw@example.test"],
    }
    app.save_settings_config(partial)

    after = json.loads(settings_path.read_text(encoding="utf-8"))
    assert after["days_back"] == 2
    for key in POLICY_KEYS:
        assert key in after, f"missing policy key after save: {key}"
        assert after[key] == before[key], f"clobbered {key}: {before[key]!r} → {after[key]!r}"

    # Effective monitor policy must stay recall (not fall back to strict).
    include_unknown = after.get("include_date_unknown", False)
    unknown_policy = after.get("date_unknown_policy") or (
        "all" if include_unknown else "strict"
    )
    assert unknown_policy == "recall"


def test_legacy_five_key_overwrite_would_flip_recall_to_strict():
    """Document the pre-fix failure mode so the regression stays obvious."""
    before = {"date_unknown_policy": "recall", "include_date_unknown": False}
    wiped = {
        "date_filter_enabled": True,
        "days_back": 3,
        "raw_all_enabled": True,
        "tenant_id": "default",
        "raw_all_recipients": [],
    }
    include_unknown = wiped.get("include_date_unknown", False)
    unknown_policy = wiped.get("date_unknown_policy") or (
        "all" if include_unknown else "strict"
    )
    assert before["date_unknown_policy"] == "recall"
    assert unknown_policy == "strict"
