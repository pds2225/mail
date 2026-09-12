"""#281 KISED·IITP: query-id canonical collapse + list deadline-as-posted.

Enabling these sources without preserving pbancSn / PMS_TSK_PBNC_ID in
``generate_canonical_notice_id`` collapsed every notice to one canon_url.
Mis-mapping 마감/접수기간 → posted_date then excluded survivors via days_back.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

for _key, _value in {
    "BIZINFO_API_KEY": "test_key",
    "ANTHROPIC_API_KEY": "test_key",
    "GMAIL_ADDRESS": "test@example.invalid",
    "GMAIL_APP_PASSWORD": "test_pass",
    "MONITOR_NO_PERSIST_SEEN": "1",
}.items():
    os.environ.setdefault(_key, _value)

import monitor  # noqa: E402

FX = Path(__file__).parent / "fixtures"
KST = monitor.KST


def _kised_items() -> list[dict]:
    html = (FX / "kised" / "kised_list.html").read_text(encoding="utf-8")
    site = {
        "id": "kised",
        "name": "창업진흥원(KISED)",
        "url": "https://www.kised.or.kr/misAnnouncement/index.es?mid=a10302000000",
        "is_aggregator": False,
        "selectors": {
            "row": "ul.lstyle_list > li",
            "title": "b.ls_tit",
            "link": "a[href*='k-startup.go.kr']",
        },
    }
    return monitor._generic_page_items(BeautifulSoup(html, "html.parser"), site, site["url"])


def _iitp_items() -> list[dict]:
    html = (FX / "iitp" / "ezone_main.html").read_text(encoding="utf-8")
    site = {
        "id": "iitp",
        "name": "정보통신기획평가원(IITP) 사업공고",
        "url": "https://ezone.iitp.kr/main/main",
        "is_aggregator": False,
        "selectors": {
            "row": "#main_01 li:has(a[onclick*='PMS_TSK_PBNC_ID'])",
            "title": "a[onclick*='PMS_TSK_PBNC_ID']",
            "link": "a[onclick*='PMS_TSK_PBNC_ID']",
            "link_template": "/common/anno/02/form.tab?PMS_TSK_PBNC_ID={0}",
            "link_arg_re": "PMS_TSK_PBNC_ID=([A-Za-z0-9]+)",
        },
    }
    return monitor._generic_page_items(BeautifulSoup(html, "html.parser"), site, site["url"])


def test_kised_distinct_pbancsn_survive_dedup():
    items = _kised_items()
    assert len(items) == 2
    cids = {monitor.generate_canonical_notice_id(it) for it in items}
    assert len(cids) == 2
    kept = monitor.dedup_items(items)
    assert len(kept) == 2
    sns = {it["link"].rsplit("pbancSn=", 1)[-1] for it in kept}
    assert sns == {"900001", "900002"}


def test_iitp_distinct_pms_id_survive_dedup():
    items = _iitp_items()
    assert len(items) == 2
    cids = {monitor.generate_canonical_notice_id(it) for it in items}
    assert len(cids) == 2
    kept = monitor.dedup_items(items)
    assert len(kept) == 2


def test_kstartup_same_board_path_different_sn_not_collapsed():
    items = [
        {
            "id": "kstartup_1001",
            "title": "2026년 공공 창업도약패키지 지원사업 공고",
            "link": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd=PBC010&schM=view&pbancSn=1001",
            "author": "중기부",
            "deadline": "2026-09-01",
            "source": "K-Startup",
            "posted_date": "2026-08-20",
            "is_aggregator": False,
        },
        {
            "id": "kstartup_1002",
            "title": "2026년 공공 딥테크 팁스 신규지원 공고",
            "link": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd=PBC010&schM=view&pbancSn=1002",
            "author": "중기부",
            "deadline": "2026-09-15",
            "source": "K-Startup",
            "posted_date": "2026-08-21",
            "is_aggregator": False,
        },
    ]
    assert monitor.generate_canonical_notice_id(items[0]) != monitor.generate_canonical_notice_id(items[1])
    assert len(monitor.dedup_items(items)) == 2


def test_kised_kstartup_same_pbancsn_cross_dedup():
    """동일 pbancSn 은 한 건으로 묶이되, 다른 sn 은 유지."""
    kised = _kised_items()
    twins = []
    for it in kised:
        sn = it["link"].rsplit("pbancSn=", 1)[-1]
        twins.append({
            **it,
            "id": f"kstartup_{sn}",
            "source": "K-Startup",
            "posted_date": "2026-08-20",
            "deadline": "2026-09-30",
            "is_aggregator": False,
        })
    kept = monitor.dedup_items(kised + twins)
    assert len(kept) == 2


def test_kised_deadline_not_used_as_posted_date():
    items = _kised_items()
    for it in items:
        assert not (it.get("posted_date") or "").strip(), it
        assert (it.get("deadline") or "").startswith("2026-")


def test_iitp_period_start_not_used_as_posted_date():
    items = _iitp_items()
    for it in items:
        assert not (it.get("posted_date") or "").strip(), it
        assert "2026-" in (it.get("deadline") or "")


def test_kised_date_unknown_survives_days_back_window():
    items = _kised_items()
    now = datetime(2026, 8, 24, 12, 0, tzinfo=KST)
    matched, unknown, excluded = monitor.partition_posted_dates(items, days_back=3, now_dt=now)
    assert matched == []
    assert excluded == []
    assert len(unknown) == 2
    included, remaining = monitor.split_unknown_by_policy(unknown, "recall", now=now)
    assert len(included) == 2
    assert remaining == []


def test_path_only_url_still_canonicalizes():
    a = {"link": "https://www.example.go.kr/notice/123", "title": "A"}
    b = {"link": "http://example.go.kr/notice/123", "title": "B"}
    assert monitor.generate_canonical_notice_id(a) == monitor.generate_canonical_notice_id(b)
