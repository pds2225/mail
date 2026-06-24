"""core_sources_checklist 스크립트 단위 테스트 (네트워크 없음)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for _k, _v in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
}.items():
    os.environ.setdefault(_k, _v)


def test_core_sources_checklist_runs_offline():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "core_sources_checklist.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = __import__("json").loads(proc.stdout)
    assert data["gate"] == "core_sources_checklist"
    assert data["ok"] is True
    assert data["passed"] == data["total"]


def test_three_sources_in_output():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "core_sources_checklist.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    data = __import__("json").loads(proc.stdout)
    ids = {s["id"] for s in data["sources"]}
    assert ids == {"bizinfo", "kstartup", "nipa"}
