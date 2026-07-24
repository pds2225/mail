"""비지원 게시물(보도자료·위원 모집) 및 입주기업 공장오탐 회귀 테스트 (네트워크/SMTP 없음).

배경(2026-07-24 사용자 O/X 피드백 — '예비창업 AI' 그룹 추천 메일):
  - 보도자료('인천 펜타포트 … 생성형 인공지능 최적화(GEO) 도입')가 그룹 추천에 올라옴.
  - 위원(사람) 모집('… 기획위원(후보자) 모집공고')이 그룹 추천에 올라옴.
  - AI 허브 '입주기업 모집'에 '공장보유 필요' 오탐 표시.
근본 원인: 잡공고/보도자료 판정이 [원본전체] 메일에만 적용되고 그룹 필터(evaluate_notice)에는 없었다.
"""
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


# ── 보도자료 판정 ─────────────────────────────────────────────
def test_press_release_detected():
    pentaport = {
        "title": "인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화'(GEO)'도입 "
                 "제공일자 2026-07-23 제공부서 예술정책과",
        "description": "보도자료 송도달빛축제공원서 개최 제공일시 2026-07-23 담당부서 예술정책과 "
                       "생성형 인공지능(AI) 검색 환경에서 축제 정보가 노출되도록 최적화",
    }
    assert m.is_press_release(pentaport) is True
    assert m.non_opportunity_reason(pentaport) == "보도자료"


def test_press_release_keeps_real_openings():
    """제목에 모집성 토큰이 있으면 보도자료 마커가 섞여 있어도 절대 막지 않는다(recall)."""
    real = {
        "title": "2026년 AI 바우처 지원사업 참여기업 모집 공고",
        "description": "보도자료 제공부서 산업정책과 신청 접수 2026.08.01까지",
    }
    assert m.is_press_release(real) is False


def test_single_marker_not_press_release():
    """마커 1개만으로는 보도자료로 단정하지 않는다(오차단 방지)."""
    one = {"title": "인공지능 활용 사례 담당부서 정책과", "description": "AI 도입 성과"}
    assert m.is_press_release(one) is False


# ── 위원(사람) 모집 = 잡공고 ─────────────────────────────────
def test_committee_member_recruitment_is_junk():
    for t in [
        "AI기반 미래자동차 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고",
        "2026년 창업지원 자문위원 모집",
        "산업육성 심의위원 모집 공고",
    ]:
        assert m.is_report_junk({"title": t}) is True, t
        assert m.non_opportunity_reason({"title": t}) == "잡공고", t


def test_committee_junk_keeps_real_grants():
    """기업 지원공고는 위원 키워드가 없으므로 영향 없다."""
    for t in ["AI 스타트업 지원사업 참여기업 모집 공고", "수출바우처 참여기업 모집",
              "제조 AI 기술 사업화 지원 수혜기업 모집"]:
        assert m.is_report_junk({"title": t}) is False, t


# ── evaluate_notice 게이트: 그룹 추천에도 비지원 게시물이 걸린다 ──
def _relevant_base():
    return dict(
        id="b", title="전국 AI 스타트업 지원사업 참여기업 모집 공고",
        description="전국 AI 스타트업 대상 인공지능 사업화 지원 신청 접수",
        author="기관", source="기업마당", deadline="2026-12-31",
        link="https://x/1", posted_date="2026-07-23",
    )


def test_gate_baseline_is_relevant():
    ev = m.evaluate_notice(_relevant_base(), None)
    assert ev["is_relevant"] is True
    assert "NON_OPPORTUNITY_NOTICE" not in ev["exclude_reason_codes"]


def test_gate_excludes_press_release():
    it = _relevant_base()
    it["title"] = ("인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화 도입 "
                   "제공일자 2026-07-23 제공부서 예술정책과")
    it["description"] = "보도자료 제공일시 2026-07-23 담당부서 예술정책과 생성형 인공지능 AI"
    ev = m.evaluate_notice(it, None)
    assert ev["is_relevant"] is False
    assert "NON_OPPORTUNITY_NOTICE" in ev["exclude_reason_codes"]
    assert ev.get("review_needed") is False
    assert ev.get("region_unknown_review") is False


def test_gate_excludes_committee_recruitment():
    it = _relevant_base()
    it["title"] = "AI 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고"
    ev = m.evaluate_notice(it, None)
    assert ev["is_relevant"] is False
    assert "NON_OPPORTUNITY_NOTICE" in ev["exclude_reason_codes"]


# ── 입주기업 공장 오탐 ────────────────────────────────────────
def test_incubation_tenant_not_factory_flagged():
    """AI 허브 입주기업 모집은 사무/보육공간 — '공장보유 필요' 표시가 붙으면 안 된다."""
    it = dict(
        id="h", title="2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
        description="시설ㆍ공간ㆍ보육 서울 AI 허브 입주기업 모집 인공지능 스타트업",
        author="K-Startup", source="K-Startup", deadline="2026-08-11",
        support_field="시설ㆍ공간ㆍ보육", link="https://x/2", posted_date="2026-07-23",
    )
    ev = m.evaluate_notice(it, None)
    assert ev["factory_required"] is False
    assert not any("공장 보유" in n for n in ev["notes"])


def test_industrial_complex_tenant_still_factory_flagged():
    """산업단지 입주기업은 제조 문맥이므로 공장조건 유지(recall/정확도 균형)."""
    it = dict(
        id="ic", title="남동산업단지 입주기업 스마트공장 구축 지원사업 모집",
        description="산업단지 입주기업 제조 생산시설 대상 스마트공장 구축 지원",
        author="기관", source="기업마당", deadline="2026-12-31",
        link="https://x/3", posted_date="2026-07-23",
    )
    ev = m.evaluate_notice(it, None)
    assert ev["factory_required"] is True
