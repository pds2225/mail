"""필터 셀렉터 보강 회귀 — date_unknown·사유코드 분리·카테고리 AI·잡공고 그룹적용."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

import monitor as m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _ai_group() -> dict:
    groups = json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))
    return next(g for g in groups if g["id"] == "grp_ai_saas")


def test_date_unknown_recall_includes_short_recruit_title():
    """게시일 없음 + '모집' 제목은 application_like 기준으로 중위험 → recall 포함."""
    now = datetime(2026, 8, 2, tzinfo=m.KST)
    items = [{
        "id": "short",
        "title": "데이터 바우처 모집",
        "description": "상세확인",
        "posted_date": "",
    }]
    assert m.assess_date_unknown_risk(items[0]) == "중간"
    included, remaining = m.split_unknown_by_policy(items, "recall", max_age_days=40, now=now)
    assert [it["id"] for it in included] == ["short"]
    assert remaining == []


def test_date_unknown_recall_excludes_stale_april_clue():
    now = datetime(2026, 8, 2, tzinfo=m.KST)
    items = [{
        "id": "apr",
        "title": "AI 지원사업 모집",
        "description": "신청기간 2026.04.01 ~ 2026.04.30",
        "posted_date": "",
    }]
    included, remaining = m.split_unknown_by_policy(items, "recall", max_age_days=40, now=now)
    assert included == []
    assert [it["id"] for it in remaining] == ["apr"]


def test_yesterday_post_with_future_deadline_included():
    """게시일=어제, 신청기간=미래 → 날짜필터·마감 모두 통과."""
    now = datetime(2026, 8, 3, 10, 0, tzinfo=m.KST)  # 월요일
    today = now.date()
    yday = today - timedelta(days=1)  # 일요일 — 주말 창에 포함
    item = {
        "title": "AI 솔루션 지원사업 모집",
        "description": "서울 소재 신청접수",
        "posted_date": yday.isoformat(),
        "application_period": {
            "start": today.isoformat(),
            "end": (today + timedelta(days=45)).isoformat(),
        },
    }
    matched, _unk, _exc = m.partition_posted_dates([item], days_back=3, now_dt=now)
    assert matched and matched[0]["posted_date"] == yday.isoformat()
    ev = m.evaluate_notice(item, _ai_group(), today=today)
    assert ev["deadline_status"] == "open"
    assert ev["is_relevant"] is True


def test_report_junk_blocks_group_filter():
    ev = m.evaluate_notice(
        {"title": "우수기업 선정결과 발표", "description": "서울 AI 결과"},
        _ai_group(),
    )
    assert ev["is_relevant"] is False
    assert "REPORT_JUNK" in ev["exclude_reason_codes"]


def test_category_and_hashtags_match_ai_keywords():
    for item in (
        {"title": "스타트업 지원사업 모집", "description": "서울 소재 신청", "category": "AI"},
        {"title": "스타트업 지원사업 모집", "description": "서울 소재 신청", "hashtags": ["AI"]},
    ):
        ev = m.evaluate_notice(item, _ai_group())
        assert ev["group_keyword_pass"] is True
        assert ev["is_relevant"] is True


def test_reason_codes_are_path_specific():
    """동일 '비지원'이라도 경로별 코드가 갈라진다."""
    group = {
        **_ai_group(),
        "exclude_keywords": ["성료"],
    }
    group_hit = m.evaluate_notice(
        {"title": "AI 지원사업 모집 성료", "description": "서울 신청"},
        group,
    )
    assert "GROUP_EXCLUSION" in group_hit["exclude_reason_codes"]

    non_app = m.evaluate_notice(
        {"title": "운영지원공고", "description": "서울 소재 AI"},
        _ai_group(),
    )
    assert "NOT_APPLICATION_LIKE" in non_app["exclude_reason_codes"]
    assert "NOT_GRANT_NOTICE" not in non_app["exclude_reason_codes"]


def test_ambiguous_infogonggae_goes_to_review_not_hard():
    """정보공개+모집(지원사업 신호 없음) → AMBIGUOUS_NOTICE review 분리."""
    ev = m.evaluate_notice(
        {
            "title": "2026년 정보공개 고객 모니터링단 모집공고",
            "description": "서울 소재 신청",
        },
        _ai_group(),
    )
    assert ev["is_relevant"] is False
    assert "AMBIGUOUS_NOTICE" in ev["exclude_reason_codes"]
    assert ev["review_needed"] is True
    assert "REPORT_JUNK" not in ev["exclude_reason_codes"]


def test_environment_infogonggae_support_still_not_ambiguous():
    """환경정보공개 지원사업은 애매 분리 대상이 아니다."""
    assert m.ambiguous_notice_reason({
        "title": "자발적 환경정보공개 지원사업 참여기업 모집 공고",
    }) == ""


def test_fund_priority_sorts_first():
    low = {"title": "AI 모집", "priority_keyword": True, "priority_keywords": ["혁신바우처"],
           "relevance_score": 50, "deadline_status": "open"}
    high = {"title": "사업화지원금 모집", "priority_keyword": True,
            "priority_keywords": ["사업화지원금"], "relevance_score": 20, "deadline_status": "open"}
    assert m._notice_sort_key(high) < m._notice_sort_key(low)


def test_refine_score_llm_demotes_on_llm_reject(monkeypatch):
    group = {
        "id": "t",
        "or_keywords": ["AI"],
        "priority_keywords": [],
        "exclude_keywords": [],
        "required_conditions": {"regions": ["서울"]},
        "score_threshold": 1,
        "llm_check_enabled": True,
        "llm_check_threshold_band": [0, 100],
        "llm_call_limit_per_run": 5,
    }
    items = [{"title": "서울 AI 지원사업 모집", "description": "서울", "summary": "x"}]

    def _fake_score(item, group):
        return {"score": 50, "breakdown": {}, "reasons": ["or 1x"]}

    def _fake_llm(item, group):
        return {"is_relevant": False, "confidence": 0.9, "reason": "test reject"}

    monkeypatch.setattr(m, "_SCORE_OK", True)
    import mail_core.matching.scoring as scoring
    monkeypatch.setattr(scoring, "compute_score", _fake_score)
    monkeypatch.setattr(scoring, "llm_relevance_check", _fake_llm)
    monkeypatch.setattr(m, "_score_and_filter", scoring.score_and_filter)

    passed, demoted = m.refine_included_by_score_llm(items, group)
    assert passed == []
    assert len(demoted) == 1
    assert "SCORE_OR_LLM_REJECT" in demoted[0]["exclude_reason_codes"]


def test_resolve_region_single_entry_incheon_vs_other():
    """인천은 classify_region, 타광역은 for_group — 단일 진입점 resolve_region."""
    bupyeong = {"title": "인천 부평구 소상공인 지원금 신청 공고", "description": ""}
    assert m.resolve_region(bupyeong, None)["region_status"] == "not_eligible"
    incheon_g = {
        "applicant_region_city": "인천광역시",
        "applicant_region_district": "남동구",
    }
    assert m.resolve_region(bupyeong, incheon_g)["region_status"] == "not_eligible"
    assert m.uses_incheon_region_engine(incheon_g) is True

    busan_g = {
        "applicant_region_city": "부산광역시",
        "applicant_region_label": "부산",
        "applicant_region_district": "해운대구",
    }
    assert m.uses_incheon_region_engine(busan_g) is False
    busan_notice = {"title": "[부산] 해운대구 중소기업 지원 모집", "description": "부산 소재"}
    assert m.resolve_region(busan_notice, busan_g)["region_status"] == "eligible"


def test_for_group_peer_district_blocks_other_gu():
    """for_group에도 동일 광역 타 구 전용 차단(부평구 vs 남동구)."""
    g = {
        "applicant_region_city": "인천광역시",
        "applicant_region_label": "인천",
        "applicant_region_district": "남동구",
        "applicant_districts": ["남동구"],
    }
    other = {"title": "인천 부평구 소재 기업 지원", "description": "부평구 소재 기업 대상"}
    assert m.classify_region_for_group(other, g)["region_status"] == "not_eligible"
    own = {"title": "인천 남동구 소재 기업 지원", "description": "남동구 소재"}
    assert m.classify_region_for_group(own, g)["region_status"] == "eligible"
