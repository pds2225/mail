"""소스 상태 관리 — Tier 1 소스의 수집 건전성을 추적한다.

상태: OK / DEGRADED / FAILING / STALE / DISABLED / UNKNOWN
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from mail_core.paths import STATE_DIR

log = logging.getLogger(__name__)

SOURCE_HEALTH_PATH = STATE_DIR / "source_health.json"
SOURCE_INCIDENT_PATH = STATE_DIR / "source_incidents.jsonl"

# 상태 상수
OK = "OK"
DEGRADED = "DEGRADED"
FAILING = "FAILING"
STALE = "STALE"
DISABLED = "DISABLED"
UNKNOWN = "UNKNOWN"

# Tier 1 소스
TIER1_SOURCES = {"bizinfo", "kstartup"}

# 기본 설정
DEFAULT_CONFIG = {
    "failure_threshold": 3,
    "max_staleness_hours": 24,
    "alert_cooldown_hours": 6,
    "degraded_parse_rate": 0.8,
}


def load_source_health() -> dict[str, dict]:
    """소스 상태 파일 로드."""
    if not SOURCE_HEALTH_PATH.exists():
        return {}
    try:
        return json.loads(SOURCE_HEALTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_source_health(data: dict[str, dict]) -> None:
    """소스 상태 파일 저장 (atomic write)."""
    SOURCE_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SOURCE_HEALTH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SOURCE_HEALTH_PATH)


def append_incident(source_id: str, event: str, details: str = "") -> None:
    """장애/복구 이력 append."""
    record = {
        "timestamp": datetime.now().isoformat(),
        "source_id": source_id,
        "event": event,
        "details": details,
    }
    SOURCE_INCIDENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCE_INCIDENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def classify_source_status(
    source_id: str,
    item_count: int,
    parse_rate: float,
    error: str | None = None,
    config: dict | None = None,
    previous_item_count: int | None = None,
) -> str:
    """소스 상태를 판정한다.

    Args:
        source_id: 소스 ID
        item_count: 수집 건수
        parse_rate: 파싱 성공률 (0.0~1.0)
        error: 에러 메시지 (없으면 None)
        config: 설정 (없으면 기본값)
        previous_item_count: 이전 실행 수집 건수 (급감 감지용)

    Returns:
        상태 문자열: OK / DEGRADED / FAILING / STALE / DISABLED / UNKNOWN
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    # 에러가 있으면 FAILING
    if error:
        return FAILING

    # 수집 건수가 0이면 DEGRADED (정상 응답인데 0건)
    if item_count == 0:
        return DEGRADED

    # 파싱률이 기준 미달이면 DEGRADED
    if parse_rate < cfg["degraded_parse_rate"]:
        return DEGRADED

    # B-4: 이전 실행 대비 수집량 급감 감지
    if previous_item_count is not None and previous_item_count > 0:
        drop_ratio = 1.0 - (item_count / previous_item_count)
        if drop_ratio > 0.8:  # 80% 이상 감소
            return DEGRADED

    return OK


def update_source_health(
    source_id: str,
    status: str,
    item_count: int = 0,
    parse_rate: float = 1.0,
    error: str | None = None,
) -> dict:
    """소스 상태를 업데이트하고 상태 전환 시 이력을 기록한다.

    Returns:
        업데이트된 소스 상태 dict
    """
    health = load_source_health()
    prev = health.get(source_id, {})
    prev_status = prev.get("status", UNKNOWN)

    now = datetime.now()
    record = {
        "status": status,
        "last_check": now.isoformat(),
        "item_count": item_count,
        "parse_rate": parse_rate,
    }

    # 상태 전환 시 이력 기록
    if status != prev_status:
        if status == FAILING:
            record["failing_since"] = now.isoformat()
            record["consecutive_failures"] = prev.get("consecutive_failures", 0) + 1
            append_incident(source_id, "FAILING", error or "")
            log.warning("소스 %s 상태 전환: %s → %s", source_id, prev_status, status)
        elif status == OK and prev_status == FAILING:
            record["recovered_at"] = now.isoformat()
            record["consecutive_failures"] = 0
            append_incident(source_id, "RECOVERED", "")
            log.info("소스 %s 복구: %s → %s", source_id, prev_status, status)
        elif status == DEGRADED:
            append_incident(source_id, "DEGRADED", f"parse_rate={parse_rate:.2f}")
    else:
        if status == FAILING:
            record["consecutive_failures"] = prev.get("consecutive_failures", 0) + 1
        else:
            record["consecutive_failures"] = 0

    health[source_id] = {**prev, **record}
    save_source_health(health)
    return health[source_id]


def check_staleness(source_id: str, config: dict | None = None) -> str:
    """소스의 신선도를 확인한다.

    Returns:
        상태 문자열 (STALE이면 stale, 아니면 현재 상태 유지)
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    health = load_source_health()
    record = health.get(source_id, {})

    if not record.get("last_check"):
        return UNKNOWN

    last_check = datetime.fromisoformat(record["last_check"])
    hours_since = (datetime.now() - last_check).total_seconds() / 3600

    if hours_since > cfg["max_staleness_hours"]:
        return STALE

    return record.get("status", UNKNOWN)


def should_alert(source_id: str, config: dict | None = None) -> bool:
    """알림을 보낼지 여부를 결정한다 (쿨다운 적용)."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    health = load_source_health()
    record = health.get(source_id, {})

    if record.get("status") != FAILING:
        return False

    # 쿨다운 확인
    last_alert = record.get("last_alert")
    if last_alert:
        last_alert_time = datetime.fromisoformat(last_alert)
        hours_since = (datetime.now() - last_alert_time).total_seconds() / 3600
        if hours_since < cfg["alert_cooldown_hours"]:
            return False

    # 연속 실패 횟수 확인
    if record.get("consecutive_failures", 0) < cfg["failure_threshold"]:
        return False

    return True


def mark_alerted(source_id: str) -> None:
    """알림 전송 시간을 기록한다."""
    health = load_source_health()
    if source_id in health:
        health[source_id]["last_alert"] = datetime.now().isoformat()
        save_source_health(health)


def get_health_summary() -> dict[str, Any]:
    """전체 소스 상태 요약을 반환한다."""
    health = load_source_health()
    summary = {
        "total": len(health),
        "ok": 0,
        "degraded": 0,
        "failing": 0,
        "stale": 0,
        "disabled": 0,
        "unknown": 0,
        "sources": {},
    }
    for source_id, record in health.items():
        status = record.get("status", UNKNOWN)
        summary[status.lower()] = summary.get(status.lower(), 0) + 1
        summary["sources"][source_id] = {
            "status": status,
            "last_check": record.get("last_check"),
            "item_count": record.get("item_count", 0),
        }
    return summary
