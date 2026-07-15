"""Unit tests for Loop Engineering auto-dev helpers (no network, no secrets)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "t@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

ROOT = Path(__file__).resolve().parent


def _load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


q = _load("auto_dev_queue_under_test", "scripts/auto_dev_queue.py")
lv = _load("loop_verify_under_test", "scripts/loop_verify.py")


def test_infer_loop_key_explicit_meta():
    assert q.infer_loop_key("loop:gate-repair FIX TASK-001 — fail") == "gate-repair"


def test_infer_loop_key_accuracy():
    assert q.infer_loop_key("FP/FN 빈틈 클러스터 정리") == "accuracy-defect"


def test_infer_loop_key_default_coding():
    assert q.infer_loop_key("README에 사용법 추가") == "coding-fix"


def test_check_email_send_risk():
    assert q.check_email_send_risk("실제 발송 켜기") is True
    assert q.check_email_send_risk("dry-run 문서화") is False


def test_loops_json_schema_ok():
    r = lv.check_loops_schema()
    assert r["ok"] is True, r.get("issues")


def test_work_assets_present():
    r = lv.check_work_asset_presence()
    assert r["ok"] is True, r.get("missing")


def test_format_loop_summary_contains_five_elements():
    loops = q.load_loops()["loops"]
    text = q.format_loop_summary("coding-fix", loops["coding-fix"])
    assert "트리거" in text and "실행" in text and "검증" in text
    assert "메모리" in text and "종료" in text


def test_next_task_id_increments():
    sections = {
        "PENDING": ["- TASK-011: a"],
        "DONE": ["- TASK-010: b"],
    }
    assert q.next_task_id(sections) == "TASK-012"


def test_drift_verify_ok():
    result = lv.run_verify(drift_only=True)
    assert result["ok"] is True
    assert result["mode"] == "drift"
