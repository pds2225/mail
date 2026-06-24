"""기업마당(bizinfo) JSON API 파서 회귀 테스트 — respx 오프라인 재생.

저장된 응답 픽스처를 respx 로 가로채(네트워크 0) `fetch_bizinfo` 가 기대한
공고 항목을 정확히 추출하는지 검증한다. 파서 로직 회귀(필드 매핑·추출 분기
변경)를 발송 전 빨간불로 잡는 첫 안전망.

respx 매칭 정책: URL 만 매칭하고 params(crtfcKey 등)는 검증하지 않는다.
crtfcKey 는 비밀키이며 테스트가 그 값에 종속되면 안 되기 때문이다.
"""
import json
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "bizinfo"
BIZINFO_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "bizinfo",
        "name": "기업마당(Bizinfo)",
        "url": BIZINFO_URL,
        "is_aggregator": True,
    }


def _load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


@respx.mock
def test_bizinfo_extracts_expected_items():
    """추출 건수·필드 매핑·9키 스키마·is_aggregator 검증."""
    payload = _load("bizinfo_sample.json")
    respx.get(BIZINFO_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_bizinfo(_site())

    # 1) 추출 건수 == 픽스처 항목 수
    assert len(items) == 3

    first = items[0]
    src = payload["jsonArray"][0]
    # 2) 필드 매핑(필드 매핑 회귀 방지)
    assert first["id"] == src["pblancId"]
    assert first["title"] == src["pblancNm"]
    assert first["link"] == src["pblancUrl"]
    assert first["author"] == src["jrsdInsttNm"]
    assert first["description"] == src["bsnsSumryCn"]
    assert first["deadline"] == src["reqstBeginEndDe"]
    assert first["source"] == "기업마당(Bizinfo)"

    # is_aggregator: site dict 의 True 가 그대로 반영
    assert first["is_aggregator"] is True

    # 5) 스키마 불변: 모든 item 이 9키를 전부 보유
    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS


@respx.mock
def test_bizinfo_posted_date_truncated():
    """regDt 11자 이상이 10자(YYYY-MM-DD)로 절단되는지 (monitor.py:667-668)."""
    payload = _load("bizinfo_sample.json")
    respx.get(BIZINFO_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_bizinfo(_site())

    # 첫 항목 regDt = "2026-06-15 09:30:00" (19자) → "2026-06-15" 로 절단
    assert payload["jsonArray"][0]["regDt"] == "2026-06-15 09:30:00"
    assert items[0]["posted_date"] == "2026-06-15"


@respx.mock
def test_bizinfo_id_fallback():
    """pblancId 없는 항목은 bizinfo_<stable_id> 폴백 id 가 생성된다."""
    payload = _load("bizinfo_sample.json")
    respx.get(BIZINFO_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_bizinfo(_site())

    # 세 번째 항목은 pblancId 가 없음 → 폴백
    third = items[2]
    assert third["id"]  # 빈 id 가 아님
    assert third["id"].startswith("bizinfo_")
    # 폴백 id 는 title+link 의 stable_id 로 결정론적
    expected = "bizinfo_" + monitor.stable_id(third["title"] + third["link"])
    assert third["id"] == expected


@respx.mock
def test_bizinfo_channel_item_branch():
    """대체 구조(channel.item)에서도 동일하게 추출되는지 (파서 두 분기 커버)."""
    payload = _load("bizinfo_channel_item.json")
    respx.get(BIZINFO_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_bizinfo(_site())

    assert len(items) == 1
    src = payload["channel"]["item"]
    assert items[0]["id"] == src["pblancId"]
    assert items[0]["title"] == src["pblancNm"]
    assert set(items[0].keys()) == SCHEMA_KEYS


@respx.mock
def test_bizinfo_empty_json_array_returns_empty():
    """구조 깨짐 시나리오 1: jsonArray 가 빈 배열이면 items == [] (빨간불)."""
    respx.get(BIZINFO_URL).mock(
        return_value=httpx.Response(200, json={"jsonArray": []}))
    assert monitor.fetch_bizinfo(_site()) == []


@respx.mock
def test_bizinfo_req_err_returns_empty():
    """인증키 오류(reqErr)는 0건 + 빈 배열이 아닌 명시 오류 — 로그 추적 가능."""
    respx.get(BIZINFO_URL).mock(
        return_value=httpx.Response(200, json={"reqErr": "존재하지 않는 인증키 입니다."}))
    assert monitor.fetch_bizinfo(_site()) == []


@respx.mock
def test_bizinfo_paginated_dedup():
    """pageIndex 2페이지까지 합치고 pblancId 중복 제거."""
    page1 = _load("bizinfo_sample.json")
    page2 = {"jsonArray": [page1["jsonArray"][0]]}  # duplicate id
    route = respx.get(BIZINFO_URL)
    route.mock(side_effect=[
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
        httpx.Response(200, json={"jsonArray": []}),
    ])
    site = {**_site(), "api_page_unit": 2, "api_max_pages": 3}
    items = monitor.fetch_bizinfo(site)
    assert len(items) == 3
