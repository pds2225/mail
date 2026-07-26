# -*- coding: utf-8 -*-
"""W3/P0-B: 빈 정보 3상태 surface·가드·추출률 계약 테스트."""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
}.items():
    os.environ.setdefault(_key, _value)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations import field_status as fs  # noqa: E402
from mail_core.operations import miss_remediation as mr  # noqa: E402
import monitor as m  # noqa: E402


def test_assert_blank_states_disjoint():
    fs.assert_blank_states_disjoint()


def test_surface_labels_are_three_way():
    assert "미기재" in fs.surface_label_for_field(fs.NOT_SPECIFIED)
    assert "추출" in fs.surface_label_for_field(fs.PARSE_FAILED)
    assert "접속" in fs.surface_label_for_field(fs.DETAIL_FETCH_FAILED)
    assert fs.surface_label_for_field(fs.NOT_SPECIFIED, field="region") == "지역 제한 없음"
    assert fs.maps_to_region_unknown_bucket(fs.NOT_SPECIFIED) is False
    assert fs.maps_to_region_unknown_bucket(fs.PARSE_FAILED) is True


def test_compute_extraction_rates_gates():
    items = [
        {
            "id": "a", "title": "t", "link": "https://x",
            "detail_extraction": {"status": fs.PARSE_FAILED, "fields": {
                "region": {"status": fs.PARSE_FAILED},
                "application_period": {"status": fs.PARSE_FAILED},
                "target": {"status": fs.PARSE_FAILED},
                "title": {"status": fs.EXTRACTION_SUCCESS},
            }},
        },
        {
            "id": "b", "title": "t2", "link": "https://y",
            "detail_extraction": {"status": fs.DETAIL_FETCH_FAILED, "fields": {
                "region": {"status": fs.DETAIL_FETCH_FAILED},
                "application_period": {"status": fs.DETAIL_FETCH_FAILED},
                "target": {"status": fs.DETAIL_FETCH_FAILED},
                "title": {"status": fs.EXTRACTION_SUCCESS},
            }},
        },
        {
            "id": "c", "title": "t3", "link": "https://z",
            "detail_extraction": {"status": fs.EXTRACTION_SUCCESS, "fields": {
                "region": {"status": fs.NOT_SPECIFIED},
                "application_period": {"status": fs.NOT_SPECIFIED},
                "target": {"status": fs.NOT_SPECIFIED},
                "title": {"status": fs.EXTRACTION_SUCCESS},
            }},
        },
        {
            "id": "d", "title": "t4", "link": "https://w",
            "detail_extraction": {"status": fs.PARSE_FAILED, "fields": {
                "region": {"status": fs.PARSE_FAILED},
                "application_period": {"status": fs.PARSE_FAILED},
                "target": {"status": fs.PARSE_FAILED},
                "title": {"status": fs.EXTRACTION_SUCCESS},
            }},
        },
    ]
    rates = fs.compute_extraction_rates(items)
    assert rates["n"] == 4
    assert rates["parse_or_fetch_fail_rate"] >= 0.5
    assert rates["risk_level"] == "P0"
    assert "DETAIL_EXTRACT_RATE_LOW" in rates["reason_codes"]
    # NOT_SPECIFIED 만으로는 P0 승격 안 함
    only_ns = fs.compute_extraction_rates([items[2]] * 4)
    assert only_ns["risk_level"] == ""
    assert only_ns["not_specified_rate"] == 1.0


def test_plan_extraction_retries_skips_not_specified():
    plans = fs.plan_extraction_retries([
        {"id": "1", "link": "u1", "detail_extraction": {"status": fs.DETAIL_FETCH_FAILED}},
        {"id": "2", "link": "u2", "detail_extraction": {"status": fs.PARSE_FAILED}},
        {"id": "3", "link": "u3", "detail_extraction": {"status": fs.NOT_SPECIFIED}},
    ])
    assert {p["item_id"] for p in plans} == {"1", "2"}
    assert {p["subtype"] for p in plans} == {fs.DETAIL_FETCH_FAILED, fs.PARSE_FAILED}


