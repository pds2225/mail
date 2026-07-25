from __future__ import annotations

import json
import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, got {count}")
    return text.replace(old, new, 1)


root = Path('.')
monitor_path = root / 'monitor.py'
text = monitor_path.read_text(encoding='utf-8')

text = replace_once(
    text,
    'SEEN_IDS_PATH = STATE_DIR / "seen_ids.json"\n# (기준일·그룹·수신자) 단위 발송 멱등 상태',
    'SEEN_IDS_PATH = STATE_DIR / "seen_ids.json"\nNOTICE_VERSIONS_PATH = STATE_DIR / "notice_versions.json"\n# (기준일·그룹·수신자) 단위 발송 멱등 상태',
    'notice versions path',
)

helpers = r'''

_NOTICE_VERSION_MATERIAL_FIELDS = frozenset({
    "title", "deadline", "application_period", "target", "support", "region",
})


def _notice_date_fields(item: dict) -> dict[str, str]:
    """게시일·등록일·수정일을 별도 표준 필드로 보존한다."""
    return {
        "published_at": str(item.get("published_at") or item.get("posted_date") or "").strip()[:10],
        "registered_at": str(item.get("registered_at") or item.get("registered_date") or item.get("reg_date") or "").strip()[:10],
        "updated_at": str(item.get("updated_at") or item.get("updated_date") or item.get("modified_at") or "").strip()[:10],
    }


def _notice_version_snapshot(item: dict) -> dict[str, str]:
    period = item.get("application_period") or {}
    return {
        "title": strip_title_badges(norm(item.get("title"))),
        "author": norm(item.get("author")),
        "deadline": resolve_item_deadline(item),
        "application_period": str(period.get("display") or "").strip(),
        "target": norm(item.get("target_field") or item.get("target_age_field")),
        "support": _mail_clean_text(item.get("support_field") or item.get("description") or "", limit=600),
        "region": norm(item.get("region_field")),
        **_notice_date_fields(item),
    }


def _notice_snapshot_hash(snapshot: dict[str, str]) -> str:
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _notice_list_hash(item: dict) -> str:
    return _notice_snapshot_hash({
        "title": strip_title_badges(norm(item.get("title"))),
        "author": norm(item.get("author")),
        "deadline": norm(item.get("deadline")),
        "link": norm(item.get("link")),
        **_notice_date_fields(item),
    })


def load_notice_versions() -> dict[str, dict]:
    raw = load_json(NOTICE_VERSIONS_PATH, {})
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def save_notice_versions(versions: dict[str, dict]) -> None:
    if not _ALLOW_PERSIST_SEEN or os.environ.get("MONITOR_NO_PERSIST_SEEN") == "1":
        log.info("notice_versions 저장 생략 (persist_seen=False)")
        return
    ordered = dict(sorted(
        versions.items(), key=lambda pair: str(pair[1].get("last_seen_at") or ""), reverse=True,
    )[:10000])
    save_json(NOTICE_VERSIONS_PATH, ordered)


def _delivery_notice_id(item: dict) -> str:
    return str(item.get("_delivery_id") or item.get("id") or "")


def _recent_recheck_dates(now: datetime, days_back: int) -> set:
    return {previous_business_day(now, offset) for offset in range(1, max(1, int(days_back or 1)) + 1)}


def _item_recent_for_recheck(item: dict, now: datetime, days_back: int) -> bool:
    targets = _recent_recheck_dates(now, days_back)
    oldest, today = min(targets), now.date()
    for value in _notice_date_fields(item).values():
        if not value:
            continue
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            continue
        if parsed in targets or (oldest < parsed < today and parsed.weekday() >= 5):
            return True
    return False


def select_notice_version_candidates(items: list[dict], seen_ids: set[str], versions: dict[str, dict], *, now: datetime, days_back: int) -> list[dict]:
    """신규·최근 N영업일·목록변경·미전달 변경만 상세보강 대상으로 고른다."""
    selected: list[dict] = []
    for item in items:
        iid = str(item.get("id") or "")
        if not iid:
            continue
        if iid not in seen_ids:
            selected.append(item)
            continue
        previous = versions.get(iid)
        if previous is None:
            if _item_recent_for_recheck(item, now, days_back):
                selected.append({**item, "_version_seed_only": True})
            continue
        pending = bool(previous.get("observed_hash") and previous.get("observed_hash") != previous.get("delivered_hash"))
        if pending or _notice_list_hash(item) != previous.get("list_hash") or _item_recent_for_recheck(item, now, days_back):
            selected.append(item)
    return selected


def _snapshot_changed_fields(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def _latest_date_from_text(value: str):
    dates = [parsed for _pos, parsed in _parse_date_candidates(str(value or ""))]
    return max(dates) if dates else None


def _classify_notice_change(before: dict, after: dict) -> str:
    if "재공고" in str(after.get("title") or "") and "재공고" not in str(before.get("title") or ""):
        return "REANNOUNCED"
    old_deadline = _latest_date_from_text(str(before.get("application_period") or before.get("deadline") or ""))
    new_deadline = _latest_date_from_text(str(after.get("application_period") or after.get("deadline") or ""))
    if new_deadline and (old_deadline is None or new_deadline > old_deadline):
        return "EXTENDED"
    return "UPDATED"


def classify_notice_versions(items: list[dict], seen_ids: set[str], versions: dict[str, dict]) -> tuple[list[dict], dict[str, dict]]:
    deliverable: list[dict] = []
    updates: dict[str, dict] = {}
    now_iso = datetime.now(KST).isoformat()
    for source in items:
        item = {**source, **_notice_date_fields(source)}
        iid = str(item.get("id") or "")
        if not iid:
            continue
        snapshot = _notice_version_snapshot(item)
        current_hash = _notice_snapshot_hash(snapshot)
        previous = versions.get(iid)
        base = {"snapshot": snapshot, "content_hash": current_hash, "list_hash": _notice_list_hash(item), "last_seen_at": now_iso}
        if iid not in seen_ids:
            version = max(1, int((previous or {}).get("version", 0) or 0))
            deliverable.append({**item, "_change_type": "NEW", "_notice_version": version, "_delivery_id": iid, "_changed_fields": list(snapshot)})
            updates[iid] = {**base, "version": version, "delivery_id": iid}
            continue
        if previous is None or item.get("_version_seed_only"):
            updates[iid] = {**base, "version": 1, "delivery_id": iid, "seed_only": True}
            continue
        old_snapshot = previous.get("delivered_snapshot") or {}
        old_hash = str(previous.get("delivered_hash") or "")
        changed = _snapshot_changed_fields(old_snapshot, snapshot)
        material = sorted(set(changed) & _NOTICE_VERSION_MATERIAL_FIELDS)
        if current_hash == old_hash or not material:
            updates[iid] = {**base, "version": int(previous.get("version", 1) or 1), "delivery_id": str(previous.get("delivery_id") or iid)}
            continue
        version = int(previous.get("version", 1) or 1) + 1
        change_type = _classify_notice_change(old_snapshot, snapshot)
        delivery_id = f"{iid}@v{version}"
        deliverable.append({**item, "_change_type": change_type, "_notice_version": version, "_delivery_id": delivery_id, "_changed_fields": material})
        updates[iid] = {**base, "version": version, "delivery_id": delivery_id, "change_type": change_type, "changed_fields": material}
    return deliverable, updates


def commit_notice_versions(versions: dict[str, dict], updates: dict[str, dict], seen_ids: set[str], *, now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now(KST)
    merged = {str(k): dict(v) for k, v in versions.items() if isinstance(v, dict)}
    for iid, update in updates.items():
        record = dict(merged.get(iid) or {})
        record.update({
            "list_hash": update.get("list_hash", ""),
            "observed_hash": update.get("content_hash", ""),
            "observed_snapshot": update.get("snapshot", {}),
            "last_seen_at": update.get("last_seen_at") or now.isoformat(),
            "pending_delivery_id": update.get("delivery_id", ""),
        })
        delivery_id = str(update.get("delivery_id") or iid)
        if update.get("seed_only") or delivery_id in seen_ids:
            record.update({
                "version": int(update.get("version", record.get("version", 1)) or 1),
                "delivery_id": delivery_id,
                "delivered_hash": update.get("content_hash", ""),
                "delivered_snapshot": update.get("snapshot", {}),
                "last_delivered_at": now.isoformat(),
                "change_type": update.get("change_type") or record.get("change_type") or "NEW",
                "pending_delivery_id": "",
            })
        merged[iid] = record
    save_notice_versions(merged)
    return merged
'''

