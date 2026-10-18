import os

for key in ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "test-value")

import monitor as m
from mail_core.delivery.digest_table import section_of
from mail_core.matching.core_sources import map_category_to_support_types
from mail_core.matching.scoring import compute_score, score_and_filter
from mail_core.matching.support_types import classify_support_types


def test_support_type_vocabulary_is_shared_and_all_matching_types_are_retained():
    item = {"title": "수출바우처와 엔젤투자 연계 참여기업 모집", "description": ""}
    types = m.classify_support_type(item)
    assert types == ["투자", "지원금/바우처"]
    assert map_category_to_support_types("사업화·멘토링·투자") == [
        "투자", "지원금/바우처", "컨설팅·교육·상담"
    ]


def test_card_shows_primary_type_and_count_of_additional_types():
    item = {"title": "수출바우처 참여기업 모집", "_types": ["지원금/바우처", "투자"]}
    cell = m._mail_support_cell(item)
    assert cell.endswith(" 외 1")
    assert section_of(cell) == "바우처"


def test_ascii_aliases_keep_word_boundaries():
    assert "투자" not in classify_support_types("xvc support")


def test_notice_evaluation_to_digest_card_keeps_multiple_types_visible():
    item = {
        "title": "수출바우처 엔젤투자 참여기업 모집",
        "description": "전국 중소기업 신청접수",
        "deadline": "2026-12-01",
    }
    evaluated = m.evaluate_notice(item, today=m._now_kst().date())
    row = m._digest_row(evaluated, today=m._now_kst().date())
    assert evaluated["_types"] == ["투자", "지원금/바우처"]
    assert row["지원"] == "바우처 외 1"


def test_priority_score_is_capped_below_suitability_threshold():
    item = {"title": "스마트공장 제조혁신", "description": ""}
    group = {"priority_keywords": ["스마트공장", "제조혁신", "제조"]}
    scored = compute_score(item, group)
    assert scored["breakdown"]["priority_score"] == 30
    assert scored["score"] == 30
    assert scored["score"] < 50
    filtered = score_and_filter([item], {**group, "score_threshold": 50})
    assert filtered["passed"] == []
    assert filtered["rejected"] == [item]


def test_priority_keyword_without_application_signal_is_not_relevant():
    group = {
        "id": "test",
        "support_types": m.ALL_SUPPORT_TYPES,
        "priority_keywords": ["스마트공장"],
        "or_keywords": [],
        "and_keyword_groups": [],
        "exclude_keywords": [],
        "required_conditions": {},
    }
    result = m.evaluate_notice({"title": "스마트공장", "description": ""}, group, m._now_kst().date())
    assert result["is_relevant"] is False
