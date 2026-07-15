"""Auto Dev Queue — Vercel Mail 프로젝트 자동개발 큐 실행기 (L1 오케스트레이터)

기능:
1. Preflight Check (필수 파일, 구조, 안전규칙 확인)
2. TASKS.md에서 다음 PENDING TASK 1개 선택
3. TASK를 RUNNING으로 이동
4. loop_runner → loop_verify (루프 엔지니어링 L1)
5. 실행 결과에 따라 DONE/FAILED/BLOCKED/AGENT_REQUIRED 처리
6. auto_dev_state.json 업데이트
7. GitHub Actions Summary 출력

설계: docs/AUTO_DEV_LOOP_ENGINEERING.md

주의:
- Secret/API Key/메일 계정 값은 절대 출력하지 않음
- 실제 이메일 발송 금지 (dry-run / draft-only 기준)
- 기존 앱 파일 수정 금지
- Mail 관련 Secret은 발송 기능 검증 전까지 미사용
"""
from __future__ import annotations

import importlib.util
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
MAIL_SECRETS = {"GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "SMTP_HOST", "SMTP_PORT",
                "IMAP_HOST", "IMAP_PORT"}
MAX_RETRY = 2

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def _load_loop_runner():
    """scripts/loop_runner.py 동적 로드 (패키지 없이)."""
    spec = importlib.util.spec_from_file_location(
        "loop_runner", ROOT / "scripts" / "loop_runner.py"
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


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

    if DRY_RUN:
        log(f"  🏷️ DRY_RUN: 실제 변경 없이 미리보기 종료")
        profile_name, _ = ("?", {})
        try:
            loop_mod = _load_loop_runner()
            if loop_mod:
                profile_name, _ = loop_mod.classify_profile(task_title)
        except Exception:
            pass
        write_summary(
            f"## 🏷️ Dry Run\n\n"
            f"다음 처리 대상: `{task_id}`: {task_title}\n\n"
            f"추정 프로필: `{profile_name}`\n\n"
            f"실제 변경은 수행하지 않았습니다."
        )
        save_state(state)
        return 0

    # 8. L1 루프 실행 (loop_runner → loop_verify)
    loop_mod = _load_loop_runner()
    if loop_mod is None:
        task_result = "FAILED"
        task_reason = "loop_runner 로드 실패"
    else:
        loop_out = loop_mod.run_task(task_id, task_title)
        status_map = {
            "DONE": "DONE",
            "FAILED": "FAILED",
            "BLOCKED": "BLOCKED",
            "AGENT_REQUIRED": "PENDING",  # Phase B까지 큐에 유지
            "SKIPPED": "DONE",
        }
        task_result = status_map.get(loop_out.status, "FAILED")
        task_reason = f"[{loop_out.profile}] {loop_out.reason}"
        if loop_out.verify_report:
            passed = sum(1 for s in loop_out.verify_report.get("steps", []) if s.get("ok"))
            total = len(loop_out.verify_report.get("steps", []))
            task_reason += f" (verify {passed}/{total})"
        if loop_out.status == "AGENT_REQUIRED":
            # RUNNING → PENDING 복귀 (에이전트 연동 전)
            final_content = move_task(
                TASKS_PATH.read_text(encoding="utf-8"), task_line, "RUNNING", "PENDING"
            )
            TASKS_PATH.write_text(final_content, encoding="utf-8")
            log(f"  ⏸ AGENT_REQUIRED: {task_id} — PENDING 유지")
            write_summary(
                f"## ⏸ Agent Required\n\n"
                f"`{task_id}`: {task_title}\n\n"
                f"프로필: `{loop_out.profile}`\n\n"
                f"Cloud Agent 연동(Phase B) 후 자동 구현 예정."
            )
            state["last_task"] = task_id
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
