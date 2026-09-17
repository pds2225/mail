"""Auto Dev Controller — TASK.md 단일원본·무인 재개·정책 범위 게이트.

이 파일은 최상위 TASK 선택과 phase/checkpoint 제어만 담당한다.
MAIL-014 분해 작업의 하위 TASK 실행은 기존 auto_dev_queue.main()에 위임한다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
TOP_TASK_PATH = ROOT / "TASK.md"
TASKS_PATH = ROOT / "docs" / "project" / "TASKS.md"
CHECKPOINT_PATH = ROOT / "var" / "state" / "auto_dev_runtime.json"

CHECKPOINT_FIELDS = frozenset(
    {
        "task_id",
        "status",
        "branch",
        "phase",
        "attempt",
        "last_completed_phase",
        "base_sha",
        "head_sha",
        "last_error",
    }
)

PHASES = (
    "SELECT_TASK",
    "PRECHECK",
    "BRANCH_READY",
    "IMPLEMENT",
    "FOCUSED_TEST",
    "COMPILE",
    "FULL_TEST",
    "DIFF_GATE",
    "DRY_RUN_GATE",
    "CREATE_PR",
    "MERGE_GATE",
    "AUTO_MERGE",
    "VERIFY_MAIN",
    "DONE",
)
ALLOWED_STATUSES = frozenset({
    "READY", "ACTIVE", "RETRY", "AWAITING_AGENT", "DONE", "BLOCKED",
})
NONINTERACTIVE = os.environ.get("AUTO_DEV_NONINTERACTIVE", "true").strip().lower() == "true"

POLICY_PREFIXES = (
    ".github/workflows/",
    "scripts/auto_dev_",
    "tests/test_auto_",
    "var/state/auto_dev_runtime.json",
)
IMPLEMENTATION_BLOCKED_PREFIXES = (
    ".github/workflows/",
    "scripts/auto_dev_",
    "auto_dev/",
    "TASK.md",
    "docs/project/TASKS.md",
    "docs/project/RULES.md",
    "AGENTS.md",
    ".env",
)


def _normalise_path(path: str) -> str:
    value = str(path or "").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _task_detail(content: str, task_id: str) -> str:
    lines = content.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(task_id)}\s*$", line.strip(), re.IGNORECASE):
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def infer_task_kind(task_id: str, title: str, detail: str = "") -> str:
    """TASK.md의 제목/상세만으로 작업 종류를 판정한다."""
    text = f"{task_id} {title} {detail}".lower()
    explicit = re.search(r"\bkind\s*=\s*([a-z0-9_-]+)\b", text, re.IGNORECASE)
    if explicit:
        value = explicit.group(1).lower()
        if value in {"implementation", "policy", "workflow", "documentation"}:
            return value
        if value in {"mail-014-decomposition", "decomposition"}:
            return "MAIL-014-decomposition"

    if (
        "mail-014" in text
        and (
            "decomposition" in text
            or "154개" in text
            or "분해" in text
            or "mail014_ai_task_spec.md" in text
        )
    ):
        return "MAIL-014-decomposition"
    if any(word in text for word in ("controller", "하드닝", "정책", "무인", "workflow", "자동개발")):
        return "policy"
    if any(word in text for word in ("workflow", "action")):
        return "workflow"
    if any(word in text for word in ("readme", "문서", "documentation")):
        return "documentation"
    if task_id.upper().startswith("MAIL-") or any(
        word in text for word in ("구현", "수정", "버그", "기능", "개선", "고친다")
    ):
        return "implementation"
    return ""


def parse_top_level_tasks(content: str) -> list[dict]:
    """루트 TASK.md의 LIST만 파싱한다."""
    tasks: list[dict] = []
    for line in content.splitlines():
        match = re.match(r"^\[([ ~])\]\s+([A-Za-z0-9_-]+)\s+\|\s+(.+?)\s*$", line)
        if not match:
            continue
        marker, task_id, title = match.groups()
        status = "ACTIVE" if marker == "~" else "READY" if marker == " " else ""
        if not status:
            continue
        detail = _task_detail(content, task_id)
        tasks.append(
            {
                "task_id": task_id,
                "title": title,
                "status": status,
                "kind": infer_task_kind(task_id, title, detail),
                "line": line.strip(),
                "source": "TASK.md",
            }
        )
    return tasks


def select_task(source_text: str | None = None) -> dict | None:
    """ACTIVE 1건을 우선 재개하고, 없으면 첫 READY를 선택한다.

    최상위 선택에서는 TASK.md 외의 큐·시트·이슈·PR을 읽지 않는다.
    """
    content = TOP_TASK_PATH.read_text(encoding="utf-8") if source_text is None else source_text
    tasks = parse_top_level_tasks(content)
    active = [task for task in tasks if task["status"] == "ACTIVE"]
    if len(active) > 1:
        return {
            "status": "BLOCKED",
            "code": "MULTIPLE_ACTIVE_TASKS",
            "reason": "TASK.md에 ACTIVE 작업이 2건 이상입니다.",
            "source": "TASK.md",
        }
    selected = active[0] if active else next(
        (task for task in tasks if task["status"] == "READY"), None
    )
    if selected is None:
        return None
    if not selected["kind"]:
        return {
            **selected,
            "status": "BLOCKED",
            "code": "TASK_KIND_AMBIGUOUS",
            "reason": "TASK.md 제목/상세에서 kind를 판정할 수 없습니다.",
        }
    return selected


def validate_changed_files(task_kind: str, changed_files: list[str]) -> dict:
    """작업 종류에 맞지 않는 파일 변경을 즉시 차단한다."""
    paths = [_normalise_path(path) for path in changed_files if _normalise_path(path)]
    if task_kind in {"implementation", "MAIL-014-decomposition"}:
        violations = [
            path
            for path in paths
            if (
                any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in IMPLEMENTATION_BLOCKED_PREFIXES)
                or path == ".env"
                or path.startswith(".env.")
                or re.search(r"(?:secret|credential|credentials|token|password|\.pem$|\.key$)", path, re.IGNORECASE)
            )
        ]
        if violations:
            return {
                "ok": False,
                "code": "TASK_KIND_SCOPE_VIOLATION",
                "reason": f"implementation 작업의 정책 파일 변경: {violations}",
            }
        return {"ok": True, "code": "SCOPE_OK", "reason": "implementation 범위 확인"}
    if task_kind == "policy":
        violations = [
            path
            for path in paths
            if not any(path.startswith(prefix) for prefix in POLICY_PREFIXES)
        ]
        if violations:
            return {
                "ok": False,
                "code": "TASK_KIND_SCOPE_VIOLATION",
                "reason": f"policy 작업의 허용 범위 밖 변경: {violations}",
            }
        return {"ok": True, "code": "SCOPE_OK", "reason": "policy 범위 확인"}
    if task_kind == "workflow":
        violations = [path for path in paths if not path.startswith(".github/workflows/")]
        if violations:
            return {
                "ok": False,
                "code": "TASK_KIND_SCOPE_VIOLATION",
                "reason": f"workflow 작업의 허용 범위 밖 변경: {violations}",
            }
        return {"ok": True, "code": "SCOPE_OK", "reason": "workflow 범위 확인"}
    if task_kind == "documentation":
        violations = [
            path
            for path in paths
            if not (path.endswith(".md") or path.startswith("docs/"))
        ]
        if violations:
            return {
                "ok": False,
                "code": "TASK_KIND_SCOPE_VIOLATION",
                "reason": f"documentation 작업의 허용 범위 밖 변경: {violations}",
            }
        return {"ok": True, "code": "SCOPE_OK", "reason": "documentation 범위 확인"}
    return {
        "ok": False,
        "code": "TASK_KIND_AMBIGUOUS",
        "reason": "작업 kind가 없어 안전한 변경 범위를 정할 수 없습니다.",
    }


def load_checkpoint(path: Path = CHECKPOINT_PATH) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in CHECKPOINT_FIELDS if key in value}


def save_checkpoint(state: dict, path: Path = CHECKPOINT_PATH) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = {key: state.get(key, "") for key in CHECKPOINT_FIELDS}
    safe["status"] = safe.get("status", "ACTIVE")
    if safe["status"] not in ALLOWED_STATUSES:
        safe["status"] = "BLOCKED"
        safe["last_error"] = "INVALID_RUNTIME_STATUS"
    temporary = path.with_name(f".{path.name}.tmp")
    payload = (json.dumps(safe, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass
    return safe


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


def _git_value(*args: str) -> str:
    try:
        result = _run_git(*args)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_lines(*args: str) -> tuple[bool, list[str]]:
    try:
        result = _run_git(*args)
    except (OSError, subprocess.TimeoutExpired):
        return False, []
    if result.returncode != 0:
        return False, []
    return True, [line.strip() for line in result.stdout.splitlines() if line.strip()]


def task_branch_name(task: dict) -> str:
    task_id = re.sub(r"[^A-Za-z0-9_-]+", "-", task.get("task_id", "task")).strip("-")
    title = re.sub(r"[^A-Za-z0-9]+", "-", task.get("title", "work")).strip("-").lower()
    suffix = title[:48].strip("-") or "work"
    return f"feat/{task_id}-{suffix}"


def ensure_task_branch(task: dict, preferred_branch: str = "") -> dict:
    """main/분리 HEAD에서 TASK 전용 branch를 만들거나 안전하게 재사용한다."""
    target = preferred_branch or task_branch_name(task)
    if not re.fullmatch(r"feat/[A-Za-z0-9._/-]+", target):
        return {"ok": False, "code": "BRANCH_NAME_INVALID", "reason": target}

    upstream = _git_value("rev-parse", "--abbrev-ref", f"{target}@{{upstream}}")
    if upstream:
        counts = _git_value("rev-list", "--left-right", "--count", f"{target}...{upstream}")
        try:
            ahead, behind = (int(value) for value in counts.split())
        except (ValueError, TypeError):
            return {"ok": False, "code": "BRANCH_DIVERGENCE_UNKNOWN", "reason": target}
        if ahead and behind:
            return {
                "ok": False,
                "code": "BRANCH_DIVERGED",
                "reason": f"{target}와 {upstream}이 서로 다른 커밋을 가집니다.",
            }

    current = _git_value("branch", "--show-current")
    if current == target:
        return {"ok": True, "code": "BRANCH_READY", "branch": target}

    ok, dirty = _git_lines("status", "--porcelain")
    if not ok:
        return {"ok": False, "code": "BRANCH_STATUS_FAILED", "reason": "git status 실패"}
    if dirty:
        return {
            "ok": False,
            "code": "WORKTREE_NOT_CLEAN",
            "reason": "기존 미커밋 변경을 덮지 않기 위해 branch 전환을 중단했습니다.",
        }

    local = _run_git("show-ref", "--verify", "--quiet", f"refs/heads/{target}")
    if local.returncode == 0:
        switched = _run_git("switch", target)
    else:
        remote = _run_git("ls-remote", "--exit-code", "--heads", "origin", target)
        if remote.returncode == 0:
            switched = _run_git("switch", "--track", "-c", target, f"origin/{target}")
        else:
            switched = _run_git("switch", "-c", target)
    if switched.returncode != 0:
        reason = (switched.stderr or switched.stdout or "git switch 실패").strip()[:300]
        return {"ok": False, "code": "BRANCH_READY_FAILED", "reason": reason}
    return {"ok": True, "code": "BRANCH_READY", "branch": target}


def durable_persist(state: dict, path: Path = CHECKPOINT_PATH) -> dict:
    """checkpoint를 fsync하고 workflow에서는 현재 task branch에 즉시 보존한다."""
    safe = save_checkpoint(state, path)
    if os.environ.get("AUTO_DEV_DURABLE_PERSIST", "false").strip().lower() != "true":
        return safe
    branch = safe.get("branch") or _git_value("branch", "--show-current")
    if not branch or branch in {"main", "master"}:
        return safe
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("checkpoint path가 repo 밖입니다") from exc
    staged = _run_git("add", "--", relative)
    if staged.returncode != 0:
        raise RuntimeError((staged.stderr or "checkpoint git add 실패").strip()[:300])
    unchanged = _run_git("diff", "--cached", "--quiet", "--", relative)
    if unchanged.returncode == 0:
        return safe
    committed = _run_git("commit", "-m", "chore(auto-dev): persist runtime checkpoint [skip ci]")
    if committed.returncode != 0:
        raise RuntimeError((committed.stderr or "checkpoint commit 실패").strip()[:300])
    pushed = _run_git("push", "origin", f"HEAD:{branch}")
    if pushed.returncode != 0:
        raise RuntimeError((pushed.stderr or "checkpoint push 실패").strip()[:300])
    return safe


def actual_changed_files(base_sha: str = "") -> list[str]:
    """커밋 diff, unstaged/staged diff, untracked를 합쳐 실제 변경 전체를 반환한다."""
    committed_ok, committed = _git_lines("diff", "--name-only", "origin/main...HEAD")
    if not committed_ok and base_sha:
        committed_ok, committed = _git_lines("diff", "--name-only", f"{base_sha}...HEAD")
    if not committed_ok:
        raise RuntimeError("origin/main...HEAD 실제 diff 조회 실패")
    unstaged_ok, unstaged = _git_lines("diff", "--name-only")
    staged_ok, staged = _git_lines("diff", "--cached", "--name-only")
    untracked_ok, untracked = _git_lines("ls-files", "--others", "--exclude-standard")
    if not all((unstaged_ok, staged_ok, untracked_ok)):
        raise RuntimeError("working-tree 실제 diff 조회 실패")
    return sorted(set(committed + unstaged + staged + untracked))


def run_decomposition_queue() -> dict:
    """MAIL-014 하위 TASK 실행은 기존 큐 구현에 위임한다."""
    try:
        import auto_dev_queue

        result = auto_dev_queue.main()
        state_path = getattr(auto_dev_queue, "STATE_PATH", None)
        if result == 0 and state_path:
            try:
                queue_state = json.loads(Path(state_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                queue_state = {}
            if queue_state.get("last_result") == "AWAITING_AGENT":
                return {
                    "ok": False,
                    "code": "AGENT_UNAVAILABLE",
                    "status": "AWAITING_AGENT",
                    "reason": "하위 큐가 에이전트 슬롯을 기다리는 transient 상태입니다.",
                }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "CHILD_QUEUE_ERROR", "reason": str(exc)[:300]}
    return {
        "ok": result == 0,
        "code": "CHILD_QUEUE_PASS" if result == 0 else "CHILD_QUEUE_FAILED",
        "reason": "docs/project/TASKS.md 하위 큐를 기존 auto_dev_queue에 위임",
    }


def _default_phase_runner(task: dict, phase: str, state: dict) -> dict:
    if not NONINTERACTIVE:
        return {
            "ok": False,
            "code": "HUMAN_DECISION_REQUIRED",
            "reason": "AUTO_DEV_NONINTERACTIVE=true가 아니므로 무인 실행을 중단합니다.",
        }
    if phase == "PRECHECK":
        required = (TOP_TASK_PATH, TASKS_PATH)
        missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
        if missing:
            return {"ok": False, "code": "PRECHECK_FAILED", "reason": f"필수 파일 누락: {missing}"}
    elif phase == "BRANCH_READY":
        return ensure_task_branch(task)
    elif phase == "IMPLEMENT":
        if task["kind"] == "MAIL-014-decomposition":
            return run_decomposition_queue()
        return {
            "ok": False,
            "code": "AGENT_UNAVAILABLE",
            "reason": "결정적 controller가 직접 구현하지 않는 TASK라 에이전트 재시도를 대기합니다.",
        }
    elif phase == "DIFF_GATE":
        try:
            changed_files = actual_changed_files(state.get("base_sha", ""))
        except RuntimeError as exc:
            return {"ok": False, "code": "DIFF_READ_FAILED", "reason": str(exc)}
        result = validate_changed_files(task["kind"], changed_files)
        result["changed_files"] = changed_files
        return result
    return {"ok": True, "code": "PASS", "reason": phase}


def _phase_output(value) -> dict:
    if value is None:
        return {"ok": True, "code": "PASS", "reason": ""}
    if isinstance(value, bool):
        return {"ok": value, "code": "PASS" if value else "PHASE_FAILED", "reason": ""}
    if isinstance(value, dict):
        result = dict(value)
        if result.get("status") == "AWAITING_AGENT":
            result["ok"] = False
            result.setdefault("code", "AGENT_UNAVAILABLE")
        result.setdefault("ok", True)
        result.setdefault("code", "PASS" if result["ok"] else "PHASE_FAILED")
        result.setdefault("reason", "")
        return result
    return {"ok": False, "code": "INVALID_PHASE_RESULT", "reason": type(value).__name__}


def run_controller(
    *,
    source_text: str | None = None,
    checkpoint_path: Path = CHECKPOINT_PATH,
    phase_runner: Callable[[dict, str, dict], dict] | None = None,
    max_attempts: int = 2,
) -> dict:
    """phase를 실행하고 중단 시 마지막 완료 phase 다음부터 재개한다."""
    selected = select_task(source_text)
    if selected is None:
        return {"status": "DONE", "code": "NO_ACTIVE_TASK", "reason": "TASK.md에 실행 대상이 없습니다."}
    if selected.get("status") == "BLOCKED":
        state = {
            "task_id": selected.get("task_id", ""),
            "status": "BLOCKED",
            "phase": "SELECT_TASK",
            "attempt": 1,
            "last_completed_phase": "",
            "last_error": selected.get("reason", ""),
            "code": selected.get("code", "TASK_SELECTION_BLOCKED"),
        }
        return save_checkpoint(state, checkpoint_path)

    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint.get("task_id") == selected["task_id"] and checkpoint.get("status") in {
        "ACTIVE", "RETRY", "AWAITING_AGENT",
    }:
        last_completed = checkpoint.get("last_completed_phase", "")
        try:
            start_index = PHASES.index(last_completed) + 1 if last_completed else 0
        except ValueError:
            return save_checkpoint(
                {
                    **checkpoint,
                    "task_id": selected["task_id"],
                    "status": "BLOCKED",
                    "code": "CHECKPOINT_INVALID",
                    "last_error": f"알 수 없는 last_completed_phase: {last_completed}",
                },
                checkpoint_path,
            )
        attempts_by_phase = {}
        if checkpoint.get("status") in {"RETRY", "AWAITING_AGENT"} and checkpoint.get("phase"):
            attempts_by_phase[checkpoint["phase"]] = int(checkpoint.get("attempt", 0) or 0)
        if checkpoint.get("last_completed_phase") and checkpoint.get("branch"):
            restored = ensure_task_branch(selected, checkpoint["branch"])
            if not restored.get("ok"):
                return save_checkpoint(
                    {
                        **checkpoint,
                        "task_id": selected["task_id"],
                        "status": "BLOCKED",
                        "phase": checkpoint.get("phase", "BRANCH_READY"),
                        "last_error": f"{restored.get('code')}: {restored.get('reason')}",
                    },
                    checkpoint_path,
                )
    else:
        start_index = 0
        attempts_by_phase = {}

    runner = phase_runner or _default_phase_runner
    state = {
        **checkpoint,
        "task_id": selected["task_id"],
        "task_title": selected["title"],
        "task_kind": selected["kind"],
        "status": "ACTIVE",
        "branch": checkpoint.get("branch") or _git_value("branch", "--show-current"),
        "base_sha": checkpoint.get("base_sha") or _git_value("rev-parse", "origin/main"),
        "head_sha": checkpoint.get("head_sha") or _git_value("rev-parse", "HEAD"),
        "attempts_by_phase": attempts_by_phase,
        "last_error": "",
    }

    for index in range(start_index, len(PHASES)):
        phase = PHASES[index]
        attempts = int(attempts_by_phase.get(phase, 0) or 0)
        while attempts < max_attempts:
            attempts += 1
            state.update({"status": "ACTIVE", "phase": phase, "attempt": attempts})
            save_checkpoint(state, checkpoint_path)
            try:
                result = _phase_output(runner(selected, phase, dict(state)))
                if phase == "IMPLEMENT" and result.get("ok"):
                    scope = validate_changed_files(
                        selected["kind"], list(result.get("changed_files") or []),
                    )
                    if not scope["ok"]:
                        result = scope
                if result.get("ok"):
                    attempts_by_phase[phase] = attempts
                    if phase == "BRANCH_READY" and result.get("branch"):
                        state["branch"] = result["branch"]
                    state["head_sha"] = _git_value("rev-parse", "HEAD") or state.get("head_sha", "")
                    state.update(
                        {
                            "status": "ACTIVE",
                            "last_completed_phase": phase,
                            "last_error": "",
                            "attempts_by_phase": attempts_by_phase,
                        }
                    )
                    durable_persist(state, checkpoint_path)
                    break
                error = f"{result.get('code')}: {result.get('reason')}"
            except KeyboardInterrupt:
                state.update(
                    {
                        "status": "ACTIVE",
                        "last_error": "PROCESS_INTERRUPTED",
                        "attempts_by_phase": attempts_by_phase,
                    }
                )
                return save_checkpoint(state, checkpoint_path)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {str(exc)[:300]}"

            attempts_by_phase[phase] = attempts
            agent_unavailable = error.startswith("AGENT_UNAVAILABLE:")
            state.update(
                {
                    "status": (
                        "AWAITING_AGENT"
                        if agent_unavailable and attempts < max_attempts
                        else "RETRY"
                        if attempts < max_attempts
                        else "BLOCKED"
                    ),
                    "last_error": error,
                    "attempts_by_phase": attempts_by_phase,
                    "code": (
                        "AGENT_UNAVAILABLE"
                        if agent_unavailable and attempts < max_attempts
                        else "PHASE_RETRY"
                        if attempts < max_attempts
                        else "AGENT_UNAVAILABLE"
                        if agent_unavailable
                        else "PHASE_RETRY_EXHAUSTED"
                    ),
                }
            )
            save_checkpoint(state, checkpoint_path)
            if attempts >= max_attempts:
                return state
        else:
            return state

    state.update(
        {
            "status": "DONE",
            "phase": "DONE",
            "last_completed_phase": "DONE",
            "attempt": int(attempts_by_phase.get("DONE", 0) or 0),
            "last_error": "",
            "attempts_by_phase": attempts_by_phase,
        }
    )
    return save_checkpoint(state, checkpoint_path)


def main() -> int:
    result = run_controller()
    status = result.get("status")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if status in {"DONE", "BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
