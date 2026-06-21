"""임시: NO_ITEMS 핵심 사이트 max_pages=3 재수집 → 진짜 0건인지 확인."""
import monitor, json
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) else s
targets = ['창업진흥원', '서울산업진흥원', '산업기술진흥원(KIAT)', '과학기술정보통신부',
           '소상공인시장진흥공단', 'KOTRA(', '중소벤처기업진흥', '신용보증기금']
print('=== NO_ITEMS 핵심 사이트 max_pages=3 재수집 ===')
for site in arr:
    nm = str(site.get('name', ''))
    if any(t in nm for t in targets):
        stype = site.get('type')
        try:
            f = monitor.FETCHERS.get(stype)
            if not f:
                print('  ' + nm[:32] + ': fetcher없음 type=' + str(stype))
                continue
            items = f({**site, 'max_pages': 3})
            print('  ' + nm[:32] + ': ' + str(len(items)) + '건  (type=' + str(stype) + ')')
        except Exception as e:
            print('  ' + nm[:32] + ': 오류 ' + type(e).__name__ + ' ' + str(e)[:40])
