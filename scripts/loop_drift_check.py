#!/usr/bin/env python3
"""Work asset drift check — 작업 자산 고착·해시 불일치 탐지.

Usage:
  python3 scripts/loop_drift_check.py
  python3 scripts/loop_drift_check.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS_PATH = ROOT / "auto_dev" / "work_assets.json"
TASKS_PATH = ROOT / "docs" / "project" / "TASKS.md"
CONFIG_PATH = ROOT / "auto_dev" / "loop_config.json"
KST = timezone(timedelta(hours=9))


def file_sha256(rel: str) -> str | None:
    p = ROOT / rel
    if not p.is_file():
        return None
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _tasks_in_section(content: str, section: str) -> list[str]:
    in_section = False
    tasks: list[str] = []
    for line in content.splitlines():
        if line.strip() == f"## {section}":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            m = re.match(r"^- (TASK-\d+):", line.strip())
            if m:
                tasks.append(m.group(1))
    return tasks


def check_running_stale() -> dict:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    hours = cfg.get("limits", {}).get("stale_running_hours", 24)
    content = TASKS_PATH.read_text(encoding="utf-8")
    running = _tasks_in_section(content, "RUNNING")
    # TASKS.md alone cannot tell when RUNNING started; use state file if present
    state_path = ROOT / "var" / "state" / "auto_dev_state.json"
    stale: list[str] = []
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        last_run = state.get("last_run")
        if running and last_run:
            try:
                ts = datetime.fromisoformat(last_run)
                if datetime.now(KST) - ts > timedelta(hours=hours):
                    stale = running
            except ValueError:
                pass
    return {
        "check": "running_stale",
        "ok": not stale,
        "running_tasks": running,
        "stale_tasks": stale,
        "threshold_hours": hours,
    }


def check_asset_checksums() -> dict:
    data = json.loads(ASSETS_PATH.read_text(encoding="utf-8"))
    expected = data.get("checksums", {})
    mismatches: list[dict] = []
    missing: list[str] = []
    for asset in data.get("assets", []):
        rel = asset["path"]
        actual = file_sha256(rel)
        if actual is None:
            missing.append(rel)
            continue
        exp = expected.get(asset["id"])
        if exp and exp != actual:
            mismatches.append({"id": asset["id"], "path": rel, "expected": exp[:12], "actual": actual[:12]})
    return {
        "check": "asset_checksums",
        "ok": not mismatches and not missing,
        "mismatches": mismatches,
        "missing_files": missing,
    }


def check_pending_backlog() -> dict:
    content = TASKS_PATH.read_text(encoding="utf-8")
    count = len(_tasks_in_section(content, "PENDING"))
    limit = 20
    return {
        "check": "pending_backlog",
        "ok": count <= limit,
        "pending_count": count,
        "limit": limit,
    }


def run_drift_check() -> dict:
    checks = [
        check_running_stale(),
        check_asset_checksums(),
        check_pending_backlog(),
    ]
    return {
        "ok": all(c["ok"] for c in checks),
        "checked_at": datetime.now(KST).isoformat(),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_drift_check()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        print(text)
    else:
        print(f"[loop-drift] {'OK' if report['ok'] else 'DRIFT'}")
        for c in report["checks"]:
            print(f"  {c['check']}: {'ok' if c['ok'] else 'WARN'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
