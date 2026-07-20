"""digest 품질(빠짐없이·적합만) 계측 스모크 — 합성 run_result 로 네트워크 없이 단언."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

from monitor import (  # noqa: E402
    KST,
    format_digest_quality_line,
    measure_digest_quality,
    write_digest_quality_report,
)


def _clean_run_result():
    """위험 0 — 빠짐없이·적합만 모두 OK 여야 하는 정상 run_result."""
    return {
        "mode": "draft",
        "final_mail_target_count": 7,
        "filtered_items": 7,
        "drafts_created": 2,
        "date_review_queue": [
            {"title": "낮은위험 공고", "date_unknown_risk": "낮음"},
        ],
        "coverage_anomalies": [],
        "coverage": [
            {"site_id": "s1", "site_name": "정상소스", "enabled": True, "fetch_success": True},
        ],
        "date_excluded": [],
        "sent_groups": [],
        "preview_groups": [
            {"name": "그룹A", "matched_items": 7, "region_unknown_items": 0},
        ],
    }


def test_clean_run_is_ok():
    v = measure_digest_quality(_clean_run_result())
    assert v["recall_ok"] is True
    assert v["precision_ok"] is True
    assert v["recall_risk"] == 0
    assert v["precision_risk"] == 0
    assert v["delivered"] == 7
    line = format_digest_quality_line(v)
    assert "빠짐없이 OK" in line and "적합만 OK" in line and "전달 7건" in line


def test_recall_risk_counts_three_signals():
    # now 를 월요일로 고정 → 전날(일요일)이 창(3일) 안에 들어오게(결정론)
    now = datetime.now(KST)
    while now.weekday() != 0:  # 0=월요일
        now += timedelta(days=1)
    weekend = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")  # 일요일, 1일 전
    rr = _clean_run_result()
    rr["date_review_queue"] = [
        {"title": "신청 살아있는 공고", "date_unknown_risk": "높음"},
        {"title": "중간위험", "date_unknown_risk": "중간"},
        {"title": "낮음(비위험)", "date_unknown_risk": "낮음"},
    ]
    rr["coverage_anomalies"] = [
        {"site_id": "s2", "site_name": "0건급락", "severity": "high"},
        {"site_id": "s3", "site_name": "급감", "severity": "medium"},
        {"site_id": "s9", "site_name": "low무시", "severity": "low"},
    ]
    rr["coverage"] = [
        {"site_id": "s4", "site_name": "수집실패", "enabled": True,
         "fetch_success": False, "fetch_error": "timeout"},
        {"site_id": "s5", "site_name": "정상", "enabled": True, "fetch_success": True},
    ]
    rr["date_excluded"] = [
        {"title": "주말 too_old 엣지", "_excluded_reason": "too_old",
         "_excluded_posted_date": weekend},
        {"title": "그냥 오래된 평일", "_excluded_reason": "too_old",
         "_excluded_posted_date": "2020-01-01"},
    ]
    v = measure_digest_quality(rr, now=now)
    # ① risky = 2(높음·중간) ② weekend_edge = 1 ③ alert_sites = {s2,s3,s4} = 3  → 6
    assert v["detail"]["recall"]["date_unknown_risky"]["count"] == 2
    assert v["detail"]["recall"]["excluded_recent_weekend"]["count"] == 1
    assert v["detail"]["recall"]["coverage_alert_sources"]["count"] == 3
    assert v["recall_risk"] == 6
    assert v["recall_ok"] is False


def test_precision_risk_from_region_unknown():
    rr = _clean_run_result()
    rr["preview_groups"] = [
        {"name": "그룹A", "matched_items": 5, "region_unknown_items": 2},
        {"name": "그룹B", "matched_items": 3, "region_unknown_items": 1},
    ]
    v = measure_digest_quality(rr)
    assert v["precision_risk"] == 3
    assert v["precision_ok"] is False
    assert "측정 근거 부족" in v["detail"]["precision"]["weak_match"]["note"]


def test_no_groups_precision_evidence_shortfall():
    rr = _clean_run_result()
    rr["preview_groups"] = []
    rr["sent_groups"] = []
    v = measure_digest_quality(rr)
    assert v["precision_risk"] == 0
    assert v["precision_ok"] is True
    assert "측정 근거 부족" in v["detail"]["precision"]["note"]


def test_excluded_count_only_is_evidence_shortfall():
    """date_excluded 리스트가 없고 count 만 있으면 주말엣지는 근거부족(0)."""
    rr = _clean_run_result()
    rr.pop("date_excluded", None)
    rr["date_excluded_count"] = 5
    v = measure_digest_quality(rr)
    assert v["detail"]["recall"]["excluded_recent_weekend"]["count"] == 0
    assert "측정 근거 부족" in v["detail"]["recall"]["excluded_recent_weekend"]["note"]


def test_write_report_roundtrip(tmp_path):
    v = measure_digest_quality(_clean_run_result())
    out = tmp_path / "digest_quality_test.json"
    p = write_digest_quality_report(v, path=out)
    assert p.exists()
    import json
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["delivered"] == 7 and loaded["recall_ok"] is True
