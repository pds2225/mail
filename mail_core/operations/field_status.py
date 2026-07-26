"""빈 정보 3상태(surface·판정 가드·추출률) — 순수 모듈 (monitor import 금지).

W3 / P0-B: NOT_SPECIFIED · PARSE_FAILED · DETAIL_FETCH_FAILED · SUCCESS 를
한 가지 “미상”으로 섞지 않는다. region_unknown 심볼은 삭제하지 않고 매핑만 한다.
"""
from __future__ import annotations

from typing import Any

EXTRACTION_SUCCESS = "SUCCESS"
NOT_SPECIFIED = "NOT_SPECIFIED"
PARSE_FAILED = "PARSE_FAILED"
DETAIL_FETCH_FAILED = "DETAIL_FETCH_FAILED"

FIELD_BLANK_STATUSES = frozenset({
    EXTRACTION_SUCCESS,
    NOT_SPECIFIED,
    PARSE_FAILED,
    DETAIL_FETCH_FAILED,
})
FAILURE_STATUSES = frozenset({PARSE_FAILED, DETAIL_FETCH_FAILED})

# 판정에 쓰는 필수 필드(금액·신청방법 제외 — PRD §5.3 W3-d)
DECISION_FIELDS = ("region", "application_period", "target", "title")
ABSOLUTE_FIELDS = ("title",)  # url 은 item 최상위 link 로 별도 검사

SURFACE_LABELS = {
    NOT_SPECIFIED: "원문 미기재",
    PARSE_FAILED: "추출 실패(검수)",
    DETAIL_FETCH_FAILED: "상세 접속 실패(재시도)",
    EXTRACTION_SUCCESS: "확보",
}

# 지역 필드 전용 표면 문구(메일·digest)
REGION_SURFACE_LABELS = {
    NOT_SPECIFIED: "지역 제한 없음",
    PARSE_FAILED: "추출 실패(검수)",
    DETAIL_FETCH_FAILED: "상세 접속 실패(재시도)",
    EXTRACTION_SUCCESS: "확보",
}

PARSE_FAIL_RATE_P1 = 0.25
PARSE_FAIL_RATE_P0 = 0.50


def normalize_field_status(status: Any) -> str:
    """알 수 없는 값은 빈 문자열. 레거시 OK→SUCCESS 는 없음(필드 전용)."""
    s = str(status or "").strip().upper()
    if s in FIELD_BLANK_STATUSES:
        return s
    return ""


def field_blank_kind(status: Any) -> str:
    """필드 공백 상태 코드. 미지정이면 빈 문자열."""
    return normalize_field_status(status)


def surface_label_for_field(
    status: Any,
    *,
    field: str = "",
) -> str:
    """운영·메일 표면 라벨. 실패 2종과 미기재를 구분한다."""
    kind = field_blank_kind(status)
    if not kind:
        return ""
    if field == "region":
        return REGION_SURFACE_LABELS.get(kind, SURFACE_LABELS.get(kind, ""))
    return SURFACE_LABELS.get(kind, "")


def maps_to_region_unknown_bucket(status: Any) -> bool:
    """실패 2종만 레거시 region_unknown 버킷에 매핑 가능.

    NOT_SPECIFIED 는 unknown 버킷에 넣지 않는다(PRD §5.2).
    """
    return field_blank_kind(status) in FAILURE_STATUSES


def should_force_review_for_extraction(item: dict[str, Any] | None) -> bool:
    """PARSE_FAILED / DETAIL_FETCH_FAILED 이면 자동 제외 금지·review 강제."""
    if not isinstance(item, dict):
        return False
    extraction = item.get("detail_extraction") or {}
    top = field_blank_kind(extraction.get("status"))
    if top in FAILURE_STATUSES:
        return True
    fields = extraction.get("fields") or {}
    if not isinstance(fields, dict):
        return False
    for meta in fields.values():
        if not isinstance(meta, dict):
            continue
        if field_blank_kind(meta.get("status")) in FAILURE_STATUSES:
            return True
    return False


def region_field_status(item: dict[str, Any] | None) -> str:
    """지역 필드의 추출 상태(없으면 상위 detail_extraction.status)."""
    if not isinstance(item, dict):
        return ""
    extraction = item.get("detail_extraction") or {}
    fields = extraction.get("fields") or {}
    if isinstance(fields, dict):
        region_meta = fields.get("region") or {}
        if isinstance(region_meta, dict) and region_meta.get("status"):
            return field_blank_kind(region_meta.get("status"))
    return field_blank_kind(extraction.get("status"))


