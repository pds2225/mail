"""커버리지 이상탐지 — 순수 로직 모듈 (monitor import 부작용 회피).

목적: "평소 N건 수집되던 사이트가 오늘 0건/급감/수집실패하면" 폰 알림으로 잡아,
라이브 사이트가 조용히 바뀌어 공고를 놓치는 사고를 사전에 감지한다.

설계 원칙:
  - 순수·오프라인 테스트 가능: monitor 를 import 하지 않는다(import 시 env 요구 회피).
  - 보수적 판정(오탐 최소): baseline 이력이 있을 때만 비교하고, 첫 실행/신규 사이트는
    절대 알림하지 않는다. 수집 실패한 날은 baseline 에 반영하지 않아 오염을 막는다.
  - BASE_DIR 는 monitor.py 와 동일 규칙(파일 위치 기준)으로 독립 계산한다.
"""
from __future__ import annotations

import json
import statistics
from datetime import date
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
COVERAGE_BASELINE_PATH = BASE_DIR / "coverage_baseline.json"


# ── baseline 입출력 ──────────────────────────────────────────────────────────
def load_coverage_baseline(path: Path = COVERAGE_BASELINE_PATH) -> dict:
    """baseline(site_id -> 과거 item_count 리스트) 로드. 없거나 깨졌으면 빈 dict."""
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_coverage_baseline(data: dict, path: Path = COVERAGE_BASELINE_PATH) -> None:
    """baseline 저장(원자적 쓰기). 실패해도 예외를 올리지 않는다(본 작업 무영향)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


# ── 대표값 ──────────────────────────────────────────────────────────────────
def _history_count(entry: Any) -> int | float | None:
    """legacy 숫자 이력과 날짜 포함 이력에서 item_count 를 꺼낸다."""
    if isinstance(entry, (int, float)):
        return entry
    if isinstance(entry, dict):
        count = entry.get("item_count")
        if isinstance(count, (int, float)):
            return count
    return None


def _history_date(entry: Any) -> str:
    """날짜 포함 이력의 수집일(YYYY-MM-DD). legacy 숫자 이력은 날짜 없음."""
    if isinstance(entry, dict):
        value = entry.get("date")
        return value if isinstance(value, str) else ""
    return ""


def _history_entry(item_count: int, day: str) -> dict[str, Any]:
    return {"date": day, "item_count": item_count}


def _representative(history: list) -> float:
    """과거 이력의 대표값. 장애성 0건에 덜 오염되도록 양수 이력을 우선한다."""
    nums = [
        count
        for count in (_history_count(entry) for entry in history)
        if count is not None
    ]
    positives = [n for n in nums if n > 0]
    nums = positives or nums
    if not nums:
        return 0.0
    return float(statistics.median(nums))


# ── 탐지 ────────────────────────────────────────────────────────────────────
def detect_coverage_anomalies(
    rows: list[dict],
    baseline: dict,
    *,
    min_healthy: int = 1,
    drop_ratio: float = 0.5,
    floor: int = 2,
) -> list[dict]:
    """오늘 coverage rows 와 baseline 을 비교해 이상(급락·수집실패·급감)을 추려 반환.

    enabled=True 인 사이트만, 그리고 baseline 이력이 있는 사이트만 비교한다
    (이력 없으면 신규로 보고 알림하지 않음 — 첫 실행 오탐 방지).

    판정(대표값 = median(history)):
      - 대표값>=min_healthy 인데 fetch_success & item_count==0  → high "0건 급락"
      - baseline 이력이 있는데 수집 실패(not fetch_success/fetch_error) → high "수집실패"
      - 대표값>=floor 인데 0<item_count<대표값*drop_ratio        → medium "급감"
    """
    anomalies: list[dict] = []
    for row in rows or []:
        if not row.get("enabled", True):
            continue
        site_id = row.get("site_id", "")
        history = baseline.get(site_id)
        if not isinstance(history, list) or not history:
            continue  # 신규/이력없음 → 알림 안 함
        item_count = row.get("item_count", 0) or 0
        fetch_success = bool(row.get("fetch_success"))
        fetch_error = row.get("fetch_error") or ""
        rep = _representative(history)

        anomaly: dict[str, Any] | None = None
        if not fetch_success or fetch_error:
            anomaly = {"reason": "수집실패", "severity": "high"}
        elif rep >= min_healthy and fetch_success and item_count == 0:
            anomaly = {"reason": "0건 급락", "severity": "high"}
        elif rep >= floor and item_count > 0 and item_count < rep * drop_ratio:
            anomaly = {"reason": "급감", "severity": "medium"}

        if anomaly:
            anomaly.update({
                "site_id": site_id,
                "site_name": row.get("site_name", ""),
                "baseline": rep,
                "current": item_count,
                "url": row.get("url", ""),
            })
            anomalies.append(anomaly)
    return anomalies


# ── baseline 갱신 ────────────────────────────────────────────────────────────
def update_coverage_baseline(
    baseline: dict,
    rows: list[dict],
    *,
    window: int = 14,
    today: str | None = None,
) -> dict:
    """fetch_success 이면서 이상치가 아닌 사이트만 오늘 item_count 를 롤링 이력에 반영한다.

    실패·급락·급감한 날은 추가하지 않아 baseline 오염을 막고, 같은 날짜 재실행은 append 대신
    마지막 값을 교체해 window 가 날짜 단위로 유지되게 한다.
    """
    updated = dict(baseline) if isinstance(baseline, dict) else {}
    anomalous_site_ids = {
        anomaly.get("site_id")
        for anomaly in detect_coverage_anomalies(rows, updated)
        if anomaly.get("site_id")
    }
    day = today or date.today().isoformat()
    for row in rows or []:
        if not row.get("enabled", True):
            continue
        if not row.get("fetch_success"):
            continue
        site_id = row.get("site_id", "")
        if not site_id:
            continue
        if site_id in anomalous_site_ids:
            continue
        history = updated.get(site_id)
        history = list(history) if isinstance(history, list) else []
        item_count = int(row.get("item_count", 0) or 0)
        entry = _history_entry(item_count, day)
        if history and _history_date(history[-1]) == day:
            history[-1] = entry
        else:
            history.append(entry)
        updated[site_id] = history[-window:]
    return updated


# ── 메시지 포맷 ──────────────────────────────────────────────────────────────
def format_anomaly_message(anomalies: list[dict]) -> str:
    """high 우선 정렬 후 사이트명·reason·(baseline→current) 간결 요약. (title 은 호출부에서)."""
    if not anomalies:
        return "수집 이상 없음"
    order = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(
        anomalies,
        key=lambda a: (order.get(a.get("severity", "low"), 3), -float(a.get("baseline", 0))),
    )
    lines: list[str] = []
    for a in ordered:
        sev = a.get("severity", "")
        mark = "🔴" if sev == "high" else ("🟡" if sev == "medium" else "•")
        name = a.get("site_name") or a.get("site_id", "")
        base = a.get("baseline", 0)
        base_s = f"{base:g}" if isinstance(base, (int, float)) else str(base)
        lines.append(f"{mark} {name}: {a.get('reason', '')} (평소 {base_s}→오늘 {a.get('current', 0)}건)")
    return "\n".join(lines)
