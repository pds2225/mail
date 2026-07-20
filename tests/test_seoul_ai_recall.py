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


ROOT = Path(__file__).resolve().parent.parent


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
    """지원분야(support_field)에만 AI가 있어도 그룹 키워드 통과.

    신청기간은 실행 시점 기준 미래 날짜로 동적 생성 — 고정 날짜(2026.07.01)는
    그 날짜가 지나는 순간 CLOSED_DEADLINE 으로 오판되는 시한폭탄이었다(2026-07 실측).
    """
    from datetime import datetime, timedelta
    future = (datetime.now(m.KST) + timedelta(days=30)).strftime("%Y.%m.%d")
    ev = _ev({
        "title": "인공지능 사업화 지원 모집",
        "description": f"신청기간 {future}~",
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


def test_nipa_regionless_ai_promoted_to_main_list():
    """NIPA(국가기관 전국사업)의 지역 단서 없는 AI 공고: region_field='전국' 보강으로
    '지역 미상' 하단 강등이 아니라 본문 상단(is_relevant) 노출 — 'AI 공고 안 옴' 근본수정.
    fetch_nipa 가 실제로 붙이는 region_field='전국' 을 그대로 재현한다."""
    from datetime import datetime, timedelta
    future = (datetime.now(m.KST) + timedelta(days=30)).strftime("%Y.%m.%d")
    item = {
        "title": "2026년 소형 데이터센터 기반 AI산업 성장 지원 사업 공고",
        "description": f"수요기업 모집 신청기간 {future}~",   # 지역 단서 없음
        "author": "정보통신산업진흥원(NIPA)",
        "region_field": "전국",                              # fetch_nipa 보강값
    }
    ev = _ev(item)
    assert ev["region_status"] == "eligible"
    assert ev["is_relevant"] is True
    assert not ev.get("region_unknown_review")   # 하단 '지역 미상'으로 강등되면 안 됨


def test_nipa_regionless_without_nationwide_would_demote():
    """대조군: region_field 없으면 동일 공고가 지역 미상('확인 필요')으로 강등된다
    (= 이번 수정 전의 버그 상태). region_field='전국' 보강이 유일한 차이임을 고정한다."""
    from datetime import datetime, timedelta
    future = (datetime.now(m.KST) + timedelta(days=30)).strftime("%Y.%m.%d")
    item = {
        "title": "2026년 소형 데이터센터 기반 AI산업 성장 지원 사업 공고",
        "description": f"수요기업 모집 신청기간 {future}~",
        "author": "정보통신산업진흥원(NIPA)",
    }
    ev = _ev(item)
    assert ev["region_status"] == "unknown"
    assert ev["is_relevant"] is False
    assert ev.get("region_unknown_review") is True


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


# ── 2026-06-25: 충북 공고 누출 차단 — 타지역 신청자한정인데 서울이 문의/운영 보일러플레이트에만 등장 ──
def test_chungbuk_applicant_with_seoul_contact_blocked():
    """'충북지역 중소기업 대상' + '문의: 서울특별시 …' → 서울 그룹 not_eligible.
    충북이 신청자-한정이고 서울은 문의처 주소뿐 → 적격 오판(누출) 차단."""
    ev = _ev({
        "title": "충북 AI 디지털전환 바우처 지원사업",
        "description": "충북지역 중소기업 대상 인공지능 도입 지원. 문의: 서울특별시 강남구 운영사무국. 신청 2026.07.01~2026.07.31",
        "author": "충북테크노파크",
    })
    assert ev["region_status"] == "not_eligible"
    assert ev["is_relevant"] is False
    assert ev["region_unknown_review"] is False


def test_chungbuk_soje_with_seoul_operator_blocked():
    """'충북 소재 중소기업 대상' + '운영기관: 서울' → not_eligible."""
    ev = _ev({
        "title": "AI 바우처 모집",
        "description": "충북 소재 중소기업 대상. 운영기관: 서울 강남 사무국. 모집",
        "author": "충북TP",
    })
    assert ev["region_status"] == "not_eligible"


def test_seoul_chungbuk_joint_still_eligible():
    """서울·충북 공동(서울도 신청자) → eligible(recall 보존)."""
    ev = _ev({
        "title": "AI 공동지원 모집",
        "description": "서울 충북 소재 중소기업 대상. 모집",
        "author": "TP",
    })
    assert ev["region_status"] == "eligible"


def test_applicant_restricted_regions_helper():
    assert m._applicant_restricted_regions("충북지역 중소기업 대상") == {"충북"}
    assert m._applicant_restricted_regions("충청북도 소재 기업") == {"충북"}
    assert m._applicant_restricted_regions("문의: 서울특별시 강남구 사무국") == set()


# ── 2026-06-25: 4월(과거) 공고 누출 차단 — 게시일 불명 + 본문 날짜 단서가 오래됨 ──
def test_april_date_unknown_excluded_by_recency():
    """게시일 불명 + 신청기간 4월(과거) 단서 → recall 정책에서도 제외(검토대기로)."""
    from datetime import datetime
    now = datetime(2026, 6, 25, tzinfo=m.KST)
    items = [{
        "id": "apr", "title": "2026 AI SaaS 사업화 지원 모집",
        "description": "서울소재 기업 대상. 신청기간 2026.04.01 ~ 2026.04.30. 모집",
        "author": "서울TP", "posted_date": "",
    }]
    included, remaining = m.split_unknown_by_policy(items, "recall", max_age_days=40, now=now)
    assert included == []
    assert len(remaining) == 1


def test_dateless_unknown_preserved_for_recall():
    """날짜 단서가 전혀 없는 게시일 불명 공고는 recall 위해 보존(나이 가드 미발동)."""
    from datetime import datetime
    now = datetime(2026, 6, 25, tzinfo=m.KST)
    items = [{
        "id": "none", "title": "AI 솔루션 지원 모집공고",
        "description": "서울소재 스타트업 신청접수", "author": "서울TP", "posted_date": "",
    }]
    included, _ = m.split_unknown_by_policy(items, "recall", max_age_days=40, now=now)
    assert len(included) == 1
