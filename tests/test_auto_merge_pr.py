"""auto_merge_pr.py 게이트 단위 테스트."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from auto_merge_pr import assess_pr, match_profile  # noqa: E402


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
