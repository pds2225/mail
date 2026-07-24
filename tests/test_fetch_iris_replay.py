"""IRIS(범부처통합연구지원) JSON API 파서 회귀 테스트 — respx 오프라인 재생.

저장된 응답 픽스처를 respx 로 가로채(네트워크 0) `fetch_iris` 가 기대한 공고
항목을 정확히 추출하는지 검증한다. 파서 로직 회귀(필드 매핑·추출 분기 변경)를
발송 전 빨간불로 잡는 안전망.

respx 매칭 정책: fetch_iris 는 httpx.Client.post 로 retrieveBsnsAncmBtinSituList.do
(목록 URL ≠ site["url"] 의 ...ListView.do) 를 호출하므로, 그 POST API URL 을
매칭한다. params/data 엔 비밀키가 없어 URL 매칭만으로 충분하다.
"""
import json
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "iris"

# fetch_iris 가 실제로 POST 하는 목록 API URL (site["url"] 의 ...ListView.do 가 아님)
IRIS_API_URL = "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do"
IRIS_DETAIL_BASE = "https://www.iris.go.kr/contents/retrieveBsnsAncmView.do"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "iris",
        "name": "IRIS(범부처통합연구지원)",
        "url": "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do",
        "is_aggregator": False,
    }


def _load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


@respx.mock
def test_iris_extracts_expected_items():
    """추출 건수·9키 스키마·source·is_aggregator 검증."""
    payload = _load("iris_sample.json")
    respx.post(IRIS_API_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_iris(_site())

    # 1) 추출 건수 == 제목 있는 항목 수(3개 중 ancmTl 빈 항목 1개 제외 → 2건)
    assert len(items) == 2

    # 스키마 불변: 모든 item 이 9키를 전부 보유
    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS
        assert it["source"] == "IRIS(범부처통합연구지원)"
        assert it["is_aggregator"] is False


@respx.mock
def test_iris_first_item_fields_literal():
    """첫 항목의 id/title/author/deadline/posted/desc/link 가 리터럴과 일치(필드 매핑 회귀)."""
    payload = _load("iris_sample.json")
    respx.post(IRIS_API_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_iris(_site())
    first = items[0]

    # id = iris_<ancmId>
    assert first["id"] == "iris_20260017"
    assert first["title"] == "2026년도 범부처 바이오·의료기술개발사업 신규과제 공고"
    assert first["author"] == "한국연구재단"
    # rcveEndDe "2026.07.31" → '.' 를 '-' 로 치환
    assert first["deadline"] == "2026-07-31"
    # ancmDe "2026.06.16" → '.' 를 '-' 로 치환
    assert first["posted_date"] == "2026-06-16"
    assert first["description"] == "자유공모, 지정공모"
    # link = detail_base?ancmId=<ancmId>
    assert first["link"] == f"{IRIS_DETAIL_BASE}?ancmId=20260017"


@respx.mock
def test_iris_title_whitespace_collapsed():
    """norm() 으로 제목 내부 다중 공백이 단일 공백으로 정규화되는지."""
    payload = _load("iris_sample.json")
    respx.post(IRIS_API_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_iris(_site())
    second = items[1]

    # 픽스처 원문엔 앞뒤·내부에 다중 공백이 있지만 norm 으로 단일 공백 정규화
    assert second["id"] == "iris_20260018"
    assert second["title"] == "2026년 소재·부품·장비 핵심기술개발사업 공고"
    assert second["author"] == "한국산업기술기획평가원"
    assert second["deadline"] == "2026-08-15"
    assert second["posted_date"] == "2026-06-17"
    assert second["link"] == f"{IRIS_DETAIL_BASE}?ancmId=20260018"


@respx.mock
def test_iris_empty_title_skipped():
    """ancmTl 이 빈 항목(ancmId=20260019)은 결과에서 제외된다."""
    payload = _load("iris_sample.json")
    respx.post(IRIS_API_URL).mock(return_value=httpx.Response(200, json=payload))

    items = monitor.fetch_iris(_site())
    ids = [it["id"] for it in items]

    # 제목 없는 세 번째 항목은 수집되지 않음
    assert "iris_20260019" not in ids


@respx.mock
def test_iris_empty_list_returns_empty():
    """구조 깨짐 시나리오 1: listBsnsAncmBtinSitu 가 빈 배열이면 items == [] (빨간불)."""
    respx.post(IRIS_API_URL).mock(
        return_value=httpx.Response(200, json={"listBsnsAncmBtinSitu": []}))
    assert monitor.fetch_iris(_site()) == []


@respx.mock
def test_iris_missing_key_returns_empty():
    """구조 깨짐 시나리오 2: listBsnsAncmBtinSitu 키가 없으면 items == [] (빨간불)."""
    respx.post(IRIS_API_URL).mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"}))
    assert monitor.fetch_iris(_site()) == []
