#!/usr/bin/env python3
"""Move recipient/company emails out of tracked JSON into encrypted local state.

Run once locally before using the dashboard or manual delivery. GitHub Actions receives
the same payload through the MAIL_PRIVATE_CONFIG_JSON secret instead of this local file.
The command intentionally reports counts only and never prints email addresses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import private_config  # noqa: E402
from state_store import atomic_write_json  # noqa: E402


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"config read failed: {path.name}") from exc


def _email_counts(payload: dict) -> dict[str, int]:
    return {
        "group_recipients": sum(
            len(value.get("recipients") or []) for value in payload.get("groups", {}).values()
        ),
        "raw_all_recipients": len(payload.get("settings", {}).get("raw_all_recipients") or []),
        "watchlist_recipients": len(payload.get("watchlist", {}).get("recipients") or []),
        "company_emails": sum(
            1 for value in payload.get("companies", {}).values() if value.get("email")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Move mail PII to encrypted private config")
    parser.add_argument("--dry-run", action="store_true", help="validate and show counts without writing")
    args = parser.parse_args()

    groups = _read(ROOT / "groups.json", [])
    settings = _read(ROOT / "settings.json", {})
    watchlist = _read(ROOT / "watchlist.json", {})
    companies = _read(ROOT / "companies.json", [])
    public_groups, public_settings, public_watchlist, public_companies, payload = (
        private_config.split_public_private(groups, settings, watchlist, companies)
    )
    counts = _email_counts(payload)

    if not args.dry_run:
        private_config.save_private_payload(payload)
        atomic_write_json(ROOT / "groups.json", public_groups, indent=2, backup=True)
        atomic_write_json(ROOT / "settings.json", public_settings, indent=2, backup=True)
        atomic_write_json(ROOT / "watchlist.json", public_watchlist, indent=2, backup=True)
        atomic_write_json(ROOT / "companies.json", public_companies, indent=2, backup=True)
    action = "validated" if args.dry_run else "migrated"
    print(
        f"private config {action}: groups={counts['group_recipients']}, "
        f"raw_all={counts['raw_all_recipients']}, watchlist={counts['watchlist_recipients']}, "
        f"companies={counts['company_emails']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
