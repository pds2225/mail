"""지원 기회 아닌 제목(기획위원·사기안내·보도성) 그룹 추천 제외 회귀.

배경: 2026-07-24 [예비창업 AI] 메일에 아래 FP가 섞여 발송됨.
  1) 기획위원(후보자) 모집 — nav 크롬의 '스마트공장·서울TP'로 priority/region 오탐
  2) 사기피해 예방 안내 — '해외'가 APPLICATION_KEYWORDS라 application_like 오탐
  3) 축제 GEO 보도자료 — '글로벌'+AI 키워드로 추천

★설계: 제목 앵커만 차단(본문 우연일치로 진짜 공고 누락 금지).
  '기획위원 모집공고'처럼 모집/공고 토큰이 있어도 위원 위촉은 막는다.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

for _k, _v in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
    "MONITOR_NO_PERSIST_SEEN": "1",
}.items():
    if not os.environ.get(_k, "").strip():
        os.environ[_k] = _v

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

G = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
PRE = G["grp_prestartup_ai"]
TODAY = date(2026, 7, 24)


def _ev(item: dict) -> dict:
    return m.evaluate_notice(item, PRE, today=TODAY)


# ── 실제 메일 FP ──────────────────────────────────────────────


def test_기획위원_모집_은_그룹추천에서_제외():
    """nav에 스마트공장·서울TP가 있어도 기획위원 모집은 지원 기회가 아니다."""
    item = {
        "title": "AI기반 종단간 미래자동차 E2E 고속자율주행 고성능 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고",
        "description": (
            "지원사업신청 스마트공장지원 입찰정보 공지사항 채용정보 "
            "서울테크노파크 인천테크노파크 경남테크노파크 제도 안내"
        ),
        "source": "경남테크노파크",
        "posted_date": "2026-07-23",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]
    assert "기획위원" in ev["excluded_keywords"]
    assert m.non_grant_opportunity_reason(item) == "기획위원"


def test_사기피해_예방_안내는_그룹추천에서_제외():
    item = {
        "title": "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
        "description": (
            "해외 무역업체를 사칭한 사기 사례. 나라장터. Global leader. "
            "AI 소프트웨어 이노비즈"
        ),
        "deadline": "2026-12-28",
        "source": "이노비즈협회",
        "posted_date": "2026-06-25",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]
    assert m.non_grant_opportunity_reason(item) in {"사기피해", "허위구매", "사칭"}


def test_축제_보도자료는_application_like_아님_추천제외():
    """산업어 '글로벌'만으로는 application_like가 열리지 않아 보도자료가 추천되지 않는다."""
    item = {
        "title": "인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화'(GEO)'도입",
        "description": (
            "보도자료. 생성형 인공지능(AI) 검색 환경. 글로벌 홍보 혁신. "
            "7월 31일~8월 2일 송도달빛축제공원서 개최"
        ),
        "deadline": "2026-08-02",
        "source": "인천광역시청 - 공고/고시",
        "posted_date": "2026-07-23",
        "author": "인천광역시",
    }
    assert m._application_like(m._notice_text(item)) is False
    ev = _ev(item)
    assert ev["is_relevant"] is False


# ── recall 가드: 진짜 AI 지원공고는 유지 ───────────────────────


@pytest.mark.parametrize("title,desc", [
    (
        "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
        "시설ㆍ공간ㆍ보육 서울 AI 허브 입주기업 모집 신청접수",
    ),
    (
        "제조 AI 기술 사업화 지원 수혜기업 모집",
        "전국 중소기업 대상 제조 AI 사업화 지원사업 공고",
    ),
    (
        "[서울] 관악구 2026년 한국전자전(KES) 관악S밸리관 참가기업 모집 공고",
        "AX AI transformation 관악 소재 유망 스타트업 참가신청",
    ),
])
def test_진짜_AI_지원공고는_유지(title, desc):
    ev = _ev({
        "title": title,
        "description": desc,
        "deadline": "2026-08-31",
        "posted_date": "2026-07-23",
        "source": "K-Startup",
        "author": "서울특별시",
    })
    assert m.non_grant_opportunity_reason({"title": title}) == ""
    assert ev["is_relevant"] is True, (title, ev["exclude_reason_codes"])


def test_본문에만_기획위원_있으면_막지_않음():
    """본문 우연일치로 진짜 공고를 누락하지 않는다(제목만 판정)."""
    item = {
        "title": "2026 AI 바우처 참여기업 모집 공고",
        "description": "서울 소재 기업. 별도 기획위원 구성 예정. 신청접수",
        "deadline": "2026-08-31",
        "posted_date": "2026-07-23",
        "author": "중기부",
    }
    assert m.non_grant_opportunity_reason(item) == ""
    ev = _ev(item)
    assert ev["is_relevant"] is True


def test_env_kill_switch_disables_nongrant_filter(monkeypatch):
    monkeypatch.setenv(m.NONGGRANT_FILTER_ENV, "1")
    item = {"title": "AI 기획위원 모집공고", "description": "서울 AI"}
    assert m.non_grant_opportunity_reason(item) == ""


def test_report_junk_includes_기획위원_and_사기():
    assert m.is_report_junk({"title": "OO 기획위원 모집"}) is True
    assert m.is_report_junk({"title": "사기피해 예방 안내"}) is True
    assert m.is_report_junk({"title": "AI 바우처 참여기업 모집 공고"}) is False


def test_application_keywords_no_longer_include_geo_industry_alone():
    """글로벌/해외 단독으로는 application_like 가 열리지 않는다."""
    for banned in ("글로벌", "해외", "베트남", "동남아", "화장품", "뷰티", "k-beauty"):
        assert banned not in m.APPLICATION_KEYWORDS
    assert m._application_like("글로벌 홍보 혁신 보도자료") is False
    assert m._application_like("해외 무역업체 사기 주의") is False
    # 진짜 신청 신호는 유지
    assert m._application_like("참여기업 모집 신청접수") is True
    assert m._application_like("해외전시회 참가신청") is True
