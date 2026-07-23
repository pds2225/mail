#!/usr/bin/env python3
"""Merge encrypted outbox copies without exposing recipients in logs."""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import delivery_outbox  # noqa: E402


def _merge_entries(left: dict, right: dict) -> dict:
    by_id: dict[str, dict] = {}
    for entry in list(left.get("entries", [])) + list(right.get("entries", [])):
        if not isinstance(entry, dict) or not str(entry.get("id") or ""):
            continue
        key = str(entry["id"])
        current = by_id.get(key)
        if current is None:
            by_id[key] = copy.deepcopy(entry)
            continue
        current["notice_ids"] = sorted({
            *[str(v) for v in current.get("notice_ids", []) if str(v)],
            *[str(v) for v in entry.get("notice_ids", []) if str(v)],
        })
        completed = [str(v) for v in (current.get("completed_at"), entry.get("completed_at")) if v]
        if completed:
            current["recipients"] = []
            current["completed_at"] = max(completed)
        else:
            current["recipients"] = sorted({
                *[str(v).strip().lower() for v in current.get("recipients", []) if str(v).strip()],
                *[str(v).strip().lower() for v in entry.get("recipients", []) if str(v).strip()],
            })
    return {"version": 1, "entries": list(by_id.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("incoming")
    args = parser.parse_args()
    target = Path(args.target)
    merged = _merge_entries(delivery_outbox.load(target), delivery_outbox.load(args.incoming))
    delivery_outbox.save(merged, target)
    print(f"delivery_outbox merged: {len(merged['entries'])} encrypted entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
