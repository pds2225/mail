"""Unit tests for outstanding_dev_audit classifiers (no network)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "t@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

import outstanding_dev_audit as audit  # noqa: E402
import auto_dev_overnight_ready as overnight  # noqa: E402


def test_is_noise_ref_backup_archive():
    assert audit.is_noise_ref("origin/backup/WIN-K20QOC29TOB") is True
    assert audit.is_noise_ref("origin/archive/2026-07-23/feat/feedback-act") is True
    assert audit.is_noise_ref("origin/agent/fix-source-quality-review") is False


def test_classify_missing_ref(monkeypatch):
    monkeypatch.setattr(audit, "resolve_ref", lambda ref: None)
    r = audit.classify_ref("origin/form/does-not-exist")
    assert r["status"] == "MISSING_REF"


def test_classify_content_on_main_no_plus(monkeypatch):
    monkeypatch.setattr(audit, "resolve_ref", lambda ref: "abc123")
    monkeypatch.setattr(audit, "cherry_plus_commits", lambda base, tip: [])
    r = audit.classify_ref("origin/agent/already-merged")
    assert r["status"] == "CONTENT_ON_MAIN"


def test_classify_unique_candidate(monkeypatch):
    monkeypatch.setattr(audit, "resolve_ref", lambda ref: "deadbeef")
    monkeypatch.setattr(
        audit,
        "cherry_plus_commits",
        lambda base, tip: ["+ deadbeef feat: brand new module"],
    )
    monkeypatch.setattr(
        audit,
        "tip_only_paths",
        lambda base, tip: ["mail_core/operations/brand_new_thing.py"],
    )
    monkeypatch.setattr(audit, "path_exists_on_ref", lambda ref, path: False)
    r = audit.classify_ref("origin/agent/new-feature")
    assert r["status"] == "UNIQUE_CANDIDATE"
    assert "brand_new_thing.py" in r["unique_paths"][0]


def test_classify_superseded_paths_as_on_main(monkeypatch):
    monkeypatch.setattr(audit, "resolve_ref", lambda ref: "deadbeef")
    monkeypatch.setattr(
        audit,
        "cherry_plus_commits",
        lambda base, tip: ["+ deadbeef feat: old root groups"],
    )
    monkeypatch.setattr(audit, "tip_only_paths", lambda base, tip: ["groups.json"])

    def exists(ref: str, path: str) -> bool:
        return path == "config/groups.json"

    monkeypatch.setattr(audit, "path_exists_on_ref", exists)
    r = audit.classify_ref("origin/cursor/old-groups")
    assert r["status"] == "CONTENT_ON_MAIN"


def test_classify_tests_only_superseded(monkeypatch):
    monkeypatch.setattr(audit, "resolve_ref", lambda ref: "deadbeef")
    monkeypatch.setattr(
        audit,
        "cherry_plus_commits",
        lambda base, tip: ["+ deadbeef fix: digest fp"],
    )
    monkeypatch.setattr(
        audit,
        "tip_only_paths",
        lambda base, tip: ["tests/test_digest_false_positive_fixes.py"],
    )
    monkeypatch.setattr(
        audit,
        "tip_changed_paths",
        lambda base, tip: [
            ("M", "monitor.py"),
            ("A", "tests/test_digest_false_positive_fixes.py"),
        ],
    )
    monkeypatch.setattr(
        audit,
        "path_exists_on_ref",
        lambda ref, path: path in audit.MAIN_FP_SUITE_MARKERS,
    )
    r = audit.classify_ref("origin/cursor/digest-false-positive-fixes-8449")
    assert r["status"] == "CONTENT_ON_MAIN"
    assert r["reason"] == "tests_only_superseded_by_main_fp_suites"


def test_overnight_user_priority_order():
    pending = [
        "TASK-020: random housekeeping",
        "TASK-014: outstanding_dev_audit merge gate (user-priority)",
        "TASK-015: overnight readiness checker",
    ]
    ordered = overnight._user_priority_first(pending)
    assert ordered[0].startswith("TASK-014")


def test_overnight_pending_parser():
    text = """# Auto Dev Queue — TASKS

## PENDING
- TASK-014: outstanding audit
- TASK-015: overnight ready

## RUNNING

## DONE
- TASK-001: old
"""
    pending = overnight._pending_tasks(text)
    assert pending == [
        "TASK-014: outstanding audit",
        "TASK-015: overnight ready",
    ]
