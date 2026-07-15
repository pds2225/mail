#!/usr/bin/env python3
"""digest 품질(빠짐없이·적합만) 단독 계측 CLI.

monitor.measure_digest_quality 를 재사용해, 매일 digest(초안)가 적합공고를
놓쳤는지(recall)/무관공고를 섞었는지(precision)만 계측한다. 새 수집·분류 없음.

사용:
  # 실 dry-run 1회 돌려 계측(네트워크 수집 포함)
  python scripts/digest_quality.py
  python scripts/digest_quality.py --skip-coverage-fetch
  # 저장된 run_result JSON 으로 오프라인 계측(네트워크 없음)
  python scripts/digest_quality.py --from-json path/to/run_result.json

환경변수(mock): test_monitor.py / monitor_dry_run.py 와 동일한 placeholder 필요.
"""
from __future__ import annotations

import argparse
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

from monitor import (  # noqa: E402
    format_digest_quality_line,
    measure_digest_quality,
    run_dry_run,
    write_digest_quality_report,
)


def _ensure_utf8_stdout() -> None:
    """cp949 콘솔/파이프에서 이모지·em-dash 출력이 UnicodeEncodeError 로 죽지 않게."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf:
            try:
                reconf(encoding="utf-8")
            except Exception:
                pass


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="digest 품질(recall/precision) 계측")
    parser.add_argument(
        "--from-json", default="", metavar="PATH",
        help="저장된 run_result JSON 으로 오프라인 계측(dry-run 생략).",
    )
    parser.add_argument(
        "--skip-coverage-fetch", action="store_true",
        help="dry-run 시 사이트별 순차 수집 생략(네트워크 절약).",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="workspace/digest_quality_*.json 저장을 생략(계측·출력만).",
    )
    args = parser.parse_args()

    if args.from_json:
        run_result = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        verdict = measure_digest_quality(run_result)
        if not args.no_write:
            write_digest_quality_report(verdict)
    else:
        result = run_dry_run(
            fetch_coverage=not args.skip_coverage_fetch,
            write_reports=not args.no_write,
        )
        verdict = result.get("digest_quality") or measure_digest_quality(result)

    print(format_digest_quality_line(verdict))
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
