#!/usr/bin/env python3
"""Overnight auto-dev readiness check (user-priority queue first).

Does NOT enable GHA cron by itself. Reports blockers honestly:
- PENDING tasks present (user-priority first)
- schedule_enabled flag in loop_config.json
- AUTO_DEV_AGENT / DRY_RUN env expectations
- Secret *presence* only (never print values): AUTO_DEV_PAT via env or note GHA secret

Usage:
  python3 scripts/auto_dev_overnight_ready.py
  python3 scripts/auto_dev_overnight_ready.py --json
  python3 scripts/auto_dev_overnight_ready.py --require-live  # exit 1 unless live-ready
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "docs" / "project" / "TASKS.md"
LOOP_CFG = ROOT / "auto_dev" / "loop_config.json"
WORKFLOW = ROOT / ".github" / "workflows" / "auto-dev-queue.yml"


def _pending_tasks(text: str) -> list[str]:
    in_pending = False
    out: list[str] = []
    for line in text.splitlines():
        if line.strip() == "## PENDING":
            in_pending = True
            continue
        if in_pending and line.startswith("## "):
            break
        if in_pending:
            m = re.match(r"^- (TASK-\d+):\s*(.*)$", line.strip())
            if m:
                out.append(f"{m.group(1)}: {m.group(2).strip()}")
    return out


def _user_priority_first(pending: list[str]) -> list[str]:
    """Prefer TASK lines that mention user-priority keywords."""
    keys = (
        "user-priority",
        "사용자",
        "요청",
        "outstanding",
        "merge",
        "병합",
        "source-field",
        "source_field",
        "overnight",
        "야간",
        "audit",
    )

    def score(line: str) -> int:
        low = line.lower()
        return sum(1 for k in keys if k.lower() in low)

    return sorted(pending, key=lambda x: (-score(x), x))


def run_check() -> dict:
    tasks_text = TASKS.read_text(encoding="utf-8") if TASKS.exists() else ""
    pending = _pending_tasks(tasks_text)
    ordered = _user_priority_first(pending)

    cfg = {}
    if LOOP_CFG.exists():
        cfg = json.loads(LOOP_CFG.read_text(encoding="utf-8"))
    schedule_enabled = bool(cfg.get("trigger", {}).get("schedule_enabled"))

    wf = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.exists() else ""
    cron_active = bool(re.search(r"(?m)^\s*schedule:\s*$", wf)) and "cron:" in wf
    # Commented schedule still has cron in comments — detect uncommented block loosely
    cron_active = bool(
        re.search(r"(?m)^  schedule:\s*\n(?:.|\n)*?cron:", wf)
        and not re.search(r"(?m)^  # schedule:", wf)
    )

    agent = os.environ.get("AUTO_DEV_AGENT", "false").lower() == "true"
    pat_env = bool(os.environ.get("AUTO_DEV_PAT") or os.environ.get("GITHUB_TOKEN"))

    blockers: list[str] = []
    if not pending:
        blockers.append("PENDING queue empty — refill user-priority tasks before overnight")
    if not schedule_enabled:
        blockers.append("loop_config trigger.schedule_enabled=false")
    if not cron_active:
        blockers.append("GHA auto-dev-queue.yml schedule not active (PAT/agent historically required)")
    if not agent:
        blockers.append("AUTO_DEV_AGENT is not true — queue will AWAITING_AGENT (no false DONE)")
    if not pat_env:
        blockers.append("No AUTO_DEV_PAT/GITHUB_TOKEN in this environment (GHA may still have secrets)")

    live_ready = (
        len(pending) > 0
        and schedule_enabled
        and cron_active
        and agent
        and pat_env
    )
    local_agent_ready = len(pending) > 0  # Cursor/local agent can drain PENDING tonight

    return {
        "ok_local_agent": local_agent_ready,
        "ok_live_gha": live_ready,
        "pending_count": len(pending),
        "pending_user_priority_order": ordered,
        "schedule_enabled": schedule_enabled,
        "gha_cron_active": cron_active,
        "auto_dev_agent": agent,
        "pat_or_token_present": pat_env,
        "blockers": blockers,
        "advice": (
            "Drain PENDING locally tonight with a coding agent (user-priority order). "
            "Do not re-enable GHA cron until schedule_enabled + valid AUTO_DEV_PAT + AUTO_DEV_AGENT."
        ),
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-live", action="store_true")
    ap.add_argument("--require-local", action="store_true")
    args = ap.parse_args()
    report = run_check()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[overnight-ready] local_agent={report['ok_local_agent']} live_gha={report['ok_live_gha']}")
        print(f"[overnight-ready] pending={report['pending_count']}")
        for line in report["pending_user_priority_order"][:10]:
            print(f"  - {line}")
        for b in report["blockers"]:
            print(f"  blocker: {b}")
        print(f"[overnight-ready] {report['advice']}")
    if args.require_live and not report["ok_live_gha"]:
        return 1
    if args.require_local and not report["ok_local_agent"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
