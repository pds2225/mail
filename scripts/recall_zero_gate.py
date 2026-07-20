#!/usr/bin/env python3
"""Recall zero gate — 알려진 누락(recall) 테스트가 전부 통과할 때만 OK.

야간 자동개발·CI가 '누락 없음' 종료 조건을 숫자로 판정할 때 쓴다.
3대 소스(기업마당·K-Startup·NIPA) 수집 완성도는 scripts/core_sources_checklist.py (별도).

Usage (PowerShell, D:\\mail):
  python scripts/recall_zero_gate.py
  python scripts/recall_zero_gate.py --json
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

# recall 회귀 전용 스위트 (전체 pytest 보다 빠름)
RECALL_SUITES = [
    "test_5field_casematrix.py",
    "test_seoul_ai_recall.py",
    "test_decision_matrix.py",
    "test_download_kstartup_targets.py",
]

SMOKE_SCRIPTS = [
    "scripts/seoul_ai_recall_check.py",
]


def _run_pytest(suite: str) -> dict:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    for key in ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        env.setdefault(key, "gate-check")
    cmd = [sys.executable, "-m", "pytest", str(ROOT / "tests" / suite), "-q", "--tb=no", "--runxfail"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    tail = (proc.stdout or "") + (proc.stderr or "")
    summary = tail.strip().splitlines()[-1] if tail.strip() else ""
    m = re.search(r"(\d+) failed|(\d+) xfailed", summary)
    failed = int(m.group(1) or 0) if m and m.group(1) else 0
    if m and m.group(2):
        failed += int(m.group(2))
    return {
        "suite": suite,
        "ok": proc.returncode == 0 and failed == 0,
        "exit_code": proc.returncode,
        "summary": summary,
    }


def _run_script(rel: str) -> dict:
    cmd = [sys.executable, str(ROOT / rel)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {
        "script": rel,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "tail": (proc.stdout or proc.stderr or "").strip().splitlines()[-3:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [_run_pytest(s) for s in RECALL_SUITES]
    results += [_run_script(s) for s in SMOKE_SCRIPTS]
    failed = [r for r in results if not r["ok"]]
    out = {
        "gate": "recall_zero",
        "passed": len(results) - len(failed),
        "total": len(results),
        "ok": len(failed) == 0,
        "results": results,
        "note": (
            "이 게이트는 '코드로 재현 가능한 누락'만 막는다. "
            "사이트 장애·날짜필터·seen_ids·본문40건 제한 등 실세계 누락은 별도."
        ),
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if out["ok"] else "FAIL"
        print(f"recall_zero_gate: {status} ({out['passed']}/{out['total']})")
        for r in results:
            mark = "OK" if r["ok"] else "NG"
            name = r.get("suite") or r.get("script")
            extra = r.get("summary") or r.get("tail")
            print(f"  [{mark}] {name} {extra}")
        if not out["ok"]:
            print("\n→ 실패 항목부터 monitor.py recall 수정 후 재실행")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
