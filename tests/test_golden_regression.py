"""MAIL-P0D-05(TASK-030) — Golden Set 회귀 Harness 테스트.

핵심소스(기업마당·K-Startup) 판정 변경이 적합공고 누락(recall 저하)을 늘리는지
매 pytest 실행마다 자동 측정한다. 골든셋은 tests/fixtures/golden_regression_set.json
(비식별·가상 데이터, 실제 고객정보 아님).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

import golden_regression_check as g  # noqa: E402
from mail_core.matching.core_sources import CORE_SOURCE_IDS  # noqa: E402


def test_fixture_loads_and_has_both_core_and_obvious_items():
    fixture = g.load_golden_set()
    assert fixture["items"], "골든셋이 비어있으면 재현율 계산 자체가 무의미하다"
    assert any(it.get("core_source") for it in fixture["items"])
    assert any(it.get("obvious") for it in fixture["items"])


def test_fixture_core_source_items_actually_use_core_source_ids():
    """fixture의 core_source=true 항목은 실제로 mail_core.matching.core_sources의
    CORE_SOURCE_IDS(기업마당·K-Startup)에 속하는 source여야 한다(라벨 정합성)."""
    fixture = g.load_golden_set()
    for it in fixture["items"]:
        if it.get("core_source"):
            assert it["source"] in CORE_SOURCE_IDS, (
                f"{it['id']}: core_source=true인데 source={it['source']!r}는 "
                f"CORE_SOURCE_IDS={sorted(CORE_SOURCE_IDS)}에 없음"
            )


def test_golden_set_regression_gate():
    """MAIL-P0D-05 핵심 게이트 — 임계치 미달 시 이 테스트가 실패해야 한다."""
    summary = g.run_check()
    core = summary["core_source"]
    obvious = summary["obvious"]

    assert core["total"] > 0, "핵심소스 표본이 0건이면 재현율 게이트가 무의미하다"
    assert obvious["total"] > 0, "명백 적합공고 표본이 0건이면 재현율 게이트가 무의미하다"

    assert core["recall"] >= g.CORE_SOURCE_RECALL_THRESHOLD, (
        f"핵심소스 재현율 {core['recall']:.2%} < 기준 {g.CORE_SOURCE_RECALL_THRESHOLD:.0%} "
        f"— 누락: {core['missed_ids']}"
    )
    assert obvious["recall"] >= g.OBVIOUS_RECALL_THRESHOLD, (
        f"명백 적합공고 재현율 {obvious['recall']:.2%} < 기준 {g.OBVIOUS_RECALL_THRESHOLD:.0%} "
        f"— 누락: {obvious['missed_ids']}"
    )


# ── 하네스 자체가 실제로 임계치 미달을 잡아내는지(가짜 fixture로 검증) ────────

def test_harness_fails_when_a_core_item_becomes_irrelevant():
    """골든셋 자체를 손대지 않고, 로드된 fixture의 in-memory 사본 하나만 깨서
    compute_recall_summary가 정말로 FAIL을 내는지 확인한다(하네스 자기검증)."""
    fixture = g.load_golden_set()
    core_item = next(it for it in fixture["items"] if it.get("core_source"))
    core_item["title"] = "전혀 관련없는 행정 안내문"
    core_item["description"] = "단순 공지사항입니다."

    results = g.evaluate_golden_set(fixture)
    summary = g.compute_recall_summary(results)

    assert summary["core_source"]["pass"] is False
    assert core_item["id"] in summary["core_source"]["missed_ids"]


def test_recall_helper_handles_empty_rows():
    hit, total, recall = g._recall([])
    assert (hit, total, recall) == (0, 0, 1.0)


def test_format_summary_reports_missed_ids_on_failure():
    fixture = g.load_golden_set()
    obvious_item = next(it for it in fixture["items"] if it.get("obvious"))
    obvious_item["title"] = "전혀 관련없는 행정 안내문"
    obvious_item["description"] = "단순 공지사항입니다."

    results = g.evaluate_golden_set(fixture)
    summary = g.compute_recall_summary(results)
    text = g.format_summary(summary)
    assert obvious_item["id"] in text


def test_cli_exits_zero_when_thresholds_met():
    assert g.main([]) == 0


def test_no_real_customer_data_markers_in_fixture():
    """FORBIDDEN: 실제 고객정보 금지 — 골든셋에 실제 수신자 이메일·전화번호 패턴이
    없어야 한다(비식별·가상 데이터라는 설계 원칙의 최소 안전망)."""
    fixture = g.load_golden_set()
    dumped = str(fixture)
    assert "@gmail.com" not in dumped
    assert "@naver.com" not in dumped
