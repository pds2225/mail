"""K-Startup(창업진흥원) HTML 파서 회귀 테스트 — respx 오프라인 재생.

저장된 HTML 픽스처를 respx 로 가로채(네트워크 0) `fetch_kstartup` 이 공공
(PBC010)·민간(PBC020) 공고를 **둘 다** 정확히 추출하는지 검증한다. 이 fetcher
가 고친 버그 = 과거 PBC010(공공)만 받아 **민간 공고를 전부 누락**한 것이므로,
"공공+민간 둘 다 수집됨"이 핵심 회귀 포인트다.

respx 매칭 정책(예외 메모): bizinfo 재생은 crtfcKey **비밀키 종속 방지**를 위해
URL 만 매칭했지만, k-startup params 엔 비밀키가 없으므로 `pbancClssCd` 로 매칭해
공공/민간에 서로 다른 HTML 을 돌려준다 — 그래야 둘 다 수집됨을 실제로 검증할 수
있다(같은 HTML 을 두 번 주면 seen_sn 중복제거로 공공/민간 구분이 사라진다).
"""
import pathlib

import httpx
import pytest
import respx

# conftest.py 가 import 전 env 를 setdefault 로 보장하므로 import 안전.
import monitor

FX = pathlib.Path(__file__).parent.parent / "fixtures" / "kstartup"
KSTARTUP_URL = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"

# 9키 스키마 (monitor._item 반환 키)
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site():
    return {
        "id": "kstartup",
        "name": "K-Startup",
        "url": KSTARTUP_URL,
        "is_aggregator": False,
    }


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


def _route_public_private():
    """PBC010→공공 HTML, PBC020→민간 HTML 로 분기 라우팅."""
    respx.get(KSTARTUP_URL, params__contains={"pbancClssCd": "PBC010"}).mock(
        return_value=httpx.Response(200, html=_load("kstartup_public.html")))
    respx.get(KSTARTUP_URL, params__contains={"pbancClssCd": "PBC020"}).mock(
        return_value=httpx.Response(200, html=_load("kstartup_private.html")))


@respx.mock
def test_kstartup_collects_public_and_private():
    """추출 총건수 == 공공+민간 고유 카드 수, 9키 스키마 불변."""
    _route_public_private()

    items = monitor.fetch_kstartup(_site())

    # 1) 추출 총건수 == 공공 2(sn 1001,1002) + 민간 고유 2(sn 2001,2002).
    #    민간의 sn=1001 카드는 공공과 중복 → seen_sn 으로 스킵 = 4건.
    assert len(items) == 4

    # 스키마 불변: 모든 item 이 9키를 전부 보유
    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS
        # site dict 의 is_aggregator=False 가 그대로 반영
        assert it["is_aggregator"] is False
        assert it["source"] == "K-Startup"


@respx.mock
def test_kstartup_both_classes_present_in_links():
    """공공(PBC010)·민간(PBC020)이 결과 link 에 각각 ≥1 (민간 누락 회귀 차단)."""
    _route_public_private()

    items = monitor.fetch_kstartup(_site())
    links = [it["link"] for it in items]

    public = [l for l in links if "pbancClssCd=PBC010" in l]
    private = [l for l in links if "pbancClssCd=PBC020" in l]

    assert len(public) >= 1   # 공공 공고 1건 이상
    assert len(private) >= 1  # 민간 공고 1건 이상 (과거 버그면 0)
    # 구체 건수: 공공 2 + 민간 고유 2
    assert len(public) == 2
    assert len(private) == 2


@respx.mock
def test_kstartup_card_fields_literal():
    """특정 카드의 id/title/org/deadline/link 가 픽스처 리터럴과 일치(필드 매핑 회귀)."""
    _route_public_private()

    items = monitor.fetch_kstartup(_site())
    by_id = {it["id"]: it for it in items}

    # 공공 sn=1001 카드 — button[onclick] 숫자 1001 우선 추출
    pub = by_id["kstartup_1001"]
    assert pub["title"] == "2026년 공공 창업도약패키지 지원사업 공고"
    assert pub["author"] == "창업진흥원"           # span.list[0] = org
    assert pub["deadline"] == "2026-06-30"          # "마감일자" 포함 span, 라벨 제거
    assert pub["description"] == "공공기관 모집"    # .flag:not(.day):not(.flag_agency)
    assert pub["link"] == (
        f"{KSTARTUP_URL}?pbancClssCd=PBC010&schM=view&pbancSn=1001")

    # 민간 sn=2001 카드 — PBC020 link 구성 확인
    priv = by_id["kstartup_2001"]
    assert priv["title"] == "2026년 민간 주도 스케일업 투자유치 프로그램 공고"
    assert priv["author"] == "한국액셀러레이터협회"
    assert priv["deadline"] == "2026-08-20"
    assert priv["link"] == (
        f"{KSTARTUP_URL}?pbancClssCd=PBC020&schM=view&pbancSn=2001")


@respx.mock
def test_kstartup_seen_sn_dedup():
    """같은 sn(1001)이 공공·민간 양쪽에 있어도 seen_sn 으로 1건만 남는다."""
    _route_public_private()

    items = monitor.fetch_kstartup(_site())
    ids = [it["id"] for it in items]

    # sn=1001 은 공공·민간 픽스처에 모두 존재하지만 결과엔 1개만
    assert ids.count("kstartup_1001") == 1
    # 그 1건은 먼저 도는 공공(PBC010) 패스에서 들어온다
    assert by_id_link(items, "kstartup_1001").endswith(
        "pbancClssCd=PBC010&schM=view&pbancSn=1001")
    # id 전수 고유(중복 sn 누수 없음)
    assert len(ids) == len(set(ids))


def by_id_link(items, iid):
    return next(it["link"] for it in items if it["id"] == iid)


@respx.mock
def test_kstartup_fetches_multiple_pages_when_configured():
    """max_pages>1 이면 pageIndex 2까지 요청(빈 페이지면 종료)."""
    _route_public_private()
    site = {**_site(), "max_pages": 2}
    items = monitor.fetch_kstartup(site)
    assert len(items) == 4
    assert len(respx.calls) >= 4  # PBC010 p1+p2 + PBC020 p1+p2 이상
