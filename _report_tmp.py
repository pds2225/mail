"""sites.json 전수 점검 → URL이 실제 공고 게시판이 아닌(0건) 사이트를 진단·정리(전달용 md)."""
import monitor, json

s = json.load(open('sites.json', encoding='utf-8'))
arr = s.get('sites', s) if isinstance(s, dict) else s
sites = [x for x in arr if x.get('enabled', True)]
print(f'enabled 사이트: {len(sites)}개 점검 시작')

problem = []
for site in sites:
    name = str(site.get('name') or site.get('id') or '?')
    url = str(site.get('url', ''))
    typ = str(site.get('type', ''))
    note = str(site.get('note', ''))
    # 1) 수집 시도
    try:
        f = monitor.FETCHERS.get(typ)
        items = f({**site, 'max_pages': 1}) if f else []
    except Exception:
        items = []
    if items:
        continue  # 정상 수집 → 문제 아님
    # 2) 0건 → 페이지 구조 진단
    try:
        soup = monitor._soup(url)
        if not soup:
            diag = '접근 불가 (연결실패/차단/타임아웃)'
        else:
            tr = len(soup.select('tbody tr'))
            tbl = len(soup.select('table'))
            a = len(soup.select('a[href]'))
            low = url.lower()
            if tr >= 3:
                diag = f'게시판 있음(행 {tr}개) → 수집 셀렉터/날짜파싱 안 맞음'
            elif any(k in low for k in ('menu.', '/menu', 'index', 'main', '/home')):
                diag = '메뉴/홈 페이지 (실제 게시판 URL 아님)'
            elif tbl == 0:
                diag = 'JS로 그리는 동적 페이지 (정적 수집 불가)'
            else:
                diag = f'구조 불일치 (table={tbl}, a={a})'
    except Exception as e:
        diag = f'분석 오류 ({type(e).__name__})'
    problem.append((name, typ, diag, url, note))

lines = [
    '# 공고 수집 안 되는 사이트 정리 (전달용)',
    '',
    '- 점검일: 2026-06-21',
    f'- enabled 사이트 {len(sites)}개 중 **{len(problem)}개**가 1페이지 수집 0건',
    '- "진단"은 왜 0건인지 추정 원인 (메뉴페이지=URL부터 게시판 아님 / JS=동적 / 셀렉터=게시판은 있으나 수집규칙 불일치 / 접근불가=사이트 다운·차단)',
    '',
    '| 사이트 | type | 진단 (왜 0건) | 현재 URL | sites.json 비고 |',
    '|---|---|---|---|---|',
]
# 진단 유형별 정렬(메뉴페이지 먼저 = URL 자체가 문제)
order = {'메': 0, '구': 1, 'J': 2, '게': 3, '접': 4, '분': 5}
problem.sort(key=lambda x: order.get(x[2][:1], 9))
for n, typ, diag, url, note in problem:
    lines.append(f'| {n[:30]} | {typ} | {diag} | {url[:60]} | {note[:35]} |')

out = 'logs/site_problem_report.md'
open(out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print(f'완료: 문제 {len(problem)}개 → {out}')
