"""서울 소재 + AI 사업 공고 recall 회귀 — grp_ai_saas 엔진 검증."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

import monitor as m  # noqa: E402


ROOT = Path(__file__).resolve().parent


def _grp_ai_saas() -> dict:
    groups = json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))
    return next(g for g in groups if g["id"] == "grp_ai_saas")


def _ev(item: dict) -> dict:
    return m.evaluate_notice(item, _grp_ai_saas())


def test_seoul_compact_soji_region_eligible_and_relevant():
    """서울소재(띄어쓰기 없음) + AI 키워드 + 모집 → 본문 매칭."""
    ev = _ev({
        "title": "2026 AI 솔루션 지원사업 모집 공고",
        "description": "서울소재 스타트업 신청접수",
        "author": "서울TP",
    })
    assert ev["region_status"] == "eligible"
    assert ev["is_relevant"] is True


def test_ai_in_support_field_matches_group_keywords():
    """지원분야(support_field)에만 AI가 있어도 그룹 키워드 통과."""
    ev = _ev({
        "title": "인공지능 사업화 지원 모집",
        "description": "신청기간 2026.07.01~",
        "support_field": "AI/데이터",
        "author": "NIPA",
    })
    assert ev["industry_status"] == "matched"
    assert ev.get("region_unknown_review") or ev["is_relevant"]


def test_seoul_headquarters_phrase_region():
    """'서울에 본사' 표현 + AI 본문."""
    ev = _ev({
        "title": "스타트업 지원 공고",
        "description": "서울에 본사를 둔 AI 기업 신청",
        "author": "중소벤처부",
    })
    assert ev["region_status"] == "eligible"
    assert ev["is_relevant"] is True


def test_nationwide_ai_still_eligible_for_seoul_group():
    """전국 대상 AI 공고는 서울 기업도 신청 가능 → eligible."""
    ev = _ev({
        "title": "[전국] AI 바우처 모집",
        "description": "전국 중소기업 대상 신청접수",
        "author": "서울창경",
    })
    assert ev["region_status"] == "eligible"
    assert ev["is_relevant"] is True


def test_busan_only_still_blocked():
    """부산 한정은 서울 그룹에서 제외(precision)."""
    ev = _ev({
        "title": "부산 AI 지원 모집",
        "description": "부산 소재 기업만 신청",
        "author": "부산TP",
    })
    assert ev["region_status"] == "not_eligible"
    assert ev["is_relevant"] is False


def test_application_like_from_grant_signal():
    """'모집' 단독 제목도 신청성 공고로 인정(recall)."""
    assert m._application_like("2026 ai 스타트업 모집")


def test_keyword_match_text_includes_support_field():
    text = m._keyword_match_text({"title": "지원", "support_field": "인공지능"})
    assert "인공지능" in text
