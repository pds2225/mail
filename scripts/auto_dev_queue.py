"""Auto Dev Queue — Vercel Mail 프로젝트 자동개발 큐 실행기

기능:
1. Preflight Check (필수 파일, 구조, 안전규칙 확인)
2. TASKS.md에서 다음 PENDING TASK 1개 선택
3. loops.json 기준으로 루프 타입·5요소 결정
4. loop_verify 게이트 실행 (종료 조건)
5. 에이전트 슬롯 없으면 AWAITING_AGENT (PENDING 유지) — 허위 DONE 금지
6. 실행 결과에 따라 DONE/FAILED/BLOCKED 처리
7. auto_dev_state.json 업데이트
8. GitHub Actions Summary 출력 (루프 5요소 포함)

주의:
- Secret/API Key/메일 계정 값은 절대 출력하지 않음
- 실제 이메일 발송 금지 (dry-run / draft-only 기준)
- 기존 앱 파일 수정 금지
- Mail 관련 Secret은 발송 기능 검증 전까지 미사용
- 설계: docs/LOOP_ENGINEERING_AUTO_DEV.md
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 상수 ─────────────────────────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = ROOT / "TASKS.md"
STATE_PATH = ROOT / "auto_dev_state.json"
DONE_PATH = ROOT / "done_tasks.md"
FAILED_PATH = ROOT / "failed_tasks.md"
BLOCKED_PATH = ROOT / "blocked_tasks.md"
LOOPS_PATH = ROOT / "auto_dev" / "loops.json"

PROTECTED_FILES = {"monitor.py", "streamlit_app.py", ".env", ".env.example"}
MAIL_SECRETS = {"GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "SMTP_HOST", "SMTP_PORT",
                "IMAP_HOST", "IMAP_PORT"}
MAX_RETRY = 2

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
# 실제 코딩 에이전트 슬롯 연결 시 true. 미설정이면 허위 DONE 하지 않음.
AGENT_ENABLED = os.environ.get("AUTO_DEV_AGENT", "false").lower() == "true"
# 레거시: 검증만 통과하면 DONE (에이전트 없이). 기본 false.
FORCE_DONE = os.environ.get("AUTO_DEV_FORCE_DONE", "false").lower() == "true"
VERIFY_QUICK = os.environ.get("AUTO_DEV_VERIFY_QUICK", "true").lower() == "true"
VERIFY_CORE = os.environ.get("AUTO_DEV_VERIFY_CORE", "false").lower() == "true"


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[auto-dev-queue] {msg}")


def write_summary(text: str) -> None:
    """GitHub Actions Job Summary에 출력"""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_run": None, "last_task": None, "retry_counts": {}}


def save_state(state: dict) -> None:
    state["last_run"] = datetime.now(KST).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_to_log(path: Path, task_id: str, title: str, reason: str = "") -> None:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    entry = f"- [{now}] {task_id}: {title}"
    if reason:
        entry += f" — {reason}"
    entry += "\n"
    if not path.exists():
        path.write_text(f"# {path.stem.replace('_', ' ').title()}\n\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


# ── TASKS.md 파서 ────────────────────────────────────────────────────────────

def parse_tasks(content: str) -> dict[str, list[str]]:
    """TASKS.md를 섹션별로 파싱. 반환: {섹션명: [라인들]}"""
    sections: dict[str, list[str]] = {}
    current_section = None
    for line in content.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            current_section = m.group(1).strip()
            sections[current_section] = []
        elif current_section is not None and line.strip().startswith("- TASK-"):
            sections[current_section].append(line.strip())
    return sections


def extract_task_info(task_line: str) -> tuple[str, str]:
    """'- TASK-001: 설명' → ('TASK-001', '설명')"""
    m = re.match(r"^- (TASK-\d+):\s*(.+)$", task_line)
    if m:
        return m.group(1), m.group(2)
    return "", task_line


def move_task(content: str, task_line: str, from_section: str, to_section: str) -> str:
    """TASKS.md 내용에서 task를 from → to 섹션으로 이동"""
    lines = content.splitlines()
    result = []
    removed = False
    inserted = False

    current_section = None
    for line in lines:
        m = re.match(r"^## (.+)$", line)
        if m:
            current_section = m.group(1).strip()

        if current_section == from_section and line.strip() == task_line and not removed:
            removed = True
            continue

        result.append(line)

        if current_section == to_section and m and not inserted:
            result.append(task_line)
            inserted = True

    if not inserted:
        result.append(f"\n## {to_section}\n\n{task_line}")

    return "\n".join(result) + "\n"


def rebuild_tasks_md(sections: dict[str, list[str]], header: str) -> str:
    """섹션 딕셔너리에서 TASKS.md 재구성"""
    lines = [header.strip(), ""]
    for section_name in ["PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"]:
        lines.append(f"## {section_name}")
        lines.append("")
        for task in sections.get(section_name, []):
            lines.append(task)
        lines.append("")
    return "\n".join(lines)


# ── Preflight Check ──────────────────────────────────────────────────────────

def preflight_check() -> list[str]:
    """사전 검증. 문제 목록 반환 (비어있으면 통과)"""
    issues: list[str] = []

    # 1. 필수 파일 존재 여부
    if not TASKS_PATH.exists():
        issues.append("TASKS.md 파일이 없습니다")
        return issues

    # 2. TASKS.md 구조 확인
    content = TASKS_PATH.read_text(encoding="utf-8")
    for section in ["PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED"]:
        if f"## {section}" not in content:
            issues.append(f"TASKS.md에 ## {section} 섹션이 없습니다")

    # 3. RULES.md 존재
    if not (ROOT / "RULES.md").exists():
        issues.append("RULES.md 파일이 없습니다")

    # 3b. Loop Engineering 작업 자산
    for rel in (
        "auto_dev/loops.json",
        "auto_dev/eval_rubric.md",
        "auto_dev/exit_conditions.md",
        "auto_dev/human_gates.md",
        "docs/LOOP_ENGINEERING_AUTO_DEV.md",
        "scripts/loop_verify.py",
    ):
        if not (ROOT / rel).exists():
            issues.append(f"루프 작업 자산 누락: {rel}")

    # 4. 앱 진입점 확인
    for pf in PROTECTED_FILES:
        full = ROOT / pf
        if not full.exists() and pf in ("monitor.py", "streamlit_app.py"):
            issues.append(f"앱 진입점 파일 누락: {pf}")

    # 5. 이메일 발송 관련 파일이 보호 대상인지 확인
    for pf in PROTECTED_FILES:
        if (ROOT / pf).exists():
            log(f"  🔒 보호 파일 확인: {pf}")

    # 6. Secret 이름 안내 (값은 출력하지 않음)
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        log("  ℹ️ GITHUB_TOKEN 미설정 (PR 생성 시 필요)")

    return issues


# ── 이메일 발송 위험 감지 ────────────────────────────────────────────────────

def check_email_send_risk(task_title: str) -> bool:
    """TASK 제목에 실제 발송 위험 키워드가 있는지 확인"""
    danger_keywords = ["실제 발송", "send email", "smtp send", "메일 발송 실행",
                       "이메일 전송", "real send", "production send",
                       "imap connect", "smtp connect", "메일 연결"]
    title_lower = task_title.lower()
    return any(kw in title_lower for kw in danger_keywords)


# ── Loop Engineering 헬퍼 ─────────────────────────────────────────────────────

def load_loops() -> dict:
    if not LOOPS_PATH.exists():
        return {"loops": {}, "defaults": {"max_retry": MAX_RETRY}}
    try:
        return json.loads(LOOPS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"loops": {}, "defaults": {"max_retry": MAX_RETRY}}


def parse_task_meta(task_title: str) -> tuple[str, str]:
    """제목에서 optional `loop:name` 메타 추출. 반환 (loop_key, cleaned_title)."""
    m = re.search(r"\bloop:([a-z0-9\-]+)\b", task_title, re.I)
    if m:
        key = m.group(1).lower()
        cleaned = (task_title[: m.start()] + task_title[m.end() :]).strip(" -—:")
        return key, cleaned or task_title
    return "", task_title


def infer_loop_key(task_title: str) -> str:
    meta, _ = parse_task_meta(task_title)
    if meta:
        return meta
    t = task_title.lower()
    if any(k in t for k in ("coverage", "수집", "core_sources", "3대 소스", "checklist")):
        return "coverage-sentinel"
    if any(k in t for k in ("fp", "fn", "accuracy", "골든", "빈틈", "matrix", "오탐", "누락")):
        return "accuracy-defect"
    if any(k in t for k in ("gate", "리콜", "recall", "pytest 실패", "회귀", "fix task")):
        return "gate-repair"
    if any(k in t for k in ("고객", "intake", "수신자 요청", "비전", "제휴")):
        return "product-vision"
    return "coding-fix"


def format_loop_summary(loop_key: str, loop: dict | None) -> str:
    if not loop:
        return f"**루프:** `{loop_key}` (정의 없음 — ESC_UNKNOWN_EXIT)\n"
    trigger = ", ".join(loop.get("trigger") or []) or "—"
    execute = ", ".join(loop.get("execute") or []) or "—"
    verify = ", ".join(loop.get("verify") or []) or "—"
    memory = ", ".join(loop.get("memory") or []) or "—"
    exit_block = loop.get("exit") or {}
    exit_s = (
        f"success={exit_block.get('success')}; "
        f"escalate={exit_block.get('escalate')}"
    )
    gate = loop.get("human_gate") or "없음(L1 무인)"
    return (
        f"**루프:** `{loop_key}` ({loop.get('id', '?')} / {loop.get('tier', '?')}) "
        f"— {loop.get('name', '')}\n\n"
        f"| 요소 | 내용 |\n|------|------|\n"
        f"| 트리거 | {trigger} |\n"
        f"| 실행 | {execute} |\n"
        f"| 검증 | {verify} |\n"
        f"| 메모리 | {memory} |\n"
        f"| 종료 | {exit_s} |\n"
        f"| 사람 게이트 | {gate} |\n"
    )


def run_loop_verify() -> dict:
    """scripts/loop_verify.py 호출. Secret 미출력."""
    cmd = [sys.executable, str(ROOT / "scripts" / "loop_verify.py"), "--json"]
    if VERIFY_QUICK:
        cmd.append("--quick")
    if VERIFY_CORE:
        cmd.append("--with-core-sources")
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e), "checks": []}
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        data = {"ok": proc.returncode == 0, "raw_tail": (proc.stdout or proc.stderr or "")[-500:]}
    data.setdefault("ok", proc.returncode == 0)
    data["exit_code"] = proc.returncode
    return data


def next_task_id(sections: dict[str, list[str]]) -> str:
    """TASKS 전체에서 최대 번호+1."""
    max_n = 0
    for tasks in sections.values():
        for line in tasks:
            m = re.match(r"^- (TASK-(\d+)):", line)
            if m:
                max_n = max(max_n, int(m.group(2)))
    return f"TASK-{max_n + 1:03d}"


def insert_pending_task(content: str, task_line: str) -> str:
    """PENDING 섹션 헤더 바로 아래에 task 한 줄 삽입."""
    lines = content.splitlines()
    result = []
    inserted = False
    current = None
    for line in lines:
        m = re.match(r"^## (.+)$", line)
        if m:
            current = m.group(1).strip()
        result.append(line)
        if current == "PENDING" and m and not inserted:
            result.append(task_line)
            inserted = True
    if not inserted:
        result.append("")
        result.append("## PENDING")
        result.append("")
        result.append(task_line)
    return "\n".join(result) + "\n"


def create_fix_task(content: str, parent_id: str, parent_title: str, reason: str) -> tuple[str, str]:
    sections = parse_tasks(content)
    fix_id = next_task_id(sections)
    title = f"loop:gate-repair FIX {parent_id} — {reason[:80]}"
    task_line = f"- {fix_id}: {title}"
    return insert_pending_task(content, task_line), fix_id


# ── 메인 실행 ────────────────────────────────────────────────────────────────

def main() -> int:
    log("=== Auto Dev Queue 시작 ===")
    log(f"DRY_RUN: {DRY_RUN} AGENT_ENABLED: {AGENT_ENABLED} FORCE_DONE: {FORCE_DONE}")
    log(f"시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")

    # 1. Preflight Check
    log("--- Preflight Check ---")
    issues = preflight_check()
    if issues:
        for issue in issues:
            log(f"  ❌ {issue}")
        write_summary("## ❌ Preflight Check 실패\n\n" + "\n".join(f"- {i}" for i in issues))
        return 1
    log("  ✅ Preflight Check 통과")

    loops_doc = load_loops()
    loops = loops_doc.get("loops") or {}

    # 2. 상태 로드
    state = load_state()

    # 3. TASKS.md 읽기 및 파싱
    content = TASKS_PATH.read_text(encoding="utf-8")
    sections = parse_tasks(content)

    pending = sections.get("PENDING", [])
    if not pending:
        log("  ℹ️ PENDING 작업 없음 — drift verify만 수행")
        verify = run_loop_verify()
        drift_cmd = [sys.executable, str(ROOT / "scripts" / "loop_verify.py"), "--drift", "--json"]
        try:
            drift_proc = subprocess.run(drift_cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
            drift = json.loads(drift_proc.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            drift = {"ok": False}
        write_summary(
            "## ✅ Auto Dev Queue\n\n처리할 PENDING 작업이 없습니다.\n\n"
            f"- loop_verify: {'pass' if verify.get('ok') else 'fail'}\n"
            f"- drift: {'pass' if drift.get('ok') else 'fail'}\n"
        )
        save_state(state)
        return 0 if verify.get("ok", False) else 1

    # 4. 다음 TASK 선택
    task_line = pending[0]
    task_id, task_title = extract_task_info(task_line)
    loop_key = infer_loop_key(task_title)
    loop = loops.get(loop_key)
    log(f"  📋 선택: {task_id} — {task_title}")
    log(f"  🔁 루프: {loop_key}")

    if not loop:
        log(f"  🚫 루프 정의 없음 → BLOCKED (ESC_UNKNOWN_EXIT)")
        if not DRY_RUN:
            new_content = move_task(content, task_line, "PENDING", "BLOCKED")
            TASKS_PATH.write_text(new_content, encoding="utf-8")
            append_to_log(BLOCKED_PATH, task_id, task_title, "루프 정의 없음 — write 권한 회수")
        state["last_task"] = task_id
        save_state(state)
        write_summary(
            f"## 🚫 BLOCKED (ESC_UNKNOWN_EXIT)\n\n`{task_id}`: {task_title}\n\n"
            f"루프 `{loop_key}` 가 loops.json에 없습니다."
        )
        return 0

    # 5. 재시도 횟수 확인
    retry_count = state.get("retry_counts", {}).get(task_id, 0)
    if retry_count >= MAX_RETRY:
        log(f"  ⚠️ {task_id} 최대 재시도 횟수({MAX_RETRY}) 초과 → BLOCKED")
        if not DRY_RUN:
            new_content = move_task(content, task_line, "PENDING", "BLOCKED")
            TASKS_PATH.write_text(new_content, encoding="utf-8")
            append_to_log(BLOCKED_PATH, task_id, task_title, f"최대 재시도 {MAX_RETRY}회 초과")
        state["last_task"] = task_id
        save_state(state)
        write_summary(
            f"## ⚠️ BLOCKED\n\n`{task_id}`: {task_title}\n\n사유: 최대 재시도 횟수 초과\n\n"
            + format_loop_summary(loop_key, loop)
        )
        return 0

    # 6. 이메일 발송 위험 감지
    if check_email_send_risk(task_title):
        log(f"  🚫 {task_id} 이메일 발송 위험 감지 → BLOCKED")
        if not DRY_RUN:
            new_content = move_task(content, task_line, "PENDING", "BLOCKED")
            TASKS_PATH.write_text(new_content, encoding="utf-8")
            append_to_log(BLOCKED_PATH, task_id, task_title, "이메일 발송 위험 감지 — 수동 처리 필요")
        state["last_task"] = task_id
        save_state(state)
        write_summary(
            f"## 🚫 BLOCKED (이메일 안전규칙 / G4)\n\n`{task_id}`: {task_title}\n\n"
            + format_loop_summary(loop_key, loop)
        )
        return 0

    # 6b. 사람 게이트 필요 루프는 자동 코딩 금지
    human_gate = loop.get("human_gate")
    if human_gate and loop_key in ("accuracy-defect", "product-vision"):
        log(f"  ⏸️ {task_id} 사람 게이트 {human_gate} 필요 — PENDING 유지")
        write_summary(
            f"## ⏸️ AWAITING_HUMAN ({human_gate})\n\n"
            f"`{task_id}`: {task_title}\n\n"
            f"이 루프는 사람 승인 전 L1 실행 금지.\n\n"
            + format_loop_summary(loop_key, loop)
        )
        state["last_task"] = task_id
        state["last_result"] = "AWAITING_HUMAN"
        save_state(state)
        return 0

    # 7. DRY_RUN: 미리보기만
    if DRY_RUN:
        log("  🏷️ DRY_RUN: 실제 변경 없이 미리보기 종료")
        write_summary(
            f"## 🏷️ Dry Run\n\n"
            f"다음 처리 대상: `{task_id}`: {task_title}\n\n"
            + format_loop_summary(loop_key, loop)
            + "\n실제 변경은 수행하지 않았습니다."
        )
        save_state(state)
        return 0

    # 8. RUNNING으로 이동
    new_content = move_task(content, task_line, "PENDING", "RUNNING")
    TASKS_PATH.write_text(new_content, encoding="utf-8")
    log(f"  ▶ RUNNING: {task_id}")

    # 9. 검증 게이트 (종료 조건의 핵심)
    log("--- loop_verify ---")
    verify = run_loop_verify()
    verify_ok = bool(verify.get("ok"))
    log(f"  loop_verify: {'✅' if verify_ok else '❌'}")

    if not verify_ok:
        task_result = "FAILED"
        task_reason = "loop_verify 실패 — 종료 조건 FAIL_RETRY"
        failed_content = move_task(
            TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "FAILED"
        )
        failed_content, fix_id = create_fix_task(
            failed_content, task_id, task_title, "loop_verify failed"
        )
        TASKS_PATH.write_text(failed_content, encoding="utf-8")
        append_to_log(FAILED_PATH, task_id, task_title, task_reason)
        retry_counts = state.get("retry_counts", {})
        retry_counts[task_id] = retry_count + 1
        state["retry_counts"] = retry_counts
        state["last_task"] = task_id
        state["last_result"] = task_result
        save_state(state)
        write_summary(
            f"## ❌ FAILED\n\n"
            f"**처리:** `{task_id}`: {task_title}\n"
            f"**결과:** {task_result}\n"
            f"**사유:** {task_reason}\n"
            f"**FIX TASK:** `{fix_id}`\n\n"
            + format_loop_summary(loop_key, loop)
        )
        log(f"  ❌ FAILED + FIX {fix_id}")
        return 1

    # 10. 에이전트 슬롯
    if not AGENT_ENABLED and not FORCE_DONE:
        # 허위 DONE 금지: RUNNING → PENDING 복귀
        back = move_task(
            TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "PENDING"
        )
        TASKS_PATH.write_text(back, encoding="utf-8")
        task_result = "AWAITING_AGENT"
        task_reason = (
            "loop_verify 통과. AUTO_DEV_AGENT 미설정 — 코딩 슬롯 대기 "
            "(허위 DONE 금지). 설계 P4 참고."
        )
        state["last_task"] = task_id
        state["last_result"] = task_result
        save_state(state)
        remaining = parse_tasks(TASKS_PATH.read_text(encoding="utf-8")).get("PENDING", [])
        next_info = ""
        if remaining:
            nid, ntitle = extract_task_info(remaining[0])
            next_info = f"\n\n**다음 TASK:** `{nid}`: {ntitle}"
        write_summary(
            f"## ⏸️ AWAITING_AGENT\n\n"
            f"**처리:** `{task_id}`: {task_title}\n"
            f"**결과:** {task_result}\n"
            f"**사유:** {task_reason}\n\n"
            + format_loop_summary(loop_key, loop)
            + next_info
        )
        log(f"  ⏸️ AWAITING_AGENT: {task_id}")
        log("=== 완료 ===")
        return 0

    # 11. 에이전트 활성 또는 FORCE_DONE — 슬롯 placeholder
    if AGENT_ENABLED:
        task_result = "DONE"
        task_reason = "AUTO_DEV_AGENT=true — 외부 에이전트 슬롯이 패치를 완료한 것으로 간주(연동 P4)"
    else:
        task_result = "DONE"
        task_reason = "AUTO_DEV_FORCE_DONE=true — 검증 통과 후 강제 DONE"

    final_content = move_task(
        TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "DONE"
    )
    TASKS_PATH.write_text(final_content, encoding="utf-8")
    append_to_log(DONE_PATH, task_id, task_title)
    state["last_task"] = task_id
    state["last_result"] = task_result
    save_state(state)

    remaining_sections = parse_tasks(TASKS_PATH.read_text(encoding="utf-8"))
    next_pending = remaining_sections.get("PENDING", [])
    next_info = ""
    if next_pending:
        next_id, next_title = extract_task_info(next_pending[0])
        next_info = f"\n\n**다음 TASK:** `{next_id}`: {next_title}"

    write_summary(
        f"## ✅ Auto Dev Queue 결과\n\n"
        f"**처리:** `{task_id}`: {task_title}\n"
        f"**결과:** {task_result}\n"
        f"**사유:** {task_reason}\n\n"
        + format_loop_summary(loop_key, loop)
        + next_info
    )
    log(f"  ✅ DONE: {task_id}")
    log("=== 완료 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
