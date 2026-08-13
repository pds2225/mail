"""스타트업플러스(서울시) JSON API 파서 회귀 테스트 — respx 오프라인 재생."""
import pathlib

import httpx
import pytest
import respx

import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "startup_plus"
API = "https://www.startup-plus.kr/api/project/list"

SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "startup_plus",
        "name": "스타트업플러스(서울시)",
        "url": "https://www.startup-plus.kr/project",
        "is_aggregator": False,
        "max_pages": 3,
        "page_size": 3,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def _route():
    respx.get(API, params={"size": "3", "page": "0"}).mock(
        return_value=httpx.Response(200, text=_load("project_page1.json")))
    respx.get(API, params={"size": "3", "page": "1"}).mock(
        return_value=httpx.Response(200, text=_load("project_page2.json")))
    respx.get(API, params={"size": "3", "page": "2"}).mock(
        return_value=httpx.Response(200, text=_load("project_empty.json")))


@respx.mock
def test_startup_plus_collects_across_pages_with_deeplinks():
    _route()
    items = monitor.fetch_startup_plus(_site())

    assert len(items) == 6
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids))

    for it in items:
        assert set(it) == SCHEMA_KEYS
        assert it["source"] == "스타트업플러스(서울시)"
        assert it["link"].startswith("https://www.startup-plus.kr/project/PRJ")
        assert it["id"].startswith("startup_plus_PRJ")

    first = items[0]
    assert first["link"] == "https://www.startup-plus.kr/project/PRJ007410"
    assert first["posted_date"] == "2026-08-10"
    assert first["deadline"] == "2026-08-12"
    assert "창업행사" in first["description"]


@respx.mock
def test_startup_plus_http_error_raises_not_silent_zero():
    respx.get(API).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError):
        monitor.fetch_startup_plus(_site())
