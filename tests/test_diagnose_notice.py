"""MAIL-P0D-04(TASK-029) — diagnose_notice CLI 회귀테스트.

누락 샘플 5종(파이프라인 단계별로 다른 원인)의 원인 식별, 개인정보 마스킹,
존재하지 않는 notice_id 예외처리를 검증한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")

import diagnose_notice as dn  # noqa: E402
from mail_core.storage.raw_store import RawStore  # noqa: E402

TODAY_UTC = datetime.now(timezone.utc).strftime("%Y%m%d")


def _write_trace(logs_dir: Path, notice_id: str, stages: dict) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"notice_stage_trace_{TODAY_UTC}.jsonl"
    row = {"run_id": TODAY_UTC, "notice_id": notice_id, "recorded_at": "x", "stages": stages}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _save_meta(raw_root: Path, **fields) -> None:
    store = RawStore(root=raw_root, run_day=datetime.now(timezone.utc).date())
    base = {
        "id": "x", "title": "제목", "link": "https://x", "source": "테스트",
        "author": "기관", "description": "", "deadline": "2099-12-31",
        "posted_date": "2026-05-01", "is_aggregator": False,
    }
    base.update(fields)
    store.save_item_meta(base)


# ── 누락 샘플 5종: 각기 다른 단계·원인이 정확히 식별돼야 한다 ────────────────

def test_sample1_enrich_failed_stops_before_evaluate(tmp_path):
    logs_dir = tmp_path / "logs1"
    _write_trace(logs_dir, "n1", {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "NORMALIZE": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "ENRICH": {"status": "FAILED", "error_code": "DETAIL_FETCH_TIMEOUT", "at": "x"},
    })
    report = dn.diagnose_notice("n1", logs_dir=logs_dir, raw_root=tmp_path / "no_raw")
    assert report["last_success_stage"] == "NORMALIZE"
    assert report["first_failed_stage"] == "ENRICH"
    assert "DETAIL_FETCH_TIMEOUT" in report["reason_codes"]


def test_sample2_region_not_eligible_at_evaluate(tmp_path):
    logs_dir = tmp_path / "logs2"
    _write_trace(logs_dir, "n2", {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "NORMALIZE": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "ENRICH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g1": {"status": "FAILED", "error_code": "REGION_NOT_ELIGIBLE", "at": "x"},
    })
    report = dn.diagnose_notice("n2", logs_dir=logs_dir, raw_root=tmp_path / "no_raw")
    assert report["last_success_stage"] == "ENRICH"
    assert report["first_failed_stage"] == "EVALUATE"
    assert report["reason_codes"] == ["REGION_NOT_ELIGIBLE"]


def test_sample3_tenant_only_at_evaluate(tmp_path):
    logs_dir = tmp_path / "logs3"
    _write_trace(logs_dir, "n3", {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "NORMALIZE": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "ENRICH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g1": {"status": "FAILED", "error_code": "TENANT_ONLY", "at": "x"},
    })
    report = dn.diagnose_notice("n3", logs_dir=logs_dir, raw_root=tmp_path / "no_raw")
    assert report["first_failed_stage"] == "EVALUATE"
    assert report["reason_codes"] == ["TENANT_ONLY"]


def test_sample4_company_match_below_threshold_after_group_pass(tmp_path):
    """그룹 판정은 통과(EVALUATE SUCCESS)했지만 기업별 정밀매칭 임계치 미달로
    최종 후보에서 빠진 경우 — FAILED가 아니라 PARTIAL이지만 원인으로 식별돼야 한다."""
    logs_dir = tmp_path / "logs4"
    _write_trace(logs_dir, "n4", {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "NORMALIZE": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "ENRICH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g1": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "COMPANY_MATCH:g1": {"status": "PARTIAL", "error_code": "BELOW_THRESHOLD", "at": "x"},
    })
    report = dn.diagnose_notice("n4", logs_dir=logs_dir, raw_root=tmp_path / "no_raw")
    assert report["last_success_stage"] == "EVALUATE"
    assert report["first_failed_stage"] == "COMPANY_MATCH"
    assert report["reason_codes"] == ["BELOW_THRESHOLD"]


def test_sample5_region_unknown_review_bucket(tmp_path):
    """지역 미상 리뷰 버킷(PARTIAL REGION_UNKNOWN)도 '왜 자동 발송에 없었는지'의
    원인으로 식별돼야 한다."""
    logs_dir = tmp_path / "logs5"
    _write_trace(logs_dir, "n5", {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "NORMALIZE": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "ENRICH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g1": {"status": "PARTIAL", "error_code": "REGION_UNKNOWN", "at": "x"},
    })
    report = dn.diagnose_notice("n5", logs_dir=logs_dir, raw_root=tmp_path / "no_raw")
    assert report["first_failed_stage"] == "EVALUATE"
    assert report["reason_codes"] == ["REGION_UNKNOWN"]


# ── 여러 그룹에 걸친 판정(그룹1 통과·그룹2 제외)도 함께 표시 ──────────────────

def test_mixed_group_outcomes_both_captured():
    stages = {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "NORMALIZE": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "ENRICH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g1": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g2": {"status": "FAILED", "error_code": "REGION_NOT_ELIGIBLE", "at": "x"},
    }
    summary = dn.summarize_stages(stages)
    assert summary["last_success_stage"] == "EVALUATE"
    assert summary["first_failed_stage"] == "EVALUATE"
    assert summary["reason_codes"] == ["REGION_NOT_ELIGIBLE"]


# ── 개인정보 마스킹 ──────────────────────────────────────────────────────────

def test_mask_pii_masks_email_and_phone():
    text = "문의: hong@example.com 또는 02-1234-5678로 연락주세요"
    masked = dn.mask_pii(text)
    assert "hong@example.com" not in masked
    assert "@example.com" in masked  # 도메인은 남기고 로컬파트만 일부 마스킹(_mask_email 정책)
    assert "1234-5678" not in masked


def test_mask_pii_passthrough_for_none_and_empty():
    assert dn.mask_pii(None) is None
    assert dn.mask_pii("") == ""


def test_live_reevaluation_evidence_is_masked(tmp_path):
    raw_root = tmp_path / "raw"
    _save_meta(
        raw_root, id="n6",
        title="부산 소재 기업 전용 지원사업 모집 공고",
        description="부산광역시 소재 중소기업만 신청 가능합니다. 문의: hong@example.com",
    )
    report = dn.diagnose_notice("n6", logs_dir=tmp_path / "no_logs", raw_root=raw_root)
    live = report["live_reevaluation"]
    assert live is not None
    for ev in live["reason_evidence"].values():
        assert "hong@example.com" not in ev


# ── 원문 전체 미노출 ─────────────────────────────────────────────────────────

def test_report_never_includes_full_description(tmp_path):
    raw_root = tmp_path / "raw"
    long_body = "이 공고는 매우 긴 본문입니다. " * 50
    _save_meta(raw_root, id="n7", description=long_body)
    report = dn.diagnose_notice("n7", logs_dir=tmp_path / "no_logs", raw_root=raw_root)
    dumped = json.dumps(report, ensure_ascii=False)
    assert long_body not in dumped


# ── 존재하지 않는 ID 예외처리 ─────────────────────────────────────────────────

def test_nonexistent_id_raises_notice_not_found(tmp_path):
    try:
        dn.diagnose_notice("no-such-id", logs_dir=tmp_path / "logs", raw_root=tmp_path / "raw")
        assert False, "예외가 발생해야 한다"
    except dn.NoticeNotFoundError:
        pass


def test_cli_exits_nonzero_for_nonexistent_id():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "diagnose_notice.py"), "definitely-not-a-real-id-zzz"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode != 0


def test_cli_json_output_is_valid_for_found_notice(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    _write_trace(logs_dir, "n8", {
        "FETCH": {"status": "SUCCESS", "error_code": "", "at": "x"},
        "EVALUATE:g1": {"status": "FAILED", "error_code": "CLOSED_DEADLINE", "at": "x"},
    })
    report = dn.diagnose_notice("n8", logs_dir=logs_dir, raw_root=tmp_path / "no_raw")
    # main()의 --json 출력 형태를 그대로 검증(직렬화 가능해야 함).
    dumped = json.dumps(report, ensure_ascii=False)
    reloaded = json.loads(dumped)
    assert reloaded["notice_id"] == "n8"
    assert reloaded["reason_codes"] == ["CLOSED_DEADLINE"]
