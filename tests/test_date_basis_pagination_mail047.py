# -*- coding: utf-8 -*-
"""MAIL-047 date basis, pagination shortfall, and list/detail deadline conflict."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402
from mail_core.operations import daily_review as dr  # noqa: E402
from mail_core.operations import coverage_alert as ca  # noqa: E402


def test_date_basis_uses_configured_source_and_preserves_default():
    item = {"id": "n1", "posted_date": "2026-10-10", "published_at": "2026-10-09",
            "registered_at": "2026-10-10", "updated_at": "2026-10-11"}
    assert m._apply_site_date_basis([item], {"id": "s"})[0]["posted_date"] == "2026-10-10"

    published = m._apply_site_date_basis([item], {"id": "s", "date_basis": "posted"})[0]
    assert published["posted_date"] == "2026-10-09"
    assert published["date_source"] == "published_at"

    registered = m._apply_site_date_basis([item], {"id": "s", "date_basis": "registered"})[0]
    assert registered["posted_date"] == "2026-10-10"
    assert registered["date_source"] == "registered_at"

    modified = m._apply_site_date_basis([item], {"id": "s", "date_basis": "modified"})[0]
    assert modified["posted_date"] == "2026-10-11"
    assert modified["date_source"] == "updated_at"


def test_core_source_date_basis_metadata_is_populated():
    bizinfo = m._bizinfo_parse_item({
        "pblancId": "b1", "pblancNm": "공고", "pblancDt": "2026-10-09",
        "regDt": "2026-10-10", "updtPnttm": "2026-10-11",
    }, "기업마당", False)
    selected_bizinfo = m._apply_site_date_basis([bizinfo], {"id": "bizinfo", "date_basis": "posted"})[0]
    assert selected_bizinfo["posted_date"] == "2026-10-09"
    assert selected_bizinfo["registered_at"] == "2026-10-10"

    card = BeautifulSoup(
        '<div class="notice"><a href="view?id=7">K 공고</a>'
        '<span class="list">등록일자 2026.10.10.</span></div>', "html.parser")
    kstartup = m._kstartup_cards_from_soup(
        card, "PBC010", {"id": "kstartup", "name": "K-Startup", "url": "https://example.test/list"}, set())
    selected_kstartup = m._apply_site_date_basis(
        kstartup, {"id": "kstartup", "date_basis": "registered"})[0]
    assert selected_kstartup["posted_date"] == "2026-10-10"
    assert selected_kstartup["date_source"] == "registered_at"


def test_api_total_count_is_read_from_supported_envelopes():
    assert m._reported_total_items({"totalCount": "1,234"}) == 1234
    assert m._reported_total_items({"response": {"body": {"totalCount": 22}}}) == 22
    assert m._reported_total_items({"channel": {"total": "7"}}) == 7
    assert m._reported_total_items({"totalCount": "unknown"}) is None


def test_explicit_posted_basis_does_not_fall_back_to_registration_date():
    item = {"id": "n1", "posted_date": "2026-10-10", "registered_at": "2026-10-10"}
    selected = m._apply_site_date_basis([item], {"id": "s", "date_basis": "posted"})[0]
    assert selected["posted_date"] == ""
    assert selected["date_source"] == "unknown"


def test_fetch_all_applies_site_date_basis_on_user_collection_path(monkeypatch):
    monkeypatch.setitem(m.FETCHERS, "basis_test", lambda _site: [{
        "id": "n1", "title": "공고", "posted_date": "2026-10-10",
        "published_at": "2026-10-09", "registered_at": "2026-10-10",
        "updated_at": "2026-10-11",
    }])
    items = m.fetch_all([{"id": "s1", "name": "S", "type": "basis_test",
                         "date_basis": "modified"}], max_workers=1)
    assert items[0]["site_id"] == "s1"
    assert items[0]["posted_date"] == "2026-10-11"
    assert items[0]["date_source"] == "updated_at"


def test_application_start_and_attachment_dates_are_not_posted_dates():
    assert m._labeled_date_from_text("접수 시작일: 2026-10-10", ("게시일", "공고일")) == ""
    assert m._labeled_date_from_text("첨부파일 생성일: 2026-10-10", ("게시일", "공고일")) == ""
    assert m._labeled_date_from_text("게시일: 2026-10-10", ("게시일",)) == "2026-10-10"


def test_generic_list_keeps_unknown_posted_date_when_only_start_date_exists(monkeypatch):
    html = (
        '<table><tbody><tr><td><a href="view?id=1">공고</a></td>'
        '<td>접수 시작일: 2026-10-10</td></tr></tbody></table>'
    )
    monkeypatch.setattr(m, "_soup", lambda *_a, **_k: BeautifulSoup(html, "html.parser"))
    items = m.fetch_html_generic({"id": "s", "name": "S", "url": "https://example.test/list",
                                  "type": "html_table"})
    assert len(items) == 1
    assert items[0]["posted_date"] == ""
    matched, unknown, _excluded = m.partition_posted_dates(
        items, now_dt=datetime(2026, 10, 16, tzinfo=m.KST))
    assert matched == [] and unknown == items
    candidates = m.select_notice_version_candidates(
        items, set(), {}, now=datetime(2026, 10, 16, tzinfo=m.KST), days_back=3)
    assert candidates == items


def test_notice_version_records_date_source_without_hashing_it():
    item = {"id": "n1", "title": "공고", "posted_date": "2026-10-15",
            "date_basis": "registered", "date_source": "registered_at",
            "deadline": "2026-10-30"}
    deliverable, updates = m.classify_notice_versions([item], set(), {})
    assert deliverable[0]["_change_type"] == "NEW"
    assert updates["n1"]["date_source"] == "registered_at"
    assert updates["n1"]["date_basis"] == "registered"
    assert "date_source" not in updates["n1"]["snapshot"]
    saved = m.commit_notice_versions({}, updates, set())
    assert saved["n1"]["date_source"] == "registered_at"
    assert saved["n1"]["date_basis"] == "registered"


def test_pagination_records_counts_and_known_shortfall(monkeypatch):
    page1 = BeautifulSoup(
        '<div class="total">총 3건</div><a class="last" href="list?page=2">2</a>'
        '<table><tbody><tr><td><a href="view?id=1">A</a></td><td>게시일 2026-10-15</td></tr>'
        '</tbody></table>', "html.parser")
    page2 = BeautifulSoup(
        '<div class="total">총 3건</div><a class="last" href="list?page=2">2</a>'
        '<table><tbody><tr><td><a href="view?id=2">B</a></td><td>게시일 2026-10-15</td></tr>'
        '</tbody></table>', "html.parser")
    monkeypatch.setattr(m, "_soup", lambda url, *_a, **_k: page1 if "page=2" not in url else page2)
    m.reset_page_stats()
    items = m.fetch_html_generic({
        "id": "s", "name": "S", "url": "https://example.test/list", "type": "html_table",
        "max_pages": 2, "total_count_selector": ".total", "last_page_selector": ".last",
    })
    stat = m.page_stats_snapshot()["s"]
    assert len(items) == 2
    assert stat["pages_read"] == 2 and stat["items_read"] == 2
    assert stat["total_items"] == 3 and stat["last_page"] == 2
    assert stat["stop_reason"] == "LAST_PAGE"


def test_pagination_metadata_detects_page_and_total_from_site_markup():
    soup = BeautifulSoup(
        '<span>전체 1,234건</span><a rel="last" href="list?page=12">마지막</a>',
        "html.parser")
    assert m._known_pagination_metadata(soup, {}) == {"total_items": 1234, "last_page": 12}


def test_coverage_alert_marks_known_page_or_item_shortfall():
    row = {"site_id": "s1", "site_name": "S", "item_count": 2,
           "fetch_success": True, "collector_fn": "fetch", "date_unknown_count": 0}
    report = ca.classify_source_status(
        row, None, page_stat={"stop_reason": "PBC010:MAX_PAGES_HIT", "pages_read": 2,
                              "last_page": 4, "items_read": 2, "total_items": 5})
    assert "PAGINATION_INCOMPLETE" in report["reason_codes"]


def test_daily_review_warns_for_pagination_and_deadline_conflicts(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    payload = {"run_status": "SUCCESS", "sources": [
        {"site_id": "s1", "item_count": 1, "status": "PARTIAL",
         "reason_codes": ["PAGINATION_INCOMPLETE"]},
    ]}
    (logs / "source_coverage_20261016.json").write_text(json.dumps(payload), encoding="utf-8")
    (logs / "deadline_conflicts_20261016.json").write_text(
        json.dumps({"conflicts": [{"site_id": "s1", "list": "2026-10-20", "detail": "2026-10-21"}]}),
        encoding="utf-8")
    report, _ = dr.run_daily_review(
        date_s="2026-10-16", slot="am", delivery_state_path=tmp_path / "missing.json",
        logs_dir=logs, reviews_root=tmp_path / "reviews", append_context=False,
        require_coverage=False)
    by_id = {check.id: check for check in report.checks}
    assert by_id["MDR-007"].status == "WARN"
    assert by_id["DEADLINE_CONFLICT"].status == "WARN"


def test_detail_deadline_wins_and_conflict_is_recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_should_generic_enrich", lambda *_a, **_k: True)
    monkeypatch.setattr(m, "_http_get", lambda *_a, **_k: SimpleNamespace(text="detail"))
    monkeypatch.setattr(m, "_parse_detail_from_page", lambda *_a, **_k: {
        "body": "접수기간: 2026-10-01 ~ 2026-10-21",
    })
    monkeypatch.setattr(m, "_persist_detail_extraction_meta", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "LOGS_DIR", tmp_path)
    item = {"id": "n1", "title": "공고", "link": "https://example.test/view",
            "source": "test", "deadline": "2026-10-20", "description": ""}
    enriched = m.enrich_item_from_detail(item)
    assert enriched["deadline"] == "2026-10-01 ~ 2026-10-21"
    assert enriched["deadline_conflict"] == {
        "list": "2026-10-20", "detail": "2026-10-01 ~ 2026-10-21"}
    path = m.write_deadline_conflicts_report([enriched], run_at=datetime(2026, 10, 16, tzinfo=m.KST))
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["conflicts"][0]["detail"].endswith("2026-10-21")
