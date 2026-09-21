from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
import hmac
import json
import os
import time
from pathlib import Path

RUNTIME_ROOT = Path("/tmp/monitor_ws")
os.environ.setdefault("MAIL_VAR_DIR", str(RUNTIME_ROOT / "var"))

KST = timezone(timedelta(hours=9))

REQUIRED_ENV_KEYS = [
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
    "IMAP_HOST",
    "IMAP_PORT",
]


def _build_mail_previews(result: dict) -> list[dict]:
    """execute_monitor()의 preview_groups(build_previews=True일 때만 subject/text/html
    포함)를 FE 계약(`group_id, group_name, subject, recipient_masked, notice_count, html,
    text`)으로 옮긴다. 새 renderer를 만들지 않고 monitor.py가 만든 값만 그대로 옮긴다.
    """
    previews = []
    for g in (result.get("preview_groups") or []):
        if not isinstance(g, dict) or "subject" not in g:
            continue  # include_previews 미요청 — 기존 legacy preview_groups만 있음
        previews.append({
            "group_id": g.get("group_id") or g.get("name"),
            "group_name": g.get("name"),
            "subject": g.get("subject"),
            "recipient_masked": g.get("recipients_masked") or [],
            "notice_count": g.get("matched_items", 0),
            "html": g.get("html"),
            "text": g.get("text"),
            "generated_at": g.get("generated_at"),
        })
    return previews


class handler(BaseHTTPRequestHandler):
    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, *, allow_send: bool) -> tuple[bool, str]:
        """Dry-run is passwordless; real-send paths remain fail-closed."""
        if not allow_send:
            return True, ""

        secret = os.environ.get("MONITOR_SECRET", "").strip()
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {secret}" if secret else ""
        if not secret:
            return False, "MONITOR_SECRET must be configured for real sends"
        if not hmac.compare_digest(auth, expected):
            return False, "Unauthorized"
        return True, ""

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

        content_len = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(content_len).decode() if content_len else "{}"
        try:
            body = json.loads(body_raw) if body_raw else {}
        except json.JSONDecodeError:
            body = {}

        dry_run = body.get("dry_run", True)
        confirm_send = body.get("confirm_send") == "SEND"
        allow_send = (dry_run is False) and confirm_send
        persist_seen = body.get("persist_seen", False) is True
        include_raw_all = body.get("include_raw_all", False) is True
        # MAIL-029: /run 화면의 "그룹별 메일 미리보기" — dry-run에서만 명시 요청 시에만
        # 실제 발송 경로와 동일한 subject/text/html을 만든다(기존 dry-run 호출자는 그대로).
        include_previews = body.get("include_previews", False) is True

        if dry_run is False and not confirm_send:
            self._json(400, {
                "ok": False,
                "error": "Explicit send confirmation required",
                "hint": "Use dry_run=true, or set confirm_send='SEND' to send.",
            })
            return

        ok_auth, auth_error = self._authorized(allow_send=allow_send)
        if not ok_auth:
            self._json(401, {"ok": False, "error": auth_error})
            return

        # Mirror CLI: --send requires --persist-seen so outbox/idempotency cannot be bypassed.
        if allow_send and not persist_seen:
            self._json(400, {
                "ok": False,
                "error": "persist_seen=true is required for real sends",
                "hint": "Omit confirm_send for dry-run, or set persist_seen=true with confirm_send='SEND'.",
            })
            return

        # Vercel Python 은 MAIL_VAR_DIR 을 /tmp 에 둔다(이 파일 L7–8). seen_ids·
        # delivery_state·outbox 가 콜드스타트마다 증발하므로 persist_seen=true 여도
        # 멱등이 성립하지 않는다 → 인증된 실발송이 전 수신자 중복 메일을 만든다.
        # 실발송은 GitHub Actions monitor 워크플로(커밋백 있는 영구 state)만 허용.
        if allow_send:
            self._json(501, {
                "ok": False,
                "error": "Real sends are not supported on Vercel serverless",
                "hint": "Use dry_run=true for preview, or trigger the GitHub Actions monitor workflow for delivery.",
            })
            return

        # 인증·send gate 통과 뒤에만 무거운 monitor 모듈을 읽는다.
        try:
            from monitor import execute_monitor
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"Monitor import failed: {exc}"})
            return

        try:
            _t0 = time.monotonic()
            result = execute_monitor(
                allow_send=allow_send,
                include_raw_all=include_raw_all,
                persist_seen=persist_seen,
                build_previews=include_previews and not allow_send,
            )
            result["processing_time_ms"] = int((time.monotonic() - _t0) * 1000)
            result["generated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
            result["mail_previews"] = _build_mail_previews(result)
            self._json(200, {"ok": True, "result": result})
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        pass  # suppress default access log
