#!/usr/bin/env python3
"""Append-only JSONL merge: target ← union(target, incoming) by exact line.

중복 줄은 한 번만. 순서: target 기존 → incoming 신규.
Secret/PII 검사 없음(호출측이 PII-free ledger만 넘길 것).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def merge_jsonl(target: Path, incoming: Path) -> int:
    existing: list[str] = []
    seen: set[str] = set()
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            existing.append(s)
    added = 0
    if incoming.is_file():
        for line in incoming.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            existing.append(s)
            added += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(("\n".join(existing) + ("\n" if existing else "")), encoding="utf-8")
    return added


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("incoming")
    args = p.parse_args()
    added = merge_jsonl(Path(args.target), Path(args.incoming))
    print(f"jsonl merge: +{added} lines → {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
