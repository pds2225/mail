import monitor, json, re, httpx
from urllib.parse import urljoin
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) and 'sites' in s else s
targets = {'지역디자인통합플랫폼': 'fnGoBizNotiDetlView', '서울TP': 'goBoardView', '혁신제품지정공고(나라장터)': 'fnMoveDtl'}
for name, fn in targets.items():
    site = [x for x in arr if x.get('name') == name][0]
    url = site['url']
    soup = monitor._soup(url)
    print('=====', name, '(' + fn + ') | url:', url[:48])
    if not soup:
        print('  접근불가'); continue
    inline = ' '.join(sc.get_text() for sc in soup.select('script') if not sc.get('src'))
    pat = re.compile(r'function\s+' + re.escape(fn) + r'\s*\(([^)]*)\)\s*\{(.{0,360}?)\}', re.S)
    m = pat.search(inline)
    if m:
        print('  args:', m.group(1), '| body:', re.sub(r'\s+', ' ', m.group(2))[:280])
    else:
        found = False
        for sc in soup.select('script[src]'):
            src = sc.get('src', '')
            if src and not src.startswith('http'):
                src = urljoin(url, src)
            try:
                js = httpx.get(src, timeout=8, headers={'User-Agent': 'Mozilla/5.0'}).text
                m2 = pat.search(js)
                if m2:
                    print('  외부JS(' + src.split('/')[-1] + ') args:', m2.group(1), '| body:', re.sub(r'\s+', ' ', m2.group(2))[:280])
                    found = True
                    break
            except Exception:
                pass
        if not found:
            print('  함수정의 못 찾음(동적/난독화 가능)')
