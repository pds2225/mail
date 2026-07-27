#!/usr/bin/env python3
"""Auto Dev Safe Executor — LLM 없이 닫을 수 있는 TASK만 처리.

Loop Engineering L1의 '실행' 슬롯 중 결정적(deterministic) 부분.
- 이미 충족된 문서/규칙 TASK → DONE_NOOP
- 허용 파일에 대한 알려진 패턴 패치 → DONE_PATCHED
- 그 외 → NEEDS_AGENT (큐가 AWAITING_AGENT로 유지)

보호 파일(monitor.py, streamlit_app.py, .env*) 수정 금지.
실제 메일 발송 금지.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = frozenset({"monitor.py", "streamlit_app.py", ".env", ".env.example"})


@dataclass
class ExecResult:
    status: str  # DONE_NOOP | DONE_PATCHED | NEEDS_AGENT | BLOCKED
    reason: str
    changed_files: list[str] = field(default_factory=list)


def _read(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _assert_not_protected(paths: list[str]) -> ExecResult | None:
    bad = [p for p in paths if Path(p).name in PROTECTED or p in PROTECTED]
    if bad:
        return ExecResult("BLOCKED", f"보호 파일 수정 시도: {bad}", bad)
    return None


def _task_mentions(title: str, *needles: str) -> bool:
    t = title.lower()
    return any(n.lower() in t for n in needles)


def try_satisfy_docs(task_id: str, title: str) -> ExecResult | None:
    """문서/규칙이 이미 요구사항을 충족하면 NOOP 완료."""
    rules = _read("docs/project/RULES.md")
    agents = _read("AGENTS.md")
    readme = _read("README.md")
    workflow = _read(".github/workflows/auto-dev-queue.yml")
    queue_src = _read("scripts/auto_dev_queue.py")
    design = _read("docs/LOOP_ENGINEERING_AUTO_DEV.md")

    checks: list[tuple[tuple[str, ...], bool, str]] = [
        (
            ("실제 이메일", "발송 금지", "preview", "dry-run"),
            ("실제 이메일 자동 발송 금지" in rules and "preview/draft/dry-run" in rules.lower())
            or ("preview/dry-run" in rules.lower() and "발송" in rules and "금지" in rules),
            "RULES.md에 발송 금지·preview/dry-run 원칙 존재",
        ),
        (
            ("summary", "다음 task", "github actions summary"),
            ("write_summary" in queue_src and "다음 TASK" in queue_src),
            "auto_dev_queue Summary에 TASK/결과/다음 TASK 출력 존재",
        ),
        (
            ("마스킹", "이메일 주소", "수신자"),
            ("마스킹" in rules and "e***@" in rules),
            "RULES.md에 수신자 마스킹 원칙 존재",
        ),
        (
            ("환경변수", "secret", "vercel"),
            ("GMAIL_ADDRESS" in rules and "AUTO_DEV_PAT" in rules),
            "RULES.md에 Vercel/GHA Secret 목록 존재",
        ),
        (
            ("loop_verify", "5요소", "루프"),
            ("loop_verify" in workflow and "format_loop_summary" in queue_src),
            "GHA·큐에 loop_verify 및 루프 5요소 Summary 존재",
        ),
        (
            ("force_done", "허위 done", "awaiting_agent"),
            ("AWAITING_AGENT" in queue_src and "AUTO_DEV_FORCE_DONE" in queue_src),
            "허위 DONE 금지·FORCE_DONE 경로 코드 존재",
        ),
        (
            ("accuracy-defect", "s3_defects", "g1", "분해", "matrix →", "빈틈"),
            (
                (ROOT / "scripts" / "decompose_defects.py").exists()
                and (ROOT / "auto_dev" / "defects_inbox.md").exists()
                and "G1" in _read("auto_dev/human_gates.md")
            ),
            "decompose_defects + defects_inbox + G1 게이트 문서 존재",
        ),
        (
            ("loop engineering", "자동개발"),
            "Loop Engineering" in design or "루프 엔지니어링" in design,
            "설계 문서 존재",
        ),
    ]

    title_l = title.lower()
    for needles, ok, reason in checks:
        # 제목이 해당 주제면 충족 여부 판정
        if any(n in title_l for n in needles) or _task_mentions(title, *needles):
            if ok:
                return ExecResult("DONE_NOOP", f"{task_id}: {reason}")
            # 주제는 맞지만 미충족 → 에이전트/패치 필요
            return None
    return None


def try_patch_force_done_docs(task_id: str, title: str) -> ExecResult | None:
    """FORCE_DONE / 허위 DONE 문서가 약하면 RULES §8에 한 줄 보강."""
    if not _task_mentions(title, "FORCE_DONE", "허위 DONE", "AWAITING_AGENT"):
        return None
    rules_path = ROOT / "docs" / "project" / "RULES.md"
    text = rules_path.read_text(encoding="utf-8")
    if "AUTO_DEV_FORCE_DONE" in text and "AWAITING_AGENT" in text:
        return ExecResult("DONE_NOOP", "RULES에 FORCE_DONE/AWAITING_AGENT 이미 명시")
    marker = "## 8. Loop Engineering 규칙"
    if marker not in text:
        return ExecResult("NEEDS_AGENT", "RULES §8 없음 — 에이전트 필요")
    addition = (
        "\n| 8 | `AUTO_DEV_FORCE_DONE=true` 는 비상용. 기본은 `AWAITING_AGENT` |"
        " 코딩 슬롯 없이 DONE 강제 금지 |\n"
    )
    if "AUTO_DEV_FORCE_DONE" in text:
        return ExecResult("DONE_NOOP", "이미 문서화됨")
    # insert before end of section 8 table — append after last | 7 | line if present
    if "| 7 |" in text:
        text = text.replace(
            "| 7 | 사람 개입은 G1~G4만 (L1 무인 기본) |",
            "| 7 | 사람 개입은 G1~G4만 (L1 무인 기본) |\n"
            "| 8 | `AUTO_DEV_FORCE_DONE` 는 비상용(기본 금지). 슬롯 없으면 `AWAITING_AGENT` |"
            " 허위 DONE 회귀 방지 |",
            1,
        )
        blocked = _assert_not_protected(["docs/project/RULES.md"])
        if blocked:
            return blocked
        rules_path.write_text(text, encoding="utf-8")
        return ExecResult(
            "DONE_PATCHED",
            f"{task_id}: RULES에 FORCE_DONE 비상 규칙 추가",
            ["docs/project/RULES.md"],
        )
    return ExecResult("NEEDS_AGENT", "RULES 표 형식 불일치")


def try_enqueue_note_for_accuracy(task_id: str, title: str) -> ExecResult | None:
    """accuracy-defect 계열은 사람 게이트 — 실행기가 코딩하지 않음."""
    if not _task_mentions(title, "accuracy", "빈틈", "matrix", "G1", "s3_defects", "골든"):
        return None
    inbox = ROOT / "auto_dev" / "defects_inbox.md"
    if not inbox.exists():
        return ExecResult(
            "NEEDS_AGENT",
            "accuracy TASK는 G1 후 decompose_defects.py 사용 — 실행기 코딩 금지",
        )
    return ExecResult(
        "NEEDS_AGENT",
        "사람 게이트 G1: `python3 scripts/decompose_defects.py --approve` 후 재실행",
    )


def execute_task(task_id: str, title: str, *, dry_run: bool = False) -> ExecResult:
    """TASK 하나 시도. dry_run이면 파일 쓰지 않고 예상 결과만."""
    # 1) 이미 충족
    noop = try_satisfy_docs(task_id, title)
    if noop:
        return noop

    # 2) accuracy → 사람
    acc = try_enqueue_note_for_accuracy(task_id, title)
    if acc:
        return acc

    # 3) FORCE_DONE 문서 패치
    if dry_run:
        # 패치 계열은 dry-run에서 NEEDS_AGENT/예상만
        if _task_mentions(title, "FORCE_DONE", "허위 DONE"):
            rules = _read("docs/project/RULES.md")
            if "AUTO_DEV_FORCE_DONE" in rules:
                return ExecResult("DONE_NOOP", "dry-run: FORCE_DONE 문서 이미 존재")
            return ExecResult(
                "DONE_PATCHED",
                "dry-run: RULES 패치 예정(미적용)",
                ["docs/project/RULES.md"],
            )
        if _task_mentions(title, "소진공", "중진공", "selector", "정책자금") and (
            "검토" in title or "확장" in title
        ):
            if (ROOT / "auto_dev" / "loan_parser_review.md").exists():
                return ExecResult("DONE_NOOP", "dry-run: 정책자금 검토 메모 존재")
        return ExecResult("NEEDS_AGENT", "dry-run: 안전 실행기가 처리 불가 — 에이전트 필요")

    patched = try_patch_force_done_docs(task_id, title)
    if patched:
        return patched

    # 3b) 정책자금 검토 메모로 검토 TASK 종료
    if _task_mentions(title, "소진공", "중진공", "selector", "정책자금") and (
        "검토" in title or "확장" in title
    ):
        review = ROOT / "auto_dev" / "loan_parser_review.md"
        if review.exists() and task_id in review.read_text(encoding="utf-8"):
            return ExecResult("DONE_NOOP", f"{task_id}: 검토 메모로 범위 충족 ({review.name})")

    # 4) 소스/파서 등 → 에이전트
    if _task_mentions(title, "selector", "파서", "소진공", "중진공", "수집", "monitor"):
        return ExecResult("NEEDS_AGENT", "코드/파서 TASK — 코딩 에이전트 슬롯 필요")

    return ExecResult("NEEDS_AGENT", "매칭되는 안전 실행 규칙 없음")


def main() -> int:
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description="Safe auto-dev executor (single task)")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    # allow env dry-run
    dry = args.dry_run or os.environ.get("DRY_RUN", "").lower() == "true"
    r = execute_task(args.task_id, args.title, dry_run=dry)
    print(f"[executor] {r.status}: {r.reason}")
    if r.changed_files:
        print(f"[executor] changed: {', '.join(r.changed_files)}")
    if r.status in ("DONE_NOOP", "DONE_PATCHED"):
        return 0
    if r.status == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
