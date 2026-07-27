"""filter_trace → Google Sheets 누적 적립.

환경변수 (우선) / config/settings.json (폴백):
  FILTER_TRACE_SHEET_ID  또는 GOOGLE_SHEET_ID  또는 settings.filter_trace_sheet_id
  GOOGLE_SERVICE_ACCOUNT_JSON_PATH  또는 GOOGLE_SERVICE_ACCOUNT_JSON
  FILTER_TRACE_SHEET_TAB  (기본: filter_trace / settings.filter_trace_sheet_tab)

시트 미설정·인증 실패 시 False 반환 (로컬 JSONL 폴백은 호출측).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mail_core.operations.filter_trace import SHEET_HEADERS, flatten_for_sheet

_ROOT = Path(__file__).resolve().parents[2]
_SETTINGS_PATH = _ROOT / "config" / "settings.json"

# 운영 기본 시트 (env/settings 미설정 시 폴백). 공유·권한은 서비스 계정 기준.
_DEFAULT_SHEET_ID = "1e95jsQ0UfILu6GvUrR3G1E0HNBv3aXOGCsc32YCbh1E"
_DEFAULT_TAB = "filter_trace"


@lru_cache(maxsize=1)
def _settings_sheet_cfg() -> dict[str, str]:
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        "sheet_id": str(raw.get("filter_trace_sheet_id") or raw.get("google_sheet_id") or "").strip(),
        "tab": str(raw.get("filter_trace_sheet_tab") or "").strip(),
    }


def _sheet_id() -> str:
    return (
        os.environ.get("FILTER_TRACE_SHEET_ID", "").strip()
        or os.environ.get("GOOGLE_SHEET_ID", "").strip()
        or _settings_sheet_cfg().get("sheet_id", "")
        or _DEFAULT_SHEET_ID
    )


def _tab_name() -> str:
    return (
        os.environ.get("FILTER_TRACE_SHEET_TAB", "").strip()
        or _settings_sheet_cfg().get("tab", "")
        or _DEFAULT_TAB
    )


def _service_account_info() -> dict[str, Any] | None:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        # 파일 경로로 준 경우
        if raw.endswith(".json") and Path(raw).exists():
            return json.loads(Path(raw).read_text(encoding="utf-8"))
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "").strip()
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    # 레포 관례 secrets/
    for cand in (
        Path("secrets/google_service_account.json"),
        Path("/workspace/secrets/google_service_account.json"),
        _ROOT / "secrets" / "google_service_account.json",
    ):
        if cand.exists():
            return json.loads(cand.read_text(encoding="utf-8"))
    return None


def sheet_configured() -> bool:
    return bool(_sheet_id() and _service_account_info())


def sheet_url() -> str:
    sid = _sheet_id()
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else ""


def _open_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    info = _service_account_info()
    sid = _sheet_id()
    if not info or not sid:
        raise RuntimeError("Google Sheet credentials or SHEET_ID missing")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sid)
    tab = _tab_name()
    try:
        ws = sh.worksheet(tab)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab, rows=1000, cols=len(SHEET_HEADERS))
        ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
        return ws

    # 헤더 없으면 1행에 기록
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
    elif [c.strip() for c in existing[: len(SHEET_HEADERS)]] != SHEET_HEADERS:
        # 헤더 불일치 시 새 탭에 쓰지 않고 첫 빈 행 앞에 맞추지 않음 — 호출측 로그
        if existing[0] != SHEET_HEADERS[0]:
            ws.insert_row(SHEET_HEADERS, index=1)
    return ws


def ensure_filter_trace_tab() -> dict[str, Any]:
    """탭·헤더만 보장. 결과: {ok, sheet_id, tab, url, error}."""
    if not sheet_configured():
        return {
            "ok": False,
            "sheet_id": _sheet_id(),
            "tab": _tab_name(),
            "url": sheet_url(),
            "error": "sheet_not_configured",
            "headers": SHEET_HEADERS,
        }
    try:
        _open_worksheet()
        return {
            "ok": True,
            "sheet_id": _sheet_id(),
            "tab": _tab_name(),
            "url": sheet_url(),
            "error": "",
            "headers": SHEET_HEADERS,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "sheet_id": _sheet_id(),
            "tab": _tab_name(),
            "url": sheet_url(),
            "error": type(exc).__name__ + ":" + str(exc)[:200],
            "headers": SHEET_HEADERS,
        }


def append_traces_to_sheet(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """trace 목록을 시트에 append. 결과: {ok, rows, error, sheet_id, tab}."""
    if not traces:
        return {"ok": True, "rows": 0, "error": "", "sheet_id": _sheet_id(), "tab": _tab_name()}
    if not sheet_configured():
        return {
            "ok": False,
            "rows": 0,
            "error": "sheet_not_configured",
            "sheet_id": _sheet_id(),
            "tab": _tab_name(),
        }
    try:
        ws = _open_worksheet()
        rows = [
            [flatten_for_sheet(tr).get(h, "") for h in SHEET_HEADERS]
            for tr in traces
        ]
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        return {
            "ok": True,
            "rows": len(rows),
            "error": "",
            "sheet_id": _sheet_id(),
            "tab": _tab_name(),
        }
    except Exception as exc:  # noqa: BLE001 — 운영 적립 실패는 본선 중단 금지
        return {
            "ok": False,
            "rows": 0,
            "error": type(exc).__name__ + ":" + str(exc)[:200],
            "sheet_id": _sheet_id(),
            "tab": _tab_name(),
        }


def accumulate_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """로컬 JSONL 항상 기록 + 설정 시 시트 적립."""
    from mail_core.operations.filter_trace import append_jsonl

    path = append_jsonl(traces)
    sheet = append_traces_to_sheet(traces)
    return {
        "jsonl_path": str(path),
        "sheet": sheet,
    }