text = replace_once(text, '\ndef normalize_title(title: str) -> str:\n', helpers + '\n\ndef normalize_title(title: str) -> str:\n', 'helpers')

pattern = re.compile(r'def partition_posted_dates\(.*?\n\ndef date_filter\(', re.S)
new_partition = r'''def partition_posted_dates(
    items: list[dict], days_back: int = 3, max_age_days: int | None = None,
    now_dt: datetime | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """최근 N영업일과 그 사이 주말 게시물을 재조회한다."""
    now = now_dt or datetime.now(KST)
    target_dates = _recent_recheck_dates(now, days_back)
    oldest, newest, today = min(target_dates), max(target_dates), now.date()
    matched, unknown, excluded = [], [], []

    def _in_window(d) -> bool:
        return d in target_dates or (oldest < d < today and d.weekday() >= 5)

    for it in items:
        pd = str(it.get("published_at") or it.get("posted_date") or "").strip()
        if not pd:
            unknown.append(it)
            continue
        try:
            item_date = datetime.strptime(pd[:10], "%Y-%m-%d").date()
        except ValueError:
            unknown.append(it)
            continue
        if max_age_days is not None and (today - item_date).days > max_age_days:
            excluded.append({**it, "_excluded_posted_date": pd[:10], "_excluded_reason": "too_old"})
        elif _in_window(item_date):
            matched.append(it)
        else:
            excluded.append({**it, "_excluded_posted_date": pd[:10]})
    log.info("날짜분류(최근 %d영업일, %s~%s): 확정 %d / 날짜불명 %d / 제외 %d", days_back, oldest, newest, len(matched), len(unknown), len(excluded))
    return matched, unknown, excluded


def date_filter('''
text, n = pattern.subn(new_partition, text, count=1)
if n != 1:
    raise RuntimeError(f'partition replace failed: {n}')

