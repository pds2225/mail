"""Repository layout regression tests."""
from __future__ import annotations

from pathlib import Path

import monitor
from mail_core.delivery import outbox
from mail_core.matching import company_match
from mail_core.operations import coverage_alert
from mail_core.paths import CONFIG_DIR, OUTBOX_DIR, REPO_ROOT, STATE_DIR


def test_canonical_config_and_runtime_paths() -> None:
    assert monitor.SITES_PATH == CONFIG_DIR / "sites.json"
    assert monitor.GROUPS_PATH == CONFIG_DIR / "groups.json"
    assert monitor.SETTINGS_PATH == CONFIG_DIR / "settings.json"
    assert monitor.SEEN_IDS_PATH == STATE_DIR / "seen_ids.json"
    assert monitor.DELIVERY_STATE_PATH == STATE_DIR / "delivery_state.json"
    assert company_match.COMPANIES_PATH == CONFIG_DIR / "companies.json"
    assert outbox.OUTBOX_PATH == OUTBOX_DIR / "delivery_outbox.enc"
    assert coverage_alert.COVERAGE_BASELINE_PATH == STATE_DIR / "coverage_baseline.json"


def test_config_and_persistent_delivery_state_exist() -> None:
    required = [
        CONFIG_DIR / "sites.json",
        CONFIG_DIR / "groups.json",
        CONFIG_DIR / "settings.json",
        CONFIG_DIR / "companies.json",
        CONFIG_DIR / "watchlist.json",
        STATE_DIR / "seen_ids.json",
        STATE_DIR / "delivery_state.json",
        OUTBOX_DIR / "delivery_outbox.enc",
    ]
    assert all(path.is_file() for path in required)


def test_legacy_root_clutter_does_not_return() -> None:
    legacy_names = {
        "sites.json",
        "groups.json",
        "settings.json",
        "companies.json",
        "watchlist.json",
        "company_match.py",
        "delivery_state.py",
        "delivery_outbox.py",
        "state_store.py",
        "run_monitor.bat",
        "auto_mail_web.html",
    }
    root_files = {path.name for path in Path(REPO_ROOT).iterdir() if path.is_file()}
    assert legacy_names.isdisjoint(root_files)
