"""0건 수집소 복구 회귀 테스트 — 신규 AJAX fetcher(KOTRA 사업신청·KOSME) respx 오프라인.

검증: kotra_biz_api(POST HTML fragment, javascript 링크 합성·신청기간 파싱),
kosme_api(POST JSON ds_infoList), 9키 스키마, FETCHERS 등록.
"""
import os
import sys
from pathlib import Path

import httpx
import respx

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor  # noqa: E402

SCHEMA = {"id", "title", "link", "author", "description", "deadline",
          "source", "posted_date", "is_aggregator"}


def test_fetchers_registered():
    assert monitor.FETCHERS.get("kotra_biz_api") is monitor.fetch_kotra_biz
    assert monitor.FETCHERS.get("kosme_api") is monitor.fetch_kosme


@respx.mock
def test_kotra_biz_parses_card_fragment():
    frag = """<div class="card">
      <a class="card-tit" href="javascript:fn_selectBizMntInfoDetailNew('/subList/20000020753/subhome/bizAply/selectBizMntInfoDetail.do?&amp;dtlBizMntNo=26CN0HE&amp;cpbizYn=N')">2026 파워셀러 육성사업</a>
      <dl class="card-meta-data"><dt>신청기간</dt><dd>2026-06-09 ~ 2026-07-02</dd></dl>
    </div>"""
    respx.get("https://www.kotra.or.kr/subList/20000020753").mock(
        return_value=httpx.Response(200, html="<html></html>"))
    respx.post("https://www.kotra.or.kr/module/subhome/bizAply/selectBmBizAllListAjax.do").mock(
        side_effect=lambda req: httpx.Response(200, html=frag if b"pageNo=1" in req.content else ""))
    site = {"id": "kotra_trade24", "name": "KOTRA 무역투자24 - 사업공고",
            "type": "kotra_biz_api", "url": "https://www.kotra.or.kr/subList/20000020753",
            "is_aggregator": False, "max_pages": 2}
    items = monitor.fetch_kotra_biz(site)
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "2026 파워셀러 육성사업"
    assert "dtlBizMntNo=26CN0HE" in it["link"] and it["link"].startswith("https://www.kotra.or.kr")
    assert it["deadline"] == "2026-06-09 ~ 2026-07-02"
    assert set(it.keys()) == SCHEMA


@respx.mock
def test_kosme_parses_json_list():
    payload = {"ds_infoList": [
        {"TITL_NM": "2026년 중진공 사업공고", "SLNO": "12345",
         "REG_DTM": "2026-06-30", "VALI_DT": "2026-07-31"},
        {"TITL_NM": "", "SLNO": "0"},  # 무제목 → 스킵
    ]}
    respx.get("https://www.kosmes.or.kr/nsh/SH/NTS/SHNTS001M0.do").mock(
        return_value=httpx.Response(200, html="<html></html>"))
    respx.post("https://www.kosmes.or.kr/sh/nts/notice_list.json").mock(
        return_value=httpx.Response(200, json=payload))
    site = {"id": "kosme", "name": "중소벤처기업진흥공단(KOSME)", "type": "kosme_api",
            "url": "https://www.kosmes.or.kr/nsh/SH/NTS/SHNTS001M0.do", "is_aggregator": False}
    items = monitor.fetch_kosme(site)
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "2026년 중진공 사업공고"
    assert "seqNo=12345" in it["link"]
    assert it["posted_date"] == "2026-06-30"
    assert it["deadline"] == "2026-07-31"
    assert set(it.keys()) == SCHEMA


def test_broken_scraper_sites_have_valid_fetchers():
    """수정한 사이트들의 type 이 FETCHERS 에 실제 존재(오타·미등록 방지)."""
    import json
    sites = json.loads((Path(__file__).resolve().parent / "sites.json").read_text(encoding="utf-8"))
    by = {s.get("id"): s for s in sites}
    assert by["kotra_trade24"]["type"] == "kotra_biz_api"
    assert by["kosme"]["type"] == "kosme_api"
    assert by["kotra"]["enabled"] is False   # 중복 비활성
    assert by["gbsa"]["enabled"] is False     # playwright 필요 비활성
    for s in sites:
        if s.get("enabled"):
            assert s.get("type") in monitor.FETCHERS, f"미등록 type: {s.get('type')} ({s.get('id')})"
