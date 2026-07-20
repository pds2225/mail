"""recall 보강 B(AI그룹 키워드 확장) + 메일 제목 라벨 버그 수정 회귀 테스트.

진단: ① mail_topic 이 SEMAS 외엔 무조건 '수출·해외진출 공고' 고정 → AI 공고도 그 제목으로 오발송.
      ② grp_ai_saas or_keywords/cmp_seoul_ai industry_keywords 협소 → 머신러닝/LLM/클라우드 등 누락.
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
import company_match as cm  # noqa: E402

GROUPS = {g["id"]: g for g in json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))}
COMPANIES = {c["id"]: c for c in cm.load_companies(ROOT / "companies.json")}

AI_ADJACENT = [
    "머신러닝 기반 솔루션 지원 신청접수",
    "딥러닝 모델 개발기업 지원 신청접수",
    "LLM 활용 서비스 지원 신청접수",
    "클라우드 전환 지원 신청접수",
    "챗봇 도입 지원 신청접수",
    "디지털전환(DX) 지원 신청접수",
    "소프트웨어 개발기업 지원 신청접수",
]


def _it(title, desc="서울 소재 중소기업 대상 신청접수 모집공고"):
    return {"id": "x", "title": title, "description": desc, "author": "기관",
            "deadline": "2099-12-31", "is_aggregator": False}


# ── 제목 라벨 버그 수정 ───────────────────────────────────────────────
def test_mail_topic_not_hardcoded_export():
    """우선키워드 없는 공고 묶음의 제목은 '수출·해외진출'이 아니라 중립 라벨."""
    items = [m.evaluate_notice(_it("AI 솔루션 도입 지원"), GROUPS["grp_ai_saas"])]
    topic = m.mail_topic(items)
    assert topic == "지원사업 공고"
    assert "수출·해외진출" not in topic


def test_mail_topic_uses_priority_keywords():
    items = [{"priority_keywords": ["수출바우처"]}, {"priority_keywords": ["수출바우처", "혁신바우처"]}]
    topic = m.mail_topic(items)
    assert "수출바우처" in topic and topic.endswith("공고")


def test_mail_topic_semas_preserved():
    items = [{"source": m.SEMAS_LOAN_SOURCE}]
    assert m.mail_topic(items) == m.SEMAS_LOAN_TITLE


# ── recall B: 1차 그룹 게이트 ─────────────────────────────────────────
def test_recall_b_group_gate_matches_ai_adjacent():
    g = GROUPS["grp_ai_saas"]
    for title in AI_ADJACENT:
        ev = m.evaluate_notice(_it(title), g)
        assert "INDUSTRY_NOT_MATCHED" not in ev["exclude_reason_codes"], title


def test_recall_b_existing_ai_still_matches():
    """기존 AI/인공지능/데이터/SaaS 도 여전히 매칭(회귀 방지)."""
    for title in ["AI 솔루션 도입 지원 신청접수", "인공지능 바우처 신청접수",
                  "빅데이터 분석 지원 신청접수", "SaaS 플랫폼 구축 지원 신청접수"]:
        ev = m.evaluate_notice(_it(title), GROUPS["grp_ai_saas"])
        assert "INDUSTRY_NOT_MATCHED" not in ev["exclude_reason_codes"], title


# ── recall B: 2차 기업 컷오프 게이트 ──────────────────────────────────
def test_recall_b_company_gate_scores_ai_adjacent():
    """기업 2차 컷오프(cmp_seoul_ai)도 AI 인접어를 산업적합으로 인정해야 누락 안 됨."""
    comp = COMPANIES["cmp_seoul_ai"]
    for title in ["머신러닝 기반 솔루션 지원", "LLM 서비스 지원", "클라우드 전환 지원", "챗봇 도입 지원"]:
        s = cm.compute_match_score(_it(title), comp)
        assert s["breakdown"]["industry_hits"] >= 1, title
