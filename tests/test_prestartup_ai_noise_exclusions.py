"""grp_prestartup_ai 노이즈 공고 제외 회귀 테스트.

사용자 실사례에서 AI 그룹에 섞여 들어온 비지원성 게시물(위원 모집/보도자료/사기 예방 안내)을
그룹 exclude_keywords 보강으로 안정적으로 배제하는지 검증한다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

import monitor as m  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
GROUPS = json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))
PRESTARTUP_AI = next(g for g in GROUPS if g["id"] == "grp_prestartup_ai")


def _ev(item: dict) -> dict:
    return m.evaluate_notice(item, PRESTARTUP_AI)


def test_committee_candidate_notice_is_excluded():
    item = {
        "title": "AI기반 종단간 미래자동차 E2E 고속자율주행 고성능 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고",
        "description": "첨부 1. 기획위원 모집공고 및 관련서식",
        "author": "경남테크노파크",
        "source": "경남테크노파크",
        "link": "https://www.gntp.or.kr/board/detail/new/20744",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]
    assert "기획위원" in ev["excluded_keywords"]


def test_press_release_style_ai_article_is_excluded():
    item = {
        "title": "인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화(GEO)도입",
        "description": "보도자료 공유레이어열기 스크랩",
        "author": "인천광역시",
        "source": "인천광역시청 - 공고/고시",
        "link": "https://www.incheon.go.kr/IC010205/view?repSeq=DOM_0000000015195041&curPage=1",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]
    assert "보도자료" in ev["excluded_keywords"]


def test_fraud_alert_notice_is_excluded():
    item = {
        "title": "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
        "description": "최근 수요기관 직원을 사칭하여 고액 물품대납을 유도하는 사례가 급증",
        "author": "이노비즈협회",
        "source": "이노비즈협회(사)중소기업기술혁신",
        "link": "https://www.innobiz.net/company/company1_view.asp?Seq=434",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in ev["exclude_reason_codes"]
    assert "사기피해" in ev["excluded_keywords"] or "허위구매" in ev["excluded_keywords"]