def allow_region_unknown_bucket(item: dict[str, Any] | None) -> bool:
    """region_unknown 버킷 진입 허용 여부.

    - 추출 실패(PARSE/FETCH) → False (review 전용)
    - 지역 NOT_SPECIFIED → False (전국/미지정 경로, unknown 금지)
    - 그 외(상태 없음·레거시) → True (기존 recall surface 유지)
    """
    if should_force_review_for_extraction(item):
        return False
    if region_field_status(item) == NOT_SPECIFIED:
        return False
    return True


def not_specified_excludes_forbidden(item: dict[str, Any] | None) -> bool:
    """가드용: NOT_SPECIFIED 만으로 exclude/region_unknown 에 들어가면 True(위반)."""
    if region_field_status(item) != NOT_SPECIFIED:
        return False
    # 호출측이 버킷을 넘기므로 여기서는 상태만 확인 — 테스트가 버킷과 조합
    return True


def _field_status_from_item(item: dict[str, Any], field: str) -> str:
    extraction = item.get("detail_extraction") or {}
    fields = extraction.get("fields") or {}
    if isinstance(fields, dict):
        meta = fields.get(field) or {}
        if isinstance(meta, dict) and meta.get("status"):
            return field_blank_kind(meta.get("status"))
    return field_blank_kind(extraction.get("status"))


def compute_extraction_rates(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    """소스(또는 배치) 단위 추출률.

    반환 키:
      absolute_ok, decision_ok, parse_failed_rate, detail_fetch_failed_rate,
      not_specified_rate, n, parse_or_fetch_fail_rate, risk_level, reason_codes
    """
    rows = list(items or [])
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "absolute_ok": True,
            "decision_ok": True,
            "parse_failed_rate": 0.0,
            "detail_fetch_failed_rate": 0.0,
            "not_specified_rate": 0.0,
            "parse_or_fetch_fail_rate": 0.0,
            "risk_level": "",
            "reason_codes": [],
        }

    parse_n = fetch_n = not_spec_n = 0
    absolute_fail = 0
    decision_fail = 0

    for it in rows:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        link = str(it.get("link") or it.get("url") or "").strip()
        if not title or not link:
            absolute_fail += 1

        statuses = [_field_status_from_item(it, f) for f in DECISION_FIELDS]
        if any(s in FAILURE_STATUSES for s in statuses):
            decision_fail += 1
        if any(s == PARSE_FAILED for s in statuses) or field_blank_kind(
            (it.get("detail_extraction") or {}).get("status")
        ) == PARSE_FAILED:
            parse_n += 1
        if any(s == DETAIL_FETCH_FAILED for s in statuses) or field_blank_kind(
            (it.get("detail_extraction") or {}).get("status")
        ) == DETAIL_FETCH_FAILED:
            fetch_n += 1
        if any(s == NOT_SPECIFIED for s in statuses):
            not_spec_n += 1

    parse_rate = parse_n / n
    fetch_rate = fetch_n / n
    not_spec_rate = not_spec_n / n
    fail_rate = (parse_n + fetch_n) / n  # 건수 합 / n (중복 가능 → 상한 1.0 으로 clamp)
    fail_rate = min(1.0, fail_rate)

    reason_codes: list[str] = []
    risk = ""
    if fail_rate >= PARSE_FAIL_RATE_P0:
        risk = "P0"
        reason_codes.append("DETAIL_EXTRACT_RATE_LOW")
    elif fail_rate >= PARSE_FAIL_RATE_P1:
        risk = "P1"
        reason_codes.append("DETAIL_EXTRACT_RATE_LOW")

    return {
        "n": n,
        "absolute_ok": absolute_fail == 0,
        "decision_ok": decision_fail == 0,
        "parse_failed_rate": round(parse_rate, 4),
        "detail_fetch_failed_rate": round(fetch_rate, 4),
        "not_specified_rate": round(not_spec_rate, 4),
        "parse_or_fetch_fail_rate": round(fail_rate, 4),
        "risk_level": risk,
        "reason_codes": reason_codes,
    }


