#!/usr/bin/env python3
"""Loop verification — L1 검증 게이트 실행기.

TASK 프로필 tier에 따라 recall_zero_gate, core_sources_checklist 등을 실행하고
verify_report.json 형태의 판정을 반환한다.

Usage:
  python3 scripts/loop_verify.py
  python3 scripts/loop_verify.py --tier 2
  python3 scripts/loop_verify.py --tier 1 --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "auto_dev" / "loop_config.json"
PROTECTED = {"monitor.py", "streamlit_app.py", ".env", ".env.example"}


def _env() -> dict[str, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    for key in ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        env.setdefault(key, "loop-verify")
    return env


def _run(cmd: list[str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        cmd, cwd=cwd or ROOT, capture_output=True, text=True, env=_env()
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return {
        "cmd": cmd,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "tail": out.strip().splitlines()[-3:] if out.strip() else [],
    }


def step_preflight() -> dict:
    issues: list[str] = []
    for name in ("TASKS.md", "RULES.md", "AGENTS.md"):
        if not (ROOT / name).exists():
            issues.append(f"missing {name}")
    content = (ROOT / "TASKS.md").read_text(encoding="utf-8") if (ROOT / "TASKS.md").exists() else ""
    for section in ("PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"):
        if f"## {section}" not in content:
            issues.append(f"TASKS.md missing ## {section}")
    return {"step": "preflight", "ok": not issues, "issues": issues}


def step_email_send_risk(task_title: str = "") -> dict:
    danger = [
        "실제 발송", "send email", "smtp send", "메일 발송 실행",
        "이메일 전송", "real send", "production send",
    ]
    hit = [kw for kw in danger if kw in task_title.lower()]
    return {"step": "email_send_risk", "ok": not hit, "hits": hit}


def step_protected_files_diff() -> dict:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    changed = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    touched = [p for p in changed if Path(p).name in PROTECTED]
    return {"step": "protected_files_diff", "ok": not touched, "touched": touched}


def step_pytest_monitor() -> dict:
    r = _run([sys.executable, "-m", "pytest", "test_monitor.py", "-q", "--tb=no"])
    r["step"] = "pytest_monitor"
    return r


def step_recall_zero_gate() -> dict:
    r = _run([sys.executable, "scripts/recall_zero_gate.py", "--json"])
    r["step"] = "recall_zero_gate"
    if r["ok"] and r["tail"]:
        try:
            r["report"] = json.loads(r["tail"][-1]) if r["tail"][-1].startswith("{") else None
        except json.JSONDecodeError:
            pass
    return r


def step_core_sources_offline() -> dict:
    r = _run([sys.executable, "scripts/core_sources_checklist.py", "--json"])
    r["step"] = "core_sources_checklist_offline"
    return r


def step_accuracy_regression() -> dict:
    path = ROOT / "test_accuracy_regression.py"
    if not path.exists():
        return {"step": "test_accuracy_regression", "ok": True, "skipped": True}
    r = _run([sys.executable, "-m", "pytest", "test_accuracy_regression.py", "-q", "--tb=no"])
    r["step"] = "test_accuracy_regression"
    return r


STEP_RUNNERS = {
    "preflight": lambda **_: step_preflight(),
    "email_send_risk": lambda task_title="", **_: step_email_send_risk(task_title),
    "protected_files_diff": lambda **_: step_protected_files_diff(),
    "pytest_monitor": lambda **_: step_pytest_monitor(),
    "recall_zero_gate": lambda **_: step_recall_zero_gate(),
    "core_sources_checklist_offline": lambda **_: step_core_sources_offline(),
    "test_accuracy_regression": lambda **_: step_accuracy_regression(),
}


def load_tier_steps(tier: int) -> list[str]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    tiers = cfg.get("verification_tiers", {})
    steps: list[str] = []
    for t in range(0, tier + 1):
        key = str(t)
        if key in tiers:
            steps.extend(tiers[key].get("steps", []))
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s in steps:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def run_verification(tier: int = 1, task_title: str = "") -> dict:
    steps = load_tier_steps(tier)
    results: list[dict] = []
    for name in steps:
        runner = STEP_RUNNERS.get(name)
        if not runner:
            results.append({"step": name, "ok": False, "error": "unknown step"})
            continue
        results.append(runner(task_title=task_title))

    all_pass = all(r.get("ok") for r in results)
    blocked = any(
        r.get("step") == "email_send_risk" and not r.get("ok") for r in results
    ) or any(
        r.get("step") == "protected_files_diff" and not r.get("ok") for r in results
    )
    return {
        "tier": tier,
        "all_pass": all_pass,
        "blocked": blocked,
        "steps": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mail auto-dev loop verification")
    parser.add_argument("--tier", type=int, default=1)
    parser.add_argument("--task-title", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = run_verification(tier=args.tier, task_title=args.task_title)
    text = json.dumps(report, ensure_ascii=False, indent=2)

    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        status = "PASS" if report["all_pass"] else "FAIL"
        print(f"[loop-verify] tier={args.tier} {status}")
        for s in report["steps"]:
            mark = "ok" if s.get("ok") else "FAIL"
            print(f"  {s.get('step')}: {mark}")

    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
