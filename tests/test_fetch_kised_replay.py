"""창업진흥원(KISED) 사업공고 HTML 파서 회귀 — respx 오프라인 재생.

실측: 옛 URL menu.es?mid=a10201000000 는 본문 ERROR 404·table 0행.
실제 목록은 misAnnouncement/index.es?mid=a10302000000 의 ul.lstyle_list.
모니터 전용 fetcher 없이 html_table(fetch_html_generic)만 사용한다.
"""
from __future__ import annotations

import json
import pathlib

import httpx
import pytest
import respx

import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "kised"
LIST_URL = "https://www.kised.or.kr/misAnnouncement/index.es?mid=a10302000000"
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site_from_config() -> dict:
    sites = json.loads((pathlib.Path("config/sites.json")).read_text(encoding="utf-8"))
    site = next(s for s in sites if s["id"] == "kised")
    assert site["enabled"] is True
    assert site["type"] == "html_table"
    return site


def _load() -> str:
    return (FX / "kised_list.html").read_text(encoding="utf-8")


@respx.mock
def test_kised_html_table_collects_list_items():
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, html=_load()))
    items = monitor.fetch_html_generic(_site_from_config())

    assert len(items) == 2
    by_title = {it["title"]: it for it in items}
    ai = by_title["2026년 AI 사업화지원금 예비창업 패키지 모집 공고"]
    gen = by_title["2026년 예비창업패키지(일반) 모집 공고"]
    assert ai["link"].endswith("pbancSn=900001")
    assert gen["link"].endswith("pbancSn=900002")
    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS
        assert it["source"] == "창업진흥원(KISED)"
        assert it["is_aggregator"] is False
        assert it["link"].startswith("https://www.k-startup.go.kr/")


@respx.mock
def test_kised_old_menu_url_is_not_the_configured_source():
    site = _site_from_config()
    assert "menu.es?mid=a10201000000" not in site["url"]
    assert "misAnnouncement" in site["url"]


def test_duplicate_imp_source_stays_disabled():
    sites = json.loads(pathlib.Path("config/sites.json").read_text(encoding="utf-8"))
    imp = next(s for s in sites if s["id"] == "imp_6e8c8360")
    assert imp["enabled"] is False
    assert imp["selectors"]["row"] == "ul.lstyle_list > li"
