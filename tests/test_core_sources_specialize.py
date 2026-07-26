# -*- coding: utf-8 -*-
"""기업마당·K-Startup 핵심소스 특화 단위 테스트."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.matching import core_sources as cs  # noqa: E402


def test_attach_bizinfo_structured_promotes_api_fields():
    raw = {
        "pldirSportRealmLclasCodeNm": "기술개발",
        "trgetNm": "중소기업",
        "jrsdAreaNm": "전국",
    }
    base = {
        "id": "PBLN_1", "title": "t", "link": "https://www.bizinfo.go.kr/x",
        "author": "중기부", "description": "요약", "deadline": "",
        "source": "기업마당(Bizinfo)", "posted_date": "2026-07-20",
        "is_aggregator": True,
    }
    out = cs.attach_bizinfo_structured(base, raw)
    assert out["core_source"] == "bizinfo"
    assert out["support_field"] == "기술개발"
    assert out["target_field"] == "중소기업"
    assert out["region_field"] == "전국"


def test_attach_kstartup_list_sets_support_from_flag():
    base = {
        "id": "kstartup_1", "title": "팁스", "link": "https://www.k-startup.go.kr/x",
        "author": "창업진흥원", "description": "", "deadline": "",
        "source": "K-Startup", "posted_date": "2026-07-20",
        "is_aggregator": False,
    }
    out = cs.attach_kstartup_list_structured(
        base, flag_text="공공 R&D 지원", clss="PBC010")
    assert out["core_source"] == "kstartup"
    assert out["support_field"] == "공공 R&D 지원"
    assert out["kstartup_class"] == "PBC010"
    assert out["kstartup_sector"] == "공공"
    assert "지원금/바우처" in cs.map_category_to_support_types(out["support_field"])


def test_select_detail_enrich_prioritizes_core_and_recent():
    items = []
    for i in range(5):
        items.append({
            "id": f"nipa_{i}",
            "link": "https://www.nipa.kr/n",
            "posted_date": "2026-07-20",
        })
    for i in range(3):
        items.append({
            "id": f"bizinfo_{i}",
            "link": "https://www.bizinfo.go.kr/b",
            "posted_date": "2025-01-01",
            "core_source": "bizinfo",
        })
    items.append({
        "id": "bizinfo_new",
        "link": "https://www.bizinfo.go.kr/b",
        "posted_date": "2026-07-22",
        "core_source": "bizinfo",
    })
    items.append({
        "id": "kstartup_new",
        "link": "https://www.k-startup.go.kr/k",
        "posted_date": "2026-07-21",
        "core_source": "kstartup",
    })
    selected = cs.select_detail_enrich_targets(
        items,
        specialized_hosts=("bizinfo.go.kr", "k-startup.go.kr", "nipa.kr"),
        core_limit=3,
        other_limit=2,
        today=date(2026, 7, 26),
    )
    ids = [it["id"] for it in selected]
    # 최근 핵심이 앞에
    assert ids[0] in {"bizinfo_new", "kstartup_new"}
    assert "bizinfo_new" in ids and "kstartup_new" in ids
    # nipa 는 other 예산
    assert sum(1 for i in ids if i.startswith("nipa_")) == 2
    assert len(selected) == 5  # core 3 + other 2


def test_keyword_extra_parts_only_for_core():
    core = {
        "core_source": "kstartup",
        "region_field": "인천",
        "business_age_text": "7년 미만",
        "link": "https://www.k-startup.go.kr/x",
    }
    other = {"link": "https://other.go.kr/x", "region_field": "서울"}
    assert "인천" in cs.keyword_extra_parts(core)
    assert cs.keyword_extra_parts(other) == []


def test_sites_json_core_collection_depth():
    import json
    sites = {s["id"]: s for s in json.loads((ROOT / "config/sites.json").read_text())}
    assert sites["bizinfo"]["api_max_pages"] >= 6
    assert sites["bizinfo"].get("datagokr_max_pages", 0) >= 6
    assert sites["kstartup"]["max_pages"] >= 10


def test_detector_core_stricter_than_defaults():
    from mail_core.operations import detector_config as dc
    cfg = dc.load_detector_config()
    assert dc.fetch_failed_risk_for_site(cfg, "bizinfo") == "P0"
    assert dc.fetch_failed_risk_for_site(cfg, "kstartup") == "P0"
    biz = dc.site_policy(cfg, "bizinfo")
    assert float(biz["valid_record_min_rate"]) >= 0.95
    assert float(biz["drop_ratio_p0"]) >= 0.3
