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
    assert deliverable[0]["_change_type"] == "DEADLINE_EXTENDED"
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


def test_detail_fetch_failure_does_not_create_false_updated():
    """재조회 중 상세 FETCH 실패로 필드가 비어도 @vN 재발송하지 않는다."""
    before = item("fail", "2026-07-20")
    snap = m._notice_version_snapshot(before)
    versions = {
        "fail": {
            "version": 1,
            "list_hash": m._notice_list_hash(before),
            "delivered_hash": m._notice_snapshot_hash(snap),
            "delivered_snapshot": snap,
            "observed_hash": m._notice_snapshot_hash(snap),
        }
    }
    thin = item(
        "fail",
        "2026-07-20",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        detail_extraction={"status": "DETAIL_FETCH_FAILED"},
    )
    thin.pop("application_period", None)
    deliverable, updates = m.classify_notice_versions([thin], {"fail"}, versions)
    assert deliverable == []
    assert updates["fail"].get("unreliable_observe") is True
    assert updates["fail"]["delivery_id"] == "fail"


def test_unreliable_observation_commit_preserves_delivered_snapshot(
    monkeypatch,
    tmp_path,
):
    """classify → commit → 정상복구 뒤에도 허위 @v2가 생기지 않는다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    before = item("recover", "2026-07-20")
    delivered_snapshot = m._notice_version_snapshot(before)
    delivered_hash = m._notice_snapshot_hash(delivered_snapshot)
    versions = {
        "recover": {
            "version": 1,
            "delivery_id": "recover",
            "delivered_hash": delivered_hash,
            "delivered_snapshot": delivered_snapshot,
            "observed_hash": delivered_hash,
        }
    }
    thin = item(
        "recover",
        "2026-07-20",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        detail_extraction={"status": "DETAIL_FETCH_FAILED"},
    )

    deliverable, updates = m.classify_notice_versions(
        [thin],
        {"recover"},
        versions,
    )
    assert deliverable == []
    committed = m.commit_notice_versions(versions, updates, {"recover"})
    assert committed["recover"]["delivered_hash"] == delivered_hash
    assert committed["recover"]["delivered_snapshot"] == delivered_snapshot

    recovered, _ = m.classify_notice_versions(
        [before],
        {"recover"},
        committed,
    )
    assert recovered == []


def test_missing_delivered_hash_seeds_instead_of_version_bump():
    """observed만 있고 delivered_hash가 없는 seen 공고는 @v2가 아니라 seed."""
    source = item("pending", "2026-07-24")
    snap = m._notice_version_snapshot(source)
    versions = {
        "pending": {
            "list_hash": m._notice_list_hash(source),
            "observed_hash": m._notice_snapshot_hash(snap),
            "observed_snapshot": snap,
            "pending_delivery_id": "pending",
            "last_seen_at": "2026-07-27T10:00:00+09:00",
        }
    }
    deliverable, updates = m.classify_notice_versions([source], {"pending"}, versions)
    assert deliverable == []
    assert updates["pending"].get("seed_only") is True


def test_seed_path_fetch_failure_does_not_promote_thin_delivered(
    monkeypatch,
    tmp_path,
):
    """seen 이지만 versions 없는 공고 + DETAIL_FETCH_FAILED 는 seed_only 로
    빈 delivered_* 를 심지 않는다. 다음 정상 enrich 가 허위 @v2 를 만들지 않아야 한다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    thin = item(
        "seedfail",
        "2026-07-24",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        author="",
        detail_extraction={"status": "DETAIL_FETCH_FAILED"},
        _version_seed_only=True,
    )
    deliverable, updates = m.classify_notice_versions([thin], {"seedfail"}, {})
    assert deliverable == []
    assert updates["seedfail"].get("unreliable_observe") is True
    assert updates["seedfail"].get("seed_only") is not True

    committed = m.commit_notice_versions({}, updates, {"seedfail"})
    assert not committed["seedfail"].get("delivered_hash")
    assert committed["seedfail"].get("observed_hash")

    full = item("seedfail", "2026-07-24")
    recovered, updates2 = m.classify_notice_versions([full], {"seedfail"}, committed)
    assert recovered == []
    assert updates2["seedfail"].get("seed_only") is True
    seeded = m.commit_notice_versions(committed, updates2, {"seedfail"})
    assert seeded["seedfail"].get("delivered_hash")
    # 시드 이후 동일 본문은 재발송 없음
    again, _ = m.classify_notice_versions([full], {"seedfail"}, seeded)
    assert again == []


