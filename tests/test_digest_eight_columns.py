"""MAIL-002: 공고 안내 메일 8컬럼 표 회귀 (실발송 없음)."""
from __future__ import annotations

import os
from datetime import date, timedelta
from email import message_from_bytes
from pathlib import Path
import sys

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402
from mail_core.delivery.digest_table import (  # noqa: E402
    COLUMNS,
    EMPTY_DIGEST,
    HEADER_LINE,
    html_email_inner,
    parse_plain_table,
)

TODAY = date(2026, 8, 14)


def _item(**extra):
    deadline = (TODAY + timedelta(days=2)).isoformat()
    base = {
        "id": "n1",
        "title": "2026년 AI 사업화 지원 참여기업 모집",
        "author": "중소벤처기업부",
        "description": "서울 소재 중소기업 대상. 사업화 자금을 지원합니다.",
        "target_field": "서울 소재 중소기업",
        "support_field": "사업화 자금 지원",
        "deadline": deadline,
        "posted_date": "2026-08-10",
        "source": "기업마당",
        "link": "https://bizinfo.go.kr/notice/1",
        "_types": ["지원금/바우처"],
        "priority_keyword": False,
        "region_status": "eligible",
        "eligible_regions": ["서울특별시"],
        "applicant_region_city": "서울특별시",
        "is_relevant": True,
        "_change_type": "NEW",
    }
    base.update(extra)
    return base


def test_columns_order_exact():
    assert COLUMNS == ("상태", "적합", "공고", "지원", "대상", "기관", "지역", "마감")
    body = m.fallback_body([_item()], today=TODAY)
    assert HEADER_LINE in body
    assert "추천이유" not in body
    assert "바로가기" not in body
    assert "사이트명" not in body
    assert "적합사유" not in body
    assert "• 원문:" not in body


def test_single_and_multiple_notices():
    one = m.fallback_body([_item()], today=TODAY)
    _, rows, _ = parse_plain_table(one)
    assert rows is not None and len(rows) == 1
    two = m.fallback_body(
        [_item(id="a"), _item(id="b", title="두 번째 공고", link="https://x/2")],
        today=TODAY,
    )
    _, rows2, _ = parse_plain_table(two)
    assert len(rows2) == 2


def test_new_badge_and_dday():
    new_row = m._digest_row(_item(_change_type="NEW", deadline="2026-08-16"), today=TODAY)
    assert new_row["상태"] == "🆕 D-2 🔴"

    d6 = m._mail_status_cell(_item(_change_type="UPDATED", deadline="2026-08-20"), today=TODAY)
    assert d6 == "D-6 🟠"

    d15 = m._mail_status_cell(_item(_change_type="", deadline="2026-08-29"), today=TODAY)
    assert d15 == "D-15 🟢"
    assert not d15.startswith("🆕")

    closed = m._mail_status_cell(_item(_change_type="", deadline="2026-08-01"), today=TODAY)
    assert closed == "마감"


def test_fit_three_values_only():
    ok = m._mail_fit_cell(_item(is_relevant=True, region_status="eligible"))
    need = m._mail_fit_cell(_item(region_status="unknown"))
    no = m._mail_fit_cell(_item(is_relevant=False))
    assert ok == "지원가능"
    assert need == "확인필요"
    assert no == "대상아님"
    for label in (ok, need, no):
        assert label in ("지원가능", "확인필요", "대상아님")


def test_title_link_when_url_present_and_plain_when_missing():
    with_url = m.fallback_body([_item(link="https://bizinfo.go.kr/notice/1")], today=TODAY)
    _, rows, _ = parse_plain_table(with_url)
    assert rows[0]["url"] == "https://bizinfo.go.kr/notice/1"
    html_part = html_email_inner(with_url, m._linkify_html)
    assert '<a href="https://bizinfo.go.kr/notice/1">' in html_part
    assert "바로가기" not in html_part

    no_url = m.fallback_body([_item(link="", source_url="")], today=TODAY)
    _, rows2, _ = parse_plain_table(no_url)
    assert rows2[0]["url"] == ""
    html2 = html_email_inner(no_url, m._linkify_html)
    assert "<a href=" not in html2.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]


