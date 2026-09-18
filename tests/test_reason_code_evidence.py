"""MAIL-P0D-02(TASK-027) — reason_code taxonomy·evidence 표준화 회귀테스트."""
from __future__ import annotations

import os
import re
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
from mail_core.operations import reason_code_taxonomy as taxo  # noqa: E402

TODAY = datetime(2026, 5, 27, tzinfo=KST).date()

GROUP = {
    "id": "g", "name": "테스트그룹", "active": True,
    "required_conditions": {"regions": ["인천"]},
    "or_keywords": ["모집", "지원", "제조", "신청접수"],
    "and_keyword_groups": [],
    "exclude_keywords": ["금지단어"],
    "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
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


# ── taxonomy 완전성(자동판정 reason_code 100%) — 소스 정적 스캔 ────────────

def test_all_add_reason_literal_codes_are_in_taxonomy():
    """evaluate_notice()가 _add_reason("CODE"...) 로 방출하는 모든 리터럴 코드가
    taxonomy에 등록돼 있어야 한다(자동판정 reason_code 100%)."""
    source = (ROOT / "monitor.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'_add_reason\("([A-Z_]+)"', source))
    assert codes, "정적 스캔이 코드를 하나도 못 찾으면 테스트 자체가 무의미하다"
    missing = taxo.missing_from_taxonomy(codes)
    assert missing == set(), f"taxonomy 미등록 코드: {sorted(missing)}"


def test_exclusion_rules_table_codes_are_in_taxonomy():
    """EXCLUSION_RULES 테이블(동적으로 code 변수를 통해 _add_reason에 전달됨)의
    코드도 taxonomy에 등록돼 있어야 한다."""
    source = (ROOT / "monitor.py").read_text(encoding="utf-8")
    m = re.search(r"^EXCLUSION_RULES = \[(.*?)^\]", source, re.M | re.S)
    codes = set(re.findall(r'\(\s*"([A-Z_]+)"', m.group(1)))
    assert codes
    missing = taxo.missing_from_taxonomy(codes)
    assert missing == set(), f"EXCLUSION_RULES taxonomy 미등록 코드: {sorted(missing)}"


def test_conditional_region_codes_are_in_taxonomy():
    """REGION_NOT_ELIGIBLE/REGION_UNKNOWN 처럼 f-string이 아닌 조건부 분기로
    방출되는 코드도 등록돼 있어야 한다(정적 정규식으로는 못 잡으므로 명시 확인)."""
    assert {"REGION_NOT_ELIGIBLE", "REGION_UNKNOWN"} <= taxo.known_reason_codes()


def test_missing_from_taxonomy_detects_unregistered_code():
    assert taxo.missing_from_taxonomy({"TOTALLY_MADE_UP_CODE"}) == {"TOTALLY_MADE_UP_CODE"}
    assert taxo.missing_from_taxonomy({"CLOSED_DEADLINE"}) == set()


def test_describe_returns_empty_for_unknown_code():
    assert taxo.describe("NOT_A_REAL_CODE") == ""
    assert taxo.describe("CLOSED_DEADLINE") != ""


# ── evaluate_notice() 가 실제로 reason_evidence 를 채우는지 ─────────────────

def test_result_always_has_reason_evidence_key():
    result = evaluate_notice(item("전국 중소기업 제조 지원사업 모집 신청접수"), GROUP, TODAY)
    assert "reason_evidence" in result
    assert isinstance(result["reason_evidence"], dict)


def test_closed_deadline_has_evidence():
    result = evaluate_notice(item("제조기업 지원사업 모집", deadline="2020.1.1 ~ 2020.1.31"), GROUP, TODAY)
    assert "CLOSED_DEADLINE" in result["exclude_reason_codes"]
    assert result["reason_evidence"].get("CLOSED_DEADLINE")


def test_tenant_only_has_evidence():
    result = evaluate_notice(
        item("입주기업 모집 공고", description="사무공간 입주기업 모집. 지원금 없음."),
        GROUP, TODAY,
    )
    assert "TENANT_ONLY" in result["exclude_reason_codes"]
    assert result["reason_evidence"].get("TENANT_ONLY")


def test_group_exclusion_has_evidence():
    result = evaluate_notice(item("제조기업 금지단어 지원 모집 신청접수"), GROUP, TODAY)
    assert "GROUP_EXCLUSION" in result["exclude_reason_codes"]
    assert "금지단어" in result["reason_evidence"].get("GROUP_EXCLUSION", "")


def test_evidence_never_contains_full_body_or_is_overly_long():
    """근거는 짧은 발췌만 — 원문 전체·Secret 유입 방지."""
    long_desc = "사무공간 입주기업 모집. " + ("장문의 안내문구. " * 50)
    result = evaluate_notice(item("입주기업 모집", description=long_desc), GROUP, TODAY)
    for code, evidence in result["reason_evidence"].items():
        assert len(evidence) <= 160, f"{code} evidence too long: {len(evidence)}"


def test_industry_not_matched_has_no_evidence_but_still_recorded():
    """근거가 없는(매칭 부재를 나타내는) 코드는 evidence 없이 코드만 기록돼도 된다."""
    result = evaluate_notice(item("전혀 관련없는 일반 공고", description="아무 키워드도 없음"), GROUP, TODAY)
    assert "INDUSTRY_NOT_MATCHED" in result["exclude_reason_codes"]
    assert "INDUSTRY_NOT_MATCHED" not in result["reason_evidence"]
