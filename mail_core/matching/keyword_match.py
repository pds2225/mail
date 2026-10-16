"""공통 그룹 키워드 경계·별칭·부정 문맥 매칭."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Mapping

DEFAULT_ALIAS_PATH = Path(__file__).resolve().parents[2] / "config" / "keyword_aliases.json"
_HANGUL_SHORT = re.compile(r"^[가-힣]{1,2}$")
_NEGATION = re.compile(
    r"제외|불가|해당\s*없(?:음|습니다|다)?|제한|아닌|아님|미지원|"
    r"하지\s*않|지원하지\s*않|대상(?:이)?\s*아님"
)
_NEGATION_CANCELLED = re.compile(
    r"제외\s*(?:(?:하지|되지)\s*않|안\s*함|대상(?:이)?\s*아님)"
)
_KOREAN_PARTICLES = (
    "으로", "에서", "에게", "부터", "까지", "처럼", "보다", "마다",
    "은", "는", "이", "가", "을", "를", "에", "의", "와", "과",
    "도", "만", "로",
)


@lru_cache(maxsize=8)
def load_keyword_aliases(path: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    """동의어 사전을 읽는다. 파일이 없거나 잘못되면 빈 사전으로 하위호환한다."""
    alias_path = Path(path) if path is not None else DEFAULT_ALIAS_PATH
    try:
        payload = json.loads(alias_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    aliases = payload.get("aliases", {}) if isinstance(payload, dict) else {}
    return _read_forms(aliases)


@lru_cache(maxsize=8)
def load_keyword_variants(path: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    """방향성 있는 활용형·합성어 사전을 읽는다."""
    alias_path = Path(path) if path is not None else DEFAULT_ALIAS_PATH
    try:
        payload = json.loads(alias_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    variants = payload.get("variants", {}) if isinstance(payload, dict) else {}
    return _read_forms(variants)


def _read_forms(raw: object) -> dict[str, tuple[str, ...]]:
    aliases = raw
    if not isinstance(aliases, dict):
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for canonical, variants in aliases.items():
        key = str(canonical or "").strip()
        if not key or not isinstance(variants, list):
            continue
        result[key] = tuple(dict.fromkeys(
            str(value).strip() for value in variants if str(value).strip()
        ))
    return result


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def keyword_forms(
    keyword: str,
    aliases: Mapping[str, tuple[str, ...]] | None = None,
    variants: Mapping[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """설정된 별칭을 양방향으로 확장하되, 미등록 키워드는 그대로 둔다."""
    key = str(keyword or "").strip()
    if not key:
        return []
    forms = [key]
    alias_map = load_keyword_aliases() if aliases is None else aliases
    variant_map = load_keyword_variants() if variants is None else variants
    compact_key = _compact(key)
    for canonical, variants in alias_map.items():
        group = [canonical, *variants]
        if compact_key in {_compact(value) for value in group}:
            forms.extend(group)
    for canonical, variant_forms in variant_map.items():
        if compact_key == _compact(canonical):
            forms.extend(variant_forms)
    return list(dict.fromkeys(forms))


def _compact_with_positions(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        if not char.isspace():
            chars.append(char.lower())
            positions.append(index)
    return "".join(chars), positions


def _short_hangul_boundary_ok(
    compact_text: str, positions: list[int], start: int, end: int, source: str
) -> bool:
    """두 글자 이하 한글은 붙어 있는 한글 합성어에서 오매칭하지 않는다."""
    if start:
        previous = positions[start - 1]
        current = positions[start]
        gap = source[previous + 1:current]
        if "가" <= compact_text[start - 1] <= "힣" and not gap:
            return False
    if end < len(compact_text):
        current = positions[end - 1]
        following = positions[end]
        gap = source[current + 1:following]
        if "가" <= compact_text[end] <= "힣" and not gap:
            tail = compact_text[end:]
            if not any(tail.startswith(particle) for particle in _KOREAN_PARTICLES):
                return False
    return True


def _is_negated(source: str, start: int, end: int) -> bool:
    context = source[max(0, start - 20):start] + source[end:end + 20]
    if source[max(0, start - 1):start] in {"미", "비"}:
        return True
    context = _NEGATION_CANCELLED.sub(" ", context)
    return bool(_NEGATION.search(context))


def keyword_match_details(
    text: str,
    keyword: str,
    *,
    aliases: Mapping[str, tuple[str, ...]] | None = None,
    variants: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[bool, bool]:
    """(긍정 히트, 부정 문맥 히트)를 반환한다."""
    source = str(text or "")
    compact_text, positions = _compact_with_positions(source)
    if not compact_text:
        return False, False
    positive = False
    negated = False
    for form in keyword_forms(keyword, aliases, variants):
        compact_form = _compact(form)
        if not compact_form:
            continue
        if compact_form.isascii():
            ascii_body = r"\s*".join(re.escape(char) for char in compact_form)
            pattern = re.compile(
                r"(?<![a-z0-9])" + ascii_body + r"(?![a-z0-9])"
            )
            for match in pattern.finditer(source.lower()):
                if _is_negated(source, match.start(), match.end()):
                    negated = True
                else:
                    positive = True
            continue
        else:
            def _occurrences():
                start = 0
                while True:
                    index = compact_text.find(compact_form, start)
                    if index < 0:
                        return
                    yield index, index + len(compact_form)
                    start = index + 1
            spans = _occurrences()
        for start, end in spans:
            if _HANGUL_SHORT.fullmatch(compact_form) and not _short_hangul_boundary_ok(
                compact_text, positions, start, end, source
            ):
                continue
            original_start = positions[start]
            original_end = positions[end - 1] + 1
            if _is_negated(source, original_start, original_end):
                negated = True
            else:
                positive = True
    return positive, negated


def keyword_hit(text: str, keyword: str) -> bool:
    return keyword_match_details(text, keyword)[0]


def negated_keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits = []
    for keyword in keywords:
        value = str(keyword or "").strip()
        if value and keyword_match_details(text, value)[1]:
            hits.append(value)
    return list(dict.fromkeys(hits))
