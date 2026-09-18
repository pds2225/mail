from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.apply_sites_payload import apply_pending, run


def test_add_and_update(tmp_path: Path) -> None:
    sites = [
        {
            "id": "a",
            "name": "A",
            "type": "html_table",
            "url": "https://a.example",
            "enabled": True,
            "is_aggregator": False,
        }
    ]
    added = apply_pending(
        sites,
        {
            "v": 1,
            "mode": "add",
            "site": {
                "id": "b",
                "name": "B",
                "type": "html_table",
                "url": "https://b.example",
                "enabled": True,
                "is_aggregator": False,
            },
        },
    )
    assert [s["id"] for s in added] == ["a", "b"]
    updated = apply_pending(
        added,
        {
            "v": 1,
            "mode": "update",
            "site": {
                "id": "a",
                "name": "A2",
                "type": "html_table",
                "url": "https://a.example",
                "enabled": False,
                "is_aggregator": False,
            },
        },
    )
    assert updated[0]["name"] == "A2"
    assert updated[0]["enabled"] is False


def test_rejects_duplicate_url() -> None:
    sites = [
        {
            "id": "a",
            "name": "A",
            "type": "html_table",
            "url": "https://a.example/",
            "enabled": True,
            "is_aggregator": False,
        }
    ]
    with pytest.raises(ValueError, match="duplicate url"):
        apply_pending(
            sites,
            {
                "v": 1,
                "mode": "add",
                "site": {
                    "id": "b",
                    "name": "B",
                    "type": "html_table",
                    "url": "https://a.example",
                    "enabled": True,
                    "is_aggregator": False,
                },
            },
        )


def test_run_writes_sites_and_deletes_pending(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / ".apply").mkdir()
    sites = [{"id": "a", "name": "A", "type": "html_table", "url": "https://a.example", "enabled": True, "is_aggregator": False}]
    (tmp_path / "config" / "sites.json").write_text(json.dumps(sites) + "\n", encoding="utf-8")
    pending = {
        "v": 1,
        "mode": "add",
        "site": {
            "id": "b",
            "name": "B",
            "type": "html_table",
            "url": "https://b.example",
            "enabled": True,
            "is_aggregator": False,
        },
    }
    (tmp_path / ".apply" / "pending.json").write_text(json.dumps(pending) + "\n", encoding="utf-8")
    assert run(tmp_path) == "add:b"
    next_sites = json.loads((tmp_path / "config" / "sites.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in next_sites] == ["a", "b"]
    assert not (tmp_path / ".apply" / "pending.json").exists()
    assert run(tmp_path) == "skip"


def test_update_enabled_both_directions_preserves_other_sites() -> None:
    sites = [
        {
            "id": "a",
            "name": "A",
            "type": "html_table",
            "url": "https://a.example",
            "enabled": True,
            "is_aggregator": False,
            "selectors": {"row": "ul li"},
        },
        {
            "id": "b",
            "name": "B",
            "type": "html_table",
            "url": "https://b.example",
            "enabled": False,
            "is_aggregator": True,
            "note": "보존",
        },
    ]
    original_other = sites[1].copy()

    disabled = apply_pending(
        sites,
        {
            "v": 1,
            "mode": "update",
            "site": {**sites[0], "enabled": False},
        },
    )
    assert disabled[0]["enabled"] is False
    assert disabled[1] == original_other

    enabled = apply_pending(
        disabled,
        {
            "v": 1,
            "mode": "update",
            "site": {**disabled[0], "enabled": True},
        },
    )
    assert enabled[0]["enabled"] is True
    assert enabled[1] == original_other


@pytest.mark.parametrize("enabled", [None, "false", 0])
def test_rejects_non_boolean_enabled(enabled: object) -> None:
    with pytest.raises(ValueError, match="site.enabled boolean"):
        apply_pending(
            [],
            {
                "v": 1,
                "mode": "add",
                "site": {
                    "id": "a",
                    "name": "A",
                    "type": "html_table",
                    "url": "https://a.example",
                    "enabled": enabled,
                    "is_aggregator": False,
                },
            },
        )
