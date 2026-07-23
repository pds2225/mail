"""메일 본문 잘림 회귀 테스트.

버그: 그룹 요약은 Claude(Haiku) 출력을 그대로 본문으로 쓰는데, 출력 토큰 상한
(max_tokens)에 걸려 응답이 중간에 끊기면 뒤쪽 공고 본문이 통째로 사라졌다
(예: '인천 화장품 제조' 공고 본문 잘림). 또 fallback 경로의 지원내용은 600자에서
조기에 잘렸다.

수정:
  ① claude_summarize: stop_reason=='max_tokens' 이면 잘린 요약 대신 전 공고를
     빠짐없이 담는 fallback_body 로 대체.
  ② _plain_text 기본 한도 600 → 1500 확대(지원내용 조기 잘림 완화).
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


def _items():
    return [
        {"id": "a", "title": "인천 화장품 제조 스마트공장 고도화 지원",
         "description": "화장품 제조기업 대상 스마트공장 구축·고도화 지원사업입니다.",
         "author": "인천테크노파크", "deadline": "2099-12-31", "source": "기업마당",
         "posted_date": "2026-07-06", "link": "https://x/1", "is_aggregator": False},
        {"id": "b", "title": "뒤쪽 공고 — 잘리면 사라짐",
         "description": "이 공고 본문이 요약 잘림으로 사라지면 안 된다.",
         "author": "기관", "deadline": "2099-12-31", "source": "기업마당",
         "posted_date": "2026-07-05", "link": "https://x/2", "is_aggregator": False},
    ]


def _group():
    return {"id": "g", "name": "인천 제조팀", "or_keywords": ["화장품", "제조"],
            "required_conditions": {"regions": ["인천"]}}


def test_summary_never_truncates_or_omits_collected_notices():
    """발송용 요약은 모델 출력 대신 전 공고를 빠짐없이 담는 결정론적 본문이다."""
    body = m.claude_summarize(_items(), _group())
    assert "인천 화장품 제조" in body
    assert "뒤쪽 공고" in body
    assert "이 공고 본문이 요약 잘림으로 사라지면 안 된다" in body


def test_summary_never_uses_model_text():
    """환경 변수와 무관하게 환각 가능한 모델 문장은 발송 본문으로 쓰지 않는다."""
    body = m.claude_summarize(_items(), _group())
    assert "MODEL_SUMMARY_OK" not in body
    assert "인천 화장품 제조" in body and "뒤쪽 공고" in body


def test_summary_never_returns_empty_for_nonempty_items():
    """공고가 있으면 모델 상태와 무관하게 본문이 비지 않는다."""
    body = m.claude_summarize(_items(), _group())
    assert "인천 화장품 제조" in body and "뒤쪽 공고" in body


def test_plain_text_keeps_long_body_up_to_new_limit():
    """지원내용이 600자에서 조기에 잘리지 않는다(한도 1500)."""
    long = "가" * 1200
    out = m._plain_text(long)
    assert len(out) >= 1200          # 600 에서 잘리면 실패
    assert "…" not in out            # 1500 이하는 말줄임 없이 전량


def test_plain_text_still_truncates_beyond_limit():
    """한도 초과분은 여전히 말줄임(…)으로 유계 유지."""
    out = m._plain_text("나" * 3000)
    assert out.endswith("…")
    assert len(out) < 3000
