"""기업마당·K-Startup → 서울 AI 예비창업자 추천 경로 회귀 테스트.

수집기 자체의 HTML/JSON 재생 테스트와 별도로, 핵심 소스가 붙이는 구조화
필드가 실제 ``grp_prestartup_ai`` 판정까지 이어지는지 고정한다.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@example.invalid",
    "GMAIL_APP_PASSWORD": "test_pass",
    "MONITOR_NO_PERSIST_SEEN": "1",
}.items():
    os.environ.setdefault(_key, _value)

import monitor  # noqa: E402
from mail_core.matching import core_sources  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
GROUP = next(
    group
    for group in json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))
    if group["id"] == "grp_prestartup_ai"
)
TODAY = date(2026, 7, 28)


def _base(**overrides) -> dict:
    item = {
        "id": "priority-case",
        "title": "2026년 예비창업자 사업화 지원사업 모집",
        "description": "신청 접수 중",
        "author": "공공기관",
        "source": "핵심소스 회귀",
        "link": "https://example.go.kr/notice/priority",
        "posted_date": "2026-07-28",
        "deadline": "2026-08-31",
        "application_period": {
            "start": "2026-07-28",
            "end": "2026-08-31",
            "display": "2026-07-28 ~ 2026-08-31",
        },
        "is_aggregator": False,
    }
    item.update(overrides)
    return item


def _bucket(item: dict) -> tuple[str, dict]:
    diagnostics = monitor.filter_for_group_with_diagnostics([item], GROUP, TODAY)
    for name in ("included", "region_unknown", "review", "excluded"):
        if diagnostics[name]:
            return name, diagnostics[name][0]
    raise AssertionError("공고가 어떤 진단 버킷에도 들어가지 않음")


def test_bizinfo_structured_fields_reach_seoul_ai_prestartup_group():
    item = core_sources.attach_bizinfo_structured(
        _base(
            id="PBLN_PRIORITY",
            title="2026년 예비창업자 사업화 지원사업 모집",
            description="신청 접수 중",
            source="기업마당(Bizinfo)",
            link="https://www.bizinfo.go.kr/notice/priority",
            is_aggregator=True,
        ),
        {
            "pldirSportRealmLclasCodeNm": "인공지능·데이터 사업화",
            "trgetNm": "서울 거주 예비창업자 및 창업예정자",
            "jrsdAreaNm": "서울특별시",
        },
    )

    bucket, evaluated = _bucket(item)

    assert item["core_source"] == "bizinfo"
    assert bucket == "included", evaluated
    assert evaluated["is_relevant"] is True
    assert evaluated["group_keyword_pass"] is True
    assert evaluated["region_status"] == "eligible"


@pytest.mark.parametrize("clss", ["PBC010", "PBC020"])
def test_kstartup_public_and_private_ai_prestartup_paths_are_included(clss: str):
    item = core_sources.attach_kstartup_list_structured(
        _base(
            id=f"kstartup_priority_{clss}",
            title="2026년 AI 분야 창업예정자 사업화 프로그램 모집",
            description="전국 예비창업자를 대상으로 신청 접수",
            source="K-Startup",
            link=(
                "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
                f"?pbancClssCd={clss}&pbancSn=9999"
            ),
            region_field="전국",
        ),
        flag_text="사업화 지원",
        clss=clss,
    )

    bucket, evaluated = _bucket(item)

    assert item["core_source"] == "kstartup"
    assert item["kstartup_class"] == clss
    assert bucket == "included", evaluated
    assert evaluated["is_relevant"] is True
    assert evaluated["group_keyword_pass"] is True
    assert evaluated["region_status"] == "eligible"


def test_other_region_only_notice_does_not_leak_into_seoul_priority_group():
    item = core_sources.attach_kstartup_list_structured(
        _base(
            id="kstartup_busan_only",
            title="부산 AI 예비창업자 사업화 지원 모집",
            description="부산광역시 거주 예비창업자만 신청 가능",
            source="K-Startup",
            link="https://www.k-startup.go.kr/notice/busan-only",
            region_field="부산광역시",
        ),
        flag_text="사업화 지원",
        clss="PBC010",
    )

    bucket, evaluated = _bucket(item)

    assert bucket == "excluded", evaluated
    assert evaluated["region_status"] == "not_eligible"
    assert "REGION_NOT_ELIGIBLE" in evaluated["exclude_reason_codes"]
