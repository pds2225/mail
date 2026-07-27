"""누락 탐지 후속조치 — 발송 필터·수동큐·재시도 계획 (순수, monitor import 없음).

W2: send_hold 소비·P0 소스 아이템 제외·manual_queue enqueue/ack.
실제 HTTP 재수집은 호출측(monitor)이 plan 을 보고 수행한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mail_core.paths import STATE_DIR

MANUAL_QUEUE_PATH = STATE_DIR / "miss_manual_queue.json"
DEFAULT_AUTO_RETRY = 2
DEFAULT_BACKOFF_SEC = (60, 180)


def p0_site_ids(reports: list[dict] | None) -> set[str]:
    return {
        str(r.get("site_id") or "")
        for r in (reports or [])
        if r.get("risk_level") == "P0" and r.get("site_id")
    }


def p0_site_names(reports: list[dict] | None) -> set[str]:
    return {
        str(r.get("site_name") or "")
        for r in (reports or [])
        if r.get("risk_level") == "P0" and r.get("site_name")
    }


def item_belongs_to_p0(item: dict, *, p0_ids: set[str], p0_names: set[str]) -> bool:
    """공고가 P0 소스 소속인지. site_id · id 접두를 우선, 이름은 비접두 id 만.

    동일 display name 을 쓰는 보드가 여럿 있다(예: 정부24×6). source 이름만으로
    제외하면 정상 sibling 보드 공고까지 발송 후보에서 빠지므로, site_id 가 있거나
    `{site_id}_…` id 접두로 소속을 알 수 있으면 이름 매칭을 쓰지 않는다.
    """
    if not item:
        return False
    sid = str(item.get("site_id") or "").strip()
    if sid:
        return sid in p0_ids

    iid = str(item.get("id") or "")
    for pid in p0_ids:
        if pid and (iid == pid or iid.startswith(f"{pid}_")):
            return True

    # id 가 이미 site_id 접두 형태면(다른 보드 소속) 공유 display name 으로 제외하지 않음
    if iid and "_" in iid:
        return False

    src = str(item.get("source") or "").strip()
    return bool(src and src in p0_names)


def drop_items_from_p0_sources(
    items: list[dict] | None,
    reports: list[dict] | None,
) -> tuple[list[dict], list[dict]]:
    """P0 소스 공고를 발송 후보에서 분리. (kept, dropped) 반환."""
    ids = p0_site_ids(reports)
    names = p0_site_names(reports)
    if not ids and not names:
        return list(items or []), []
    kept: list[dict] = []
    dropped: list[dict] = []
    for it in items or []:
        if item_belongs_to_p0(it, p0_ids=ids, p0_names=names):
            dropped.append(it)
        else:
            kept.append(it)
    return kept, dropped


def effective_allow_send(
    allow_send: bool,
    *,
    send_hold: bool,
    shadow: bool | None = None,
    force_allow: bool | None = None,
) -> tuple[bool, str]:
    """send_hold 시 실발송 여부. (effective_allow_send, reason).

    shadow / force_allow 인자가 None 이면 환경변수 사용:
      MONITOR_SEND_HOLD_SHADOW=1 → 보류 로그만, 발송 계속
      MONITOR_ALLOW_SEND_ON_FAILED=1 → 강제 발송 허용
    """
    if not allow_send:
        return False, "allow_send_false"
    if not send_hold:
        return True, "ok"
    if force_allow is None:
        force_allow = os.environ.get("MONITOR_ALLOW_SEND_ON_FAILED", "") in (
            "1", "true", "True")
    if force_allow:
        return True, "override_ALLOW_SEND_ON_FAILED"
    if shadow is None:
        shadow = os.environ.get("MONITOR_SEND_HOLD_SHADOW", "") in (
            "1", "true", "True")
    if shadow:
        return True, "shadow_SEND_HOLD"
    return False, "send_hold_RUN_FAILED"


def load_manual_queue(path: Path | None = None) -> dict[str, Any]:
    target = path or MANUAL_QUEUE_PATH
    try:
        if not target.exists():
            return {"items": []}
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"items": []}
        items = data.get("items")
        if not isinstance(items, list):
            items = []
        return {"items": items}
    except Exception:
        return {"items": []}


def save_manual_queue(queue: dict[str, Any], path: Path | None = None) -> bool:
    target = path or MANUAL_QUEUE_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": list(queue.get("items") or [])}
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(target)
        return True
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enqueue_manual(
    queue: dict[str, Any],
    *,
    site_id: str,
    site_name: str = "",
    reason_codes: list[str] | None = None,
    risk_level: str = "P0",
    note: str = "",
    subtype: str = "COLLECTION",
) -> dict[str, Any]:
    """수동 확인 큐에 항목 추가(동일 site_id+open 이면 갱신)."""
    items = list(queue.get("items") or [])
    entry = {
        "id": f"{site_id}:{_now_iso()}",
        "site_id": site_id,
        "site_name": site_name,
        "reason_codes": list(reason_codes or []),
        "risk_level": risk_level,
        "subtype": subtype,
        "note": note[:200],
        "status": "open",
        "created_at": _now_iso(),
        "resolution": "",
        "resolved_at": "",
    }
    # 동일 site_id open 건이 있으면 덮어쓰기(중복 방지)
    replaced = False
    for i, old in enumerate(items):
        if old.get("site_id") == site_id and old.get("status") == "open":
            entry["id"] = old.get("id") or entry["id"]
            entry["created_at"] = old.get("created_at") or entry["created_at"]
            items[i] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    return {"items": items}


def enqueue_p0_from_reports(
    reports: list[dict] | None,
    path: Path | None = None,
) -> int:
    """P0 소스를 manual_queue 에 넣고 저장. 추가/갱신 건수 반환."""
    queue = load_manual_queue(path)
    n = 0
    for r in reports or []:
        if r.get("risk_level") != "P0":
            continue
        sid = str(r.get("site_id") or "")
        if not sid:
            continue
        queue = enqueue_manual(
            queue,
            site_id=sid,
            site_name=str(r.get("site_name") or ""),
            reason_codes=list(r.get("reason_codes") or []),
            risk_level="P0",
            note=str((r.get("detail") or {}).get("fetch_error") or "")[:200],
            subtype="COLLECTION",
        )
        n += 1
    if n:
        save_manual_queue(queue, path)
    return n


def ack_manual(
    queue: dict[str, Any],
    entry_id: str,
    resolution: str,
) -> dict[str, Any]:
    """resolution: ack | false_alarm | fixed."""
    if resolution not in {"ack", "false_alarm", "fixed"}:
        resolution = "ack"
    items = []
    for it in queue.get("items") or []:
        row = dict(it)
        if row.get("id") == entry_id and row.get("status") == "open":
            row["status"] = "closed"
            row["resolution"] = resolution
            row["resolved_at"] = _now_iso()
        items.append(row)
    return {"items": items}


def plan_retries(
    p0_sources: list[dict] | None,
    *,
    auto_retry: int = DEFAULT_AUTO_RETRY,
    backoff_sec: tuple[int, ...] | list[int] = DEFAULT_BACKOFF_SEC,
) -> list[dict[str, Any]]:
    """재시도 대상 계획. FETCH/PARSER/CONTENT 계열만."""
    retryable = {
        "FETCH_FAILED", "PARSER_FAILED", "CONTENT_VALIDATION_FAILED",
        "SOURCE_NOT_EXECUTED",
    }
    plans: list[dict[str, Any]] = []
    for r in p0_sources or []:
        codes = set(r.get("reason_codes") or [])
        if not (codes & retryable):
            continue
        sid = str(r.get("site_id") or "")
        if not sid:
            continue
        plans.append({
            "site_id": sid,
            "site_name": r.get("site_name", ""),
            "reason_codes": list(r.get("reason_codes") or []),
            "max_attempts": int(auto_retry),
            "backoff_sec": list(backoff_sec)[: int(auto_retry)],
            "attempt": 0,
        })
    return plans


def enqueue_extraction_failures(
    items: list[dict] | None,
    path: Path | None = None,
) -> int:
    """추출 실패(PARSE/FETCH) 공고를 manual_queue 에 subtype 분리 enqueue.

    수집 P0(COLLECTION)와 혼동하지 않도록 subtype=PARSE_FAILED|DETAIL_FETCH_FAILED.
    NOT_SPECIFIED 는 큐에 넣지 않는다.
    """
    from mail_core.operations.field_status import (
        DETAIL_FETCH_FAILED,
        PARSE_FAILED,
        plan_extraction_retries,
    )

    plans = plan_extraction_retries(items)
    if not plans:
        return 0
    by_id = {
        str(it.get("id") or ""): it
        for it in (items or [])
        if isinstance(it, dict) and it.get("id")
    }
    queue = load_manual_queue(path)
    n = 0
    for plan in plans:
        iid = str(plan.get("item_id") or "")
        subtype = str(plan.get("subtype") or "")
        if subtype not in {PARSE_FAILED, DETAIL_FETCH_FAILED}:
            continue
        it = by_id.get(iid) or {}
        sid = str(it.get("site_id") or it.get("source") or iid or "unknown")
        items_q = list(queue.get("items") or [])
        entry = {
            "id": f"{sid}::{iid}::{subtype}:{_now_iso()}",
            "site_id": sid,
            "site_name": str(it.get("source") or it.get("site_name") or ""),
            "notice_id": iid,
            "notice_url": str(plan.get("url") or ""),
            "reason_codes": [subtype],
            "risk_level": "P1",
            "subtype": subtype,
            "note": str(it.get("title") or "")[:200],
            "status": "open",
            "created_at": _now_iso(),
            "resolution": "",
            "resolved_at": "",
        }
        replaced = False
        for i, old in enumerate(items_q):
            if (
                old.get("site_id") == sid
                and old.get("notice_id") == iid
                and old.get("subtype") == subtype
                and old.get("status") == "open"
            ):
                entry["id"] = old.get("id") or entry["id"]
                entry["created_at"] = old.get("created_at") or entry["created_at"]
                items_q[i] = entry
                replaced = True
                break
        if not replaced:
            items_q.append(entry)
        queue = {"items": items_q}
        n += 1
    if n:
        save_manual_queue(queue, path)
    return n


def apply_extraction_rate_to_reports(
    reports: list[dict] | None,
    rates_by_site: dict[str, dict] | None,
) -> list[dict]:
    """소스 리포트에 extraction_rates 를 주입하고 DETAIL_EXTRACT_RATE_LOW 를 반영."""
    out: list[dict] = []
    rates_by_site = rates_by_site or {}
    for r in reports or []:
        row = dict(r)
        sid = str(row.get("site_id") or "")
        rates = rates_by_site.get(sid)
        if rates:
            row["extraction_rates"] = rates
            codes = list(row.get("reason_codes") or [])
            for code in rates.get("reason_codes") or []:
                if code not in codes:
                    codes.append(code)
            row["reason_codes"] = codes
            # 기존 P0 를 낮추지 않음. 추출률만으로 P0 승격은 rates.risk_level 이 P0 일 때.
            existing = str(row.get("risk_level") or "")
            new_risk = str(rates.get("risk_level") or "")
            if new_risk == "P0" and existing != "P0":
                row["risk_level"] = "P0"
            elif new_risk == "P1" and existing not in {"P0", "P1"}:
                row["risk_level"] = "P1"
                if row.get("status") == "SUCCESS":
                    row["status"] = "PARTIAL"
        out.append(row)
    return out
