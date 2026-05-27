"""Keyword rules for SEMAS policy loan monitoring."""

from __future__ import annotations

from collections.abc import Iterable


POLICY_LOAN_KEYWORDS = [
    "정책자금",
    "직접대출",
    "대리대출",
    "재도전특별자금",
    "재창업",
    "소공인특화자금",
    "스마트자금",
    "일반경영안정자금",
    "특별경영안정자금",
    "접수",
    "신청",
    "마감",
    "예산소진",
    "보완",
    "공지",
    "안내",
    "온라인신청",
]

KEYWORD_GROUPS = {
    "정책자금": [
        "정책자금",
        "직접대출",
        "대리대출",
        "소공인특화자금",
        "스마트자금",
        "일반경영안정자금",
        "특별경영안정자금",
    ],
    "재도전특별자금": ["재도전특별자금", "재창업"],
    "접수": ["접수", "접수중"],
    "신청": ["신청", "온라인신청"],
    "마감": ["마감"],
    "예산소진": ["예산소진", "예산 소진"],
    "공지/안내": ["공지", "안내"],
    "오류/점검": ["오류", "점검", "시스템 점검", "서비스 중단", "장애"],
}


def normalize_space(value: str) -> str:
    """Collapse whitespace without changing Korean terms."""
    return " ".join((value or "").split())


def detect_keywords(text: str, keywords: Iterable[str] = POLICY_LOAN_KEYWORDS) -> list[str]:
    """Return configured keywords present in text, preserving rule order."""
    haystack = normalize_space(text).casefold()
    return [keyword for keyword in keywords if keyword.casefold() in haystack]


def keyword_presence(text: str) -> dict[str, bool]:
    """Return grouped keyword booleans used in the Markdown report."""
    return {
        group: bool(detect_keywords(text, terms))
        for group, terms in KEYWORD_GROUPS.items()
    }


def keyword_evidence(text: str, *, max_chars: int = 100) -> dict[str, str]:
    """Return short evidence snippets without exposing full page HTML."""
    normalized = normalize_space(text)
    folded = normalized.casefold()
    evidence: dict[str, str] = {}
    for group, terms in KEYWORD_GROUPS.items():
        snippet = ""
        for term in terms:
            idx = folded.find(term.casefold())
            if idx == -1:
                continue
            start = max(0, idx - 35)
            end = min(len(normalized), idx + len(term) + 65)
            snippet = normalized[start:end].strip()
            if len(snippet) > max_chars:
                snippet = snippet[: max_chars - 1].rstrip() + "..."
            break
        evidence[group] = snippet
    return evidence

