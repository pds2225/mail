"""NIPA(정보통신산업진흥원) HTML 파서 회귀 테스트 — respx 오프라인 재생.

저장된 HTML 픽스처를 respx 로 가로채(네트워크 0) `fetch_nipa` 가 curPage
페이지네이션을 순회하며 a[href*='nttDetail'] 공고를 정확히 추출하는지 검증한다.
이 fetcher 가 고친 버그 = 과거 1페이지(10건)만 받아 **대량 누락**(실측 tab=2만 390건)
한 것이므로, "여러 페이지 순회 + 중복 종료" 가 핵심 회귀 포인트다.

respx 매칭 정책: NIPA 는 params 에 비밀키가 없으므로 `curPage` 로 분기 매칭해
1페이지(신규 카드들)·2페이지(전부 중복 → page_new==0 → 루프 종료)에 서로 다른
HTML 을 돌려준다. 그래야 ① 멀티페이지 순회 ② link 기준 중복제거 ③ 신규 0이면
break 가 실제로 동작하는지 검증된다.
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "nipa"
NIPA_URL = "https://www.nipa.kr/home/bsnsAll/0/nttList?bbsNo=4&tab=2"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}

# 픽스처에 넣은 리터럴 값(동어반복 방지 — src 와 비교하지 않고 하드코딩)
LINK_40001 = "https://www.nipa.kr/home/bsnsAll/0/nttDetail?bbsNo=4&nttNo=40001&tab=2"
LINK_40002 = "https://www.nipa.kr/home/bsnsAll/0/nttDetail?bbsNo=4&nttNo=40002&tab=2"
LINK_40003 = "https://www.nipa.kr/home/bsnsAll/0/nttDetail?bbsNo=4&nttNo=40003&tab=2"
# nttNo 없는 카드 → 안정 id 폴백. stable_id 는 결정론적이라 리터럴로 고정.
LINK_NONNO = "https://www.nipa.kr/home/bsnsAll/0/nttDetail?bbsNo=4&tab=2&searchKey=hangul"
TITLE_NONNO = "2026년 디지털 콘텐츠 글로벌 진출 지원 공고"
ID_NONNO = "nipa_3a1daca1ae2b08079aab"


def _site():
    return {
        "id": "nipa",
        "name": "정보통신산업진흥원(NIPA)",
        "url": NIPA_URL,
        "is_aggregator": False,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def _route_pages():
    """curPage=1 → 신규 카드 HTML, curPage=2 → 전부 중복 HTML(→ 종료)."""
    respx.get(NIPA_URL, params__contains={"curPage": "1"}).mock(
        return_value=httpx.Response(200, html=_load("nipa_page1.html")))
    respx.get(NIPA_URL, params__contains={"curPage": "2"}).mock(
        return_value=httpx.Response(200, html=_load("nipa_page2.html")))


@respx.mock
def test_nipa_collects_all_cards_across_pages():
    """추출 총건수 == 1페이지 고유 카드 4건. 2페이지 전부 중복 → 종료(누락/중복 없음)."""
    _route_pages()

    items = monitor.fetch_nipa(_site())

    # 1) 유효 카드 4건. (제목 5자 미만 '공고' 카드는 스킵, nttDetail 아닌 링크는 무시)
    assert len(items) == 4

    # 스키마 불변(9키) + NIPA 전용 region_field='전국' 보강 + 고정 메타 필드.
    # region_field='전국': NIPA(국가기관 전국 ICT/SW/AI 사업)의 지역 미상 하드컷을 막아
    #  AI 키워드 그룹 본문 상단에 정상 노출되게 하는 recall 보정(전국 공고로 인정).
    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS | {"region_field"}
        assert it["region_field"] == "전국"
        assert it["author"] == "정보통신산업진흥원(NIPA)"
        assert it["description"] == ""
        assert it["source"] == "정보통신산업진흥원(NIPA)"
        assert it["is_aggregator"] is False

    # id 전수 고유(중복 누수 없음)
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids))


@respx.mock
def test_nipa_card_fields_literal():
    """카드별 id/title/link/posted/deadline 가 픽스처 리터럴과 정확히 일치."""
    _route_pages()

    items = monitor.fetch_nipa(_site())
    by_id = {it["id"]: it for it in items}

    # 카드 1: nttNo=40001 → 안정 id, 상대경로 './nttDetail' → 절대 link 조립,
    #         날짜 2개 → posted=첫번째, deadline=마지막
    c1 = by_id["nipa_40001"]
    assert c1["title"] == "2026년 ICT 융합 기술개발 지원사업 공고"
    assert c1["link"] == LINK_40001
    assert c1["posted_date"] == "2026-06-01"
    assert c1["deadline"] == "2026-06-30"

    # 카드 2: 절대경로 href(http로 시작) → 그대로 사용. 날짜 1개 → deadline 빈값.
    c2 = by_id["nipa_40002"]
    assert c2["title"] == "2026년 AI 바우처 지원사업 모집 공고"
    assert c2["link"] == LINK_40002
    assert c2["posted_date"] == "2026-06-05"
    assert c2["deadline"] == ""  # 날짜 1개뿐 → deadline 미배정

    # 카드 3: tr 부모, 날짜 3개 → posted=dates[0], deadline=dates[-1]
    c3 = by_id["nipa_40003"]
    assert c3["title"] == "2026년 SW 인재양성 콘텐츠 제작 지원 공고"
    assert c3["link"] == LINK_40003
    assert c3["posted_date"] == "2026-06-10"
    assert c3["deadline"] == "2026-06-09"  # dates[-1] (카드 텍스트의 마지막 날짜)


@respx.mock
def test_nipa_stable_id_fallback_when_no_nttno():
    """nttNo 파라미터 없는 카드는 nipa_<stable_id(title+link)> 폴백 id 가 생성된다."""
    _route_pages()

    items = monitor.fetch_nipa(_site())
    by_id = {it["id"]: it for it in items}

    # 폴백 id 가 존재
    assert ID_NONNO in by_id
    card = by_id[ID_NONNO]
    assert card["title"] == TITLE_NONNO
    assert card["link"] == LINK_NONNO
    # 폴백 id 는 결정론적: nipa_ + stable_id(title+link)
    assert card["id"] == "nipa_" + monitor.stable_id(TITLE_NONNO + LINK_NONNO)
    # dl 부모의 날짜 2개(2026-06-12 ~ 2026-08-01)
    assert card["posted_date"] == "2026-06-12"
    assert card["deadline"] == "2026-08-01"


@respx.mock
def test_nipa_short_title_and_nonmatching_link_excluded():
    """제목 5자 미만(스킵)·nttDetail 아닌 링크(무시)는 결과에 포함되지 않는다."""
    _route_pages()

    items = monitor.fetch_nipa(_site())
    links = [it["link"] for it in items]
    titles = [it["title"] for it in items]

    # 5자 미만 제목 '공고'(nttNo=99999) 카드는 스킵 → id/link 부재
    assert all("nttNo=99999" not in l for l in links)
    assert "공고" not in titles
    # nttDetail 아닌 'otherList' 링크는 애초에 매칭 안 됨
    assert all("otherList" not in l for l in links)


@respx.mock
def test_nipa_stops_when_page_all_duplicates():
    """2페이지가 전부 중복(page_new==0)이면 루프 종료 — 같은 link 중복 누수 없음."""
    _route_pages()

    items = monitor.fetch_nipa(_site())
    links = [it["link"] for it in items]

    # link 기준 전수 고유(페이지 간 중복 카드가 한 번만)
    assert len(links) == len(set(links))
    # 2페이지에도 있던 40001/40002 가 정확히 1건씩만
    assert links.count(LINK_40001) == 1
    assert links.count(LINK_40002) == 1


@respx.mock
def test_nipa_empty_page_returns_empty():
    """구조 깨짐 시나리오: 1페이지에 nttDetail 링크가 전혀 없으면 items == []."""
    empty_html = (
        "<html><body><div id='contents'>"
        "<a href='./otherList?tab=2'>관련 없는 링크</a>"
        "</div></body></html>"
    )
    respx.get(NIPA_URL).mock(return_value=httpx.Response(200, html=empty_html))

    assert monitor.fetch_nipa(_site()) == []
