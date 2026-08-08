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

from mail_core.paths import STATE_DIR

COVERAGE_BASELINE_PATH = STATE_DIR / "coverage_baseline.json"


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

    실패·급락·품질 이상·비정상 급증일은 추가하지 않아 baseline 오염을 막고,
    같은 날짜 재실행은 append 대신 마지막 값을 교체해 window 가 날짜 단위로 유지되게 한다.
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
        if _row_has_baseline_pollution(row, updated.get(site_id)):
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


# ══════════════════════════════════════════════════════════════════════════
# P0 수집누락 탐지 — 상태 5종·사유코드·P0/P1 등급 (기존 판정과 독립)
# ══════════════════════════════════════════════════════════════════════════
# 위 detect_coverage_anomalies 는 "알림용 보수적 판정"이라 신규 사이트를 건너뛰고
# severity high/medium 2단계만 쓴다. 아래는 그와 별개로 "활성 소스가 전부 실행됐고
# 정상 수집됐는가"를 운영 게이트 수준으로 판정한다. 기존 함수의 반환에는 아무것도
# 추가하지 않는다(알림 볼륨·digest 품질 지표가 조용히 흔들리는 것을 막기 위해).

COLLECT_STATUS_SUCCESS = "SUCCESS"
COLLECT_STATUS_PARTIAL = "PARTIAL"
COLLECT_STATUS_FAILED = "FAILED"
COLLECT_STATUS_SKIPPED = "SKIPPED"
COLLECT_STATUS_ZERO_SUSPICIOUS = "ZERO_SUSPICIOUS"

# 기존 사유코드는 이름을 바꾸지 않는다. 아래 3종은 HTTP 200 위장 실패·스키마 붕괴·
# 과거 전체목록 유입을 조용히 정상으로 오인하던 빈틈을 메운다.
REASON_SOURCE_NOT_EXECUTED = "SOURCE_NOT_EXECUTED"
REASON_FETCH_FAILED = "FETCH_FAILED"
REASON_PARSER_FAILED = "PARSER_FAILED"
REASON_ZERO_ITEMS_WITH_BASELINE = "ZERO_ITEMS_WITH_BASELINE"
REASON_COLLECTION_DROP_HIGH = "COLLECTION_DROP_HIGH"
REASON_DATE_PARSE_RATE_LOW = "DATE_PARSE_RATE_LOW"
REASON_PAGINATION_INCOMPLETE = "PAGINATION_INCOMPLETE"
REASON_DUPLICATE_PAGE_LOOP = "DUPLICATE_PAGE_LOOP"
REASON_DETAIL_LINK_RATE_LOW = "DETAIL_LINK_RATE_LOW"
REASON_BASELINE_INSUFFICIENT = "BASELINE_INSUFFICIENT"
REASON_CONTENT_VALIDATION_FAILED = "CONTENT_VALIDATION_FAILED"
REASON_SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
REASON_COLLECTION_SPIKE_HIGH = "COLLECTION_SPIKE_HIGH"
# 다경로 소스(기업마당 등)에서 앞선 경로가 하드 실패하고 뒤 경로가 살려낸 상태.
# 이번 수집은 성공이라 P0 가 아니지만, 남은 경로마저 실패하면 곧바로 0건이다.
# 조용히 넘어가면 안전망이 몇 주씩 죽은 채 방치된다(2026-08-02 data.go.kr 사례).
REASON_FALLBACK_PATH_DEGRADED = "FALLBACK_PATH_DEGRADED"

P0_REASONS = frozenset({
    REASON_SOURCE_NOT_EXECUTED,
    REASON_FETCH_FAILED,
    REASON_PARSER_FAILED,
    REASON_ZERO_ITEMS_WITH_BASELINE,
    REASON_COLLECTION_DROP_HIGH,
    REASON_DUPLICATE_PAGE_LOOP,
    REASON_CONTENT_VALIDATION_FAILED,
    REASON_SCHEMA_VALIDATION_FAILED,
})
P1_REASONS = frozenset({
    REASON_DATE_PARSE_RATE_LOW,
    REASON_PAGINATION_INCOMPLETE,
    REASON_DETAIL_LINK_RATE_LOW,
    REASON_BASELINE_INSUFFICIENT,
    REASON_COLLECTION_SPIKE_HIGH,
    REASON_FALLBACK_PATH_DEGRADED,
})

