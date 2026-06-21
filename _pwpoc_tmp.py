"""PoC: playwright(브라우저)로 KISED JS 페이지를 읽어 공고가 나오는지 시연."""
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

url = 'https://www.kised.or.kr/menu.es?mid=a10201000000'
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto(url, timeout=30000)
    pg.wait_for_timeout(3500)  # JS 렌더링 대기
    html = pg.content()
    b.close()

soup = BeautifulSoup(html, 'html.parser')
print('=== playwright로 읽은 KISED 페이지 ===')
print('table:', len(soup.select('table')),
      '/ tbody tr:', len(soup.select('tbody tr')),
      '/ a[href]:', len(soup.select('a[href]')))
print('--- 공고 제목 샘플 ---')
n = 0
for tr in soup.select('tbody tr'):
    a = tr.select_one('a')
    txt = (a.get_text(strip=True) if a else tr.get_text(strip=True))[:50]
    if txt:
        print('  -', txt)
        n += 1
    if n >= 8:
        break
print('읽힌 공고 행:', len(soup.select('tbody tr')))
