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


DEFAULT_UNKNOWN_MAX_AGE_DAYS = 30


def filter_watchlist_hits(
    items: list[dict],
    *,
    classify: Callable[[dict], str],
    is_junk: Callable[[dict], bool] | None = None,
    today: date | None = None,
    unknown_max_age_days: int = DEFAULT_UNKNOWN_MAX_AGE_DAYS,
) -> tuple[list[dict], list[dict]]:
    """집중 모니터링 후보에서 지난 공고를 거른다(2026-10). 반환 (keep, dropped).

    - classify(it) == 'closed' (마감일 경과·제목 [마감]/결과발표) → 제외
    - is_junk(it) (결과·채용 등 잡공고) → 제외
    - 마감 불명(classify == 'unknown')이고 posted_date 가 unknown_max_age_days 보다 오래됨 → 제외
      (posted_date 불명이면 유지 — 놓치지 않기 우선)
    판정 함수 예외는 유지 쪽으로 처리한다.
    """
    today = today or date.today()
    keep: list[dict] = []
    dropped: list[dict] = []
    for item in items or []:
        try:
            status = classify(item)
        except Exception:
            status = "unknown"
        try:
            junk = bool(is_junk(item)) if is_junk else False
        except Exception:
            junk = False
        if status == "closed" or junk:
            dropped.append(item)
            continue
        if status == "unknown":
            posted = _parse_posted(item.get("posted_date"))
            if posted is not None and (today - posted).days > int(unknown_max_age_days):
                dropped.append(item)
                continue
        keep.append(item)
    return keep, dropped
