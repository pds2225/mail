from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request

app = Flask(__name__)

REQUIRED_ENV_KEYS = [
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
    "IMAP_HOST",
    "IMAP_PORT",
]


def _missing_env_keys() -> list[str]:
    return [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key, "").strip()]


@app.get("/api/health")
def health() -> Any:
    missing = _missing_env_keys()
    return jsonify(
        {
            "ok": True,
            "service": "auto-mail",
            "mode": "serverless",
            "missing_env_keys": missing,
        }
    )


@app.post("/api/run")
def run_monitor() -> Any:
    body = request.get_json(silent=True) or {}
    dry_run = body.get("dry_run", True)
    confirm_send = body.get("confirm_send") == "SEND"
    include_raw_all = bool(body.get("include_raw_all", False))
    persist_seen = bool(body.get("persist_seen", False))

    allow_send = (not dry_run) and confirm_send
    if not dry_run and not confirm_send:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Explicit send confirmation required",
                    "hint": "Use dry_run=true, or set confirm_send='SEND' to send.",
                }
            ),
            400,
        )

    try:
        from monitor import execute_monitor

        result = execute_monitor(
            allow_send=allow_send,
            include_raw_all=include_raw_all,
            persist_seen=persist_seen,
        )
        return jsonify(
            {
                "ok": True,
                "requested_dry_run": bool(dry_run),
                "effective_send": allow_send,
                "result": result,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

