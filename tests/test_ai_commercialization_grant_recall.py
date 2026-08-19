"""MAIL-012: AI 사업화지원금 공고는 1·2차와 워치리스트에서 빠지지 않는다.

배경: MAIL-005/006 이후 예비창업 본공고는 살아났지만, 제목에 `참여기업`이
있는 AI 사업화지원금은 precision_exclude 감점만 먹고 OR 점수가 0이 되어
2차에서 탈락했다. 사용자는 이 유형을 전수 수집하기를 원한다.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@example.invalid",
    "GMAIL_APP_PASSWORD": "test_pass",
    "MONITOR_NO_PERSIST_SEEN": "1",
}.items():
    os.environ.setdefault(_key, _value)

import monitor  # noqa: E402
from mail_core.matching import scoring  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
GROUPS = json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))
GROUP = next(g for g in GROUPS if g["id"] == "grp_prestartup_ai")
WATCHLIST = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
TODAY = date(2026, 8, 19)

GRANT_TITLES = [
    "2026년 AI 사업화지원금 모집 공고",
    "2026년 AI 사업화 지원금 참여기업 모집",
    "인공지능 사업화지원금 지원사업",
    "인공지능 사업화 자금 지원 공고",
    "생성형 AI 사업화자금 모집",
    "AI 사업화 지원사업 참여자 모집",
]


def _item(title: str, description: str = "", **overrides) -> dict:
    item = {
        "id": title[:24],
        "title": title,
        "description": description or "전국 대상. 사업화자금을 지원합니다. 신청 접수 중.",
        "author": "공공기관",
        "source": "MAIL-012 회귀",
        "link": "https://example.go.kr/notice/ai-grant",
        "posted_date": "2026-08-19",
        "deadline": "2026-09-30",
        "application_period": {
            "start": "2026-08-19",
            "end": "2026-09-30",
            "display": "2026-08-19 ~ 2026-09-30",
        },
        "region_field": "전국",
        "is_aggregator": False,
    }
    item.update(overrides)
    return item


def _bucket(item: dict) -> tuple[str, dict]:
    diagnostics = monitor.filter_for_group_with_diagnostics([item], GROUP, TODAY)
    for name in ("included", "region_unknown", "review", "excluded"):
        if diagnostics[name]:
            return name, diagnostics[name][0]
    raise AssertionError("공고가 어떤 진단 버킷에도 들어가지 않음")


def test_group_keep_keywords_cover_commercialization_grants():
    for kw in ("사업화지원금", "사업화자금", "사업화지원"):
        assert kw in GROUP["precision_keep_keywords"]
    for kw in ("AI 사업화", "인공지능 사업화", "AI 사업화지원금"):
        assert kw in GROUP["or_keywords"]


def test_and_groups_include_ai_grant_pairs():
    pairs = {tuple(g) for g in GROUP["and_keyword_groups"]}
    assert ("AI", "지원금") in pairs
    assert ("인공지능", "지원금") in pairs
    assert ("AI", "사업화자금") in pairs
    assert ("인공지능", "사업화자금") in pairs


@pytest.mark.parametrize("title", GRANT_TITLES)
def test_ai_commercialization_grant_survives_group_and_score(title: str):
    item = _item(title)
    bucket, evaluated = _bucket(item)
    assert bucket == "included", evaluated
    assert evaluated["is_relevant"] is True
    assert evaluated["group_keyword_pass"] is True

    passed, rejected = monitor.refine_included_by_score_llm([evaluated], GROUP)
    assert passed, {
        "title": title,
        "rejected": [it.get("exclude_reason_codes") for it in rejected],
        "score": evaluated.get("_match_score"),
        "breakdown": scoring.compute_score(item, GROUP)["breakdown"],
    }
    assert not rejected
    assert passed[0].get("_match_score", 0) >= GROUP.get("score_threshold", 1)


@pytest.mark.parametrize("title", GRANT_TITLES)
def test_watchlist_force_includes_ai_grant_titles(title: str):
    assert monitor.is_watchlisted({"title": title, "author": "창업진흥원"}, WATCHLIST)


def test_participant_word_does_not_drop_ai_grant():
    """MAIL-006 참여기업 감점이 사업화지원금 keep 을 이기면 안 된다."""
    item = _item(
        "2026년 AI 사업화지원금 참여기업 모집",
        "기창업·참여기업 문구가 있어도 사업화지원금을 지급하는 공고.",
    )
    s = scoring.compute_score(item, GROUP)
    assert s["breakdown"]["precision_keep_hits"] >= 1
    assert s["breakdown"]["precision_penalty"] == 0
    assert s["score"] >= int(GROUP.get("score_threshold", 1))
    out = scoring.score_and_filter([item], GROUP)
    assert out["audit"][0]["decision"] == "passed"
    assert not out["rejected"]


def test_established_solution_intro_still_dropped():
    """MAIL-006 유지: 기창업 솔루션 도입만 있으면 예비창업 메일에서 뺀다."""
    item = _item(
        "AI 솔루션 도입 참여기업 모집",
        "기창업 중소기업의 AI 솔루션 도입 비용을 지원합니다.",
    )
    bucket, evaluated = _bucket(item)
    assert bucket == "included", evaluated
    passed, rejected = monitor.refine_included_by_score_llm([evaluated], GROUP)
    assert not passed
    assert rejected
    assert "SCORE_OR_LLM_REJECT" in (rejected[0].get("exclude_reason_codes") or [])


def test_non_ai_commercialization_grant_does_not_enter_prestartup_group():
    item = _item(
        "2026년 화장품 사업화지원금 모집",
        "뷰티 제조 중소기업 대상 사업화자금을 지원합니다. 전국.",
    )
    bucket, evaluated = _bucket(item)
    assert bucket in {"review", "excluded"}, evaluated
    assert evaluated["group_keyword_pass"] is False
    assert monitor.is_watchlisted(
        {"title": item["title"], "author": "중기부"}, WATCHLIST
    ) is False


def test_consultant_watchlist_keywords_still_present():
    for kw in ("컨설턴트 신청", "컨설턴트 모집", "경영지도사 모집"):
        assert kw in WATCHLIST["keywords"]
