#!/usr/bin/env python3
"""Apply `.apply/pending.json` onto `config/sites.json`.

Vercel cannot hold a long-lived GitHub PAT. The admin UI opens GitHub's
new-file page; the repo owner clicks Commit; this script (via Actions)
merges that payload into the live sites list and deletes the pending file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PENDING_REL = ".apply/pending.json"
SITES_REL = "config/sites.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_pending(sites: list[Any], pending: dict[str, Any]) -> list[Any]:
    if pending.get("v") != 1:
        raise ValueError("unsupported pending version")
    mode = pending.get("mode")
    site = pending.get("site")
    if not isinstance(site, dict):
        raise ValueError("site object required")
    for key in ("id", "name", "type", "url"):
        if not str(site.get(key) or "").strip():
            raise ValueError(f"site.{key} required")
    url = str(site["url"]).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("site.url must be http(s)")
    site_id = str(site["id"]).strip()
    ids = [str(item.get("id")) for item in sites if isinstance(item, dict)]
    if mode == "add":
        if site_id in ids:
            raise ValueError(f"duplicate id: {site_id}")
        url_key = url.rstrip("/").lower()
        for item in sites:
            if not isinstance(item, dict):
                continue
            existing = str(item.get("url") or "").rstrip("/").lower()
            if existing == url_key:
                raise ValueError(f"duplicate url: {url}")
        return [*sites, site]
    if mode == "update":
        if site_id not in ids:
            raise ValueError(f"site not found: {site_id}")
        url_key = url.rstrip("/").lower()
        for item in sites:
            if not isinstance(item, dict) or str(item.get("id")) == site_id:
                continue
            existing = str(item.get("url") or "").rstrip("/").lower()
            if existing == url_key:
                raise ValueError(f"duplicate url: {url}")
        return [
            site if isinstance(item, dict) and str(item.get("id")) == site_id else item
            for item in sites
        ]
    raise ValueError(f"unknown mode: {mode}")


def run(repo_root: Path) -> str:
    pending_path = repo_root / PENDING_REL
    sites_path = repo_root / SITES_REL
    if not pending_path.is_file():
        return "skip"
    raw = pending_path.read_text(encoding="utf-8").strip()
    if not raw:
        return "skip"
    pending = json.loads(raw)
    if not isinstance(pending, dict) or not pending:
        return "skip"
    sites = _load(sites_path)
    if not isinstance(sites, list):
        raise ValueError("config/sites.json must be a list")
    next_sites = apply_pending(sites, pending)
    sites_path.write_text(f"{json.dumps(next_sites, ensure_ascii=False, indent=2)}\n", encoding="utf-8")
    pending_path.unlink()
    mode = pending.get("mode")
    site_id = (pending.get("site") or {}).get("id")
    return f"{mode}:{site_id}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    result = run(Path(args.repo_root).resolve())
    print(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
