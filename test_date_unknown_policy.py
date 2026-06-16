"""
날짜불명(게시일 못읽음) 공고 처리정책 테스트 (split_unknown_by_policy).
재현 우선(recall) = 신청키워드·마감 살아있는 불명만 메일 포함, 나머지는 검토대기.
실제 API/이메일 호출 없음.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 환경변수 mock — monitor 임포트 전에 설정
os.environ.setdefault("BIZINFO_API_KEY",    "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY",  "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS",      "test@test.com")

from monitor import split_unknown_by_policy, assess_date_unknown_risk


def _mk(title, description="", link="", deadline=""):
    return {"title": title, "description": description, "link": link, "deadline": deadline}


def test_strict_excludes_all_unknown():
    items = [_mk("A", deadline="2026-12-31"), _mk("B", description="신청 접수")]
    included, remaining = split_unknown_by_policy(items, "strict")
    assert included == []
    assert len(remaining) == 2


def test_all_includes_every_unknown():
    items = [_mk("A"), _mk("B", description="뉴스레터")]
    included, remaining = split_unknown_by_policy(items, "all")
    assert len(included) == 2
    assert remaining == []


def test_recall_includes_item_with_live_deadline():
    # 게시일 불명이어도 신청마감이 살아있으면 '안 놓치게' 포함(직접 코딩된 규칙: deadline → 중간)
    items = [_mk("마감있는공고", deadline="2026-12-31")]
    included, remaining = split_unknown_by_policy(items, "recall")
    assert len(included) == 1 and len(remaining) == 0
    assert assess_date_unknown_risk(items[0]) in ("중간", "높음")


def test_recall_split_is_consistent_with_risk():
    items = [
        _mk("A", deadline="2026-12-31"),          # 마감 → 포함
        _mk("B", description="사업 신청 접수 모집"),  # 신청키워드 → 포함(있다면)
        _mk("C", description="정기 뉴스레터 안내"),    # 신호 없음 → 검토대기
    ]
    included, remaining = split_unknown_by_policy(items, "recall")
    # 포함분은 모두 위험도 중간↑, 잔여는 모두 낮음 — 정책이 위험도와 일치
    for it in included:
        assert assess_date_unknown_risk(it) in ("중간", "높음")
    for it in remaining:
        assert assess_date_unknown_risk(it) == "낮음"
    # 마감 있는 A는 반드시 발송 포함
    assert any(it["title"] == "A" for it in included)
    assert len(included) + len(remaining) == 3