text = replace_once(text, '    days_back = settings.get("days_back", 1)\n', '    days_back = max(1, int(settings.get("days_back", 3) or 3))\n', 'days_back')

old_block = '''    # ③ 신규 필터 (seen_ids)
    new_items = [it for it in deduped if it["id"] and it["id"] not in seen_ids]
    log.info("신규(미발송): %d건 / 전체: %d건", len(new_items), len(deduped))

    if _RAW_STORE is not None:
        _RAW_STORE.begin_run(
            collected=len(all_items), deduped=len(deduped), new_items=len(new_items),
        )
        for it in new_items:
            _RAW_STORE.save_item_meta(it)

    new_items = enrich_items(new_items)
'''
new_block = '''    # ③ 신규 + 최근 N영업일 재검사 + 수정/연장/재공고 버전 판정
    notice_versions = load_notice_versions()
    version_candidates = select_notice_version_candidates(
        deduped, seen_ids, notice_versions, now=now, days_back=days_back,
    )
    enriched_candidates = enrich_items(version_candidates)
    new_items, notice_version_updates = classify_notice_versions(enriched_candidates, seen_ids, notice_versions)
    brand_new_count = sum(1 for it in new_items if it.get("_change_type") == "NEW")
    changed_count = len(new_items) - brand_new_count
    log.info("처리대상: 신규 %d / 중요변경 %d / 버전검사 %d", brand_new_count, changed_count, len(version_candidates))

    if _RAW_STORE is not None:
        _RAW_STORE.begin_run(collected=len(all_items), deduped=len(deduped), new_items=len(new_items))
        for it in new_items:
            _RAW_STORE.save_item_meta(it)
'''
text = replace_once(text, old_block, new_block, 'new filter')

