# -*- coding: utf-8 -*-
"""K-Startup 수집 정책(공공우선·중복종료·page 파라미터) 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.matching import kstartup_collect as kc  # noqa: E402


def test_build_list_params_uses_page_not_page_index():
    params = kc.build_list_params(page=3, clss="PBC010")
    assert params["page"] == "3"
    assert "pageIndex" not in params
    for bad in kc.forbidden_page_params():
        assert bad not in params


def test_class_plan_public_first_private_lower_cap():
    plan = kc.class_plan({
        "max_pages_public": 30,
        "max_pages_private": 10,
    })
    assert [p["clss"] for p in plan] == ["PBC010", "PBC020"]
    assert plan[0]["label"] == "공공" and plan[0]["max_pages"] == 30
    assert plan[1]["label"] == "민간" and plan[1]["max_pages"] == 10


def test_class_plan_legacy_max_pages_maps_to_public():
    plan = kc.class_plan({"max_pages": 25})
    assert plan[0]["max_pages"] == 25
    assert plan[1]["max_pages"] == kc.DEFAULT_PRIVATE_MAX_PAGES


def test_stop_on_empty_new_streak_before_max():
    # 신규0 연속 2회 → 종료 (max 미도달)
    assert kc.stop_reason_after_page(
        page=16, max_pages=30, raw_count=1, new_count=0,
        empty_new_streak=2, streak_limit=2,
    ) == "EMPTY_NEW_STREAK"
    assert kc.stop_reason_after_page(
        page=30, max_pages=30, raw_count=15, new_count=15,
        empty_new_streak=0, streak_limit=2,
    ) == "MAX_PAGES_HIT"
    assert kc.stop_reason_after_page(
        page=5, max_pages=30, raw_count=15, new_count=15,
        empty_new_streak=0, streak_limit=2,
    ) is None


def test_merge_unique_dedups_across_classes():
    collected: list[dict] = []
    seen: set[str] = set()
    _, n1 = kc.merge_unique_items(
        collected,
        [{"id": "kstartup_1", "title": "a"}, {"id": "kstartup_2", "title": "b"}],
        seen,
    )
    _, n2 = kc.merge_unique_items(
        collected,
        [{"id": "kstartup_1", "title": "a-dup"}, {"id": "kstartup_3", "title": "c"}],
        seen,
    )
    assert n1 == 2 and n2 == 1
    assert [x["id"] for x in collected] == ["kstartup_1", "kstartup_2", "kstartup_3"]


def test_sites_json_public_priority_caps():
    import json
    sites = {s["id"]: s for s in json.loads((ROOT / "config/sites.json").read_text())}
    ks = sites["kstartup"]
    assert int(ks["max_pages_public"]) >= 30
    assert int(ks["max_pages_private"]) >= 8
    assert int(ks["max_pages_public"]) > int(ks["max_pages_private"])
