"""컨설턴트 신청·모집 공고 수집/강제포함 회귀 (네트워크/SMTP 없음).

배경: 기존 소스(기업마당·지자체 게시판·한국경영기술지도사회 등)에도
컨설턴트 모집 공고가 들어오지만, 그룹 필터가 기업 지원금 공고만 남기므로
CONSULTING_ONLY 등으로 메일에 안 실렸다. 정부24 지자체소식 검색 소스 +
워치리스트 키워드로 신청·모집 제목을 강제포함한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import monitor as m

ROOT = Path(__file__).resolve().parent.parent
SITES = json.loads((ROOT / "config/sites.json").read_text(encoding="utf-8"))
WL = json.loads((ROOT / "config/watchlist.json").read_text(encoding="utf-8"))
BY_ID = {site["id"]: site for site in SITES}

GOV24_CONSULTANT_URL = (
    "https://www.gov.kr/portal/locgovNews"
    "?srchTxt=%EC%BB%A8%EC%84%A4%ED%84%B4%ED%8A%B8&srchSort=01"
)
GOV24_MGMT_URL = (
    "https://www.gov.kr/portal/locgovNews"
    "?srchTxt=%EA%B2%BD%EC%98%81%EC%A7%80%EB%8F%84%EC%82%AC&srchSort=01"
)


def test_gov24_consultant_sources_registered_enabled():
    consultant = BY_ID["gov24_consultant"]
    mgmt = BY_ID["gov24_mgmt_consultant"]
    sibling = BY_ID["imp_73a18059"]

    assert consultant["enabled"] is True
    assert mgmt["enabled"] is True
    assert consultant["type"] == "html_table"
    assert mgmt["type"] == "html_table"
    assert consultant["url"] == GOV24_CONSULTANT_URL
    assert mgmt["url"] == GOV24_MGMT_URL
    assert consultant["selectors"]["row"] == sibling["selectors"]["row"] == "ul.list li"
    assert mgmt["selectors"]["row"] == "ul.list li"


def test_gov24_consultant_urls_are_unique():
    urls = [site["url"] for site in SITES]
    assert urls.count(GOV24_CONSULTANT_URL) == 1
    assert urls.count(GOV24_MGMT_URL) == 1


@pytest.mark.parametrize("title", [
    "경기도 규제샌드박스 컨설턴트 모집공고",
    "2026년 제주신용보증재단 컨설턴트 모집 재공고",
    "[마감]인천송림 소공인특화지원센터 컨설턴트 2차 모집공고",
    "「산업·일자리전환 지원센터」컨설턴트 추가 모집 공고",
    "충남광역새일센터 강사·컨설턴트 인력풀(Pool) 모집 공고",
    "2026년 일터혁신 상생컨설팅 수행 컨설턴트 모집",
    "2026년 소상공인 컨설턴트 신청공고",
    "경영지도사 모집 공고",
])
def test_watchlist_catches_consultant_application_titles(title):
    assert m.is_watchlisted({"title": title, "author": "기관"}, WL) is True


@pytest.mark.parametrize("title", [
    "인천 소재 중소기업 수출바우처 참여기업 모집",
    "2026년 소상공인 재도약 컨설팅 지원 모집 공고",
    "멘토링 단독 공고",
    "컨설팅지원 단독 공고",
])
def test_watchlist_ignores_company_grant_or_consulting_support_titles(title):
    assert m.is_watchlisted({"title": title, "author": "기관"}, WL) is False


def test_watchlist_ignores_consultant_mention_only_in_body():
    item = {
        "title": "일터혁신 상생컨설팅 지원사업 기업 모집 공고",
        "author": "한국능률협회컨설팅",
        "description": "수행기관에서 담당 컨설턴트를 배정하여 선정사업장으로 연락 드립니다.",
    }
    assert m.is_watchlisted(item, WL) is False


def test_existing_groups_still_exclude_consulting_only():
    """워치 강제포함과 별개로, 기업 그룹 필터의 CONSULTING_ONLY 는 유지."""
    groups = {g["id"]: g for g in json.loads(
        (ROOT / "config/groups.json").read_text(encoding="utf-8"))}
    item = {
        "title": "멘토링 단독 공고",
        "description": "멘토링만 제공합니다",
        "deadline": "2099-12-31",
        "posted_date": "2026-08-13",
    }
    ev = m.evaluate_notice(item, groups["grp_ai_saas"])
    assert ev["is_relevant"] is False
    assert "CONSULTING_ONLY" in ev["exclude_reason_codes"]


GOV24_LIST_HTML = """
<html><body>
<ul class="list">
  <li>
    <a href="/portal/locgovNews/9001">경기도 규제샌드박스 컨설턴트 모집공고</a>
    <span class="date">2026.08.12</span>
  </li>
  <li>
    <a href="/portal/locgovNews/9002">2026년 소상공인 컨설턴트 신청공고</a>
    <span class="date">2026.08.11</span>
  </li>
</ul>
</body></html>
"""


def test_gov24_consultant_html_table_parses_list_items(monkeypatch):
    monkeypatch.setattr(
        m, "_soup", lambda url, **kw: BeautifulSoup(GOV24_LIST_HTML, "html.parser"))
    items = m.fetch_html_generic(BY_ID["gov24_consultant"])
    assert len(items) == 2
    assert items[0]["title"] == "경기도 규제샌드박스 컨설턴트 모집공고"
    assert items[0]["link"].endswith("/portal/locgovNews/9001")
    assert items[1]["title"] == "2026년 소상공인 컨설턴트 신청공고"
