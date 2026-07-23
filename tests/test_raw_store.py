import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

for _k, _v in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@test.com",
    "GMAIL_APP_PASSWORD": "test_pass",
}.items():
    os.environ.setdefault(_k, _v)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from raw_store import RawStore, safe_notice_dirname  # noqa: E402


def test_safe_notice_dirname():
    assert safe_notice_dirname("bizinfo_abc/123") == "bizinfo_abc_123"


def test_save_meta_and_detail(tmp_path):
    store = RawStore(root=tmp_path, run_day=date(2026, 6, 24), retention_days=30)
    store.begin_run(collected=10, deduped=8, new_items=2)
    item = {
        "id": "test_notice_1",
        "title": "테스트 공고",
        "link": "https://example.com/1",
        "source": "테스트",
        "description": "요약",
    }
    store.save_item_meta(item)
    store.save_detail_html("test_notice_1", item["link"], "<html>본문</html>")
    store.update_meta_after_enrich({**item, "detail_enriched": True, "region_field": "인천"})

    meta = RawStore.load_meta("test_notice_1", root=tmp_path, run_day=date(2026, 6, 24))
    assert meta["title"] == "테스트 공고"
    assert meta["region_field"] == "인천"
    html = RawStore.load_detail_html("test_notice_1", root=tmp_path, run_day=date(2026, 6, 24))
    assert "본문" in (html or "")

    s = store.summary()
    assert s["raw_store_meta_saved"] >= 2
    assert s["raw_store_detail_saved"] == 1


def test_prune_old(tmp_path):
    old = tmp_path / "2026-01-01" / "notices" / "x"
    old.mkdir(parents=True)
    (old / "meta.json").write_text("{}", encoding="utf-8")
    keep = tmp_path / "2026-06-20" / "notices" / "y"
    keep.mkdir(parents=True)
    (keep / "meta.json").write_text("{}", encoding="utf-8")

    store = RawStore(root=tmp_path, run_day=date(2026, 6, 24), retention_days=30)
    removed = store.prune_old()
    assert removed == 1
    assert not (tmp_path / "2026-01-01").exists()
    assert (tmp_path / "2026-06-20").exists()


def test_from_settings_disabled():
    assert RawStore.from_settings({"raw_store_enabled": False}) is None


def test_from_settings_enabled(tmp_path):
    store = RawStore.from_settings(
        {"raw_store_enabled": True, "raw_store_dir": str(tmp_path), "raw_store_retention_days": 7},
        run_day=date(2026, 6, 24),
    )
    assert store is not None
    assert store.root == tmp_path
