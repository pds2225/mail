#!/usr/bin/env python3
"""golden_regression_check — MAIL-P0D-05(TASK-030): 핵심소스 판정 변경이 적합공고
누락(recall 저하)을 늘리는지 자동 측정하는 회귀 harness.

tests/fixtures/golden_regression_set.json 의 비식별·가상 골든셋(모두 "적합"으로
라벨된 공고)을 evaluate_notice()에 태워, 다음 두 재현율(recall)이 기준선 이상인지
검사한다:
  - 핵심소스(mail_core.matching.core_sources.CORE_SOURCE_IDS, 기업마당·K-Startup)
    재현율 >= CORE_SOURCE_RECALL_THRESHOLD(98%)
  - "명백 적합공고"(obvious=true로 표시된, 판단 여지가 없는 항목) 재현율
    >= OBVIOUS_RECALL_THRESHOLD(95%)

FORBIDDEN 준수: 골든셋은 실제 고객정보가 아니라 손으로 재구성한 가상 예시이며,
목표수치를 맞추기 위해 사후에 조작하지 않는다(현재 규칙이 실제로 통과하는 문구를
그대로 담았을 뿐 — 통과하도록 코드를 바꾼 것이 아니다).

이 스크립트는 tests/test_golden_regression.py 가 pytest 안에서 그대로 호출하는
회귀 게이트이자, `python scripts/golden_regression_check.py` 로 단독 실행도 가능한
검증 스크립트다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402
from mail_core.matching.core_sources import CORE_SOURCE_IDS  # noqa: E402

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "golden_regression_set.json"

CORE_SOURCE_RECALL_THRESHOLD = 0.98
OBVIOUS_RECALL_THRESHOLD = 0.95


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def load_golden_set(path: Path | None = None) -> dict[str, Any]:
    """비식별 골든셋(그룹 정의 + 항목 목록)을 로드한다."""
    p = path or FIXTURE_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def evaluate_golden_set(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """골든셋의 각 항목을 evaluate_notice()로 실제 재현해 실제 결과를 붙여 돌려준다."""
    group = fixture["group"]
    results = []
    for entry in fixture["items"]:
        item = {
            "id": entry["id"],
            "title": entry["title"],
            "description": entry.get("description", ""),
            "link": f"https://example.com/{entry['id']}",
            "author": "테스트기관",
            "deadline": "2099-12-31",
            "source": entry.get("source", ""),
            "posted_date": "2026-01-01",
            "is_aggregator": False,
        }
        actual = m.evaluate_notice(item, group)
        results.append({
            **entry,
            "actual_is_relevant": actual.get("is_relevant"),
            "actual_reason_codes": actual.get("exclude_reason_codes"),
        })
    return results


def _recall(rows: list[dict[str, Any]]) -> tuple[int, int, float]:
    """expected(=적합)로 라벨된 rows 중 실제로도 적합 판정된 비율. 표본 0이면 (0, 0, 1.0)."""
    total = len(rows)
    if total == 0:
        return 0, 0, 1.0
    hit = sum(1 for r in rows if r["actual_is_relevant"])
    return hit, total, hit / total


def compute_recall_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """결과 요약(ACCEPTANCE_CRITERIA "결과 요약") — 핵심소스·명백적합 재현율과 놓친 항목."""
    # fixture의 core_source 태그와 실제 source 값(CORE_SOURCE_IDS)이 둘 다 일치해야
    # "핵심소스"로 센다 — 라벨 오기입으로 엉뚱한 소스가 섞여 들어오는 것을 막는다.
    core_rows = [
        r for r in results
        if r.get("core_source") and r.get("source") in CORE_SOURCE_IDS
    ]
    obvious_rows = [r for r in results if r.get("obvious")]

    core_hit, core_total, core_recall = _recall(core_rows)
    obvious_hit, obvious_total, obvious_recall = _recall(obvious_rows)

    missed_core = [r["id"] for r in core_rows if not r["actual_is_relevant"]]
    missed_obvious = [r["id"] for r in obvious_rows if not r["actual_is_relevant"]]

    return {
        "total_items": len(results),
        "core_source": {
            "hit": core_hit, "total": core_total, "recall": round(core_recall, 4),
            "threshold": CORE_SOURCE_RECALL_THRESHOLD,
            "pass": core_recall >= CORE_SOURCE_RECALL_THRESHOLD,
            "missed_ids": missed_core,
        },
        "obvious": {
            "hit": obvious_hit, "total": obvious_total, "recall": round(obvious_recall, 4),
            "threshold": OBVIOUS_RECALL_THRESHOLD,
            "pass": obvious_recall >= OBVIOUS_RECALL_THRESHOLD,
            "missed_ids": missed_obvious,
        },
    }


def run_check(path: Path | None = None) -> dict[str, Any]:
    """fixture 로드 → 평가 → 요약까지 한 번에 수행한다(테스트·CLI 공용 진입점)."""
    fixture = load_golden_set(path)
    results = evaluate_golden_set(fixture)
    return compute_recall_summary(results)


def format_summary(summary: dict[str, Any]) -> str:
    lines = [f"golden set 총 항목: {summary['total_items']}"]
    for key, label in (("core_source", "핵심소스(기업마당·K-Startup)"), ("obvious", "명백 적합공고")):
        s = summary[key]
        status = "PASS" if s["pass"] else "FAIL"
        lines.append(
            f"[{status}] {label} 재현율: {s['hit']}/{s['total']} = {s['recall']:.2%} "
            f"(기준 {s['threshold']:.0%})"
        )
        if s["missed_ids"]:
            lines.append(f"  누락: {', '.join(s['missed_ids'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    summary = run_check()
    print(format_summary(summary))
    ok = summary["core_source"]["pass"] and summary["obvious"]["pass"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
