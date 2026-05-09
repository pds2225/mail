"""Vercel Python Serverless Function — monitor.main() HTTP 트리거

POST /api/run
  Header: Authorization: Bearer <MONITOR_SECRET>
  → monitor.main() 실행 후 JSON 응답 반환

주의사항:
  - Vercel Hobby: 10초 / Pro: 60초 타임아웃 — 긴 실행은 GitHub Actions 권장
  - seen_ids.json은 /tmp/monitor_ws 에 저장 (Lambda warm-reuse 중만 유지)
  - 일일 영구 persistence는 .github/workflows/monitor.yml (GitHub Actions) 담당
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from http.server import BaseHTTPRequestHandler

# ── 경로 설정 ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = "/tmp/monitor_ws"
_CONFIG_FILES = ("sites.json", "groups.json", "settings.json")


def _setup_workspace() -> None:
    """읽기 전용 프로젝트 루트의 JSON 설정을 /tmp 작업공간으로 복사."""
    os.makedirs(WORKSPACE, exist_ok=True)
    for fname in _CONFIG_FILES:
        src = os.path.join(ROOT, fname)
        dst = os.path.join(WORKSPACE, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)


# Lambda 초기화 시 한 번만 실행
_setup_workspace()
os.chdir(WORKSPACE)          # monitor.py의 상대경로(Path("sites.json") 등)가 /tmp/monitor_ws를 가리킴
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


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless handler."""

    def do_POST(self):  # noqa: N802
        # ── 인증 ─────────────────────────────────────────────────────────────
        secret = os.environ.get("MONITOR_SECRET", "")
        if secret:
            auth_header = self.headers.get("Authorization", "")
            if auth_header != f"Bearer {secret}":
                self._json(401, {"error": "Unauthorized"})
                return

        # ── 실행 ─────────────────────────────────────────────────────────────
        try:
            monitor = _load_monitor()
            monitor.main()
            self._json(200, {"status": "ok", "message": "Monitor run completed"})
        except EnvironmentError as exc:
            log.error("환경변수 오류: %s", exc)
            self._json(503, {"error": str(exc)})
        except Exception as exc:
            log.exception("monitor.main() 실패: %s", exc)
            self._json(500, {"error": str(exc)})

    def do_GET(self):  # noqa: N802
        self._json(405, {"error": "POST /api/run 으로 요청하세요."})

    def log_message(self, fmt, *args):  # silence default access log
        log.info(fmt, *args)

    def _json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
