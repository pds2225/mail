# -*- coding: utf-8 -*-
"""범용 파서(fetch_html_generic) 기준 사이트 파싱 진단.

site_diagnostic.py 는 'URL 생존'만 보지만, 이 스크립트는 실제로 공고 row 가
몇 건 추출되는지(item_count)를 본다. 신규 imp_* 사이트의 셀렉터 보강 대상 선별용.

사용:
  python scripts/diagnose_site_parse.py            # 신규 imp_* 만
  python scripts/diagnose_site_parse.py --all       # 전체 sites.json
메일 발송 없음. .env 의 BIZINFO_API_KEY 를 import 전에 주입한다(값 미출력).
"""
from __future__ import annotations
import os, sys, json, logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env() -> None:
    envp = ROOT / ".env"
    if not envp.exists():
        return
    for line in envp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    load_env()
    import monitor  # noqa: E402  (.env 주입 후)
    logging.getLogger().setLevel(logging.ERROR)  # fetch_html_generic 의 info 로그 억제

    all_mode = "--all" in sys.argv
    sites = json.loads((ROOT / "sites.json").read_text(encoding="utf-8"))
    target = sites if all_mode else [s for s in sites if s.get("id", "").startswith("imp_")]
    print(f"진단 대상: {len(target)}개 ({'전체' if all_mode else '신규 imp_*'})", flush=True)

    def diag(s: dict) -> dict:
        try:
            items = monitor.fetch_html_generic(s)
            n = len(items)
            return {"id": s["id"], "name": s.get("name", ""), "url": s.get("url", ""),
                    "status": "ok" if n > 0 else "empty", "item_count": n, "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"id": s["id"], "name": s.get("name", ""), "url": s.get("url", ""),
                    "status": "fail", "item_count": 0,
                    "error": f"{type(e).__name__}: {str(e)[:140]}"}

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(diag, s): s for s in target}
        done = 0
        for f in as_completed(futs):
            results.append(f.result())
            done += 1
            if done % 25 == 0:
                print(f"  진행 {done}/{len(target)}", flush=True)

    ok = [r for r in results if r["status"] == "ok"]
    empty = [r for r in results if r["status"] == "empty"]
    fail = [r for r in results if r["status"] == "fail"]

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = reports / f"site_parse_diag_{ts}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 파싱 진단 요약 =====", flush=True)
    print(f"총 {len(results)} | OK(row≥1) {len(ok)} | EMPTY(접속O·row0) {len(empty)} | FAIL(접속X) {len(fail)}")
    print(f"결과 저장: {out}")
    print("\n[EMPTY 상위 15 — 셀렉터 보강 후보]")
    for r in empty[:15]:
        print(f"  {r['id']} | {r['name'][:24]} | {r['url'][:70]}")
    print("\n[FAIL 상위 15 — 접속불가/비활성 후보]")
    for r in fail[:15]:
        print(f"  {r['id']} | {r['name'][:20]} | {r['error'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
