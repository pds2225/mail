# -*- coding: utf-8 -*-
"""[임시] K-Startup 실데이터 코퍼스 수집 → 회귀/정확도 검증 기준선.
현재 코드(main)로 grp_goyang 에 대해 각 공고가 어떻게 판정되는지 + 상세 구조화 필드를 덤프.
메일 발송/seen 저장 없음(읽기 전용)."""
import json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for k, v in [("BIZINFO_API_KEY","x"),("ANTHROPIC_API_KEY","x"),
             ("GMAIL_ADDRESS","x@x.com"),("GMAIL_APP_PASSWORD","x"),
             ("MONITOR_NO_PERSIST_SEEN","1")]:
    os.environ.setdefault(k, v)
import monitor as m
from bs4 import BeautifulSoup

def detail_fields(link):
    """상세 p.tit/p.txt 라벨쌍 전부 추출(중복 라벨은 첫 값)."""
    soup = m._soup(link)
    out = {}
    if not soup:
        return out
    for tit in soup.select("p.tit"):
        label = m.norm(tit.get_text())
        nxt = tit.find_next("p", class_="txt")
        if nxt and label and label not in out:
            out[label] = m.norm(nxt.get_text())
    return out

site = [s for s in json.load(open("sites.json",encoding="utf-8")) if s.get("id")=="kstartup"][0]
items = m.fetch_kstartup(site)
print(f"[수집] K-Startup {len(items)}건", file=sys.stderr)
grp = [g for g in json.load(open("groups.json",encoding="utf-8")) if g["id"]=="grp_goyang"][0]

rows = []
for it in items[:50]:
    f = detail_fields(it.get("link",""))
    enr = m.enrich_item_from_detail(dict(it))
    ev = m.evaluate_notice(enr, grp)
    rows.append({
        "title": it.get("title"),
        "지역": f.get("지역"),
        "지원분야": f.get("지원분야"),
        "대상연령": f.get("대상연령"),
        "대상": f.get("대상"),
        "창업업력": f.get("창업업력"),
        "주관기관명": f.get("주관기관명"),
        "제외대상": (f.get("제외대상") or "")[:60],
        "cur_is_relevant": ev.get("is_relevant"),
        "cur_region": ev.get("region_status"),
        "cur_biz": ev.get("business_years_status"),
        "cur_amt": ev.get("support_amount_status"),
        "cur_reasons": ev.get("exclude_reason_codes"),
    })
json.dump(rows, open("_corpus_kstartup.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
# 요약 출력
inc = [r for r in rows if r["cur_is_relevant"]]
print(f"\n현재 grp_goyang is_relevant=True: {len(inc)}/{len(rows)}건")
for r in inc:
    print(f"  ✓ {r['title'][:42]:42s} | 지역:{r['지역']} 대상연령:{r['대상연령']} 업력:{r['창업업력']} 주관:{r['주관기관명']}")
print(f"\n[저장] _corpus_kstartup.json ({len(rows)}건)")
