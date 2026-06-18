# -*- coding: utf-8 -*-
"""[임시] K-Startup 상세 페이지 HTML 구조 점검 — 본문/지역/대상/업력 필드 셀렉터 찾기."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import httpx
from bs4 import BeautifulSoup

url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd=PBC010&schM=view&pbancSn=178167"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = httpx.get(url, headers=HDR, timeout=30, follow_redirects=True)
soup = BeautifulSoup(r.text, "html.parser")

print("=== p.tit / p.txt 라벨쌍 ===")
for tit in soup.select("p.tit"):
    nxt = tit.find_next("p", class_="txt")
    print(f"  [{tit.get_text(strip=True)}] = {nxt.get_text(' ', strip=True)[:80] if nxt else None}")

print("\n=== 본문 후보 컨테이너 길이 ===")
for sel in [".view_cont", ".content_view", "#contents", ".bizpbanc-view",
            ".titbox", "dl", ".information", ".cont", ".view", "article", "main",
            ".board_view", ".pbanc", ".detail", "table"]:
    els = soup.select(sel)
    tot = sum(len(e.get_text(strip=True)) for e in els)
    if els:
        print(f"  {sel:20s} n={len(els):3d} totlen={tot}")

print("\n=== dt/dd 또는 th/td 라벨 후보 ===")
for tag in soup.select("dt, th")[:40]:
    sib = tag.find_next_sibling(["dd", "td"])
    label = tag.get_text(strip=True)
    if label:
        print(f"  <{tag.name}> [{label}] = {(sib.get_text(' ', strip=True)[:70]) if sib else None}")

print("\n=== '지역','업력','대상','신청' 포함 텍스트 노드(앞 120자) ===")
import re
txt = soup.get_text("\n", strip=True)
for kw in ["지역", "업력", "창업", "대상", "신청기간", "전국", "서울", "성북", "길음", "강원"]:
    idx = txt.find(kw)
    if idx >= 0:
        print(f"  '{kw}': ...{txt[max(0,idx-20):idx+40]!r}...")
    else:
        print(f"  '{kw}': (없음)")
print("\n=== 전체 text 길이:", len(txt))
