"""Auto Dev Controller 하드닝 회귀 테스트."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_controller():
    path = ROOT / "scripts" / "auto_dev_controller.py"
    spec = importlib.util.spec_from_file_location("auto_dev_controller_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


c = _load_controller()


def test_task_md_is_only_source_for_top_level_selection(tmp_path, monkeypatch):
    task_md = tmp_path / "TASK.md"
    task_md.write_text(
        "[ ] TOP-001 | kind=implementation top-level task\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(c, "TOP_TASK_PATH", task_md)
    monkeypatch.setattr(c, "TASKS_PATH", tmp_path / "must-not-be-read.md")

    selected = c.select_task()

    assert selected["task_id"] == "TOP-001"
    assert selected["source"] == "TASK.md"
    assert selected["kind"] == "implementation"


def test_active_task_always_resumes_before_new_ready():
    selected = c.select_task(
        "\n".join(
            [
                "[ ] READY-001 | kind=implementation new ready task",
                "[~] ACTIVE-001 | kind=policy active task",
            ]
        )
    )

    assert selected["task_id"] == "ACTIVE-001"
    assert selected["status"] == "ACTIVE"


def test_never_requests_user_confirmation():
    patterns = (
        r"\binput\s*\(",
        r"\bask_user\s*\(",
        r"\bconfirm_user\s*\(",
        r"\bwait_for_user\s*\(",
    )
    for relative in (
        "scripts/auto_dev_controller.py",
        "scripts/auto_dev_executor.py",
        "scripts/auto_dev_queue.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert not any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns), relative


def test_interrupted_run_resumes_from_checkpoint(tmp_path):
    checkpoint = tmp_path / "auto_dev_runtime.json"
    source = "[~] ACTIVE-001 | kind=policy active controller task"
    first_calls = []

    def interrupt_before_full_test(task, phase, state):
        first_calls.append(phase)
        if phase == "FULL_TEST":
            raise KeyboardInterrupt
        return {"ok": True}

    first = c.run_controller(
        source_text=source,
        checkpoint_path=checkpoint,
        phase_runner=interrupt_before_full_test,
    )
    assert first["status"] == "ACTIVE"
    assert first["last_completed_phase"] == "COMPILE"
    assert "IMPLEMENT" in first_calls

    resumed_calls = []

    def complete_after_restart(task, phase, state):
        resumed_calls.append(phase)
        return {"ok": True}

    second = c.run_controller(
        source_text=source,
        checkpoint_path=checkpoint,
        phase_runner=complete_after_restart,
    )
    assert second["status"] == "DONE"
    assert resumed_calls[0] == "FULL_TEST"
    assert "IMPLEMENT" not in resumed_calls


def test_implementation_cannot_modify_policy_files():
    blocked = c.validate_changed_files(
        "implementation",
        ["scripts/auto_dev_controller.py", "mail_core/example.py"],
    )
    allowed = c.validate_changed_files("implementation", ["mail_core/example.py"])

    assert blocked["ok"] is False
    assert blocked["code"] == "TASK_KIND_SCOPE_VIOLATION"
    assert allowed["ok"] is True


def test_agent_unavailable_is_transient_then_blocks_without_new_task(tmp_path, monkeypatch):
    checkpoint = tmp_path / "auto_dev_runtime.json"
    snapshots = []
    original_save = c.save_checkpoint

    def capture(state, path):
        snapshots.append(dict(state))
        return original_save(state, path)

    monkeypatch.setattr(c, "save_checkpoint", capture)
    result = c.run_controller(
        source_text="[~] ACTIVE-001 | kind=implementation active task",
        checkpoint_path=checkpoint,
    )

    assert any(state.get("status") == "AWAITING_AGENT" for state in snapshots)
    assert result["status"] == "BLOCKED"
    assert result["code"] == "AGENT_UNAVAILABLE"
    assert result["task_id"] == "ACTIVE-001"