BASELINE_WINDOW_RUNS = 7   # 기준선 = 최근 정상 7회
BASELINE_MIN_RUNS = 3      # 3회 미만이면 BASELINE_INSUFFICIENT
DROP_RATIO_P0 = 0.2        # 중앙값 대비 80% 이상 급감(=20% 미만 잔존) → P0
DROP_RATIO_P1 = 0.5        # 50~79% 급감 → P1
DATE_PARSE_MIN_RATE = 0.5  # 게시일 파싱률 50% 미만 → P0
DATE_PARSE_DROP_PP = 0.3   # 평소 대비 30%p 이상 하락 → P1
DETAIL_LINK_MIN_RATE = 0.5  # 상세링크 추출률 50% 미만 → P1
VALID_RECORD_MIN_RATE = 0.8  # id·title·link 정상 레코드 80% 미만 → P0
SUSPICIOUS_CONTENT_MAX_RATE = 0.5  # 로그인·캡차·점검 화면이 절반 이상 → P0
SPIKE_RATIO_P1 = 3.0        # 평소 중앙값의 3배 이상
SPIKE_ABSOLUTE_EXCESS = 20  # 단, 절대 증가가 20건 이상일 때만 → P1

# ── Run 상태 (ADR: docs/prd/adr-miss-detect-status-enums.md) ───────────────
RUN_STATUS_SUCCESS = "SUCCESS"
RUN_STATUS_DEGRADED = "DEGRADED"
RUN_STATUS_FAILED = "FAILED"
RUN_STATUS_OK = "OK"  # deprecated alias ≡ SUCCESS
RUN_FAILED_MISSING_RATIO = 0.30
RUN_FAILED_MISSING_ABS = 5


def normalize_run_status(status: str | None) -> str:
    """OK → SUCCESS. 그 외는 원문(빈 값은 SUCCESS 로 보지 않음)."""
    value = str(status or "")
    if value in (RUN_STATUS_OK, RUN_STATUS_SUCCESS):
        return RUN_STATUS_SUCCESS
    return value


def is_run_failed(
    exec_check: dict | None,
    *,
    missing_ratio: float = RUN_FAILED_MISSING_RATIO,
    missing_abs: int = RUN_FAILED_MISSING_ABS,
) -> bool:
    """실행대장 붕괴·대량 미실행이면 True.

    active_expected==0 이거나 exec_check 가 skip 이면 False (근거 없는 보류 금지).
    """
    check = exec_check if isinstance(exec_check, dict) else {}
    if check.get("skipped"):
        return False
    active = int(check.get("active_expected", 0) or 0)
    if active <= 0:
        return False
    missing_ids = list(check.get("missing_site_ids") or [])
    missing_n = len(missing_ids)
    if missing_n <= 0 and bool(check.get("ok", True)):
        return False
    if missing_n >= int(missing_abs):
        return True
    if missing_n / active >= float(missing_ratio):
        return True
    return False


# 파서 계열 실패를 접속 실패와 구분하기 위한 단서(소문자 비교)
_PARSER_ERROR_HINTS = (
    "attributeerror", "keyerror", "indexerror", "typeerror", "nonetype",
    "selector", "parse", "json", "decode",
)

DEFAULT_THRESHOLDS: dict[str, float] = {
    "drop_ratio_p0": DROP_RATIO_P0,
    "drop_ratio_p1": DROP_RATIO_P1,
    "date_parse_min_rate": DATE_PARSE_MIN_RATE,
    "date_parse_drop_pp": DATE_PARSE_DROP_PP,
    "detail_link_min_rate": DETAIL_LINK_MIN_RATE,
    "valid_record_min_rate": VALID_RECORD_MIN_RATE,
    "suspicious_content_max_rate": SUSPICIOUS_CONTENT_MAX_RATE,
    "spike_ratio_p1": SPIKE_RATIO_P1,
    "spike_absolute_excess": SPIKE_ABSOLUTE_EXCESS,
    "baseline_min_runs": BASELINE_MIN_RUNS,
    "baseline_window_runs": BASELINE_WINDOW_RUNS,
}


def baseline_stats(
    history: list | None,
    *,
    runs: int = BASELINE_WINDOW_RUNS,
    min_runs: int = BASELINE_MIN_RUNS,
) -> dict:
    """최근 정상 runs 회의 중앙값·표본수. update_coverage_baseline 이 실패·이상일을
    애초에 저장하지 않으므로 baseline 에 남은 항목 = 정상 회차다.

    반환: {"median": float|None, "n": int, "sufficient": bool, "samples": list}
    """
    counts = [
        c for c in (_history_count(e) for e in (history or []))
        if c is not None
    ]
    recent = counts[-runs:] if runs > 0 else counts
    n = len(recent)
    return {
        "median": float(statistics.median(recent)) if recent else None,
        "n": n,
        "sufficient": n >= min_runs,
        "samples": recent,
    }


def _rate(numerator: Any, denominator: Any) -> float | None:
    """0 나눗셈 없이 비율. 분모가 0/None 이면 None(판정 불가 → 사유코드 미부여)."""
    try:
        den = float(denominator or 0)
        if den <= 0:
            return None
        return float(numerator or 0) / den
    except (TypeError, ValueError):
        return None


