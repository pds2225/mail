# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/mail")

from dotenv import load_dotenv

load_dotenv("D:/mail/.env")

import httpx
import monitor
from scripts.download_kstartup_targets import (
    load_targets,
    collect_kstartup_items,
    collect_bizinfo_items,
    match_notice,
    norm_text,
    search_keywords_from_title,
)

targets = load_targets(Path("targets/kstartup_20260623.txt"))
biz = collect_bizinfo_items()
headers = {**monitor.HTTP_HEADERS, "Referer": "https://www.k-startup.go.kr/"}
with httpx.Client(timeout=60, headers=headers, follow_redirects=True, verify=False) as c:
    ks = collect_kstartup_items(client=c)

print("kstartup", len(ks), "bizinfo", len(biz))
print()

for t in targets:
    item_k, sk = match_notice(t, ks)
    item_b, sb = match_notice(t, biz)
    best_score = max(sk, sb)
    src = ""
    if item_k and sk >= 0.72:
        src = "kstartup"
    elif item_b and sb >= 0.72:
        src = "bizinfo"
    status = "OK" if src else "MISS"
    near_b = ""
    if item_b and sb < 0.72:
        near_b = item_b["title"][:55]
    print(f"{status} k={sk:.3f} b={sb:.3f} | {t[:48]}")
    if status == "MISS" and near_b:
        print(f"     near-biz: {near_b}")
