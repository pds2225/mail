import monitor, json, httpx
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) and 'sites' in s else s
fixes = {
    '한국산업기술평가관리원(KEIT)': {
        'row': 'table.table-response01 tbody tr', 'title': "a[onclick*='f_detailPage']",
        'link': "a[onclick*='f_detailPage']",
        'link_arg_re': r"f_detailPage\('([^']+)','([^']+)'\)",
        'link_template': 'retrieveSprtBsnsAncmDetail.do?ancmId={0}&bsnsYy={1}'},
    '신용보증기금(KODIT)': {
        'row': 'table tbody tr', 'title': 'td.bbs_tit', 'link': 'a[data-id]',
        'link_id_attr': 'data-id', 'link_template': 'selectNttInfo.do?mi=263&nttSn={0}'},
    '경남테크노파크': {
        'row': 'table tbody tr', 'title': 'a', 'link': "a[onclick*='goPage']",
        'link_arg_re': r"goPage\([^,]*,[^,]*,\s*'([^']+)'\)", 'link_template': '{0}'},
}
for name, sel in fixes.items():
    site = [x for x in arr if x.get('name') == name][0]
    site['selectors'] = sel
    items = monitor.fetch_html_generic(site)
    link0 = items[0]['link'] if items else ''
    st = ''
    if link0:
        try:
            st = httpx.get(link0, follow_redirects=True, timeout=12, headers={'User-Agent': 'Mozilla/5.0'}).status_code
        except Exception as e:
            st = type(e).__name__
    print(name, '|', len(items), '건 | HTTP', st, '| ', link0[:60])
