"""MAIL-P0C-02(TASK-022) — canonical ID 기반 5종 duplicate_type 분류 회귀테스트.

NEW / EXACT_DUPLICATE / MODIFIED / REPOSTED / MULTI_AGENCY_DUPLICATE
Run: python -m pytest tests/test_duplicate_type_classification.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

from monitor import classify_duplicate_type, dedup_items  # noqa: E402


def _item(iid, title, *, link, deadline, source="기업마당", author="중소벤처기업부", is_aggregator=False):
    return {
        "id": iid,
        "title": title,
        "link": link,
        "author": author,
        "description": "테스트용 지원사업 공고",
        "deadline": deadline,
        "source": source,
        "posted_date": "2026-09-15",
        "is_aggregator": is_aggregator,
    }


# ── 1. NEW — 처음 보는 공고, 비교 대상 없음 ──────────────────────────────

def test_first_seen_notice_is_new():
    items = [_item("a1", "2026년 AI 스타트업 사업화 지원", link="https://x.kr/a1", deadline="2026-11-01")]
    deduped = dedup_items(items)
    assert len(deduped) == 1
    assert deduped[0]["duplicate_type"] == "NEW"


# ── 2. EXACT_DUPLICATE — 같은 소스에서 완전히 동일한 내용 재수집 ────────

def test_identical_recrawl_same_round_is_exact_duplicate_and_merges_to_one():
    items = [
        _item("b1", "2026년 소상공인 정책자금 지원", link="https://x.kr/b1", deadline="2026-10-15"),
        _item("b2", "2026년 소상공인 정책자금 지원", link="https://x.kr/b1", deadline="2026-10-15"),
    ]
    deduped = dedup_items(items)
    assert len(deduped) == 1, "동일 차수 완전중복은 1건으로 통합돼야 한다"
    assert deduped[0]["duplicate_type"] == "EXACT_DUPLICATE"


# ── 3. MODIFIED — 같은 공고인데 마감일 등 핵심 필드가 달라짐 ────────────

def test_same_link_deadline_change_is_modified():
    items = [
        _item("c1", "2026년 제조혁신 바우처 지원사업", link="https://x.kr/c1", deadline="2026-10-01"),
        _item("c1", "2026년 제조혁신 바우처 지원사업", link="https://x.kr/c1", deadline="2026-10-20"),
    ]
    deduped = dedup_items(items)
    assert len(deduped) == 1
    assert deduped[0]["duplicate_type"] == "MODIFIED"


# ── 4. REPOSTED — 같은 소스, 제목에 재공고/추가모집 마커가 새로 붙음 ────

def test_repost_marker_added_is_reposted():
    items = [
        _item("d1", "2026년 청년창업 지원사업 참여기업 모집", link="https://x.kr/d1", deadline="2026-10-05"),
        _item("d2", "2026년 청년창업 지원사업 참여기업 모집 재공고", link="https://x.kr/d2", deadline="2026-10-25"),
    ]
    deduped = dedup_items(items)
    assert len(deduped) == 1
    assert deduped[0]["duplicate_type"] == "REPOSTED"


def test_additional_recruitment_marker_is_reposted():
    assert classify_duplicate_type(
        {"title": "2026년 예비창업패키지 2차 모집", "source": "K-Startup"},
        {"title": "2026년 예비창업패키지 모집", "source": "K-Startup"},
    ) == "REPOSTED"


# ── 5. MULTI_AGENCY_DUPLICATE — 서로 다른 기관/포털이 같은 공고를 올림 ──

def test_same_title_different_source_is_multi_agency_duplicate():
    items = [
        _item("e1", "2026년 수출바우처 참여기업 모집", link="https://bizinfo.go.kr/e1",
              deadline="2026-11-30", source="기업마당"),
        _item("e2", "2026년 수출바우처 참여기업 모집", link="https://k-startup.go.kr/e2",
              deadline="2026-11-30", source="K-Startup"),
    ]
    deduped = dedup_items(items)
    assert len(deduped) == 1
    assert deduped[0]["duplicate_type"] == "MULTI_AGENCY_DUPLICATE"


# ── 6. 다른 차수·기간은 별도 유지 (합쳐지면 안 됨) ───────────────────────

def test_different_rounds_with_distinct_titles_stay_separate():
    items = [
        _item("f1", "2026년 뿌리기업 스마트공장 지원 1차", link="https://x.kr/f1", deadline="2026-09-30"),
        _item("f2", "2026년 뿌리기업 스마트공장 지원 2차", link="https://x.kr/f2", deadline="2026-12-31"),
    ]
    deduped = dedup_items(items)
    assert len(deduped) == 2, "다른 차수·기간 공고는 하나로 합쳐지지 않고 별도 유지돼야 한다"
    assert {it["duplicate_type"] for it in deduped} == {"NEW"}


# ── classify_duplicate_type() 단위 테스트 ────────────────────────────────

def test_classify_duplicate_type_new_when_no_existing():
    assert classify_duplicate_type({"title": "x", "source": "a"}, None) == "NEW"


def test_classify_duplicate_type_exact_duplicate_requires_identical_fields():
    item = {"title": "동일 공고", "source": "기업마당", "deadline": "2026-01-01", "link": "https://x/1"}
    existing = dict(item)
    assert classify_duplicate_type(item, existing) == "EXACT_DUPLICATE"


def test_classify_duplicate_type_modified_when_deadline_differs():
    existing = {"title": "동일 공고", "source": "기업마당", "deadline": "2026-01-01", "link": "https://x/1"}
    item = {**existing, "deadline": "2026-01-15"}
    assert classify_duplicate_type(item, existing) == "MODIFIED"
