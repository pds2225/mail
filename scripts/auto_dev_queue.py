"""Auto Dev Queue — Mail 프로젝트 자동개발 큐 실행기

기능:
1. Preflight Check (필수 파일, 구조, 안전규칙 확인)
2. TASKS.md에서 다음 PENDING TASK 1개 선택
3. TASK를 RUNNING으로 이동
4. 실행 결과에 따라 DONE/FAILED/BLOCKED 처리
5. auto_dev_state.json 업데이트
6. GitHub Actions Summary 출력

주의:
- Secret/API Key/메일 계정 값은 절대 출력하지 않음
- 실제 이메일 발송 금지
- 기존 앱 파일 수정 금지
"""
from __future__ import annotations

import json
import os
import re
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

PROTECTED_FILES = {"monitor.py", "streamlit_app.py", ".env", ".env.example"}
MAX_RETRY = 2

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


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

    if not TASKS_PATH.exists():
        issues.append("TASKS.md 파일이 없습니다")
        return issues

    content = TASKS_PATH.read_text(encoding="utf-8")

    if "## PENDING" not in content:
        issues.append("TASKS.md에 ## PENDING 섹션이 없습니다")
    if "## RUNNING" not in content:
        issues.append("TASKS.md에 ## RUNNING 섹션이 없습니다")
    if "## DONE" not in content:
        issues.append("TASKS.md에 ## DONE 섹션이 없습니다")
    if "## FAILED" not in content:
        issues.append("TASKS.md에 ## FAILED 섹션이 없습니다")
    if "## BLOCKED" not in content:
        issues.append("TASKS.md에 ## BLOCKED 섹션이 없습니다")

    rules_path = ROOT / "RULES.md"
    if not rules_path.exists():
        issues.append("RULES.md 파일이 없습니다")

    for pf in PROTECTED_FILES:
        full = ROOT / pf
        if not full.exists() and pf in ("monitor.py", "streamlit_app.py"):
            issues.append(f"앱 진입점 파일 누락: {pf}")

    return issues


# ── 이메일 발송 위험 감지 ────────────────────────────────────────────────────

def check_email_send_risk(task_title: str) -> bool:
    """TASK 제목에 실제 발송 위험 키워드가 있는지 확인"""
    danger_keywords = ["실제 발송", "send email", "smtp send", "메일 발송 실행",
                       "이메일 전송", "real send", "production send"]
    title_lower = task_title.lower()
    return any(kw in title_lower for kw in danger_keywords)


# ── 메인 실행 ────────────────────────────────────────────────────────────────

