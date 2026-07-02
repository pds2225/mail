"""임시: 모든 enabled 사이트의 대표 공고 링크 HTTP 상태 확인."""
import json, httpx
import monitor

s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) else s
sites = [x for x in arr if x.get('enabled', True)]
print(f'enabled 사이트: {len(sites)}개')
results = []
for site in sites:
    name = (site.get('name') or site.get('id') or '?')[:38]
    ftype = site.get('type')
    try:
        fetcher = monitor.FETCHERS.get(ftype)
        if not fetcher:
            results.append((name, 'NO_FETCHER', str(ftype))); continue
        items = fetcher({**site, 'max_pages': 1})
        if not items:
            results.append((name, 'NO_ITEMS', '')); continue
        link = (items[0].get('link') or '').strip()
        if not link:
            results.append((name, 'NO_LINK', '')); continue
        try:
            r = httpx.get(link, follow_redirects=True, timeout=15,
                          headers={'User-Agent': 'Mozilla/5.0'})
            results.append((name, r.status_code, link[:58]))
        except Exception as e:
            results.append((name, 'HTTP_ERR', type(e).__name__))
    except Exception as e:
        results.append((name, 'FETCH_ERR', type(e).__name__))

print('\n=== 사이트별 대표 링크 HTTP 상태 ===')
bad = []
for n, st, info in results:
    mark = 'OK' if st == 200 else '!!'
    print(f'[{mark}] {str(st):>10} | {n:38} | {info}')
    if st != 200:
        bad.append((n, st, info))
ok_n = sum(1 for _, st, _ in results if st == 200)
print(f'\n정상(200): {ok_n} / {len(results)}')
if bad:
    print('확인 필요:')
    for n, st, info in bad:
        print(f'  - {n}: {st} ({info})')