def test_pending_without_delivered_hash_fetch_failure_does_not_promote(
    monkeypatch,
    tmp_path,
):
    """delivered_hash 없는 pending 레코드 + FETCH 실패도 빈 스냅샷을 승격하지 않는다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    full = item("pendfail", "2026-07-24")
    snap = m._notice_version_snapshot(full)
    versions = {
        "pendfail": {
            "version": 1,
            "delivery_id": "pendfail",
            "list_hash": m._notice_list_hash(full),
            "observed_hash": m._notice_snapshot_hash(snap),
            "observed_snapshot": snap,
            "pending_delivery_id": "pendfail",
        }
    }
    thin = item(
        "pendfail",
        "2026-07-24",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        detail_extraction={"status": "DETAIL_FETCH_FAILED"},
    )
    deliverable, updates = m.classify_notice_versions([thin], {"pendfail"}, versions)
    assert deliverable == []
    assert updates["pendfail"].get("unreliable_observe") is True
    committed = m.commit_notice_versions(versions, updates, {"pendfail"})
    assert not committed["pendfail"].get("delivered_hash")
    assert committed["pendfail"].get("pending_delivery_id") == "pendfail"

    recovered, _ = m.classify_notice_versions([full], {"pendfail"}, committed)
    # 정상 enrich 후 seed 가능 — 허위 @v2(EXTENDED) 가 아니어야 한다
    assert recovered == []


def test_real_deadline_extension_still_versions_after_reliable_enrich():
    """추출 성공 상태의 실제 마감 연장은 계속 @vN 재발송한다."""
    before = item("extend2", "2026-07-20", deadline="2026-07-25")
    snap = m._notice_version_snapshot(before)
    versions = {
        "extend2": {
            "version": 1,
            "list_hash": m._notice_list_hash(before),
            "delivered_hash": m._notice_snapshot_hash(snap),
            "delivered_snapshot": snap,
            "observed_hash": m._notice_snapshot_hash(snap),
        }
    }
    after = item(
        "extend2",
        "2026-07-20",
        deadline="2026-08-10",
        detail_extraction={"status": "SUCCESS"},
    )
    deliverable, updates = m.classify_notice_versions([after], {"extend2"}, versions)
    assert deliverable[0]["_change_type"] == "DEADLINE_EXTENDED"
    assert deliverable[0]["_delivery_id"] == "extend2@v2"
    assert updates["extend2"]["version"] == 2


def test_new_path_fetch_failure_does_not_promote_thin_delivered(
    monkeypatch,
    tmp_path,
):
    """미seen NEW + DETAIL_FETCH_FAILED 는 첫 메일은 나가되, 얇은 스냅샷을
    delivered_* 로 잠그지 않는다. 다음 정상 enrich 가 허위 @v2 를 만들면 안 된다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 7, 31, 10, tzinfo=m.KST)
    thin = item(
        "newfail",
        "2026-07-30",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        author="",
        detail_extraction={"status": "DETAIL_FETCH_FAILED"},
    )
    deliverable, updates = m.classify_notice_versions([thin], set(), {})
    assert len(deliverable) == 1
    assert deliverable[0]["_change_type"] == "NEW"
    assert deliverable[0]["_delivery_id"] == "newfail"
    assert updates["newfail"].get("unreliable_new") is True

    # 발송 완료 후 seen 에 들어가도 delivered_* 는 비워 둔다
    committed = m.commit_notice_versions({}, updates, {"newfail"}, now=now)
    assert not committed["newfail"].get("delivered_hash")
    assert committed["newfail"].get("change_type") == "NEW"
    assert committed["newfail"].get("pending_delivery_id") == ""

    full = item("newfail", "2026-07-30")
    recovered, updates2 = m.classify_notice_versions([full], {"newfail"}, committed)
    assert recovered == []
    assert updates2["newfail"].get("seed_only") is True
    seeded = m.commit_notice_versions(committed, updates2, {"newfail"}, now=now)
    assert seeded["newfail"].get("delivered_hash")
    again, _ = m.classify_notice_versions([full], {"newfail"}, seeded)
    assert again == []


def test_new_path_parse_failure_then_enrich_does_not_version_bump(
    monkeypatch,
    tmp_path,
):
    """PARSE_FAILED NEW 발송 후 필드가 채워져도 EXTENDED/UPDATED @v2 가 아니어야 한다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 7, 31, 10, tzinfo=m.KST)
    thin = item(
        "newparse",
        "2026-07-30",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        author="",
        detail_extraction={"status": "PARSE_FAILED"},
    )
    _d, updates = m.classify_notice_versions([thin], set(), {})
    committed = m.commit_notice_versions({}, updates, {"newparse"}, now=now)
    full = item("newparse", "2026-07-30", deadline="2026-08-15")
    recovered, updates2 = m.classify_notice_versions([full], {"newparse"}, committed)
    assert recovered == []
    assert updates2["newparse"].get("seed_only") is True


def test_reliable_new_still_promotes_delivered_snapshot(monkeypatch, tmp_path):
    """추출 성공 NEW 는 기존처럼 delivered_* 를 승격하고 동일본 재발송이 없다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 7, 31, 10, tzinfo=m.KST)
    source = item(
        "newok",
        "2026-07-30",
        detail_extraction={"status": "SUCCESS"},
    )
    deliverable, updates = m.classify_notice_versions([source], set(), {})
    assert deliverable[0]["_change_type"] == "NEW"
    assert updates["newok"].get("unreliable_new") is not True
    committed = m.commit_notice_versions({}, updates, {"newok"}, now=now)
    assert committed["newok"].get("delivered_hash")
    again, _ = m.classify_notice_versions([source], {"newok"}, committed)
    assert again == []


