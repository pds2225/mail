"""MAIL-015: 과거 사용자 기준이 현재 판정 파이프라인에 살아 있는지 고정한다.

이 파일은 수집·메일·외부 네트워크를 호출하지 않는다. 공고 1건을 evaluator에 넣어
신청자격/마감/지역/제외/관심어 판정과 버전·중복 계약만 확인한다.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@example.invalid",
    "GMAIL_APP_PASSWORD": "test_pass",
    "ALLOW_SEND_EMAIL": "false",
    "ALLOW_DELETE_EMAIL": "false",
    "ALLOW_LABEL_CHANGE": "false",
    "MONITOR_NO_PERSIST_SEEN": "1",
}.items():
    os.environ.setdefault(_key, _value)

import monitor as m  # noqa: E402
from mail_core.matching.scoring import score_and_filter  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 9, 17)
GROUPS = json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))


def _group(group_id: str) -> dict:
    return next(group for group in GROUPS if group["id"] == group_id)


def _item(title: str, description: str, **overrides) -> dict:
    item = {
        "id": title[:32],
        "title": title,
        "description": description,
        "author": "MAIL-015 회귀기관",
        "source": "MAIL-015 회귀",
        "link": "https://example.invalid/notice/1",
        "posted_date": "2026-09-16",
        "deadline": "2026-12-31",
        "application_period": {
            "start": "2026-09-16",
            "end": "2026-12-31",
            "display": "2026-09-16 ~ 2026-12-31",
        },
        "region_field": "전국",
        "is_aggregator": False,
    }
    item.update(overrides)
    return item


def _evaluated(group_id: str, title: str, description: str, **overrides) -> dict:
    return m.evaluate_notice(
        _item(title, description, **overrides), _group(group_id), TODAY,
    )


def test_prestartup_target_is_included():
    ev = _evaluated(
        "grp_prestartup_ai",
        "AI 사업화 지원사업 예비창업자 모집",
        "전국 예비창업자와 창업예정자 대상 사업화지원금 신청접수.",
    )
    assert ev["is_relevant"] is True


def test_established_business_only_is_rejected_by_precision_stage():
    item = _item(
        "AI 솔루션 도입 참여기업 모집",
        "기창업기업만 신청 가능하며 사업자등록 기업의 AI 솔루션 도입 비용을 지원합니다.",
    )
    audit = score_and_filter([item], _group("grp_prestartup_ai"))
    assert audit["rejected"]
    assert audit["audit"][0]["decision"] == "rejected_by_score"


def test_nationwide_notice_passes_region_gate():
    ev = _evaluated(
        "grp_prestartup_ai",
        "전국 AI 창업지원사업 참여자 모집",
        "전국 예비창업자 대상 사업화자금 지원.",
    )
    assert ev["region_status"] == "eligible"
    assert ev["is_relevant"] is True


def test_incheon_whole_is_possible_for_incheon_group():
    ev = _evaluated(
        "grp_bnco",
        "인천 전체 소상공인 지원금 신청접수",
        "인천광역시 소재 소상공인 대상 지원사업 모집.",
        region_field="인천광역시",
    )
    assert ev["region_status"] == "eligible"
    assert ev["is_relevant"] is True


def test_incheon_specific_other_district_is_rejected():
    ev = _evaluated(
        "grp_bnco",
        "인천 서구 소재 기업만 지원사업 모집",
        "인천 서구 소재 기업만 신청 가능한 지원금 사업.",
        region_field="인천광역시",
    )
    assert ev["is_relevant"] is False
    assert "DISTRICT_NOT_ELIGIBLE" in ev["exclude_reason_codes"]


def test_factory_required_notice_is_kept_with_condition():
    ev = _evaluated(
        "grp_bnco",
        "인천 남동구 공장 보유 기업 지원사업 참여기업 모집",
        "인천 남동구 소재 공장등록증 보유 제조기업 대상 지원금 신청접수.",
        region_field="인천광역시",
    )
    assert ev["factory_required"] is True
    assert "공장보유 또는 제조시설 조건" in ev["required_conditions"]
    assert ev["is_relevant"] is True


def test_innovation_voucher_is_priority():
    ev = _evaluated(
        "grp_bnco",
        "혁신바우처 수요기업 모집",
        "인천 소재 제조기업 대상 혁신바우처 지원금 신청접수.",
        region_field="인천광역시",
    )
    assert "혁신바우처" in ev["priority_keywords"]


def test_export_voucher_is_priority():
    ev = _evaluated(
        "grp_bnco",
        "수출바우처 참여기업 모집",
        "인천 소재 기업의 해외진출을 위한 수출바우처 신청접수.",
        region_field="인천광역시",
    )
    assert "수출바우처" in ev["priority_keywords"]


def test_overseas_interest_terms_are_matched():
    group = _group("grp_bnco")
    for term in ("베트남", "동남아", "해외", "글로벌"):
        ev = m.evaluate_notice(
            _item(
                f"{term} 진출 지원사업 신청접수",
                f"인천 소재 기업 대상 {term} 판로지원.",
                region_field="인천광역시",
            ),
            group,
            TODAY,
        )
        assert term in ev["matched_keywords"], (term, ev)


def test_exhibition_interest_terms_are_matched():
    group = _group("grp_bnco")
    for term in ("박람회", "전시회"):
        ev = m.evaluate_notice(
            _item(
                f"{term} 참가기업 모집",
                f"인천 소재 기업 대상 {term} 참가비 지원.",
                region_field="인천광역시",
            ),
            group,
            TODAY,
        )
        assert term in ev["matched_keywords"], (term, ev)


def test_info_session_only_is_rejected():
    ev = _evaluated(
        "grp_bnco",
        "해외진출 지원 설명회 안내",
        "인천 소재 기업 대상 설명회만 진행합니다.",
        region_field="인천광역시",
    )
    assert ev["is_relevant"] is False
    assert "INFO_SESSION" in ev["exclude_reason_codes"] or "GROUP_EXCLUSION" in ev["exclude_reason_codes"]


def test_mentoring_only_is_rejected_but_not_body_keyword_rule():
    ev = _evaluated(
        "grp_prestartup_ai",
        "예비창업자 1대1 멘토링 모집",
        "전국 예비창업자 대상 전문가 멘토링만 제공합니다.",
    )
    assert ev["is_relevant"] is False
    assert "CONSULTING_ONLY" in ev["exclude_reason_codes"]


def test_consulting_support_only_is_rejected():
    ev = _evaluated(
        "grp_prestartup_ai",
        "AI 창업 컨설팅지원 모집",
        "전국 예비창업자 대상 컨설팅지원만 제공합니다.",
    )
    assert ev["is_relevant"] is False
    assert "CONSULTING_ONLY" in ev["exclude_reason_codes"]


def test_closed_notice_is_rejected():
    ev = _evaluated(
        "grp_prestartup_ai",
        "AI 사업화 지원사업 예비창업자 모집",
        "전국 예비창업자 대상 사업화자금 지원.",
        deadline="2026-08-31",
        application_period={
            "start": "2026-07-01",
            "end": "2026-08-31",
            "display": "2026-07-01 ~ 2026-08-31",
        },
    )
    assert ev["is_relevant"] is False
    assert "CLOSED_DEADLINE" in ev["exclude_reason_codes"]


def test_result_announcement_is_rejected():
    ev = _evaluated(
        "grp_prestartup_ai",
        "AI 사업화 지원사업 결과발표",
        "전국 예비창업자 모집 결과를 발표합니다.",
    )
    assert ev["is_relevant"] is False
    assert "REPORT_JUNK" in ev["exclude_reason_codes"]


def test_selected_company_only_is_rejected():
    ev = _evaluated(
        "grp_prestartup_ai",
        "AI 사업화 지원사업 선정기업 대상 협약 안내",
        "기선정된 예비창업자 및 선정기업만 협약을 진행합니다.",
    )
    assert ev["is_relevant"] is False
    assert "SELECTED_COMPANY_ONLY" in ev["exclude_reason_codes"]


def test_extended_notice_is_reclassified_as_open_version():
    before = _item(
        "AI 사업화 지원사업 모집",
        "전국 예비창업자 대상 사업화자금 지원.",
        id="extended-notice",
        deadline="2026-09-30",
        application_period={
            "start": "2026-09-01",
            "end": "2026-09-30",
            "display": "2026-09-01 ~ 2026-09-30",
        },
    )
    item = _item(
        "AI 사업화 지원사업 연장공고",
        "전국 예비창업자 대상 사업화자금 지원. 접수기간 연장.",
        id="extended-notice",
        deadline="2027-01-31",
        application_period={
            "start": "2026-09-01",
            "end": "2027-01-31",
            "display": "2026-09-01 ~ 2027-01-31 (연장공고)",
        },
    )
    assert m.classify_deadline_status(item, TODAY) == "extended"
    snap = m._notice_version_snapshot(before)
    versions = {
        item["id"]: {
            "version": 1,
            "list_hash": m._notice_list_hash(before),
            "delivered_hash": m._notice_snapshot_hash(snap),
            "delivered_snapshot": snap,
            "observed_hash": m._notice_snapshot_hash(snap),
        }
    }
    deliverable, _updates = m.classify_notice_versions([item], {item["id"]}, versions)
    assert deliverable[0]["_change_type"] == "DEADLINE_EXTENDED"


def test_same_notice_is_deduplicated():
    first = _item("AI 사업화 지원사업 모집", "전국 예비창업자 대상", id="same-notice")
    second = {**first, "description": "전국 예비창업자 대상 사업화자금 지원"}
    deduped = m.dedup_items([first, second])
    assert len(deduped) == 1


def test_tenant_only_boundary_keeps_ai_hub_and_does_not_infer_factory():
    """과거 P0-4의 입주공간 단독 의도를 고정하되 AI 허브 정당 공고는 보존한다."""
    generic = _evaluated(
        "grp_prestartup_ai",
        "창업보육센터 입주기업 모집",
        "입주 공간 제공과 사무실 이용만 가능합니다.",
    )
    assert generic["is_relevant"] is False

    ai_hub = _evaluated(
        "grp_prestartup_ai",
        "2026년 서울 AI 허브 신규 입주기업 모집 안내",
        "서울 AI 기업에 사무공간과 성장 지원을 제공하며 신청을 받습니다.",
        region_field="서울특별시",
    )
    assert ai_hub["factory_required"] is False
    assert ai_hub["is_relevant"] is True
