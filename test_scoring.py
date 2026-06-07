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


# ── zero-match 개선: Recall (R1, R2) ──────────────────────────────────────────

def test_r1_haystack_reads_description_and_raw_text():
    """R1: 키워드가 description/raw_text 에만 있어도 히트로 잡혀야 한다 (recall)."""
    s_desc = scoring.compute_score(
        {"title": "공고 안내", "description": "인천 스마트공장 구축 지원"}, _group()
    )
    assert s_desc["breakdown"]["priority_hits"] == 1  # '스마트공장' from description

    s_raw = scoring.compute_score(
        {"title": "공고 안내", "raw_text": "수출바우처 신청 접수"}, _group()
    )
    assert s_raw["breakdown"]["priority_hits"] == 1  # '수출바우처' from raw_text


def test_r2_or_cluster_bonus_lets_multi_or_pass_without_priority():
    """R2: or-키워드 3개 이상 적중하면 priority 없이도 임계값을 넘는다 (recall 회복)."""
    grp = _group(
        or_keywords=["화장품", "뷰티", "해외전시회", "수출지원"],
        priority_keywords=["스마트공장"],  # 이 공고에는 없음
        score_threshold=50,
    )
    item = _item("인천 화장품 뷰티 해외전시회 수출지원 안내")
    s = scoring.compute_score(item, grp)
    assert s["breakdown"]["or_hits"] >= 3
    assert s["breakdown"]["or_cluster"] == 1
    assert s["breakdown"]["priority_hits"] == 0
    assert s["score"] >= 50


def test_r2_or_cluster_below_threshold_no_bonus():
    """R2 경계: or-히트가 3개 미만이면 군집 보너스가 붙지 않는다."""
    grp = _group(or_keywords=["화장품", "뷰티", "해외전시회"], priority_keywords=[])
    s = scoring.compute_score(_item("화장품 뷰티 공고"), grp)  # 2 히트
    assert s["breakdown"]["or_hits"] == 2
    assert s["breakdown"]["or_cluster"] == 0


def test_r2_cluster_weights_overridable():
    """신규 가중치는 group.weights 로 override 가능 (하위호환)."""
    grp = _group(
        or_keywords=["a계열", "b계열", "c계열"],
        priority_keywords=[],
        weights={"or_cluster_bonus": 0},
    )
    s = scoring.compute_score(_item("a계열 b계열 c계열 공고"), grp)
    assert s["breakdown"]["or_cluster"] == 1
    # 보너스 0 으로 override 했으므로 군집 보너스 점수 기여가 없다
    assert s["score"] == 3 * scoring.DEFAULT_WEIGHTS["or_keyword_match"]


# ── zero-match 개선: Precision (P1, P2) ───────────────────────────────────────

def test_p1_region_mismatch_penalizes_other_region_only():
    """P1: 그룹 지역(인천) 부재 + 타 광역(부산)만 언급 → 감점, 임계값 미만 (precision)."""
    grp = _group(
        or_keywords=["화장품", "뷰티", "해외전시회", "수출지원"],
        required_conditions={"regions": ["인천"]},
        score_threshold=50,
    )
    item = _item("부산 화장품 뷰티 해외전시회 수출지원 전용 공고")
    s = scoring.compute_score(item, grp)
    assert s["breakdown"]["region_match"] == 0
    assert s["breakdown"]["region_mismatch"] == 1
    assert s["score"] < 50


def test_p1_region_mismatch_skips_nationwide():
    """P1: '전국' 언급 공고에는 타지역 패널티를 적용하지 않는다."""
    grp = _group(required_conditions={"regions": ["인천"]})
    s = scoring.compute_score(_item("전국 부산 등 화장품 수출 지원"), grp)
    assert s["breakdown"]["region_mismatch"] == 0


def test_p2_ascii_keyword_word_boundary_no_false_positive():
    """P2: ASCII 키워드는 단어경계 매칭 — 'email' 안의 'ai' 에 매칭되면 안 된다."""
    grp = _group(
        or_keywords=["AI", "SaaS"],
        priority_keywords=[],
        required_conditions={"regions": ["서울"]},
    )
    s_neg = scoring.compute_score(_item("email 발송 시스템 안내"), grp)
    assert s_neg["breakdown"]["or_hits"] == 0

    s_pos = scoring.compute_score(_item("AI 기반 SaaS 사업화 지원"), grp)
    assert s_pos["breakdown"]["or_hits"] == 2


def test_p2_korean_keyword_substring_still_matches_compound():
    """P2: 한글 키워드는 합성어 내부 substring 매칭 유지 (recall 보존)."""
    grp = _group(or_keywords=["화장품"], priority_keywords=[], required_conditions={})
    s = scoring.compute_score(_item("화장품산업 활성화 공고"), grp)
    assert s["breakdown"]["or_hits"] == 1
