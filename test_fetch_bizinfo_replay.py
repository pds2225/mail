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
def test_bizinfo_req_err_raises():
    """인증키 오류(reqErr)는 '진짜 0건'이 아니라 하드 실패 → RuntimeError 로 올린다.

    이래야 fetch_site_coverage 가 fetch_success=False='수집실패'로 분류하고
    (커버리지 알림이 '0건 급락'이 아닌 '수집실패'로 정확 표기),
    update_coverage_baseline 이 그날을 평소값에 넣지 않아 baseline 오염을 막는다.
    """
    respx.get(BIZINFO_URL).mock(
        return_value=httpx.Response(200, json={"reqErr": "존재하지 않는 인증키 입니다."}))
    with pytest.raises(RuntimeError, match="기업마당 API 오류"):
        monitor.fetch_bizinfo(_site())


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


# ── 실패 신호 규약 회귀 (커버리지 '0건 급락' 오탐 방지) ────────────────────────
def test_bizinfo_http_failure_page1_raises(monkeypatch):
    """1페이지 HTTP 접속 실패(재시도 소진) → 빈 리스트가 아니라 RuntimeError.

    과거엔 조용히 [] 를 반환해 fetch_success=True·item_count=0 →
    커버리지가 '0건 급락'(정상 응답인데 0건)으로 오분류했다. 이제 '수집실패'로 잡힌다.
    """
    monkeypatch.setattr(monitor, "_HTTP_RETRY_BACKOFF", 0)
    with respx.mock:
        respx.get(BIZINFO_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(RuntimeError, match="접속 실패"):
            monitor.fetch_bizinfo({**_site(), "api_retries": 1})


def test_bizinfo_retry_recovers_transient_failure(monkeypatch):
    """일시적 5xx 블립은 api_retries 로 흡수 — 재시도 후 성공하면 정상 수집."""
    monkeypatch.setattr(monitor, "_HTTP_RETRY_BACKOFF", 0)
    payload = _load("bizinfo_sample.json")
    with respx.mock:
        route = respx.get(BIZINFO_URL)
        route.side_effect = [
            httpx.Response(500),                # page1 1차 시도 실패
            httpx.Response(200, json=payload),  # page1 재시도 성공(3건 < pageUnit → 종료)
        ]
        items = monitor.fetch_bizinfo({**_site(), "api_retries": 2})
    assert len(items) == 3


def test_bizinfo_partial_collection_preserved_no_raise(monkeypatch):
    """1페이지 수집 성공 후 2페이지 실패면 예외 대신 모은 만큼 부분 반환(가용 데이터 보존)."""
    monkeypatch.setattr(monitor, "_HTTP_RETRY_BACKOFF", 0)
    payload = _load("bizinfo_sample.json")  # 3건
    with respx.mock:
        route = respx.get(BIZINFO_URL)
        route.side_effect = [
            httpx.Response(200, json=payload),  # page1 성공(3건 ≥ pageUnit=2 → 다음 페이지로)
            httpx.Response(500),                # page2 실패 → 부분 반환
        ]
        site = {**_site(), "api_page_unit": 2, "api_max_pages": 3, "api_retries": 0}
        items = monitor.fetch_bizinfo(site)  # 예외 없이
    assert len(items) == 3  # page1 부분 수집분 보존


def test_bizinfo_hard_failure_classified_as_collect_fail(monkeypatch):
    """★ 사용자 버그 직결 회귀: 하드 실패가 커버리지에서 '수집실패'로 분류되고
    baseline(평소값)을 오염시키지 않는지 end-to-end 확인."""
    import coverage_alert

    def _raiser(_site_arg):
        raise RuntimeError("기업마당 API 오류: 인증키")

    monkeypatch.setitem(monitor.FETCHERS, "bizinfo_api", _raiser)
    site = {"id": "bizinfo", "name": "기업마당(Bizinfo)", "type": "bizinfo_api",
            "url": BIZINFO_URL, "enabled": True}
    rows = monitor.fetch_site_coverage([site], days_back=1)
    row = rows[0]
    assert row["fetch_success"] is False
    assert row["item_count"] == 0
    assert row["fetch_error"]  # 오류 메시지 존재

    baseline = {"bizinfo": [1443, 1440, 1445]}
    anomalies = coverage_alert.detect_coverage_anomalies(rows, baseline)
    assert len(anomalies) == 1
    assert anomalies[0]["reason"] == "수집실패"  # '0건 급락' 아님

    # baseline 미오염: 실패한 날은 append 되지 않아 median 이 0 으로 끌려가지 않는다
    updated = coverage_alert.update_coverage_baseline(baseline, rows)
    assert updated["bizinfo"] == [1443, 1440, 1445]
