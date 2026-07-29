# -*- coding: utf-8 -*-
"""W2: send_hold·P0 소스 제외·manual_queue 계약 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations import miss_remediation as mr  # noqa: E402


def test_effective_allow_send_hold_blocks():
    ok, reason = mr.effective_allow_send(True, send_hold=True, shadow=False, force_allow=False)
    assert ok is False and reason == "send_hold_RUN_FAILED"


def test_effective_allow_send_shadow_continues():
    ok, reason = mr.effective_allow_send(True, send_hold=True, shadow=True, force_allow=False)
    assert ok is True and "shadow" in reason


def test_effective_allow_send_override():
    ok, reason = mr.effective_allow_send(True, send_hold=True, shadow=False, force_allow=True)
    assert ok is True and "override" in reason


def test_drop_items_from_p0_sources_by_name_and_id_prefix():
    reports = [
        {"site_id": "nipa", "site_name": "정보통신산업진흥원(NIPA)", "risk_level": "P0"},
        {"site_id": "bizinfo", "site_name": "기업마당", "risk_level": ""},
    ]
    items = [
        {"id": "nipa_1", "title": "A", "source": "정보통신산업진흥원(NIPA)"},
        {"id": "bizinfo_1", "title": "B", "source": "기업마당"},
        {"id": "x", "title": "C", "source": "기타", "site_id": "nipa"},
        # 접두 없는 legacy id 는 display name 으로만 소속 판별
        {"id": "legacyNipa", "title": "D", "source": "정보통신산업진흥원(NIPA)"},
    ]
    kept, dropped = mr.drop_items_from_p0_sources(items, reports)
    assert {it["id"] for it in kept} == {"bizinfo_1"}
    assert {it["id"] for it in dropped} == {"nipa_1", "x", "legacyNipa"}


def test_drop_items_from_p0_does_not_drop_sibling_boards_with_same_name():
    """동일 display name 보드가 여러 개일 때 P0 1건이 sibling 정상 보드를 같이 지우면 안 됨.

    sites.json 에 정부24×6, 대전테크노파크×3 등 중복 name 이 있다. html_table 공고 id 는
    `{site_id}_{hash}` 형태이므로 id 접두로만 제외해야 한다.
    """
    reports = [
        {
            "site_id": "imp_0671c689",
            "site_name": "정부24",
            "risk_level": "P0",
            "reason_codes": ["FETCH_FAILED"],
        },
        {"site_id": "imp_73a18059", "site_name": "정부24", "risk_level": ""},
        {"site_id": "imp_410e209d", "site_name": "정부24", "risk_level": ""},
    ]
    items = [
        {
            "id": "imp_0671c689_aaa",
            "title": "from P0 board",
            "source": "정부24",
        },
        {
            "id": "imp_73a18059_bbb",
            "title": "healthy sibling",
            "source": "정부24",
        },
        {
            "id": "imp_410e209d_ccc",
            "title": "healthy sibling2",
            "source": "정부24",
            "site_id": "imp_410e209d",
        },
        {"id": "bizinfo_1", "title": "unrelated", "source": "기업마당"},
    ]
    kept, dropped = mr.drop_items_from_p0_sources(items, reports)
    assert {it["id"] for it in dropped} == {"imp_0671c689_aaa"}
    assert {it["id"] for it in kept} == {
        "imp_73a18059_bbb",
        "imp_410e209d_ccc",
        "bizinfo_1",
    }


def test_pbln_id_maps_to_bizinfo_instead_of_generic_underscore_fallback():
    """기업마당 실제 ID(PBLN_*)는 알려진 별칭으로 P0 bizinfo에 연결한다."""
    assert mr.item_belongs_to_p0(
        {"id": "PBLN_000000000123", "source": "기업마당"},
        p0_ids={"bizinfo"},
        p0_names={"기업마당"},
    ) is True


def test_manual_queue_enqueue_and_ack(tmp_path):
    path = tmp_path / "miss_manual_queue.json"
    reports = [
        {"site_id": "nipa", "site_name": "NIPA", "risk_level": "P0",
         "reason_codes": ["FETCH_FAILED"], "detail": {"fetch_error": "timeout"}},
        {"site_id": "ok", "site_name": "OK", "risk_level": ""},
    ]
    n = mr.enqueue_p0_from_reports(reports, path=path)
    assert n == 1
    q = mr.load_manual_queue(path)
    assert len(q["items"]) == 1
    assert q["items"][0]["status"] == "open"
    entry_id = q["items"][0]["id"]

    # 같은 사이트 재enqueue → open 1건 유지
    mr.enqueue_p0_from_reports(reports, path=path)
    q2 = mr.load_manual_queue(path)
    assert len([i for i in q2["items"] if i["status"] == "open"]) == 1

    q3 = mr.ack_manual(q2, entry_id, "false_alarm")
    mr.save_manual_queue(q3, path)
    closed = mr.load_manual_queue(path)["items"][0]
    assert closed["status"] == "closed"
    assert closed["resolution"] == "false_alarm"


def test_plan_retries_only_fetch_parser_content():
    plans = mr.plan_retries([
        {"site_id": "a", "reason_codes": ["FETCH_FAILED"], "risk_level": "P0"},
        {"site_id": "b", "reason_codes": ["ZERO_ITEMS_WITH_BASELINE"], "risk_level": "P0"},
        {"site_id": "c", "reason_codes": ["PARSER_FAILED"], "risk_level": "P0"},
    ])
    ids = {p["site_id"] for p in plans}
    assert ids == {"a", "c"}
    assert plans[0]["max_attempts"] == 2
