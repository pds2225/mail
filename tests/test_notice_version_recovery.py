"""최근 3영업일 재조회와 수정·연장·재공고 복구 회귀테스트."""
import os, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
import monitor as m  # noqa: E402

def item(iid, posted, deadline="2026-08-01", **extra):
    value = {"id": iid, "title": "2026년 AI 사업화 지원사업", "author": "지원기관", "description": "서울 소재 AI 중소기업의 사업화 자금과 판로개척을 지원", "support_field": "사업화 자금과 판로개척 지원", "target_field": "서울 소재 AI 중소기업", "region_field": "서울", "deadline": deadline, "posted_date": posted, "link": f"https://example.com/{iid}", "source": "테스트", "is_aggregator": False}
    value.update(extra)
    return value

def test_three_business_day_window_recovers_delayed_index_and_weekend():
    now = datetime(2026, 7, 27, 8, tzinfo=m.KST)
    items = [item("wed", "2026-07-22"), item("thu", "2026-07-23"), item("fri", "2026-07-24"), item("sat", "2026-07-25"), item("sun", "2026-07-26"), item("old", "2026-07-21")]
    matched, _, excluded = m.partition_posted_dates(items, days_back=3, now_dt=now)
    assert {v["id"] for v in matched} == {"wed", "thu", "fri", "sat", "sun"}
    assert {v["id"] for v in excluded} == {"old"}
    matched_one, _, _ = m.partition_posted_dates(items, days_back=1, now_dt=now)
    assert "wed" not in {v["id"] for v in matched_one}

def test_seen_without_state_is_seeded_not_resent():
    source = item("seed", "2026-07-24")
    candidates = m.select_notice_version_candidates([source], {"seed"}, {}, now=datetime(2026, 7, 27, 8, tzinfo=m.KST), days_back=3)
    deliverable, updates = m.classify_notice_versions(candidates, {"seed"}, {})
    assert deliverable == [] and updates["seed"]["seed_only"] is True

def test_deadline_extension_creates_versioned_delivery_id():
    before = item("extend", "2026-07-20", deadline="2026-07-25")
    snap = m._notice_version_snapshot(before)
    versions = {"extend": {"version": 1, "list_hash": m._notice_list_hash(before), "delivered_hash": m._notice_snapshot_hash(snap), "delivered_snapshot": snap, "observed_hash": m._notice_snapshot_hash(snap)}}
    deliverable, updates = m.classify_notice_versions([item("extend", "2026-07-20", deadline="2026-08-10")], {"extend"}, versions)
    assert deliverable[0]["_change_type"] == "EXTENDED"
    assert deliverable[0]["_delivery_id"] == "extend@v2"
    assert "deadline" in deliverable[0]["_changed_fields"]
    assert updates["extend"]["version"] == 2

def test_unchanged_seen_notice_is_not_delivered_again():
    source = item("same", "2026-07-24")
    snap = m._notice_version_snapshot(source)
    digest = m._notice_snapshot_hash(snap)
    deliverable, _ = m.classify_notice_versions([source], {"same"}, {"same": {"version": 1, "delivered_hash": digest, "delivered_snapshot": snap}})
    assert deliverable == []

def test_version_advances_only_after_versioned_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    update = {"x": {"snapshot": {"title": "수정"}, "content_hash": "newhash", "list_hash": "listhash", "last_seen_at": "2026-07-25T10:00:00+09:00", "version": 2, "delivery_id": "x@v2", "change_type": "UPDATED"}}
    pending = m.commit_notice_versions({}, update, {"x"})
    assert pending["x"].get("delivered_hash") != "newhash"
    delivered = m.commit_notice_versions(pending, update, {"x", "x@v2"})
    assert delivered["x"]["delivered_hash"] == "newhash" and delivered["x"]["version"] == 2
