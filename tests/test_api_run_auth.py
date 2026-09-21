"""HTTP /api/run gates — passwordless dry-run + real-send fail-closed."""
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


def test_api_run_checks_auth_before_importing_monitor(monkeypatch):
    index_mod = _load_index_module(monkeypatch, MONITOR_SECRET="s3cret")
    monkeypatch.setitem(sys.modules, "monitor", None)
    h = _FakeHandler(
        index_mod,
        {"dry_run": False, "confirm_send": "SEND", "persist_seen": True},
        headers={"Authorization": "Bearer wrong"},
    )
    h.do_POST()
    assert h._responses[0][0] == 401


def test_api_run_requires_literal_true_for_persist_seen(monkeypatch):
    index_mod = _load_index_module(monkeypatch, MONITOR_SECRET="s3cret")
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(
        index_mod,
        {"dry_run": False, "confirm_send": "SEND", "persist_seen": "true"},
        headers={"Authorization": "Bearer s3cret"},
    )
    h.do_POST()
    assert h._responses[0][0] == 400
    assert calls == []


def test_api_run_non_boolean_falsy_dry_run_never_sends(monkeypatch):
    index_mod = _load_index_module(monkeypatch)
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(
        index_mod,
        {"dry_run": 0, "confirm_send": "SEND", "persist_seen": True},
    )
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls[0]["allow_send"] is False


def test_api_run_rejects_serverless_real_send_even_when_authorized(monkeypatch):
    """Vercel /tmp state 로는 persist_seen 멱등이 성립하지 않는다 → 실발송 501."""
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
    assert h._responses[0][0] == 501
    assert "not supported" in h._responses[0][1]["error"]
    assert "GitHub Actions" in h._responses[0][1]["hint"]
    assert calls == []


def test_api_run_dry_run_ok_without_secret(monkeypatch):
    index_mod = _load_index_module(monkeypatch)
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(index_mod, {"dry_run": True})
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls[0]["allow_send"] is False


def test_api_run_dry_run_ignores_configured_monitor_secret(monkeypatch):
    """웹 미리보기는 MONITOR_SECRET 설정 여부와 무관하게 암호 없이 실행한다."""
    index_mod = _load_index_module(monkeypatch, MONITOR_SECRET="s3cret")
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(index_mod, {"dry_run": True})
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls[0]["allow_send"] is False


def test_api_run_include_previews_forwards_build_previews_true(monkeypatch):
    """MAIL-029: dry-run + include_previews=true → monitor에 build_previews=True 전달."""
    index_mod = _load_index_module(monkeypatch)
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(index_mod, {"dry_run": True, "include_previews": True})
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls[0]["build_previews"] is True


def test_api_run_default_does_not_request_build_previews(monkeypatch):
    """MAIL-029: include_previews 미지정 시 기존 dry-run 호출자는 그대로(비용 불변)."""
    index_mod = _load_index_module(monkeypatch)
    calls: list[dict] = []
    _install_fake_monitor(monkeypatch, calls)
    h = _FakeHandler(index_mod, {"dry_run": True})
    h.do_POST()
    assert h._responses[0][0] == 200
    assert calls[0]["build_previews"] is False


def test_api_run_response_includes_mail_previews_and_timing(monkeypatch):
    """MAIL-029: preview_groups(subject/text/html 포함)를 mail_previews 계약으로 옮긴다."""
    index_mod = _load_index_module(monkeypatch)

    def _fake_execute(**kwargs):
        return {
            "ok": True,
            "mail_sent": False,
            "preview_groups": [
                {
                    "group_id": "g1",
                    "name": "예비창업 AI",
                    "matched_items": 3,
                    "subject": "[예비창업 AI] 3건 (09/21 오전)",
                    "text": "본문",
                    "html": "<html><body>본문</body></html>",
                    "recipients_masked": ["ow***@example.test"],
                    "generated_at": "2026-09-21 09:00:00 KST",
                },
                {"group_id": "g2", "name": "미요청그룹", "matched_items": 0},
            ],
        }

    monkeypatch.setitem(
        sys.modules, "monitor", SimpleNamespace(execute_monitor=_fake_execute),
    )
    h = _FakeHandler(index_mod, {"dry_run": True, "include_previews": True})
    h.do_POST()
    assert h._responses[0][0] == 200
    result = h._responses[0][1]["result"]
    assert isinstance(result["processing_time_ms"], int)
    assert result["generated_at"].endswith("KST")
    previews = result["mail_previews"]
    assert len(previews) == 1  # subject 없는 두 번째 그룹(미요청)은 제외
    p = previews[0]
    assert p["group_id"] == "g1"
    assert p["group_name"] == "예비창업 AI"
    assert p["notice_count"] == 3
    assert p["recipient_masked"] == ["ow***@example.test"]
    assert "<html" in p["html"]
    assert p["text"] == "본문"
