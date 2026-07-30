"""Vercel Python Serverless Function — 공고 모니터 HTTP 트리거 (safe-by-default)

POST /api/run
  Header: Authorization: Bearer <MONITOR_SECRET>
    - dry-run: MONITOR_SECRET 이 설정돼 있으면 필수
    - 실발송: MONITOR_SECRET 미설정이면 거부(fail closed), 설정 시 Bearer 필수
  Body(JSON, 모두 선택):
    {
      "dry_run": true,           # 기본 true — 미지정/true 면 미리보기만(발송 없음)
      "confirm_send": "SEND",    # 실제 발송하려면 정확히 "SEND" 이어야 함
      "include_raw_all": false,  # 원본전체 보고 메일 포함 여부
      "persist_seen": false      # 실발송 시 반드시 true (CLI --send/--persist-seen 와 동일)
    }
  → 실제 발송은 dry_run=false 이고 confirm_send=="SEND" 이고 persist_seen=true 일 때만.

GET /api/run?dry_run=1
  → dry-run(미리보기)만 허용. GET 으로는 절대 발송하지 않는다.

주의사항:
  - Vercel Hobby: 10초 / Pro: 60초 타임아웃 — 긴 실행은 GitHub Actions 권장
  - seen_ids.json 은 /tmp/monitor_ws 에 저장(Lambda warm-reuse 중만 유지)
  - 실발송·영구 persistence 는 명시적 트리거에서만(자동 스케줄·GET 은 dry-run)
"""
from __future__ import annotations

import json
import hmac
import logging
import os
import shutil
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# ── 경로 설정 ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = "/tmp/monitor_ws"
_CONFIG_FILES = (
    "sites.json",
    "groups.json",
    "settings.json",
    "companies.json",
    "watchlist.json",
)


def _setup_workspace() -> None:
    """읽기 전용 프로젝트 루트의 JSON 설정을 /tmp 작업공간으로 복사."""
    os.makedirs(WORKSPACE, exist_ok=True)
    for fname in _CONFIG_FILES:
        src = os.path.join(ROOT, "config", fname)
        dst = os.path.join(WORKSPACE, "config", fname)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)


# Lambda 초기화 시 한 번만 실행
_setup_workspace()
os.environ.setdefault("MAIL_CONFIG_DIR", os.path.join(WORKSPACE, "config"))
os.environ.setdefault("MAIL_VAR_DIR", os.path.join(WORKSPACE, "var"))
os.chdir(WORKSPACE)
sys.path.insert(0, ROOT)     # monitor 모듈 임포트 경로 추가

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _load_monitor():
    """환경변수 검증 후 monitor 모듈 임포트."""
    required = ("BIZINFO_API_KEY", "ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"필수 환경변수 누락: {', '.join(missing)}")
    import monitor  # noqa: PLC0415
    return monitor


def _result_summary(result: dict) -> dict:
    """execute_monitor 결과에서 스칼라 값(건수·플래그)만 추려 JSON 응답용으로 축약.

    sent_groups·preview_groups·date_review_queue·coverage 같은 큰 리스트는 응답에서 제외.
    """
    if not isinstance(result, dict):
        return {}
    return {k: v for k, v in result.items() if isinstance(v, (int, float, str, bool))}


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless handler (safe-by-default)."""

    def _authorized(self, *, allow_send: bool) -> tuple[bool, str]:
        """Fail closed for real sends; dry-run still honors MONITOR_SECRET when set."""
        secret = os.environ.get("MONITOR_SECRET", "").strip()
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {secret}" if secret else ""
        if allow_send:
            if not secret:
                return False, "MONITOR_SECRET must be configured for real sends"
            if not hmac.compare_digest(auth, expected):
                return False, "Unauthorized"
            return True, ""
        if secret and not hmac.compare_digest(auth, expected):
            return False, "Unauthorized"
        return True, ""

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def do_POST(self):  # noqa: N802
        # ── 발송 여부 판정 (safe-by-default) ─────────────────────────────────
        body = self._read_json_body()
        dry_run = body.get("dry_run", True)               # 기본 true
        confirm_send = str(body.get("confirm_send", ""))
        include_raw_all = body.get("include_raw_all", False) is True
        persist_seen = body.get("persist_seen", False) is True
        # 실제 발송은 dry_run 이 명시적으로 False(JSON false) 이고 confirm_send=="SEND" 일 때만.
        allow_send = (dry_run is False) and (confirm_send == "SEND")

        # ── 인증 (실발송은 MONITOR_SECRET 필수) ───────────────────────────────
        ok_auth, auth_error = self._authorized(allow_send=allow_send)
        if not ok_auth:
            self._json(401, {"error": auth_error})
            return

        # Mirror CLI: --send requires --persist-seen so outbox/idempotency cannot be bypassed.
        if allow_send and not persist_seen:
            self._json(400, {
                "error": "persist_seen=true is required for real sends",
                "hint": "Omit confirm_send for dry-run, or set persist_seen=true with confirm_send='SEND'.",
            })
            return

        # ── 실행 ─────────────────────────────────────────────────────────────
        try:
            monitor = _load_monitor()
            result = monitor.execute_monitor(
                allow_send=allow_send,
                include_raw_all=include_raw_all,
                persist_seen=persist_seen,
            )
            self._json(200, {
                "status": "ok",
                "dry_run": not allow_send,
                "mail_sent": bool(result.get("mail_sent")),
                "result": _result_summary(result),
            })
        except EnvironmentError as exc:
            log.error("환경변수 오류: %s", exc)
            self._json(503, {"error": str(exc)})
        except Exception as exc:
            log.exception("monitor 실행 실패: %s", exc)
            self._json(500, {"error": str(exc)})

    def do_GET(self):  # noqa: N802
        qs = parse_qs(urlparse(self.path).query)
        dry = (qs.get("dry_run", ["0"])[0] or "0").lower() in ("1", "true", "yes")
        if not dry:
            self._json(405, {
                "error": "GET 은 dry-run 전용입니다. /api/run?dry_run=1 로 호출하세요. "
                         "실제 발송은 POST 로 {\"dry_run\": false, \"confirm_send\": \"SEND\"}.",
            })
            return
        try:
            monitor = _load_monitor()
            result = monitor.execute_monitor(
                allow_send=False, include_raw_all=False, persist_seen=False,
            )
            self._json(200, {"status": "ok", "dry_run": True, "result": _result_summary(result)})
        except EnvironmentError as exc:
            log.error("환경변수 오류: %s", exc)
            self._json(503, {"error": str(exc)})
        except Exception as exc:
            log.exception("monitor dry-run 실패: %s", exc)
            self._json(500, {"error": str(exc)})

    def log_message(self, fmt, *args):  # silence default access log
        log.info(fmt, *args)

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
