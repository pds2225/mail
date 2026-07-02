# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/mail")
import httpx
from bs4 import BeautifulSoup
import monitor

# K-Startup search for SBA title
title_kw = "K-뷰티"
url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
for sttus in ("ing", "end", ""):
    params = {"schMenuId": "10090", "pageIndex": "1", "viewCount": "100", "pbancClssCd": "PBC010", "schPbancNm": title_kw}
    if sttus:
        params["pbancSttus"] = sttus
    r = httpx.get(url, params=params, headers=monitor.HTTP_HEADERS, timeout=60, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select(".notice")
    print(f"status={sttus or 'ALL'} search={title_kw} cards={len(cards)}")
    for c in cards[:5]:
        a = c.select_one("a")
        print(" ", (a.get_text(strip=True) if a else "")[:70])

# also try without status filter all pages
for page in range(1, 6):
    params = {"schMenuId": "10090", "pageIndex": str(page), "viewCount": "100", "schPbancNm": "SBA"}
    r = httpx.get(url, params=params, headers=monitor.HTTP_HEADERS, timeout=60, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select(".notice")
    if not cards:
        print(f"SBA search page {page}: 0")
        break
    print(f"SBA search page {page}: {len(cards)}")
    for c in cards[:3]:
        a = c.select_one("a")
        print(" ", (a.get_text(strip=True) if a else "")[:70])