def test_missing_support_target_region_are_확인필요():
    item = _item(
        support_field="", description="단순 안내", _types=[],
        target_field="", target_age_field="", business_age_text="",
        region_status="unknown",
    )
    row = m._digest_row(item, today=TODAY)
    assert row["지원"] == "확인필요"
    assert row["대상"] == "확인필요"
    assert row["지역"] == "확인필요"


def test_empty_items_no_table():
    body = m.fallback_body([])
    assert body == EMPTY_DIGEST
    assert HEADER_LINE not in body
    html_part = html_email_inner(body, m._linkify_html)
    assert "<table" not in html_part
    assert EMPTY_DIGEST in html_part


def test_row_field_error_does_not_break_table(monkeypatch):
    monkeypatch.setattr(m, "resolve_item_deadline", lambda it: (_ for _ in ()).throw(ValueError("bad date")))
    body = m.fallback_body([_item(), _item(id="n2", title="정상 두 번째")], today=TODAY)
    _, rows, _ = parse_plain_table(body)
    assert len(rows) == 2
    assert rows[0]["마감"] == "추출실패"
    assert rows[1]["공고"] == "정상 두 번째"


def test_mime_html_is_gmail_table():
    body = m.fallback_body([_item()], today=TODAY)
    msg = m._build_mime_message("[AI팀] 1건", body, "recipient@example.test")
    parsed = message_from_bytes(msg.as_bytes())
    parts = {
        part.get_content_type(): part.get_payload(decode=True).decode(part.get_content_charset())
        for part in parsed.walk() if part.get_content_maintype() != "multipart"
    }
    html_part = parts["text/html"]
    assert "<table" in html_part
    assert all(col in html_part for col in COLUMNS)
    assert "추천이유" not in html_part
    assert '<a href="https://bizinfo.go.kr/notice/1">' in html_part


def test_source_url_preferred_over_link():
    item = _item(link="https://other.example/x", source_url="https://bizinfo.go.kr/canonical")
    row = m._digest_row(item, today=TODAY)
    assert row["url"] == "https://bizinfo.go.kr/canonical"


def test_deadline_this_year_vs_other_year():
    this = m._mail_deadline_cell(_item(deadline="2026-08-20"), today=TODAY)
    other = m._mail_deadline_cell(_item(deadline="2027-01-05"), today=TODAY)
    assert this == "8/20"
    assert other == "2027/1/5"


def test_org_not_abbreviated_and_not_source_name():
    row = m._digest_row(_item(author="중소벤처기업부", source="기업마당"), today=TODAY)
    assert row["기관"] == "중소벤처기업부"
    empty = m._digest_row(_item(author="", source="기업마당"), today=TODAY)
    assert empty["기관"] == "확인필요"


def test_support_kinds_from_existing_data_never_invent_amount():
    voucher = m._mail_support_cell(_item(_types=["바우처"], support_field="", description=""))
    grant = m._mail_support_cell(_item(
        _types=[], support_field="중소기업 해외진출 지원금 최대 5천만원", description="",
    ))
    cost = m._mail_support_cell(_item(
        _types=[], support_field="해외 전시회 참가 비용 지원", description="", title="전시 참가",
    ))
    facility = m._mail_support_cell(_item(_types=[], support_field="입주 공간 제공", description="", title="입주"))
    market = m._mail_support_cell(_item(_types=[], support_field="판로 개척 및 실증", description="", title="판로"))
    assert voucher == "바우처"
    assert grant == "지원금/사업비"
    assert "5천" not in grant and "만원" not in grant
    assert cost == "비용지원"
    assert facility == "시설/입주"
    assert market == "판로/실증"