def _row_has_baseline_pollution(row: dict, history: list | None) -> bool:
    """실패 화면·깨진 레코드·비정상 대량 유입을 정상 기준선에 넣지 않는다."""
    item_count = int(row.get("item_count", 0) or 0)
    if item_count <= 0:
        return False

    if "valid_record_count" in row:
        valid_rate = _rate(row.get("valid_record_count"), item_count)
        if valid_rate is not None and valid_rate < VALID_RECORD_MIN_RATE:
            return True

    if "suspicious_content_count" in row:
        suspicious_rate = _rate(row.get("suspicious_content_count"), item_count)
        if (suspicious_rate is not None
                and suspicious_rate >= SUSPICIOUS_CONTENT_MAX_RATE):
            return True

    stats = baseline_stats(history)
    median = stats["median"]
    if stats["sufficient"] and median and median > 0:
        if (item_count / median >= SPIKE_RATIO_P1
                and item_count - median >= SPIKE_ABSOLUTE_EXCESS):
            return True
    return False


def grade_for(reason_codes: list[str]) -> str:
    """사유코드 목록 → 등급. P0 사유가 하나라도 있으면 P0, P1 만 있으면 P1, 없으면 ""."""
    codes = set(reason_codes or [])
    if codes & P0_REASONS:
        return "P0"
    if codes & P1_REASONS:
        return "P1"
    return ""


