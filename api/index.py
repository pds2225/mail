from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path

RUNTIME_ROOT = Path("/tmp/monitor_ws")
os.environ.setdefault("MAIL_VAR_DIR", str(RUNTIME_ROOT / "var"))

REQUIRED_ENV_KEYS = [
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
    "IMAP_HOST",
    "IMAP_PORT",
]

class handler(BaseHTTPRequestHandler):
    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/api/health", "/api/health/"):
            missing = [k for k in REQUIRED_ENV_KEYS if not os.environ.get(k, "").strip()]
            self._json(200, {
                "ok": True,
                "service": "auto-mail",
                "mode": "serverless",
                "missing_env_keys": missing,
            })
        else:
            self._json(200, {
                "ok": True,
                "service": "auto-mail",
                "note": "Use POST /api/run to trigger monitor",
            })

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/api/run", "/api/run/"):
            self._json(404, {"ok": False, "error": "Unknown endpoint"})
            return

        # lazy import: monitor.py has module-level env checks
        try:
            from monitor import execute_monitor
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"Monitor import failed: {exc}"})
            return

        content_len = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(content_len).decode() if content_len else "{}"
        try:
            body = json.loads(body_raw) if body_raw else {}
        except json.JSONDecodeError:
            body = {}

        dry_run = body.get("dry_run", True)
        confirm_send = body.get("confirm_send") == "SEND"
        allow_send = (not dry_run) and confirm_send

        if not dry_run and not confirm_send:
            self._json(400, {
                "ok": False,
                "error": "Explicit send confirmation required",
                "hint": "Use dry_run=true, or set confirm_send='SEND' to send.",
            })
            return

        try:
            result = execute_monitor(
                allow_send=allow_send,
                include_raw_all=bool(body.get("include_raw_all", False)),
                persist_seen=bool(body.get("persist_seen", False)),
            )
            self._json(200, {"ok": True, "result": result})
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        pass  # suppress default access log

