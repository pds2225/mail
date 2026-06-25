"""기업마당 상세 페이지 보강 회귀 — respx 오프라인."""
from __future__ import annotations

import os
import pathlib
import sys

import pytest
import respx
from httpx import Response

for _k, _v in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
}.items():
    os.environ.setdefault(_k, _v)

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402

FX = ROOT / "fixtures" / "bizinfo"
DETAIL_URL = (
    "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do"
    "?pblancId=PBLN_000000000123386"
)


@respx.mock
def test_bizinfo_detail_enrich_adds_body_and_period():
  html = (FX / "bizinfo_detail_sba.html").read_text(encoding="utf-8")
  respx.get(DETAIL_URL).mock(return_value=Response(200, text=html))

  item = {
      "id": "bizinfo_sba_test",
      "title": "K-뷰티 판로 연계사업",
      "link": DETAIL_URL,
      "author": "서울특별시",
      "description": "짧은 API 요약",
      "region_field": "전국",
      "deadline": "",
      "source": "기업마당(Bizinfo)",
      "posted_date": "2026-06-18",
      "is_aggregator": True,
  }
  out = m.enrich_item_from_detail(item)

  assert out.get("detail_enriched") is True
  assert "서울 소재" in out.get("description", "")
  assert out.get("deadline")  # 신청기간 파싱
  fields = m._parse_detail_from_page(
      __import__("bs4").BeautifulSoup(html, "html.parser"), DETAIL_URL,
  )
  assert "서울 소재" in fields.get("body", "")


@respx.mock
def test_bizinfo_host_in_detail_enrich_targets():
  assert "bizinfo.go.kr" in m.DETAIL_ENRICH_HOSTS
  item = {
      "id": "x",
      "title": "t",
      "link": DETAIL_URL,
      "description": "",
      "source": "기업마당",
  }
  html = (FX / "bizinfo_detail_sba.html").read_text(encoding="utf-8")
  respx.get(DETAIL_URL).mock(return_value=Response(200, text=html))
  targets = [
      it for it in [item]
      if any(h in (it.get("link") or "") for h in m.DETAIL_ENRICH_HOSTS)
  ]
  assert len(targets) == 1
