from datetime import date, datetime, timezone

import pytest

import monitor as mon
from mail_core.operations.deadline_context import extract_deadline_details
from mail_core.operations.period_gate import classify_period_status
from mail_core.delivery.digest_table import _is_deadline_part, render_plain, parse_plain_table, render_html_blocks
from mail_core.delivery.digest_lint import lint_digest


@pytest.mark.parametrize("raw,expected", [("18시", "18:00"), ("18:00", "18:00"),
    ("24시", "23:59"), ("24:00", "23:59"), ("오후 6시", "18:00"),
    ("오전 12시", "00:00"), ("23:59", "23:59"), ("없음", ""), ("25시", "")])
def test_parse_explicit_time(raw, expected):
    assert extract_deadline_details(raw)["deadline_time"] == expected


def notice(raw="접수기간: 2026.10.01 ~ 2026.10.20.(화) 18:00까지", **changes):
    return {"id": "fixture", "title": "전국 제조기업 성장지원 사업 신청접수", "description": raw,
            "deadline": "2026-10-20", "posted_date": "2026-10-01", **changes}


@pytest.mark.parametrize("hour,expected", [(17, "open"), (19, "closed")])
def test_kst_same_day_cutoff_in_evaluation(hour, expected):
    it = notice()
    now = datetime(2026, 10, 20, hour, tzinfo=mon.KST)
    assert mon.classify_deadline_status(it, now=now) == expected
    ev = mon.evaluate_notice(it, today=now.date(), now=now)
    assert ev["deadline_time"] == "18:00"
    assert ev["deadline_status"] == expected
    assert ("CLOSED_DEADLINE" in ev["exclude_reason_codes"]) == (expected == "closed")
    assert classify_period_status(it, now=now) == ("closed" if expected == "closed" else "closing_soon")
    assert mon._digest_is_closed(it, now.date(), now=now) == (expected == "closed")


def test_utc_is_compared_in_kst():
    assert mon.classify_deadline_status(notice(), now=datetime(2026, 10, 20, 10, tzinfo=timezone.utc)) == "closed"


def test_structured_date_does_not_erase_body_time():
    it = notice(application_period={"start": "2026-10-01", "end": "2026-10-20"})
    assert mon.classify_deadline_status(it, now=datetime(2026, 10, 20, 19, tzinfo=mon.KST)) == "closed"


def test_short_date_deadline_and_time():
    it = notice(raw="", deadline="10.20.(화) 18:00까지")
    assert mon.classify_deadline_status(it, now=datetime(2026, 10, 20, 19, tzinfo=mon.KST)) == "closed"
    assert mon._mail_deadline_cell(it, date(2026, 10, 20)) == "10/20 (D-0 18시)"


def test_time_is_only_shown_on_d_zero():
    assert mon._mail_deadline_cell(notice(), date(2026, 10, 20)) == "10/20 (D-0 18시)"
    assert mon._mail_deadline_cell(notice(), date(2026, 10, 19)) == "10/20 (D-1)"
    assert mon._mail_deadline_cell(notice(raw=""), date(2026, 10, 20)) == "10/20 (D-0)"


@pytest.mark.parametrize("basis", ["도착분에 한함", "도착 기준", "우편 소인"])
def test_arrival_basis_reaches_card_and_lint(basis):
    it = notice(raw=f"접수기간: 2026.10.01 ~ 2026.10.20 18시까지 {basis}")
    label = mon._mail_deadline_cell(it, date(2026, 10, 20))
    assert label == "10/20 (D-0 18시) (도착기준)"
    assert mon.evaluate_notice(it, today=date(2026, 10, 19))["deadline_basis"] == "도착"
    assert _is_deadline_part(label)
    rows = [{"공고": "제조기업 성장지원", "마감": label, "지원": "지원금/바우처", "지원내용": "제작비 지원"}]
    body = render_plain(rows)
    assert parse_plain_table(body)[1][0]["마감"] == label
    assert label in render_html_blocks(rows)
    assert lint_digest("[공고] 1건", body)["ok"]


def test_opening_time_is_not_deadline():
    it = notice(raw="접수기간: 2026.10.01 09:00 ~ 2026.10.20")
    # 시작 시각을 마감 시각으로 사용하면 안 된다.
    assert mon._deadline_details(it)["deadline_time"] == ""


def test_runtime_card_excludes_after_cutoff(monkeypatch):
    from mail_core.operations import deadline_context as dc
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, 19, tzinfo=mon.KST)
    monkeypatch.setattr(dc, "datetime", Clock)
    assert "성장지원" not in mon.fallback_body([notice()], today=date(2026, 10, 20))


def test_duration_does_not_replace_explicit_deadline():
    assert extract_deadline_details("오후 6시까지 (온라인 시스템은 24시간 이용 가능)")["deadline_time"] == "18:00"


@pytest.mark.parametrize("field,value", [("deadline_time", "16:00"), ("deadline_basis", "도착")])
def test_time_and_basis_changes_are_material(field, value):
    old = notice(deadline_time="18:00")
    snapshot = mon._notice_version_snapshot(old)
    versions = {old["id"]: {"version": 1, "delivered_snapshot": snapshot,
                             "delivered_hash": mon._notice_snapshot_hash(snapshot)}}
    changed = {**old, field: value}
    deliverable, _ = mon.classify_notice_versions([changed], {old["id"]}, versions)
    assert deliverable and field in deliverable[0]["_changed_fields"]
    assert deliverable[0]["_change_type"] == "UPDATED"
