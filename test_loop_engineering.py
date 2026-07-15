"""루프 엔지니어링 L1 인프라 단위 테스트 (네트워크·에이전트 불필요)."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "t@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

from loop_runner import classify_profile, load_profiles  # noqa: E402
from loop_verify import load_tier_steps, step_preflight, step_email_send_risk  # noqa: E402


def test_loop_config_valid_json():
    cfg = json.loads((ROOT / "auto_dev" / "loop_config.json").read_text(encoding="utf-8"))
    assert cfg["limits"]["max_retry_per_task"] == 2
    assert "verification_tiers" in cfg


def test_task_profiles_classify_doc():
    name, cfg = classify_profile("README에 Auto Dev Queue 사용법 추가")
    assert name == "doc_only"
    assert cfg.get("auto_merge_eligible") is True


def test_task_profiles_classify_blocked():
    name, cfg = classify_profile("monitor.py 발송 로직 수정")
    assert name == "core_logic"
    assert cfg.get("blocked") is True


def test_load_tier_steps_cumulative():
    steps = load_tier_steps(2)
    assert "preflight" in steps
    assert "pytest_monitor" in steps
    assert "recall_zero_gate" in steps


def test_step_preflight_ok():
    r = step_preflight()
    assert r["ok"] is True
    assert r["issues"] == []


def test_step_email_send_risk_blocks():
    r = step_email_send_risk("실제 발송 테스트")
    assert r["ok"] is False
    assert r["hits"]


def test_work_assets_registry():
    data = json.loads((ROOT / "auto_dev" / "work_assets.json").read_text(encoding="utf-8"))
    ids = {a["id"] for a in data["assets"]}
    assert "rules" in ids
    assert "recall_gate" in ids
