"""auto_merge_pr.py 게이트 단위 테스트."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from auto_merge_pr import assess_pr, match_profile, resolve_pr_number  # noqa: E402


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
    assert "actions: read" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "actions/runs/" not in text
    assert "gh api" not in text
    assert "--print-pr-number" in text


class _FakeProc:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def test_resolve_pr_prefers_payload():
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return _FakeProc("99")

    assert resolve_pr_number(payload_pr="248", head_branch="x", runner=runner) == "248"
    assert calls == []


def test_resolve_pr_falls_back_to_head_branch():
    def runner(cmd):
        assert "--head" in cmd
        return _FakeProc("244\n")

    assert resolve_pr_number(payload_pr="", head_branch="fix/foo", runner=runner) == "244"


def test_resolve_pr_falls_back_to_sha_when_branch_empty():
    def runner(cmd):
        assert "--search" in cmd
        return _FakeProc("250")

    assert resolve_pr_number(head_sha="abc123", runner=runner) == "250"


def test_resolve_pr_empty_is_skip_not_error():
    def runner(cmd):
        return _FakeProc("")

    assert resolve_pr_number(runner=runner) == ""

