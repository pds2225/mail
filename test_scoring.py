"""Unit tests for scoring.py.

Run: python -m pytest test_scoring.py -v
"""
from __future__ import annotations

import scoring


def _group(**overrides):
    g = {
        "id": "test_grp",
        "or_keywords": ["수출", "해외"],
        "priority_keywords": ["스마트공장", "수출바우처"],
        "exclude_keywords": ["설명회", "교육일정"],
        "required_conditions": {"regions": ["인천"]},
        "score_threshold": 50,
        "weights": {
            "priority_match": 30,
            "or_keyword_match": 5,
            "exclude_penalty": -50,
            "region_match": 20,
        },
    }
    g.update(overrides)
    return g


def _item(title="", summary=""):
    return {"title": title, "summary": summary}


def test_compute_score_priority_hit_boosts():
    s = scoring.compute_score(_item("인천 스마트공장 지원사업"), _group())
    assert s["score"] >= 50
    assert s["breakdown"]["priority_hits"] == 1


def test_compute_score_exclude_penalty_drops():
    s = scoring.compute_score(_item("스마트공장 설명회 안내"), _group())
    assert s["breakdown"]["exclude_hits"] == 1
    assert s["score"] < 50


def test_compute_score_or_only_low():
    s = scoring.compute_score(_item("수출 관련 공지"), _group())
    assert s["breakdown"]["or_hits"] == 1
    assert s["breakdown"]["priority_hits"] == 0


def test_compute_score_region_only_no_keyword():
    s = scoring.compute_score(_item("인천 행정 안내"), _group())
    assert s["breakdown"]["region_match"] == 1


def test_compute_score_empty_item():
    s = scoring.compute_score(_item(), _group())
    assert s["score"] == 0


def test_score_and_filter_backward_compat_no_threshold():
    """score_threshold 없으면 입력 그대로 통과 (회귀 방지)."""
    items = [_item("아무 제목"), _item("다른 제목")]
    out = scoring.score_and_filter(items, {"id": "legacy"})
    assert len(out["passed"]) == 2
    assert len(out["rejected"]) == 0


def test_score_and_filter_threshold_filters():
    items = [
        _item("인천 스마트공장 지원사업 신청"),  # passes
        _item("일반 행정 공지"),  # fails
    ]
    out = scoring.score_and_filter(items, _group())
    assert len(out["passed"]) == 1
    assert len(out["rejected"]) == 1
    assert all("decision" in a for a in out["audit"])


def test_score_and_filter_exclude_pushes_to_reject():
    items = [_item("스마트공장 설명회 일정")]
    out = scoring.score_and_filter(items, _group())
    assert len(out["passed"]) == 0
    assert len(out["rejected"]) == 1
