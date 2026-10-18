import os
from datetime import date, datetime, timedelta, timezone

for key in ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    os.environ.setdefault(key, "test-value")

import monitor as m

KST = timezone(timedelta(hours=9))


def test_deadline_without_time_is_recorded_and_assumed_to_end_at_2359():
    item = {"title": "2026년 10월 20일까지 모집", "deadline": "2026-10-20"}
    details = m._deadline_details(item)
    assert details["deadline_time"] == ""
    assert details["deadline_time_assumed"] is True
    assert "deadline_time_assumed" not in item
    evaluated = m.evaluate_notice(item, today=date(2026, 10, 20))
    assert evaluated["deadline_time_assumed"] is True
    assert m.classify_deadline_status(item, now=datetime(2026, 10, 20, 23, 58, tzinfo=KST)) == "open"
    assert m.classify_deadline_status(item, now=datetime(2026, 10, 20, 23, 59, 1, tzinfo=KST)) == "closed"


def test_nearest_future_round_is_selected_and_all_rounds_are_preserved():
    item = {
        "title": "차수별 모집",
        "deadline": "1차 접수: 2026-10-10 ~ 2026-10-20\n2차 접수: 2026-11-10 ~ 2026-11-20",
    }
    selected = m._digest_deadline_end(item, date(2026, 10, 19))
    assert selected == date(2026, 10, 20)
    assert item["rounds"] == [
        {"round": 1, "deadline": "2026-10-20"},
        {"round": 2, "deadline": "2026-11-20"},
    ]
    assert item["selected_deadline_round"] == 1
    assert m._digest_deadline_end(item, date(2026, 10, 21)) == date(2026, 11, 20)
    assert item["selected_deadline_round"] == 2
    assert m._digest_deadline_end(
        item, date(2026, 10, 20), now=datetime(2026, 10, 20, 23, 59, 1, tzinfo=KST)
    ) == date(2026, 11, 20)
    assert m.classify_deadline_status(
        item, now=datetime(2026, 10, 20, 23, 59, 1, tzinfo=KST)
    ) == "open"


def test_run_clock_is_frozen_for_the_entire_wrapped_run(monkeypatch):
    original = m.datetime
    calls = []

    class AdvancingDateTime(original):
        @classmethod
        def now(cls, tz=None):
            calls.append(1)
            return original(2026, 10, 19, 23, 59, len(calls), tzinfo=tz)

    monkeypatch.setattr(m, "datetime", AdvancingDateTime)

    @m._freeze_run_clock
    def read_twice():
        return m._now_kst(), m._now_kst()

    first, second = read_twice()
    assert first == second
    assert len(calls) == 1
