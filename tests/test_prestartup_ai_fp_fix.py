"""예비창업 AI 그룹 오탐 회귀 — 2026-07-24 메일 피드백 사례.

OR 단독 키워드(AI·데이터·생성형)만으로 잡히던 비창업·비지원 공고를 차단하고,
서울 AI 허브 등 정당 공고는 유지한다.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

G = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
GRP = G["grp_prestartup_ai"]


def _ev(item: dict) -> dict:
    return m.evaluate_notice(item, GRP)


def _included(item: dict) -> bool:
    return m.filter_for_group_with_diagnostics([item], GRP)["included"] != []


# ── 오탐 차단 (사용자 ❌ 예상) ────────────────────────────────────────────────
def test_blocks_defense_manufacturing_notice():
    item = {
        "title": "인천시 방산 중소기업 생산성향상 지원사업 수혜 후보기업 모집 공고",
        "description": "방산 중소기업 생산설비 고도화 지원금 모집 신청",
        "deadline": "2026-08-05",
        "posted_date": "2026-07-22",
        "region_field": "인천",
        "author": "인천테크노파크",
    }
    assert _ev(item)["is_relevant"] is False


def test_blocks_planning_committee_recruitment():
    item = {
        "title": "AI기반 미래자동차 E2E 고속자율주행 플랫폼 검증 기반구축 기획위원(후보자) 모집공고",
        "description": "기획위원 모집",
        "posted_date": "2026-07-23",
        "author": "경남테크노파크",
        "region_field": "경남",
    }
    assert _ev(item)["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in _ev(item)["exclude_reason_codes"]


def test_blocks_impersonation_fraud_notice():
    item = {
        "title": "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
        "description": "사기 예방 안내",
        "deadline": "2026-12-28",
        "posted_date": "2026-06-25",
        "region_field": "전국",
    }
    assert _ev(item)["is_relevant"] is False


def test_blocks_music_festival_press_release():
    item = {
        "title": "인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화(GEO) 도입",
        "description": "생성형 인공지능 축제 홍보",
        "deadline": "2026-08-02",
        "posted_date": "2026-07-23",
        "author": "인천광역시",
    }
    assert _ev(item)["is_relevant"] is False


def test_blocks_bigdata_academy_without_startup_signal():
    item = {
        "title": "[일반] 2026년 데이터 ON 고양 빅데이터 아카데미 참여자 모집 공고",
        "description": "빅데이터 아카데미 참여자 모집 교육",
        "deadline": "2026-08-13",
        "posted_date": "2026-07-23",
        "author": "고양산업진흥원",
    }
    assert _ev(item)["is_relevant"] is False


# ── 정당 공고 유지 (recall) ───────────────────────────────────────────────────
def test_keeps_seoul_ai_hub_incubation():
    item = {
        "title": "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
        "description": "서울 AI 허브 입주기업 모집 인공지능 스타트업",
        "deadline": "2026-08-11",
        "posted_date": "2026-07-23",
        "support_field": "시설ㆍ공간ㆍ보육",
        "region_field": "서울",
    }
    assert _ev(item)["is_relevant"] is True
    assert _included(item)


def test_keeps_ai_solution_participant_notice():
    """기존 test_filter_accuracy_r2 회귀 — support_field=멘토링 + AI 솔루션 공고."""
    item = {
        "title": "서울 AI 솔루션 도입 참여기업 모집 신청접수",
        "description": "신청",
        "deadline": "2099-12-31",
        "support_field": "멘토링",
        "region_field": "전국",
    }
    ev = _ev(item)
    assert ev["is_relevant"] is True
    assert ev["group_keyword_pass"] is True


def test_and_keyword_gate_requires_both_ai_and_startup():
    item = {"title": "전국 중소기업 경영안정 자금 지원", "description": "모집 신청", "region_field": "전국"}
    assert _ev(item)["group_keyword_pass"] is False
