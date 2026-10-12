"""2026-10 다이제스트 개편 회귀: 마감 제외·제목 마감감지·섹션 번호·열 삭제·워치리스트 필터."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import monitor as m  # noqa: E402
from mail_core.delivery.digest_table import (  # noqa: E402
    EMPTY_DIGEST,
    HEADER_LINE,
    html_email_inner,
    parse_plain_table,
    render_plain,
)
from mail_core.matching.watchlist_select import filter_watchlist_hits  # noqa: E402

TODAY = date(2026, 10, 12)


def _item(i, title, deadline="2026-10-30", posted="2026-10-10", desc="", **extra):
    base = {
        "id": f"n{i}", "title": title, "author": "테스트기관",
        "description": desc or "중소기업 대상 지원사업", "target_field": "중소기업",
        "support_field": "", "deadline": deadline, "posted_date": posted,
        "link": f"https://example.test/{i}", "region_status": "eligible",
        "eligible_regions": ["서울특별시"], "applicant_region_city": "서울특별시",
        "is_relevant": True, "_change_type": "NEW",
    }
    base.update(extra)
    return base


# 1. 마감일 지난 공고 제외 / 상시·불명 유지
def test_past_deadline_excluded_from_digest():
    body = m.fallback_body([
        _item(1, "수출바우처 참여기업 모집", deadline="2026-10-01"),
        _item(2, "혁신바우처 참여기업 모집", deadline="2026-10-20"),
    ], today=TODAY)
    _, rows, _ = parse_plain_table(body)
    titles = [r["공고"] for r in rows]
    assert titles == ["혁신바우처 참여기업 모집"]


def test_always_open_and_unknown_deadline_kept():
    body = m.fallback_body([
        _item(1, "바우처 상시모집 안내", deadline="", desc="상시모집"),
        _item(2, "지원금 참여기업 모집", deadline="", desc="자세한 내용은 첨부 참조"),
    ], today=TODAY)
    _, rows, _ = parse_plain_table(body)
    assert len(rows) == 2


def test_all_closed_gives_empty_digest():
    assert m.fallback_body([_item(1, "지원금 모집", deadline="2026-09-01")], today=TODAY) == EMPTY_DIGEST


# 2. 제목 기반 마감/발표 감지
@pytest.mark.parametrize("title", [
    "[마감] 소공인 컨설턴트 2차 모집",
    "[모집마감] 충북소상공인지원센터 컨설턴트 모집",
    "컨설턴트 모집 접수마감 안내",
    "컨설턴트 추가 모집 합격자 발표",
    "2026 지원사업 선정 결과 발표",
    "최종 발표",
    "공모 결과발표",
    "모집이 마감되었습니다",
])
def test_title_closed_detection(title):
    assert m.classify_deadline_status(_item(1, title, deadline="2026-12-31"), TODAY) == "closed"


@pytest.mark.parametrize("title", [
    "2026 수출바우처 참여기업 모집",
    "마감임박! 혁신바우처 모집",
    "발표평가 일정 안내 및 참여기업 모집",
    "2026 바우처 수행기관 선정 공고",
    "창업지원사업 최종 공고",
    "참여기업 선정 안내 및 모집",
    "결과 공고 이후 추가 모집",
])
def test_title_open_not_misdetected(title):
    assert m.classify_deadline_status(_item(1, title, deadline="2026-12-31"), TODAY) != "closed"


# 3·4. 섹션·번호, 열 삭제, ⚠️ 문단 삭제
def test_sections_numbering_restart_and_columns_removed():
    items = [
        _item(1, "수출바우처 A", support_field="바우처 지원"),
        _item(2, "지원금 A", support_field="사업비 지원금 지급"),
        _item(3, "수출바우처 B", support_field="바우처 지원"),
        _item(4, "지원금 B", support_field="사업비 지원금 지급"),
        _item(5, "지원금 C", support_field="사업비 지원금 지급", deadline="2026-10-14"),
    ]
    body = m.fallback_body(items, today=TODAY)
    assert "⚠️" not in body and "7일 이내 마감" not in body
    assert "상태" not in body and "적합" not in body and " | " not in body
    assert body.index("■ 바우처 (2건)") < body.index("■ 지원금 (3건)")
    _, rows, _ = parse_plain_table(body)
    by_sec: dict[str, list[int]] = {}
    for r in rows:
        by_sec.setdefault(r["지원"], []).append(r["_no"])
    assert by_sec == {"바우처": [1, 2], "지원금": [1, 2, 3]}
    row = m._digest_row(items[0], today=TODAY)
    assert "상태" not in row and "적합" not in row


def test_plain_roundtrip_and_html_blocks():
    rows = [
        {"공고": "제목1", "url": "https://e.test/1", "지원": "바우처", "기관": "기관A",
         "대상": "중소기업", "지역": "전국", "마감": "10/20"},
        {"공고": "제목2", "url": "", "지원": "확인필요", "기관": "기관·B",
         "대상": "확인필요", "지역": "서울", "마감": "확인필요"},
    ]
    body = "머리말\n\n" + render_plain(rows) + "\n\n────\n피드백 안내"
    before, parsed, after = parse_plain_table(body)
    assert before == "머리말" and after.startswith("────")
    assert [p["공고"] for p in parsed] == ["제목1", "제목2"]
    assert parsed[0]["url"] == "https://e.test/1" and parsed[0]["마감"] == "10/20"
    assert parsed[1]["지원"] == "기타" and parsed[1]["기관"] == "기관,B"
    html_part = html_email_inner(body, m._linkify_html)
    assert "<table" not in html_part and "<style" not in html_part
    assert "word-break:keep-all" in html_part and "max-width:640px" in html_part
    assert "기관A · 중소기업 · 전국 · <span style='color:#d93025;font-weight:700;white-space:nowrap'>10/20" in html_part
    assert '<a href="https://e.test/1"' in html_part
    assert "피드백 안내" in html_part
    assert HEADER_LINE in body


# 6. 워치리스트 필터
def test_filter_watchlist_hits():
    items = [
        _item(1, "[마감] 컨설턴트 모집"),
        _item(2, "컨설턴트 모집", deadline="2026-09-01"),
        _item(3, "컨설턴트 추가 모집 합격자 발표"),
        _item(4, "진로제시 컨설팅 수행기관 모집", deadline="2026-10-30"),
        _item(5, "컨설턴트 모집 오래됨", deadline="", posted="2026-08-01"),
        _item(6, "컨설턴트 모집 최근", deadline="", posted="2026-10-01"),
        _item(7, "컨설턴트 모집 게시일불명", deadline="", posted=""),
    ]
    keep, dropped = filter_watchlist_hits(
        items,
        classify=lambda it: m.classify_deadline_status(it, TODAY),
        is_junk=m.is_report_junk,
        today=TODAY,
    )
    assert [it["id"] for it in keep] == ["n4", "n6", "n7"]
    assert {it["id"] for it in dropped} == {"n1", "n2", "n3", "n5"}


def test_filter_watchlist_hits_errors_keep_item():
    keep, dropped = filter_watchlist_hits(
        [_item(1, "x")], classify=lambda it: 1 / 0, is_junk=lambda it: 1 / 0, today=TODAY,
    )
    assert len(keep) == 1 and not dropped


# 5. 3줄 카드 (2026-10)
def test_card_three_lines_plain_and_html():
    from mail_core.delivery.digest_table import html_email_inner
    it = _item(1, "수출바우처 참여기업 모집", support_field="바우처 최대 3천만원", desc="해외마케팅 비용 바우처 지원 (세부내용 첨부)", deadline="2026-10-30")
    body = m.fallback_body([it], today=TODAY)
    lines = body.splitlines()
    i = lines.index("수출바우처 참여기업 모집")
    assert lines[i + 1].startswith("   💰 최대 3천만원")
    assert lines[i + 2].endswith(" · 10/30 (D-18)") and "마감" not in lines[i + 2]
    _, rows, _ = parse_plain_table(body)
    assert rows[0]["지원내용"].startswith("최대 3천만원")
    h = html_email_inner(body, lambda t: t)
    assert "text-overflow:ellipsis'>💰 최대 3천만원" in h and "color:#d93025;font-weight:700;white-space:nowrap'>10/30 (D-" in h
    assert "color:#1a5fd6;text-decoration:none" in h
    assert "white-space:nowrap;overflow:hidden;text-overflow:ellipsis" in h
    assert len(rows[0]["지원내용"]) <= 40


def test_card_omits_support_line_when_empty():
    it = _item(1, "참여기업 모집", support_field="", desc="첨부 참조", deadline="2026-10-30")
    body = m.fallback_body([it], today=TODAY)
    assert "💰" not in body


def test_support_line_truncated_short():
    it = _item(1, "바우처 모집", support_field="", desc="해외마케팅 통번역 인증 전시회 참가 등 다양한 비용을 바우처로 폭넓게 지원합니다 최대 3천만원", deadline="2026-10-30")
    sup = m._mail_support_summary(it)
    assert sup.startswith("최대 3천만원") and 22 < len(sup) <= 60
    from mail_core.delivery.digest_table import render_plain
    body = m.fallback_body([it], today=TODAY)
    line = next(l for l in body.splitlines() if "💰" in l)
    assert len(line.strip()) <= 42 and line.endswith("…")


@pytest.mark.parametrize("raw,exp", [("서울특별시 전체", "서울"), ("경기도 전체", "경기"), ("전국", "전국"),
    ("인천광역시 남동구", "인천 남동구"), ("세종특별자치시", "세종"), ("강원특별자치도", "강원"),
    ("충청북도 전체", "충북"), ("확인필요", "확인필요")])
def test_short_region(raw, exp):
    from mail_core.delivery.digest_table import short_region
    assert short_region(raw) == exp


def test_short_org():
    from mail_core.delivery.digest_table import short_org
    assert short_org("KOTRA") == "KOTRA"
    assert short_org("소상공인시장진흥공단본부") == "소상공인시장진흥공…"


def test_no_item_numbering():
    from mail_core.delivery.digest_table import html_email_inner
    body = m.fallback_body([_item(1, "수출바우처 A", support_field="바우처 지원"),
                            _item(2, "수출바우처 B", support_field="바우처 지원")], today=TODAY)
    assert not any(l[:1].isdigit() and l[1:3] == ". " for l in body.splitlines())
    _, rows, _ = parse_plain_table(body + "\n\n────\n피드백")
    assert [r["공고"] for r in rows] == ["수출바우처 A", "수출바우처 B"]
    assert "<b>1.</b>" not in html_email_inner(body, lambda t: t)
