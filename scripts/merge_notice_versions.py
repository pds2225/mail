from __future__ import annotations
import json, sys
from pathlib import Path

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
            if key in local: out[key] = local[key]
    rv, lv = int(remote.get("version", 0) or 0), int(local.get("version", 0) or 0)
    if lv > rv or (lv == rv and str(local.get("last_delivered_at") or "") >= str(remote.get("last_delivered_at") or "")):
        for key in ("version", "delivery_id", "delivered_hash", "delivered_snapshot", "last_delivered_at", "change_type"):
            if key in local: out[key] = local[key]
    return out

def main() -> int:
    if len(sys.argv) != 3: return 2
    remote_path, local_path = map(Path, sys.argv[1:])
    remote, local = load(remote_path), load(local_path)
    for iid, record in local.items():
        if isinstance(record, dict): remote[str(iid)] = merge_record(remote.get(str(iid), {}), record)
    remote_path.parent.mkdir(parents=True, exist_ok=True)
    remote_path.write_text(json.dumps(remote, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
