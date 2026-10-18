"""Shared support-type vocabulary loaded from config/support_types.json."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def support_type_rules() -> dict[str, tuple[str, ...]]:
    path = Path(__file__).resolve().parents[2] / "config" / "support_types.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = data.get("지원유형")
    if not isinstance(rules, dict) or not rules:
        raise ValueError("config/support_types.json must define non-empty 지원유형")
    return {str(name): tuple(str(alias) for alias in aliases if str(alias).strip())
            for name, aliases in rules.items()}


def classify_support_types(text: object) -> list[str]:
    normalized = str(text or "").lower()
    if not normalized:
        return []
    def contains(alias: str) -> bool:
        needle = alias.lower()
        if re.search(r"[a-z0-9]", needle):
            return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", normalized))
        return needle in normalized

    return [name for name, aliases in support_type_rules().items()
            if any(contains(alias) for alias in aliases)]


def map_category_to_support_types(text: object) -> list[str]:
    return classify_support_types(text)
