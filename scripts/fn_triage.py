r"""fn_triage — fn_weaklabel_own 후보(자기지역인데 점수미달 거절) 원인 분해·분류 (S3b 입력).

accuracy_matrix 가 낸 fn_candidates.json 의 fn_weaklabel_own 후보 각각에 대해
company_match.compute_match_score 를 재실행해 점수 구성(가점·감점·mismatch)을 분해하고,
아래 결정론 기준으로 3분류해 s3_fn.json 을 만든다(읽기전용 — 판정 로직 무수정).

분류 기준(보수적 — 애매하면 needs_review, 버리지 않음):
  real_miss_suspect : 업종/관심 키워드 히트 ≥1 이고 기업별 임계 근접(score ≥ 36)
                      — "우리 업종 공고인데 아깝게 미달" = 점수체계가 놓쳤을 의심
  not_relevant      : 키워드 히트 0 — 지역만 맞고 업종 무관(정당 제외)
  needs_review      : 키워드는 맞는데 크게 미달(score < 36) — 사람확인

실행 (repo 루트): python scripts\fn_triage.py [--run fnhunt-before]
산출: .omc/accuracy/runs/{run}/s3_fn.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))

from mail_core.matching import company_match  # noqa: E402
from accuracy_matrix import _load_items, _notice_key  # noqa: E402
from run_company_match import _enrich_for_company  # noqa: E402

NEAR_SCORE = 36  # 근접 미달 컷 — 기업별 임계와 함께 s3_fn.json criteria 에 명시 기록


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    _fix_console()
    ap = argparse.ArgumentParser(description="fn_weaklabel_own 후보 원인 분해·3분류 (읽기전용)")
    ap.add_argument("--run", default="fnhunt-before")
    args = ap.parse_args()

    run_dir = BASE_DIR / ".omc" / "accuracy" / "runs" / args.run
    fn_path = run_dir / "fn_candidates.json"
    if not fn_path.exists():
        print(f"[triage] 없음: {fn_path}")
        return 1
    cands = json.loads(fn_path.read_text(encoding="utf-8"))["candidates"].get("fn_weaklabel_own", [])
    if not cands:
        print("[triage] fn_weaklabel_own 후보 0건 — 종료")
        return 0

    items = _load_items(BASE_DIR / "data" / "raw", None, None)
    by_key = {_notice_key(it): it for it in items}
    companies = {c["id"]: c for c in company_match.load_companies()}

    rows: list[dict] = []
    clusters: dict[str, list[str]] = defaultdict(list)
    verdict_count: Counter = Counter()

    for cand in cands:
        it = by_key.get(cand["id"])
        comp = companies.get(cand["cid"])
        if it is None or comp is None:
            verdict_count["needs_review"] += 1
            rows.append({**cand, "verdict": "needs_review", "cluster": "raw_or_company_missing"})
            continue
        enriched = _enrich_for_company([it], comp)
        res = company_match.compute_match_score(enriched[0] if enriched else it, comp)
        kw_hits = sum(1 for r in res.get("reasons", []) if r.startswith(("산업적합", "관심사")))
        score = int(res.get("score", cand.get("score", 0)))
        if kw_hits >= 1 and score >= NEAR_SCORE:
            verdict = "real_miss_suspect"
        elif kw_hits == 0:
            verdict = "not_relevant"
        else:
            verdict = "needs_review"
        # 원인 클러스터: 부족 원인의 서명(키워드무관/근접미달+주요 mismatch)
        if verdict == "not_relevant":
            cluster = "no_industry_keyword"
        else:
            mm = (res.get("mismatches") or ["(mismatch 없음)"])[0]
            cluster = f"near_threshold|{mm[:24]}" if verdict == "real_miss_suspect" else f"kw_but_far|{mm[:24]}"
        verdict_count[verdict] += 1
        clusters[cluster].append(cand["id"])
        rows.append({
            "id": cand["id"], "cid": cand["cid"], "city": cand["city"], "rf": cand["rf"],
            "matrix_score": cand.get("score"), "triage_score": score, "kw_hits": kw_hits,
            "reasons": res.get("reasons", [])[:4], "mismatches": res.get("mismatches", [])[:3],
            "title": cand.get("title", "")[:90], "verdict": verdict, "cluster": cluster,
        })

    thresholds = {cid: c.get("match_threshold") for cid, c in companies.items()}
    out = {
        "run": args.run,
        "criteria": {"company_thresholds": thresholds, "near_score_cut": NEAR_SCORE,
                     "rule": "kw>=1 & score>=cut → real_miss_suspect / kw==0 → not_relevant / else needs_review"},
        "stats": dict(verdict_count),
        "total": len(cands),
        "classified_total": sum(verdict_count.values()),
        "clusters": {k: {"n": len(v), "ids": v[:20]} for k, v in
                     sorted(clusters.items(), key=lambda x: -len(x[1]))},
        "items": rows,
    }
    (run_dir / "s3_fn.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[triage] {len(cands)}건 → {dict(verdict_count)}  (합계 {sum(verdict_count.values())})")
    for k, v in sorted(clusters.items(), key=lambda x: -len(x[1]))[:8]:
        print(f"  {k}: {len(v)}")
    print(f"[triage] 저장: {run_dir / 's3_fn.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