def test_enrichment_clears_review_after_success():
    failed = {"detail_extraction": {"status": fs.DETAIL_FETCH_FAILED}}
    ok = {
        "detail_enriched": True,
        "detail_extraction": {"status": fs.EXTRACTION_SUCCESS},
    }
    assert fs.enrichment_clears_review(failed) is False
    assert fs.enrichment_clears_review(ok) is True


def test_run_extraction_retries_recovers_fetch_failure():
    """DETAIL_FETCH_FAILED 재시도 성공 시 아이템이 교체되고 recovered 증가."""
    calls = {"n": 0}

    def enrich(item):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                **item,
                "detail_extraction": {"status": fs.DETAIL_FETCH_FAILED},
                "detail_enriched": False,
            }
        return {
            **item,
            "detail_enriched": True,
            "detail_extraction": {
                "status": fs.EXTRACTION_SUCCESS,
                "fields": {"region": {"status": fs.NOT_SPECIFIED}},
            },
        }

    items = [{
        "id": "n1",
        "link": "https://example.go.kr/1",
        "title": "t",
        "detail_extraction": {"status": fs.DETAIL_FETCH_FAILED},
    }]
    out, stats = fs.run_extraction_retries(
        items, enrich, fetch_auto_retry=2, backoff_sec=(0, 0), sleep_fn=lambda _s: None,
    )
    assert stats["planned"] == 1
    assert stats["recovered"] == 1
    assert stats["still_failed"] == 0
    assert fs.enrichment_clears_review(out[0]) is True
    assert calls["n"] == 2  # 1차 실패 후 2차 성공


def test_run_extraction_retries_skips_not_specified_and_queues_only_failures():
    items = [
        {
            "id": "ok",
            "link": "https://x",
            "detail_extraction": {"status": fs.NOT_SPECIFIED},
        },
        {
            "id": "bad",
            "link": "https://y",
            "detail_extraction": {"status": fs.PARSE_FAILED},
        },
    ]
    calls = []

    def enrich(item):
        calls.append(item["id"])
        return {
            **item,
            "detail_extraction": {"status": fs.PARSE_FAILED},
        }

    out, stats = fs.run_extraction_retries(
        items, enrich, parse_auto_retry=1, backoff_sec=(0,), sleep_fn=lambda _s: None,
    )
    assert "ok" not in calls
    assert calls == ["bad"]
    assert stats["still_failed"] == 1
    assert out[0]["detail_extraction"]["status"] == fs.NOT_SPECIFIED


def test_enqueue_extraction_failures_subtypes(tmp_path):
    path = tmp_path / "q.json"
    items = [
        {
            "id": "n1", "title": "A", "source": "기업마당", "site_id": "bizinfo",
            "link": "https://a",
            "detail_extraction": {"status": fs.PARSE_FAILED},
        },
        {
            "id": "n2", "title": "B", "source": "NIPA", "site_id": "nipa",
            "link": "https://b",
            "detail_extraction": {"status": fs.DETAIL_FETCH_FAILED},
        },
        {
            "id": "n3", "title": "C", "source": "X",
            "detail_extraction": {"status": fs.NOT_SPECIFIED},
        },
    ]
    n = mr.enqueue_extraction_failures(items, path=path)
    assert n == 2
    q = mr.load_manual_queue(path)
    subtypes = {it["subtype"] for it in q["items"]}
    assert subtypes == {fs.PARSE_FAILED, fs.DETAIL_FETCH_FAILED}


def _blank_region_item(status: str) -> dict:
    return {
        "id": f"blank-{status}",
        "title": "스마트공장 지원사업 신청 모집 공고",
        "link": "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/view.do?seq=1",
        "author": "중기부",
        "description": "스마트공장 구축 지원 신청을 접수합니다. 제조 중소기업 대상.",
        "deadline": "2026-12-31",
        "source": "기업마당",
        "posted_date": "2026-07-23",
        "region_field": "",
        "is_aggregator": True,
        "detail_extraction": {
            "status": status if status != fs.NOT_SPECIFIED else fs.EXTRACTION_SUCCESS,
            "reason": "test",
            "fields": {
                "region": {"status": status, "source": "detail", "evidence": ""},
                "application_period": {
                    "status": fs.EXTRACTION_SUCCESS, "source": "list",
                    "evidence": "2026-12-31",
                },
                "target": {"status": fs.NOT_SPECIFIED, "source": "detail", "evidence": ""},
                "title": {
                    "status": fs.EXTRACTION_SUCCESS, "source": "list",
                    "evidence": "스마트공장",
                },
            },
        },
    }


