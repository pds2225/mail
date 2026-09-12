#!/usr/bin/env python3
"""Union two notice_versions.json maps after a GitHub push race.

Writes via atomic tmp→replace so a mid-write crash/ENOSPC cannot truncate the
on-disk file to empty/partial JSON (same hazard as the old merge_seen_ids write_text).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mail_core.storage.state_store import atomic_write_bytes  # noqa: E402


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def merge_record(remote: dict, local: dict) -> dict:
    out = dict(remote)
    if str(local.get("last_seen_at") or "") >= str(remote.get("last_seen_at") or ""):
        for key in ("list_hash", "observed_hash", "observed_snapshot", "last_seen_at", "pending_delivery_id"):
            if key in local:
                out[key] = local[key]
    rv, lv = int(remote.get("version", 0) or 0), int(local.get("version", 0) or 0)
    if lv > rv or (lv == rv and str(local.get("last_delivered_at") or "") >= str(remote.get("last_delivered_at") or "")):
        for key in ("version", "delivery_id", "delivered_hash", "delivered_snapshot", "last_delivered_at", "change_type"):
            if key in local:
                out[key] = local[key]
    return out


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    remote_path, local_path = map(Path, sys.argv[1:])
    remote, local = load(remote_path), load(local_path)
    for iid, record in local.items():
        if isinstance(record, dict):
            remote[str(iid)] = merge_record(remote.get(str(iid), {}), record)
    remote_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep prior trailing newline; atomic so truncate-on-open cannot wipe the file.
    payload = (json.dumps(remote, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write_bytes(remote_path, payload, backup=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
