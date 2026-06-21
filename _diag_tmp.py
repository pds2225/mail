import monitor, json, inspect
print('=== fetch_html_generic 소스(앞부분) ===')
print(inspect.getsource(monitor.fetch_html_generic)[:1600])
print()
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) else s
kised = None
for x in arr:
    if 'KISED' in str(x.get('name', '')):
        kised = x
        break
if kised:
    print('=== KISED 설정 ===')
    print('url:', kised.get('url'))
    print('type:', kised.get('type'))
    print('config:', {k: v for k, v in kised.items() if k not in ('name', 'id', 'url', 'type')})
    soup = monitor._soup(kised['url'])
    if soup:
        print('table:', len(soup.select('table')), '/ tbody tr:', len(soup.select('tbody tr')),
              '/ tr:', len(soup.select('tr')), '/ a[href]:', len(soup.select('a[href]')))
        t = soup.select_one('table')
        if t:
            print('첫 table 텍스트(앞300):', t.get_text(' ', strip=True)[:300])
    else:
        print('페이지 못 가져옴(JS 렌더링/차단 가능)')
