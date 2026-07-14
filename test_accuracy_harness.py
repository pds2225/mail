"""정확도 하네스(측정 백본) 자체 회귀 가드 — 빠른 스모크.

accuracy_matrix.build 가 실데이터 일부(cap)로 크래시 없이 돌고, KPI/산출물 스키마가
계약대로 나오는지, region_FP 카운트가 region_fp_hits 와 정합하는지 확인한다.
단독 foreground 실행 권장: python -m pytest test_accuracy_harness.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
for p in (BASE_DIR, BASE_DIR / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import accuracy_matrix  # noqa: E402


def _build_small():
    return accuracy_matrix.build(date=None, cap=150)


def test_build_runs_and_has_sections():
    res = _build_small()
    if res.get("error"):  # raw store 없는 환경이면 스킵(측정 불가)
        import pytest
        pytest.skip(res["error"])
    for key in ("summary", "matrix", "fp", "fn", "contradictions", "region_fp_hits"):
        assert key in res, f"산출 누락: {key}"


def test_kpi_schema_and_region_fp_consistency():
    res = _build_small()
    if res.get("error"):
        import pytest
        pytest.skip(res["error"])
    kpi = res["summary"]["kpi"]
    for key in ("region_FP", "region_recall_at_labeled", "region_recall_denom", "region_recall_fn"):
        assert key in kpi, f"KPI 키 누락: {key}"
    assert isinstance(kpi["region_FP"], int)
    # region_FP 는 region_fp_hits 길이와 정확히 일치해야 한다(집계 정합성)
    assert kpi["region_FP"] == len(res["region_fp_hits"])


def test_matrix_notice_shape():
    res = _build_small()
    if res.get("error"):
        import pytest
        pytest.skip(res["error"])
    notices = res["matrix"]["notices"]
    assert isinstance(notices, list) and notices
    n = notices[0]
    for key in ("id", "title", "region_field", "companies", "groups"):
        assert key in n, f"notice 필드 누락: {key}"
    assert isinstance(n["companies"], dict)
    assert isinstance(n["groups"], dict)


def test_candidate_codes_are_known():
    """FP/FN 후보 코드가 계약된 집합에 속하는지(오타·스키마 drift 방지)."""
    res = _build_small()
    if res.get("error"):
        import pytest
        pytest.skip(res["error"])
    fp_ok = {"fp_weaklabel_otherregion", "fp_region_leak", "fp_exclude_leak"}
    fn_ok = {"fn_weaklabel_own", "fn_nationwide_blocked", "fn_titletag_own"}
    assert set(res["fp"]["counts"]).issubset(fp_ok), res["fp"]["counts"]
    assert set(res["fn"]["counts"]).issubset(fn_ok), res["fn"]["counts"]
