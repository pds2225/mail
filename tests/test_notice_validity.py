"""MAIL-P1A-01(TASK-031) — 공고 유효성·quarantine 회귀테스트.

로그인/오류/CAPTCHA 등 정상 공고가 아닌 입력을 exclude_reason_codes(비즈니스 규칙
제외)와 분리해 quarantine/parse_error 로 보내는지, 그리고 정상 공고는 절대
오격리(잘못 quarantine)되지 않는지를 검증한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

from mail_core.operations import notice_validity as nv  # noqa: E402


def item(**kw):
    base = {
        "id": "x1", "title": "제조업 스마트공장 구축 지원사업 모집 공고",
        "link": "https://example.com/x1", "description": "전국 소재 중소 제조기업 대상.",
        "author": "테스트기관", "deadline": "2099-12-31", "source": "테스트",
        "posted_date": "2026-01-01", "is_aggregator": False,
    }
    base.update(kw)
    return base


# ── 오류페이지 fixture는 자동발송 후보에서 반드시 빠져야 한다 ──────────────────

def test_captcha_page_title_is_quarantined():
    it = item(title="자동입력방지 보안문자를 입력해주세요", description="")
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.QUARANTINE
    assert reason == nv.REASON_ERROR_PAGE_SIGNAL
    assert evidence


def test_login_required_page_is_quarantined():
    it = item(title="정상 제목", description="로그인이 필요합니다. 다시 시도해주세요.")
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.QUARANTINE
    assert reason == nv.REASON_ERROR_PAGE_SIGNAL


def test_maintenance_page_is_quarantined():
    it = item(title="시스템 점검 안내", description="현재 서비스 점검 중입니다.")
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.QUARANTINE


def test_english_error_page_is_quarantined():
    it = item(title="Access Denied", description="You do not have permission (Forbidden).")
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.QUARANTINE


def test_missing_title_and_link_is_parse_error():
    it = item(title="", link="")
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.PARSE_ERROR
    assert reason == nv.REASON_MISSING_REQUIRED_FIELD


# ── 정상공고 오격리 최소화 ───────────────────────────────────────────────────

def test_normal_notice_is_valid():
    it = item()
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.VALID
    assert reason == ""
    assert evidence == ""


def test_notice_mentioning_own_eligibility_review_is_not_quarantined():
    """공고 자체 내용에 '점검'·'오류' 같은 단어가 업무 맥락으로 쓰여도(예: 하드웨어
    점검 지원사업) 이 정도 흔한 오탐 소스는 아니지만, 최소한 흔한 정상 공고
    패턴은 절대 걸리지 않아야 한다."""
    it = item(
        title="스마트공장 구축 지원사업 3차 모집 공고",
        description="접수기간: 2026-01-01 ~ 2026-01-31. 신청 방법: 온라인 접수.",
    )
    validity, _, _ = nv.classify_notice_validity(it)
    assert validity == nv.VALID


def test_notice_with_only_title_no_link_is_valid_not_parse_error():
    """링크가 없어도 제목이 있으면 진짜 빈 레코드는 아니다(둘 다 없을 때만 parse_error)."""
    it = item(link="")
    validity, _, _ = nv.classify_notice_validity(it)
    assert validity == nv.VALID


# ── quarantine_invalid_notices: 분리·필드 부착 ─────────────────────────────

def test_quarantine_invalid_notices_splits_and_tags_reason():
    items = [
        item(id="ok1"),
        item(id="bad1", title="보안문자 확인", description=""),
        item(id="bad2", title="", link=""),
    ]
    valid, quarantined = nv.quarantine_invalid_notices(items)
    assert [it["id"] for it in valid] == ["ok1"]
    assert {it["id"] for it in quarantined} == {"bad1", "bad2"}
    by_id = {it["id"]: it for it in quarantined}
    assert by_id["bad1"]["validity_status"] == nv.QUARANTINE
    assert by_id["bad1"]["validity_reason_code"] == nv.REASON_ERROR_PAGE_SIGNAL
    assert by_id["bad2"]["validity_status"] == nv.PARSE_ERROR


def test_quarantine_invalid_notices_does_not_mutate_valid_items():
    items = [item(id="ok1")]
    valid, quarantined = nv.quarantine_invalid_notices(items)
    assert "validity_status" not in valid[0]
    assert quarantined == []


def test_quarantine_invalid_notices_empty_list():
    valid, quarantined = nv.quarantine_invalid_notices([])
    assert valid == []
    assert quarantined == []


# ── evidence는 짧고 원문 전체를 담지 않는다 ─────────────────────────────────

def test_evidence_is_short_hint_not_full_body():
    long_body = "정상적인 공고 본문입니다. " * 30 + "로그인이 필요합니다."
    it = item(title="정상 제목", description=long_body)
    validity, reason, evidence = nv.classify_notice_validity(it)
    assert validity == nv.QUARANTINE
    assert evidence == "로그인이 필요"
    assert len(evidence) < 50


# ── execute_monitor() 파이프라인 통합: 오류페이지 fixture 자동발송 후보 0건 ───

import monitor as m  # noqa: E402
from datetime import datetime  # noqa: E402


def test_execute_monitor_never_sends_quarantined_error_page_as_candidate(monkeypatch):
    """ACCEPTANCE_CRITERIA: 오류페이지 fixture는 자동발송 후보(final_mail_count·
    발송 그룹)에 절대 포함되지 않아야 하고, 정상 공고는 여전히 정상 처리돼야 한다
    (정상공고 오격리 최소화)."""
    items = [
        {"id": "normal1", "title": "지식재산 활용 지원사업 공고", "description": "",
         "link": "https://x/1", "author": "기관", "deadline": "2099-12-31",
         "source": "RIPC", "posted_date": "2000-01-01", "is_aggregator": False,
         "detail_extraction": {"status": "SUCCESS"}},
        {"id": "errpage1", "title": "자동입력방지 보안문자를 입력해주세요", "description": "",
         "link": "https://x/2", "author": "기관", "deadline": "2099-12-31",
         "source": "RIPC", "posted_date": "2000-01-01", "is_aggregator": False,
         "detail_extraction": {"status": "SUCCESS"}},
    ]
    monkeypatch.setattr(m, "fetch_all", lambda sites, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{"id": "g", "name": "t", "active": True,
                                                    "or_keywords": ["지식재산"], "recipients": []}])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": True, "days_back": 1, "raw_all_enabled": False,
        "raw_all_recipients": [], "company_match_enabled": False,
    })
    monkeypatch.setattr(m, "load_watchlist", lambda: {
        "keywords": ["지식재산", "보안문자"], "urls": [], "recipients": ["r@example.test"]})
    sent_bodies: list = []
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: sent_bodies.append((s, b)))
    monkeypatch.setattr(m, "alert_ntfy", lambda *a, **k: None)

    result = m.execute_monitor(allow_send=True, include_raw_all=False, persist_seen=False)

    assert result.get("quarantine_items_dropped") == 1
    # 오류페이지가 워치리스트 강제포함 경로로도 새어나가지 않아야 한다(가장 중요).
    for _subject, body in sent_bodies:
        assert "자동입력방지" not in body
        assert "보안문자" not in body

