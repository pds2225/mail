"""Local dashboard O/X + group priority hits."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "t")
os.environ.setdefault("ANTHROPIC_API_KEY", "t")
os.environ.setdefault("GMAIL_ADDRESS", "t@t.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "t")

import monitor as m  # noqa: E402
from mail_core.delivery import feedback as fb  # noqa: E402
from mail_core.matching import scoring  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_record_local_verdict_no_mail(tmp_path):
    path = tmp_path / "feedback_labels.jsonl"
    stats = fb.record_local_verdict(
        "nid_test_1", "O", title="AI 지원사업 모집", source="dashboard-ox", path=path,
    )
    assert stats["added"] == 1
    assert fb.feedback_verdicts(path)["nid_test_1"] == "O"
    stats2 = fb.record_local_verdict("nid_test_1", "X", title="AI 지원사업 모집", path=path)
    assert stats2["updated"] == 1
    assert fb.feedback_verdicts(path)["nid_test_1"] == "X"


def test_group_priority_hits_include_group_keywords():
    """bnco 그룹 priority(K-뷰티)가 전역 사전에 없어도 우선 추천에 잡힌다."""
    groups = json.loads((ROOT / "config" / "groups.json").read_text(encoding="utf-8"))
    bnco = next(g for g in groups if g["id"] == "grp_bnco")
    ev = m.evaluate_notice(
        {
            "title": "K-뷰티 해외전시회 참여기업 모집",
            "description": "인천 소재 화장품 기업 신청접수",
            "region_field": "인천",
        },
        bnco,
    )
    assert "K-뷰티" in (ev.get("priority_keywords") or [])
    assert ev.get("priority_keyword") is True


def test_llm_model_env_override(monkeypatch):
    called = {}

    def fake_anthropic(prompt, model):
        called["model"] = model
        return {"is_relevant": True, "confidence": 1.0, "reason": "ok"}

    monkeypatch.setenv("MONITOR_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("MONITOR_LLM_MODEL", "claude-test-model")
    monkeypatch.setattr(scoring, "_llm_anthropic", fake_anthropic)
    out = scoring.llm_relevance_check({"title": "x", "summary": "y"}, {"priority_keywords": []})
    assert out["is_relevant"] is True
    assert called["model"] == "claude-test-model"


def test_ox_title_queue_exists():
    q = ROOT / "data" / "golden" / "ox_title_queue.json"
    assert q.exists()
    data = json.loads(q.read_text(encoding="utf-8"))
    assert data.get("count", 0) >= 10
    assert data["items"][0]["title"]
