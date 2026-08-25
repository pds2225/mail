"""IITP 사업공고(ezone 메인) HTML 파서 회귀 — respx 오프라인 재생.

www.iitp.kr 사업공고 경로는 SPA 홈으로 리다이렉트되어 table 0건.
공개 목록은 ezone.iitp.kr/main/main 접수중 탭(#main_01).
onclick PMS_TSK_PBNC_ID 로 상세 URL을 합성한다. 로그인 불필요.
#main_04 중복 행은 셀렉터가 버린다.
"""
from __future__ import annotations

import json
import pathlib

import httpx
import pytest
import respx

import monitor

FX = pathlib.Path(__file__).parent / "fixtures" / "iitp"
LIST_URL = "https://ezone.iitp.kr/main/main"
SCHEMA_KEYS = {
    "id", "title", "link", "author", "description",
    "deadline", "source", "posted_date", "is_aggregator",
}


def _site_from_config() -> dict:
    sites = json.loads(pathlib.Path("config/sites.json").read_text(encoding="utf-8"))
    site = next(s for s in sites if s["id"] == "iitp")
    assert site["enabled"] is True
    assert site["type"] == "html_table"
    return site


def _load() -> str:
    return (FX / "ezone_main.html").read_text(encoding="utf-8")


@respx.mock
def test_iitp_ezone_collects_open_tab_only():
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, html=_load()))
    items = monitor.fetch_html_generic(_site_from_config())

    assert len(items) == 2
    titles = [it["title"] for it in items]
    assert titles == [
        "2026년도 AI 기반 주파수 간섭분석 및 전파예측기술 개발사업 신규지원 대상과제 공고",
        "(수정공고)2026년도 AI최고급신진연구자지원 사업 공고",
    ]
    assert items[0]["link"] == (
        "https://ezone.iitp.kr/common/anno/02/form.tab?PMS_TSK_PBNC_ID=PBD202600000088"
    )
    assert items[1]["link"].endswith("PMS_TSK_PBNC_ID=PBD202600000071")
    assert items[0]["deadline"] == "2026-08-31 ~ 2026-09-11"
    for it in items:
        assert set(it.keys()) == SCHEMA_KEYS
        assert it["source"] == "정보통신기획평가원(IITP) 사업공고"
        assert it["is_aggregator"] is False


def test_iitp_does_not_use_spa_home_url():
    site = _site_from_config()
    assert "businessPblancList.it" not in site["url"]
    assert site["url"] == LIST_URL
