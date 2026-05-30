#!/usr/bin/env python3
"""Dry-run: 발송·seen_ids 저장 없이 커버리지·review queue 보고서 생성.

사용:
  python3 scripts/monitor_dry_run.py
  python3 scripts/monitor_dry_run.py --skip-coverage-fetch

환경변수(mock): test_monitor.py와 동일하게 API 키 placeholder 필요.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BIZINFO_API_KEY", "dry_run_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "dry_run_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "dry_run_pass")
os.environ.setdefault("GMAIL_ADDRESS", "dry-run@example.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

from monitor import run_dry_run  # noqa: E402


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-coverage-fetch", action="store_true")
    parser.add_argument("--json", action="store_true", help="요약 JSON stdout")
    args = parser.parse_args()

    summary = run_dry_run(
        write_reports=True,
        fetch_coverage=not args.skip_coverage_fetch,
    )
    public = {
        k: summary[k]
        for k in summary
        if k not in ("date_review_queue", "coverage", "recipient_audit", "preview_groups")
    }
    if args.json:
        print(json.dumps(public, ensure_ascii=False, indent=2, default=str))
    else:
        print("=== monitor dry-run summary ===")
        for key, val in public.items():
            print(f"  {key}: {val}")
        print("Reports: logs/site_collection_coverage_report.md")
        print("         logs/today_notice_missing_risk_report.md")
        print("         logs/review_queue_YYYYMMDD.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
