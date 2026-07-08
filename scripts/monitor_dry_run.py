#!/usr/bin/env python3
"""Dry-run: 발송·seen_ids 저장 없이 커버리지·review queue 보고서 생성.

사용:
  python3 scripts/monitor_dry_run.py
  python3 scripts/monitor_dry_run.py --skip-coverage-fetch

환경변수(mock): test_monitor.py와 동일하게 API 키 placeholder 필요.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BIZINFO_API_KEY", "dry_run_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "dry_run_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "dry_run_pass")
os.environ.setdefault("GMAIL_ADDRESS", "dry-run@example.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

from monitor import run_dry_run  # noqa: E402


def _ensure_utf8_stdout() -> None:
    """cp949 콘솔/파이프에서 em-dash(—) 등 출력이 UnicodeEncodeError 로 죽지 않게.

    fetch_notice_attachments.py 관례 재사용 — 출력은 UTF-8(errors=replace) 고정,
    reconfigure 불가 스트림(StringIO 등)은 조용히 통과.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _print_summary(public: dict, ru_groups: list[dict]) -> None:
    """사람용 요약 출력(테스트 가능하도록 main 에서 분리)."""
    print("=== monitor dry-run summary ===")
    for key, val in public.items():
        print(f"  {key}: {val}")
    if ru_groups:
        print("\n=== 지역 미상(확인 필요) — 보고 메일 하단에 함께 발송 ===")
        for g in ru_groups:
            print(f"  [{g.get('name')}] {g.get('region_unknown_items')}건")
            for t in g.get("region_unknown_titles", []):
                print(f"     - {t}")
    print("Reports: logs/site_collection_coverage_report.md")
    print("         logs/today_notice_missing_risk_report.md")
    print("         logs/review_queue_YYYYMMDD.md")


def main() -> int:
    import argparse

    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-coverage-fetch", action="store_true")
    parser.add_argument("--json", action="store_true", help="요약 JSON stdout")
    args = parser.parse_args()

    summary = run_dry_run(
        write_reports=True,
        fetch_coverage=not args.skip_coverage_fetch,
    )
    preview = summary.get("preview_groups", []) or []
    ru_groups = [g for g in preview if g.get("region_unknown_items")]
    public = {
        k: summary[k]
        for k in summary
        if k not in ("date_review_queue", "coverage", "recipient_audit", "preview_groups")
    }
    # 지역 미상(확인 필요) 합계 — 보고 메일 하단에 함께 발송될 공고 수(누락 방지 가시화)
    public["region_unknown_total"] = sum(g.get("region_unknown_items", 0) for g in preview)
    if args.json:
        print(json.dumps(public, ensure_ascii=False, indent=2, default=str))
    else:
        print("=== monitor dry-run summary ===")
        for key, val in public.items():
            print(f"  {key}: {val}")
        if ru_groups:
            print("\n=== 지역 미상(확인 필요) — 보고 메일 하단에 함께 발송 ===")
            for g in ru_groups:
                print(f"  [{g.get('name')}] {g.get('region_unknown_items')}건")
                for t in g.get("region_unknown_titles", []):
                    print(f"     - {t}")
        print("Reports: logs/site_collection_coverage_report.md")
        print("         logs/today_notice_missing_risk_report.md")
        print("         logs/review_queue_YYYYMMDD.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
