"""발송 멱등 완료 시 수집 생략 게이트.

주말 재실행·이미 발송된 기준일 재실행이 2시간+ 수집을 반복하는 낭비를 막는다.
(2026-07-26: 기준일 2026-07-24 전 그룹 멱등 skip 인데도 수집 풀 수행)
"""
from __future__ import annotations

import os
from typing import Iterable

from mail_core.delivery import state as delivery_state


def env_skip_if_delivered_enabled() -> bool:
    """MONITOR_SKIP_IF_DELIVERED 기본 on. '0'/'false'/'no' 이면 끔."""
    raw = str(os.environ.get("MONITOR_SKIP_IF_DELIVERED", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def planned_delivery_units(
    *,
    target_date: str,
    groups: list[dict] | None,
    settings: dict | None = None,
    watchlist: dict | None = None,
    include_raw_all: bool = False,
) -> list[tuple[str, str, str, str]]:
    """이번 run 이 발송할 (date, tenant, group, recipient) 목록.

    수신자가 비어 있는 그룹은 제외(발송 단위가 아님).
    """
    settings = settings if isinstance(settings, dict) else {}
    watchlist = watchlist if isinstance(watchlist, dict) else {}
    date_s = str(target_date or "").strip()
    units: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def _add(tenant: str, group: str, recipient: str) -> None:
        recip = (recipient or "").strip().lower()
        if not recip or "@" not in recip:
            return
        key = (date_s, tenant, group, recip)
        if key in seen:
            return
        seen.add(key)
        units.append(key)

    for group in groups or []:
        if not isinstance(group, dict) or not group.get("active", True):
            continue
        gid = str(group.get("id") or group.get("name") or "").strip()
        if not gid:
            continue
        tenant = str(group.get("tenant_id") or settings.get("tenant_id") or "default")
        for recip in group.get("recipients") or []:
            _add(tenant, gid, str(recip))

    wl_recips = list(watchlist.get("recipients") or [])
    if not wl_recips:
        wl_recips = list(settings.get("raw_all_recipients") or [])
    if watchlist.get("keywords") or watchlist.get("urls"):
        tenant = str(watchlist.get("tenant_id") or settings.get("tenant_id") or "default")
        for recip in wl_recips:
            _add(tenant, "watchlist", str(recip))

    if include_raw_all and settings.get("raw_all_enabled", True):
        tenant = str(settings.get("tenant_id") or "default")
        for recip in settings.get("raw_all_recipients") or []:
            _add(tenant, "raw_all", str(recip))

    return units


def units_to_keys(units: Iterable[tuple[str, str, str, str]]) -> list[str]:
    return [
        delivery_state.key(date_s, group, recip, tenant=tenant)
        for date_s, tenant, group, recip in units
    ]


def all_units_delivered(
    delivered: set[str],
    units: list[tuple[str, str, str, str]],
) -> bool:
    """계획된 발송 단위가 1개 이상이고 전부 멱등 완료면 True."""
    if not units:
        return False
    for date_s, tenant, group, recip in units:
        dkey = delivery_state.key(date_s, group, recip, tenant=tenant)
        legacy = delivery_state.legacy_key(date_s, group, recip)
        if dkey not in delivered and legacy not in delivered:
            return False
    return True


def should_skip_fetch_already_delivered(
    *,
    target_date: str,
    groups: list[dict] | None,
    settings: dict | None = None,
    watchlist: dict | None = None,
    include_raw_all: bool = False,
    delivered: set[str] | None = None,
    delivery_path: str | os.PathLike | None = None,
    enabled: bool | None = None,
) -> dict:
    """수집 생략 여부. enabled 기본은 env.

    반환: {"skip": bool, "reason": str, "units": int, "target_date": str}
    """
    if enabled is None:
        enabled = env_skip_if_delivered_enabled()
    if not enabled:
        return {"skip": False, "reason": "disabled", "units": 0, "target_date": str(target_date)}

    units = planned_delivery_units(
        target_date=target_date,
        groups=groups,
        settings=settings,
        watchlist=watchlist,
        include_raw_all=include_raw_all,
    )
    if not units:
        return {
            "skip": False,
            "reason": "no_planned_units",
            "units": 0,
            "target_date": str(target_date),
        }

    if delivered is None:
        if delivery_path is None:
            return {
                "skip": False,
                "reason": "no_delivery_state",
                "units": len(units),
                "target_date": str(target_date),
            }
        delivered = delivery_state.load(delivery_path)

    if all_units_delivered(delivered, units):
        return {
            "skip": True,
            "reason": "already_delivered",
            "units": len(units),
            "target_date": str(target_date),
        }
    return {
        "skip": False,
        "reason": "pending_units",
        "units": len(units),
        "target_date": str(target_date),
    }
