"""Vercel Python Serverless Function — 헬스체크

GET /api/health
  → {"status": "ok", "service": "monitor-api"} 반환
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless handler."""

    def do_GET(self):  # noqa: N802
        required = ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
        missing = [k for k in required if not os.environ.get(k)]
        data = {
            "status": "ok" if not missing else "degraded",
            "service": "monitor-api",
            "env_missing": missing,
        }
        self._json(200, data)

    def do_POST(self):  # noqa: N802
        self._json(405, {"error": "GET /api/health 으로 요청하세요."})

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
