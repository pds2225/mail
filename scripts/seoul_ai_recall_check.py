#!/usr/bin/env python3
"""서울/AI 그룹 recall 스모크 — 실사용 전 엔진 점검.

Usage (PowerShell, D:\\mail):
  python scripts/seoul_ai_recall_check.py
  python scripts/seoul_ai_recall_check.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BIZINFO_API_KEY", "check")
os.environ.setdefault("ANTHROPIC_API_KEY", "check")
os.environ.setdefault("GMAIL_ADDRESS", "check@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "check")

import monitor as m  # noqa: E402

FIXTURES = [
    {
        "id": "seoul_compact_soji",
        "item": {
            "title": "2026 AI 솔루션 지원사업 모집 공고",
            "description": "서울소재 스타트업 신청접수",
            "author": "서울TP",
        },
        "expect": "relevant",
    },
    {
        "id": "support_field_ai",
        "item": {
            "title": "인공지능 사업화 지원 모집",
            "description": "상시 신청접수",
            "support_field": "AI/데이터",
            "author": "NIPA",
        },
        "expect": "relevant_or_region_unknown",
    },
    {
        "id": "busan_block",
        "item": {
            "title": "부산 AI 지원 모집",
            "description": "부산 소재 기업만 신청",
            "author": "부산TP",
        },
        "expect": "blocked",
    },
]


def _grp() -> dict:
    groups = json.loads((ROOT / "groups.json").read_text(encoding="utf-8"))
    return next(g for g in groups if g["id"] == "grp_ai_saas")


def _classify(expect: str, ev: dict) -> str:
    if expect == "blocked":
        return "pass" if not ev.get("is_relevant") and ev.get("region_status") == "not_eligible" else "fail"
    if expect == "relevant_or_region_unknown":
        ok = ev.get("is_relevant") or ev.get("region_unknown_review")
        return "pass" if ok else "fail"
    return "pass" if ev.get("is_relevant") else "fail"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    group = _grp()
    rows = []
    fails = 0
    for fx in FIXTURES:
        ev = m.evaluate_notice(fx["item"], group)
        status = _classify(fx["expect"], ev)
        if status == "fail":
            fails += 1
        rows.append({
            "id": fx["id"],
            "status": status,
            "is_relevant": ev.get("is_relevant"),
            "region": ev.get("region_status"),
            "region_unknown_review": ev.get("region_unknown_review"),
            "codes": ev.get("exclude_reason_codes"),
            "title": fx["item"].get("title"),
        })
    out = {"group": group.get("name"), "passed": len(rows) - fails, "failed": fails, "cases": rows}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"서울/AI recall check — {out['passed']}/{len(rows)} pass")
        for r in rows:
            mark = "OK" if r["status"] == "pass" else "NG"
            print(f"  [{mark}] {r['id']}: rel={r['is_relevant']} reg={r['region']}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
