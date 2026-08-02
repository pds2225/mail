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
