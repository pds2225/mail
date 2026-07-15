#!/usr/bin/env python3
"""Loop runner — TASK 프로필 분류 + 검증 골격 (Phase B Cloud Agent 연동용).

`auto_dev_queue.py`는 main의 `loops.json` + `auto_dev_executor` 경로를 사용한다.
이 모듈은 `task_profiles.json` 기반 보조 실행기로만 유지한다.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES_PATH = ROOT / "auto_dev" / "task_profiles.json"
VERIFY_SCRIPT = ROOT / "scripts" / "loop_verify.py"


@dataclass
class TaskResult:
    status: str  # DONE | FAILED | BLOCKED | AGENT_REQUIRED | SKIPPED
    reason: str
    profile: str
    verify_report: dict | None = None


def load_profiles() -> dict:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def classify_profile(task_title: str) -> tuple[str, dict]:
    data = load_profiles()
    title_lower = task_title.lower()
    best = data.get("default_profile", "doc_only")
    best_score = 0
    best_cfg: dict = data["profiles"].get(best, {})

    for name, cfg in data.get("profiles", {}).items():
        score = 0
        for kw in cfg.get("title_keywords", []):
            if kw.lower() in title_lower:
                score += len(kw)
        if score > best_score:
            best_score = score
            best = name
            best_cfg = cfg
    return best, best_cfg


def _git_diff_names() -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]


def paths_allowed(changed: list[str], profile_cfg: dict) -> tuple[bool, list[str]]:
    if profile_cfg.get("blocked"):
        return False, changed
    allowed = profile_cfg.get("allowed_path_prefixes", [])
    if not allowed:
        return False, changed
    bad: list[str] = []
    for p in changed:
        if not any(p == pref or p.startswith(pref) for pref in allowed):
            bad.append(p)
    return not bad, bad


def run_verify(tier: int, task_title: str) -> dict:
    cmd = [sys.executable, str(VERIFY_SCRIPT), "--json"]
    if tier <= 1:
        cmd.append("--quick")
    elif tier >= 3:
        cmd.append("--with-core-sources")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout.strip():
        try:
            report = json.loads(proc.stdout)
            report["all_pass"] = report.get("ok", False)
            return report
        except json.JSONDecodeError:
            pass
    return {"ok": False, "all_pass": False, "checks": [], "parse_error": proc.stderr}


def run_task(task_id: str, task_title: str) -> TaskResult:
    profile_name, profile_cfg = classify_profile(task_title)

    if profile_cfg.get("blocked"):
        return TaskResult(
            status="BLOCKED",
            reason=f"프로필 {profile_name}은 자동 실행 금지 (보호 영역)",
            profile=profile_name,
        )

    changed = _git_diff_names()
    if changed:
        ok, bad = paths_allowed(changed, profile_cfg)
        if not ok:
            return TaskResult(
                status="BLOCKED",
                reason=f"허용 경로 밖 변경: {', '.join(bad)}",
                profile=profile_name,
            )

    tier = int(profile_cfg.get("tier", 1))
    report = run_verify(tier=tier, task_title=task_title)

    v1 = next((c for c in report.get("checks", []) if c.get("id") == "V1"), None)
    if v1 and not v1.get("ok"):
        return TaskResult(
            status="BLOCKED",
            reason="검증 게이트 blocked (보호 파일)",
            profile=profile_name,
            verify_report=report,
        )

    if not changed:
        # Phase A: 구현 없이 큐 인프라만 — 에이전트 연동 대기
        return TaskResult(
            status="AGENT_REQUIRED",
            reason="코드 변경 필요 — Phase B Cloud Agent 연동 대기",
            profile=profile_name,
            verify_report=report,
        )

    if report.get("all_pass"):
        return TaskResult(
            status="DONE",
            reason="검증 통과",
            profile=profile_name,
            verify_report=report,
        )

    return TaskResult(
        status="FAILED",
        reason="검증 실패",
        profile=profile_name,
        verify_report=report,
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: loop_runner.py TASK-XXX 'task title'", file=sys.stderr)
        sys.exit(2)
    r = run_task(sys.argv[1], " ".join(sys.argv[2:]))
    print(json.dumps({"status": r.status, "reason": r.reason, "profile": r.profile}, ensure_ascii=False))
    sys.exit(0 if r.status in ("DONE", "AGENT_REQUIRED", "SKIPPED") else 1)
