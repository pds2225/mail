"""seen_ids 상한·정렬 — monitor.save_seen_ids / merge_seen_ids 공통.

문제(2026-07-28): MAX_SEEN_IDS=5000 + 알파벳 꼬리 절단이 기업마당 `PBLN_*` 를
파일에서 전부 밀어냈다. `PBLN_000…` 는 정규식이 `00000000` 을 날짜로 오인하거나,
날짜 없을 때 `P…` < `imp_`/`nipa_` 로 정렬되어 `[-5000:]` 에서 탈락한다.
결과: 발송 직후 persist 해도 다음 run 에 다시 NEW 로 잡혀 중복 메일.

정책:
  - 상한을 넉넉히 둔다(일 수집 증가에 여유).
  - 날짜 키는 20xx 만 인정(제로패딩 PBLN 오인 방지).
  - 상한 초과 시 핵심 소스(PBLN/bizinfo/kstartup/nipa/kita)를 비핵심보다 우선 보존.
"""
from __future__ import annotations

import re
from typing import Iterable

# 일 수집·다소스 누적에 여유. 5000 은 2026-07 실측으로 이미 포화했다.
MAX_SEEN_IDS = 50_000

# 날짜 없는 id 가 잘릴 때에도 전국 종합공고 소스는 우선 남긴다.
CORE_SEEN_PREFIXES: tuple[str, ...] = (
    "PBLN_",
    "pbln_",
    "bizinfo_",
    "kstartup_",
    "nipa_",
    "kita_",
)

# YYYY-MM-DD 또는 YYYYMMDD — 연도는 20xx 만 (PBLN_00000000… 오인 방지)
_SEEN_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2}|20\d{6})")


def seen_id_sort_key(value: str) -> str:
    """날짜 포함 id 는 날짜키, 그 외는 원문(안정 정렬)."""
    text = str(value or "")
    match = _SEEN_DATE_RE.search(text)
    return match.group(1) if match else text


def _is_core_seen_id(value: str) -> bool:
    return str(value or "").startswith(CORE_SEEN_PREFIXES)


def _sorted_seen_ids(values: Iterable[str]) -> list[str]:
    """날짜키가 같은 ID도 원문으로 tie-break해 실행마다 같은 JSON을 만든다."""
    return sorted(values, key=lambda item: (seen_id_sort_key(item), item))


def prune_seen_ids(
    ids: Iterable[str],
    *,
    max_keep: int = MAX_SEEN_IDS,
) -> list[str]:
    """합집합/저장 직전 상한 적용. 핵심 소스 id 를 비핵심보다 우선 보존."""
    unique = {str(x) for x in ids if x}
    limit = max(1, int(max_keep))
    if len(unique) <= limit:
        return _sorted_seen_ids(unique)

    core = {item for item in unique if _is_core_seen_id(item)}
    other = unique - core
    if len(core) >= limit:
        # 핵심만으로도 초과 — 날짜/문자 키 기준 최신 쪽을 남긴다.
        return _sorted_seen_ids(core)[-limit:]

    remain = limit - len(core)
    other_kept = _sorted_seen_ids(other)[-remain:] if remain else []
    return _sorted_seen_ids(core | set(other_kept))