def test_same_blank_region_branches_by_status():
    """동일 빈 region 문자열이라도 status 3종 → 포함후보 / review / review."""
    groups = json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))
    group = next(g for g in groups if g.get("active"))
    today = date(2026, 7, 23)

    ns = m.filter_for_group_with_diagnostics(
        [_blank_region_item(fs.NOT_SPECIFIED)], group, today=today)
    pf = m.filter_for_group_with_diagnostics(
        [_blank_region_item(fs.PARSE_FAILED)], group, today=today)
    ff = m.filter_for_group_with_diagnostics(
        [_blank_region_item(fs.DETAIL_FETCH_FAILED)], group, today=today)

    # NOT_SPECIFIED → region_unknown 금지. included 또는 (비추출사유) review 가능.
    assert not ns["region_unknown"], "NOT_SPECIFIED must not enter region_unknown"
    assert not ns["excluded"] or not any(
        "REGION_UNKNOWN" in (it.get("exclude_reason_codes") or [])
        for it in ns["excluded"]
    )

    # PARSE / FETCH → review only, exclude·region_unknown 금지
    assert pf["review"] and not pf["excluded"] and not pf["region_unknown"]
    assert pf["review"][0]["detail_failure_review"] is True
    assert ff["review"] and not ff["excluded"] and not ff["region_unknown"]
    assert ff["review"][0]["detail_failure_review"] is True

    # NOT_SPECIFIED 는 포함 후보가 될 수 있음(키워드·마감 충족 시)
    assert ns["included"] or (
        ns["review"] and not ns["review"][0].get("detail_failure_review")
    )


def test_not_specified_guard_never_region_unknown_or_exclude_for_blank_region():
    groups = json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))
    group = next(g for g in groups if g.get("active"))
    buckets = m.filter_for_group_with_diagnostics(
        [_blank_region_item(fs.NOT_SPECIFIED)], group, today=date(2026, 7, 23),
    )
    assert buckets["region_unknown"] == []
    for it in buckets["excluded"]:
        assert "REGION_UNKNOWN" not in (it.get("exclude_reason_codes") or [])


def test_date_unknown_parse_failed_is_high_risk_not_unstated():
    item = {
        "title": "공고",
        "description": "",
        "link": "https://www.bizinfo.go.kr/x",
        "detail_extraction": {
            "status": fs.PARSE_FAILED,
            "fields": {
                "application_period": {"status": fs.PARSE_FAILED},
            },
        },
    }
    assert m.assess_date_unknown_risk(item) == "높음"
    included, remaining = m.split_unknown_by_policy([item], "recall")
    assert included and not remaining


def test_company_match_not_specified_region_gets_nationwide_bonus():
    from mail_core.matching import company_match as cm

    company = {
        "id": "c1",
        "name": "테스트",
        "active": True,
        "region": {"city": "인천", "district": "남동구"},
        "industry_keywords": ["스마트공장"],
        "interest_keywords": [],
        "exclude_keywords": [],
        "has_factory": True,
        "export_focus": False,
        "support_type_prefs": [],
        "match_threshold": 10,
    }
    item = {
        "title": "스마트공장 지원 사업 모집",
        "description": "제조 중소기업 신청 접수",
        "region_field": "",
        "detail_extraction": {
            "status": fs.EXTRACTION_SUCCESS,
            "fields": {"region": {"status": fs.NOT_SPECIFIED}},
        },
    }
    result = cm.compute_match_score(item, company)
    assert result["breakdown"]["region_status"] == "nationwide_not_specified"
    assert result["score"] > 0
