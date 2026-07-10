"""TIPA(중소기업기술정보진흥원) HTML 파서 회귀 테스트 — respx 오프라인 재생.

이 fetcher 가 고친 버그 = tipa.or.kr(CodeIgniter)이 세션쿠키·Referer 없는 직접 GET 을
"The action you have requested is not allowed." 차단 페이지(HTTP 200, 테이블 0개)로
응답 → 기존 html_table 파서가 '진짜 0건'으로 오분류(수집 실패 미감지)했다.
핵심 회귀 포인트:
  ① 정상 목록(세션 예열 후) 에서 td.subject a 공고를 딥링크와 함께 정확히 추출
  ② 차단/구조변경(테이블 0행) 시 조용한 [] 가 아니라 RuntimeError('수집실패')로 승격
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "tipa"
LIST_URL = "https://www.tipa.or.kr/s040101/index/page/1"
HOME_URL = "https://www.tipa.or.kr/"

SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "imp_fae5a127",
        "name": "중소기업기술정보진흥원(TIPA)",
        "url": LIST_URL,
        "is_aggregator": False,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


@respx.mock
def test_tipa_parses_list_with_deeplinks():
    """세션 예열 후 목록 파싱: 공고 10건, 스키마 준수, 상세 딥링크·등록일 추출."""
    respx.get(HOME_URL).mock(return_value=httpx.Response(200, html="<html>home</html>"))
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, html=_load("tipa_list.html")))

    items = monitor.fetch_tipa(_site())

    assert len(items) == 10
    for it in items:
        assert set(it) == SCHEMA_KEYS
        assert it["source"] == "중소기업기술정보진흥원(TIPA)"
        # javascript:/# 가 아니라 실제 상세 딥링크(/s040101/view/...)여야 한다.
        assert it["link"].startswith("https://www.tipa.or.kr/s040101/view/")
        assert it["id"].startswith("imp_fae5a127_")

    titles = [it["title"] for it in items]
    assert any("스마트공장" in t for t in titles)
    # 등록일이 최소 한 건 이상 YYYY-MM-DD 로 추출돼야 한다(목록 td 에서).
    assert any(it["posted_date"].count("-") == 2 for it in items)


@respx.mock
def test_tipa_blocked_page_raises_not_silent_zero():
    """차단 페이지(200·테이블 0행)는 조용한 0건이 아니라 RuntimeError('수집실패')로 승격."""
    respx.get(HOME_URL).mock(return_value=httpx.Response(200, html="<html>home</html>"))
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, html=_load("tipa_blocked.html")))

    with pytest.raises(RuntimeError):
        monitor.fetch_tipa(_site())


@respx.mock
def test_tipa_http_error_raises():
    """4xx/5xx 접속 실패도 RuntimeError 로 승격(커버리지 '수집실패' 정확 표기)."""
    respx.get(HOME_URL).mock(return_value=httpx.Response(200, html="<html>home</html>"))
    respx.get(LIST_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(RuntimeError):
        monitor.fetch_tipa(_site())