def classify_source_status(
    row: dict,
    history: list | None = None,
    *,
    page_stat: dict | None = None,
    baseline_date_rate: float | None = None,
    thresholds: dict | None = None,
    zero_item_policy: str = "p0_if_baseline",
    fetch_failed_risk: str = "P0",
) -> dict:
    """coverage row 1건 → 상태·사유코드·등급 판정 (순수·오프라인·네트워크 없음).

    상태는 배타(하나만), 사유코드는 누적(여러 개 가능). 판정 재료가 없으면
    사유코드를 부여하지 않는다(모르는 것을 위험으로 만들지 않는다 — 오탐 폭발 방지).

    zero_item_policy:
      - p0_if_baseline: 기준선 충분·0건 → P0 (기본)
      - p0_always: 기준선 없어도 0건 → P0 (기업마당 등 핵심소스 fail-closed)
      - warning: 0건이어도 P1 만 (지역·월간 사이트)
      - ignore_zero: 0건 사유 미부여 (SUCCESS, 남용 금지)

    fetch_failed_risk:
      - P0/P1: 접속 실패(FETCH_FAILED) 등급. 파서 실패는 항상 P0.
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    policy = str(zero_item_policy or "p0_if_baseline")
    if policy not in {"p0_if_baseline", "p0_always", "warning", "ignore_zero"}:
        policy = "p0_if_baseline"
    fail_risk = str(fetch_failed_risk or "P0").upper()
    if fail_risk not in {"P0", "P1"}:
        fail_risk = "P0"
    stats = baseline_stats(
        history,
        runs=int(th["baseline_window_runs"]),
        min_runs=int(th["baseline_min_runs"]),
    )
    median = stats["median"]
    item_count = int(row.get("item_count", 0) or 0)
    fetch_success = bool(row.get("fetch_success"))
    fetch_error = str(row.get("fetch_error") or "")
    reason_codes: list[str] = []
    detail: dict[str, Any] = {
        "item_count": item_count,
        "baseline_median": median,
        "baseline_n": stats["n"],
        "zero_item_policy": policy,
        "fetch_failed_risk": fail_risk,
    }

    # ① 비활성/설정상 미수행 → SKIPPED (위험 아님)
    if not row.get("enabled", True) or fetch_error == "disabled_in_config":
        return _source_report(row, COLLECT_STATUS_SKIPPED, [], stats, detail)

    # ② 수집기 자체가 배정되지 않음 = 실행되지 않은 것과 같다 → P0
    if fetch_error.startswith("unknown_type:") or not row.get("collector_fn"):
        reason_codes.append(REASON_SOURCE_NOT_EXECUTED)
        return _source_report(row, COLLECT_STATUS_FAILED, reason_codes, stats, detail)

    # ③④ 실패 — 파서 계열과 접속 계열을 구분
    if not fetch_success or fetch_error:
        low = fetch_error.lower()
        is_parser = any(hint in low for hint in _PARSER_ERROR_HINTS)
        if is_parser:
            reason_codes.append(REASON_PARSER_FAILED)
        else:
            reason_codes.append(REASON_FETCH_FAILED)
            detail["risk_override"] = fail_risk
        detail["fetch_error"] = fetch_error[:200]
        return _source_report(row, COLLECT_STATUS_FAILED, reason_codes, stats, detail)

    # ⑤⑥ 0건 — 정책·기준선에 따라 갈린다
    if item_count == 0:
        if policy == "ignore_zero":
            return _source_report(row, COLLECT_STATUS_SUCCESS, [], stats, detail)
        if policy == "p0_always":
            reason_codes.append(REASON_ZERO_ITEMS_WITH_BASELINE)
            detail["drop_rate"] = 1.0
            detail["p0_always"] = True
            return _source_report(
                row, COLLECT_STATUS_ZERO_SUSPICIOUS, reason_codes, stats, detail)
        if stats["sufficient"] and (median or 0) >= 1:
            if policy == "warning":
                # 평소 수집되던 사이트라도 warning 정책이면 P1 만
                reason_codes.append(REASON_BASELINE_INSUFFICIENT)
                detail["drop_rate"] = 1.0
                detail["zero_warning"] = True
            else:
                reason_codes.append(REASON_ZERO_ITEMS_WITH_BASELINE)
                detail["drop_rate"] = 1.0
            return _source_report(
                row, COLLECT_STATUS_ZERO_SUSPICIOUS, reason_codes, stats, detail)
        # 기준선 부족: 0건을 '이상'으로 보지 않는다(오탐·P1 폭주 방지)
        detail["baseline_insufficient"] = True
        return _source_report(row, COLLECT_STATUS_SUCCESS, [], stats, detail)

    # ⑦~⑭ 수집은 됐지만 품질 이상 — 누적 판정
    if "valid_record_count" in row:
        valid_rate = _rate(row.get("valid_record_count"), item_count)
        if valid_rate is not None:
            detail["valid_record_rate"] = round(valid_rate, 4)
            if valid_rate < float(th["valid_record_min_rate"]):
                reason_codes.append(REASON_SCHEMA_VALIDATION_FAILED)

    if "suspicious_content_count" in row:
        suspicious_rate = _rate(row.get("suspicious_content_count"), item_count)
        if suspicious_rate is not None:
            detail["suspicious_content_rate"] = round(suspicious_rate, 4)
            if suspicious_rate >= float(th["suspicious_content_max_rate"]):
                reason_codes.append(REASON_CONTENT_VALIDATION_FAILED)

    if stats["sufficient"] and median and median > 0:
        ratio = item_count / median
        drop_rate = max(0.0, 1.0 - ratio)
        detail["drop_rate"] = round(drop_rate, 4)
        if ratio < float(th["drop_ratio_p0"]):
            # 80% 이상 급감 → P0
            reason_codes.append(REASON_COLLECTION_DROP_HIGH)
        elif ratio < float(th["drop_ratio_p1"]):
            # 50~79% 급감 → 같은 사유코드지만 등급만 P1 (스펙상 중간 급감 전용 코드가 없다)
            reason_codes.append(REASON_COLLECTION_DROP_HIGH)
            detail["drop_p1"] = True
        if (ratio >= float(th["spike_ratio_p1"])
                and item_count - median >= float(th["spike_absolute_excess"])):
            reason_codes.append(REASON_COLLECTION_SPIKE_HIGH)
            detail["spike_ratio"] = round(ratio, 4)

    if page_stat:
        stop_reason = str(page_stat.get("stop_reason") or "")
        if page_stat.get("duplicate_page"):
            reason_codes.append(REASON_DUPLICATE_PAGE_LOOP)
        elif stop_reason == "MAX_PAGES_HIT":
            reason_codes.append(REASON_PAGINATION_INCOMPLETE)
        if page_stat.get("fallback_degraded"):
            reason_codes.append(REASON_FALLBACK_PATH_DEGRADED)
        detail["page_stat"] = page_stat

    # 게시일 파싱률 = 날짜를 읽어낸 비율. posted_parsed_count 는 "직전영업일 게시분"이라
    # 파싱 성공 수가 아니다(오늘 새 공고가 없으면 0이 정상) → date_unknown_count 로 센다.
    date_rate = _rate(item_count - int(row.get("date_unknown_count", 0) or 0), item_count)
    if date_rate is not None:
        detail["posted_date_parse_rate"] = round(date_rate, 4)
        if date_rate < float(th["date_parse_min_rate"]):
            reason_codes.append(REASON_DATE_PARSE_RATE_LOW)
        elif (baseline_date_rate is not None
              and baseline_date_rate - date_rate >= float(th["date_parse_drop_pp"])):
            reason_codes.append(REASON_DATE_PARSE_RATE_LOW)
            detail["date_parse_baseline"] = round(baseline_date_rate, 4)
            detail["date_parse_drop_p1"] = True

    link_rate = _rate(row.get("detail_link_ok_count"), item_count)
    if link_rate is not None:
        detail["detail_link_rate"] = round(link_rate, 4)
        if link_rate < float(th["detail_link_min_rate"]):
            reason_codes.append(REASON_DETAIL_LINK_RATE_LOW)

    status = COLLECT_STATUS_PARTIAL if reason_codes else COLLECT_STATUS_SUCCESS
    if not reason_codes and detail.get("drop_p1"):
        status = COLLECT_STATUS_PARTIAL
    return _source_report(row, status, reason_codes, stats, detail)


def _source_report(
    row: dict, status: str, reason_codes: list[str], stats: dict, detail: dict,
) -> dict:
    """판정 결과를 산출물 스키마로 직렬화.

    등급 조정: 50~79% 급감(drop_p1)·게시일 파싱률 30%p 하락(date_parse_drop_p1)은
    사유코드는 P0 계열과 같지만 스펙상 P1 이므로, 다른 P0 사유가 없을 때 P1 로 낮춘다.
    FETCH_FAILED 는 사이트 정책(fetch_failed_risk)으로 P0/P1 을 고른다.
    """
    grade = grade_for(reason_codes)
    soft_p1 = detail.get("drop_p1") or detail.get("date_parse_drop_p1")
    if grade == "P0" and soft_p1:
        hard_p0 = [c for c in reason_codes
                   if c in P0_REASONS and c != REASON_COLLECTION_DROP_HIGH]
        if not hard_p0:
            grade = "P1"
    elif not grade and soft_p1:
        grade = "P1"
    # 접속 실패만 있을 때 사이트별 등급 오버라이드(만성 지역소스 노이즈 축소)
    if (reason_codes == [REASON_FETCH_FAILED]
            and detail.get("risk_override") in {"P0", "P1"}):
        grade = detail["risk_override"]
    return {
        "site_id": row.get("site_id", ""),
        "site_name": row.get("site_name", ""),
        "url": row.get("url", ""),
        "status": status,
        "item_count": int(row.get("item_count", 0) or 0),
        "baseline_median": stats.get("median"),
        "baseline_n": stats.get("n", 0),
        "drop_rate": detail.get("drop_rate"),
        "posted_date_parse_rate": detail.get("posted_date_parse_rate"),
        "risk_level": grade,
        "reason_codes": list(reason_codes),
        "detail": detail,
    }


def classify_sources(
    rows: list[dict],
    baseline: dict | None = None,
    *,
    page_stats: dict | None = None,
    thresholds: dict | None = None,
    detector_cfg: dict | None = None,
) -> list[dict]:
    """coverage rows 전체 판정. 한 사이트의 판정 실패가 나머지를 막지 않는다.

    detector_cfg 가 있으면 사이트별 thresholds·zero_item_policy·fetch_failed_risk 를 병합한다.
    """
    from mail_core.operations.detector_config import (  # noqa: PLC0415
        fetch_failed_risk_for_site,
        thresholds_for_site,
        zero_item_policy_for_site,
    )

    baseline = baseline if isinstance(baseline, dict) else {}
    page_stats = page_stats or {}
    reports: list[dict] = []
    for row in rows or []:
        site_id = row.get("site_id", "")
        try:
            site_th = dict(thresholds or {})
            policy = "p0_if_baseline"
            fail_risk = "P0"
            if detector_cfg is not None:
                site_th.update(thresholds_for_site(detector_cfg, site_id))
                policy = zero_item_policy_for_site(detector_cfg, site_id)
                fail_risk = fetch_failed_risk_for_site(detector_cfg, site_id)
            reports.append(classify_source_status(
                row,
                baseline.get(site_id),
                page_stat=page_stats.get(site_id),
                thresholds=site_th,
                zero_item_policy=policy,
                fetch_failed_risk=fail_risk,
            ))
        except Exception as exc:  # 판정 실패도 관측 대상이지 중단 사유가 아니다
            reports.append({
                "site_id": site_id,
                "site_name": row.get("site_name", ""),
                "url": row.get("url", ""),
                "status": COLLECT_STATUS_FAILED,
                "item_count": 0,
                "baseline_median": None,
                "baseline_n": 0,
                "drop_rate": None,
                "posted_date_parse_rate": None,
                "risk_level": "P0",
                "reason_codes": [REASON_PARSER_FAILED],
                "detail": {"classify_error": str(exc)[:200]},
            })
    return reports


def verify_source_execution(sites: list[dict] | None, rows: list[dict]) -> dict:
    """활성 소스 수 = 실행결과 수 검증. 불일치하면 그 자체가 P0(누락 위험).

    sites 를 알 수 없으면(None) 검증을 건너뛴다 — 근거 없이 P0 을 만들지 않는다.
    """
    if sites is None:
        return {
            "skipped": True, "ok": True, "active_expected": 0, "executed": 0,
            "missing_site_ids": [], "extra_site_ids": [], "missing_sources": [],
        }
    active = {
        s.get("id", ""): s for s in (sites or [])
        if s.get("enabled", True) and s.get("id")
    }
    executed = {
        r.get("site_id", "") for r in (rows or [])
        if r.get("enabled", True) and r.get("site_id")
    }
    missing = sorted(set(active) - executed)
    extra = sorted(executed - set(active))
    return {
        "skipped": False,
        "ok": not missing,
        "active_expected": len(active),
        "executed": len(executed & set(active)),
        "missing_site_ids": missing,
        "extra_site_ids": extra,
        "missing_sources": [
            {
                "site_id": sid,
                "site_name": active[sid].get("name", ""),
                "url": active[sid].get("url", ""),
                "status": COLLECT_STATUS_FAILED,
                "item_count": 0,
                "baseline_median": None,
                "baseline_n": 0,
                "drop_rate": None,
                "posted_date_parse_rate": None,
                "risk_level": "P0",
                "reason_codes": [REASON_SOURCE_NOT_EXECUTED],
                "detail": {"note": "활성 소스인데 실행대장에 없음"},
            }
            for sid in missing
        ],
    }


def summarize_run_status(source_reports: list[dict], exec_check: dict | None = None) -> dict:
    """실행 전체 상태 요약.

    - FAILED: 실행대장 대량 미실행 → send_hold=True (실발송 보류는 W1에서 소비)
    - DEGRADED: 일부 소스 P0 → 정상 소스 발송 계속 (필터는 W1)
    - SUCCESS: P0 없음 (구 OK alias)
    """
    exec_check = exec_check or {}
    reports = list(source_reports or []) + list(exec_check.get("missing_sources") or [])
    p0 = [r for r in reports if r.get("risk_level") == "P0"]
    p1 = [r for r in reports if r.get("risk_level") == "P1"]
    status_counts: dict[str, int] = {}
    for r in reports:
        key = str(r.get("status") or "")
        status_counts[key] = status_counts.get(key, 0) + 1

    failed = is_run_failed(exec_check)
    if failed:
        status = RUN_STATUS_FAILED
    elif p0:
        status = RUN_STATUS_DEGRADED
    else:
        status = RUN_STATUS_SUCCESS

    return {
        "status": status,
        "send_hold": failed,
        "send_hold_reason": "RUN_FAILED" if failed else "",
        "p0_count": len(p0),
        "p1_count": len(p1),
        "p0_sources": p0,
        "p1_sources": p1,
        "status_counts": status_counts,
        "active_expected": exec_check.get("active_expected", 0),
        "executed": exec_check.get("executed", 0),
        "exec_ok": bool(exec_check.get("ok", True)),
        "recheck_site_ids": [r.get("site_id", "") for r in p0 if r.get("site_id")],
    }


# ── 산출물 렌더링 (순수 — 파일 I/O 없음, 오프라인 테스트 가능) ────────────────
_REASON_LABELS = {
    REASON_SOURCE_NOT_EXECUTED: "활성인데 실행 안 됨",
    REASON_FETCH_FAILED: "접속 실패",
    REASON_PARSER_FAILED: "파싱 실패",
    REASON_ZERO_ITEMS_WITH_BASELINE: "평소 수집되던 소스가 0건",
    REASON_COLLECTION_DROP_HIGH: "수집건수 급감",
    REASON_DATE_PARSE_RATE_LOW: "게시일 파싱률 저하",
    REASON_PAGINATION_INCOMPLETE: "페이지네이션 종료조건 미확인",
    REASON_DUPLICATE_PAGE_LOOP: "페이지 반복(동일 내용)",
    REASON_DETAIL_LINK_RATE_LOW: "상세링크 추출률 저하",
    REASON_BASELINE_INSUFFICIENT: "기준선 부족(정상 3회 미만)",
    REASON_CONTENT_VALIDATION_FAILED: "로그인·캡차·점검 화면 의심",
    REASON_SCHEMA_VALIDATION_FAILED: "필수 항목 구조 손상",
    REASON_COLLECTION_SPIKE_HIGH: "수집건수 비정상 급증",
}


def describe_reasons(reason_codes: list[str]) -> str:
    """사유코드를 사람이 읽는 한국어로. 미지 코드는 원문 유지."""
    return ", ".join(
        _REASON_LABELS.get(c, c) for c in (reason_codes or [])
    ) or "-"


def describe_source_line(report: dict) -> str:
    """소스 1건을 한 줄로. 상태에 따라 의미 있는 수치만 보여준다.

    FAILED 는 item_count 가 무의미하므로(수집 자체가 안 됨) 건수를 쓰지 않는다.
    """
    name = report.get("site_name") or report.get("site_id", "")
    codes = report.get("reason_codes") or []
    status = report.get("status", "")
    base = report.get("baseline_median")
    cur = report.get("item_count", 0)
    reasons = describe_reasons(codes)

    if status == COLLECT_STATUS_FAILED:
        err = str((report.get("detail") or {}).get("fetch_error") or "")
        tail = f" — {err[:60]}" if err else ""
        return f"{name}: {reasons}{tail}"
    if REASON_DATE_PARSE_RATE_LOW in codes:
        detail = report.get("detail") or {}
        now_rate = report.get("posted_date_parse_rate")
        was = detail.get("date_parse_baseline")
        if now_rate is not None and was is not None:
            return (f"{name}: 게시일 파싱률 {was * 100:.0f}% → {now_rate * 100:.0f}%"
                    + (f" ({reasons})" if len(codes) > 1 else ""))
        if now_rate is not None:
            return f"{name}: 게시일 파싱률 {now_rate * 100:.0f}% ({reasons})"
    if REASON_DUPLICATE_PAGE_LOOP in codes:
        return f"{name}: 페이지 반복 — 다음 페이지가 이전과 동일 ({reasons})"
    if base:
        return f"{name}: 평소 {base:g}건 → 금일 {cur}건 ({reasons})"
    return f"{name}: {reasons}"


def build_coverage_payload(
    rows: list[dict],
    source_reports: list[dict],
    run_summary: dict,
    *,
    exec_check: dict | None = None,
    generated_at: str = "",
) -> dict:
    """기계 판독용 실행대장 payload. 산출물 JSON 의 스키마 정의처이기도 하다."""
    exec_check = exec_check or {}
    reports = list(source_reports or []) + list(exec_check.get("missing_sources") or [])
    run_status = normalize_run_status(run_summary.get("status")) or RUN_STATUS_SUCCESS
    send_hold = bool(run_summary.get("send_hold")) or run_status == RUN_STATUS_FAILED
    return {
        "generated_at": generated_at,
        "run_status": run_status,
        "send_hold": send_hold,
        "send_hold_reason": run_summary.get("send_hold_reason") or (
            "RUN_FAILED" if send_hold else ""),
        "active_expected": exec_check.get("active_expected", run_summary.get("active_expected", 0)),
        "executed": exec_check.get("executed", run_summary.get("executed", 0)),
        "execution_complete": bool(exec_check.get("ok", True)),
        "missing_site_ids": list(exec_check.get("missing_site_ids") or []),
        "p0_count": run_summary.get("p0_count", 0),
        "p1_count": run_summary.get("p1_count", 0),
        "status_counts": run_summary.get("status_counts", {}),
        "recheck_site_ids": list(run_summary.get("recheck_site_ids") or []),
        "sources": reports,
        "row_count": len(rows or []),
    }


def _md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |")
    return "\n".join(out)


def render_coverage_markdown(payload: dict) -> str:
    """관리자 확인용 실행대장 보고서. P0 가 있으면 최상단에 경고를 띄운다."""
    lines: list[str] = ["# 소스 수집 실행대장", ""]
    run_status = normalize_run_status(payload.get("run_status"))
    if run_status == RUN_STATUS_FAILED or payload.get("send_hold"):
        lines += [
            f"> ⛔ **전체상태 FAILED — 발송 보류(send_hold)** "
            f"(P0 {payload.get('p0_count', 0)}건 / P1 {payload.get('p1_count', 0)}건)",
            "> 실행대장이 크게 깨져 실발송을 보류하는 상태입니다 (W1 배선).",
            "",
        ]
    elif run_status == RUN_STATUS_DEGRADED:
        lines += [
            f"> 🔴 **누락위험 경고 — 전체상태 DEGRADED** "
            f"(P0 {payload.get('p0_count', 0)}건 / P1 {payload.get('p1_count', 0)}건)",
            "> 정상 수집된 공고의 판정·발송은 계속 진행됩니다.",
            "",
        ]
    if not payload.get("execution_complete", True):
        lines += [
            f"> ⛔ **활성 소스 미실행 {len(payload.get('missing_site_ids') or [])}건** — "
            f"활성 {payload.get('active_expected', 0)} / 실행 {payload.get('executed', 0)}",
            "",
        ]
    lines += [
        f"- 생성: {payload.get('generated_at', '')}",
        f"- 활성 소스: {payload.get('active_expected', 0)}개 / 실행: {payload.get('executed', 0)}개",
        f"- 상태 분포: {payload.get('status_counts', {})}",
        "",
    ]
    risky = [s for s in payload.get("sources", []) if s.get("risk_level")]
    order = {"P0": 0, "P1": 1}
    risky.sort(key=lambda s: (order.get(s.get("risk_level", ""), 9),
                              -(s.get("baseline_median") or 0)))
    if risky:
        lines += ["## 누락위험 소스", ""]
        lines.append(_md_table(
            ["등급", "소스", "상태", "현재", "기준선", "감소율", "사유"],
            [[
                s.get("risk_level", ""),
                (s.get("site_name") or s.get("site_id", ""))[:28],
                s.get("status", ""),
                # 실패한 소스의 건수는 의미가 없다(수집 자체가 안 됨)
                "-" if s.get("status") == COLLECT_STATUS_FAILED else s.get("item_count", 0),
                "-" if s.get("baseline_median") is None else f"{s['baseline_median']:g}",
                "-" if s.get("drop_rate") is None else f"{s['drop_rate'] * 100:.0f}%",
                describe_reasons(s.get("reason_codes")),
            ] for s in risky],
        ))
        lines.append("")
    else:
        lines += ["## 누락위험 소스", "", "_없음_", ""]
    ok = [s for s in payload.get("sources", []) if not s.get("risk_level")]
    lines += [f"## 정상·미수행 소스: {len(ok)}개", ""]
    return "\n".join(lines) + "\n"


def digest_p0_sources(
    p0: list[dict],
    *,
    max_named: int = 12,
) -> tuple[list[dict], list[str]]:
    """P0 목록을 알림용으로 축약. (표시할 소스, 요약 꼬리 문구).

    imp_* 등 동일 접두 대량 실패는 'imp_* N건' 한 줄로 접는다.
    """
    if not p0:
        return [], []
    named: list[dict] = []
    prefix_counts: dict[str, int] = {}
    for report in p0:
        sid = str(report.get("site_id") or "")
        if sid.startswith("imp_"):
            prefix_counts["imp_*"] = prefix_counts.get("imp_*", 0) + 1
            continue
        named.append(report)
    named = named[: max(0, int(max_named))]
    tails = [
        f"{prefix} 접속실패 {count}건 (상세는 실행대장)"
        for prefix, count in sorted(prefix_counts.items())
        if count
    ]
    omitted = len(p0) - len(named) - sum(prefix_counts.values())
    if omitted > 0:
        tails.append(f"그 외 {omitted}건")
    return named, tails


def render_p0_alert_markdown(payload: dict) -> str:
    """P0 전용 알림 본문. 이메일·폰 알림과 같은 내용을 파일로도 남긴다."""
    p0 = [s for s in payload.get("sources", []) if s.get("risk_level") == "P0"]
    if not p0:
        return "# P0 수집 누락 위험\n\n_해당 없음_\n"
    named, tails = digest_p0_sources(p0)
    lines = [
        "# [P0 수집 누락 위험]",
        "",
        f"활성 소스 {payload.get('active_expected', 0)}개 중 {len(p0)}개 발생",
        "",
    ]
    for s in named:
        lines.append(f"- {describe_source_line(s)}")
    for tail in tails:
        lines.append(f"- {tail}")
    hold = bool(payload.get("send_hold")) or (
        normalize_run_status(payload.get("run_status")) == RUN_STATUS_FAILED)
    send_note = (
        "[FAILED][send_hold] 실발송 보류 상태."
        if hold else
        "정상 수집 공고 발송은 계속 진행됨."
    )
    # 재점검 대상은 명명 소스 + 요약(전체 id 나열 폭주 방지)
    recheck = [s.get("site_id", "") for s in named if s.get("site_id")]
    if not recheck:
        recheck = list(payload.get("recheck_site_ids") or [])[:12]
    lines += [
        "",
        send_note,
        "",
        f"재점검 대상: {', '.join(recheck) or '-'}",
    ]
    return "\n".join(lines) + "\n"


def format_p0_alert_message(payload: dict) -> str:
    """알림(이메일) 본문용 축약 텍스트."""
    p0 = [s for s in payload.get("sources", []) if s.get("risk_level") == "P0"]
    if not p0:
        return "P0 수집 누락 위험 없음"
    hold = bool(payload.get("send_hold")) or (
        normalize_run_status(payload.get("run_status")) == RUN_STATUS_FAILED)
    tag = "[FAILED][send_hold] " if hold else ""
    head = (f"{tag}[P0 수집 누락 위험] 활성 소스 {payload.get('active_expected', 0)}개 중 "
            f"{len(p0)}개 발생")
    named, tails = digest_p0_sources(p0, max_named=10)
    body = [f"- {describe_source_line(s)}" for s in named]
    body.extend(f"- {t}" for t in tails)
    send_note = (
        "실발송 보류(send_hold)."
        if hold else
        "정상 수집 공고 발송은 계속 진행됨."
    )
    return head + "\n\n" + "\n".join(body) + "\n\n" + send_note
