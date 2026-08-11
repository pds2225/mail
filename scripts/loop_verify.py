#!/usr/bin/env python3
"""Loop verification entrypoint — Auto Dev L1 검증 단일 진입점.

eval_rubric.md 의 V1–V3·V9(및 옵션 V6)를 실행한다.
Secret 값은 출력하지 않는다.

Usage:
  python3 scripts/loop_verify.py
  python3 scripts/loop_verify.py --json
  python3 scripts/loop_verify.py --quick          # unit only
  python3 scripts/loop_verify.py --with-core-sources
  python3 scripts/loop_verify.py --drift          # 작업 자산 드리프트 점검
  python3 scripts/loop_verify.py --base-ref origin/main  # 보호파일 diff 기준
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
PROTECTED = ("monitor.py", "streamlit_app.py", ".env", ".env.example")
WORK_ASSETS = (
    "docs/project/RULES.md",
    "docs/project/TASKS.md",
    ".github/workflows/auto-dev-queue.yml",
    "auto_dev/work_assets.json",
    "auto_dev/loop_config.json",
    "auto_dev/loops.json",
    "auto_dev/eval_rubric.md",
    "auto_dev/exit_conditions.md",
    "auto_dev/human_gates.md",
    "auto_dev/defects_inbox.md",
    "docs/autodev/LOOP_ENGINEERING_AUTO_DEV.md",
    "scripts/auto_dev_queue.py",
    "scripts/auto_dev_executor.py",
    "scripts/decompose_defects.py",
    "scripts/loop_verify.py",
)


def _env_for_tests() -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    for key in ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        env.setdefault(key, "gate-check")
    return env


def _run(cmd: list[str], timeout: int = 600) -> dict:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env_for_tests(),
        timeout=timeout,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    tail = "\n".join(out.splitlines()[-8:]) if out else ""
    return {
        "cmd": " ".join(cmd),
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "tail": tail,
    }


def check_protected_files(base_ref: str | None) -> dict:
    """V1: 보호 파일 변경 여부. base_ref 없으면 working tree vs HEAD."""
    changed: list[str] = []
    try:
        if base_ref:
            proc = subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            names = {n.strip() for n in (proc.stdout or "").splitlines() if n.strip()}
            # also include unstaged/staged local changes
            proc2 = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            names |= {n.strip() for n in (proc2.stdout or "").splitlines() if n.strip()}
        else:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            names = {n.strip() for n in (proc.stdout or "").splitlines() if n.strip()}
            proc_staged = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            names |= {n.strip() for n in (proc_staged.stdout or "").splitlines() if n.strip()}
        for pf in PROTECTED:
            if pf in names or any(n == pf or n.endswith("/" + pf) for n in names):
                changed.append(pf)
    except OSError as e:
        return {"id": "V1", "name": "protected_files", "ok": False, "error": str(e), "changed": []}
    return {
        "id": "V1",
        "name": "protected_files",
        "ok": len(changed) == 0,
        "changed": changed,
        "base_ref": base_ref or "HEAD(working-tree)",
    }


def check_unit() -> dict:
    r = _run([sys.executable, "-m", "pytest", "tests/test_monitor.py", "-q", "--tb=no"], timeout=300)
    return {"id": "V2", "name": "unit_pytest", **r}


def check_recall() -> dict:
    r = _run([sys.executable, "scripts/recall_zero_gate.py"], timeout=600)
    return {"id": "V3", "name": "recall_zero_gate", **r}


def check_core_sources() -> dict:
    r = _run([sys.executable, "scripts/core_sources_checklist.py"], timeout=600)
    return {"id": "V6", "name": "core_sources_checklist", **r}


def check_source_field_quality() -> dict:
    r = _run(
        [sys.executable, "scripts/source_field_quality_gate.py", "--offline"],
        timeout=300,
    )
    return {"id": "V9", "name": "source_field_quality_gate", **r}


def check_work_asset_presence() -> dict:
    paths = set(WORK_ASSETS)
    issues: list[str] = []
    registry_path = ROOT / "auto_dev" / "work_assets.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for asset in registry.get("assets", []):
            path = asset.get("path") if isinstance(asset, dict) else None
            if isinstance(path, str) and path.strip():
                paths.add(path.strip())
            else:
                issues.append("work_assets.json contains an asset without a valid path")
    except (OSError, json.JSONDecodeError) as e:
        issues.append(str(e))

    missing = [p for p in sorted(paths) if not (ROOT / p).exists()]
    return {
        "id": "D1",
        "name": "work_assets_present",
        "ok": not missing and not issues,
        "missing": missing,
        "issues": issues,
    }


def check_loops_schema() -> dict:
    path = ROOT / "auto_dev" / "loops.json"
    issues: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"id": "D2", "name": "loops_schema", "ok": False, "issues": [str(e)]}
    loops = data.get("loops") or {}
    required = ("trigger", "execute", "verify", "memory", "exit")
    for name, loop in loops.items():
        for key in required:
            if key not in loop:
                issues.append(f"{name}: missing {key}")
        exit_block = loop.get("exit") or {}
        if not exit_block.get("escalate") and not exit_block.get("success"):
            issues.append(f"{name}: exit has no success/escalate")
    return {"id": "D2", "name": "loops_schema", "ok": len(issues) == 0, "issues": issues}


def check_tasks_structure() -> dict:
    path = ROOT / "docs" / "project" / "TASKS.md"
    if not path.exists():
        return {"id": "D3", "name": "tasks_structure", "ok": False, "issues": ["TASKS.md missing"]}
    text = path.read_text(encoding="utf-8")
    issues = []
    for section in ("PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"):
        if f"## {section}" not in text:
            issues.append(f"missing ## {section}")
    # orphan RUNNING warning (drift)
    import re

    m = re.search(r"## RUNNING\n+(.*?)(?=\n## |\Z)", text, re.S)
    running_items = []
    if m:
        running_items = [ln for ln in m.group(1).splitlines() if ln.strip().startswith("- TASK-")]
    return {
        "id": "D3",
        "name": "tasks_structure",
        "ok": len(issues) == 0,
        "issues": issues,
        "running_orphan_count": len(running_items),
        "running": running_items,
    }


def check_pending_backlog() -> dict:
    """드리프트: PENDING 과다 적체는 L2 개입 신호."""
    path = ROOT / "docs" / "project" / "TASKS.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    import re

    m = re.search(r"## PENDING\n+(.*?)(?=\n## |\Z)", text, re.S)
    pending = []
    if m:
        pending = [ln.strip() for ln in m.group(1).splitlines() if ln.strip().startswith("- TASK-")]
    warn_threshold = 20
    return {
        "id": "D4",
        "name": "pending_backlog",
        "ok": True,  # 경고만 — 검증 실패로 만들지 않음
        "count": len(pending),
        "warn": len(pending) >= warn_threshold,
        "threshold": warn_threshold,
    }


def check_outstanding_dev() -> dict:
    """D6: leftover remotes/worktrees must not hide UNIQUE_CANDIDATE content."""
    script = ROOT / "scripts" / "outstanding_dev_audit.py"
    if not script.exists():
        return {
            "id": "D6",
            "name": "outstanding_dev_audit",
            "ok": False,
            "issues": ["scripts/outstanding_dev_audit.py missing"],
        }
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--json", "--strict"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_env_for_tests(),
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {
            "id": "D6",
            "name": "outstanding_dev_audit",
            "ok": False,
            "issues": [str(e)],
        }
    issues: list[str] = []
    unique: list[str] = []
    stashes = 0
    raw = (proc.stdout or "").strip()
    if raw:
        try:
            report = json.loads(raw)
            unique = [
                f"{u.get('ref')}:{','.join((u.get('unique_paths') or [])[:3])}"
                for u in report.get("unique_candidates") or []
            ]
            stashes = len(report.get("stashes") or [])
            if unique:
                issues.append(f"UNIQUE_CANDIDATE={unique}")
            if stashes:
                issues.append(f"stash_count={stashes}")
        except json.JSONDecodeError as e:
            issues.append(f"audit json parse failed: {e}")
    elif proc.returncode != 0:
        issues.append((proc.stderr or "outstanding_dev_audit failed").strip()[:500])
    return {
        "id": "D6",
        "name": "outstanding_dev_audit",
        "ok": len(issues) == 0 and proc.returncode == 0,
        "issues": issues,
        "unique_candidates": unique,
        "stash_count": stashes,
    }


def check_trigger_alignment() -> dict:
    """D5: declared schedule state must match the active workflow trigger."""
    config_path = ROOT / "auto_dev" / "loop_config.json"
    workflow_path = ROOT / ".github" / "workflows" / "auto-dev-queue.yml"
    issues: list[str] = []
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        schedule_enabled = config.get("trigger", {}).get("schedule_enabled")
    except (OSError, json.JSONDecodeError) as e:
        return {"id": "D5", "name": "trigger_alignment", "ok": False, "issues": [str(e)]}

    if not isinstance(schedule_enabled, bool):
        issues.append("loop_config.trigger.schedule_enabled must be boolean")

    try:
        workflow_lines = workflow_path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return {"id": "D5", "name": "trigger_alignment", "ok": False, "issues": [str(e)]}

    active_lines = [
        line for line in workflow_lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    workflow_schedule_enabled = any(
        re.match(r"^\s+schedule\s*:\s*$", line) for line in active_lines
    )
    workflow_dispatch_enabled = any(
        re.match(r"^\s+workflow_dispatch\s*:\s*$", line) for line in active_lines
    )
    if isinstance(schedule_enabled, bool) and schedule_enabled != workflow_schedule_enabled:
        issues.append(
            "loop_config schedule_enabled does not match auto-dev-queue.yml"
        )
    if not workflow_dispatch_enabled:
        issues.append("auto-dev-queue.yml has no active workflow_dispatch trigger")

    return {
        "id": "D5",
        "name": "trigger_alignment",
        "ok": not issues,
        "issues": issues,
        "schedule_enabled": workflow_schedule_enabled,
        "workflow_dispatch_enabled": workflow_dispatch_enabled,
    }


def run_verify(
    *,
    quick: bool = False,
    with_core_sources: bool = False,
    base_ref: str | None = None,
    drift_only: bool = False,
) -> dict:
    checks: list[dict] = []
    if drift_only:
        checks = [
            check_work_asset_presence(),
            check_loops_schema(),
            check_tasks_structure(),
            check_pending_backlog(),
            check_trigger_alignment(),
            check_outstanding_dev(),
        ]
    else:
        checks.append(check_protected_files(base_ref))
        checks.append(check_unit())
        checks.append(check_source_field_quality())
        if not quick:
            checks.append(check_recall())
        if with_core_sources:
            checks.append(check_core_sources())
        # always attach lightweight drift presence (non-fatal unless missing assets when expected)
        checks.append(check_work_asset_presence())
        checks.append(check_loops_schema())
        if not quick:
            checks.append(check_outstanding_dev())

    # Fatal: V* and D1/D2; D3 issues fatal; D4 warn only
    fatal_ids = {"V1", "V2", "V3", "V6", "V9", "D1", "D2", "D3", "D5", "D6"}
    ok = True
    for c in checks:
        if c.get("id") in fatal_ids and not c.get("ok", False):
            ok = False
        if c.get("id") == "D4" and c.get("warn"):
            pass

    return {
        "ok": ok,
        "ts": datetime.now(KST).isoformat(),
        "mode": "drift" if drift_only else ("quick" if quick else "full"),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mail Auto Dev loop verifier")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--quick", action="store_true", help="unit + protected only")
    parser.add_argument("--with-core-sources", action="store_true")
    parser.add_argument("--drift", action="store_true", help="작업 자산 드리프트만")
    parser.add_argument("--base-ref", default=None, help="보호파일 diff 기준 ref")
    args = parser.parse_args()

    result = run_verify(
        quick=args.quick,
        with_core_sources=args.with_core_sources,
        base_ref=args.base_ref,
        drift_only=args.drift,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(f"[loop_verify] mode={result['mode']} ok={result['ok']}")
        for c in result["checks"]:
            # ASCII markers keep the verifier usable on Windows consoles whose
            # default cp949 codec cannot encode emoji status characters.
            status = "[PASS]" if c.get("ok") else "[FAIL]"
            if c.get("id") == "D4" and c.get("warn"):
                status = "[WARN]"
            name = c.get("name", c.get("id"))
            extra = ""
            if c.get("changed"):
                extra = f" changed={c['changed']}"
            if c.get("missing"):
                extra = f" missing={c['missing']}"
            if c.get("issues"):
                extra = f" issues={c['issues']}"
            if c.get("summary"):
                extra = f" {c['summary']}"
            if c.get("tail") and not c.get("ok"):
                extra = f" | {c['tail'][:200]}"
            if c.get("id") == "D4":
                extra = f" pending={c.get('count')} warn={c.get('warn')}"
            print(f"  {status} {c.get('id')} {name}{extra}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.TimeoutExpired:
        print("[loop_verify] timeout", file=sys.stderr)
        sys.exit(2)
