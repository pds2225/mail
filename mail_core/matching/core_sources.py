"""핵심 소스(기업마당·K-Startup) 수집·분류 특화.

이 두 사이트는 매일 digest 의 주력 공급원이다, 일반 소스와 같은
상세보강 상한(40)·느슨한 탐지 임계를 쓰면 분류 신호가 부족해진다.

역할(순수·monitor import 없음):
  - 핵심 소스 판별
  - 기업마당 API 부가필드를 구조화 키로 승격
  - K-Startup 목록 flag → support_field 조기 부여
  - 상세 보강 대상 선별(핵심 우선·더 큰 예산)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

CORE_SOURCE_IDS = frozenset({"bizinfo", "kstartup"})
CORE_SOURCE_HOSTS = ("bizinfo.go.kr", "k-startup.go.kr")
CORE_SOURCE_MARKERS = (
    "기업마당", "bizinfo", "k-startup", "kstartup", "K-Startup",
)

# 상세 보강 예산 — 핵심은 넓게, 그 외 전용호스트는 기존 40 유지
CORE_MAX_DETAIL_ENRICH = 150
OTHER_SPECIALIZED_DETAIL_ENRICH = 40
# 최근 게시분 우선 보강(메일 대상에 가까운 공고)
CORE_ENRICH_RECENT_DAYS = 21

# 기업마당 API(직결·data.go.kr)에서 종종 오는 부가필드 → 구조화 키
# 픽스처에는 없을 수 있으나, 실응답에 있으면 상세 fetch 전에 분류에 쓴다.
BIZINFO_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "support_field": (
        "pldirSportRealmLclasCodeNm",
        "pldirSportRealmMlsfcCodeNm",
        "hashtags",
        "hashTag",
        "hashTags",
        "sportRealmLclasCodeNm",
    ),
    "target_field": (
        "trgetNm",
        "trget",
        "applTrgetCn",
        "aplyTrgetCn",
    ),
    "region_field": (
        "jrsdAreaNm",
        "areaNm",
        "rgnNm",
        "rgnLclsfNm",
    ),
}

# 목록 flag / 지원분야 문자열 → 지원유형 (기존 SUPPORT_TYPE_RULES 버킷만)
LIST_CATEGORY_TO_SUPPORT: dict[str, str] = {
    "사업화": "지원금/바우처",
    "정책자금": "지원금/바우처",
    "융자": "지원금/바우처",
    "보증": "지원금/바우처",
    "기술개발": "지원금/바우처",
    "r&d": "지원금/바우처",
    "팁스": "지원금/바우처",
    "tips": "지원금/바우처",
    "수출": "지원금/바우처",
    "글로벌": "지원금/바우처",
    "투자": "투자",
    "멘토링": "컨설팅·교육·상담",
    "컨설팅": "컨설팅·교육·상담",
    "교육": "컨설팅·교육·상담",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def is_core_source_item(item: dict | None) -> bool:
    """링크·출처·id 로 기업마당/K-Startup 공고인지 판별."""
    if not isinstance(item, dict):
        return False
    if item.get("core_source") in CORE_SOURCE_IDS:
        return True
    link = _norm(item.get("link") or item.get("url")).lower()
    if any(host in link for host in CORE_SOURCE_HOSTS):
        return True
    iid = _norm(item.get("id")).lower()
    if iid.startswith("bizinfo_") or iid.startswith("kstartup_") or iid.startswith("pbln_"):
        return True
    source = _norm(item.get("source"))
    return any(m.lower() in source.lower() for m in CORE_SOURCE_MARKERS)


def _first_alias(raw: dict, keys: Iterable[str]) -> str:
    for key in keys:
        val = _norm(raw.get(key))
        if val:
            return val
    return ""


def attach_bizinfo_structured(item: dict, raw: dict | None) -> dict:
    """API 원본 부가필드를 구조화 키로 승격(이미 있으면 유지)."""
    out = dict(item)
    out["core_source"] = "bizinfo"
    raw = raw if isinstance(raw, dict) else {}
    for field, aliases in BIZINFO_FIELD_ALIASES.items():
        if _norm(out.get(field)):
            continue
        found = _first_alias(raw, aliases)
        if found:
            out[field] = found
    return out


def attach_kstartup_list_structured(
    item: dict,
    *,
    flag_text: str = "",
    clss: str = "",
) -> dict:
    """목록 카드에서 분류 신호를 조기 부여(상세 보강 전에도 지원유형·키워드 매칭)."""
    out = dict(item)
    out["core_source"] = "kstartup"
    if clss:
        out["kstartup_class"] = clss  # PBC010 공공 / PBC020 민간
        out["kstartup_sector"] = (
            "공공" if clss == "PBC010" else ("민간" if clss == "PBC020" else clss)
        )
    flag = _norm(flag_text)
    if flag and not _norm(out.get("support_field")):
        out["support_field"] = flag
    if flag and not _norm(out.get("description")):
        out["description"] = flag
    return out


def map_category_to_support_types(text: str) -> list[str]:
    """목록/지원분야 문자열 → 지원유형 버킷(복수 가능)."""
    low = _norm(text).lower()
    if not low:
        return []
    matched: list[str] = []
    for kw, bucket in LIST_CATEGORY_TO_SUPPORT.items():
        if kw in low and bucket not in matched:
            matched.append(bucket)
    return matched


def _parse_posted(value: Any) -> date | None:
    text = _norm(value)[:10]
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _enrich_sort_key(item: dict, today: date) -> tuple:
    """최근 게시일 우선, 날짜불명은 뒤로."""
    posted = _parse_posted(item.get("posted_date"))
    if posted is None:
        return (1, 10**6, _norm(item.get("id")))
    age = (today - posted).days
    recent = 0 if 0 <= age <= CORE_ENRICH_RECENT_DAYS else 1
    return (recent, age if age >= 0 else 10**6, _norm(item.get("id")))


def select_detail_enrich_targets(
    items: list[dict],
    *,
    specialized_hosts: tuple[str, ...] | list[str],
    core_limit: int = CORE_MAX_DETAIL_ENRICH,
    other_limit: int = OTHER_SPECIALIZED_DETAIL_ENRICH,
    today: date | None = None,
) -> list[dict]:
    """전용 호스트 상세보강 대상 — 핵심 소스 우선·최근게시 우선·예산 분리."""
    today = today or date.today()
    hosts = tuple(specialized_hosts or ())
    core: list[dict] = []
    other: list[dict] = []
    for it in items or []:
        if not it or it.get("detail_enriched"):
            continue
        link = _norm(it.get("link") or it.get("url")).lower()
        if not any(h in link for h in hosts):
            continue
        if is_core_source_item(it) or any(h in link for h in CORE_SOURCE_HOSTS):
            core.append(it)
        else:
            other.append(it)
    core.sort(key=lambda it: _enrich_sort_key(it, today))
    other.sort(key=lambda it: _enrich_sort_key(it, today))
    return core[: max(0, int(core_limit))] + other[: max(0, int(other_limit))]


def keyword_extra_parts(item: dict) -> list[str]:
    """핵심 소스 키워드 매칭용 추가 필드(주관기관명 제외 — 오매칭 방지)."""
    if not is_core_source_item(item):
        return []
    parts: list[str] = []
    for key in (
        "region_field",
        "business_age_text",
        "target_age_field",
        "exclude_target_field",
        "kstartup_sector",
    ):
        val = _norm(item.get(key))
        if val:
            parts.append(val)
    return parts
