#!/usr/bin/env python3
"""기업마당·K-Startup·NIPA·KITA 필드 품질 게이트/학습 기록.

--offline: 네트워크 없이 관련 회귀 테스트만 실행
--live: 각 소스 최신 3건만 읽어 제목·본문·날짜·신청기간·대상 추출률 측정
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "var" / "logs"
STATE_DIR = ROOT / "var" / "state"
REPORT_JSON = LOG_DIR / "source_field_quality_latest.json"
REPORT_MD = LOG_DIR / "source_field_quality_latest.md"
HISTORY_PATH = STATE_DIR / "source_field_quality_history.json"
PRIORITY_SOURCES = ("bizinfo", "kstartup", "nipa", "kita")
SAMPLE_SIZE = 3
OFFLINE_TESTS = (
    "tests/test_source_field_quality.py",
    "tests/test_runtime_detail_adapter.py",
    "tests/test_core_sources_specialize.py",
    "tests/test_fetch_kita_replay.py",
)


def _bounded_site(site_id: str, site: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(site)
    if site_id == "bizinfo":
        out.update(
            api_page_unit=10,
            api_max_pages=1,
            datagokr_page_unit=10,
            datagokr_max_pages=1,
        )
    elif site_id == "kstartup":
        out.update(
            max_pages_public=1,
            max_pages_private=1,
            empty_new_streak=1,
            view_count=10,
        )
    elif site_id == "nipa":
        out["max_pages"] = 1
    return out


def collect_live_metrics() -> tuple[dict[str, dict], dict[str, str]]:
    """메일/seen 저장 없이 핵심 소스별 최신 3건만 상세보강."""
    os.environ["MONITOR_NO_PERSIST_SEEN"] = "1"
    os.environ["MONITOR_EXTRACTION_RETRY_SLEEP"] = "0"
    from mail_core.operations.detail_runtime_adapter import (
        install_kstartup_body_selector_adapter,
    )

    install_kstartup_body_selector_adapter()
    import monitor as m
    from mail_core.operations.source_field_quality import evaluate_source_items

    sites = {s.get("id"): s for s in m.load_json(m.SITES_PATH, [])}
    metrics: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for site_id in PRIORITY_SOURCES:
        site = sites.get(site_id)
        if not isinstance(site, dict):
            errors[site_id] = "SITE_CONFIG_MISSING"
            continue
        fetcher = m.FETCHERS.get(site.get("type", ""))
        if fetcher is None:
            errors[site_id] = "FETCHER_MISSING"
            continue
        try:
            fetched = list(fetcher(_bounded_site(site_id, site)) or [])
            sample = fetched[:SAMPLE_SIZE]
            enriched = m.enrich_items(sample, limit=max(40, len(sample)))
            metrics[site_id] = evaluate_source_items(site_id, enriched)
        except Exception as exc:  # 오류문/URL은 history에 남기지 않는다.
            errors[site_id] = type(exc).__name__
    return metrics, errors


def run_live_and_record() -> dict[str, Any]:
    from mail_core.operations.source_field_quality import (
        append_history,
        build_quality_report,
        load_history,
        render_markdown,
    )

    history = load_history(HISTORY_PATH)
    metrics, errors = collect_live_metrics()
    report = build_quality_report(
        metrics,
        fetch_errors=errors,
        history=history,
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    append_history(history, report, path=HISTORY_PATH)
    return report


def run_offline() -> int:
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    for key in (
        "BIZINFO_API_KEY",
        "ANTHROPIC_API_KEY",
        "GMAIL_ADDRESS",
        "GMAIL_APP_PASSWORD",
    ):
        env.setdefault(key, "source-field-gate")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *OFFLINE_TESTS, "-q", "--tb=no"],
        cwd=ROOT,
        env=env,
    )
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="핵심 공고 필드 품질 게이트")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--strict", action="store_true", help="P0이면 non-zero")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.offline or not args.live:
        return run_offline()
    report = run_live_and_record()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"source_field_quality: {report['status']} "
            f"sources={len(report['sources'])} issues={len(report['issues'])}"
        )
        print(f"report: {REPORT_JSON}")
    return 1 if args.strict and report.get("status") == "P0" else 0


if __name__ == "__main__":
    raise SystemExit(main())
