# -*- coding: utf-8 -*-
"""P0-B No.31 상세 HTML 표 구조 보존 회귀 테스트."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
}.items():
    os.environ.setdefault(_key, _value)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402


DETAIL_URL = "https://example.com/notice/1"


def _item() -> dict:
    return {
        "id": "table-notice-1",
        "title": "표 구조 보존 공고",
        "link": DETAIL_URL,
        "author": "",
        "description": "",
        "deadline": "",
        "source": "테스트",
        "posted_date": "2026-07-24",
        "is_aggregator": False,
    }


def test_extract_detail_tables_preserves_relationships_and_excludes_nested_rows():
    soup = m.BeautifulSoup(
        """
        <table>
          <caption>지원 내용</caption>
          <tr><th rowspan="2">구분</th><th colspan="2">지원액</th></tr>
          <tr><th>최소</th><th>최대</th></tr>
          <tr>
            <td>창업기업<table><tr><td>중첩 설명</td></tr></table></td>
            <td>100만원</td><td>500만원</td>
          </tr>
        </table>
        """,
        "html.parser",
    )

    structured = m._extract_detail_tables(soup)

    assert structured["truncated"] is False
    assert len(structured["tables"]) == 1
    table = structured["tables"][0]
    assert table["caption"] == "지원 내용"
    assert len(table["rows"]) == 3
    assert table["rows"][0] == [
        {"text": "구분", "header": True, "rowspan": 2, "colspan": 1},
        {"text": "지원액", "header": True, "rowspan": 1, "colspan": 2},
    ]
    assert table["rows"][2][0]["text"] == "창업기업"
    assert "중첩 설명" not in table["rows"][2][0]["text"]


def test_extract_detail_tables_applies_size_caps(monkeypatch):
    monkeypatch.setattr(m, "_DETAIL_TABLE_MAX_TABLES", 1)
    monkeypatch.setattr(m, "_DETAIL_TABLE_MAX_ROWS", 1)
    monkeypatch.setattr(m, "_DETAIL_TABLE_MAX_CELLS", 1)
    monkeypatch.setattr(m, "_DETAIL_TABLE_MAX_CELL_CHARS", 5)
    soup = m.BeautifulSoup(
        """
        <table>
          <tr><td>123456789</td><td>두 번째 셀</td></tr>
          <tr><td>두 번째 행</td></tr>
        </table>
        <table><tr><td>두 번째 표</td></tr></table>
        """,
        "html.parser",
    )

    structured = m._extract_detail_tables(soup)

    assert structured["truncated"] is True
    assert len(structured["tables"]) == 1
    assert structured["tables"][0]["truncated"] is True
    assert structured["tables"][0]["rows"] == [[{
        "text": "12345",
        "header": False,
        "rowspan": 1,
        "colspan": 1,
    }]]


def test_table_only_detail_is_parsed_and_attached(monkeypatch):
    html = """
    <html><body>
      <table><tr><th>지원대상</th><td>서울 소재 기업</td></tr></table>
    </body></html>
    """
    monkeypatch.setattr(
        m, "_http_get", lambda *args, **kwargs: SimpleNamespace(text=html))

    out = m.enrich_item_from_detail(_item())

    assert out["detail_enriched"] is True
    assert out["detail_extraction"]["status"] == m.EXTRACTION_SUCCESS
    assert out["detail_tables"]["tables"][0]["rows"][0][1]["text"] == "서울 소재 기업"
