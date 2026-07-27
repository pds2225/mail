r"""accuracy_eval — 추천 정확도 측정엔진 (읽기전용, 코드 미수정).

raw store(data/raw/날짜/notices/*/meta.json)의 전수 공고를 각 기업과 매칭하고,
공고 메타의 region_field(공고의 정답 지역)와 대조해 region_FP(타지역 오추천) 를 센다.

region_FP = 어느 기업에 '맞춤(matched)'으로 추천됐는데, 공고의 region_field 가
그 기업 지역도 전국/수도권도 아닌 명백한 타지역인 경우 = 잘못된 추천.

실행 (PowerShell, D:\mail 에서):
  python scripts\accuracy_eval.py
종료코드: region_FP==0 이면 0, 아니면 1 (CI 게이트로 사용 가능).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "scripts"))

from mail_core.matching import company_match  # noqa: E402
from run_company_match import _enrich_for_company  # noqa: E402  (인천고정 버그 수정 반영)

# region_field 가 이 값들이면 기업 지역 무관하게 적격(타지역 아님) — region_FP 대상 아님
_REGION_OK_TOKENS = ("전국", "수도권", "전국(지역무관)", "지역무관", "")


def _load_raw_items(data_root: Path) -> list[dict]:
    items: list[dict] = []
    for mp in data_root.glob("*/notices/*/meta.json"):
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d, dict) and (d.get("title") or d.get("description")):
            items.append(d)
    return items


def _is_region_fp(region_field: str, city: str) -> bool:
    """matched 공고의 region_field 가 기업 지역이 아닌 명백한 타지역인가."""
    rf = (region_field or "").strip()
    if not rf or rf in _REGION_OK_TOKENS:
        return False
    if "전국" in rf or "수도권" in rf:
        return False
    return bool(city) and (city not in rf)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    data_root = BASE_DIR / "data" / "raw"
    if not data_root.exists():
        print(f"[SKIP] raw store 없음: {data_root} (수집 후 측정 가능)")
        return 0
    items = _load_raw_items(data_root)
    companies = company_match.load_companies()
    if not items or not companies:
        print(f"[SKIP] 공고 {len(items)} / 기업 {len(companies)} — 측정 불가")
        return 0

    print(f"[측정] 공고 {len(items)}건 × 기업 {len(companies)}곳 (기업별 지역판정 enrich 반영)")
    total_fp = 0
    rf_dist = Counter()
    for c in companies:
        city = (c.get("region") or {}).get("city", "") or ""
        enriched = _enrich_for_company(items, c)
        res = company_match.match_for_company(enriched, c)
        matched = res["matched"]
        fps = []
        for it in matched:
            rf = str(it.get("region_field") or "").strip()
            rf_dist[rf or "(없음)"] += 1
            if _is_region_fp(rf, city):
                fps.append((rf, str(it.get("title", ""))[:46]))
        total_fp += len(fps)
        print(f"  {str(c.get('id')):22s}({city:4s}): 맞춤 {len(matched):3d} / region_FP {len(fps)}")
        for rf, t in fps[:5]:
            print(f"        [rf:{rf}] {t}")

    print(f"\n[KPI] region_FP(타지역 오추천) = {total_fp}  (목표 0)")
    return 0 if total_fp == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
