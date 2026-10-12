"""실행 시간 예산 (2026-10, 240분 timeout 근본 수정).

GitHub Actions 발송 step 은 timeout-minutes: 240 이다. 10/7·10/11 실측:
  - 순차 커버리지 감사(fetch_site_coverage)가 접속 불가 사이트마다 ~3분씩 막혀 55→158분,
  - 상세 보강(enrich_items)이 bizinfo 상세 timeout(건당 90~150초)으로 35→155분+,
  - 발송 뒤 필드품질 표본 수집이 bizinfo 재시도로 10분+ → 240분 초과로 step 강제 종료.
→ 수집 단계에 예산을 두고, 초과하면 그때까지 모은 것으로 발송까지 진행한다.

환경변수(분, 0 이하 = 해당 예산 끔):
  MONITOR_COVERAGE_BUDGET_MIN  순차 커버리지 감사 상한(시작 기준)      기본 75
  MONITOR_COLLECT_BUDGET_MIN   수집+상세보강 전체 상한(시작 기준)      기본 150
  MONITOR_POST_SEND_SKIP_MIN   이 시각 이후엔 발송 뒤 부가 계측 생략   기본 180
시작 시각은 프로세스 import 시점(=monitor_runtime/monitor 시작)이다.
"""
from __future__ import annotations

import os
import time

_START = time.monotonic()

DEFAULTS = {
    "MONITOR_COVERAGE_BUDGET_MIN": 75.0,
    "MONITOR_COLLECT_BUDGET_MIN": 150.0,
    "MONITOR_POST_SEND_SKIP_MIN": 180.0,
}


def reset(start: float | None = None) -> None:
    """테스트·엔트리포인트용: 예산 기준 시각을 다시 잡는다."""
    global _START
    _START = time.monotonic() if start is None else float(start)


def elapsed_min() -> float:
    return (time.monotonic() - _START) / 60.0


def budget_min(name: str) -> float:
    raw = os.environ.get(name, "")
    try:
        return float(raw) if str(raw).strip() else DEFAULTS[name]
    except ValueError:
        return DEFAULTS[name]


def remaining_s(name: str) -> float | None:
    """남은 초. 예산이 꺼져 있으면 None."""
    b = budget_min(name)
    if b <= 0:
        return None
    return max(0.0, b * 60.0 - (time.monotonic() - _START))


def exceeded(name: str) -> bool:
    rem = remaining_s(name)
    return rem is not None and rem <= 0
