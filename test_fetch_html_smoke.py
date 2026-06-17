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