text = replace_once(
    text,
    '    target_date = previous_business_day(now, days_back)\n    date_str    = now.strftime("%m/%d")\n',
    '    recheck_dates = sorted(_recent_recheck_dates(now, days_back))\n    target_date = recheck_dates[0]\n    window_label = f"{recheck_dates[0]} ~ {recheck_dates[-1]}"\n    date_str    = now.strftime("%m/%d")\n',
    'window label',
)

anchor = '''    else:
        filtered_new = new_items
        date_unknown = []
        date_excluded = []

    # 워치리스트 매칭분 강제포함 — 날짜필터로 빠졌어도 '절대 안 놓침'
'''
replacement = '''    else:
        filtered_new = new_items
        date_unknown = []
        date_excluded = []

    # 같은 ID의 중요 변경은 게시일이 과거여도 재처리한다. 여전히 마감된 단순수정은 제외.
    _filtered_ids = {_delivery_notice_id(it) for it in filtered_new}
    for it in new_items:
        if it.get("_change_type") not in {"EXTENDED", "REANNOUNCED", "UPDATED"}:
            continue
        if classify_deadline_status(it, now.date()) == "closed":
            continue
        did = _delivery_notice_id(it)
        if did and did not in _filtered_ids:
            filtered_new.append({**it, "_forced_change_reprocess": True})
            _filtered_ids.add(did)

    # 워치리스트 매칭분 강제포함 — 날짜필터로 빠졌어도 '절대 안 놓침'
'''
text = replace_once(text, anchor, replacement, 'force changed')

text = text.replace('notice_ids=[str(it.get("id") or "") for it in watch_hits],', 'notice_ids=[_delivery_notice_id(it) for it in watch_hits],')
text = text.replace('notice_ids=[str(it.get("id") or "") for it in raw_items],', 'notice_ids=[_delivery_notice_id(it) for it in raw_items],')
text = text.replace('notice_ids=[str(it.get("id") or "") for it in (g_items + ru_items)],', 'notice_ids=[_delivery_notice_id(it) for it in (g_items + ru_mail_items)],')
text = text.replace('f"기준일자: {target_date} (직전영업일) 공고\\n"', 'f"재조회범위: {window_label} (최근 {days_back}영업일)\\n"')

text = replace_once(text, '    if not filtered_new:\n        log.info("처리 대상 없음. 종료.")\n', '    if not filtered_new:\n        if persist_seen and _ALLOW_PERSIST_SEEN:\n            commit_notice_versions(notice_versions, notice_version_updates, seen_ids, now=now)\n        log.info("처리 대상 없음. 종료.")\n', 'early persist')
text = replace_once(text, '            "new_items": len(new_items),\n            "filtered_items": 0,', '            "new_items": len(new_items),\n            "brand_new_items": brand_new_count,\n            "changed_items": changed_count,\n            "filtered_items": 0,', 'early counts')
text = replace_once(text, '    if allow_send and persist_seen:\n        seen_ids = persist_completed_outbox(seen_ids)\n    log.info("=== 완료 ===")', '    if allow_send and persist_seen:\n        seen_ids = persist_completed_outbox(seen_ids)\n        commit_notice_versions(notice_versions, notice_version_updates, seen_ids, now=now)\n    log.info("=== 완료 ===")', 'final persist')
text = replace_once(text, '        "new_items": len(new_items),\n        "filtered_items": len(filtered_new),', '        "new_items": len(new_items),\n        "brand_new_items": brand_new_count,\n        "changed_items": changed_count,\n        "date_window": window_label,\n        "filtered_items": len(filtered_new),', 'final counts')
text = replace_once(text, '            title = strip_title_badges(_mail_clean_text(it.get("title") or "(제목없음)", limit=160))\n', '            title = strip_title_badges(_mail_clean_text(it.get("title") or "(제목없음)", limit=160))\n            _badge = {"EXTENDED": "[마감연장] ", "REANNOUNCED": "[재공고] ", "UPDATED": "[수정] "}.get(it.get("_change_type"), "")\n            title = _badge + title\n', 'badge')

