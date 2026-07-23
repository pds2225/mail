# -*- coding: utf-8 -*-
"""P0-B 상세정보 추출 실패상태·검토 유지 회귀 테스트."""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
}.items():
    os.environ.setdefault(_key, _value)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402


DETAIL_URL = "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?id=1"


def _item(**changes) -> dict:
    item = {
        "id": "notice-1",
        "title": "지원사업 공고",
        "link": DETAIL_URL,
        "author": "",
        "description": "",
        "deadline": "",
        "source": "기업마당",
        "posted_date": "2026-07-23",
        "is_aggregator": True,
    }
    item.update(changes)
    return item


def test_detail_fetch_failure_is_not_saved_as_plain_empty(monkeypatch):
    monkeypatch.setattr(m, "_http_get", lambda *args, **kwargs: None)

    out = m.enrich_item_from_detail(_item())

    extraction = out["detail_extraction"]
    assert extraction["status"] == m.DETAIL_FETCH_FAILED
    assert extraction["reason"] == "http_no_response"
    assert extraction["fields"]["title"] == {
        "status": m.EXTRACTION_SUCCESS,
        "source": "list",
        "evidence": "지원사업 공고",
    }
    for field in ("organizer", "application_period", "target", "region"):
        assert extraction["fields"][field]["status"] == m.DETAIL_FETCH_FAILED
    assert out.get("detail_enriched") is not True


def test_parsed_detail_marks_unstated_fields_not_specified(monkeypatch):
    html = "<html><article>서울 소재 기업을 위한 지원사업 신청 안내 본문입니다. 신청을 접수합니다.</article></html>"
    monkeypatch.setattr(
        m, "_http_get", lambda *args, **kwargs: SimpleNamespace(text=html))

    out = m.enrich_item_from_detail(_item())

    extraction = out["detail_extraction"]
    assert extraction["status"] == m.EXTRACTION_SUCCESS
    assert extraction["fields"]["description"]["status"] == m.EXTRACTION_SUCCESS
    assert extraction["fields"]["description"]["source"] == "detail"
    assert extraction["fields"]["application_period"]["status"] == m.NOT_SPECIFIED
    assert extraction["fields"]["target"]["status"] == m.NOT_SPECIFIED
    assert out["detail_enriched"] is True


def test_http_success_without_extractable_detail_is_parse_failed(monkeypatch):
    monkeypatch.setattr(
        m, "_http_get",
        lambda *args, **kwargs: SimpleNamespace(text="<html><body>ok</body></html>"),
    )

    out = m.enrich_item_from_detail(_item())

    assert out["detail_extraction"]["status"] == m.PARSE_FAILED
    assert out["detail_extraction"]["reason"] == "no_extractable_detail"
    assert out["detail_extraction"]["fields"]["region"]["status"] == m.PARSE_FAILED
    assert out.get("detail_enriched") is not True


def test_enrich_worker_exception_keeps_failure_state(monkeypatch):
    monkeypatch.setattr(
        m, "enrich_item_from_detail",
        lambda item: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    out = m.enrich_items([_item()], limit=1)[0]

    assert out["detail_extraction"]["status"] == m.DETAIL_FETCH_FAILED
    assert out["detail_extraction"]["reason"] == "detail_exception"


def test_detail_failure_without_definitive_exclusion_goes_to_review():
    groups = json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))
    group = next(g for g in groups if g.get("active"))
    item = _item(
        title="제목만 있는 공고",
        description="",
        detail_extraction={
            "status": m.PARSE_FAILED,
            "reason": "no_extractable_detail",
            "fields": {},
        },
    )

    buckets = m.filter_for_group_with_diagnostics(
        [item], group, today=date(2026, 7, 23))

    assert not buckets["excluded"]
    assert buckets["review"]
    reviewed = buckets["review"][0]
    assert reviewed["detail_failure_review"] is True
    assert any("상세정보 추출 실패" in note for note in reviewed["notes"])
