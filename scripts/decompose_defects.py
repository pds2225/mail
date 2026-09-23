#!/usr/bin/env python3
"""L2 accuracy-defect → 파생 TASKS.md 분해기 (G1 + root TASK 게이트).

사람(G1)이 승인한 빈틈도 루트 TASK.md의 READY/ACTIVE 작업에 연결될 때만
coding-fix PENDING으로 넣는다. 루트 TASK가 없으면 독립 작업을 만들지 않는다.
미승인 상태로 돌리면 미리보기만 하고 TASKS.md를 바꾸지 않는다.

Usage:
  python3 scripts/decompose_defects.py                                   # dry preview
  python3 scripts/decompose_defects.py --approve --root-task MAIL-014    # root TASK 하위 enqueue
  python3 scripts/decompose_defects.py --inbox auto_dev/defects_inbox.md
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "docs" / "project" / "TASKS.md"
ROOT_TASK_PATH = ROOT / "TASK.md"
DEFAULT_INBOX = ROOT / "auto_dev" / "defects_inbox.md"
KST = timezone(timedelta(hours=9))


def _configure_console_output() -> None:
    """Replace characters unsupported by the active Windows console codec."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def parse_defects(text: str) -> list[dict]:
    """간단 포맷:
    ## DEFECT-001
    title: ...
    approved: yes|no
    summary: ...
    """
    defects: list[dict] = []
    blocks = re.split(r"(?m)^##\s+(DEFECT-\d+)\s*$", text)
    # blocks: [preamble, id1, body1, id2, body2, ...]
    i = 1
    while i + 1 < len(blocks):
        did = blocks[i].strip()
        body = blocks[i + 1]
        i += 2
        def _field(name: str) -> str:
            m = re.search(rf"(?im)^{name}:\s*(.+)$", body)
            return m.group(1).strip() if m else ""

        approved_raw = _field("approved").lower()
        defects.append(
            {
                "id": did,
                "title": _field("title") or did,
                "approved": approved_raw in ("yes", "y", "true", "1", "승인"),
                "summary": _field("summary"),
                "loop": _field("loop") or "coding-fix",
            }
        )
    return defects


def next_task_id(tasks_text: str) -> int:
    nums = [int(x) for x in re.findall(r"TASK-(\d+)", tasks_text)]
    return (max(nums) if nums else 0) + 1


def root_task_is_active(root_text: str, task_id: str) -> bool:
    """Only READY/ACTIVE root MAIL tasks may authorize derived queue rows."""
    m = re.search(
        rf"(?m)^\[([ ~x!\-])\]\s+{re.escape(task_id)}\s+\|",
        root_text,
    )
    return bool(m and m.group(1) in {" ", "~"})


def insert_pending(tasks_text: str, lines: list[str]) -> str:
    out: list[str] = []
    inserted = False
    current = None
    for line in tasks_text.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            current = m.group(1).strip()
        out.append(line)
        if current == "PENDING" and m and not inserted:
            for tl in lines:
                out.append(tl)
            inserted = True
    if not inserted:
        out.extend(["", "## PENDING", ""] + lines)
    return "\n".join(out) + "\n"


def main() -> int:
    _configure_console_output()
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument(
        "--approve",
        action="store_true",
        help="G1 승인: approved=yes 인 결함만 파생 TASKS.md PENDING에 추가",
    )
    parser.add_argument(
        "--root-task",
        help="파생 큐의 부모 루트 TASK ID (예: MAIL-014). --approve 시 필수",
    )
    args = parser.parse_args()

    if not args.inbox.exists():
        print(f"[decompose] inbox 없음: {args.inbox}", file=sys.stderr)
        print("auto_dev/defects_inbox.md 템플릿을 채운 뒤 다시 실행하세요.", file=sys.stderr)
        return 1

    defects = parse_defects(args.inbox.read_text(encoding="utf-8"))
    if not defects:
        print("[decompose] 파싱된 DEFECT 없음")
        return 0

    approved = [d for d in defects if d["approved"]]
    pending_g1 = [d for d in defects if not d["approved"]]

    print(f"[decompose] total={len(defects)} approved={len(approved)} awaiting_g1={len(pending_g1)}")
    for d in pending_g1:
        print(f"  ⏸️  {d['id']}: {d['title']} (G1 대기)")
    for d in approved:
        print(f"  ✅ {d['id']}: {d['title']}")

    if not args.approve:
        print("[decompose] --approve 없음 → TASKS.md 미변경 (미리보기)")
        return 0

    if not approved:
        print("[decompose] 승인된 결함 없음 — enqueue 생략")
        return 0

    root_task = (args.root_task or "").strip().upper()
    if not re.fullmatch(r"MAIL-\d+", root_task):
        print("[decompose] --approve에는 --root-task MAIL-xxx가 필요합니다.", file=sys.stderr)
        return 2
    if not ROOT_TASK_PATH.exists():
        print("[decompose] 루트 TASK.md SSOT가 없습니다.", file=sys.stderr)
        return 2
    root_text = ROOT_TASK_PATH.read_text(encoding="utf-8")
    if not root_task_is_active(root_text, root_task):
        print(
            f"[decompose] {root_task}가 READY/ACTIVE가 아니므로 파생 큐를 만들지 않습니다.",
            file=sys.stderr,
        )
        return 2

    tasks = TASKS_PATH.read_text(encoding="utf-8")
    # 이미 enqueue된 defect id는 건너뜀
    n = next_task_id(tasks)
    new_lines: list[str] = []
    for d in approved:
        marker = d["id"]
        if marker in tasks:
            print(f"  skip already enqueued: {marker}")
            continue
        title = (
            f"loop:{d['loop']} [{marker}] {d['title']}"
            f" — {d['summary'][:60] if d['summary'] else 'G1 approved'}"
        )
        line = f"- TASK-{n:03d}: [ROOT={root_task}] {title}"
        new_lines.append(line)
        n += 1

    if not new_lines:
        print("[decompose] 신규 TASK 없음")
        return 0

    TASKS_PATH.write_text(insert_pending(tasks, new_lines), encoding="utf-8")
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print(f"[decompose] {stamp} enqueued {len(new_lines)} TASK(s)")
    for ln in new_lines:
        print(f"  + {ln}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
