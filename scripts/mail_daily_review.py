#!/usr/bin/env python3
"""매일 메일 발송 후 당일 검수 + 컨텍스트 적재 (L규칙/MDR 스타일).

IMAP/SMTP 없음. delivery_state·source_coverage·draft/log 만 본다.
Secret 출력 금지. 실발송 추가 금지.

Usage (PowerShell, repo root):
  python scripts/mail_daily_review.py
  python scripts/mail_daily_review.py --date 2026-07-30 --slot am
  python scripts/mail_daily_review.py --json
  python scripts/mail_daily_review.py --append-context --fail-on-error

GHA: monitor.yml 발송 step 이후 실행.
스키마: docs/project/mail_daily_reviews/README.md
규칙: docs/project/mail_daily_reviews/rules.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# monitor import 크래시 방지(본 스크립트는 monitor 를 안 쓰지만 테스트 환경 공유)
os.environ.setdefault("BIZINFO_API_KEY", "daily-review")
os.environ.setdefault("ANTHROPIC_API_KEY", "daily-review")
os.environ.setdefault("GMAIL_ADDRESS", "daily-review@example.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "daily-review")
os.environ.setdefault("PYTHONUTF8", "1")

from mail_core.operations.daily_review import run_daily_review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Mail daily post-send review (MDR rules)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today KST)")
    parser.add_argument("--slot", choices=("am", "pm"), help="발송 회차 (default: hour-based)")
    parser.add_argument(
        "--run-duration-sec",
        type=float,
        default=None,
        help="이번 monitor 실행 초(선택). 짧으면 MDR-001 강화",
    )
    parser.add_argument(
        "--append-context",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="docs/.../context/ledger.jsonl 에 append (기본 ON, --no-append-context 로 끔)",
    )
    parser.add_argument(
        "--fail-on-error",
        "--strict",
        action="store_true",
        help="overall FAIL 이면 exit 2 (GHA에서 스텝 경고; --strict 별칭)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="FAIL 이어도 exit 0 (아티팩트만)",
    )
    parser.add_argument("--json", action="store_true", help="JSON만 stdout")
    parser.add_argument(
        "--relax-coverage",
        action="store_true",
        help="coverage 파일 없어도 MDR-001 을 즉시 FAIL 하지 않음(로컬 실험용)",
    )
    args = parser.parse_args()

    report, paths = run_daily_review(
        date_s=args.date,
        slot=args.slot,
        append_context=bool(args.append_context),
        run_duration_sec=args.run_duration_sec,
        require_coverage=not args.relax_coverage,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"[mail_daily_review] overall={report.overall} cycle={report.cycle_key}")
        for c in report.checks:
            line = f"  {c.status:4} {c.id} {c.label}: {c.detail}"
            try:
                print(line)
            except UnicodeEncodeError:
                print(line.encode("utf-8", errors="replace").decode("ascii", errors="replace"))
        print(f"  wrote: {paths.get('md')}")
        if "ledger" in paths:
            print(f"  ledger: {paths['ledger']}")

    # GHA summary
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            md = (paths.get("md") or Path()).read_text(encoding="utf-8")
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(md + "\n")
        except OSError:
            pass

    if report.overall == "FAIL" and args.fail_on_error and not args.warn_only:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
