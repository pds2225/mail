r"""accuracy_baseline — 게이트 기준선(ratchet) 갱신 + 시계열(trend) 누적.

최신 매트릭스 실행의 summary.json 을 읽어:
  1) baseline_metrics.json 이 없으면 시딩(현재값=기준선).
  2) 있으면 ratchet 판정 — region_FP==0(하드) · region_recall≥baseline(하드) 위반 시 실패(exit 2).
     좋아지면(recall↑) baseline 갱신, 나빠지면 갱신 안 함(빨강 유지).
  3) trend.csv 에 이번 실행 1행 append(날짜별 시계열 — "계속 좋아지는 중" 증명).

산출물 (D:\mail\.omc\accuracy\):
  baseline_metrics.json   ratchet 기준선
  trend.csv               date,n_notices,region_FP,region_recall,denom,fp_cand,fn_cand,contradictions,matched_total

실행 (PowerShell, D:\mail 에서):
  python scripts\accuracy_baseline.py                     # 오늘 실행 폴더 사용
  python scripts\accuracy_baseline.py --run 2026-07-14    # 특정 실행 폴더
  python scripts\accuracy_baseline.py --seed              # 강제 재시딩(기준선 덮어쓰기)
종료코드: 0 통과 / 2 게이트 위반(region_FP>0 또는 recall 하락).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ACC_DIR = BASE_DIR / ".omc" / "accuracy"
BASELINE = ACC_DIR / "baseline_metrics.json"
TREND = ACC_DIR / "trend.csv"
RUNS = ACC_DIR / "runs"

_TREND_HEADER = [
    "date", "n_notices", "region_FP", "region_recall", "recall_denom",
    "fp_cand_total", "fn_cand_total", "contradictions", "matched_total",
    # 5필드 건전성(지역 외 4) 시계열 — 추출 완성도 추적
    "posted_ok", "period_ok", "deadline_unknown", "amount_present", "type_classified",
]


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _latest_run() -> Path | None:
    if not RUNS.exists():
        return None
    dirs = [d for d in RUNS.iterdir() if d.is_dir() and (d / "summary.json").exists()]
    return sorted(dirs)[-1] if dirs else None


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    ap = argparse.ArgumentParser(description="정확도 게이트 기준선/시계열 갱신")
    ap.add_argument("--run", default=None, help="실행 폴더명(예: 2026-07-14). 생략=최신")
    ap.add_argument("--seed", action="store_true", help="기준선 강제 재시딩")
    args = ap.parse_args(argv)

    run_dir = (RUNS / args.run) if args.run else _latest_run()
    if not run_dir or not (run_dir / "summary.json").exists():
        print(f"[SKIP] summary.json 없음: {run_dir}. 먼저 accuracy_matrix.py 실행 필요.")
        return 0
    s = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    kpi = s.get("kpi", {})
    region_fp = int(kpi.get("region_FP", 0))
    recall = kpi.get("region_recall_at_labeled")
    denom = int(kpi.get("region_recall_denom", 0))
    fp_total = sum((s.get("fp_candidate_counts") or {}).values())
    fn_total = sum((s.get("fn_candidate_counts") or {}).values())
    contra = int(s.get("contradiction_count", 0))
    matched_total = sum((s.get("matched_by_company") or {}).values())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ACC_DIR.mkdir(parents=True, exist_ok=True)

    # ── ratchet ──
    status = "OK"
    exit_code = 0
    if BASELINE.exists() and not args.seed:
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        base_recall = base.get("region_recall_at_labeled")
        if region_fp > 0:
            status = f"FAIL region_FP={region_fp}(>0)"
            exit_code = 2
        elif recall is not None and base_recall is not None and recall < base_recall - 1e-9:
            status = f"FAIL region_recall {recall} < baseline {base_recall}"
            exit_code = 2
        else:
            # 개선 시 기준선 갱신(recall↑ 또는 라벨분모↑)
            improved = (recall is not None and base_recall is not None and recall > base_recall) or (denom > int(base.get("region_recall_denom", 0)))
            if improved:
                base.update({
                    "updated_utc": now, "source_run": run_dir.name,
                    "n_notices": s.get("n_notices"), "region_FP": region_fp,
                    "region_recall_at_labeled": recall, "region_recall_denom": denom,
                    "matched_by_company": s.get("matched_by_company"),
                })
                BASELINE.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
                status = "OK (baseline↑ 갱신)"
    else:
        base = {
            "updated_utc": now, "source_run": run_dir.name,
            "n_notices": s.get("n_notices"), "region_FP": region_fp,
            "region_recall_at_labeled": recall, "region_recall_denom": denom,
            "matched_by_company": s.get("matched_by_company"),
            "gate": {
                "region_FP": "==0 (하드)",
                "region_recall_at_labeled": ">= baseline (하드)",
                "matched_total": "±drift 경보(소프트)",
            },
            "note": "정확도 게이트 ratchet 기준선. region_FP 0 유지·recall 비하락이 PR 병합 하드게이트.",
        }
        BASELINE.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "SEED (기준선 신규)"

    # 5필드 건전성(지역 외 4) 추출
    fh = s.get("field_health") or {}
    posted_ok = (fh.get("posted") or {}).get("ok", "")
    period_ok = (fh.get("period") or {}).get("ok", "")
    deadline_unknown = (fh.get("deadline_status") or {}).get("unknown", "")
    amount_present = (fh.get("amount") or {}).get("present", "")
    type_classified = (fh.get("type") or {}).get("classified", "")

    # ── trend append ──
    new_file = not TREND.exists()
    with TREND.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(_TREND_HEADER)
        w.writerow([run_dir.name, s.get("n_notices"), region_fp, recall, denom,
                    fp_total, fn_total, contra, matched_total,
                    posted_ok, period_ok, deadline_unknown, amount_present, type_classified])

    print(f"[baseline] {status}")
    print(f"[KPI] region_FP={region_fp} region_recall={recall}(분모{denom}) FP후보={fp_total} FN후보={fn_total} 모순={contra} 매칭총={matched_total}")
    print(f"[out] {BASELINE.name} / {TREND.name}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
