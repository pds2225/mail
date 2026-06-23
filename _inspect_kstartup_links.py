# -*- coding: utf-8 -*-
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/mail")
import httpx
from bs4 import BeautifulSoup
import monitor
from scripts.download_kstartup_targets import collect_kstartup_items

items = collect_kstartup_items(max_pages=100)
for it in items[:5]:
    r = httpx.get(it["link"], headers=monitor.HTTP_HEADERS, timeout=60, verify=False)
    html = r.text
    print("===", it["title"][:55])
    patterns = [
        r"fn_open_window\([^)]{10,200}\)",
        r"pbancUrl[^\"']{0,80}",
        r"orginl[^\"']{0,80}",
        r"bizinfo\.go\.kr[^\"']{0,120}",
        r"sba\.seoul[^\"']{0,120}",
    ]
    for pat in patterns:
        ms = re.findall(pat, html, re.I)
        if ms:
            print(" ", pat[:30], "->", ms[:2])
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("button, a, .btn, .btn-primary"):
        t = el.get_text(" ", strip=True)
        if any(k in t for k in ("원본", "신청", "바로가기", "공고보기", "홈페이지", "기업마당")):
            print(
                " BTN",
                t[:35],
                "| href=",
                str(el.get("href", ""))[:90],
                "| onclick=",
                str(el.get("onclick", ""))[:140],
            )
    for inp in soup.select("input[type=hidden]"):
        n, v = inp.get("name", ""), inp.get("value", "")
        if v and ("http" in v or "bizinfo" in v.lower() or "url" in n.lower()):
            print(" HIDDEN", n, "=", v[:120])
    print()
