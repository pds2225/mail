"""auto_merge_pr.py 게이트 단위 테스트."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from auto_merge_pr import (  # noqa: E402
    assess_pr,
    match_profile,
    optional_positive_int,
    resolve_pr_number,
)


def _profiles():
    return json.loads((ROOT / "auto_dev" / "task_profiles.json").read_text(encoding="utf-8"))


def _cfg(enabled: bool = True) -> dict:
    return {
        "auto_merge": {
            "enabled": enabled,
            "allowed_profiles": ["doc_only", "script_safe", "test_fix"],
            "required_labels_absent": ["needs-human", "blocked"],
        }
    }


def test_doc_only_paths_eligible():
    verdict = match_profile(["docs/project/RULES.md", "AGENTS.md"], _profiles())
    assert verdict.ok
    assert verdict.profile == "doc_only"


def test_monitor_py_blocked():
    verdict = match_profile(["monitor.py", "tests/test_x.py"], _profiles())
    assert not verdict.ok
    assert "보호 파일" in verdict.reason


def test_assess_skips_draft():
    pr = {"isDraft": True, "labels": [], "mergeable": "MERGEABLE"}
    verdict = assess_pr(pr, ["docs/foo.md"], _cfg())
    assert not verdict.ok
    assert "Draft" in verdict.reason


def test_assess_skips_blocked_label():
    pr = {"isDraft": False, "labels": [{"name": "needs-human"}], "mergeable": "MERGEABLE"}
    verdict = assess_pr(pr, ["docs/foo.md"], _cfg())
    assert not verdict.ok
    assert "차단 라벨" in verdict.reason


def test_assess_disabled_config():
    pr = {"isDraft": False, "labels": [], "mergeable": "MERGEABLE"}
    verdict = assess_pr(pr, ["docs/foo.md"], _cfg(enabled=False))
    assert not verdict.ok
    assert "enabled=false" in verdict.reason


def test_task_md_doc_only_eligible():
    verdict = match_profile(["TASK.md"], _profiles())
    assert verdict.ok
    assert verdict.profile == "doc_only"


def test_assess_skips_merged_state():
    pr = {"isDraft": False, "labels": [], "mergeable": "MERGEABLE", "state": "MERGED"}
    verdict = assess_pr(pr, ["docs/foo.md"], _cfg())
    assert not verdict.ok
    assert "MERGED" in verdict.reason


def test_optional_positive_int():
    assert optional_positive_int("253") == 253
    assert optional_positive_int("0") is None
    assert optional_positive_int("") is None
    assert optional_positive_int(None) is None


def test_resolve_prefers_event_pr():
    assert resolve_pr_number(event_pr=253, head_branch="docs/x") == 253


def test_resolve_uses_gh_pr_list(monkeypatch):
    def fake_run(cmd, *, check=False):
        if cmd[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(cmd, 0, '[{"number": 99}]', "")
        return subprocess.CompletedProcess(cmd, 1, "", "no")

    monkeypatch.setattr("auto_merge_pr._run", fake_run)
    assert resolve_pr_number(head_branch="docs/task-template-20260813") == 99


def test_resolve_falls_back_to_commit_pulls(monkeypatch):
    def fake_run(cmd, *, check=False):
        if cmd[:2] == ["gh", "api"] and "/commits/" in cmd[2]:
            return subprocess.CompletedProcess(cmd, 0, '[{"number": 253}]', "")
        return subprocess.CompletedProcess(cmd, 1, "", "Not Found")

    monkeypatch.setattr("auto_merge_pr._run", fake_run)
    assert resolve_pr_number(head_sha="abc", repo="pds2225/mail") == 253


def test_resolve_missing_returns_none(monkeypatch):
    def fake_run(cmd, *, check=False):
        return subprocess.CompletedProcess(cmd, 1, "", "Not Found")

    monkeypatch.setattr("auto_merge_pr._run", fake_run)
    assert resolve_pr_number(head_branch="x", head_sha="abc", repo="o/r") is None


def test_auto_merge_workflow_uses_github_token_not_pat():
    """만료 PAT 를 checkout token 으로 쓰면 인증 실패 (run 31660085605)."""
    text = (ROOT / ".github/workflows/auto-merge.yml").read_text(encoding="utf-8")
    token_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip().startswith("token:") or ln.strip().startswith("GH_TOKEN:")
    ]
    assert token_lines, "checkout token / GH_TOKEN 설정이 없다"
    for ln in token_lines:
        assert "github.token" in ln
        assert "AUTO_DEV_PAT" not in ln
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "actions/runs/" not in text
    assert "--head-branch" in text
    assert "--head-sha" in text
    assert "head_repository.full_name == github.repository" in text

