"""HTML 일반화 증명 스모크 — fetch_html_generic respx 오프라인 재생.

`_soup` 경유 HTML 파서(`fetch_html_generic`)가 저장된 HTML 픽스처를 정상
파싱하는지 1회 실증한다. 대표 사이트는 sites.json 의 `msit`(html_table,
표준 `table tbody tr` row, 기본 <a> 링크 추출).

scope creep 가드: 이 스모크는 패턴 일반화 1회 증명용. 추출 행 수 + 첫 행
title/link 정확성만 검증한다(selector 전수·추가 사이트·SSL 폴백 경로는 후속).

respx 매칭 정책: URL 만 매칭(params 검증 없음). 정상 200 이면 `_soup` 의
3단계 SSL 폴백 중 첫 strict 단계에서 즉시 성공한다.
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "msit"
MSIT_URL = "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=113&mPid=112"


def _site():
    return {
        "id": "msit",
        "name": "과학기술정보통신부",
        "type": "html_table",
        "url": MSIT_URL,
        "is_aggregator": False,
        "selectors": {"row": "table tbody tr"},
    }


@respx.mock
def test_html_generic_smoke():
    html = (FX / "msit_sample.html").read_text(encoding="utf-8")
    respx.get(MSIT_URL).mock(return_value=httpx.Response(200, html=html))

    items = monitor.fetch_html_generic(_site())

    # 1) 추출 행 수 == 픽스처 행 수(tbody tr 2개)
    assert len(items) == 2

    # 2) 첫 행 title/link 정확
    first = items[0]
    assert first["title"] == "2026년 정보통신방송 기술개발사업 신규지원 공고"
    assert first["link"] == (
        "https://www.msit.go.kr/bbs/view.do"
        "?sCode=user&mId=113&mPid=112&bbsSeqNo=101"
    )


# ── 실패 신호 규약 (커버리지 '0건 급락' 오탐 방지) ─────────────────────────────
# 접속/파싱 실패(soup=None)는 '진짜 0건'과 다르다 → fetcher 가 예외를 올려야
# fetch_site_coverage 가 fetch_success=False='수집실패'로 분류하고 baseline 오염을 막는다.
# (정상 응답인데 행 0개면 soup 는 truthy → [] 반환은 그대로 = 진짜 0건.)

@respx.mock
def test_html_generic_raises_on_fetch_failure():
    """KOTRA·KIAT 등 html_table: 접속 실패면 [] 가 아니라 RuntimeError."""
    respx.get(MSIT_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(RuntimeError, match="접속 실패"):
        monitor.fetch_html_generic(_site())


MSS_URL = "https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=310"


def _mss_site():
    return {"id": "mss", "name": "중소벤처기업부", "type": "mss_html", "url": MSS_URL}


@respx.mock
def test_mss_smoke_minimal():
    """중기부(fetch_mss) 정상 파싱 1회 실증(번호→상세 URL, 날짜 추출)."""
    html = ('<table><tbody><tr>'
            '<td>12345</td>'
            '<td><a href="#view">중소벤처 지원사업 신규 공고</a></td>'
            '<td>2026.07.01</td></tr></tbody></table>')
    respx.get(MSS_URL).mock(return_value=httpx.Response(200, html=html))
    items = monitor.fetch_mss(_mss_site())
    assert len(items) == 1
    assert items[0]["id"] == "mss_12345"
    assert items[0]["link"].endswith("bcIdx=12345")
    assert "중소벤처" in items[0]["title"]
    assert items[0]["posted_date"] == "2026-07-01"


@respx.mock
def test_mss_raises_on_fetch_failure():
    """중기부(fetch_mss): 접속 실패면 [] 가 아니라 RuntimeError."""
    respx.get(MSS_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(RuntimeError, match="접속 실패"):
        monitor.fetch_mss(_mss_site())


# ── _soup 일시적 실패 재시도 규약 ─────────────────────────────────────────────
@respx.mock
def test_soup_retries_on_network_error(monkeypatch):
    """네트워크/타임아웃 등 일시적 실패는 _HTTP_RETRIES 만큼 재시도한다.

    재시도 1회 → (1+1) 시도 × 3 SSL 단계 = 6 요청 후 None(단발 블립 흡수 목적)."""
    monkeypatch.setattr(monitor, "_HTTP_RETRY_BACKOFF", 0)
    monkeypatch.setattr(monitor, "_HTTP_RETRIES", 1)
    route = respx.get(MSIT_URL).mock(side_effect=httpx.ConnectError("boom"))
    soup = monitor._soup(MSIT_URL)
    assert soup is None
    assert route.call_count == 6


@respx.mock
def test_soup_no_retry_on_http_status_error(monkeypatch):
    """4xx/5xx(HTTPStatusError)는 페이지 수준 오류 → 재시도 없이 즉시 None(1 요청)."""
    monkeypatch.setattr(monitor, "_HTTP_RETRIES", 1)
    route = respx.get(MSIT_URL).mock(return_value=httpx.Response(404))
    soup = monitor._soup(MSIT_URL)
    assert soup is None
    assert route.call_count == 1
