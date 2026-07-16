r"""predev_goal_diagnose — 개발 착수 전 '예상 개발목표'를 실사용 기준으로 자가진단.

사용자 요청(2026-07-16): "사전에 개발예상목표를 실제사용기준으로 진단한다 — 훅으로."
개발을 시작하기 전에, 이 프로젝트가 '실제 사용자에게 제대로 동작하는가'를 지표·상태로 진단해
아직 실사용 기준 미달인 목표(=다음에 개발할 것)를 우선순위로 뽑아 준다. 자가개발 루프의 Loop 0.

판정은 추측이 아니라 실측(최신 accuracy summary + RESUME 미결 + 회귀테스트 존재)으로 한다.
읽기 전용(코드·데이터 미수정). 각 목표에 '실사용 기준(done_when)'과 현재 상태를 붙인다.

실행 (PowerShell, D:\mail):
  python scripts\predev_goal_diagnose.py            # 사람이 읽는 진단표
  python scripts\predev_goal_diagnose.py --json      # 기계판독(훅/오케 입력)
종료코드: 0 = 실사용 기준 모두 충족(개발할 것 없음) / 1 = 미달 목표 존재(개발 대상 있음).

훅 연결(사용자가 settings.json에 등록 — 에이전트는 권한파일 자가수정 불가):
  UserPromptSubmit 훅에서 개발 키워드(개발/자동개발/무인/목표) 감지 시 이 스크립트를 --json 으로
  실행해 결과를 컨텍스트로 주입 → "무엇을 개발할지"를 실사용 기준으로 먼저 못박는다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _fix_console() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _latest_summary() -> dict:
    runs = BASE_DIR / ".omc" / "accuracy" / "runs"
    if not runs.exists():
        return {}
    dirs = [d for d in runs.iterdir() if d.is_dir() and (d / "summary.json").exists()]
    if not dirs:
        return {}
    try:
        return json.loads((sorted(dirs)[-1] / "summary.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _resume_open_items() -> list[str]:
    """RESUME.md 에서 '미결/대기/미해결/승인 필요' 같은 사용자-미해결 신호 줄을 뽑는다."""
    rp = BASE_DIR / "RESUME.md"
    if not rp.exists():
        return []
    out: list[str] = []
    pat = re.compile(r"(미결|미해결|대기|승인 필요|승인필요|남은 것|미완|보류)")
    for line in rp.read_text(encoding="utf-8").splitlines():
        s = line.strip("-* \t")
        if pat.search(s) and len(s) > 8:
            out.append(s[:160])
    # 중복 제거(앞 40자 기준), 최신 우선 상위 12
    seen: set[str] = set()
    uniq: list[str] = []
    for s in out:
        k = s[:40]
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq[:12]


def diagnose() -> dict:
    s = _latest_summary()
    kpi = (s.get("kpi") or {})
    fh = (s.get("field_health") or {})
    fc = (s.get("field_candidate_counts") or {})

    def _get(field, key):
        return int((fh.get(field) or {}).get(key, 0))

    goals: list[dict] = []

    # ── 실사용 기준 목표(measured) ──
    region_fp = int(kpi.get("region_FP", 0))
    goals.append({
        "goal": "지역 오추천 0 유지",
        "done_when": "region_FP == 0 (타지역 공고가 기업에 잘못 안 감)",
        "current": f"region_FP={region_fp}",
        "met": region_fp == 0,
        "severity": "hard",
    })
    recall = kpi.get("region_recall_at_labeled")
    goals.append({
        "goal": "지역 누락 0 유지(recall 1순위)",
        "done_when": "region_recall_at_labeled >= 1.0 & 지역차단 FN == 0",
        "current": f"recall={recall}, region_recall_fn={kpi.get('region_recall_fn')}",
        "met": (recall is not None and recall >= 1.0 and int(kpi.get("region_recall_fn", 0)) == 0),
        "severity": "hard",
    })
    # 5필드 표시 완성도(실사용: 메일에 날짜·유형이 채워져 나가나)
    n = int(s.get("n_notices", 0)) or 1
    period_missing = _get("period", "missing")
    goals.append({
        "goal": "접수기간(마감) 표시 완성",
        "done_when": "접수기간 판정불명이 감소 추세(빈 마감으로 나가는 공고↓)",
        "current": f"접수기간 없음 {period_missing}/{n} ({round(100*period_missing/n)}%)",
        "met": period_missing <= n * 0.30,
        "severity": "soft",
        "fix_hint": "리스트-온리 소스 detail-enrich(bizok·ic_bupyeong·sehub) + '수시모집' 상시어",
    })
    type_uncls = _get("type", "unclassified")
    goals.append({
        "goal": "지원유형(성격) 표시 완성",
        "done_when": "'그외' 미분류가 감소(전시회·수출·기술지원 등 명확신호는 유형 표기)",
        "current": f"성격 미분류 {type_uncls}/{n} ({round(100*type_uncls/n)}%)",
        "met": type_uncls <= n * 0.50,
        "severity": "soft",
        "fix_hint": "SUPPORT_TYPE_RULES 기존 버킷에 전시회/수출/융자/기술지원 키워드 추가('그외' 게이트 중립 유지)",
    })
    posted_bad = _get("posted", "missing") + _get("posted", "bad")
    goals.append({
        "goal": "게시일 표시 완성",
        "done_when": "게시일 없음/불량 감소",
        "current": f"게시일 없음/불량 {posted_bad}/{n}",
        "met": posted_bad <= n * 0.10,
        "severity": "soft",
        "fix_hint": "대부분 목록스크랩 소스의 본문·등록일 미저장(크롤러 변경 필요) + 공고번호 day-00 오파싱 차단",
    })

    # ── RESUME 미해결 사용자 요청(복기) ──
    resume_open = _resume_open_items()

    met = [g for g in goals if g["met"]]
    unmet = [g for g in goals if not g["met"]]
    return {
        "measured_from": s.get("date_filter") or "N/A",
        "n_notices": s.get("n_notices"),
        "goals": goals,
        "met_count": len(met),
        "unmet_count": len(unmet),
        "unmet_goals": unmet,
        "resume_open_items": resume_open,
        "all_realuse_met": len(unmet) == 0,
    }


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    ap = argparse.ArgumentParser(description="개발 착수 전 실사용 기준 목표 진단")
    ap.add_argument("--json", action="store_true", help="기계판독 JSON 출력")
    args = ap.parse_args(argv)

    d = diagnose()
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0 if d["all_realuse_met"] else 1

    print("=== 개발 착수 전 실사용 기준 목표 진단 ===")
    print(f"측정: 공고 {d['n_notices']} (accuracy runs 최신)  |  충족 {d['met_count']} · 미달 {d['unmet_count']}")
    for g in d["goals"]:
        mark = "✅" if g["met"] else "❌"
        print(f"  {mark} {g['goal']}  [{g['severity']}]")
        print(f"       기준: {g['done_when']}")
        print(f"       현재: {g['current']}")
        if not g["met"] and g.get("fix_hint"):
            print(f"       →픽스: {g['fix_hint']}")
    if d["resume_open_items"]:
        print("\n[RESUME 미해결 사용자 요청 복기]")
        for s in d["resume_open_items"]:
            print(f"  · {s}")
    print(f"\n[결론] 실사용 기준 {'전부 충족(개발할 것 없음)' if d['all_realuse_met'] else str(d['unmet_count'])+'개 목표 미달 → 개발 대상'}")
    return 0 if d["all_realuse_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