def main() -> int:
    log("=== Auto Dev Queue 시작 ===")
    log(f"DRY_RUN: {DRY_RUN}")
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

    # 2. 상태 로드
    state = load_state()

    # 3. TASKS.md 읽기 및 파싱
    content = TASKS_PATH.read_text(encoding="utf-8")
    sections = parse_tasks(content)

    pending = sections.get("PENDING", [])
    if not pending:
        log("  ℹ️ PENDING 작업 없음. 종료.")
        write_summary("## ✅ Auto Dev Queue\n\n처리할 PENDING 작업이 없습니다.")
        save_state(state)
        return 0

    # 4. 다음 TASK 선택
    task_line = pending[0]
    task_id, task_title = extract_task_info(task_line)
    log(f"  📋 선택: {task_id} — {task_title}")

    # 5. 재시도 횟수 확인
    retry_count = state.get("retry_counts", {}).get(task_id, 0)
    if retry_count >= MAX_RETRY:
        log(f"  ⚠️ {task_id} 최대 재시도 횟수({MAX_RETRY}) 초과 → BLOCKED")
        new_content = move_task(content, task_line, "PENDING", "BLOCKED")
        TASKS_PATH.write_text(new_content, encoding="utf-8")
        append_to_log(BLOCKED_PATH, task_id, task_title, f"최대 재시도 {MAX_RETRY}회 초과")
        state["last_task"] = task_id
        save_state(state)
        write_summary(f"## ⚠️ BLOCKED\n\n`{task_id}`: {task_title}\n\n사유: 최대 재시도 횟수 초과")
        return 0

    # 6. 이메일 발송 위험 감지
    if check_email_send_risk(task_title):
        log(f"  🚫 {task_id} 이메일 발송 위험 감지 → BLOCKED")
        new_content = move_task(content, task_line, "PENDING", "BLOCKED")
        TASKS_PATH.write_text(new_content, encoding="utf-8")
        append_to_log(BLOCKED_PATH, task_id, task_title, "이메일 발송 위험 감지 — 수동 처리 필요")
        state["last_task"] = task_id
        save_state(state)
        write_summary(f"## 🚫 BLOCKED (이메일 안전규칙)\n\n`{task_id}`: {task_title}")
        return 0

    # 7. RUNNING으로 이동
    new_content = move_task(content, task_line, "PENDING", "RUNNING")
    if not DRY_RUN:
        TASKS_PATH.write_text(new_content, encoding="utf-8")

    log(f"  ▶ RUNNING: {task_id}")

    # 8. TASK 실행 (현재는 placeholder — 향후 AI 연동)
    # 실제 TASK 처리 로직은 향후 구현
    # 지금은 구조만 설정: PENDING → RUNNING → DONE/FAILED
    task_result = "DONE"
    task_reason = "큐 인프라 설치 완료 — 실제 TASK 처리는 향후 구현"

    if DRY_RUN:
        log(f"  🏷️ DRY_RUN: 실제 변경 없이 미리보기 종료")
        write_summary(
            f"## 🏷️ Dry Run\n\n"
            f"다음 처리 대상: `{task_id}`: {task_title}\n\n"
            f"실제 변경은 수행하지 않았습니다."
        )
        save_state(state)
        return 0

    # 9. 결과 처리
    if task_result == "DONE":
        final_content = move_task(
            TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "DONE"
        )
        TASKS_PATH.write_text(final_content, encoding="utf-8")
        append_to_log(DONE_PATH, task_id, task_title)
        log(f"  ✅ DONE: {task_id}")
        summary_icon = "✅"
    elif task_result == "BLOCKED":
        final_content = move_task(
            TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "BLOCKED"
        )
        TASKS_PATH.write_text(final_content, encoding="utf-8")
        append_to_log(BLOCKED_PATH, task_id, task_title, task_reason)
        log(f"  🚫 BLOCKED: {task_id} — {task_reason}")
        summary_icon = "🚫"
    else:
        final_content = move_task(
            TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "FAILED"
        )
        TASKS_PATH.write_text(final_content, encoding="utf-8")
        append_to_log(FAILED_PATH, task_id, task_title, task_reason)
        retry_counts = state.get("retry_counts", {})
        retry_counts[task_id] = retry_count + 1
        state["retry_counts"] = retry_counts
        log(f"  ❌ FAILED: {task_id} — {task_reason}")
        summary_icon = "❌"

    # 10. 상태 저장
    state["last_task"] = task_id
    save_state(state)

    # 11. 다음 PENDING 확인
    remaining_content = TASKS_PATH.read_text(encoding="utf-8")
    remaining_sections = parse_tasks(remaining_content)
    next_pending = remaining_sections.get("PENDING", [])

    # 12. Summary 출력
    next_info = ""
    if next_pending:
        next_id, next_title = extract_task_info(next_pending[0])
        next_info = f"\n\n**다음 TASK:** `{next_id}`: {next_title}"

    write_summary(
        f"## {summary_icon} Auto Dev Queue 결과\n\n"
        f"**처리:** `{task_id}`: {task_title}\n"
        f"**결과:** {task_result}\n"
        f"**사유:** {task_reason}"
        f"{next_info}"
    )

    log("=== 완료 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
