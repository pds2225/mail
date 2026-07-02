import monitor, json
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) and 'sites' in s else s
targets = ['한국산업기술평가관리원(KEIT)', '신용보증기금(KODIT)', '지역디자인통합플랫폼',
           '서울TP', '혁신제품지정공고(나라장터)', '경남테크노파크']
for name in targets:
    site = [x for x in arr if x.get('name') == name][0]
    url = site['url']
    soup = monitor._soup(url)
    print('=====', name, '=====')
    print('  url:', url[:60])
    if not soup:
        print('  접근불가'); continue
    rowsel = site.get('selectors', {}).get('row', 'table tbody tr')
    rows = soup.select(rowsel)
    print('  row("' + rowsel + '"):', len(rows), '| table tbody tr:', len(soup.select('table tbody tr')), '| li:', len(soup.select('tbody tr')))
    use = rows or soup.select('table tbody tr')
    if use:
        a = use[0].select_one('a[onclick]') or use[0].select_one('a')
        if a:
            print('  a.onclick:', (a.get('onclick') or '')[:80])
            print('  a.href:', (a.get('href') or '')[:55], '| data-id:', a.get('data-id'), '| data-seq:', a.get('data-seq'))
            print('  제목:', a.get_text(strip=True)[:30])
