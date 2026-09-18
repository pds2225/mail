"""MAIL-P0D-03(TASK-028) — rule_version·config_snapshot_id 재현성 회귀테스트."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

from monitor import KST, evaluate_notice  # noqa: E402
from mail_core.operations import rule_version as rv  # noqa: E402

TODAY = datetime(2026, 5, 27, tzinfo=KST).date()

GROUP_A = {
    "id": "gA", "name": "테스트그룹A", "active": True,
    "recipients": ["someone@example.com"],
    "required_conditions": {"regions": ["인천"]},
    "or_keywords": ["모집", "지원", "제조", "신청접수"],
    "and_keyword_groups": [],
    "exclude_keywords": ["금지단어"],
}

GROUP_B = {
    "id": "gB", "name": "테스트그룹B", "active": True,
    "recipients": ["other@example.com"],
    "required_conditions": {"regions": ["부산"]},
    "or_keywords": ["전혀다른키워드셋"],
    "and_keyword_groups": [],
    "exclude_keywords": [],
}


def item(title, description="", **extra):
    value = {
        "id": "x1", "title": title, "link": "https://example.com/x1",
        "author": "테스트기관", "description": description,
        "deadline": "2099.6.1 ~ 2099.6.30", "source": "테스트",
        "posted_date": "2026-05-20", "is_aggregator": False,
    }
    value.update(extra)
    return value


# ── 평가결과 rule_version 100% ────────────────────────────────────────────

def test_result_always_has_rule_version_and_config_snapshot_id():
    it = item("제조업 스마트공장 지원사업 모집 공고")
    result = evaluate_notice(it, GROUP_A, today=TODAY)
    assert result["rule_version"]
    assert result["config_snapshot_id"]
    assert isinstance(result["rule_version"], str)
    assert isinstance(result["config_snapshot_id"], str)


def test_rule_version_and_config_snapshot_id_present_regardless_of_verdict():
    """제외 판정이 나는 공고도 예외 없이 rule_version이 채워져야 한다(100%)."""
    it = item("전혀 관련없는 행정 안내문")
    result = evaluate_notice(it, GROUP_A, today=TODAY)
    assert result["rule_version"]
    assert result["config_snapshot_id"]


# ── 동일 fixture+동일 version → 결과 재현 ──────────────────────────────────

def test_same_fixture_and_group_reproduces_identical_result():
    it = item("제조업 스마트공장 지원사업 모집 공고")
    r1 = evaluate_notice(it, GROUP_A, today=TODAY)
    r2 = evaluate_notice(it, GROUP_A, today=TODAY)
    assert r1["rule_version"] == r2["rule_version"]
    assert r1["config_snapshot_id"] == r2["config_snapshot_id"]
    assert r1["is_relevant"] == r2["is_relevant"]
    assert r1["exclude_reason_codes"] == r2["exclude_reason_codes"]


def test_rule_version_stable_across_process_wide_reevaluations():
    """모듈 import 시 1회 계산된 캐시값이므로, 여러 번 호출해도 항상 같은 값이어야 한다."""
    it1 = item("교육생 모집 공고")
    it2 = item("R&D 기술개발 지원사업 공고", id="x2")
    r1 = evaluate_notice(it1, GROUP_A, today=TODAY)
    r2 = evaluate_notice(it2, GROUP_B, today=TODAY)
    assert r1["rule_version"] == r2["rule_version"]


# ── config_snapshot_id는 그룹 설정이 다르면 달라진다 ────────────────────────

def test_different_group_config_yields_different_snapshot_id():
    it = item("제조업 스마트공장 지원사업 모집 공고")
    r_a = evaluate_notice(it, GROUP_A, today=TODAY)
    r_b = evaluate_notice(it, GROUP_B, today=TODAY)
    assert r_a["config_snapshot_id"] != r_b["config_snapshot_id"]


def test_recipients_do_not_affect_config_snapshot_id():
    """수신자(recipients)는 판정과 무관한 개인정보 — 바뀌어도 스냅샷 id는 그대로여야 한다."""
    group_same_rules_diff_recipients = {**GROUP_A, "recipients": ["another@example.com"]}
    it = item("제조업 스마트공장 지원사업 모집 공고")
    r1 = evaluate_notice(it, GROUP_A, today=TODAY)
    r2 = evaluate_notice(it, group_same_rules_diff_recipients, today=TODAY)
    assert r1["config_snapshot_id"] == r2["config_snapshot_id"]


# ── 민감설정 저장 0건 ───────────────────────────────────────────────────────

def test_config_snapshot_id_never_leaks_raw_recipients_or_group_dict():
    """config_snapshot_id 자체가 짧은 해시 문자열이지, 원본 그룹 dict나 수신자 이메일을
    그대로 담지 않는다(FORBIDDEN: 전체 설정파일 복제 / 개인정보 스냅샷)."""
    snap = rv.config_snapshot_id(GROUP_A)
    assert isinstance(snap, str)
    assert len(snap) == 16
    assert "example.com" not in snap
    assert "@" not in snap


def test_config_snapshot_id_is_deterministic_pure_function():
    assert rv.config_snapshot_id(GROUP_A) == rv.config_snapshot_id(dict(GROUP_A))
    assert rv.config_snapshot_id(None) == rv.config_snapshot_id({})


# ── compute_version_hash ────────────────────────────────────────────────────

def test_compute_version_hash_deterministic_and_sensitive_to_input():
    h1 = rv.compute_version_hash("a", "b")
    h2 = rv.compute_version_hash("a", "b")
    h3 = rv.compute_version_hash("a", "c")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16


# ── 변경 전후 비교 helper ───────────────────────────────────────────────────

def test_diff_versions_flags_nondeterminism_when_result_changes_but_version_same():
    before = {"rule_version": "v1", "config_snapshot_id": "c1", "is_relevant": True,
              "exclude_reason_codes": []}
    after = {"rule_version": "v1", "config_snapshot_id": "c1", "is_relevant": False,
             "exclude_reason_codes": ["CLOSED_DEADLINE"]}
    diff = rv.diff_versions(before, after)
    assert diff["same_rule_and_config"] is True
    assert diff["nondeterministic"] is True
    assert "is_relevant" in diff["changed_fields"]


def test_diff_versions_does_not_flag_expected_change_when_rule_version_differs():
    before = {"rule_version": "v1", "config_snapshot_id": "c1", "is_relevant": True,
              "exclude_reason_codes": []}
    after = {"rule_version": "v2", "config_snapshot_id": "c1", "is_relevant": False,
             "exclude_reason_codes": ["CLOSED_DEADLINE"]}
    diff = rv.diff_versions(before, after)
    assert diff["same_rule_and_config"] is False
    assert diff["nondeterministic"] is False
    assert "is_relevant" in diff["changed_fields"]


def test_diff_versions_no_changed_fields_when_results_identical():
    same = {"rule_version": "v1", "config_snapshot_id": "c1", "is_relevant": True,
            "exclude_reason_codes": ["A"], "notice_type": "grant", "target_type": "company"}
    diff = rv.diff_versions(same, dict(same))
    assert diff["changed_fields"] == {}
    assert diff["nondeterministic"] is False
