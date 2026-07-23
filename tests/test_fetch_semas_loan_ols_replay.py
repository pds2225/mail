"""소진공 정책자금 온라인신청(semas_loan_ols) JSON AJAX 파서 회귀 테스트 — respx 오프라인 재생.

저장된 응답 픽스처를 respx 로 가로채(네트워크 0) `fetch_semas_loan_ols` 가
/ols/man/SMAN051M/search.do AJAX 를 pageNo 로 순회하며 정책자금 공지만 정확히
추출하는지 검증한다. 파서 회귀(필드 매핑·필터 분기·id 규칙·페이지 순회 중단)를
발송 전 빨간불로 잡는 안전망.

respx 매칭 정책: URL 매칭 + pageNo(비밀 아님) 파라미터로 페이지별 분기.
fetcher 는 POST 이므로 respx.post 로 라우팅한다. pageNo=1→page1, pageNo=2→page2,
이후(pageNo>=3)→빈 result 를 돌려주면 파서가 break 한다.
"""
import json
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "semas_loan_ols"
SEARCH_URL = "https://ols.semas.or.kr/ols/man/SMAN051M/search.do"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "semas_loan_ols",
        "name": "소진공 정책자금 온라인신청",
        "url": "https://ols.semas.or.kr/ols/man/SMAN051M/page.do",
        "is_aggregator": False,
        "max_pages": 3,
    }


def _load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def _route_pages():
    """pageNo=1→page1, pageNo=2→page2, 그 외→빈 result(파서 break 유도)."""
    respx.post(SEARCH_URL, data__contains={"pageNo": "1"}).mock(
        return_value=httpx.Response(200, json=_load("semas_page1.json")))
    respx.post(SEARCH_URL, data__contains={"pageNo": "2"}).mock(
        return_value=httpx.Response(200, json=_load("semas_page2.json")))
    # pageNo=3 (max_pages 기본/지정 3) → 빈 result → break
    respx.post(SEARCH_URL, data__contains={"pageNo": "3"}).mock(
        return_value=httpx.Response(200, json=_load("semas_empty.json")))


@respx.mock
def test_semas_extracts_policy_fund_notices_only():
    """추출 건수 == 정책자금 공지만(비대상 1건 필터), 9키 스키마 불변."""
    _route_pages()

    items = monitor.fetch_semas_loan_ols(_site())

    # page1: 대출정보(seq 5001) + '상환' 키워드(seq 5003) = 2건,
    #        '온라인 신청 시스템 점검 안내'(일반공지·키워드 없음) = 필터됨
    # page2: 대출정보(seq 없음, stable_id 폴백) = 1건
    # 총 3건
    assert len(items) == 3

    for it in items:
        # 9키 + region_field(전국 소상공인 대상이라 nationwide 명시 — 발송 누락 방지 수정)
        assert set(it.keys()) == SCHEMA_KEYS | {"region_field"}
        assert it["region_field"] == "전국"
        assert it["is_aggregator"] is False
        assert it["source"] == "소진공 정책자금 온라인신청"
        assert it["author"] == "소상공인시장진흥공단"
        # link 는 항상 site["url"]
        assert it["link"] == "https://ols.semas.or.kr/ols/man/SMAN051M/page.do"


@respx.mock
def test_semas_first_item_fields_literal():
    """대출정보 카드(seq 5001)의 id/title/posted/description 이 픽스처 리터럴과 일치."""
    _route_pages()

    items = monitor.fetch_semas_loan_ols(_site())
    by_id = {it["id"]: it for it in items}

    # id 규칙: semas_loan_ols_{seq}_{bbsTypeCd}
    target = by_id["semas_loan_ols_5001_10"]
    assert target["title"] == "2026년 소상공인 정책자금 융자 신청 안내"
    # frstRegDt "2026.06.15" → extract_date_from_text → "2026-06-15"
    assert target["posted_date"] == "2026-06-15"
    assert target["deadline"] == ""
    # description: 대출구분 / 구분 / 공지번호 (비어있지 않은 부분만 ' / ' 결합)
    assert target["description"] == "대출구분: 직접대출 / 구분: 대출정보 / 공지번호: 5001"


@respx.mock
def test_semas_keyword_only_notice_included():
    """category 가 대출정보 아니어도 제목에 '상환' 키워드 있으면 포함(seq 5003)."""
    _route_pages()

    items = monitor.fetch_semas_loan_ols(_site())
    by_id = {it["id"]: it for it in items}

    target = by_id["semas_loan_ols_5003_20"]
    assert target["title"] == "긴급경영안정자금 상환 일정 변경 공지"
    assert target["posted_date"] == "2026-06-13"
    # 일반공지 카드 → description 의 '구분'은 일반공지
    assert target["description"] == "대출구분: 대리대출 / 구분: 일반공지 / 공지번호: 5003"

    # 필터로 빠진 비대상 카드(seq 5002)는 결과에 없음
    assert "semas_loan_ols_5002_20" not in by_id


@respx.mock
def test_semas_id_fallback_when_no_seq():
    """seq 없는 page2 카드는 semas_loan_ols_{stable_id(title)} 폴백 id 가 생성된다."""
    _route_pages()

    items = monitor.fetch_semas_loan_ols(_site())

    title = "정책자금 보증 연계 대출 추가 모집"
    expected = f"semas_loan_ols_{monitor.stable_id(title)}"
    fallback = next(it for it in items if it["title"] == title)

    assert fallback["id"] == expected
    assert fallback["posted_date"] == "2026-06-10"
    # seq 가 비어 description 의 '공지번호' 부분은 생략됨
    assert fallback["description"] == "대출구분: 보증부대출 / 구분: 대출정보"


@respx.mock
def test_semas_empty_result_breaks_pagination():
    """첫 페이지부터 빈 result 면 즉시 break → items == []."""
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"result": []}))

    assert monitor.fetch_semas_loan_ols(_site()) == []


@respx.mock
def test_semas_missing_result_key_returns_empty():
    """result 키 자체가 없으면 안전하게 빈 결과(빨간불)."""
    respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"}))

    assert monitor.fetch_semas_loan_ols(_site()) == []


@respx.mock
def test_semas_http_error_returns_empty():
    """search.do 가 500 이면 except 로 빈 리스트 반환(발송 차단 아님)."""
    respx.post(SEARCH_URL).mock(return_value=httpx.Response(500))

    assert monitor.fetch_semas_loan_ols(_site()) == []
