#!/usr/bin/env python3
"""3대 핵심 소스(기업마당·K-Startup·NIPA) 완성 체크리스트.

수집기 + 상세보강 + 오프라인 회귀테스트를 한 번에 판정한다.
실무 기준: 기능 '있다'가 아니라 이 스크립트 PASS가 3곳 완성도 게이트.

Usage (PowerShell, D:\\mail):
  python scripts/core_sources_checklist.py
  python scripts/core_sources_checklist.py --json
  python scripts/core_sources_checklist.py --live   # 네트워크 수집 실측 (API 키 필요)

관련 문서: docs/CORE_SOURCES_CHECKLIST.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("BIZINFO_API_KEY", "checklist")
os.environ.setdefault("ANTHROPIC_API_KEY", "checklist")
os.environ.setdefault("GMAIL_ADDRESS", "check@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "checklist")
os.environ.setdefault("PYTHONUTF8", "1")


@dataclass
class Check:
    id: str
    label: str
    run: Callable[[], tuple[bool, str]]


@dataclass
class SourceSpec:
    id: str
    name: str
    site_id: str
    fetcher_type: str
    enrich_host: str
    pytest_files: list[str]
    live_min_items: int
    checks: list[Check] = field(default_factory=list)


def _load_sites() -> list[dict]:
    return json.loads((ROOT / "sites.json").read_text(encoding="utf-8"))


def _site_by_id(site_id: str) -> dict | None:
    return next((s for s in _load_sites() if s.get("id") == site_id), None)


def _run_pytest(rel: str) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    cmd = [sys.executable, "-m", "pytest", str(ROOT / "tests" / rel), "-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    tail = (proc.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else ""
    failed = bool(re.search(r"failed|xfailed", summary))
    ok = proc.returncode == 0 and not failed
    return ok, summary or f"exit={proc.returncode}"


def _check_site_enabled(spec: SourceSpec) -> tuple[bool, str]:
    site = _site_by_id(spec.site_id)
    if not site:
        return False, f"sites.json에 {spec.site_id} 없음"
    if not site.get("enabled", True):
        return False, "enabled=false"
    if site.get("type") != spec.fetcher_type:
        return False, f"type={site.get('type')} (기대 {spec.fetcher_type})"
    return True, "enabled·type OK"


def _check_enrich_host(spec: SourceSpec) -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT))
    import monitor as m  # noqa: PLC0415

    if spec.enrich_host not in m.DETAIL_ENRICH_HOSTS:
        return False, f"DETAIL_ENRICH_HOSTS에 {spec.enrich_host} 없음"
    return True, f"상세보강 대상 ({m.MAX_DETAIL_ENRICH}건/실행)"


def _check_bizinfo_api_config() -> tuple[bool, str]:
    site = _site_by_id("bizinfo")
    if not site:
        return False, "bizinfo 없음"
    unit = int(site.get("api_page_unit", 0) or 0)
    pages = int(site.get("api_max_pages", 0) or 0)
    if unit < 100 or pages < 1:
        return False, f"api_page_unit={unit} api_max_pages={pages}"
    return True, f"API {unit}×{pages}페이지"


def _check_kstartup_pages() -> tuple[bool, str]:
    site = _site_by_id("kstartup")
    if not site:
        return False, "kstartup 없음"
    mp = int(site.get("max_pages", 1) or 1)
    if mp < 2:
        return False, f"max_pages={mp} (민간·공공 다페이지 권장 ≥2)"
    return True, f"max_pages={mp}"


def _check_nipa_pagination_config() -> tuple[bool, str]:
    site = _site_by_id("nipa")
    if not site:
        return False, "nipa 없음"
    mp = site.get("max_pages", 300)
    return True, f"max_pages={mp} (전량순회 상한)"


def _live_fetch(spec: SourceSpec) -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT))
    import monitor as m  # noqa: PLC0415

    site = _site_by_id(spec.site_id)
    if not site:
        return False, "site 없음"
    fn = m.FETCHERS.get(site.get("type", ""))
    if not fn:
        return False, f"fetcher 없음: {site.get('type')}"
    try:
        items = fn(site)
    except Exception as exc:
        return False, f"수집 예외: {exc}"
    n = len(items)
    if n < spec.live_min_items:
        return False, f"수집 {n}건 < 최소 {spec.live_min_items}"
    extra = ""
    if spec.id == "bizinfo":
        with_link = sum(1 for it in items if "bizinfo.go.kr" in (it.get("link") or ""))
        if with_link < min(10, n // 2):
            return False, f"bizinfo.go.kr 링크 {with_link}/{n} 부족"
        extra = f", 상세링크 {with_link}건"
    if spec.id == "nipa":
        with_date = sum(1 for it in items if (it.get("posted_date") or "").strip())
        rate = with_date / n if n else 0
        if rate < 0.05:
            return False, f"게시일 파싱률 {rate:.0%} ({with_date}/{n}) — NIPA 날짜 병목"
        extra = f", 게시일 {with_date}/{n} ({rate:.0%})"
    if spec.id == "kstartup":
        hosts = sum(1 for it in items if "k-startup.go.kr" in (it.get("link") or ""))
        if hosts < min(5, n):
            return False, f"k-startup 링크 {hosts}/{n} 부족"
        extra = f", k-startup 링크 {hosts}건"
    return True, f"수집 {n}건{extra}"


def _build_specs() -> list[SourceSpec]:
    specs = [
        SourceSpec(
            id="bizinfo",
            name="기업마당",
            site_id="bizinfo",
            fetcher_type="bizinfo_api",
            enrich_host="bizinfo.go.kr",
            pytest_files=["test_fetch_bizinfo_replay.py", "test_bizinfo_detail_enrich.py"],
            live_min_items=100,
        ),
        SourceSpec(
            id="kstartup",
            name="K-Startup",
            site_id="kstartup",
            fetcher_type="kstartup_html",
            enrich_host="k-startup.go.kr",
            pytest_files=["test_fetch_kstartup_replay.py"],
            live_min_items=10,
        ),
        SourceSpec(
            id="nipa",
            name="NIPA",
            site_id="nipa",
            fetcher_type="nipa_html",
            enrich_host="nipa.kr",
            pytest_files=["test_fetch_nipa_replay.py"],
            live_min_items=50,
        ),
    ]
    extra: dict[str, list[Check]] = {
        "bizinfo": [Check("bizinfo_api_config", "API pageUnit×pages", _check_bizinfo_api_config)],
        "kstartup": [Check("kstartup_pages", "다페이지 설정", _check_kstartup_pages)],
        "nipa": [Check("nipa_pages", "페이지순회 상한", _check_nipa_pagination_config)],
    }
    for spec in specs:
        spec.checks = [
            Check(f"{spec.id}_site", "sites.json 활성·타입", lambda s=spec: _check_site_enabled(s)),
            Check(f"{spec.id}_enrich", "상세보강 대상", lambda s=spec: _check_enrich_host(s)),
            *extra.get(spec.id, []),
        ]
        for pf in spec.pytest_files:
            spec.checks.append(
                Check(f"{spec.id}_pytest_{pf}", f"회귀 {pf}", lambda p=pf: _run_pytest(p)),
            )
    return specs


def run_checklist(*, live: bool = False) -> dict[str, Any]:
    specs = _build_specs()
    sources_out: list[dict[str, Any]] = []
    total = 0
    passed = 0

    for spec in specs:
        rows: list[dict[str, Any]] = []
        for chk in spec.checks:
            ok, detail = chk.run()
            rows.append({"id": chk.id, "label": chk.label, "ok": ok, "detail": detail})
            total += 1
            if ok:
                passed += 1
        if live:
            ok, detail = _live_fetch(spec)
            rows.append({
                "id": f"{spec.id}_live_fetch",
                "label": "실수집(live)",
                "ok": ok,
                "detail": detail,
            })
            total += 1
            if ok:
                passed += 1
        sources_out.append({
            "id": spec.id,
            "name": spec.name,
            "checks": rows,
            "ok": all(r["ok"] for r in rows),
        })

    return {
        "gate": "core_sources_checklist",
        "passed": passed,
        "total": total,
        "ok": passed == total,
        "live": live,
        "sources": sources_out,
        "note": (
            "3대 소스 완성도 게이트. recall_zero_gate(판정 로직)와 별도. "
            "--live 는 BIZINFO_API_KEY·네트워크 필요."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="기업마당·K-Startup·NIPA 완성 체크리스트")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--live", action="store_true", help="실제 HTTP 수집 검사 추가")
    args = parser.parse_args()

    out = run_checklist(live=args.live)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if out["ok"] else "FAIL"
        print(f"core_sources_checklist: {status} ({out['passed']}/{out['total']})")
        for src in out["sources"]:
            mark = "OK" if src["ok"] else "NG"
            print(f"\n[{mark}] {src['name']} ({src['id']})")
            for row in src["checks"]:
                m2 = "OK" if row["ok"] else "NG"
                print(f"  [{m2}] {row['label']}: {row['detail']}")
        if not out["ok"]:
            print("\n→ NG 항목부터 수정. 전체: docs/CORE_SOURCES_CHECKLIST.md")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
