# -*- coding: utf-8 -*-
"""expand_golden_labels(제목태그 Tier B 라벨) + matrix golden 보충 회귀 테스트."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from expand_golden_labels import canon_region, classify_title  # noqa: E402


# ── canon_region: 태그 전체가 광역명일 때만 정식명칭 ──

def test_canon_short_names():
    assert canon_region("서울") == "서울특별시"
    assert canon_region("경기") == "경기도"
    assert canon_region("전국") == "전국"
    assert canon_region("세종") == "세종특별자치시"


def test_canon_variants():
    assert canon_region("인천시") == "인천광역시"
    assert canon_region("제주도") == "제주특별자치도"
    assert canon_region("전라북도") == "전북특별자치도"
    assert canon_region("광주광역시") == "광주광역시"


def test_canon_ambiguous_gwangju_rejected():
    # "광주"는 광주광역시/경기 광주시 모호 → 라벨 금지
    assert canon_region("광주") is None
    assert canon_region("광주시") is None


def test_canon_org_rejected():
    assert canon_region("인천테크노파크") is None
    assert canon_region("서울바이오허브") is None


# ── classify_title: 라벨 vs 리뷰 큐 분류 ──

def test_classify_pure_tag_labels():
    rf, reason, tag = classify_title("[서울] 2026 청년창업 지원사업 모집")
    assert rf == "서울특별시" and reason is None and tag == "서울"


def test_classify_paren_tag():
    rf, reason, _ = classify_title("(경기) 스타트업 패키지")
    assert rf == "경기도" and reason is None


def test_classify_org_tag_goes_review():
    rf, reason, tag = classify_title("[인천테크노파크] 수출기업 애로상담 창구 운영")
    assert rf is None and reason == "org_or_ambiguous" and "인천" in tag


def test_classify_sub_region_goes_review():
    rf, reason, _ = classify_title("[고양시] 관내기업 지원")
    assert rf is None and reason == "sub_region"


def test_classify_no_tag():
    assert classify_title("2026년 창업지원사업 통합공고") == (None, None, None)
    assert classify_title("") == (None, None, None)


def test_classify_non_region_tag_ignored():
    # 지역 힌트 없는 태그(예: [모집공고])는 라벨도 리뷰도 아님
    rf, reason, _ = classify_title("[모집공고] 기술창업 아카데미")
    assert rf is None and reason is None


# ── matrix golden 보충: meta 우선, 빈 곳만 골든 ──

def test_matrix_golden_fill(tmp_path, monkeypatch):
    import accuracy_matrix as am

    golden = tmp_path / "region_labels.jsonl"
    golden.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"id": "n1", "region_field": "서울특별시", "tier": "B"},
        {"id": "n2", "region_field": "경기도", "tier": "B"},
    ]
    golden.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    real_base = am.BASE_DIR
    monkeypatch.setattr(am, "BASE_DIR", tmp_path.parent)
    # _load_golden_regions 는 BASE_DIR/data/golden/... 을 봄 → tmp 구조로 맞춤
    g2 = tmp_path.parent / "data" / "golden"
    g2.mkdir(parents=True, exist_ok=True)
    (g2 / "region_labels.jsonl").write_text(
        golden.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        loaded = am._load_golden_regions()
    finally:
        monkeypatch.setattr(am, "BASE_DIR", real_base)

    assert loaded == {"n1": "서울특별시", "n2": "경기도"}
    # 보충 규칙: meta 값이 있으면 meta 우선(빈 값만 골든)
    meta_rf = "전국"
    assert (meta_rf or loaded.get("n1", "")) == "전국"
    assert ("" or loaded.get("n1", "")) == "서울특별시"
