#!/usr/bin/env python3
"""Read-only detector for contradictory group keyword, region, and type rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _key(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _group_keywords(group: dict) -> set[str]:
    values = list(group.get("or_keywords") or []) + list(group.get("priority_keywords") or [])
    values += [keyword for row in group.get("and_keyword_groups") or [] for keyword in (row or [])]
    return {normalized for value in values if (normalized := _key(value))}


def _regions(group: dict) -> set[str]:
    conditions = group.get("required_conditions") or {}
    values = conditions.get("regions", []) if isinstance(conditions, dict) else []
    return {_key(value) for value in values if _key(value)}


def _types(group: dict) -> set[str]:
    return {_key(value) for value in group.get("support_types") or [] if _key(value)}


def find_conflicts(groups: list[dict]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for i, left in enumerate(groups):
        for right in groups[i + 1:]:
            lid, rid = str(left.get("id") or "?"), str(right.get("id") or "?")
            included_left, included_right = _group_keywords(left), _group_keywords(right)
            excluded_left = {_key(value) for value in left.get("exclude_keywords") or [] if _key(value)}
            excluded_right = {_key(value) for value in right.get("exclude_keywords") or [] if _key(value)}
            for keyword in sorted((included_left & excluded_right) | (included_right & excluded_left)):
                findings.append({"kind": "include_exclude", "groups": f"{lid},{rid}", "rule": keyword})

            shared = included_left & included_right
            if not shared:
                continue
            left_regions, right_regions = _regions(left), _regions(right)
            if left_regions and right_regions and not left_regions.intersection(right_regions):
                findings.append({"kind": "region_conflict", "groups": f"{lid},{rid}",
                                 "rule": ",".join(sorted(shared))})
            left_types, right_types = _types(left), _types(right)
            if left_types and right_types and not left_types.intersection(right_types):
                findings.append({"kind": "support_type_conflict", "groups": f"{lid},{rid}",
                                 "rule": ",".join(sorted(shared))})
    return findings


def _load_groups(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    groups = value.get("groups", value) if isinstance(value, dict) else value
    if isinstance(groups, dict):
        return [dict(group, id=group.get("id") or key) for key, group in groups.items() if isinstance(group, dict)]
    if isinstance(groups, list):
        return [group for group in groups if isinstance(group, dict)]
    raise ValueError("groups.json must contain a group list or object")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, default=root / "config" / "groups.json")
    args = parser.parse_args()
    findings = find_conflicts(_load_groups(args.groups))
    print(json.dumps({"conflicts": findings, "count": len(findings)}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
