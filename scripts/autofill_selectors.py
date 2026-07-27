# -*- coding: utf-8 -*-
"""parse_empty 사이트의 게시판 row 셀렉터를 휴리스틱으로 자동 추론·주입.

monitor._soup 로 HTML 을 받아(운영 수집과 동일 경로) 후보 셀렉터별로
'링크+텍스트+날짜' 유효 row 수를 세고, 가장 그럴듯한 셀렉터를 selectors.row 로
sites.json 에 주입한다. 채택 기준에 못 미치면 건너뜀(LLM 보강 잔여로 남김).

사용:
  python scripts/autofill_selectors.py            # 드라이런(추천만 출력)
  python scripts/autofill_selectors.py --write      # sites.json 에 selectors.row 주입
.env 의 BIZINFO_API_KEY 를 import 전에 주입(값 미출력).
"""
from __future__ import annotations
import os, sys, json, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATE = re.compile(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{2}[.\-]\d{2}[.\-]\d{2}")

CANDIDATES = [
    "table tbody tr", "table tr", "tbody tr",
    ".board_list tbody tr", ".bbs_list tbody tr", ".tbl_list tbody tr",
    ".tbl_board tbody tr", "table.board tbody tr", ".table tbody tr",
    "ul.board_list li", ".board_list li", "ul.list li", ".list_wrap li",
    ".bbs_list li", ".notice_list li", ".gallery_list li", ".board li",
    "div.board_list li", ".card_list li", ".list li", "li.item",
    ".board-list li", ".lst li", ".cont_list li",
]


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
    write = "--write" in sys.argv
    load_env()
    import logging
    import monitor
    logging.getLogger().setLevel(logging.CRITICAL)
    norm = monitor.norm

    cls = json.loads((ROOT / "var" / "reports" / "diag_classified.json").read_text(encoding="utf-8"))
    targets = cls["parse_empty"]
    print(f"보강 대상(parse_empty): {len(targets)}개", flush=True)

    def count(soup, sel) -> tuple[int, int]:
        rows = soup.select(sel)
        if not rows or len(rows) > 400:
            return 0, 0
        cnt = dated = 0
        for r in rows:
            a = r.select_one("a")
            if not a:
                continue
            href = a.get("href", "") or ""
            if not href or href.startswith("javascript:"):
                continue
            title = norm(r.get_text())
            if not title or len(title) < 6:
                continue
            cnt += 1
            if DATE.search(r.get_text()):
                dated += 1
        return cnt, dated

    def infer(site: dict) -> dict:
        soup = monitor._soup(site["url"])
        if soup is None:
            return {"id": site["id"], "sel": None, "cnt": 0, "dated": 0, "reason": "no_soup"}
        best = (None, 0, 0)  # sel, dated, cnt
        for sel in CANDIDATES:
            cnt, dated = count(soup, sel)
            if cnt < 3:
                continue
            if (dated, cnt) > (best[1], best[2]):
                best = (sel, dated, cnt)
        return {"id": site["id"], "name": site.get("name", ""), "url": site["url"],
                "sel": best[0], "dated": best[1], "cnt": best[2],
                "reason": "ok" if best[0] else "no_candidate"}

    recs: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(infer, s): s for s in targets}
        done = 0
        for f in as_completed(futs):
            recs.append(f.result())
            done += 1
            if done % 25 == 0:
                print(f"  진행 {done}/{len(targets)}", flush=True)

    found = [r for r in recs if r["sel"]]
    none = [r for r in recs if not r["sel"]]
    print(f"\n셀렉터 추론 성공: {len(found)} / 미추론: {len(none)}")
    from collections import Counter
    print("[채택 셀렉터 분포]")
    for sel, c in Counter(r["sel"] for r in found).most_common(10):
        print(f"  {c:3d}  {sel}")

    if write:
        sites = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))
        by_id = {s["id"]: s for s in sites}
        n = 0
        skipped_default = 0
        for r in found:
            if r["sel"] == "table tbody tr":  # fetch_html_generic 기본값 → 주입 무의미
                skipped_default += 1
                continue
            s = by_id.get(r["id"])
            if not s:
                continue
            sel = s.setdefault("selectors", {})
            sel["row"] = r["sel"]
            n += 1
        print(f"  (기본값 셀렉터라 스킵: {skipped_default}건)")
        (ROOT / "config" / "sites.json").write_text(
            json.dumps(sites, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n[WRITE] selectors.row 주입 {n}건 → sites.json 갱신")
    else:
        print("\n[DRY-RUN] --write 미지정. 변경 없음.")
        for r in found[:12]:
            print(f"  {r['id']} | dated={r['dated']} cnt={r['cnt']} | {r['sel']} | {r['name'][:20]}")

    (ROOT / "var" / "reports" / "autofill_recs.json").write_text(
        json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
