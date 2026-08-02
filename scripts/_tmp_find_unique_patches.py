#!/usr/bin/env python3
"""Find cherry+ commits whose patch is not reverse-applicable on main."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if (Path(__file__).name != "find_unique_patches.py") else Path.cwd()
if not (ROOT / ".git").exists() and (Path.cwd() / ".git").exists():
    ROOT = Path.cwd()


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    code, out = run(["git", "branch", "-r", "--format=%(refname:short)"])
    branches: list[str] = []
    for ln in out.splitlines():
        b = ln.strip()
        if not b or b.endswith("/HEAD") or b in ("origin/main", "origin/HEAD"):
            continue
        if b.startswith("origin/backup/") or b.startswith("origin/archive/"):
            continue
        branches.append(b)

    unique: list[dict] = []
    already: list[tuple[str, str, str]] = []
    empty: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for b in branches:
        _, cherry = run(["git", "cherry", "-v", "origin/main", b])
        for ln in cherry.splitlines():
            if not ln.startswith("+ "):
                continue
            parts = ln.split(None, 2)
            if len(parts) < 2:
                continue
            sha = parts[1]
            if sha in seen:
                continue
            seen.add(sha)
            msg = parts[2] if len(parts) > 2 else ""
            code, patch = run(["git", "show", "--binary", "--format=", sha])
            if code != 0 or not patch.strip():
                empty.append((sha, b, msg))
                continue
            with tempfile.NamedTemporaryFile(
                "w", delete=False, suffix=".patch", encoding="utf-8", errors="replace"
            ) as f:
                f.write(patch)
                path = f.name
            try:
                code_rev, out_rev = run(["git", "apply", "--reverse", "--check", path])
                if code_rev == 0:
                    already.append((sha, b, msg))
                    continue
                code_fwd, out_fwd = run(["git", "apply", "--check", path])
                unique.append(
                    {
                        "sha": sha,
                        "branch": b,
                        "msg": msg,
                        "forward_applies": code_fwd == 0,
                        "reverse_err": out_rev.strip()[:400],
                        "forward_err": out_fwd.strip()[:400] if code_fwd else "",
                    }
                )
            finally:
                os.unlink(path)

    print(f"TOTAL_PLUS_UNIQUE_SHA={len(seen)}")
    print(f"ALREADY_ON_MAIN_REVERSE_OK={len(already)}")
    print(f"TRULY_MISSING_OR_DRIFTED={len(unique)}")
    print(f"EMPTY_PATCH={len(empty)}")
    print("==== TRULY MISSING / NEEDS REVIEW ====")
    for u in unique:
        print(
            f"{u['sha'][:12]} | fwd={u['forward_applies']} | {u['branch']} | {u['msg'][:100]}"
        )
    if unique:
        print("==== DETAILS ====")
        for u in unique:
            print("---", u["sha"], u["msg"][:80])
            print("reverse:", u["reverse_err"][:200].replace("\n", " | "))
            if not u["forward_applies"]:
                print("forward:", u["forward_err"][:200].replace("\n", " | "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
