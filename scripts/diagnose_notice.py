#!/usr/bin/env python3
"""diagnose_notice — MAIL-P0D-04(TASK-029): 특정 공고가 왜 메일 후보에 없었는지 진단한다.

notice_id를 입력하면:
1. 파이프라인 trace(mail_core.operations.notice_pipeline_trace, TASK-026)에서 그
   공고가 마지막으로 성공한 단계와 처음 실패한 단계·reason_code(들)를 찾는다.
2. 원문 메타(mail_core.storage.raw_store.RawStore, 있으면)를 다시 evaluate_notice()에
   태워, "지금 규칙으로 재평가하면" 어떤 reason_code·evidence·rule_version이 나오는지도
   함께 보여준다 — 규칙이 바뀐 뒤에도 과거 trace와 현재 재현 결과를 나란히 비교할 수 있다.

읽기 전용 진단 도구다. 메일 발송·상태 변경·데이터 수정을 절대 하지 않는다(FORBIDDEN).
원문 전체(본문 description·상세 HTML)는 출력하지 않는다 — reason_code별 근거(evidence,
160자 이내로 이미 절단됨)만 보여준다. 이메일·전화번호로 보이는 문자열은 출력 전 마스킹한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402
from mail_core.operations.notice_pipeline_trace import (  # noqa: E402
    STAGES,
    iter_notice_traces,
    notice_trace_path,
)
from mail_core.storage.raw_store import RawStore  # noqa: E402

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
# \b는 Python 정규식에서 한글도 \w로 취급해 "...5678로"처럼 숫자 뒤에 한글이 바로 오면
# 경계로 인식되지 않는다 — 대신 앞뒤가 숫자가 아님을 lookaround로 직접 확인한다.
_PHONE_RE = re.compile(r"(?<!\d)0\d{1,2}-?\d{3,4}-?\d{4}(?!\d)")


def _fix_console() -> None:
    """Windows cp949 콘솔에서 한국어·특수기호(em dash 등) 출력 시 UnicodeEncodeError를
    막는다(이 저장소 다른 CLI 스크립트들과 동일한 관례 — scripts/accuracy_baseline.py 등)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


class NoticeNotFoundError(LookupError):
    """trace 기록과 원문 메타 어디에도 해당 notice_id가 없을 때."""


def mask_pii(text: str | None) -> str | None:
    """이메일·전화번호로 보이는 패턴을 마스킹한다(원문 전체 출력 금지와 별개의 안전장치)."""
    if not text:
        return text
    text = _EMAIL_RE.sub(lambda mm: m._mask_email(mm.group(0)), text)
    text = _PHONE_RE.sub("***-****-****", text)
    return text


def find_trace_record(notice_id: str, *, days_back: int = 30, logs_dir: Path | None = None) -> dict | None:
    """최근 days_back일의 trace 파일을 최신 날짜부터 훑어 해당 notice_id의 기록을 찾는다."""
    today = datetime.now(timezone.utc).date()
    for offset in range(days_back):
        day = (today - timedelta(days=offset)).strftime("%Y%m%d")
        path = (logs_dir / f"notice_stage_trace_{day}.jsonl") if logs_dir else notice_trace_path(day)
        for row in iter_notice_traces(path):
            if str(row.get("notice_id")) == str(notice_id):
                return row
    return None


def summarize_stages(stages: dict) -> dict:
    """stages(예: {"FETCH": {...}, "EVALUATE:g1": {...}})에서 파이프라인 순서 기준으로
    마지막 성공단계·첫 실패단계·그 단계의 reason_code(error_code)를 뽑는다.

    "실패단계"는 status=="FAILED"(하드 제외)뿐 아니라 PARTIAL/SKIPPED(예: COMPANY_MATCH
    BELOW_THRESHOLD·SUMMARIZE PREVIEW_MODE)도 포함한다 — 이런 상태도 "이 공고가 최종
    후보에 없었던 이유"이기 때문이다. 그룹마다 결과가 다를 수 있어(예: group1은 통과,
    group2는 제외) 같은 단계가 성공/실패 둘 다에 걸릴 수 있다(그룹별로 독립 판정)."""
    def base_stage(key: str) -> str:
        return key.split(":", 1)[0]

    by_stage: dict[str, list[dict]] = {}
    for key, entry in stages.items():
        by_stage.setdefault(base_stage(key), []).append(entry)

    last_success_stage = None
    first_failed_stage = None
    reason_codes: list[str] = []
    for stage in STAGES:
        entries = by_stage.get(stage, [])
        if not entries:
            continue
        if any(e.get("status") == "SUCCESS" for e in entries):
            last_success_stage = stage
        failed = [e for e in entries if e.get("status") in ("FAILED", "PARTIAL", "SKIPPED")]
        if failed and first_failed_stage is None:
            first_failed_stage = stage
            for e in failed:
                code = e.get("error_code", "")
                if code:
                    reason_codes.extend(c for c in code.split(",") if c)
    return {
        "last_success_stage": last_success_stage,
        "first_failed_stage": first_failed_stage,
        "reason_codes": sorted(set(reason_codes)),
    }


