"""중소기업 혁신바우처(MSSMIV) HTML 파서 회귀 테스트 — respx 오프라인 재생.

저장된 HTML 픽스처를 respx 로 가로채(네트워크 0) `fetch_mssmiv` 가 목록
테이블의 onclick=goDetail(seq) 행에서 공고를 정확히 추출하는지 검증한다.
파서 로직 회귀(셀렉터·링크 조립·id 규칙·posted/deadline 날짜 배정 변경)를
발송 전 빨간불로 잡는 안전망.

핵심 파서 계약(monitor.fetch_mssmiv):
  - `table tbody tr` 안 `a[onclick]` 만 후보, goDetail(\\d+) 없으면 스킵
  - title len < 5 스킵
  - link = https://www.mssmiv.com/portal/board/BoardView?seq={seq}
  - id   = mssmiv_{seq}
  - tds 합친 텍스트의 YYYY.MM.DD 날짜 중 첫째=posted, 2개 이상이면 마지막=deadline
  - author 고정 "중소기업혁신바우처(중소벤처기업부)", description "" , source=site name

respx 매칭 정책: 이 URL params(bbsId=1)엔 비밀키가 없으므로 URL 전체를 그대로
매칭한다(bizinfo 처럼 비밀키 종속 회피가 필요없음).
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "mssmiv"
MSSMIV_URL = "https://www.mssmiv.com/portal/board/BoardList?bbsId=1"
BASE = "https://www.mssmiv.com"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "mssmiv",
        "name": "중소기업 혁신바우처(MSSMIV)",
        "url": MSSMIV_URL,
        "is_aggregator": False,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


@respx.mock
def test_mssmiv_extracts_expected_items():
    """추출 건수·9키 스키마·source·is_aggregator 검증.

    픽스처 행 4개 중: 항목1(seq4001)·항목2(seq4002)=수집,
    항목3(제목 '공지' 5자 미만)=스킵, 노이즈 행(a[onclick] 없음)=스킵 → 2건.
    """
    respx.get(MSSMIV_URL).mock(
        return_value=httpx.Response(200, html=_load("mssmiv_list.html")))

    items = monitor.fetch_mssmiv(_site())

    # 1) 추출 건수 == 유효 공고 2건 (짧은 제목·onclick 없는 행 제외)
    assert len(items) == 2

    for it in items:
        # 스키마 불변: 모든 item 이 9키를 전부 보유
        assert set(it.keys()) == SCHEMA_KEYS
        # site dict 의 is_aggregator=False 가 그대로 반영
        assert it["is_aggregator"] is False
        # source = site["name"], author 고정값
        assert it["source"] == "중소기업 혁신바우처(MSSMIV)"
        assert it["author"] == "중소기업혁신바우처(중소벤처기업부)"
        # description 은 항상 빈 문자열
        assert it["description"] == ""


@respx.mock
def test_mssmiv_item_with_two_dates_literal():
    """날짜 2개 행: id/title/link/posted/deadline 가 픽스처 리터럴과 정확히 일치."""
    respx.get(MSSMIV_URL).mock(
        return_value=httpx.Response(200, html=_load("mssmiv_list.html")))

    items = monitor.fetch_mssmiv(_site())
    by_id = {it["id"]: it for it in items}

    # 항목1 (seq=4001) — 등록일 2026.06.10 + 접수마감 2026.07.15 (2개)
    one = by_id["mssmiv_4001"]
    assert one["title"] == "2026년 중소기업 혁신바우처 사업 참여기업 모집 공고"
    assert one["link"] == f"{BASE}/portal/board/BoardView?seq=4001"
    # 날짜는 점(.)→대시(-) 정규화: 첫 날짜=posted, 마지막 날짜=deadline
    assert one["posted_date"] == "2026-06-10"
    assert one["deadline"] == "2026-07-15"


@respx.mock
def test_mssmiv_item_with_one_date_no_deadline():
    """날짜 1개 행: posted 만 채워지고 deadline 은 빈 문자열(2개 미만 규칙)."""
    respx.get(MSSMIV_URL).mock(
        return_value=httpx.Response(200, html=_load("mssmiv_list.html")))

    items = monitor.fetch_mssmiv(_site())
    by_id = {it["id"]: it for it in items}

    # 항목2 (seq=4002) — 등록일 2026.06.08 1개뿐 (마감 '-' 는 날짜 아님)
    two = by_id["mssmiv_4002"]
    assert two["title"] == "혁신바우처 수행기관 추가 모집 안내"
    assert two["link"] == f"{BASE}/portal/board/BoardView?seq=4002"
    assert two["posted_date"] == "2026-06-08"
    # 날짜가 1개뿐이므로 deadline 은 빈 값
    assert two["deadline"] == ""


@respx.mock
def test_mssmiv_id_rule_and_short_title_skipped():
    """id 규칙(mssmiv_{seq}) + 5자 미만 제목('공지') 스킵 회귀 차단."""
    respx.get(MSSMIV_URL).mock(
        return_value=httpx.Response(200, html=_load("mssmiv_list.html")))

    items = monitor.fetch_mssmiv(_site())
    ids = [it["id"] for it in items]

    # id 규칙: 모두 mssmiv_<seq> 형태, 수집된 두 seq 만 존재
    assert ids == ["mssmiv_4001", "mssmiv_4002"]
    # 제목 '공지'(seq=4003)는 len<5 라 스킵 → id 부재
    assert "mssmiv_4003" not in ids
    # id 전수 고유
    assert len(ids) == len(set(ids))


@respx.mock
def test_mssmiv_no_onclick_returns_empty():
    """구조 깨짐 시나리오: a[onclick] 없는 표만 있으면 items == [] (빨간불)."""
    respx.get(MSSMIV_URL).mock(
        return_value=httpx.Response(200, html=_load("mssmiv_no_onclick.html")))

    assert monitor.fetch_mssmiv(_site()) == []


@respx.mock
def test_mssmiv_empty_html_returns_empty():
    """완전 빈 HTML(테이블 없음)이면 items == [] (안전 처리)."""
    respx.get(MSSMIV_URL).mock(
        return_value=httpx.Response(200, html="<html><body></body></html>"))

    assert monitor.fetch_mssmiv(_site()) == []
