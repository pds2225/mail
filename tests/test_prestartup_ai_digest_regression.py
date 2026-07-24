"""2026-07-24 예비창업 AI 실수신 메일의 오추천 회귀 테스트."""
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


ROOT = Path(__file__).resolve().parent.parent
GROUP = next(
    group
    for group in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))
    if group["id"] == "grp_prestartup_ai"
)
TODAY = date(2026, 7, 23)


def _item(title: str, description: str, **overrides) -> dict:
    item = {
        "id": title[:20],
        "title": title,
        "description": description,
        "author": "공공기관",
        "source": "실수신 회귀",
        "link": "https://example.go.kr/notice/1",
        "posted_date": "2026-07-23",
        "deadline": "2026-08-31",
        "application_period": {
            "start": "2026-07-23",
            "end": "2026-08-31",
            "display": "2026-07-23 ~ 2026-08-31",
        },
        "region_field": "전국",
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


FALSE_RECOMMENDATIONS = [
    pytest.param(
        _item(
            "AI기반 미래자동차 검증 기반구축 기획위원(후보자) 모집공고",
            "지원사업 신청 메뉴가 함께 수집된 기획위원 모집 안내",
        ),
        "기획위원",
        id="planning-committee-recruitment",
    ),
    pytest.param(
        _item(
            "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
            "소상공인 기업 데이터 악용과 입찰보증금 입금 유도 사기 대응방법 안내",
            deadline="2026-12-28",
        ),
        "사기피해 예방",
        id="fraud-prevention-notice",
    ),
    pytest.param(
        _item(
            "인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화 도입",
            "보도자료. 글로벌 음악축제 홍보에 생성형 인공지능 기술을 도입한다.",
            application_period={},
            region_field="인천광역시",
        ),
        "보도자료",
        id="ai-press-release",
    ),
]


@pytest.mark.parametrize(("item", "expected_hit"), FALSE_RECOMMENDATIONS)
def test_non_grant_notices_are_not_recommended(item: dict, expected_hit: str):
    bucket, evaluated = _bucket(item)

    assert bucket in {"review", "excluded"}, evaluated
    assert evaluated["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in evaluated["exclude_reason_codes"]
    assert expected_hit in evaluated["excluded_keywords"]


def test_big_data_academy_without_startup_signal_is_excluded():
    item = _item(
        "2026년 데이터 ON 고양 빅데이터 아카데미 참여자 모집 공고",
        "시민을 대상으로 데이터 교육 참여 신청을 받는다.",
        region_field="경기도",
    )

    bucket, evaluated = _bucket(item)

    assert bucket in {"review", "excluded"}, evaluated
    assert evaluated["is_relevant"] is False
    assert evaluated["group_keyword_pass"] is False


def test_expired_2025_notice_stays_excluded():
    item = _item(
        "인천테크노파크 방산 중소기업 생산성향상 지원사업 수혜 후보기업 모집 공고",
        "인천 방산 중소기업 대상 생산설비 지원",
        posted_date="2025-07-22",
        deadline="2025-08-05",
        application_period={
            "start": "2025-07-22",
            "end": "2025-08-05",
            "display": "2025-07-22 ~ 2025-08-05",
        },
        region_field="인천광역시",
    )

    bucket, evaluated = _bucket(item)

    assert bucket == "excluded"
    assert evaluated["deadline_status"] == "closed"
    assert "CLOSED_DEADLINE" in evaluated["exclude_reason_codes"]


LEGITIMATE_RECOMMENDATIONS = [
    pytest.param(
        _item(
            "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
            "서울 AI 기업에 사무공간과 성장 지원을 제공하며 신청을 받는다. 홈페이지 보도자료 메뉴도 제공한다.",
            region_field="서울특별시",
        ),
        id="seoul-ai-hub",
    ),
    pytest.param(
        _item(
            "제조 AI 기술 사업화 지원 수혜기업 모집",
            "전국 제조 AI 기업의 기술 사업화와 시설·보육을 지원한다.",
        ),
        id="manufacturing-ai-commercialization",
    ),
    pytest.param(
        _item(
            "한국전자전 관악S밸리관 참가기업 모집",
            "관악 소재 AI 스타트업에 전시 부스와 비즈니스 밋업을 지원한다.",
            region_field="서울특별시",
        ),
        id="seoul-kes",
    ),
    pytest.param(
        _item(
            "생성형AI 솔루션 실증기업 모집",
            "생성형AI 서비스의 현장 실증과 사업화를 지원한다.",
        ),
        id="generative-ai-pilot",
    ),
    pytest.param(
        _item(
            "LLM 상용화 지원사업 참여기업 모집",
            "국산 LLM 기술의 사업화와 시장검증을 지원한다.",
        ),
        id="llm-commercialization",
    ),
    pytest.param(
        _item(
            "컴퓨터비전 기술 현장실증 참여기업 모집",
            "컴퓨터비전 솔루션 실증 비용을 지원한다.",
        ),
        id="computer-vision-pilot",
    ),
    pytest.param(
        _item(
            "SaaS 예비창업 보육기업 모집",
            "SaaS 창업팀에 입주공간과 사업화 프로그램을 제공한다.",
        ),
        id="saas-incubation",
    ),
    pytest.param(
        _item(
            "빅데이터 기반 창업기업 육성사업 모집",
            "빅데이터 창업기업에 사업화 자금과 멘토링을 지원한다.",
        ),
        id="bigdata-startup",
    ),
    pytest.param(
        _item(
            "AI 솔루션 도입 참여기업 모집",
            "AI 사업화와 멘토링을 지원하는 참여기업 모집 공고다.",
        ),
        id="ai-solution-mentoring",
    ),
    pytest.param(
        _item(
            "AI 스타트업 투자 매칭데이 참가기업 모집",
            "AI 스타트업과 투자사를 연결하고 후속 상담을 지원한다.",
        ),
        id="ai-investment-matching",
    ),
]


@pytest.mark.parametrize("item", LEGITIMATE_RECOMMENDATIONS)
def test_real_application_notices_remain_included(item: dict):
    bucket, evaluated = _bucket(item)

    assert bucket == "included", evaluated
    assert evaluated["is_relevant"] is True
