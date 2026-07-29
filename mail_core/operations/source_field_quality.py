"""핵심 공고 소스 필드 품질과 반복 결함을 학습하는 순수 계측 모듈.

원문은 저장하지 않고 필드별 성공 건수/비율과 실패 fingerprint만 남긴다.
동일 fingerprint가 반복되면 P1에서 P0로 승격하며, 정상 이력의 중앙값보다
급락한 경우에도 회귀 결함으로 판정한다.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

QUALITY_FIELDS = ("title", "body", "date", "application_period", "target")
DEFAULT_MIN_READ_RATES = {
    "title": 1.0,
    "body": 0.8,
    "date": 0.8,
    "application_period": 0.6,
    "target": 0.8,
}
BODY_MIN_CHARS = 80
BASELINE_MIN_RUNS = 3
BASELINE_DROP_PP = 0.2
HISTORY_MAX_RUNS = 30
FAILURE_STATUSES = frozenset({"PARSE_FAILED", "DETAIL_FETCH_FAILED"})
OPTIONAL_NOT_SPECIFIED_FIELDS = frozenset({"application_period", "target"})
# 사용자 최우선: 두 전국 종합포털은 첫 실패부터 P0. NIPA/KITA는 한 번의
# 일시오류를 허용하되 같은 fingerprint가 2회 연속이면 P0로 올린다.
CRITICAL_SOURCE_IDS = frozenset({"bizinfo", "kstartup"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _field_status(item: dict[str, Any], field: str) -> str:
    extraction = item.get("detail_extraction") or {}
    fields = extraction.get("fields") or {}
    meta = fields.get(field) if isinstance(fields, dict) else None
    if isinstance(meta, dict):
        return _text(meta.get("status")).upper()
    return _text(extraction.get("status")).upper()


def _field_value(item: dict[str, Any], field: str) -> str:
    if field == "title":
        return _text(item.get("title"))
    if field == "body":
        body = _text(item.get("description"))
        return body if len(body) >= BODY_MIN_CHARS else ""
    if field == "date":
        return _text(
            item.get("published_at")
            or item.get("posted_date")
            or item.get("registered_at")
        )
    if field == "application_period":
        period = item.get("application_period") or {}
        if isinstance(period, dict):
            display = _text(period.get("display") or period.get("end"))
            if display:
                return display
        return _text(item.get("deadline"))
    if field == "target":
        return _text(
            item.get("target_field")
            or item.get("target_age_field")
            or item.get("business_age_text")
        )
    return ""


def evaluate_source_items(site_id: str, items: list[dict[str, Any]] | None) -> dict[str, Any]:
    """상세보강된 표본을 필드별 읽기 성공률/값 존재율로 요약."""
    rows = [item for item in (items or []) if isinstance(item, dict)]
    n = len(rows)
    fields: dict[str, dict[str, Any]] = {}
    for field in QUALITY_FIELDS:
        value_count = 0
        read_count = 0
        failure_count = 0
        for item in rows:
            value = _field_value(item, field)
            status_name = "description" if field == "body" else (
                "application_period" if field == "application_period" else field
            )
            status = _field_status(item, status_name)
            if value:
                value_count += 1
            if field == "body":
                readable = bool(value)
            else:
                # SUCCESS는 실제 값이 있을 때만 읽기 성공이다. 상위 상세 파싱이
                # 성공했다는 이유로 빈 날짜/지원대상을 성공 처리하지 않는다.
                # 신청기간·지원대상은 원문 미기재가 정상 상태일 수 있다.
                readable = bool(value) or (
                    field in OPTIONAL_NOT_SPECIFIED_FIELDS
                    and status == "NOT_SPECIFIED"
                )
            if readable:
                read_count += 1
            if status in FAILURE_STATUSES:
                failure_count += 1
        fields[field] = {
            "read_count": read_count,
            "read_rate": round(read_count / n, 4) if n else 0.0,
            "value_count": value_count,
            "value_rate": round(value_count / n, 4) if n else 0.0,
            "failure_count": failure_count,
        }
    return {"site_id": site_id, "sample_size": n, "fields": fields}


def load_history(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = data.get("runs") if isinstance(data, dict) else None
        return {"version": 1, "runs": list(runs or [])}
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "runs": []}


def _baseline_rates(
    history: dict[str, Any],
    site_id: str,
    field: str,
) -> list[float]:
    rates: list[float] = []
    for run in history.get("runs") or []:
        fingerprint = f"{site_id}:{field}"
        if fingerprint in set(run.get("fingerprints") or []):
            continue
        source = (run.get("sources") or {}).get(site_id) or {}
        metric = (source.get("fields") or {}).get(field) or {}
        try:
            if int(source.get("sample_size", 0) or 0) > 0:
                rates.append(float(metric.get("read_rate", 0.0)))
        except (TypeError, ValueError):
            continue
    return rates[-HISTORY_MAX_RUNS:]


def _prior_repeat_count(history: dict[str, Any], fingerprint: str) -> int:
    count = 0
    for run in reversed(history.get("runs") or []):
        fingerprints = set(run.get("fingerprints") or [])
        if fingerprint not in fingerprints:
            break
        count += 1
    return count


def _issue_severity(site_id: str, repeat: int) -> str:
    if site_id in CRITICAL_SOURCE_IDS or repeat >= 2:
        return "P0"
    return "P1"


def build_quality_report(
    source_metrics: dict[str, dict[str, Any]],
    *,
    fetch_errors: dict[str, str] | None = None,
    history: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """임계·과거 중앙값·반복 횟수를 적용해 결함 보고서를 만든다."""
    history = history or {"runs": []}
    fetch_errors = fetch_errors or {}
    issues: list[dict[str, Any]] = []
    fingerprints: list[str] = []

    for site_id in sorted(set(source_metrics) | set(fetch_errors)):
        source = source_metrics.get(site_id) or {
            "site_id": site_id,
            "sample_size": 0,
            "fields": {},
        }
        if fetch_errors.get(site_id):
            fingerprint = f"{site_id}:fetch"
            repeat = _prior_repeat_count(history, fingerprint) + 1
            issues.append({
                "site_id": site_id,
                "field": "fetch",
                "reason": "LIVE_SAMPLE_FETCH_FAILED",
                "severity": _issue_severity(site_id, repeat),
                "repeat_count": repeat,
                "fingerprint": fingerprint,
                "error_type": fetch_errors[site_id],
            })
            fingerprints.append(fingerprint)
            continue

        for field, minimum in DEFAULT_MIN_READ_RATES.items():
            metric = (source.get("fields") or {}).get(field) or {}
            rate = float(metric.get("read_rate", 0.0) or 0.0)
            reasons: list[str] = []
            if rate < minimum:
                reasons.append("FIELD_READ_RATE_LOW")
            previous = _baseline_rates(history, site_id, field)
            baseline = statistics.median(previous) if len(previous) >= BASELINE_MIN_RUNS else None
            if (
                baseline is not None
                and baseline - rate >= BASELINE_DROP_PP - 1e-9
            ):
                reasons.append("FIELD_READ_RATE_REGRESSION")
            if not reasons:
                continue
            fingerprint = f"{site_id}:{field}"
            repeat = _prior_repeat_count(history, fingerprint) + 1
            issues.append({
                "site_id": site_id,
                "field": field,
                "reason": "+".join(reasons),
                "severity": _issue_severity(site_id, repeat),
                "repeat_count": repeat,
                "fingerprint": fingerprint,
                "read_rate": round(rate, 4),
                "minimum": minimum,
                "baseline_median": (
                    round(float(baseline), 4) if baseline is not None else None
                ),
            })
            fingerprints.append(fingerprint)

    return {
        "version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": "P0" if any(i["severity"] == "P0" for i in issues) else (
            "P1" if issues else "SUCCESS"
        ),
        "sources": source_metrics,
        "issues": issues,
        "fingerprints": sorted(set(fingerprints)),
        "learning": {
            "history_runs_used": len(history.get("runs") or []),
            "baseline_min_runs": BASELINE_MIN_RUNS,
            "baseline_drop_pp": BASELINE_DROP_PP,
            "repeat_escalates_at": 2,
            "critical_sources": sorted(CRITICAL_SOURCE_IDS),
        },
    }


def append_history(
    history: dict[str, Any],
    report: dict[str, Any],
    *,
    path: Path,
) -> None:
    """원문/오류문 없이 비율·fingerprint만 30회 롤링 저장."""
    run = {
        "generated_at": report.get("generated_at", ""),
        "status": report.get("status", ""),
        "sources": report.get("sources") or {},
        "fingerprints": list(report.get("fingerprints") or []),
    }
    runs = [*(history.get("runs") or []), run][-HISTORY_MAX_RUNS:]
    payload = {"version": 1, "runs": runs}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 핵심 공고 필드 품질",
        "",
        f"- 생성: {report.get('generated_at', '')}",
        f"- 상태: {report.get('status', '')}",
        f"- 학습 이력: {report.get('learning', {}).get('history_runs_used', 0)}회",
        "",
        "| 소스 | 표본 | 제목 | 본문 | 날짜 | 신청기간 | 지원대상 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for site_id, source in sorted((report.get("sources") or {}).items()):
        fields = source.get("fields") or {}
        rates = [
            f"{float((fields.get(field) or {}).get('read_rate', 0)):.0%}"
            for field in QUALITY_FIELDS
        ]
        lines.append(
            f"| {site_id} | {source.get('sample_size', 0)} | "
            + " | ".join(rates)
            + " |"
        )
    lines.extend(["", "## 결함 신호", ""])
    if not report.get("issues"):
        lines.append("- 없음")
    for issue in report.get("issues") or []:
        lines.append(
            f"- {issue.get('severity')} {issue.get('fingerprint')} "
            f"({issue.get('reason')}, 반복 {issue.get('repeat_count')}회)"
        )
    return "\n".join(lines) + "\n"