def live_reevaluate(meta: dict) -> dict | None:
    """원문 메타를 다시 evaluate_notice()에 태워 현재 규칙 기준 reason_code·evidence·
    rule_version을 구한다. 특정 그룹 조건 없이(그룹 미지정) 일반 판정만 재현한다 —
    당시 실제로 쓰인 그룹 설정은 trace에 저장되지 않으므로 완전 재현은 아니다."""
    item = {k: v for k, v in meta.items() if k not in ("saved_at",)}
    item.setdefault("id", meta.get("notice_id", ""))
    try:
        result = m.evaluate_notice(item, group=None)
    except Exception:
        return None
    return {
        "is_relevant": result.get("is_relevant"),
        "exclude_reason_codes": result.get("exclude_reason_codes"),
        "reason_evidence": {
            code: mask_pii(ev) for code, ev in (result.get("reason_evidence") or {}).items()
        },
        "rule_version": result.get("rule_version"),
        "config_snapshot_id": result.get("config_snapshot_id"),
    }


def diagnose_notice(notice_id: str, *, logs_dir: Path | None = None, raw_root: Path | None = None) -> dict:
    """notice_id 하나를 진단해 보고서 dict를 만든다. 어디에도 없으면 NoticeNotFoundError."""
    trace_row = find_trace_record(notice_id, logs_dir=logs_dir)
    try:
        meta = RawStore.load_meta(notice_id, root=raw_root)
    except OSError:
        # raw_store가 한 번도 활성화된 적 없어 루트 폴더 자체가 없는 경우 등 —
        # 원문 재현 없이 trace만으로 진단을 계속한다(진단 도구가 죽으면 안 됨).
        meta = None

    if trace_row is None and meta is None:
        raise NoticeNotFoundError(f"notice_id={notice_id!r}: trace·원문 메타 어디에도 없음")

    report: dict = {"notice_id": notice_id}

    if trace_row is not None:
        report.update(summarize_stages(trace_row.get("stages", {})))
        report["trace_run_id"] = trace_row.get("run_id")
    else:
        report.update({
            "last_success_stage": None,
            "first_failed_stage": None,
            "reason_codes": [],
        })
        report["note"] = "trace 기록 없음(보관기간 만료 또는 이 실행에서 미수집) — 원문 메타 기준으로만 재현"

    live = live_reevaluate(meta) if meta else None
    report["live_reevaluation"] = live
    if live is None and meta is None:
        report.setdefault("note", "원문 메타 없음(raw_store 비활성 또는 보관기간 만료) — 현재 규칙 재현 불가, trace만 표시")

    return report


def format_report(report: dict) -> str:
    lines = [f"notice_id: {report['notice_id']}"]
    lines.append(f"last_success_stage: {report.get('last_success_stage') or '(기록 없음)'}")
    lines.append(f"first_failed_stage: {report.get('first_failed_stage') or '(기록 없음 — 실패단계 없이 통과했거나 미수집)'}")
    lines.append(f"reason_code(trace): {', '.join(report.get('reason_codes') or []) or '(없음)'}")
    live = report.get("live_reevaluation")
    if live:
        lines.append(f"is_relevant(현재 규칙 재현): {live['is_relevant']}")
        lines.append(f"exclude_reason_codes(현재 규칙 재현): {', '.join(live.get('exclude_reason_codes') or []) or '(없음)'}")
        for code, ev in (live.get("reason_evidence") or {}).items():
            lines.append(f"  evidence[{code}]: {ev}")
        lines.append(f"rule_version: {live.get('rule_version')}")
        lines.append(f"config_snapshot_id: {live.get('config_snapshot_id')}")
    if report.get("note"):
        lines.append(f"note: {report['note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("notice_id", help="진단할 공고 id")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        report = diagnose_notice(args.notice_id)
    except NoticeNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
