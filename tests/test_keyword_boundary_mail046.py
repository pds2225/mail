from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_password")
os.environ.setdefault("GMAIL_ADDRESS", "test@example.test")

from mail_core.matching import keyword_match as matcher
from mail_core.matching import scoring
from monitor import KST, evaluate_notice, keyword_match


TODAY = datetime(2026, 10, 16, tzinfo=KST).date()


def _group(**overrides):
    value = {
        "id": "mail046-test",
        "required_conditions": {"regions": ["인천"]},
        "or_keywords": ["AI"],
        "and_keyword_groups": [],
        "exclude_keywords": [],
        "priority_keywords": [],
        "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
    }
    value.update(overrides)
    return value


def _item(title: str, description: str = ""):
    return {
        "id": "mail046-fixture",
        "title": title,
        "description": description,
        "author": "테스트기관",
        "deadline": "2099.10.1 ~ 2099.10.31",
        "source": "테스트",
        "link": "https://example.test/notices/1",
    }


def test_ascii_keyword_uses_token_boundaries():
    assert not matcher.keyword_hit("MAIL TRAIN", "AI")
    assert matcher.keyword_hit("AI 기업 모집", "AI")
    assert matcher.keyword_hit("mail AI2", "AI2")
    assert not matcher.keyword_hit("xAI", "AI")


def test_aliases_match_both_directions_and_curated_word_forms():
    assert matcher.keyword_hit("인공지능 창업기업 모집", "AI")
    assert matcher.keyword_hit("AI 기반 인공지능", "인공지능")
    assert matcher.keyword_hit("소프트웨어 기업", "SW")
    assert matcher.keyword_hit("창업 기업 지원사업", "창업기업")
    assert matcher.keyword_hit("지원하는 기업 모집", "지원")
    assert matcher.keyword_hit("지원함", "지원")
    assert matcher.keyword_hit("수출바우처 참여기업", "수출")
    assert not matcher.keyword_hit("수출", "수출바우처")


def test_short_korean_keyword_allows_particles_but_not_arbitrary_word_suffix():
    assert matcher.keyword_hit("기업은 신청할 수 있음", "기업")
    assert matcher.keyword_hit("인천 창업 모집", "창업")
    assert not matcher.keyword_hit("일반창업패키지", "업")


def test_negated_keyword_is_excluded_and_reported_by_group_gate():
    evaluated = evaluate_notice(
        _item("인천 AI 기업 제외 모집 공고"), _group(), TODAY
    )
    assert evaluated["group_keyword_pass"] is False
    assert evaluated["negated_hits"] == ["AI"]
    assert "INDUSTRY_NOT_MATCHED" in evaluated["exclude_reason_codes"]
    assert any("부정 문맥" in note and "AI" in note for note in evaluated["notes"])


def test_positive_alternative_survives_a_separate_negated_keyword():
    evaluated = evaluate_notice(
        _item("인천 AI 기업 제외, " + ("가" * 25) + " SaaS 기업 모집 공고"),
        _group(or_keywords=["AI", "SaaS"]),
        TODAY,
    )
    assert evaluated["group_keyword_pass"] is True
    assert evaluated["negated_hits"] == ["AI"]


def test_legacy_keyword_match_uses_aliases_and_negation():
    assert keyword_match(
        {"title": "인공지능 사업", "description": "", "author": ""},
        {"keywords": ["AI"], "logic": "OR"},
    )
    assert not keyword_match(
        {"title": "AI 기업 제외", "description": "", "author": ""},
        {"keywords": ["AI"], "logic": "OR"},
    )


@pytest.mark.parametrize("legacy_keywords", [["AI"], {"keywords": ["AI"], "logic": "OR"}])
def test_legacy_group_config_keeps_gate_and_records_negation(legacy_keywords):
    evaluated = evaluate_notice(
        _item("인천 AI 기업 제외 모집 공고"),
        {"id": "legacy", "keywords": legacy_keywords, "exclude_keywords": []},
        TODAY,
    )
    assert evaluated["group_keyword_pass"] is False
    assert evaluated["negated_hits"] == ["AI"]


def test_scoring_uses_same_alias_and_negation_rules():
    alias_score = scoring.compute_score(
        {"title": "인공지능 사업"},
        {"or_keywords": ["AI"], "priority_keywords": [], "required_conditions": {}},
    )
    assert alias_score["breakdown"]["or_hits"] == 1

    negated_score = scoring.compute_score(
        {"title": "AI 기업 제외"},
        {"or_keywords": ["AI"], "priority_keywords": [], "required_conditions": {}},
    )
    assert negated_score["breakdown"]["or_hits"] == 0
    assert negated_score["breakdown"]["negated_hits"] == ["AI"]
    assert any("negated" in reason for reason in negated_score["reasons"])


def test_negation_exception_and_twenty_character_window():
    assert matcher.keyword_hit("AI 기업을 제외하지 않는 조건", "AI")
    assert not matcher.keyword_hit("AI는 제외하지 않지만 신청 불가", "AI")
    assert matcher.keyword_hit("제외 " + ("가" * 21) + " AI 모집", "AI")
    assert not matcher.keyword_hit("AI " + ("가" * 16) + " 제외", "AI")


def test_missing_alias_file_falls_back_to_no_aliases(tmp_path):
    missing = tmp_path / "keyword_aliases.json"
    assert matcher.load_keyword_aliases(missing) == {}
    assert not matcher.keyword_match_details(
        "인공지능 모집", "AI",
        aliases=matcher.load_keyword_aliases(missing),
        variants=matcher.load_keyword_variants(missing),
    )[0]