def test_success_enrich_empty_deadline_does_not_lock_false_vn(
    monkeypatch,
    tmp_path,
):
    """SUCCESS enrich 인데 마감이 비어 있으면 delivered_* 를 잠그지 않는다.

    본문 파싱이 마감을 못 찾은 채 SUCCESS 로 끝나면 empty baseline 이 승격되고,
    다음 수집에서 마감이 채워질 때 허위 DEADLINE_EXTENDED id@vN 이 나간다.
    """
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 7, 31, 10, tzinfo=m.KST)
    thin = item(
        "success_empty",
        "2026-07-30",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        author="",
        detail_extraction={"status": "SUCCESS"},
    )
    deliverable, updates = m.classify_notice_versions([thin], set(), {})
    assert len(deliverable) == 1
    assert deliverable[0]["_change_type"] == "NEW"
    assert updates["success_empty"].get("unreliable_new") is True

    committed = m.commit_notice_versions({}, updates, {"success_empty"}, now=now)
    assert not committed["success_empty"].get("delivered_hash")

    filled = item(
        "success_empty",
        "2026-07-30",
        deadline="2026-08-15",
        detail_extraction={"status": "SUCCESS"},
    )
    recovered, updates2 = m.classify_notice_versions(
        [filled], {"success_empty"}, committed
    )
    assert recovered == []
    assert updates2["success_empty"].get("seed_only") is True
    seeded = m.commit_notice_versions(committed, updates2, {"success_empty"}, now=now)
    assert seeded["success_empty"].get("delivered_hash")
    again, _ = m.classify_notice_versions([filled], {"success_empty"}, seeded)
    assert again == []


def test_success_enrich_empty_deadline_observe_does_not_seed(
    monkeypatch,
    tmp_path,
):
    """이미 seen 인 SUCCESS+빈마감 관찰도 seed_only 로 빈 baseline 을 심지 않는다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 7, 31, 10, tzinfo=m.KST)
    before = item("obs_empty", "2026-07-20", deadline="2026-07-25")
    snap = m._notice_version_snapshot(before)
    versions = {
        "obs_empty": {
            "version": 1,
            "list_hash": m._notice_list_hash(before),
            "delivered_hash": m._notice_snapshot_hash(snap),
            "delivered_snapshot": snap,
            "observed_hash": m._notice_snapshot_hash(snap),
        }
    }
    thin = item(
        "obs_empty",
        "2026-07-20",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        author="",
        detail_extraction={"status": "SUCCESS"},
    )
    deliverable, updates = m.classify_notice_versions([thin], {"obs_empty"}, versions)
    assert deliverable == []
    assert updates["obs_empty"].get("unreliable_observe") is True
    committed = m.commit_notice_versions(versions, updates, {"obs_empty"}, now=now)
    assert committed["obs_empty"].get("delivered_hash") == versions["obs_empty"]["delivered_hash"]
    assert committed["obs_empty"].get("delivered_snapshot") == snap


def test_new_missing_detail_extraction_thin_does_not_promote(
    monkeypatch,
    tmp_path,
):
    """enrich 예산 스킵 등으로 detail_extraction 없는 얇은 NEW 는 첫 메일은 나가되
    delivered_* 를 잠그지 않는다. 다음 SUCCESS enrich 가 DEADLINE_EXTENDED @v2 를
    만들면 안 된다."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 8, 13, 10, tzinfo=m.KST)
    thin = item(
        "newskip",
        "2026-08-12",
        deadline="",
        support_field="",
        target_field="",
        region_field="",
        description="",
        author="",
    )
    # enrich 미실행: detail_extraction 키 없음
    thin.pop("application_period", None)
    assert "detail_extraction" not in thin

    deliverable, updates = m.classify_notice_versions([thin], set(), {})
    assert len(deliverable) == 1
    assert deliverable[0]["_change_type"] == "NEW"
    assert updates["newskip"].get("unreliable_new") is True

    committed = m.commit_notice_versions({}, updates, {"newskip"}, now=now)
    assert not committed["newskip"].get("delivered_hash")

    full = item(
        "newskip",
        "2026-08-12",
        deadline="2026-09-30",
        detail_extraction={"status": "SUCCESS"},
    )
    recovered, updates2 = m.classify_notice_versions([full], {"newskip"}, committed)
    assert recovered == []
    assert updates2["newskip"].get("seed_only") is True
    seeded = m.commit_notice_versions(committed, updates2, {"newskip"}, now=now)
    assert seeded["newskip"].get("delivered_hash")
    again, _ = m.classify_notice_versions([full], {"newskip"}, seeded)
    assert again == []


