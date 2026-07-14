"""공고 digest 자동발송 '조용한 정지' 재발방지 가드 (2026-07-14 사용자: "동일문제 없도록").

배경: 6/24 커밋으로 일일 스케줄이 --send→--draft(초안만)로 바뀌어 실제 자동발송이 몇 주간
조용히 멈췄는데 아무도 몰랐다. 이 테스트가 CI 게이트로 그 재발을 막는다 — 스케줄 워크플로가
실발송(--send)이 아니거나 중복방지(--persist-seen)·seen_ids 커밋백이 빠지면 CI 실패.
"""
import pathlib

import yaml

WF = pathlib.Path(__file__).resolve().parent / ".github/workflows/monitor.yml"


def _load():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _steps(wf):
    return [s for job in wf.get("jobs", {}).values() for s in job.get("steps", [])]


def _monitor_run(wf):
    cmds = [s.get("run", "") for s in _steps(wf) if "monitor.py" in (s.get("run") or "")]
    assert cmds, "워크플로에 monitor.py 실행 스텝이 없다"
    return " ; ".join(cmds)


def test_workflow_file_exists():
    assert WF.exists(), "monitor.yml 워크플로가 없다"


def test_scheduled_trigger_present():
    wf = _load()
    # PyYAML 은 'on:' 키를 boolean True 로 파싱한다(유명한 함정) → 둘 다 확인
    on = wf.get("on") if "on" in wf else wf.get(True)
    assert on and "schedule" in on, "매일 자동 스케줄(cron)이 없다"


def test_daily_workflow_actually_sends():
    """★핵심: 일일 워크플로가 실제 발송(--send)이어야 한다(초안·미리보기로 조용히 안 꺼지게)."""
    cmd = _monitor_run(_load())
    assert "--send" in cmd, f"자동발송이 꺼져 있다(--send 없음): {cmd!r}"
    assert "--draft" not in cmd, f"--draft(초안만)라 실발송 안 됨: {cmd!r}"
    # --send 없이 --dry-run 단독도 금지(발송 안 함)
    assert not ("--dry-run" in cmd and "--send" not in cmd), f"dry-run 단독이라 발송 안 됨: {cmd!r}"


def test_dedup_persist_present():
    """중복 재발송 방지: --persist-seen + seen_ids.json 커밋백 스텝이 있어야 한다."""
    wf = _load()
    cmd = _monitor_run(wf)
    assert "--persist-seen" in cmd, "--persist-seen 없음 → 매일 중복 재발송 위험"
    all_runs = " ".join(s.get("run", "") for s in _steps(wf))
    assert "seen_ids.json" in all_runs and "git commit" in all_runs, "seen_ids 커밋백 스텝 없음"


def test_crash_alert_present():
    """완전 크래시 시 알림 스텝(if: failure)이 있어야 한다(조용한 정지 방지)."""
    wf = _load()
    assert any(str(s.get("if", "")).replace(" ", "") == "failure()" for s in _steps(wf)), \
        "크래시 알림(if: failure()) 스텝이 없다"
