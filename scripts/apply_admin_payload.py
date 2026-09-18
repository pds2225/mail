#!/usr/bin/env python3
"""Apply V1 admin web pending patches without exposing GitHub credentials to the browser."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PENDING_REL = ".apply/config-pending.json"
GROUPS_REL = "config/groups.json"
SETTINGS_REL = "config/settings.json"
FEEDBACK_REL = "data/golden/feedback_labels.jsonl"

GROUP_FIELDS = {
    "name",
    "active",
    "required_conditions",
    "or_keywords",
    "and_keyword_groups",
    "exclude_keywords",
    "support_types",
}
SETTINGS_FIELDS = {
    "date_filter_enabled",
    "days_back",
    "raw_all_enabled",
    "date_unknown_policy",
    "date_unknown_max_age_days",
    "region_unknown_mail_limit",
}
NOTICE_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-%]{1,120}$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_patch(raw: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if key in allowed}


def _apply_group(repo_root: Path, pending: dict[str, Any]) -> str:
    group_id = str(pending.get("id") or "").strip()
    patch = _pick_patch(pending.get("patch"), GROUP_FIELDS)
    if not group_id or not patch:
        raise ValueError("group id and patch are required")
    path = repo_root / GROUPS_REL
    groups = _load_json(path)
    if not isinstance(groups, list):
        raise ValueError("config/groups.json must be a list")
    found = False
    next_groups: list[Any] = []
    for item in groups:
        if isinstance(item, dict) and str(item.get("id") or "") == group_id:
            next_groups.append({**item, **patch})
            found = True
        else:
            next_groups.append(item)
    if not found:
        raise ValueError(f"group not found: {group_id}")
    path.write_text(f"{json.dumps(next_groups, ensure_ascii=False, indent=2)}\n", encoding="utf-8")
    return f"group:{group_id}"


def _apply_settings(repo_root: Path, pending: dict[str, Any]) -> str:
    patch = _pick_patch(pending.get("patch"), SETTINGS_FIELDS)
    if not patch:
        raise ValueError("settings patch is required")
    path = repo_root / SETTINGS_REL
    settings = _load_json(path)
    if not isinstance(settings, dict):
        raise ValueError("config/settings.json must be an object")
    settings.update(patch)
    path.write_text(f"{json.dumps(settings, ensure_ascii=False, indent=2)}\n", encoding="utf-8")
    return "settings"


def _load_feedback(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id"):
            rows[str(row["id"])] = row
    return rows


def _apply_review(repo_root: Path, pending: dict[str, Any]) -> str:
    # MAIL-018: 배치 저장이 기본이다("items"). 이전 단일 항목 pending 페이로드("item")도
    # 계속 처리해야 한다 — 이미 만들어진 게스트 모드 commit-url 링크가 남아있을 수 있다.
    raw_items = pending.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        single = pending.get("item")
        raw_items = [single] if isinstance(single, dict) else []
    if not raw_items:
        raise ValueError("review item is required")

    path = repo_root / FEEDBACK_REL
    rows = _load_feedback(path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    applied: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("review item is required")
        notice_id = str(item.get("id") or "").strip()
        verdict = str(item.get("verdict") or "").strip().upper()
        title = str(item.get("title") or "").strip()[:110]
        if not NOTICE_ID_RE.fullmatch(notice_id):
            raise ValueError("invalid notice id")
        if verdict not in {"O", "X"}:
            raise ValueError("verdict must be O or X")

        previous = rows.get(notice_id, {})
        rows[notice_id] = {
            **previous,
            "id": notice_id,
            "verdict": verdict,
            "tier": "C",
            "source": "dashboard-ox",
            "title": title or str(previous.get("title") or ""),
            "first_seen": previous.get("first_seen") or now,
            "last_seen": now,
        }
        applied.append(f"{verdict}:{notice_id}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(rows[key], ensure_ascii=False) for key in sorted(rows)) + "\n",
        encoding="utf-8",
    )
    if len(applied) == 1:
        return f"review:{applied[0]}"
    return f"review:{len(applied)}items"


def run(repo_root: Path) -> str:
    pending_path = repo_root / PENDING_REL
    if not pending_path.is_file():
        return "skip"
    raw = pending_path.read_text(encoding="utf-8").strip()
    if not raw:
        return "skip"
    pending = json.loads(raw)
    if not isinstance(pending, dict) or pending.get("v") != 1:
        raise ValueError("unsupported pending payload")

    resource = pending.get("resource")
    if resource == "group":
        result = _apply_group(repo_root, pending)
    elif resource == "settings":
        result = _apply_settings(repo_root, pending)
    elif resource == "review":
        result = _apply_review(repo_root, pending)
    else:
        raise ValueError(f"unknown resource: {resource}")

    pending_path.unlink()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    print(run(Path(args.repo_root).resolve()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
