"""2026-10: 240분 timeout 근본 수정 — 실행 시간 예산·발송 실패 exit·smoke-test."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@example.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402
from mail_core.operations import run_budget  # noqa: E402
from mail_core.operations.coverage_alert import (  # noqa: E402
    COVERAGE_BUDGET_SKIPPED,
    detect_coverage_anomalies,
)


@pytest.fixture(autouse=True)
def _fresh_budget(monkeypatch):
    for k in run_budget.DEFAULTS:
        monkeypatch.delenv(k, raising=False)
    run_budget.reset()
    yield
    run_budget.reset()


def _expire(name, monkeypatch):
    monkeypatch.setenv(name, "1")
    run_budget.reset(time.monotonic() - 120)  # 2분 경과 > 1분 예산


def test_budget_defaults_and_disable(monkeypatch):
    assert run_budget.budget_min("MONITOR_COLLECT_BUDGET_MIN") == 150
    assert run_budget.budget_min("MONITOR_COVERAGE_BUDGET_MIN") == 75
    assert not run_budget.exceeded("MONITOR_COLLECT_BUDGET_MIN")
    monkeypatch.setenv("MONITOR_COLLECT_BUDGET_MIN", "0")
    assert run_budget.remaining_s("MONITOR_COLLECT_BUDGET_MIN") is None
    monkeypatch.setenv("MONITOR_COLLECT_BUDGET_MIN", "abc")
    assert run_budget.budget_min("MONITOR_COLLECT_BUDGET_MIN") == 150


def test_fetch_all_stops_at_budget_and_keeps_gathered(monkeypatch):
    monkeypatch.setenv("MONITOR_COLLECT_BUDGET_MIN", str(1.0 / 60))  # 1초

    def fast(site):
        return [{"id": "a", "title": "x"}]

    def slow(site):
        time.sleep(3)
        return [{"id": "b", "title": "y"}]

    monkeypatch.setitem(m.FETCHERS, "t_fast", fast)
    monkeypatch.setitem(m.FETCHERS, "t_slow", slow)
    outcomes: dict = {}
    t0 = time.monotonic()
    items = m.fetch_all([{"id": "f", "type": "t_fast"}, {"id": "s", "type": "t_slow"}],
                        outcomes=outcomes)
    assert time.monotonic() - t0 < 2.5
    assert [it["id"] for it in items] == ["a"]
    assert outcomes["s"]["error"] == "collect_budget_exceeded"
    assert outcomes["f"]["success"] is True


def test_enrich_items_skipped_when_budget_exceeded(monkeypatch):
    _expire("MONITOR_COLLECT_BUDGET_MIN", monkeypatch)
    called = []
    monkeypatch.setattr(m, "enrich_item_from_detail", lambda it: called.append(it) or it)
    host = next(iter(m.DETAIL_ENRICH_HOSTS))
    items = [{"id": "1", "title": "t", "link": f"https://{host}/x?1", "posted_date": "2026-10-12"}]
    assert m.enrich_items(items) == items
    assert called == []


def test_coverage_audit_skips_after_budget(monkeypatch):
    _expire("MONITOR_COVERAGE_BUDGET_MIN", monkeypatch)
    hits = []
    monkeypatch.setitem(m.FETCHERS, "t_cov", lambda s: hits.append(s) or [])
    rows = m.fetch_site_coverage([{"id": "c1", "name": "c1", "type": "t_cov"}])
    assert hits == []
    assert rows[0]["fetch_error"] == COVERAGE_BUDGET_SKIPPED
    # 예산 생략 사이트는 '수집실패' 이상치로 알리지 않는다
    assert detect_coverage_anomalies(rows, {"c1": [10, 10, 10, 10]}) == []


def test_smoke_test_requires_only_to(monkeypatch):
    sent = []
    monkeypatch.setattr(m.smtplib, "SMTP_SSL", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SMTP")))
    assert m.run_smoke_test("") == 2
    assert sent == []


def test_smoke_test_sends_only_to_target(monkeypatch):
    calls = []
    monkeypatch.setattr(m, "_build_mime_message", lambda s, b, to: type("M", (), {"as_string": lambda self: "x"})())

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def sendmail(self, frm, to, msg): calls.append(to)

    monkeypatch.setattr(m.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(m, "_ALLOW_SMTP_SEND", False)
    monkeypatch.setattr(m, "_ONLY_TO", "")
    monkeypatch.setattr(m, "_DRAFT_MODE", False, raising=False)
    assert m.run_smoke_test("tester@example.com") == 0
    assert calls == ["tester@example.com"]


def test_smoke_test_send_failure_returns_3(monkeypatch):
    def boom(*a, **k):
        raise OSError("smtp down")
    monkeypatch.setattr(m, "send_email", boom)
    monkeypatch.setattr(m, "_ALLOW_SMTP_SEND", False)
    monkeypatch.setattr(m, "_ONLY_TO", "")
    assert m.run_smoke_test("tester@example.com") == 3


def test_main_block_exits_nonzero_on_send_failure():
    src = (ROOT / "monitor.py").read_text(encoding="utf-8")
    assert "if args.send and _SEND_FAIL > 0:" in src and "raise SystemExit(3)" in src


def test_runtime_skips_quality_audit_when_late(monkeypatch, capsys):
    sys.path.insert(0, str(ROOT / "scripts"))
    import monitor_runtime as rt
    monkeypatch.setenv("MONITOR_POST_SEND_SKIP_MIN", "1")
    run_budget.reset(time.monotonic() - 120)
    called = []
    import types
    monkeypatch.setitem(sys.modules, "source_field_quality_gate",
                        types.SimpleNamespace(run_live_and_record=lambda: called.append(1) or {}))
    rt._record_quality_nonfatal()
    assert called == []
    assert "field quality audit skipped" in capsys.readouterr().err


def test_workflow_smoke_requires_only_to_and_budgets_set():
    y = (ROOT / ".github/workflows/monitor.yml").read_text(encoding="utf-8")
    assert "smoke_test:" in y and "--smoke-test $ONLY_TO_FLAG" in y
    assert "smoke_test 는 only_to 와 함께만" in y
    assert "MONITOR_COLLECT_BUDGET_MIN: '150'" in y
    assert "timeout-minutes: 240" in y
