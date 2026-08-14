"""auto_merge_pr.py 게이트 단위 테스트."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from auto_merge_pr import (  # noqa: E402
    assess_pr,
    head_sha_matches,
    match_profile,
    resolve_pr_number,
)


def _profiles():
    return json.loads((ROOT / "auto_dev" / "task_profiles.json").read_text(encoding="utf-8"))


def _cfg(enabled: bool = True) -> dict:
    return {
        "auto_merge": {
            "enabled": enabled,
            "allowed_profiles": [],
            "required_labels_absent": ["needs-human", "blocked"],
        }
    }


def test_doc_only_paths_eligible():
    verdict = match_profile(["docs/project/RULES.md", "AGENTS.md"], _profiles())
    assert verdict.ok
    assert verdict.profile == "doc_only"


def test_monitor_py_eligible_by_default():
    """Standing policy: auto-merge is the default, including monitor.py."""
    verdict = match_profile(["monitor.py", "tests/test_x.py"], _profiles())
    assert verdict.ok
    assert verdict.profile == "core_logic"


def test_secret_file_still_blocked():
    verdict = match_profile([".env"], _profiles())
    assert not verdict.ok
    assert "secret" in verdict.reason


def test_env_star_variants_blocked():
    """MAIL-004 docstring says `.env*`; production/staging basenames must not auto-merge."""
    for path in (".env.production", ".env.staging", "deploy/.env.local", ".env.backup"):
        verdict = match_profile([path], _profiles())
        assert not verdict.ok, path
        assert "secret" in verdict.reason


def test_mixed_app_paths_eligible():
    verdict = match_profile(["mail_core/matching/scoring.py", ".github/workflows/test.yml"], _profiles())
    assert verdict.ok
    assert verdict.profile == "default"


def test_assess_allowlist_still_restricts_when_set():
    cfg = _cfg()
    cfg["auto_merge"]["allowed_profiles"] = ["doc_only"]
    pr = {"isDraft": False, "labels": [], "mergeable": "MERGEABLE"}
    verdict = assess_pr(pr, ["scripts/foo.py"], cfg)
    assert not verdict.ok
    assert "allowed_profiles" in verdict.reason


def test_loop_config_default_allowlist_is_empty():
    cfg = json.loads((ROOT / "auto_dev" / "loop_config.json").read_text(encoding="utf-8"))
    assert cfg["auto_merge"]["enabled"] is True
    assert cfg["auto_merge"]["allowed_profiles"] == []


def test_assess_monitor_py_eligible():
    pr = {"isDraft": False, "labels": [], "mergeable": "MERGEABLE"}
    verdict = assess_pr(pr, ["monitor.py"], _cfg())
    assert verdict.ok
    assert verdict.profile == "core_logic"


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


def test_head_sha_matches_full_and_prefix():
    full = "abcdef0123456789abcdef0123456789abcdef01"
    assert head_sha_matches(full, full)
    assert head_sha_matches(full[:12], full)
    assert head_sha_matches(full, full[:12])
    assert not head_sha_matches(full, "ffffffffffffffffffffffffffffffffffffffff")
    assert not head_sha_matches("", full)
    assert not head_sha_matches("abc", full)  # too short to be unambiguous


def test_assess_refuses_when_pr_head_moved_after_ci():
    """CI-green SHA A must not merge PR head B (push race + fallback_direct_merge)."""
    ci_sha = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    pr_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    pr = {
        "isDraft": False,
        "labels": [],
        "mergeable": "MERGEABLE",
        "headRefOid": pr_sha,
    }
    verdict = assess_pr(
        pr,
        ["monitor.py"],
        _cfg(),
        expected_head_sha=ci_sha,
    )
    assert not verdict.ok
    assert "head SHA mismatch" in verdict.reason


def test_assess_allows_when_pr_head_matches_ci_sha():
    sha = "cccccccccccccccccccccccccccccccccccccccc"
    pr = {
        "isDraft": False,
        "labels": [],
        "mergeable": "MERGEABLE",
        "headRefOid": sha,
    }
    verdict = assess_pr(pr, ["docs/foo.md"], _cfg(), expected_head_sha=sha)
    assert verdict.ok


def test_auto_merge_workflow_pins_expected_head_sha():
    text = (ROOT / ".github/workflows/auto-merge.yml").read_text(encoding="utf-8")
    assert "--expected-head-sha" in text
    assert "workflow_run.head_sha" in text


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
    assert "head_repository.full_name == github.repository" in text


def test_task_md_doc_only_eligible():
    verdict = match_profile(["TASK.md"], _profiles())
    assert verdict.ok
    assert verdict.profile == "doc_only"


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
