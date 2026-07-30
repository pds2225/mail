# -*- coding: utf-8 -*-
"""mail_daily_review — 발송 후 MDR 가드레일 최소 회귀."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations import daily_review as dr  # noqa: E402


def test_merge_jsonl_append_dedupes(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "merge_jsonl_append", ROOT / "scripts" / "merge_jsonl_append.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    target = tmp_path / "ledger.jsonl"
    incoming = tmp_path / "local.jsonl"
    target.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    incoming.write_text('{"b":2}\n{"c":3}\n', encoding="utf-8")
    added = mod.merge_jsonl(target, incoming)
    assert added == 1
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert lines == ['{"a":1}', '{"b":2}', '{"c":3}']


def _write_coverage(tmp: Path, *, bizinfo: int = 10, kstartup: int = 5, nipa: int = 3) -> Path:
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_status": "SUCCESS",
        "sources": [
            {"site_id": "bizinfo", "item_count": bizinfo, "status": "SUCCESS"},
            {"site_id": "kstartup", "item_count": kstartup, "status": "SUCCESS"},
            {"site_id": "nipa", "item_count": nipa, "status": "SUCCESS"},
            {"site_id": "other", "item_count": 0, "status": "SUCCESS"},
        ],
    }
    path = logs / "source_coverage_20260730.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_delivery(tmp: Path, keys: list[str]) -> Path:
    path = tmp / "delivery_state.json"
    path.write_text(json.dumps(keys), encoding="utf-8")
    return path


def test_pass_happy_path(tmp_path):
    _write_coverage(tmp_path)
    delivery = _write_delivery(
        tmp_path,
        ["2026-07-30#am|default|grp_x|hmac_abc", "2026-07-30#am|default|grp_y|hmac_def"],
    )
    report, paths = dr.run_daily_review(
        date_s="2026-07-30",
        slot="am",
        delivery_state_path=delivery,
        logs_dir=tmp_path / "logs",
        reviews_root=tmp_path / "reviews",
        ledger_path=tmp_path / "ledger.jsonl",
        append_context=True,
        require_coverage=True,
    )
    assert report.overall == "PASS"
    by_id = {c.id: c for c in report.checks}
    assert by_id["MDR-001"].status == "PASS"
    assert by_id["MDR-002"].status == "PASS"
    assert by_id["MDR-004"].status == "PASS"
    assert (tmp_path / "reviews" / "2026-07-30" / "review_am.json").is_file()
    assert (tmp_path / "ledger.jsonl").is_file()
    line = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert json.loads(line)["overall"] == "PASS"
    assert paths["md"].is_file()


def test_fail_core_zero_and_missing_delivery(tmp_path):
    _write_coverage(tmp_path, bizinfo=0, kstartup=8, nipa=2)
    delivery = _write_delivery(tmp_path, ["2026-07-29#am|default|g|hmac_x"])
    report, _ = dr.run_daily_review(
        date_s="2026-07-30",
        slot="am",
        delivery_state_path=delivery,
        logs_dir=tmp_path / "logs",
        reviews_root=tmp_path / "reviews",
        ledger_path=tmp_path / "ledger.jsonl",
        append_context=True,
    )
    assert report.overall == "FAIL"
    by_id = {c.id: c for c in report.checks}
    assert by_id["MDR-002"].status == "FAIL"
    assert "bizinfo=0" in by_id["MDR-002"].detail
    assert by_id["MDR-004"].status == "FAIL"


def test_fail_silent_skip_no_coverage(tmp_path):
    delivery = _write_delivery(tmp_path, [])
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    # skip 마커만 있는 로그
    (tmp_path / "logs" / "site_collection_coverage_report.md").write_text(
        "skipped_fetch=true already_delivered\n", encoding="utf-8"
    )
    report, _ = dr.run_daily_review(
        date_s="2026-07-30",
        slot="am",
        delivery_state_path=delivery,
        logs_dir=tmp_path / "logs",
        reviews_root=tmp_path / "reviews",
        ledger_path=tmp_path / "ledger.jsonl",
        run_duration_sec=120,
        append_context=False,
    )
    assert report.overall == "FAIL"
    by_id = {c.id: c for c in report.checks}
    assert by_id["MDR-001"].status == "FAIL"


def test_external_send_fingerprint(tmp_path):
    _write_coverage(tmp_path)
    delivery = _write_delivery(
        tmp_path, ["2026-07-30#am|default|g|hmac_x"]
    )
    sample = tmp_path / "reviews" / "2026-07-30" / "inbox_sample.txt"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text(
        "소스: 기업마당 API + 마이페어 + K-Startup\n공고 목록...\n",
        encoding="utf-8",
    )
    report, _ = dr.run_daily_review(
        date_s="2026-07-30",
        slot="am",
        delivery_state_path=delivery,
        logs_dir=tmp_path / "logs",
        reviews_root=tmp_path / "reviews",
        ledger_path=tmp_path / "ledger.jsonl",
        extra_scan=[sample],
        append_context=False,
    )
    by_id = {c.id: c for c in report.checks}
    assert by_id["MDR-003"].status == "FAIL"


def test_title_badge_fail(tmp_path):
    _write_coverage(tmp_path)
    delivery = _write_delivery(
        tmp_path, ["2026-07-30#pm|default|g|hmac_x"]
    )
    draft = tmp_path / "draft.txt"
    draft.write_text("모집 안내 새로운게시글\n정상 제목\n", encoding="utf-8")
    report, _ = dr.run_daily_review(
        date_s="2026-07-30",
        slot="pm",
        delivery_state_path=delivery,
        logs_dir=tmp_path / "logs",
        reviews_root=tmp_path / "reviews",
        ledger_path=tmp_path / "ledger.jsonl",
        extra_scan=[draft],
        append_context=False,
    )
    by_id = {c.id: c for c in report.checks}
    assert by_id["MDR-005"].status == "FAIL"
    assert by_id["MDR-004"].status == "PASS"
