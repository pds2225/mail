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
    collect_extra_source_items,
    collect_full_monitor_items,
    find_notice_for_target,
    accept_match,
)

targets = load_targets(Path("targets/kstartup_20260623.txt"))
biz = collect_bizinfo_items()
extra = collect_extra_source_items()
print("loading full monitor pool...")
full = collect_full_monitor_items()
headers = {**monitor.HTTP_HEADERS, "Referer": "https://www.k-startup.go.kr/"}
with httpx.Client(timeout=60, headers=headers, follow_redirects=True, verify=False) as c:
    ks = collect_kstartup_items(client=c)
    found = 0
    misses = []
    for t in targets:
        item, score, src = find_notice_for_target(
            t, ks, c,
            bizinfo_pool=biz,
            extra_pool=extra,
            monitor_pool=full,
            min_score=0.72,
        )
        title = str((item or {}).get("title", ""))
        if item and accept_match(t, title, score, 0.72):
            found += 1
            print(f"OK {src} {score:.3f} | {t[:48]}")
        else:
            misses.append((score, t, src))
    print()
    print("found", found, "/", len(targets))
    print("misses", len(misses))
    for s, t, src in sorted(misses, reverse=True)[:20]:
        print(f" {s:.3f} {src:8} | {t[:52]}")
