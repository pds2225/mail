"""MAIL-029: /run 미리보기가 실제 발송 renderer를 그대로 재사용하는지 회귀 검증.

Preview(execute_monitor(build_previews=True))가 만드는 subject/text/html이 실제 발송
경로(allow_send=True)가 만드는 subject/body와 항상 동일해야 하고, Preview 도중에는
SMTP·초안·ntfy·seen 저장이 절대 호출되지 않아야 한다.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "sender@example.test")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402
from mail_core.delivery.digest_table import COLUMNS, HEADER_LINE  # noqa: E402


def _items():
    return [
        {
            "id": "a1", "title": "AI 솔루션 도입 지원 신청접수",
            "description": "서울 전국 중소기업 대상 사업화 자금 지원",
            "link": "https://bizinfo.go.kr/a1",
            "source_url": "https://bizinfo.go.kr/canonical-a1",
            "author": "중소벤처기업부", "deadline": "2099-12-31",
            "source": "기업마당", "posted_date": "2026-08-10",
            "is_aggregator": False, "target_field": "전국 중소기업",
            "support_field": "사업화 자금 지원", "_types": ["지원금/바우처"],
        },
        {
            "id": "b1", "title": "AI 수출 바우처 참여기업 모집",
            "description": "수출 바우처를 지원합니다",
            "link": "https://bizinfo.go.kr/b1",
            "author": "KOTRA", "deadline": "2099-11-30",
            "source": "기업마당", "posted_date": "2026-08-11",
            "is_aggregator": False, "target_field": "수출 중소기업",
            "support_field": "수출 바우처", "_types": ["바우처"],
        },
    ]


def _install_fixture(monkeypatch, *, items, groups):
    monkeypatch.setattr(m, "fetch_all", lambda s, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: groups)
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": False, "raw_all_enabled": False, "raw_all_recipients": [],
        "company_match_enabled": False,
    })
    monkeypatch.setattr(m, "load_watchlist", lambda: {"keywords": [], "urls": [], "recipients": []})
    monkeypatch.setattr(m, "load_seen_ids", lambda: set())
    monkeypatch.setattr(m, "alert_ntfy", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Preview 중 ntfy 호출 금지")))


def _forbid_delivery(monkeypatch):
    """Preview 경로에서 SMTP/초안/outbox가 절대 호출되지 않는지 못을 박는다."""
    monkeypatch.setattr(m, "send_email", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Preview 중 SMTP 발송 금지")))
    monkeypatch.setattr(m, "send_to_list", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Preview 중 send_to_list 호출 금지")))
    monkeypatch.setattr(m, "save_draft_to_gmail", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Preview 중 Gmail 초안 생성 금지")))
    monkeypatch.setattr(m, "deliver_with_outbox", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Preview 중 outbox 발송 금지")))


def _one_group(recipients=("owner@example.test",)):
    return [{
        "id": "g1", "name": "예비창업 AI", "active": True, "or_keywords": ["AI"],
        "required_conditions": {"regions": ["전국"]},
        "applicant_region_city": "서울특별시", "applicant_region_label": "서울",
        "recipients": list(recipients),
    }]


def test_preview_matches_real_send_subject_and_body(monkeypatch):
    """MUST: Preview subject/text/html == 실제 발송 subject/body (같은 renderer)."""
    groups = _one_group()
    _install_fixture(monkeypatch, items=_items(), groups=groups)
    _forbid_delivery(monkeypatch)

    preview = m.execute_monitor(
        allow_send=False, include_raw_all=False, persist_seen=False, build_previews=True,
    )
    assert preview["ok"] is True
    assert preview["mode"] == "preview"
    assert preview["mail_sent"] is False
    assert preview["seen_ids_persisted"] is False
    pg = preview["preview_groups"]
    assert len(pg) == 1
    entry = pg[0]
    assert entry["subject"].startswith("[예비창업 AI]")
    assert HEADER_LINE in entry["text"]
    assert "<table" in entry["html"]
    assert all(col in entry["html"] for col in COLUMNS)

    # 실제 발송 경로 — send_to_list 로 넘어가는 subject/body를 그대로 캡처해 비교한다.
    _install_fixture(monkeypatch, items=_items(), groups=_one_group())
    sent = []
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: sent.append((s, b, r)))
    monkeypatch.setattr(m, "send_email", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("SMTP 금지")))

    real = m.execute_monitor(allow_send=True, include_raw_all=False, persist_seen=False)
    assert real["mail_sent"] is True
    assert sent, "발송 경로가 호출되어야 한다"
    real_subject, real_body, _real_recips = sent[0]

    assert entry["subject"] == real_subject
    assert entry["text"] == real_body
    assert entry["html"] == m._render_email_html(real_body)


def test_preview_masks_recipients_never_exposes_raw_email(monkeypatch):
    raw = "owner-secret@example.test"
    groups = _one_group(recipients=(raw,))
    _install_fixture(monkeypatch, items=_items(), groups=groups)
    _forbid_delivery(monkeypatch)

    result = m.execute_monitor(
        allow_send=False, persist_seen=False, build_previews=True,
    )
    entry = result["preview_groups"][0]
    assert raw not in entry["recipients_masked"][0]
    assert raw not in str(result)
    assert entry["recipients_masked"][0] == m._mask_email(raw)


def test_preview_group_with_zero_matched_notices_still_returns_entry(monkeypatch):
    """공고가 수집돼도, 이 그룹 조건에 하나도 안 맞으면 matched_items=0 인 Preview를 보여준다."""
    groups = _one_group()
    groups[0]["or_keywords"] = ["이키워드는아무공고에도없음"]
    _install_fixture(monkeypatch, items=_items(), groups=groups)
    _forbid_delivery(monkeypatch)

    result = m.execute_monitor(allow_send=False, persist_seen=False, build_previews=True)
    pg = result["preview_groups"]
    assert len(pg) == 1
    assert pg[0]["matched_items"] == 0
    assert "오늘 기준 조건 매칭 공고는 없습니다." in pg[0]["text"]
    assert pg[0]["subject"].startswith("[예비창업 AI] 0건")


def test_preview_multiple_groups_each_get_own_content(monkeypatch):
    groups = _one_group(recipients=("a@example.test",)) + [{
        "id": "g2", "name": "수출", "active": True, "or_keywords": ["수출"],
        "required_conditions": {"regions": ["전국"]},
        "applicant_region_city": "서울특별시", "applicant_region_label": "서울",
        "recipients": ["b@example.test"],
    }]
    _install_fixture(monkeypatch, items=_items(), groups=groups)
    _forbid_delivery(monkeypatch)

    result = m.execute_monitor(allow_send=False, persist_seen=False, build_previews=True)
    pg = result["preview_groups"]
    assert len(pg) == 2
    names = {g["name"] for g in pg}
    assert names == {"예비창업 AI", "수출"}
    # 그룹마다 독립된 group_id·수신자 마스킹을 갖는다(그룹 전환 시 서로 섞이지 않음).
    by_name = {g["name"]: g for g in pg}
    assert by_name["예비창업 AI"]["group_id"] == "g1"
    assert by_name["수출"]["group_id"] == "g2"
    assert by_name["예비창업 AI"]["recipients_masked"] != by_name["수출"]["recipients_masked"]


def test_preview_without_build_previews_flag_keeps_legacy_shape(monkeypatch):
    """기존 dry-run 호출자(build_previews 미지정)는 비용·응답 형태가 그대로여야 한다."""
    groups = _one_group()
    _install_fixture(monkeypatch, items=_items(), groups=groups)
    _forbid_delivery(monkeypatch)

    result = m.execute_monitor(allow_send=False, persist_seen=False)
    entry = result["preview_groups"][0]
    assert "subject" not in entry
    assert "html" not in entry
    assert "text" not in entry
