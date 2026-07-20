"""수출바우처(exportvoucher) HTML 파서 회귀 테스트 — respx 오프라인 재생.

저장된 목록 HTML 픽스처를 respx 로 가로채(네트워크 0) `fetch_exportvoucher` 가
goDetail(...) 링크에서 공고를 정확히 추출하는지 검증한다. 이 fetcher 는 목록
페이지를 `_soup`(GET)로 읽어 모든 `<a>` 태그에서 `goDetail(ntt_id[,bbs_id])` 를
정규식으로 뽑아내며(2인자=구버전, 1인자=개편 신버전), bbs_id 로 게시판/메뉴를
분기하고, NOISE(시스템점검 등) 제목을 거른다. playwright 미사용 → respx 재생 가능.

respx 매칭 정책: 목록 URL(boardList) 만 매칭한다. 비밀키 파라미터가 없고
multiple_calls 도 아니므로 단일 라우트로 충분하다.

assert 는 픽스처 src 와의 동어반복이 아니라 **리터럴 하드코딩**으로 검증한다:
추출 건수, title/link/id/author/posted/deadline 의 구체 리터럴 값, id 규칙,
bbs_id 분기(menu 코드)·NOISE 필터·게시판 제외·짧은 제목 스킵·구조 깨짐 안전 처리.
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "exportvoucher"
LIST_URL = (
    "https://www.exportvoucher.com/portal/board/boardList"
    "?bbs_id=1&active_menu_cd=EZ005004000"
)
BASE = "https://www.exportvoucher.com"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "exportvoucher",
        "name": "수출바우처(수출지원기반활용)",
        "url": LIST_URL,
        "is_aggregator": False,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def _route(html_name="exportvoucher_list.html"):
    # boardList URL 만 매칭(파라미터 무관, 단일 호출)
    respx.get(url__startswith=BASE + "/portal/board/boardList").mock(
        return_value=httpx.Response(200, html=_load(html_name)))


@respx.mock
def test_exportvoucher_extracts_expected_items():
    """추출 건수 == 유효 항목 3건, 9키 스키마 불변, 공통 메타 리터럴."""
    _route()

    items = monitor.fetch_exportvoucher(_site())

    # 1) 유효 항목 3건만:
    #    - 1001(공지,2인자) / 2002(자료실,2인자) / 3003(1인자 default bbs)
    #    제외: 4004(NOISE 시스템점검), 5005(bbs_id=3 FAQ), 6006("공지" <5자),
    #          goDetail 없는 메인 링크
    assert len(items) == 3

    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS
        assert it["is_aggregator"] is False          # site dict False 반영
        assert it["source"] == "수출바우처(수출지원기반활용)"
        assert it["author"] == "수출바우처(KOTRA/중진공)"
        # 날짜는 목록에서 못 읽어 빈 값(상세 enrich 의존)
        assert it["posted_date"] == ""
        assert it["deadline"] == ""
        assert it["description"] == ""


@respx.mock
def test_exportvoucher_notice_item_literal():
    """공지(bbs_id=1, 2인자) 항목의 id/title/link 가 리터럴과 정확히 일치."""
    _route()
    by_id = {it["id"]: it for it in monitor.fetch_exportvoucher(_site())}

    notice = by_id["exportvoucher_1001"]
    assert notice["title"] == "2026년 수출바우처 참여기업 모집 공고"
    # bbs_id=1 → menu EZ005004000, link 는 boardView GET 으로 재구성
    assert notice["link"] == (
        f"{BASE}/portal/board/boardView"
        f"?bbs_id=1&ntt_id=1001&active_menu_cd=EZ005004000")


@respx.mock
def test_exportvoucher_archive_item_literal():
    """자료실(bbs_id=2, 2인자) 항목 → menu EZ005005000 분기 리터럴 검증."""
    _route()
    by_id = {it["id"]: it for it in monitor.fetch_exportvoucher(_site())}

    archive = by_id["exportvoucher_2002"]
    assert archive["title"] == "수출바우처 사업운영 지침 자료 안내"
    assert archive["link"] == (
        f"{BASE}/portal/board/boardView"
        f"?bbs_id=2&ntt_id=2002&active_menu_cd=EZ005005000")


@respx.mock
def test_exportvoucher_single_arg_uses_default_bbs():
    """1인자 goDetail(3003) → URL 의 bbs_id=1 기본값 적용(개편 신버전 회귀 차단)."""
    _route()
    by_id = {it["id"]: it for it in monitor.fetch_exportvoucher(_site())}

    single = by_id["exportvoucher_3003"]
    assert single["title"] == "개편 신버전 단일인자 수출바우처 추가 공고"
    # bbs_id 인자 없음 → default_bbs="1" → menu EZ005004000
    assert single["link"] == (
        f"{BASE}/portal/board/boardView"
        f"?bbs_id=1&ntt_id=3003&active_menu_cd=EZ005004000")


@respx.mock
def test_exportvoucher_noise_and_excluded_filtered():
    """NOISE(시스템점검)·제외게시판(bbs_id=3)·짧은제목 항목이 결과에 없다."""
    _route()
    ids = {it["id"] for it in monitor.fetch_exportvoucher(_site())}

    assert "exportvoucher_4004" not in ids   # 시스템 점검 NOISE
    assert "exportvoucher_5005" not in ids   # bbs_id=3 (FAQ 등) 제외
    assert "exportvoucher_6006" not in ids   # 제목 "공지" 5자 미만 스킵
    # 추출된 id 는 정확히 이 3개뿐
    assert ids == {
        "exportvoucher_1001",
        "exportvoucher_2002",
        "exportvoucher_3003",
    }


@respx.mock
def test_exportvoucher_id_rule():
    """id 규칙: exportvoucher_<ntt_id> (ntt_id 그대로 사용)."""
    _route()
    items = monitor.fetch_exportvoucher(_site())

    for it in items:
        assert it["id"].startswith("exportvoucher_")
        # 접미부가 순수 숫자(ntt_id)인지
        assert it["id"].split("exportvoucher_", 1)[1].isdigit()


@respx.mock
def test_exportvoucher_empty_html_returns_empty():
    """구조 깨짐 1: a 태그/goDetail 이 전혀 없으면 items == [] (빨간불)."""
    respx.get(url__startswith=BASE + "/portal/board/boardList").mock(
        return_value=httpx.Response(
            200, html="<html><body><p>no anchors here</p></body></html>"))

    assert monitor.fetch_exportvoucher(_site()) == []


@respx.mock
def test_exportvoucher_http_error_returns_empty():
    """구조 깨짐 2: 접속 실패(404)면 _soup 가 None → items == [] 안전 처리."""
    respx.get(url__startswith=BASE + "/portal/board/boardList").mock(
        return_value=httpx.Response(404))

    assert monitor.fetch_exportvoucher(_site()) == []
