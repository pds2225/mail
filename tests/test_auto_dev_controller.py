"""Auto Dev Controller 하드닝 회귀 테스트."""
from __future__ import annotations

import importlib.util
import json
import re
from types import SimpleNamespace
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
    persisted = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert set(persisted) == c.CHECKPOINT_FIELDS

    fresh_runner = _load_controller()
    resumed_calls = []

    def complete_after_restart(task, phase, state):
        resumed_calls.append(phase)
        return {"ok": True}

    second = fresh_runner.run_controller(
        source_text=source,
        checkpoint_path=checkpoint,
        phase_runner=complete_after_restart,
    )
    assert second["status"] == "DONE"
    assert resumed_calls[0] == "FULL_TEST"
    assert "IMPLEMENT" not in resumed_calls


def test_checkpoint_uses_tracked_path_and_never_persists_extra_fields(tmp_path):
    assert c.CHECKPOINT_PATH == ROOT / "var" / "state" / "auto_dev_runtime.json"
    assert ".omc" not in c.CHECKPOINT_PATH.parts

    checkpoint = tmp_path / "auto_dev_runtime.json"
    c.save_checkpoint(
        {
            "task_id": "TASK-001",
            "status": "ACTIVE",
            "phase": "IMPLEMENT",
            "attempt": 1,
            "secret": "must-not-persist",
        },
        checkpoint,
    )
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert set(saved) == c.CHECKPOINT_FIELDS
    assert "secret" not in saved


def test_main_checkout_prepares_task_branch_without_force(monkeypatch):
    calls = []

    def fake_value(*args):
        return "main" if args == ("branch", "--show-current") else ""

    def fake_lines(*args):
        if args == ("status", "--porcelain"):
            return True, ["?? var/state/auto_dev_runtime.json"]
        return True, []

    def fake_run(*args):
        calls.append(args)
        code = 1 if args[0] == "show-ref" else 2 if args[0] == "ls-remote" else 0
        return SimpleNamespace(returncode=code, stdout="", stderr="")

    monkeypatch.setattr(c, "_git_value", fake_value)
    monkeypatch.setattr(c, "_git_lines", fake_lines)
    monkeypatch.setattr(c, "_run_git", fake_run)

    result = c.ensure_task_branch(
        {"task_id": "MAIL-014", "title": "decomposition", "kind": "MAIL-014-decomposition"}
    )

    assert result["ok"] is True
    assert result["branch"] == "feat/MAIL-014-decomposition"
    assert ("switch", "-c", "feat/MAIL-014-decomposition") in calls
    assert not any("-f" in arg or "--force" in arg for call in calls for arg in call)


def test_diff_gate_reads_actual_git_diff_and_blocks_policy_file(monkeypatch):
    monkeypatch.setattr(c, "NONINTERACTIVE", True)

    def fake_lines(*args):
        if args == ("diff", "--name-only", "origin/main...HEAD"):
            return True, ["docs/project/RULES.md"]
        return True, []

    monkeypatch.setattr(c, "_git_lines", fake_lines)
    result = c._default_phase_runner(
        {"task_id": "MAIL-012", "kind": "implementation"},
        "DIFF_GATE",
        {"base_sha": "base"},
    )

    assert result["code"] == "TASK_KIND_SCOPE_VIOLATION"
    assert result["changed_files"] == ["docs/project/RULES.md"]


def test_implementation_blocks_rules_env_and_credential_files():
    for path in ("docs/project/RULES.md", ".env", ".env.production", "config/service_credentials.json"):
        result = c.validate_changed_files("implementation", [path])
        assert result["code"] == "TASK_KIND_SCOPE_VIOLATION", path


def test_current_task_md_selection_matches_active_then_ready_contract(capsys):
    content = c.TOP_TASK_PATH.read_text(encoding="utf-8")
    tasks = c.parse_top_level_tasks(content)
    expected = next((task for task in tasks if task["status"] == "ACTIVE"), None)
    expected = expected or next((task for task in tasks if task["status"] == "READY"), None)
    selected = c.select_task()
    print(f"TASK.md controller selection: {selected['task_id'] if selected else 'NONE'}")
    assert selected is not None
    assert expected is not None
    assert selected["task_id"] == expected["task_id"]


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

    def agent_runner(task, phase, state):
        if phase == "IMPLEMENT":
            return {"ok": False, "code": "AGENT_UNAVAILABLE", "reason": "test transient"}
        return {"ok": True}

    monkeypatch.setattr(c, "save_checkpoint", capture)
    result = c.run_controller(
        source_text=(
            "[~] ACTIVE-001 | kind=implementation active task\n"
            "[ ] READY-002 | kind=implementation another task"
        ),
        checkpoint_path=checkpoint,
        phase_runner=agent_runner,
    )

    assert any(state.get("status") == "AWAITING_AGENT" for state in snapshots)
    assert result["status"] == "BLOCKED"
    assert result["code"] == "AGENT_UNAVAILABLE"
    assert result["task_id"] == "ACTIVE-001"
