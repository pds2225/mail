# -*- coding: utf-8 -*-
"""재진단 결과를 sites.json 의 enabled 에 반영(신규 imp_* 한정).

실제 공고 row 가 추출된(status=ok) 신규 사이트만 enabled=true, 나머지는 false.
기존 사이트(비 imp_)는 건드리지 않는다.

사용:
  python scripts/apply_enabled_from_diag.py [diag_json]            # 드라이런
  python scripts/apply_enabled_from_diag.py [diag_json] --write     # 반영
diag_json 생략 시 reports/site_parse_diag_*.json 중 최신 사용.
"""
from __future__ import annotations
import sys, json, glob, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def latest_diag() -> Path:
    files = sorted(glob.glob(str(ROOT / "var" / "reports" / "site_parse_diag_*.json")),
                   key=os.path.getmtime)
    return Path(files[-1])


def main() -> int:
    write = "--write" in sys.argv
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    diag_path = Path(pos[0]) if pos else latest_diag()
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    ok_ids = {r["id"] for r in diag if r["status"] == "ok"}
    print(f"진단 파일: {diag_path.name} | OK(추출됨) {len(ok_ids)}건")

    sites = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))
    on = off = 0
    for s in sites:
        if not s.get("id", "").startswith("imp_"):
            continue
        if s["id"] in ok_ids:
            if write:
                s["enabled"] = True
            on += 1
        else:
            if write:
                s["enabled"] = False
            off += 1

    print(f"신규 imp_* → enabled=true {on}건 / enabled=false {off}건")
    if write:
        (ROOT / "config" / "sites.json").write_text(
            json.dumps(sites, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        import collections
        en = collections.Counter(x["enabled"] for x in sites)
        print(f"[WRITE] sites.json 갱신 | 전체 enabled 분포: {dict(en)}")
    else:
        print("[DRY-RUN] --write 미지정. 변경 없음.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
