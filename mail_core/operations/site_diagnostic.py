"""govsupport-mailing-v2 site diagnostic module.

Design Ref: §5 site_diagnostic.py — 82개 사이트 dry-run + Markdown 리포트.
Plan SC2: var/reports/site_diagnostic_YYYYMMDD.md 존재.

monitor.py를 import하지 않고 독립적으로 사이트 URL에 HTTP HEAD/GET을 시도하여
응답 가능 여부와 응답 시간만 측정한다. 컨텐츠 파싱 검증은 후속 단계.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import ssl

from mail_core.paths import REPORTS_DIR

DEFAULT_TIMEOUT = 15
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _legacy_ssl_ctx() -> ssl.SSLContext:
    """한국 정부 사이트의 legacy SSL/cipher 호환용 context."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT  # OpenSSL 3.x
    except AttributeError:
        pass
    return ctx


def _try_fetch(url: str, timeout: int, *, verify: Any, headers: dict[str, str]):
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        verify=verify,
        http2=False,
    ) as client:
        return client.get(url)


def diagnose_site(site: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    site_id = site.get("id") or site.get("name") or site.get("url", "")
    url = site.get("url") or site.get("api_url") or ""
    result: dict[str, Any] = {
        "site_id": site_id,
        "url": url,
        "status": "fail",
        "http_code": None,
        "items_count": 0,
        "error_type": None,
        "elapsed_ms": 0,
        "fallback_used": None,
    }
    if not url:
        result["error_type"] = "no_url"
        return result

    # 3단계 폴백: (1) verify=True (2) verify=False (3) legacy SSL ctx
    strategies = [
        ("strict", True),
        ("no_verify", False),
        ("legacy_ssl", _legacy_ssl_ctx()),
    ]

    start = time.monotonic()
    last_err: Exception | None = None
    resp = None
    for name, verify in strategies:
        try:
            resp = _try_fetch(url, timeout, verify=verify, headers=BROWSER_HEADERS)
            result["fallback_used"] = name
            break
        except Exception as e:
            last_err = e
            continue

    result["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    if resp is None:
        if isinstance(last_err, httpx.TimeoutException):
            result["error_type"] = "timeout"
        elif isinstance(last_err, httpx.ConnectError):
            msg = str(last_err)
            if "SSL" in msg or "ssl" in msg:
                result["error_type"] = "ssl_handshake"
            elif "10054" in msg:
                result["error_type"] = "connection_reset"
            else:
                result["error_type"] = "connect_error"
        elif isinstance(last_err, httpx.HTTPError):
            result["error_type"] = f"http_error:{type(last_err).__name__}"
        else:
            result["error_type"] = f"err:{type(last_err).__name__}"
        return result

    result["http_code"] = resp.status_code
    result["status"] = "ok" if 200 <= resp.status_code < 400 else "fail"
    if result["status"] == "ok":
        content_len = len(resp.content or b"")
        result["items_count"] = 1 if content_len > 0 else 0
        if content_len == 0:
            result["status"] = "empty"
    else:
        result["error_type"] = f"http_{resp.status_code}"
    return result


def diagnose_all(sites: list[dict], reports_dir: Path | str | None = None) -> str:
    reports_dir = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"site_diagnostic_{ts}.md"

    results = [diagnose_site(s) for s in sites]
    ok = [r for r in results if r["status"] == "ok"]
    fail = [r for r in results if r["status"] == "fail"]
    empty = [r for r in results if r["status"] == "empty"]

    lines: list[str] = []
    lines.append(f"# Site Diagnostic Report — {ts}")
    lines.append("")
    lines.append(f"- Total sites: **{len(results)}**")
    lines.append(f"- OK: **{len(ok)}** | FAIL: **{len(fail)}** | EMPTY: **{len(empty)}**")
    lines.append(f"- Success rate: **{len(ok) / len(results) * 100:.1f}%**" if results else "- No sites")
    lines.append("")
    lines.append("## Failed Sites (priority for fix)")
    lines.append("")
    lines.append("| site_id | http | error | elapsed_ms | url |")
    lines.append("|---|---|---|---|---|")
    for r in fail:
        lines.append(
            f"| {r['site_id']} | {r['http_code'] or '-'} | {r['error_type'] or '-'} | "
            f"{r['elapsed_ms']} | {r['url'][:80]} |"
        )
    lines.append("")
    lines.append("## Empty / OK Sites (summary)")
    lines.append("")
    lines.append("| site_id | status | http | elapsed_ms |")
    lines.append("|---|---|---|---|")
    for r in empty + ok:
        lines.append(
            f"| {r['site_id']} | {r['status']} | {r['http_code'] or '-'} | {r['elapsed_ms']} |"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")

    json_path = reports_dir / f"site_diagnostic_{ts}.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(report_path)
