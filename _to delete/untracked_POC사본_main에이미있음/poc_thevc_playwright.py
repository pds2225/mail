"""THE VC 지원사업 Playwright POC — 접근·필드 추출 가능 여부만 확인."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

KST = timezone(timedelta(hours=9))
URL = "https://thevc.kr/grants"
OUT = Path(__file__).resolve().parent.parent / "logs" / "poc_thevc_result.json"
MAX_SAMPLE = 10


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _extract_items(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    # 1) 테이블 행
    for tr in soup.select("table tbody tr, table tr"):
        a = tr.select_one("a[href]")
        if not a:
            continue
        title = _norm(a.get_text())
        href = a.get("href", "")
        if not title or len(title) < 4:
            continue
        link = urljoin(base_url, href)
        if link in seen:
            continue
        seen.add(link)
        row_text = _norm(tr.get_text(" "))
        dates = re.findall(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}", row_text)
        items.append({
            "title": title,
            "external_url": link,
            "deadline": dates[-1] if dates else None,
            "agency": None,
            "external_category": None,
            "official_url": None,
            "source_row": row_text[:200],
        })

    # 2) 카드/리스트 링크 (테이블 없을 때)
    if not items:
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            title = _norm(a.get_text())
            if not title or len(title) < 8:
                continue
            if not any(k in href for k in ("grant", "grants", "support", "biz", "notice", "article")):
                if "/grants" not in href and "thevc.kr" not in href:
                    continue
            link = urljoin(base_url, href)
            if link in seen or link.rstrip("/") == base_url.rstrip("/"):
                continue
            seen.add(link)
            items.append({
                "title": title,
                "external_url": link,
                "deadline": None,
                "agency": None,
                "external_category": None,
                "official_url": None,
            })

    return items


def _extract_official_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    official_hosts = (
        "bizinfo.go.kr", "k-startup.go.kr", "smes.go.kr", "go.kr",
        "or.kr", "re.kr", "tp.or.kr", "creativekorea.or.kr",
    )
    found: list[str] = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href.startswith("http"):
            continue
        if any(h in href for h in official_hosts):
            if href not in found:
                found.append(href)
    return found


def run_poc(*, headless: bool = True, detail_samples: int = 3) -> dict:
    result: dict = {
        "url": URL,
        "started_at": datetime.now(KST).isoformat(),
        "access_ok": False,
        "http_status": None,
        "page_title": None,
        "list_items_found": 0,
        "samples": [],
        "detail_probe": [],
        "errors": [],
        "verdict": "FAIL",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        try:
            resp = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            result["http_status"] = resp.status if resp else None
            page.wait_for_timeout(4000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            result["page_title"] = page.title()
            html = page.content()
            result["access_ok"] = result["http_status"] == 200 and "403" not in (result["page_title"] or "")
            if not result["access_ok"]:
                result["errors"].append(f"access blocked or bad status: {result['http_status']} title={result['page_title']}")
            else:
                items = _extract_items(html, URL)
                result["list_items_found"] = len(items)
                result["samples"] = items[:MAX_SAMPLE]

                for item in items[:detail_samples]:
                    detail_url = item["external_url"]
                    probe = {"external_url": detail_url, "official_urls": [], "error": None}
                    try:
                        dresp = page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2500)
                        dhtml = page.content()
                        probe["http_status"] = dresp.status if dresp else None
                        probe["official_urls"] = _extract_official_urls(dhtml)[:5]
                        if probe["official_urls"]:
                            item["official_url"] = probe["official_urls"][0]
                    except Exception as exc:
                        probe["error"] = str(exc)
                    result["detail_probe"].append(probe)
        except Exception as exc:
            result["errors"].append(str(exc))
        finally:
            browser.close()

    official_count = sum(1 for s in result["samples"] if s.get("official_url"))
    if result["access_ok"] and result["list_items_found"] >= 5:
        result["verdict"] = "PASS" if official_count >= 1 or result["detail_probe"] else "PARTIAL"
    elif result["access_ok"] and result["list_items_found"] > 0:
        result["verdict"] = "PARTIAL"
    else:
        result["verdict"] = "FAIL"

    result["finished_at"] = datetime.now(KST).isoformat()
    return result


def main() -> int:
    headless = "--headed" not in sys.argv
    result = run_poc(headless=headless)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "verdict": result["verdict"],
        "http_status": result["http_status"],
        "list_items_found": result["list_items_found"],
        "samples": len(result["samples"]),
        "official_in_samples": sum(1 for s in result["samples"] if s.get("official_url")),
        "out": str(OUT),
        "errors": result["errors"],
    }, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