monitor_path.write_text(text, encoding='utf-8')

settings_path = root / 'config/settings.json'
settings = json.loads(settings_path.read_text(encoding='utf-8'))
settings['days_back'] = 3
settings['notice_versioning_enabled'] = True
settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

state_path = root / 'var/state/notice_versions.json'
state_path.parent.mkdir(parents=True, exist_ok=True)
if not state_path.exists():
    state_path.write_text('{}\n', encoding='utf-8')

(root / 'scripts/merge_notice_versions.py').write_text(r'''from __future__ import annotations
import json, sys
from pathlib import Path

def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def merge_record(remote: dict, local: dict) -> dict:
    out = dict(remote)
    if str(local.get("last_seen_at") or "") >= str(remote.get("last_seen_at") or ""):
        for key in ("list_hash", "observed_hash", "observed_snapshot", "last_seen_at", "pending_delivery_id"):
            if key in local: out[key] = local[key]
    rv, lv = int(remote.get("version", 0) or 0), int(local.get("version", 0) or 0)
    if lv > rv or (lv == rv and str(local.get("last_delivered_at") or "") >= str(remote.get("last_delivered_at") or "")):
        for key in ("version", "delivery_id", "delivered_hash", "delivered_snapshot", "last_delivered_at", "change_type"):
            if key in local: out[key] = local[key]
    return out

def main() -> int:
    if len(sys.argv) != 3: return 2
    remote_path, local_path = map(Path, sys.argv[1:])
    remote, local = load(remote_path), load(local_path)
    for iid, record in local.items():
        if isinstance(record, dict): remote[str(iid)] = merge_record(remote.get(str(iid), {}), record)
    remote_path.parent.mkdir(parents=True, exist_ok=True)
    remote_path.write_text(json.dumps(remote, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
''', encoding='utf-8')

(root / 'tests/test_notice_version_recovery.py').write_text(r'''"""최근 3영업일 재조회와 수정·연장·재공고 복구 회귀테스트."""
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
''', encoding='utf-8')

workflow_path = root / '.github/workflows/monitor.yml'
workflow = workflow_path.read_text(encoding='utf-8')
workflow = workflow.replace('git add -f var/state/seen_ids.json data/golden/feedback_labels.jsonl var/state/delivery_state.json var/outbox/delivery_outbox.enc || true', 'git add -f var/state/seen_ids.json var/state/notice_versions.json data/golden/feedback_labels.jsonl var/state/delivery_state.json var/outbox/delivery_outbox.enc || true')
workflow = workflow.replace('            # 수신자별 delivery checkpoint/outbox 도 함께 보존한다. 이 둘을 잃으면 부분성공', '            if [ -f var/state/notice_versions.json ] && ! cp -f var/state/notice_versions.json /tmp/local_notice_versions.json; then\n              echo "::warning::notice_versions 백업 실패 — reset --hard 생략, 이번 재시도 건너뜀"\n              sleep 2; continue\n            fi\n            # 수신자별 delivery checkpoint/outbox 도 함께 보존한다. 이 둘을 잃으면 부분성공')
workflow = workflow.replace('            python scripts/merge_seen_ids.py var/state/seen_ids.json /tmp/local_seen_ids.json || true   # 원격 ∪ 우리\n', '            python scripts/merge_seen_ids.py var/state/seen_ids.json /tmp/local_seen_ids.json || true   # 원격 ∪ 우리\n            if [ -f /tmp/local_notice_versions.json ]; then\n              python scripts/merge_notice_versions.py var/state/notice_versions.json /tmp/local_notice_versions.json || true\n            fi\n')
workflow_path.write_text(workflow, encoding='utf-8')
print('notice recovery patch applied')
