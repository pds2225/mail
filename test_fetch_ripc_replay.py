"""RIPC(지역지식재산센터 PMS) JSON API 파서 회귀 테스트 — respx 오프라인 재생(네트워크 0).

검증 포인트:
- getNoticeList.do(JSON)에서 noticeTitle/writeTimeStr/start~endDateStr/centerName 정확 매핑
- 페이징은 currentPageNo (currentPage/pageIndex 는 서버가 무시) — 2페이지 누적 수집
- noticeSeq 기준 dedup, 9키 스키마 불변
"""
import json
import pathlib  # noqa: F401
import sys
import os

import httpx
import respx

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import monitor  # noqa: E402

API = "https://pms.ripc.org/pms/biz/applicant/notice/getNoticeList.do"
SCHEMA_KEYS = {"id", "title", "link", "author", "description",
               "deadline", "source", "posted_date", "is_aggregator"}


def _rec(seq, title, center, write, sd, ed):
    return {"noticeSeq": seq, "noticeTitle": title, "centerName": center,
            "writeTimeStr": write, "startDateStr": sd, "endDateStr": ed,
            "bizCategory1Name": "지식재산", "bizCategory2Name": "", "noticeNo": f"NO-{seq}"}


def _page(records, total_pages=2):
    return {"result": {"totalPageCount": total_pages, "totalRecordCount": 15,
                       "recordCountPerPage": 10, "noticeList": records}}


def _site(max_pages=5):
    return {"id": "ripc_pms_notice", "name": "지역지식재산센터(RIPC) 사업공고",
            "type": "ripc_api", "url": "https://pms.ripc.org/pms/biz/applicant/notice/list.do",
            "is_aggregator": False, "max_pages": max_pages}


def _route(pages):
    """currentPageNo 값에 따라 다른 페이지 JSON 반환(currentPage/pageIndex 는 무시 검증)."""
    def handler(request):
        body = request.content.decode("utf-8")
        # form: currentPageNo=N
        import urllib.parse
        q = urllib.parse.parse_qs(body)
        no = (q.get("currentPageNo") or ["1"])[0]
        return httpx.Response(200, json=pages.get(no, pages["1"]))
    respx.post(API).mock(side_effect=handler)
    # 목록 페이지 GET(세션쿠키)도 가짜 응답
    respx.get("https://pms.ripc.org/pms/biz/applicant/notice/list.do").mock(
        return_value=httpx.Response(200, html="<html></html>"))


@respx.mock
def test_ripc_collects_and_maps_fields():
    p1 = _page([_rec(4783, "[부산]글로벌 IP스타기업 육성", "부산", "2026-06-30",
                     "2026-06-30 13:00", "2026-07-16 23:00")], total_pages=2)
    p2 = _page([_rec(4773, "[인천]지식재산 창출 지원", "인천", "2026-06-29",
                     "2026-06-29 09:00", "2026-07-10 18:00")], total_pages=2)
    _route({"1": p1, "2": p2})

    items = monitor.fetch_ripc(_site(max_pages=5))

    # 2페이지 누적 = 2건(페이지당 1건), totalPages=2 에서 break
    assert len(items) == 2
    by_id = {it["id"]: it for it in items}
    a = by_id["ripc_pms_notice_4783"]
    assert a["title"] == "[부산]글로벌 IP스타기업 육성"
    assert a["posted_date"] == "2026-06-30"
    assert a["deadline"] == "2026-06-30 ~ 2026-07-16"   # start ~ end
    assert "부산" in a["author"]
    assert a["source"] == "지역지식재산센터(RIPC) 사업공고"
    assert set(a.keys()) == SCHEMA_KEYS
    assert "이천" not in by_id  # sanity


@respx.mock
def test_ripc_dedup_by_notice_seq():
    """같은 noticeSeq 가 여러 페이지에 나와도 1건."""
    dup = _rec(4783, "[부산]중복공고", "부산", "2026-06-30", "2026-06-30 13:00", "2026-07-16 23:00")
    _route({"1": _page([dup], total_pages=3), "2": _page([dup], total_pages=3),
            "3": _page([dup], total_pages=3)})
    items = monitor.fetch_ripc(_site(max_pages=3))
    assert len(items) == 1 and items[0]["id"] == "ripc_pms_notice_4783"


@respx.mock
def test_ripc_registered_in_fetchers():
    assert monitor.FETCHERS.get("ripc_api") is monitor.fetch_ripc
