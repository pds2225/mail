import monitor, json, httpx, shutil
shutil.copy('sites.json', 'sites.json.bak_genfix')
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) and 'sites' in s else s

fixes = {
    '산업통상자원부': {'url': None, 'sel': {
        'row': 'table tbody tr', 'title': 'div.board-link a', 'link': 'div.board-link a',
        'link_arg_re': r"article\.view\('(\d+)'\)", 'link_template': '/kor/article/ATCL2826a2625/{0}/view'}},
    '한국산업기술평가관리원(KEIT)': {'url': None, 'sel': {
        'row': 'table.table-response01 tbody tr', 'title': "a[onclick*='f_detailPage']", 'link': "a[onclick*='f_detailPage']",
        'link_arg_re': r"f_detailPage\('([^']+)','([^']+)'\)", 'link_template': 'retrieveSprtBsnsAncmDetail.do?ancmId={0}&bsnsYy={1}'}},
    '경남테크노파크': {'url': None, 'sel': {
        'row': 'table tbody tr', 'title': 'a', 'link': "a[onclick*='goPage']",
        'link_arg_re': r"goPage\([^,]*,[^,]*,\s*'([^']+)'\)", 'link_template': '{0}'}},
    '신용보증기금(KODIT)': {'url': 'https://www.kodit.co.kr/kodit/na/ntt/selectNttList.do?mi=2638&bbsId=148', 'sel': {
        'row': 'table tbody tr', 'title': 'td.bbs_tit', 'link': 'a[data-id]',
        'link_id_attr': 'data-id', 'link_template': 'selectNttInfo.do?mi=2638&bbsId=148&nttSn={0}'}},
}
for name, fx in fixes.items():
    site = [x for x in arr if x.get('name') == name][0]
    if fx['url']:
        site['url'] = fx['url']
    site['selectors'] = fx['sel']
json.dump(s, open('sites.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
json.load(open('sites.json', encoding='utf-8'))  # 유효성

print('=== 최종 검증 (재수집 + 링크 HTTP) ===')
for name in fixes:
    site = [x for x in arr if x.get('name') == name][0]
    items = monitor.fetch_html_generic(site)
    link0 = items[0]['link'] if items else ''
    st = ''
    if link0:
        try:
            st = httpx.get(link0, follow_redirects=True, timeout=12, headers={'User-Agent': 'Mozilla/5.0'}).status_code
        except Exception as e:
            st = type(e).__name__
    mark = 'OK' if (items and st == 200) else 'XX'
    print(f'  [{mark}] {name[:22]} | {len(items)}건 | HTTP {st}')