def plan_extraction_retries(
    items: list[dict[str, Any]] | None,
    *,
    fetch_auto_retry: int = 2,
    parse_auto_retry: int = 1,
    backoff_sec: tuple[int, ...] | list[int] = (60, 180),
) -> list[dict[str, Any]]:
    """추출 실패 공고 재시도 계획. NOT_SPECIFIED 는 재시도 없음."""
    plans: list[dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        extraction = it.get("detail_extraction") or {}
        status = field_blank_kind(extraction.get("status"))
        if status == DETAIL_FETCH_FAILED:
            plans.append({
                "item_id": str(it.get("id") or ""),
                "url": str(it.get("link") or it.get("url") or ""),
                "subtype": DETAIL_FETCH_FAILED,
                "max_attempts": int(fetch_auto_retry),
                "backoff_sec": list(backoff_sec)[: int(fetch_auto_retry)],
                "attempt": 0,
            })
        elif status == PARSE_FAILED:
            plans.append({
                "item_id": str(it.get("id") or ""),
                "url": str(it.get("link") or it.get("url") or ""),
                "subtype": PARSE_FAILED,
                "max_attempts": int(parse_auto_retry),
                "backoff_sec": list(backoff_sec)[: int(parse_auto_retry)],
                "attempt": 0,
            })
    return plans


def enrichment_clears_review(item: dict[str, Any] | None) -> bool:
    """DETAIL_FETCH_FAILED 재시도 후 SUCCESS/NOT_SPECIFIED 이면 review 해제 가능."""
    if not isinstance(item, dict):
        return False
    status = field_blank_kind((item.get("detail_extraction") or {}).get("status"))
    if status in FAILURE_STATUSES:
        return False
    if item.get("detail_enriched") is True:
        return True
    return status in {EXTRACTION_SUCCESS, NOT_SPECIFIED}


def write_extraction_rates_report(
    rates_by_site: dict[str, dict[str, Any]] | None,
    *,
    run_at: Any = None,
    path: Any = None,
) -> Any:
    """소스별 not_specified / parse_failed / detail_fetch_failed 비율 MD 리포트."""
    from datetime import datetime
    from pathlib import Path

    from mail_core.paths import LOGS_DIR

    rates_by_site = rates_by_site or {}
    if not rates_by_site:
        return None
    moment = run_at or datetime.now()
    try:
        stamp = moment.strftime("%Y%m%d")
    except Exception:
        stamp = "unknown"
    target = Path(path) if path else (LOGS_DIR / f"extraction_rates_{stamp}.md")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# 상세 추출률 리포트 — {stamp}",
            "",
            "| site | n | not_specified | parse_failed | fetch_failed | fail_rate | risk |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for sid, rates in sorted(rates_by_site.items()):
            lines.append(
                "| {site} | {n} | {ns:.0%} | {pf:.0%} | {ff:.0%} | {fr:.0%} | {risk} |".format(
                    site=sid,
                    n=int(rates.get("n", 0) or 0),
                    ns=float(rates.get("not_specified_rate", 0) or 0),
                    pf=float(rates.get("parse_failed_rate", 0) or 0),
                    ff=float(rates.get("detail_fetch_failed_rate", 0) or 0),
                    fr=float(rates.get("parse_or_fetch_fail_rate", 0) or 0),
                    risk=rates.get("risk_level") or "-",
                )
            )
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target
    except Exception:
        return None


def assert_blank_states_disjoint() -> None:
    """계약 가드: 4상태가 서로 다른 surface 를 갖는다."""
    labels = {
        EXTRACTION_SUCCESS: surface_label_for_field(EXTRACTION_SUCCESS),
        NOT_SPECIFIED: surface_label_for_field(NOT_SPECIFIED),
        PARSE_FAILED: surface_label_for_field(PARSE_FAILED),
        DETAIL_FETCH_FAILED: surface_label_for_field(DETAIL_FETCH_FAILED),
    }
    assert labels[NOT_SPECIFIED] != labels[PARSE_FAILED]
    assert labels[NOT_SPECIFIED] != labels[DETAIL_FETCH_FAILED]
    assert labels[PARSE_FAILED] != labels[DETAIL_FETCH_FAILED]
    assert maps_to_region_unknown_bucket(NOT_SPECIFIED) is False
    assert maps_to_region_unknown_bucket(PARSE_FAILED) is True
    assert maps_to_region_unknown_bucket(DETAIL_FETCH_FAILED) is True
