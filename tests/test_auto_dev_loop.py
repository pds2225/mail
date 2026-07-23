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

ROOT = Path(__file__).resolve().parent.parent


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


ex = _load("auto_dev_executor_under_test", "scripts/auto_dev_executor.py")
dec = _load("decompose_defects_under_test", "scripts/decompose_defects.py")


def test_executor_noop_email_rules():
    r = ex.execute_task(
        "TASK-002",
        "RULES.md에 실제 이메일 자동 발송 금지, preview/dry-run 우선 원칙을 추가한다.",
        dry_run=True,
    )
    assert r.status == "DONE_NOOP", r.reason


def test_executor_noop_summary():
    r = ex.execute_task(
        "TASK-003",
        "GitHub Actions Summary에 이번 실행 TASK, 결과, 다음 TASK를 표시",
        dry_run=True,
    )
    assert r.status == "DONE_NOOP", r.reason


def test_executor_needs_agent_for_parser():
    r = ex.execute_task("TASK-006", "소진공 파서 selector 안정화", dry_run=True)
    assert r.status == "NEEDS_AGENT"


def test_decompose_parse_and_preview(tmp_path):
    inbox = tmp_path / "inbox.md"
    inbox.write_text(
        "## DEFECT-009\n\ntitle: 테스트 빈틈\napproved: yes\nsummary: x\nloop: coding-fix\n",
        encoding="utf-8",
    )
    defects = dec.parse_defects(inbox.read_text(encoding="utf-8"))
    assert len(defects) == 1
    assert defects[0]["approved"] is True
    assert defects[0]["id"] == "DEFECT-009"


def test_move_task_to_pending_end():
    content = """# T\n\n## PENDING\n\n- TASK-001: a\n- TASK-002: b\n\n## RUNNING\n\n- TASK-003: c\n\n## DONE\n\n## FAILED\n\n## BLOCKED\n"""
    out = q.move_task_to_pending_end(content, "- TASK-003: c", from_section="RUNNING")
    sections = q.parse_tasks(out)
    assert sections["RUNNING"] == []
    assert sections["PENDING"][-1] == "- TASK-003: c"
    assert sections["PENDING"][0] == "- TASK-001: a"


def test_executor_loan_review_noop():
    r = ex.execute_task(
        "TASK-006",
        "소진공 정책자금 페이지 구조 변경에 대비해 파서 selector 안정화를 검토한다.",
        dry_run=True,
    )
    assert r.status == "DONE_NOOP", r.reason
