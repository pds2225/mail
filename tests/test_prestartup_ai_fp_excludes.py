"""grp_prestartup_ai 그룹 — 2026-07-24 사용자 O/X 피드백 FP 4건 회귀 테스트.

배경: 실 발송 메일에서 아래 4가지 유형이 '예비창업 AI' 공고로 잘못 매칭됐다.
  1. 방위산업(방산) 생산성향상 지원사업 — "방산" 키워드, AI 스타트업 무관
  2. AI기반 미래자동차 기획위원(후보자) 모집 — 위원 채용, 지원사업 아님
  3. 수요기관 임직원 사칭 사기피해 예방 안내 — 사기 예방 공지, 지원사업 아님
  4. 세계 음악축제 생성형AI 최적화(GEO)도입 보도자료 — 문화행사 보도, 지원사업 아님

수정: groups.json grp_prestartup_ai.exclude_keywords 에 해당 패턴 추가.
★이 파일의 모든 테스트는 precision 목적이므로 recall 회귀 가드도 함께 포함한다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

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
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

G = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
_GRP = G["grp_prestartup_ai"]

_FUTURE = (datetime.now(m.KST) + timedelta(days=30)).strftime("%Y-%m-%d")


def _ev(item: dict) -> dict:
    return m.evaluate_notice(item, _GRP)


def _is_blocked(item: dict) -> bool:
    return not _ev(item)["is_relevant"]


# ═══════════════════════════════════════════════════════════════
# (A) FP 차단 — precision: 이 4건은 반드시 is_relevant=False
# ═══════════════════════════════════════════════════════════════

def test_방산_중소기업_생산성향상_blocked():
    """방산/방위산업 공고는 예비창업 AI 그룹 대상이 아니다."""
    item = {
        "title": "2026년도 인천시 방산 중소기업 생산성향상 지원사업 수혜 후보기업 모집",
        "description": (
            "방위산업 부품 생산기업의 방산 부품 생산능력 향상을 위한 금형 및 생산설비 고도화 지원. "
            "인천지역 방산 중소기업 대상 모집."
        ),
        "author": "인천테크노파크",
        "deadline": _FUTURE,
        "region_field": "인천",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False, "방산 공고는 예비창업 AI 그룹에서 제외돼야 함"
    assert any(kw in ("방산", "방위산업") for kw in ev.get("excluded_keywords", [])), \
        "제외 근거('방산' 또는 '방위산업')가 excluded_keywords 에 기록돼야 함"


def test_ai기반_기획위원_모집_blocked():
    """'기획위원(후보자) 모집'은 위원 채용 공고이지 창업 지원사업이 아니다."""
    item = {
        "title": "AI기반 종단간 미래자동차 E2E 고속자율주행 고성능 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고",
        "description": "기획위원 모집공고. 담당자정보 윤문영 부서 자동차산업팀.",
        "author": "경남테크노파크",
        "deadline": _FUTURE,
        "region_field": "전국",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False, "기획위원 모집은 예비창업 AI 그룹에서 제외돼야 함"
    assert "기획위원" in ev.get("excluded_keywords", []), \
        "제외 근거('기획위원')가 excluded_keywords 에 기록돼야 함"


def test_사기피해_예방_안내_blocked():
    """사기피해 예방 안내 공지는 지원사업이 아니다."""
    item = {
        "title": "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
        "description": (
            "최근 수요기관(지자체, 공공기관, 소방서 등) 직원을 사칭하여 고액 물품대납을 "
            "유도하는 사기 사례가 급증하고 있습니다. 사칭사기수법 안내."
        ),
        "author": "이노비즈협회",
        "deadline": _FUTURE,
        "region_field": "전국",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False, "사기피해 안내는 예비창업 AI 그룹에서 제외돼야 함"
    excluded = ev.get("excluded_keywords", [])
    assert any(kw in excluded for kw in ("사기피해", "사칭", "허위구매")), \
        "제외 근거(사기피해·사칭·허위구매 중 하나)가 excluded_keywords 에 기록돼야 함"


def test_음악축제_AI최적화_보도자료_blocked():
    """음악축제 보도자료(AI 언급 포함)는 지원사업 공고가 아니다."""
    item = {
        "title": "인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화'(GEO)'도입",
        "description": (
            "인천광역시가 주최하는 인천펜타포트 음악축제가 세계 음악축제 최초로 "
            "생성형 엔진 최적화(GEO) 개념을 도입해 글로벌 홍보 혁신에 나선다. "
            "7월 31일~8월 2일 송도달빛축제공원서 개최."
        ),
        "author": "인천광역시청",
        "deadline": _FUTURE,
        "region_field": "인천",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False, "음악축제 보도는 예비창업 AI 그룹에서 제외돼야 함"
    assert "음악축제" in ev.get("excluded_keywords", []), \
        "제외 근거('음악축제')가 excluded_keywords 에 기록돼야 함"


# ═══════════════════════════════════════════════════════════════
# (B) recall 가드 — 정당 공고가 새 exclude 에 걸리지 않음을 못박는다
# ═══════════════════════════════════════════════════════════════

def test_서울AI허브_입주기업_모집_not_blocked():
    """2026년 서울 AI 허브 신규 입주기업 모집은 반드시 통과돼야 한다."""
    item = {
        "title": "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
        "description": (
            "서울시 소재 AI 스타트업 대상 AI 허브 입주기업 모집. "
            "신청기간 내 온라인 접수."
        ),
        "author": "서울산업진흥원",
        "deadline": _FUTURE,
        "region_field": "서울",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is True, "서울 AI 허브 입주 모집은 예비창업 AI 그룹에서 통과돼야 함"


def test_관악구_한국전자전_모집_not_blocked():
    """[서울] 관악구 한국전자전 참가기업 모집은 통과돼야 한다."""
    item = {
        "title": "[서울] 관악구 2026년 한국전자전(KES) 관악S밸리관 참가기업 모집 공고",
        "description": (
            "AX(AI transformation), 로보틱스 등 전 산업 분야 IT 전시회 참가 모집. "
            "관악 소재 유망 스타트업 신청 가능."
        ),
        "author": "관악중소벤처진흥원",
        "deadline": _FUTURE,
        "region_field": "서울",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is True, "한국전자전 AI 스타트업 참가 모집은 통과돼야 함"


def test_제조AI기술사업화_지원_not_blocked():
    """제조 AI 기술 사업화 지원 수혜기업 모집은 통과돼야 한다."""
    item = {
        "title": "제조 AI 기술 사업화 지원 수혜기업 모집",
        "description": (
            "AI 솔루션을 활용한 제조 공정 혁신 기업 모집. "
            "스타트업·중소기업 신청접수."
        ),
        "author": "중소벤처기업부",
        "deadline": _FUTURE,
        "region_field": "전국",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is True, "제조 AI 사업화 지원은 예비창업 AI 그룹에서 통과돼야 함"


def test_클라우드AI사업_지원_not_blocked():
    """클라우드·AI 기반 스타트업 지원 공고는 방산·사기피해·음악축제 exclude 에 걸리지 않는다."""
    item = {
        "title": "2026년 AI·클라우드 스타트업 성장지원사업 참여기업 모집",
        "description": (
            "AI, 클라우드, SaaS 분야 예비창업자 및 초기 스타트업 신청 가능. "
            "전국 모집."
        ),
        "author": "NIPA",
        "deadline": _FUTURE,
        "region_field": "전국",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is True, "AI·클라우드 스타트업 지원은 통과돼야 함"
