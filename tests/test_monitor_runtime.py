from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATH = ROOT / "scripts" / "monitor_runtime.py"
SPEC = importlib.util.spec_from_file_location("monitor_runtime_under_test", RUNTIME_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_quality_p0_emits_actions_error_and_urgent_ntfy(monkeypatch, capsys):
    sent: dict[str, object] = {}

    def fake_urlopen(notification, timeout):
        sent["url"] = notification.full_url
        sent["priority"] = notification.headers["Priority"]
        sent["body"] = notification.data.decode("utf-8")
        sent["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("NTFY_TOPIC", "mail quality")
    monkeypatch.setattr(runtime.request, "urlopen", fake_urlopen)

    runtime._notify_quality_p0_nonfatal({
        "status": "P0",
        "issues": [
            {
                "severity": "P0",
                "fingerprint": "kstartup:body",
            },
            {
                "severity": "P1",
                "fingerprint": "kita:target",
            },
        ],
    })

    stderr = capsys.readouterr().err
    assert "::error title=Core-source field quality P0::" in stderr
    assert "kstartup:body" in stderr
    assert sent == {
        "url": "https://ntfy.sh/mail%20quality",
        "priority": "urgent",
        "body": "핵심소스 필드 품질 P0: kstartup:body",
        "timeout": 10,
    }


def test_non_p0_quality_does_not_notify(monkeypatch, capsys):
    monkeypatch.setattr(
        runtime.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected ntfy")),
    )

    runtime._notify_quality_p0_nonfatal({"status": "P1", "issues": []})

    assert capsys.readouterr().err == ""


def test_protected_monitor_gets_priority_hosts_before_main_body(
    tmp_path,
    monkeypatch,
):
    protected = tmp_path / "monitor.py"
    protected.write_text(
        "\n".join([
            'DETAIL_ENRICH_HOSTS = ("bizinfo.go.kr",)',
            'assert "kita.net" in DETAIL_ENRICH_HOSTS',
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "MONITOR", protected)
    monkeypatch.setenv("MONITOR_SKIP_FIELD_QUALITY", "1")

    assert runtime.main() == 0
