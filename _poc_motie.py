import monitor, json
s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) and 'sites' in s else s
motie = [x for x in arr if x.get('name') == '산업통상자원부'][0]
motie['selectors'] = {
    'row': 'table tbody tr',
    'title': 'div.board-link a',
    'link': 'div.board-link a',
    'link_arg_re': r"article\.view\('(\d+)'\)",
    'link_template': '/kor/article/ATCL2826a2625/{0}/view',
}
items = monitor.fetch_html_generic(motie)
print('산업부:', len(items), '건')
for it in items[:4]:
    print('  -', str(it['title'])[:34], '|', str(it['link'])[:66])
