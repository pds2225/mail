# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/mail")
import httpx
from bs4 import BeautifulSoup
import monitor
from scripts.download_kstartup_targets import norm_text, match_notice

targets = [
    "SBA x LG전자 「K-뷰티·라이프스타일 판로 연계사업(태국)」 참여기업 모집",
    "「2026 헬스엑스챌린지 서울」 참여기업 모집",
    "가죽·패션 제품개발 협업사업 모집 공고",
]

# fetch broader list: no pbancSttus filter, more pages
url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
all_items = []
seen = set()
for clss in ("PBC010", "PBC020"):
    for page in range(1, 21):
        params = {"schMenuId": "10090", "pageIndex": str(page), "viewCount": "100", "pbancClssCd": clss}
        r = httpx.get(url, params=params, headers=monitor.HTTP_HEADERS, timeout=60, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".notice")
        if not cards:
            break
        new = 0
        for card in cards:
            a = card.select_one("a")
            title = (a.get_text(strip=True) if a else "").replace("새로운게시글", "").strip()
            sn = ""
            for btn in card.select("button[onclick]"):
                m = re.search(r"\d+", btn.get("onclick", ""))
                if m:
                    sn = m.group(0)
                    break
            if not title or (sn and sn in seen):
                continue
            if sn:
                seen.add(sn)
            link = f"https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd={clss}&schM=view&pbancSn={sn}" if sn else ""
            all_items.append({"title": title, "link": link, "sn": sn})
            new += 1
        if new == 0:
            break
print("total items no-status-filter:", len(all_items))

for t in targets:
    item, score = match_notice(t, all_items)
    print(f"\nTARGET: {t[:50]}")
    print(f"  match: {score:.2f} -> {(item or {}).get('title','')[:60]}")

# per-target keyword search
for kw in ["헬스엑스", "SBA", "가죽", "LG전자"]:
    params = {"schMenuId": "10090", "pageIndex": "1", "viewCount": "100", "schPbancNm": kw}
    r = httpx.get(url, params=params, headers=monitor.HTTP_HEADERS, timeout=60, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    titles = [(a.get_text(strip=True) if (a := c.select_one("a")) else "") for c in soup.select(".notice")]
    hit = [t for t in titles if kw.lower() in t.lower() or kw in t]
    print(f"\nsearch kw={kw}: {len(titles)} cards, keyword hits={len(hit)}")
    for h in hit[:3]:
        print(" ", h[:70])
