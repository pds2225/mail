# -*- coding: utf-8 -*-
"""fetch_html_generic 페이지네이션 — opt-in 동작·안전장치 검증.

네트워크 없이 _soup 를 monkeypatch 해 페이지 흐름만 검증한다.
핵심 계약: **max_pages 미설정 = 첫 페이지만(기존 동작 100% 보존)**.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402


BASE = "https://x.kr/board/list.do"


def _page_html(rows: list[tuple[str, str]], pager: list[int] | None = None) -> str:
    """행(제목, 상세id) + 하단 페이지 링크로 게시판 HTML 을 만든다."""
    trs = "".join(
        f'<tr><td class="title"><a href="view.do?id={rid}">{title}</a></td>'
        f'<td>2026-07-{20 + i:02d}</td></tr>'
        for i, (title, rid) in enumerate(rows)
    )
    links = "".join(
        f'<a href="list.do?page={n}">{n}</a>' for n in (pager or [])
    )
    return f"<html><body><table><tbody>{trs}</tbody></table><div>{links}</div></body></html>"


def _site(**kw) -> dict:
    base = {"id": "s1", "name": "테스트게시판", "type": "html_table",
            "url": BASE, "enabled": True}
    base.update(kw)
    return base


@pytest.fixture()
def pages(monkeypatch):
    """URL → HTML 매핑. 호출된 URL 순서를 기록한다."""
    store: dict[str, str] = {}
    calls: list[str] = []

    def fake_soup(url, *a, **k):
        calls.append(url)
        html = store.get(url)
        return BeautifulSoup(html, "html.parser") if html is not None else None

    monkeypatch.setattr(m, "_soup", fake_soup)
    m.reset_page_stats()
    return store, calls


# ── 기본 동작 보존 (가장 중요한 계약) ────────────────────────────────────────
def test_default_fetches_first_page_only(pages):
    store, calls = pages
    store[BASE] = _page_html([("공고A", "1"), ("공고B", "2")], pager=[1, 2, 3])

    items = m.fetch_html_generic(_site())   # max_pages 미설정

    assert len(items) == 2
    assert len(calls) == 1                   # 요청 1회 — 추가 부하 없음
    stat = m.page_stats_snapshot()["s1"]
    assert stat["stop_reason"] == "SINGLE_PAGE"
    assert stat["pages_fetched"] == 1


def test_max_pages_1_is_same_as_default(pages):
    store, calls = pages
    store[BASE] = _page_html([("공고A", "1")], pager=[1, 2])
    m.fetch_html_generic(_site(max_pages=1))
    assert len(calls) == 1


def test_invalid_max_pages_falls_back_to_one(pages):
    store, calls = pages
    store[BASE] = _page_html([("공고A", "1")], pager=[1, 2])
    m.fetch_html_generic(_site(max_pages="이상한값"))
    assert len(calls) == 1


# ── opt-in 페이지네이션 ─────────────────────────────────────────────────────
def test_follows_pages_when_max_pages_set(pages):
    store, calls = pages
    store[BASE] = _page_html([("A", "1"), ("B", "2")], pager=[1, 2, 3])
    store["https://x.kr/board/list.do?page=2"] = _page_html(
        [("C", "3"), ("D", "4")], pager=[1, 2, 3])
    store["https://x.kr/board/list.do?page=3"] = _page_html(
        [("E", "5")], pager=[1, 2, 3])

    items = m.fetch_html_generic(_site(max_pages=3))

    assert len(items) == 5
    assert [it["title"] for it in items] == ["A", "B", "C", "D", "E"]
    assert len(calls) == 3
    stat = m.page_stats_snapshot()["s1"]
    assert stat["stop_reason"] == "MAX_PAGES_HIT"
    assert stat["pages_fetched"] == 3


def test_stops_when_no_next_link(pages):
    """페이지 링크가 없으면 1페이지에서 정직하게 멈춘다(추측 금지)."""
    store, calls = pages
    store[BASE] = _page_html([("A", "1")])        # pager 없음

    items = m.fetch_html_generic(_site(max_pages=5))

    assert len(items) == 1 and len(calls) == 1
    assert m.page_stats_snapshot()["s1"]["stop_reason"] == "NO_NEXT_LINK"


def test_stops_on_duplicate_page(pages):
    """2페이지가 1페이지와 같으면(페이지 파라미터 무시 사이트) 중단하고 표시한다."""
    store, calls = pages
    same = _page_html([("A", "1"), ("B", "2")], pager=[1, 2, 3])
    store[BASE] = same
    store["https://x.kr/board/list.do?page=2"] = same

    items = m.fetch_html_generic(_site(max_pages=3))

    assert len(items) == 2                       # 중복 미포함
    stat = m.page_stats_snapshot()["s1"]
    assert stat["stop_reason"] == "DUPLICATE_PAGE"
    assert stat["duplicate_page"] is True


def test_partial_result_kept_when_later_page_fails(pages):
    """2페이지 접속 실패해도 1페이지 수집분은 버리지 않는다."""
    store, calls = pages
    store[BASE] = _page_html([("A", "1"), ("B", "2")], pager=[1, 2])
    # page=2 는 store 에 없음 → fake_soup 이 None 반환(접속 실패)

    items = m.fetch_html_generic(_site(max_pages=3))

    assert len(items) == 2
    assert m.page_stats_snapshot()["s1"]["stop_reason"] == "PAGE_FETCH_FAILED"


def test_first_page_failure_still_raises(pages):
    """1페이지 실패는 기존대로 예외 — '진짜 0건'과 구분돼야 커버리지가 오탐하지 않는다."""
    store, _calls = pages                        # BASE 를 넣지 않음
    with pytest.raises(RuntimeError):
        m.fetch_html_generic(_site(max_pages=3))


def test_dedup_across_pages(pages):
    """페이지 간 겹치는 항목은 한 번만 담는다."""
    store, _calls = pages
    store[BASE] = _page_html([("A", "1"), ("B", "2")], pager=[1, 2])
    store["https://x.kr/board/list.do?page=2"] = _page_html(
        [("B", "2"), ("C", "3")], pager=[1, 2])   # B 중복

    items = m.fetch_html_generic(_site(max_pages=2))

    assert [it["title"] for it in items] == ["A", "B", "C"]


def test_relative_links_resolve_against_current_page(pages):
    """2페이지의 상대링크는 2페이지 URL 기준으로 풀려야 한다."""
    store, _calls = pages
    store[BASE] = _page_html([("A", "1")], pager=[1, 2])
    store["https://x.kr/board/list.do?page=2"] = _page_html([("B", "9")], pager=[1, 2])

    items = m.fetch_html_generic(_site(max_pages=2))

    assert items[1]["link"] == "https://x.kr/board/view.do?id=9"


# ── 다음 페이지 URL 탐지 ────────────────────────────────────────────────────
def test_next_page_url_skips_javascript_links():
    soup = BeautifulSoup(
        '<a href="javascript:goPage(2)">2</a><a href="#">2</a>', "html.parser")
    assert m._next_page_url(soup, BASE, 2) == ""


def test_next_page_url_skips_self_link():
    soup = BeautifulSoup(f'<a href="{BASE}">2</a>', "html.parser")
    assert m._next_page_url(soup, BASE, 2) == ""


def test_next_page_url_finds_numeric_link():
    soup = BeautifulSoup(
        '<a href="list.do?page=1">1</a><a href="list.do?page=2">2</a>', "html.parser")
    assert m._next_page_url(soup, BASE, 2) == "https://x.kr/board/list.do?page=2"


def test_next_page_url_ignores_numeric_detail_link_before_pager():
    soup = BeautifulSoup(
        '<a href="view.do?id=2">2</a><a href="list.do?page=2">2</a>', "html.parser")
    assert m._next_page_url(soup, BASE, 2) == "https://x.kr/board/list.do?page=2"


def test_next_page_url_rejects_wrong_page_number():
    soup = BeautifulSoup('<a href="list.do?page=20">2</a>', "html.parser")
    assert m._next_page_url(soup, BASE, 2) == ""


def test_next_page_url_never_raises():
    assert m._next_page_url(None, BASE, 2) == ""   # type: ignore[arg-type]
