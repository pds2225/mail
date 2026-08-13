#!/usr/bin/env python3
"""CI 통과 후 자동 병합 가능한 PR만 main에 merge한다 (G2 게이트).

loop_config.json 의 auto_merge.enabled 가 true 일 때만 동작한다.
보호 파일(monitor.py·streamlit_app.py)·차단 라벨·Draft·비허용 경로는 스킵한다.

Usage:
  python3 scripts/auto_merge_pr.py --pr 42
  python3 scripts/auto_merge_pr.py --pr 42 --dry-run
  python3 scripts/auto_merge_pr.py --pr 42 --base-ref origin/main
  python3 scripts/auto_merge_pr.py --head-branch feat/x --head-sha abc --event-pr 0
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_CONFIG = ROOT / "auto_dev" / "loop_config.json"
PROFILES_PATH = ROOT / "auto_dev" / "task_profiles.json"
PROTECTED = ("monitor.py", "streamlit_app.py", ".env", ".env.example")
BLOCKED_LABELS = frozenset({"needs-human", "blocked"})
PR_VIEW_FIELDS = (
    "number,title,isDraft,labels,mergeable,headRefName,baseRefName,state"
)


@dataclass
class Eligibility:
    ok: bool
    reason: str
    profile: str = ""


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=check)


def load_loop_config() -> dict:
    return json.loads(LOOP_CONFIG.read_text(encoding="utf-8"))


def load_profiles() -> dict:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        n = int(text)
    except ValueError:
        return None
    return n if n > 0 else None


def gh_json(args: list[str]) -> dict | list:
    proc = _run(["gh", *args, "--json", PR_VIEW_FIELDS])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh command failed")
    data = json.loads(proc.stdout or "null")
    if isinstance(data, list):
        return data[0] if data else {}
    return data


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    proc = _run(["git", "diff", "--name-only", f"{base_ref}...{head_ref}"])
    if proc.returncode != 0:
        proc = _run(["git", "diff", "--name-only", base_ref, head_ref])
    return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]


def _profile_rank(name: str) -> int:
    order = {"test_fix": 3, "script_safe": 2, "doc_only": 1}
    return order.get(name, 0)


def match_profile(changed: list[str], profiles: dict) -> Eligibility:
    if not changed:
        return Eligibility(False, "변경 파일 없음")

    for pf in PROTECTED:
        if pf in changed:
            return Eligibility(False, f"보호 파일 변경: {pf}")

    matches: list[tuple[str, dict]] = []
    for name, cfg in profiles.get("profiles", {}).items():
        if not cfg.get("auto_merge_eligible"):
            continue
        allowed = cfg.get("allowed_path_prefixes") or []
        if not allowed:
            continue
        bad = [p for p in changed if not any(p == pref or p.startswith(pref) for pref in allowed)]
        if not bad:
            matches.append((name, cfg))

    if not matches:
        bad_sample = ", ".join(changed[:5])
        return Eligibility(False, f"자동병합 허용 프로필 없음 (예: {bad_sample})")

    best = max(matches, key=lambda pair: _profile_rank(pair[0]))[0]
    return Eligibility(True, "eligible", profile=best)


def assess_pr(pr: dict, changed: list[str], cfg: dict) -> Eligibility:
    auto_cfg = cfg.get("auto_merge") or {}
    if not auto_cfg.get("enabled"):
        return Eligibility(False, "loop_config.auto_merge.enabled=false")

    state = str(pr.get("state") or "OPEN").upper()
    if state != "OPEN":
        return Eligibility(False, f"PR state={state}")

    if pr.get("isDraft"):
        return Eligibility(False, "Draft PR")

    labels = {str(lb.get("name", "")).lower() for lb in (pr.get("labels") or []) if isinstance(lb, dict)}
    blocked = BLOCKED_LABELS | {str(x).lower() for x in (auto_cfg.get("required_labels_absent") or [])}
    hit = sorted(labels & blocked)
    if hit:
        return Eligibility(False, f"차단 라벨: {', '.join(hit)}")

    if str(pr.get("mergeable", "")).upper() == "CONFLICTING":
        return Eligibility(False, "merge conflict")

    profiles = load_profiles()
    path_check = match_profile(changed, profiles)
    if not path_check.ok:
        return path_check

    allowed = set(auto_cfg.get("allowed_profiles") or [])
    if allowed and path_check.profile not in allowed:
        return Eligibility(False, f"프로필 {path_check.profile!r} 은 allowed_profiles 밖")

    return path_check


def merge_pr(pr_number: int, cfg: dict, *, dry_run: bool) -> int:
    auto_cfg = cfg.get("auto_merge") or {}
    method = str(auto_cfg.get("merge_method") or "squash")
    use_auto = bool(auto_cfg.get("use_github_auto_merge", True))
    fallback = bool(auto_cfg.get("fallback_direct_merge", True))

    cmd = ["gh", "pr", "merge", str(pr_number), f"--{method}"]
    if use_auto:
        cmd.append("--auto")

    if dry_run:
        print(f"[dry-run] would run: {' '.join(cmd)}")
        return 0

    proc = _run(cmd)
    if proc.returncode == 0:
        print(f"PR #{pr_number} auto-merge 요청 완료 ({method})")
        return 0

    err = (proc.stderr or proc.stdout or "").strip()
    if use_auto and fallback and "allow_auto_merge" in err.lower():
        direct = ["gh", "pr", "merge", str(pr_number), f"--{method}"]
        proc2 = _run(direct)
        if proc2.returncode == 0:
            print(f"PR #{pr_number} 직접 merge 완료 (GitHub auto-merge 미설정 → fallback)")
            return 0
        err = (proc2.stderr or proc2.stdout or err).strip()

    print(f"merge 실패: {err}", file=sys.stderr)
    return 1


def resolve_pr_number(
    *,
    event_pr: object = None,
    head_branch: str = "",
    head_sha: str = "",
    repo: str = "",
) -> int | None:
    """workflow_run 의 Actions pull-requests API 는 GITHUB_TOKEN 에서 404 가 난다.

    대신 이벤트 payload → `gh pr list --head` → commit associated pulls 순으로 찾는다.
    """
    found = optional_positive_int(event_pr)
    if found:
        return found

    branch = (head_branch or "").strip()
    if branch:
        proc = _run([
            "gh", "pr", "list",
            "--head", branch,
            "--base", "main",
            "--state", "open",
            "--json", "number",
        ])
        if proc.returncode == 0:
            try:
                rows = json.loads(proc.stdout or "[]")
            except json.JSONDecodeError:
                rows = []
            if isinstance(rows, list) and rows:
                n = optional_positive_int((rows[0] or {}).get("number"))
                if n:
                    return n

    sha = (head_sha or "").strip()
    repo = (repo or os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if sha and repo:
        proc = _run([
            "gh", "api",
            f"repos/{repo}/commits/{sha}/pulls",
            "-H", "Accept: application/vnd.github+json",
        ])
        if proc.returncode == 0:
            try:
                rows = json.loads(proc.stdout or "[]")
            except json.JSONDecodeError:
                rows = []
            if isinstance(rows, list) and rows:
                n = optional_positive_int((rows[0] or {}).get("number"))
                if n:
                    return n
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-merge eligible PRs after CI")
    parser.add_argument("--pr", default=None, help="PR number (optional if head-branch/sha given)")
    parser.add_argument("--event-pr", default="", help="workflow_run.pull_requests[0].number")
    parser.add_argument("--head-branch", default="", help="workflow_run.head_branch")
    parser.add_argument("--head-sha", default="", help="workflow_run.head_sha")
    parser.add_argument("--repo", default="", help="owner/name (default GITHUB_REPOSITORY)")
    parser.add_argument("--base-ref", default="origin/main", help="Diff base ref")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pr_number = optional_positive_int(args.pr) or resolve_pr_number(
        event_pr=args.event_pr,
        head_branch=args.head_branch,
        head_sha=args.head_sha,
        repo=args.repo,
    )
    if not pr_number:
        print("PR 번호 없음 — skip")
        return 0

    cfg = load_loop_config()
    pr = gh_json(["pr", "view", str(pr_number)])
    if not pr.get("headRefName"):
        print("head ref 없음", file=sys.stderr)
        return 1

    _run(["git", "fetch", "origin", f"pull/{pr_number}/head:pr-{pr_number}"], check=False)
    files = changed_files(args.base_ref, f"pr-{pr_number}")
    verdict = assess_pr(pr, files, cfg)
    print(f"PR #{pr_number} profile={verdict.profile or '-'} → {verdict.reason}")
    if not verdict.ok:
        return 0

    return merge_pr(pr_number, cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
