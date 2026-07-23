import datetime as dt
import os

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "test@example.invalid")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

import monitor


TODAY = dt.date(2026, 7, 23)

GROUP = {
    "id": "p1_context",
    "name": "서울 AI",
    "applicant_region_city": "서울특별시",
    "applicant_region_label": "서울",
    "or_keywords": ["AI"],
    "and_keyword_groups": [],
    "exclude_keywords": ["교육 일정", "공급기업", "유의사항"],
    "support_types": ["지원금/바우처", "그외"],
    "required_conditions": {"regions": ["서울"]},
}


def _item(title: str, description: str) -> dict:
    return {
        "title": title,
        "description": description,
        "support_field": "사업화",
        "application_period": {"start": "2026-07-01", "end": "2026-08-31"},
    }


def test_body_only_education_schedule_does_not_drop_application():
    item = _item(
        "2026 AI 사업화 지원 참여기업 모집",
        "서울 소재 기업 신청 접수. 선정기업 교육 일정은 별도 안내합니다.",
    )

    result = monitor.evaluate_notice(item, GROUP, today=TODAY)

    assert result["is_relevant"] is True
    assert "EDUCATION_ONLY" not in result["exclude_reason_codes"]
    assert "NOT_GRANT_NOTICE" not in result["exclude_reason_codes"]
    assert "교육 일정" in result["soft_excluded_keywords"]
    assert result["filter_confidence"] == "medium"


def test_body_only_guideline_note_does_not_drop_application():
    item = _item(
        "2026 AI 사업화 지원 참여기업 모집",
        "서울 소재 기업 신청 접수. 제출 유의사항은 첨부문서를 확인하세요.",
    )

    result = monitor.evaluate_notice(item, GROUP, today=TODAY)

    assert result["is_relevant"] is True
    assert "GUIDELINE_OR_MANUAL" not in result["exclude_reason_codes"]
    assert "유의사항" in result["soft_excluded_keywords"]


def test_title_education_schedule_remains_hard_excluded():
    item = _item(
        "2026 AI 지원사업 선정기업 교육 일정 안내",
        "서울 소재 선정기업 대상 안내입니다.",
    )

    result = monitor.evaluate_notice(item, GROUP, today=TODAY)

    assert result["is_relevant"] is False
    assert "EDUCATION_ONLY" in result["exclude_reason_codes"]


def test_recruitment_result_title_does_not_soften_body_exclusion():
    item = _item(
        "2026 AI 참여기업 모집 결과 안내",
        "서울 소재 선정기업 대상 교육 일정입니다.",
    )

    result = monitor.evaluate_notice(item, GROUP, today=TODAY)

    assert result["is_relevant"] is False
    assert "EDUCATION_ONLY" in result["exclude_reason_codes"]
    assert result["soft_excluded_keywords"] == []


def test_mixed_demand_and_supplier_recruitment_is_not_supplier_only():
    item = _item(
        "2026 서울 AI 수요기업 및 공급기업 공동 모집",
        "수요기업과 공급기업이 함께 신청 접수할 수 있습니다.",
    )

    result = monitor.evaluate_notice(item, GROUP, today=TODAY)

    assert result["is_relevant"] is True
    assert result["target_type"] == "mixed"
    assert "SUPPLIER_ONLY" not in result["exclude_reason_codes"]
    assert "공급기업" in result["soft_excluded_keywords"]


def test_supplier_only_title_remains_hard_excluded():
    item = _item(
        "2026 서울 AI 공급기업 추가모집 안내",
        "서비스 제공자 신청 접수",
    )

    result = monitor.evaluate_notice(item, GROUP, today=TODAY)

    assert result["is_relevant"] is False
    assert "SUPPLIER_ONLY" in result["exclude_reason_codes"]
