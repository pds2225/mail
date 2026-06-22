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
def _representative(history: list) -> float:
    """과거 이력의 대표값. 일시적 스파이크에 둔감하도록 중앙값(median) 사용."""
    nums = [n for n in history if isinstance(n, (int, float))]
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
      - 대표값>=min_healthy 인데 수집 실패(not fetch_success/fetch_error) → high "수집실패"
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
        rep = _representative(history)
        if rep <= 0:
            continue
        item_count = row.get("item_count", 0) or 0
        fetch_success = bool(row.get("fetch_success"))
        fetch_error = row.get("fetch_error") or ""

        anomaly: dict[str, Any] | None = None
        if rep >= min_healthy and (not fetch_success or fetch_error):
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
) -> dict:
    """fetch_success 인 사이트만 오늘 item_count 를 롤링 리스트에 append(최대 window).

    실패한 날은 추가하지 않아 baseline 오염을 막는다(실패 0건이 정상으로 학습되는 것 방지).
    """
    updated = dict(baseline) if isinstance(baseline, dict) else {}
    for row in rows or []:
        if not row.get("enabled", True):
            continue
        if not row.get("fetch_success"):
            continue
        site_id = row.get("site_id", "")
        if not site_id:
            continue
        history = updated.get(site_id)
        history = list(history) if isinstance(history, list) else []
        history.append(int(row.get("item_count", 0) or 0))
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
