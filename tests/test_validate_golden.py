"""featureless feedback는 MEASURED로 포장하지 않는다."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import validate_golden as vg  # noqa: E402


def test_featureless_feedback_is_not_measured(tmp_path):
    path = tmp_path / "feedback.jsonl"
    rows = [
        {"id": "a", "verdict": "X", "title": ""},
        {"id": "b", "verdict": "O", "title": "   ", "description": ""},
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    group = {"id": "g1", "keywords": ["AI"], "exclude_keywords": []}
    labeled = vg.run_labeled_benchmark(str(path), group)
    assert labeled["status"] == "NOT_MEASURABLE"
    assert labeled["reason"] == "all labels are featureless"
    assert labeled["labeled_count"] == 0
    assert labeled["skipped_featureless"] == 2


def test_titled_feedback_still_measured(tmp_path):
    path = tmp_path / "feedback.jsonl"
    rows = [
        {"id": "a", "verdict": "X", "title": ""},
        {
            "id": "b",
            "verdict": "X",
            "title": "2026년 예비창업패키지 모집",
            "description": "예비창업자 대상",
        },
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    group = {"id": "g1", "keywords": ["AI"], "exclude_keywords": []}
    labeled = vg.run_labeled_benchmark(str(path), group)
    assert labeled["status"] == "MEASURED"
    assert labeled["labeled_count"] == 1
    assert labeled["skipped_featureless"] == 1
