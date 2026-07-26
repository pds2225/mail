"""워치리스트 매칭 결과 선별 — 게시판 URL 전체 매칭 폭발을 막는다.

문제(2026-07-26): RIPC·수출바우처 게시판 URL 이 워치리스트에 있으면
해당 보드의 공고 전량(날짜 무관)이 강제포함되어 74건 집중메일·푸시가 발생.

정책:
  - 키워드 매칭: 우선 유지(놓치면 안 되는 신호)
  - URL(게시판) 매칭: 최근 N일 이내 posted_date 만 (날짜불명은 별도 소량 캡)
  - 전체 max_items 상한(기본 20)
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable


DEFAULT_MAX_ITEMS = 20
DEFAULT_URL_MAX_AGE_DAYS = 14
DEFAULT_URL_UNKNOWN_CAP = 5


def _parse_posted(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _sort_key(item: dict, today: date) -> tuple:
    """최신 posted_date 우선, 날짜불명은 뒤로."""
    posted = _parse_posted(item.get("posted_date"))
    if posted is None:
        return (1, 10**6, str(item.get("id") or ""))
    age = (today - posted).days
    return (0, age, str(item.get("id") or ""))


def select_watchlist_hits(
    items: list[dict],
    *,
    match_kind: Callable[[dict], str],
    max_items: int = DEFAULT_MAX_ITEMS,
    url_max_age_days: int = DEFAULT_URL_MAX_AGE_DAYS,
    url_unknown_cap: int = DEFAULT_URL_UNKNOWN_CAP,
    today: date | None = None,
) -> list[dict]:
    """매칭 공고를 종류·날짜·상한으로 선별. match_kind 는 ''|'keyword'|'url'."""
    today = today or date.today()
    max_items = max(0, int(max_items))
    if max_items == 0:
        return []

    keyword_hits: list[dict] = []
    url_recent: list[dict] = []
    url_unknown: list[dict] = []
    seen_ids: set[str] = set()

    for item in items or []:
        if not item:
            continue
        kind = match_kind(item)
        if kind not in {"keyword", "url"}:
            continue
        iid = str(item.get("id") or "")
        if iid and iid in seen_ids:
            continue
        if iid:
            seen_ids.add(iid)

        if kind == "keyword":
            keyword_hits.append(item)
            continue

        posted = _parse_posted(item.get("posted_date"))
        if posted is None:
            url_unknown.append(item)
            continue
        age = (today - posted).days
        if 0 <= age <= int(url_max_age_days):
            url_recent.append(item)

    keyword_hits.sort(key=lambda it: _sort_key(it, today))
    url_recent.sort(key=lambda it: _sort_key(it, today))
    url_unknown.sort(key=lambda it: _sort_key(it, today))

    selected: list[dict] = []
    selected.extend(keyword_hits[:max_items])
    remain = max_items - len(selected)
    if remain > 0:
        selected.extend(url_recent[:remain])
    remain = max_items - len(selected)
    if remain > 0:
        selected.extend(url_unknown[: min(remain, int(url_unknown_cap))])
    return selected


def watchlist_limits_from_config(watchlist: dict | None) -> dict[str, int]:
    """watchlist.json 선택 필드 → 선별 한도."""
    raw = watchlist if isinstance(watchlist, dict) else {}

    def _int(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "max_items": _int("max_items", DEFAULT_MAX_ITEMS),
        "url_max_age_days": _int("url_max_age_days", DEFAULT_URL_MAX_AGE_DAYS),
        "url_unknown_cap": _int("url_unknown_cap", DEFAULT_URL_UNKNOWN_CAP),
    }
