#!/usr/bin/env python3
"""Audit remotes/worktrees/stashes for development not yet on main.

Classifies leftover refs after squash merges:
- SKIP_NOISE: backup/*, archive/*
- MISSING_REF: listed but unresolvable
- CONTENT_ON_MAIN: cherry all equivalent, or no unique tip files vs main
- UNIQUE_CANDIDATE: cherry '+' commits AND tip still has paths with content
  not present on main (heuristic: new test/module file missing on main)

Usage:
  python3 scripts/outstanding_dev_audit.py
  python3 scripts/outstanding_dev_audit.py --json
  python3 scripts/outstanding_dev_audit.py --strict   # exit 1 if UNIQUE_CANDIDATE
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PREFIXES = ("origin/backup/", "origin/archive/", "backup/", "archive/")
# Old branch tips often touch these; later squash merges relocated/renamed coverage.
SUPERSEDED_PROD_PATHS = frozenset(
    {
        "monitor.py",
        "streamlit_app.py",
        "groups.json",
        "scoring.py",
        "config/groups.json",
    }
)
MAIN_FP_SUITE_MARKERS = (
    "tests/test_digest_fp_hardening.py",
    "tests/test_prestartup_ai_digest_regression.py",
    "tests/test_nonnotice_title_filter.py",
    "tests/test_report_format.py",
)


def _run(args: list[str], *, cwd: Path = ROOT) -> tuple[int, str]:
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as e:
        return 1, str(e)
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode, out.strip()


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def is_noise_ref(ref: str) -> bool:
    r = ref.replace("refs/remotes/", "").replace("refs/heads/", "")
    if not r.startswith("origin/") and "/" in r and not r.startswith("origin/"):
        # local branch names like archive/... still noise
        pass
    check = r if r.startswith("origin/") else f"origin/{r}" if r.startswith(("backup/", "archive/")) else r
    return any(check.startswith(p) or r.startswith(p.removeprefix("origin/")) for p in SKIP_PREFIXES)


def is_active_checkout_ref(ref: str) -> bool:
    """현재 작업 중인 PR/브랜치는 leftover UNIQUE_CANDIDATE가 아니다."""
    names: set[str] = set()
    head_ref = (os.environ.get("GITHUB_HEAD_REF") or "").strip()
    if head_ref:
        names.add(head_ref)
        names.add(f"origin/{head_ref}")
    code, cur = _run(["git", "branch", "--show-current"])
    if code == 0 and cur.strip():
        names.add(cur.strip())
        names.add(f"origin/{cur.strip()}")
    r = ref.replace("refs/remotes/", "").replace("refs/heads/", "")
    if r in names:
        return True
    head = resolve_ref("HEAD")
    tip = resolve_ref(ref)
    return bool(head and tip and head == tip)


def list_remote_branches() -> list[str]:
    code, out = _run(["git", "branch", "-r", "--format=%(refname:short)"])
    if code != 0:
        return []
    refs = []
    for ln in _lines(out):
        if ln.endswith("/HEAD") or ln == "origin/HEAD":
            continue
        if ln == "origin/main" or ln == "origin/master":
            continue
        if is_active_checkout_ref(ln):
            continue
        refs.append(ln)
    return refs


def list_worktrees() -> list[dict]:
    code, out = _run(["git", "worktree", "list", "--porcelain"])
    if code != 0:
        return []
    items: list[dict] = []
    cur: dict = {}
    for ln in out.splitlines():
        if not ln.strip():
            if cur:
                items.append(cur)
                cur = {}
            continue
        if ln.startswith("worktree "):
            cur = {"path": ln[len("worktree ") :]}
        elif ln.startswith("HEAD "):
            cur["head"] = ln[len("HEAD ") :]
        elif ln.startswith("branch "):
            cur["branch"] = ln[len("branch ") :].replace("refs/heads/", "")
    if cur:
        items.append(cur)
    return items


def list_stashes() -> list[str]:
    code, out = _run(["git", "stash", "list"])
    if code != 0 or not out:
        return []
    return _lines(out)


def resolve_ref(ref: str) -> str | None:
    code, out = _run(["git", "rev-parse", "--verify", ref])
    if code != 0:
        return None
    return out.splitlines()[0].strip() if out else None


def cherry_plus_commits(base: str, tip: str) -> list[str]:
    code, out = _run(["git", "cherry", "-v", base, tip])
    if code != 0:
        return []
    plus = []
    for ln in _lines(out):
        if ln.startswith("+ "):
            plus.append(ln)
    return plus


def tip_changed_paths(base: str, tip: str) -> list[tuple[str, str]]:
    """Return (status, path) for three-dot name-status."""
    code, out = _run(["git", "diff", "--name-status", f"{base}...{tip}"])
    if code != 0:
        return []
    rows: list[tuple[str, str]] = []
    for ln in _lines(out):
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        rows.append((status, path))
    return rows


def tip_only_paths(base: str, tip: str) -> list[str]:
    """Files added on tip side of three-dot diff (A = added)."""
    return [path for status, path in tip_changed_paths(base, tip) if status.startswith("A")]


def path_exists_on_ref(ref: str, path: str) -> bool:
    code, _ = _run(["git", "cat-file", "-e", f"{ref}:{path}"])
    return code == 0


def main_has_fp_regression_suite(base: str) -> bool:
    return any(path_exists_on_ref(base, p) for p in MAIN_FP_SUITE_MARKERS)


def tests_only_superseded(base: str, tip: str, unique_paths: list[str]) -> bool:
    """True when leftover unique paths are only tests and prod edits are superseded."""
    if not unique_paths or any(not p.startswith("tests/") for p in unique_paths):
        return False
    if not main_has_fp_regression_suite(base):
        return False
    changed = [path for _status, path in tip_changed_paths(base, tip)]
    prod = [p for p in changed if not p.startswith("tests/")]
    return all(p in SUPERSEDED_PROD_PATHS for p in prod)


def classify_ref(ref: str, *, base: str = "origin/main") -> dict:
    if is_noise_ref(ref):
        return {"ref": ref, "status": "SKIP_NOISE", "plus": [], "unique_paths": []}
    sha = resolve_ref(ref)
    if not sha:
        return {"ref": ref, "status": "MISSING_REF", "plus": [], "unique_paths": []}
    plus = cherry_plus_commits(base, ref)
    if not plus:
        return {
            "ref": ref,
            "status": "CONTENT_ON_MAIN",
            "sha": sha[:12],
            "plus": [],
            "unique_paths": [],
            "reason": "no_unique_cherry",
        }
    added = tip_only_paths(base, ref)
    unique_paths = [p for p in added if not path_exists_on_ref(base, p)]
    filtered = []
    for p in unique_paths:
        if p == "groups.json" and path_exists_on_ref(base, "config/groups.json"):
            continue
        if p.endswith(".md") and p.startswith("docs/prd/") and path_exists_on_ref(base, p):
            continue
        filtered.append(p)
    if filtered and tests_only_superseded(base, ref, filtered):
        return {
            "ref": ref,
            "status": "CONTENT_ON_MAIN",
            "sha": sha[:12],
            "plus": plus[:10],
            "unique_paths": [],
            "reason": "tests_only_superseded_by_main_fp_suites",
            "superseded_test_paths": filtered[:50],
        }
    if filtered:
        return {
            "ref": ref,
            "status": "UNIQUE_CANDIDATE",
            "sha": sha[:12],
            "plus": plus[:20],
            "unique_paths": filtered[:50],
            "reason": "cherry_plus_and_missing_paths_on_main",
        }
    return {
        "ref": ref,
        "status": "CONTENT_ON_MAIN",
        "sha": sha[:12],
        "plus": plus[:10],
        "unique_paths": [],
        "reason": "cherry_plus_but_paths_superseded_on_main",
    }


def run_audit(*, base: str = "origin/main") -> dict:
    # Ensure base resolves; fall back to main
    if not resolve_ref(base):
        base = "main" if resolve_ref("main") else "HEAD"

    remote_results = [classify_ref(r, base=base) for r in list_remote_branches()]
    worktrees = list_worktrees()
    wt_results = []
    for wt in worktrees:
        branch = wt.get("branch")
        head = wt.get("head")
        tip = f"refs/heads/{branch}" if branch else head
        if not tip:
            continue
        # Skip primary main checkout noise
        if branch == "main" or tip in ("main", "origin/main"):
            wt_results.append(
                {
                    "path": wt.get("path"),
                    "branch": branch,
                    "status": "PRIMARY_OR_MAIN",
                }
            )
            continue
        if branch:
            c = classify_ref(f"origin/{branch}" if resolve_ref(f"origin/{branch}") else branch, base=base)
        else:
            c = classify_ref(head, base=base) if head else {"status": "MISSING_REF"}
        c["path"] = wt.get("path")
        c["branch"] = branch
        wt_results.append(c)

    stashes = list_stashes()
    by_status: dict[str, int] = {}
    for r in remote_results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    unique = [r for r in remote_results if r["status"] == "UNIQUE_CANDIDATE"]
    report = {
        "ok": len(unique) == 0 and len(stashes) == 0,
        "base": base,
        "counts": by_status,
        "unique_candidates": unique,
        "remotes": remote_results,
        "worktrees": wt_results,
        "stashes": stashes,
        "user_priority_note": (
            "User-priority merge-all: only UNIQUE_CANDIDATE should be PR'd; "
            "SKIP_NOISE and CONTENT_ON_MAIN are intentional leftovers."
        ),
    }
    return report


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass

    ap = argparse.ArgumentParser(description="Audit outstanding development vs main")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 if UNIQUE_CANDIDATE or stash")
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args()
    report = run_audit(base=args.base)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[outstanding-dev-audit] base={report['base']} ok={report['ok']}")
        print(f"[outstanding-dev-audit] counts={report['counts']}")
        for u in report["unique_candidates"]:
            print(f"  UNIQUE {u['ref']} paths={u.get('unique_paths')}")
        if report["stashes"]:
            print(f"[outstanding-dev-audit] stashes={len(report['stashes'])}")
        for wt in report["worktrees"]:
            if wt.get("status") in ("UNIQUE_CANDIDATE",):
                print(f"  WT-UNIQUE {wt.get('path')} {wt.get('branch')}")
    if args.strict and not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
