"""govsupport-mailing-v2 scoring module.

Design Ref: §5 scoring.py — 점수 계산 + LLM 2차 판정 + 임계값.
Plan SC1: 부적합 공고 50% 감소.

monitor.py의 키워드 1차 필터를 통과한 아이템에 대해 가중치 점수를 매기고,
score_threshold 미만은 제외. 회색지대(llm_check_threshold_band) 아이템은
Claude로 2차 판정.

하위호환: group에 'score_threshold' 키가 없으면 score_and_filter는 입력 전체를
그대로 통과시킨다 (monitor.py 회귀 방지).
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_WEIGHTS: dict[str, int] = {
    "priority_match": 30,
    "or_keyword_match": 5,
    "exclude_penalty": -50,
    "region_match": 20,
}
DEFAULT_THRESHOLD = 50
DEFAULT_LLM_BAND = (40, 70)


def _haystack(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title", "")),
        str(item.get("summary", "")),
        str(item.get("content", "")),
        str(item.get("category", "")),
    ]
    return " ".join(parts).lower()


def _count_hits(text: str, keywords: list[str]) -> int:
    if not keywords:
        return 0
    return sum(1 for kw in keywords if kw and kw.lower() in text)


def compute_score(item: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    weights = {**DEFAULT_WEIGHTS, **(group.get("weights") or {})}
    text = _haystack(item)

    priority_hits = _count_hits(text, group.get("priority_keywords") or [])
    or_hits = _count_hits(text, group.get("or_keywords") or [])
    exclude_hits = _count_hits(text, group.get("exclude_keywords") or [])

    region_match = 0
    regions = (group.get("required_conditions") or {}).get("regions") or []
    if regions:
        region_match = 1 if any(r and r.lower() in text for r in regions) else 0

    score = (
        priority_hits * weights["priority_match"]
        + or_hits * weights["or_keyword_match"]
        + exclude_hits * weights["exclude_penalty"]
        + region_match * weights["region_match"]
    )
    score = max(0, min(100, score))

    reasons: list[str] = []
    if priority_hits:
        reasons.append(f"priority {priority_hits}x")
    if or_hits:
        reasons.append(f"or {or_hits}x")
    if exclude_hits:
        reasons.append(f"exclude {exclude_hits}x (penalty)")
    if region_match:
        reasons.append("region match")

    return {
        "score": int(score),
        "breakdown": {
            "priority_hits": priority_hits,
            "or_hits": or_hits,
            "exclude_hits": exclude_hits,
            "region_match": region_match,
        },
        "reasons": reasons,
    }


def llm_relevance_check(item: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    """Claude 2차 판정. 비용 절감을 위해 score 회색지대 아이템에만 호출.

    실패 시 'is_relevant': True 로 통과 (보수적). 호출 측에서 캐시/상한 제어.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        return {"is_relevant": True, "confidence": 0.0, "reason": "anthropic not installed"}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"is_relevant": True, "confidence": 0.0, "reason": "no api key"}

    title = str(item.get("title", ""))[:200]
    summary = str(item.get("summary", ""))[:500]
    priority_kw = ", ".join((group.get("priority_keywords") or [])[:10])
    exclude_kw = ", ".join((group.get("exclude_keywords") or [])[:10])
    region = ", ".join((group.get("required_conditions") or {}).get("regions") or [])

    prompt = (
        "다음 정부지원사업 공고가 아래 그룹 조건에 신청 가능/적합한지 판정하라.\n"
        f"그룹 지역: {region}\n"
        f"우선 키워드: {priority_kw}\n"
        f"제외 키워드: {exclude_kw}\n"
        "JSON만 응답: {\"is_relevant\": true|false, \"confidence\": 0~1, \"reason\": \"...\"}\n"
        f"제목: {title}\n"
        f"요약: {summary}"
    )

    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content) if msg.content else ""
        import json
        import re
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"is_relevant": True, "confidence": 0.0, "reason": "parse fail"}
        parsed = json.loads(m.group(0))
        return {
            "is_relevant": bool(parsed.get("is_relevant", True)),
            "confidence": float(parsed.get("confidence", 0.5)),
            "reason": str(parsed.get("reason", ""))[:200],
        }
    except Exception as e:
        return {"is_relevant": True, "confidence": 0.0, "reason": f"err:{type(e).__name__}"}


def score_and_filter(items: list[dict], group: dict) -> dict[str, Any]:
    """Backward compatible: if 'score_threshold' not in group, pass through."""
    if "score_threshold" not in group:
        return {"passed": list(items), "rejected": [], "audit": []}

    threshold = int(group.get("score_threshold", DEFAULT_THRESHOLD))
    band = tuple(group.get("llm_check_threshold_band") or DEFAULT_LLM_BAND)
    llm_enabled = bool(group.get("llm_check_enabled", False))
    llm_call_count = 0
    llm_call_limit = int(group.get("llm_call_limit_per_run", 30))

    passed: list[dict] = []
    rejected: list[dict] = []
    audit: list[dict] = []

    for item in items:
        s = compute_score(item, group)
        score = s["score"]
        record: dict[str, Any] = {
            "title": str(item.get("title", ""))[:80],
            "score": score,
            "breakdown": s["breakdown"],
            "reasons": s["reasons"],
            "llm": None,
        }

        if llm_enabled and band[0] <= score <= band[1] and llm_call_count < llm_call_limit:
            llm_result = llm_relevance_check(item, group)
            llm_call_count += 1
            record["llm"] = llm_result
            if not llm_result.get("is_relevant", True):
                rejected.append(item)
                record["decision"] = "rejected_by_llm"
                audit.append(record)
                continue

        if score >= threshold:
            passed.append(item)
            record["decision"] = "passed"
        else:
            rejected.append(item)
            record["decision"] = "rejected_by_score"
        audit.append(record)

    return {"passed": passed, "rejected": rejected, "audit": audit}