def test_nationwide_region_label():
    row = m._digest_row(_item(
        region_field="전국",
        description="전국 중소기업 대상 사업화 자금을 지원합니다.",
        target_field="전국 중소기업",
        region_status="eligible",
    ), today=TODAY)
    assert row["지역"] == "전국"


def test_execute_monitor_preview_and_digest_table_no_real_send(monkeypatch):
    """production entrypoint: preview는 미발송, 발송 경로 본문은 8컬럼 표. SMTP 없음."""
    items = [
        {
            "id": "a1", "title": "AI 솔루션 도입 지원 신청접수",
            "description": "서울 전국 중소기업 대상 사업화 자금 지원",
            "link": "https://bizinfo.go.kr/a1",
            "source_url": "https://bizinfo.go.kr/canonical-a1",
            "author": "중소벤처기업부", "deadline": "2099-12-31",
            "source": "기업마당", "posted_date": "2026-08-10",
            "is_aggregator": False, "target_field": "전국 중소기업",
            "support_field": "사업화 자금 지원", "_types": ["지원금/바우처"],
        },
        {
            "id": "a2", "title": "AI 솔루션 도입 지원 신청접수",
            "description": "서울 전국 중소기업 대상 사업화 자금 지원",
            "link": "https://bizinfo.go.kr/a1",
            "author": "중소벤처기업부", "deadline": "2099-12-31",
            "source": "K-Startup", "posted_date": "2026-08-10",
            "is_aggregator": False,
        },
        {
            "id": "b1", "title": "AI 수출 바우처 참여기업 모집",
            "description": "수출 바우처를 지원합니다",
            "link": "https://bizinfo.go.kr/b1",
            "author": "KOTRA", "deadline": "2099-11-30",
            "source": "기업마당", "posted_date": "2026-08-11",
            "is_aggregator": False, "target_field": "수출 중소기업",
            "support_field": "수출 바우처", "_types": ["바우처"],
        },
    ]
    monkeypatch.setattr(m, "fetch_all", lambda s, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{
        "id": "g", "name": "AI팀", "active": True, "or_keywords": ["AI"],
        "required_conditions": {"regions": ["전국"]},
        "applicant_region_city": "서울특별시", "applicant_region_label": "서울",
        "recipients": ["test-recipient@example.test"],
    }])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": False, "raw_all_enabled": False, "raw_all_recipients": [],
        "company_match_enabled": False,
    })
    monkeypatch.setattr(m, "load_watchlist", lambda: {"keywords": [], "urls": [], "recipients": []})
    monkeypatch.setattr(m, "load_seen_ids", lambda: set())
    monkeypatch.setattr(m, "alert_ntfy", lambda *a, **k: None)

    preview = m.execute_monitor(allow_send=False, include_raw_all=False, persist_seen=False)
    assert preview.get("mode") == "preview"
    assert preview.get("mail_sent") is False
    assert preview.get("ok") is True

    sent = []
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: sent.append((s, b)))
    monkeypatch.setattr(m, "send_email", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SMTP 금지")))

    result = m.execute_monitor(allow_send=True, include_raw_all=False, persist_seen=False)
    assert result.get("ok") is True
    assert sent, "발송 경로 본문이 캡처되어야 함"
    subj, body = sent[0]
    assert subj.startswith("[AI팀]")
    assert HEADER_LINE in body
    _, rows, _ = parse_plain_table(body)
    assert rows and len(rows) >= 1
    assert all(col in body for col in COLUMNS)
    assert "추천이유" not in body and "바로가기" not in body
    html_part = html_email_inner(body, m._linkify_html)
    assert "<table" in html_part
    assert '<a href="https://bizinfo.go.kr/canonical-a1">' in html_part or '<a href="https://bizinfo.go.kr/a1">' in html_part or '<a href="https://bizinfo.go.kr/b1">' in html_part