def test_list_complete_without_detail_extraction_still_promotes(monkeypatch, tmp_path):
    """리스트에 마감이 이미 있으면 detail_extraction 없이도 baseline 승격·실연장 감지."""
    monkeypatch.setattr(m, "NOTICE_VERSIONS_PATH", tmp_path / "notice_versions.json")
    monkeypatch.setattr(m, "_ALLOW_PERSIST_SEEN", True)
    now = datetime(2026, 8, 13, 10, tzinfo=m.KST)
    source = item("listok", "2026-08-12", deadline="2026-08-31")
    assert "detail_extraction" not in source

    deliverable, updates = m.classify_notice_versions([source], set(), {})
    assert deliverable[0]["_change_type"] == "NEW"
    assert updates["listok"].get("unreliable_new") is not True
    committed = m.commit_notice_versions({}, updates, {"listok"}, now=now)
    assert committed["listok"].get("delivered_hash")

    extended = item(
        "listok",
        "2026-08-12",
        deadline="2026-09-15",
        detail_extraction={"status": "SUCCESS"},
    )
    bumped, _ = m.classify_notice_versions([extended], {"listok"}, committed)
    assert len(bumped) == 1
    assert bumped[0]["_change_type"] == "DEADLINE_EXTENDED"
    assert bumped[0]["_delivery_id"] == "listok@v2"


def test_material_support_change_outside_days_back_is_force_reprocessed():
    """이미 seen 이고 게시일이 days_back 밖이어도 지원내용 material @vN 은 재처리한다.

    Pre-fix: support/title material 변경이 MINOR_TEXT_CHANGE 로 분류되면
    partition_posted_dates 가 제외하고 _IMPORTANT_CHANGE_TYPES 강제재처리도
    빗나가 영구 침묵 누락이 난다.
    """
    now = datetime(2026, 8, 23, 10, tzinfo=m.KST)
    before = item(
        "old-support",
        "2026-01-05",
        deadline="2026-12-31",
        support_field="최대 1천만원",
        description="최대 1천만원",
    )
    after = item(
        "old-support",
        "2026-01-05",
        deadline="2026-12-31",
        support_field="최대 3천만원",
        description="최대 3천만원",
        title="2026년 AI 사업화 지원사업 (예산 증액)",
    )
    snap = m._notice_version_snapshot(before)
    versions = {
        "old-support": {
            "version": 1,
            "delivery_id": "old-support",
            "delivered_hash": m._notice_snapshot_hash(snap),
            "delivered_snapshot": snap,
            "list_hash": m._notice_list_hash(before),
        }
    }
    deliverable, _ = m.classify_notice_versions([after], {"old-support"}, versions)
    assert len(deliverable) == 1
    assert deliverable[0]["_delivery_id"] == "old-support@v2"
    assert deliverable[0]["_change_type"] in {
        "SUPPORT_AMOUNT_CHANGED",
        "UPDATED",
    }
    assert set(deliverable[0]["_changed_fields"]) & m._NOTICE_VERSION_MATERIAL_FIELDS

    matched, _, excluded = m.partition_posted_dates(deliverable, days_back=3, now_dt=now)
    assert matched == []
    assert len(excluded) == 1

    # Mirror execute_monitor force-reprocess gate
    important = {
        "EXTENDED", "REANNOUNCED", "UPDATED",
        "DEADLINE_EXTENDED", "TARGET_CHANGED", "SUPPORT_AMOUNT_CHANGED",
        "APPLICATION_URL_CHANGED", "REANNOUNCEMENT", "ADDITIONAL_RECRUITMENT",
    }
    filtered = list(matched)
    filtered_ids = {m._delivery_notice_id(it) for it in filtered}
    for it in deliverable:
        changed_material = set(it.get("_changed_fields") or []) & m._NOTICE_VERSION_MATERIAL_FIELDS
        if it.get("_change_type") not in important and not changed_material:
            raise AssertionError("material @vN must qualify for force reprocess")
        if m.classify_deadline_status(it, now.date()) == "closed":
            continue
        did = m._delivery_notice_id(it)
        if did and did not in filtered_ids:
            filtered.append({**it, "_forced_change_reprocess": True})
            filtered_ids.add(did)
    assert len(filtered) == 1
    assert filtered[0].get("_forced_change_reprocess") is True
