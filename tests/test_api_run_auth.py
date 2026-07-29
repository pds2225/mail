"""HTTP /api/run send gates — auth fail-closed + persist_seen required."""
from __future__ import annotations

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent


def _load_index_module(monkeypatch, **env):
    monkeypatch.delenv("MONITOR_SECRET", raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    path = ROOT / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("api_index_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Fresh module each test so env changes apply to handler closures/logic.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeHandler:
    """Drive api.index.handler.do_POST without a real socket."""

    def __init__(self, index_mod, body: dict, headers: dict | None = None):
        self.path = "/api/run"
        raw = json.dumps(body).encode()
        self.headers = {"Content-Length": str(len(raw)), **(headers or {})}
        self.rfile = BytesIO(raw)
        self._responses: list[tuple[int, dict]] = []
        self._authorized = index_mod.handler._authorized.__get__(self, _FakeHandler)
        self._json = self._capture_json
        self.do_POST = index_mod.handler.do_POST.__get__(self, _FakeHandler)

    def _capture_json(self, code: int, data: dict) -> None:
        self._responses.append((code, data))


def _install_fake_monitor(monkeypatch, calls: list[dict]):
    def _fake_execute(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "mail_sent": bool(kwargs.get("allow_send"))}

    monkeypatch.setitem(
        sys.modules,
        "monitor",
        SimpleNamespace(execute_monitor=_fake_execute),
    )


def test_api_run_rejects_send_without_monitor_secret(monkeypatch):
    index_mod = _load_index_module(monkeypatch)
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(
        index_mod,
        {"dry_run": False, "confirm_send": "SEND", "persist_seen": True},
    )
    h.do_POST()
    assert h._responses[0][0] == 401
    assert "MONITOR_SECRET" in h._responses[0][1]["error"]
    assert calls == []


def test_api_run_rejects_send_without_persist_seen(monkeypatch):
    index_mod = _load_index_module(monkeypatch, MONITOR_SECRET="s3cret")
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(
        index_mod,
        {"dry_run": False, "confirm_send": "SEND", "persist_seen": False},
        headers={"Authorization": "Bearer s3cret"},
    )
    h.do_POST()
    assert h._responses[0][0] == 400
    assert "persist_seen" in h._responses[0][1]["error"]
    assert calls == []


def test_api_run_rejects_send_with_wrong_bearer(monkeypatch):
    index_mod = _load_index_module(monkeypatch, MONITOR_SECRET="s3cret")
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(
        index_mod,
        {"dry_run": False, "confirm_send": "SEND", "persist_seen": True},
        headers={"Authorization": "Bearer wrong"},
    )
    h.do_POST()
    assert h._responses[0][0] == 401
    assert calls == []


def test_api_run_allows_authorized_send_with_persist_seen(monkeypatch):
    index_mod = _load_index_module(monkeypatch, MONITOR_SECRET="s3cret")
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(
        index_mod,
        {
            "dry_run": False,
            "confirm_send": "SEND",
            "persist_seen": True,
            "include_raw_all": True,
        },
        headers={"Authorization": "Bearer s3cret"},
    )
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls == [
        {
            "allow_send": True,
            "include_raw_all": True,
            "persist_seen": True,
        }
    ]


def test_api_run_dry_run_ok_without_secret(monkeypatch):
    index_mod = _load_index_module(monkeypatch)
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(index_mod, {"dry_run": True})
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls[0]["allow_send"] is False
