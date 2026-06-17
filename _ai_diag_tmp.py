"""[임시] grp_ai_saas 깔때기 진단 — 어디서 AI 공고가 떨어지나. 읽기전용·발송없음. 실행 후 삭제."""
import os, sys
from pathlib import Path
from collections import Counter

envf = Path(r"D:\mail\.env")
for line in envf.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
sys.path.insert(0, r"D:\mail")
import monitor as m  # noqa: E402

sites = m.load_sites()
items = m.fetch_all(sites)
deduped = m.dedup_items(items)
group = [g for g in m.load_groups() if g["id"] == "grp_ai_saas"][0]
print("or_keywords:", group.get("or_keywords"))
print("score_threshold:", group.get("score_threshold", "(없음)"), "/ company_id:", group.get("company_id", "(없음)"), flush=True)

ork = [k.lower() for k in group.get("or_keywords", [])]
def has_kw(it):
    t = f"{it.get('title','')} {it.get('description','')} {it.get('author','')}".lower()
    return any(m._kw_in_text(t, k) for k in ork)
kw_items = [it for it in deduped if has_kw(it)]
print(f"\n전체 deduped: {len(deduped)} / AI키워드 포함: {len(kw_items)}", flush=True)

diag = m.filter_for_group_with_diagnostics(deduped, group)
inc, rev, exc = diag["included"], diag["review"], diag["excluded"]
print(f"그룹필터: included {len(inc)} / review(검토) {len(rev)} / excluded {len(exc)}")

kw_ids = {it["id"] for it in kw_items}
exc_kw = [it for it in exc if it.get("id") in kw_ids]
rev_kw = [it for it in rev if it.get("id") in kw_ids]
print(f"\nAI키워드 있는데 → 제외 {len(exc_kw)} / 검토강등 {len(rev_kw)}")
reasons = Counter()
for it in exc_kw:
    for c in it.get("exclude_reason_codes", []):
        reasons[c] += 1
print("제외 사유 top:", reasons.most_common(15), flush=True)

print("\nincluded 게시일 분포:", Counter(it.get("posted_date", "")[:10] for it in inc).most_common(12))
print("\n[샘플] AI키워드인데 제외된 공고 10개:")
for it in exc_kw[:10]:
    print(f"  - {it.get('title','')[:50]} | {it.get('exclude_reason_codes')}")
print("\n[샘플] included 공고:")
for it in inc[:8]:
    print(f"  + {it.get('title','')[:50]} | 게시 {it.get('posted_date','?')}")
