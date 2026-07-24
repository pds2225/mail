"""한국무역협회(KITA) HTML 파서 회귀 테스트 — respx 오프라인 재생.

저장된 HTML 픽스처를 respx 로 가로채(네트워크 0) `fetch_kita` 가 진행중 사업
공고를 정확히 추출하는지 검증한다. 파서 핵심 로직(onclick→sn 추출, 상세 URL
조립, 조상 li 카드 텍스트에서 '모집기간 …~…' 로 posted/deadline, '사업:'·
'지역:' 으로 desc 구성)의 회귀를 발송 전 빨간불로 잡는 안전망이다.

respx 매칭 정책: URL 만 매칭한다. fetch_kita 의 _soup 호출은 GET 에 query
param 을 붙이지 않으며 비밀키도 없으므로 URL 매칭으로 충분하다.

assert 는 픽스처 src 와 비교하는 동어반복이 아니라 **리터럴 하드코딩**이다 —
픽스처 HTML 에 내가 의도적으로 넣은 값(sn·제목·모집기간·사업·지역)이 파서를
거쳐 나오는 최종 필드 리터럴과 정확히 일치하는지를 못박는다.
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "kita"
KITA_URL = "https://www.kita.net/asocBiz/asocBiz/asocBizOngoingList.do"
DETAIL = "https://www.kita.net/asocBiz/asocBiz/asocBizOngoingView.do"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "kita",
        "name": "한국무역협회(KITA)",
        "url": KITA_URL,
        "is_aggregator": False,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def _route(html):
    respx.get(KITA_URL).mock(return_value=httpx.Response(200, html=html))


@respx.mock
def test_kita_extracts_expected_count_and_schema():
    """추출 건수 == 유효 카드 3건(노이즈 3건 제외), 9키 스키마·고정 필드 불변."""
    _route(_load("kita_ongoing_list.html"))

    items = monitor.fetch_kita(_site())

    # 리스트엔 a[onclick~=goDetailPage] 후보가 5개지만, goDetailPage 없는 일반
    # 링크 제외 + 5자 미만 제목 스킵 + 숫자 아닌 인자 continue → 유효 3건.
    assert len(items) == 3

    for it in items:
        # 스키마 불변: 모든 item 이 9키를 전부 보유
        assert set(it.keys()) == SCHEMA_KEYS
        # author·source·is_aggregator 는 고정값
        assert it["author"] == "한국무역협회(KITA)"
        assert it["source"] == "한국무역협회(KITA)"
        assert it["is_aggregator"] is False


@respx.mock
def test_kita_item1_fields_literal():
    """항목1: sn·title·link·desc(사업+지역)·posted·deadline 가 픽스처 리터럴과 일치."""
    _route(_load("kita_ongoing_list.html"))

    by_id = {it["id"]: it for it in monitor.fetch_kita(_site())}

    it = by_id["kita_202603046"]
    # id 규칙: kita_<sn>
    assert it["id"] == "kita_202603046"
    assert it["title"] == "2026년 무역아카데미 수출전문가 양성과정 참가기업 모집 공고"
    # 링크 조립: 상세 URL + ?sn=<sn>
    assert it["link"] == f"{DETAIL}?sn=202603046"
    # 모집기간 시작/마감 (점 표기 → 하이픈 변환)
    assert it["posted_date"] == "2026-03-04"
    assert it["deadline"] == "2026-04-20"
    # 사업 + 지역 둘 다 → "사업값 / 지역: 지역값"
    assert it["description"] == "인력양성 / 지역: 서울"


@respx.mock
def test_kita_item2_hyphen_dates_and_business_only():
    """항목2: 하이픈 표기 모집기간·사업만(지역 없음) → desc 에 '지역:' 없음."""
    _route(_load("kita_ongoing_list.html"))

    by_id = {it["id"]: it for it in monitor.fetch_kita(_site())}

    it = by_id["kita_202603099"]
    assert it["title"] == "중소기업 해외전시회 단체참가 지원 신청 안내"
    assert it["link"] == f"{DETAIL}?sn=202603099"
    # 하이픈 표기 날짜도 동일하게 추출
    assert it["posted_date"] == "2026-05-01"
    assert it["deadline"] == "2026-06-30"
    # 사업만 존재 → 지역 prefix 없음
    assert it["description"] == "수출마케팅"
    assert "지역:" not in it["description"]


@respx.mock
def test_kita_item3_no_period_fallback_posted_empty_deadline():
    """항목3: '모집기간' 없음 → deadline 빈값, posted 는 extract_date_from_text 폴백."""
    _route(_load("kita_ongoing_list.html"))

    by_id = {it["id"]: it for it in monitor.fetch_kita(_site())}

    it = by_id["kita_202601010"]
    assert it["title"] == "FTA 활용 원산지증명 실무 컨설팅 참가기업 상시 모집"
    assert it["link"] == f"{DETAIL}?sn=202601010"
    # 모집기간 패턴 없음 → deadline 은 빈 문자열
    assert it["deadline"] == ""
    # posted 는 카드 텍스트('등록일 2026.02.15 기준')의 첫 날짜로 폴백
    assert it["posted_date"] == "2026-02-15"
    # 지역만 존재
    assert it["description"] == "지역: 부산"


@respx.mock
def test_kita_noise_links_excluded():
    """노이즈 3종이 결과에서 빠진다: goDetailPage 없음·5자 미만·숫자 아닌 인자."""
    _route(_load("kita_ongoing_list.html"))

    items = monitor.fetch_kita(_site())
    ids = {it["id"] for it in items}
    titles = [it["title"] for it in items]

    # goDetailPage 없는 일반 링크 → onclick 매칭 안 됨
    assert "한국무역협회 사업안내 메인 페이지로 이동" not in titles
    # 5자 미만 제목('공고') → 스킵 (sn 202609999 결과 없음)
    assert "kita_202609999" not in ids
    # goDetailPage('event-banner') → 숫자 추출 실패 continue
    assert all("event" not in i for i in ids)
    # 정확히 유효 3건만
    assert ids == {"kita_202603046", "kita_202603099", "kita_202601010"}


@respx.mock
def test_kita_ids_unique_and_link_prefix():
    """id 전수 고유 + 모든 link 가 상세 URL prefix·sn 쿼리를 갖는다."""
    _route(_load("kita_ongoing_list.html"))

    items = monitor.fetch_kita(_site())
    ids = [it["id"] for it in items]

    assert len(ids) == len(set(ids))           # id 누수 없음
    for it in items:
        assert it["link"].startswith(f"{DETAIL}?sn=")
        # id 의 sn 과 link 의 sn 이 일치
        sn = it["id"].removeprefix("kita_")
        assert it["link"].endswith(f"?sn={sn}")


@respx.mock
def test_kita_empty_list_returns_empty():
    """구조 깨짐: goDetailPage 앵커가 하나도 없으면 items == [] (빨간불)."""
    _route("<html><body><ul><li>공지사항이 없습니다</li></ul></body></html>")
    assert monitor.fetch_kita(_site()) == []
