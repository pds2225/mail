"""O/X 피드백 루프가 '자동 수집'까지 연결돼 있는지 가드.

배경: 메일 하단 ⭕/❌ 버튼과 수집 스크립트(scripts/collect_feedback.py)는 있었지만,
스케줄 워크플로에 물려 있지 않아 O/X 가 눌려도 어디에도 안 쌓였다(루프 열림).
이 테스트는 그 재발을 막는다 — 일일 워크플로가 collect_feedback 를 실행하고 골든
라벨(feedback_labels.jsonl)을 커밋백하지 않으면 CI 실패.
"""
import pathlib

import yaml

WF = pathlib.Path(__file__).resolve().parent.parent / ".github/workflows/monitor.yml"


def _steps():
    wf = yaml.safe_load(WF.read_text(encoding="utf-8"))
    return [s for job in wf.get("jobs", {}).values() for s in job.get("steps", [])]


def _all_runs():
    return "\n".join(s.get("run", "") for s in _steps())


def test_collect_feedback_is_scheduled():
    """일일 워크플로가 collect_feedback.py 를 실행해야 한다(O/X 자동 수집)."""
    runs = _all_runs()
    assert "collect_feedback.py" in runs, "collect_feedback 수집 스텝이 워크플로에 없다(루프 열림)"


def test_feedback_labels_committed_back():
    """수집한 골든 라벨(feedback_labels.jsonl)을 커밋백해야 실행 간에 누적된다."""
    runs = _all_runs()
    assert "feedback_labels.jsonl" in runs, "feedback_labels.jsonl 커밋백이 없다(수집분 유실)"
    assert "git commit" in runs, "커밋 스텝이 없다"


def test_feedback_collection_failure_is_nonfatal():
    """피드백 수집 실패가 발송/워크플로를 죽이면 안 된다(발송 우선)."""
    step = next((s for s in _steps() if "collect_feedback.py" in (s.get("run") or "")), None)
    assert step is not None
    run = step["run"]
    # collect_feedback 호출 줄은 `|| echo`/`|| true` 등으로 실패를 흡수해야 한다.
    line = next((ln for ln in run.splitlines() if "collect_feedback.py" in ln), "")
    assert "||" in line, "collect_feedback 실패가 흡수되지 않는다(발송 후 단계라도 워크플로 red 위험)"
