"""Run site diagnostic without sending any mail.

Usage (PowerShell, from D:\\mail):
    python scripts\\run_site_diagnostic.py

Loads sites.json, runs HEAD/GET for each, writes reports/site_diagnostic_*.md.
No mail is sent. No environment variables required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from site_diagnostic import diagnose_all


def main() -> int:
    sites_path = ROOT / "sites.json"
    if not sites_path.exists():
        print(f"sites.json not found at {sites_path}", file=sys.stderr)
        return 2
    try:
        sites = json.loads(sites_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to parse sites.json: {e}", file=sys.stderr)
        return 2
    if not isinstance(sites, list):
        print("sites.json must be a list", file=sys.stderr)
        return 2

    report = diagnose_all(sites, reports_dir=ROOT / "reports")
    print(f"Report written: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
