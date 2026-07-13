"""한양대 창업지원단(Next.js SPA) JSON API 파서 회귀 테스트 — respx 오프라인 재생.

이 fetcher 의 핵심:
  ① 정적 HTML 에 목록이 없는 SPA → JSON API `/api/board/content?boardEnName=&page=N`
     의 data.list 를 파싱(contentId/title/regDate/categoryCodeName).
  ② 페이지 이동은 `page` 파라미터(서버가 pageNo 는 무시) → 멀티페이지 순회·중복 종료.
  ③ 상세 링크는 `/board/{보드}/view/{contentId}` 로 합성(딥링크).
  ④ 접속/JSON 실패는 조용한 [] 가 아니라 RuntimeError('수집실패')로 승격.
"""
import pathlib

import httpx
import pytest
import respx

import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "hanyang"
API = "https://startup.hanyang.ac.kr/api/board/content"

SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "hanyang_startup",
        "name": "한양대 창업지원단(신규사업공고)",
        "url": "https://startup.hanyang.ac.kr/board/startup_info/list",
        "is_aggregator": False,
        "max_pages": 3,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def _route():
    """page=1 → 3건, page=2 → 3건(다른 글), page>=3 → 빈 목록(→ 순회 종료)."""
    respx.get(API, params__contains={"page": "1"}).mock(
        return_value=httpx.Response(200, text=_load("content_page1.json")))
    respx.get(API, params__contains={"page": "2"}).mock(
        return_value=httpx.Response(200, text=_load("content_page2.json")))
    respx.get(API, params__contains={"page": "3"}).mock(
        return_value=httpx.Response(200, text=_load("content_empty.json")))


@respx.mock
def test_hanyang_collects_across_pages_with_deeplinks():
    _route()
    items = monitor.fetch_hanyang_startup(_site())

    # page1(3) + page2(3) 고유 6건, page3 빈 목록 → 종료
    assert len(items) == 6
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids))                      # 중복 없음

    for it in items:
        assert set(it) == SCHEMA_KEYS
        assert it["author"] == "한양대학교 창업지원단"
        assert it["source"] == "한양대 창업지원단(신규사업공고)"
        # 상세 딥링크(/board/startup_info/view/{contentId})
        assert it["link"].startswith("https://startup.hanyang.ac.kr/board/startup_info/view/")
        assert it["id"].startswith("hanyang_startup_")

    # 리터럴 검증: 첫 글 = contentId 4336
    first = items[0]
    assert first["link"].endswith("/view/4336")
    assert first["posted_date"] == "2026-07-13"           # regDate ISO → YYYY-MM-DD
    assert "행사" in first["description"]                  # categoryCodeName → [카테고리]


@respx.mock
def test_hanyang_board_name_extracted_from_url():
    """URL /board/<name>/list 에서 보드명 추출 → API boardEnName·view 링크에 반영."""
    respx.get(API).mock(return_value=httpx.Response(200, text=_load("content_page1.json")))
    site = {**_site(), "url": "https://startup.hanyang.ac.kr/board/notice/list", "max_pages": 1}
    items = monitor.fetch_hanyang_startup(site)
    assert items
    # 요청이 boardEnName=notice 로 나갔는지 확인
    sent = respx.calls.last.request
    assert "boardEnName=notice" in str(sent.url)
    assert all("/board/notice/view/" in it["link"] for it in items)


@respx.mock
def test_hanyang_http_error_raises_not_silent_zero():
    """접속 실패(5xx)는 조용한 [] 가 아니라 RuntimeError('수집실패')로 승격."""
    respx.get(API).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError):
        monitor.fetch_hanyang_startup(_site())
