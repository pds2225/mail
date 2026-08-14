#!/usr/bin/env python3
"""CI 통과 후 PR을 main에 squash-merge한다. 자동 머지가 기본이다.

loop_config.json 의 auto_merge.enabled 가 true 일 때만 동작한다.
예외(opt-out): Draft, needs-human/blocked, merge conflict, .env* .
monitor.py / streamlit_app.py 변경도 기본 병합한다.

Usage:
  python3 scripts/auto_merge_pr.py --pr 42
  python3 scripts/auto_merge_pr.py --pr 42 --dry-run
  python3 scripts/auto_merge_pr.py --pr 42 --base-ref origin/main
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_CONFIG = ROOT / "auto_dev" / "loop_config.json"
PROFILES_PATH = ROOT / "auto_dev" / "task_profiles.json"
# Secret/env files never auto-merge. App files (monitor.py, streamlit_app.py)
# are eligible — auto-merge is the default for all work.
SECRET_FILES = (".env", ".env.local", ".env.example")
CORE_FILES = ("monitor.py", "streamlit_app.py")
BLOCKED_LABELS = frozenset({"needs-human", "blocked"})


@dataclass
class Eligibility:
    ok: bool
    reason: str
    profile: str = ""


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=check)


def resolve_pr_number(
    *,
    payload_pr: str = "",
    head_branch: str = "",
    head_sha: str = "",
    runner=None,
) -> str:
    """Resolve PR number without GET /actions/runs/{id}/pull-requests.

    That endpoint 404s from workflow_run jobs even with actions:read
    (runs 31662894294, 31660656278). Prefer the workflow_run payload, then
    ``gh pr list`` by branch / SHA. Empty string means skip, not fail.
    """
    run = runner or _run
    payload = str(payload_pr or "").strip()
    if payload.isdigit():
        return payload

    branch = str(head_branch or "").strip()
    if branch:
        proc = run(
            [
                "gh", "pr", "list", "--state", "open", "--head", branch,
                "--json", "number", "--jq", ".[0].number // empty",
            ]
        )
        num = (proc.stdout or "").strip()
        if num.isdigit():
            return num

    sha = str(head_sha or "").strip()
    if sha:
        proc = run(
            [
                "gh", "pr", "list", "--state", "open", "--search", sha,
                "--json", "number", "--jq", ".[0].number // empty",
            ]
        )
        num = (proc.stdout or "").strip()
        if num.isdigit():
            return num

    return ""


def load_loop_config() -> dict:
    return json.loads(LOOP_CONFIG.read_text(encoding="utf-8"))


def load_profiles() -> dict:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


def gh_json(args: list[str]) -> dict | list:
    proc = _run(["gh", *args, "--json", "number,title,isDraft,labels,mergeable,headRefName,baseRefName"])
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
    order = {
        "test_fix": 3,
        "script_safe": 2,
        "config_data": 2,
        "accuracy": 2,
        "doc_only": 1,
        "core_logic": 0,
        "default": 0,
    }
    return order.get(name, 0)


def _secret_hits(changed: list[str]) -> list[str]:
    hits: list[str] = []
    for path in changed:
        name = Path(path).name
        if path in SECRET_FILES or name in SECRET_FILES:
            hits.append(path)
    return hits


def _covers(changed: list[str], prefixes: list[str]) -> bool:
    if not prefixes:
        return False
    return all(
        any(path == pref or path.startswith(pref) for pref in prefixes)
        for path in changed
    )


def _profile_opted_out(name: str, spec: dict) -> Eligibility | None:
    if spec.get("blocked") or spec.get("auto_merge_eligible") is False:
        return Eligibility(False, f"프로필 {name!r} 은 자동병합 제외", profile=name)
    return None


def match_profile(changed: list[str], profiles: dict) -> Eligibility:
    """Classify changed files. Eligible by default unless secrets or a profile opts out."""
    if not changed:
        return Eligibility(False, "변경 파일 없음")

    secrets = _secret_hits(changed)
    if secrets:
        return Eligibility(False, f"secret file: {', '.join(secrets)}")

    specs = profiles.get("profiles") or {}
    matches: list[tuple[str, dict]] = []
    for name, cfg in specs.items():
        prefixes = cfg.get("allowed_path_prefixes") or []
        if _covers(changed, prefixes):
            matches.append((name, cfg))

    if matches:
        best, spec = max(matches, key=lambda pair: _profile_rank(pair[0]))
        opted = _profile_opted_out(best, spec)
        if opted:
            return opted
        return Eligibility(True, "eligible", profile=best)

    profile = "core_logic" if any(path in CORE_FILES for path in changed) else "default"
    opted = _profile_opted_out(profile, specs.get(profile) or {})
    if opted:
        return opted
    return Eligibility(True, "eligible", profile=profile)


def assess_pr(pr: dict, changed: list[str], cfg: dict) -> Eligibility:
    auto_cfg = cfg.get("auto_merge") or {}
    if not auto_cfg.get("enabled"):
        return Eligibility(False, "loop_config.auto_merge.enabled=false")

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-merge eligible PRs after CI")
    parser.add_argument("--pr", type=int, default=0, help="PR number")
    parser.add_argument("--base-ref", default="origin/main", help="Diff base ref")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--print-pr-number",
        action="store_true",
        help="Resolve PR number from workflow_run payload/branch/SHA and print number=<n>",
    )
    parser.add_argument("--payload-pr", default="", help="github.event.workflow_run.pull_requests[0].number")
    parser.add_argument("--head-branch", default="", help="workflow_run.head_branch")
    parser.add_argument("--head-sha", default="", help="workflow_run.head_sha")
    args = parser.parse_args(argv)

    if args.print_pr_number:
        num = resolve_pr_number(
            payload_pr=args.payload_pr,
            head_branch=args.head_branch,
            head_sha=args.head_sha,
        )
        print(f"number={num}")
        return 0

    if not args.pr:
        print("--pr 또는 --print-pr-number 가 필요합니다", file=sys.stderr)
        return 1

    cfg = load_loop_config()
    pr = gh_json(["pr", "view", str(args.pr)])
    head = f"origin/{pr.get('headRefName') or ''}"
    if not pr.get("headRefName"):
        print("head ref 없음", file=sys.stderr)
        return 1

    _run(["git", "fetch", "origin", f"pull/{args.pr}/head:pr-{args.pr}"], check=False)
    files = changed_files(args.base_ref, f"pr-{args.pr}")
    verdict = assess_pr(pr, files, cfg)
    print(f"PR #{args.pr} profile={verdict.profile or '-'} → {verdict.reason}")
    if not verdict.ok:
        return 0

    return merge_pr(args.pr, cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
