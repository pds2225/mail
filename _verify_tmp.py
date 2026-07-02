"""임시 검증: watchlist AI 제거 후 🎯 건수 + 예비창업 AI 그룹 매칭 공고 확인. 검증 후 삭제."""
import os, json
for k in ['BIZINFO_API_KEY', 'ANTHROPIC_API_KEY', 'GMAIL_ADDRESS', 'GMAIL_APP_PASSWORD']:
    os.environ.setdefault(k, 'x')
import monitor

r = monitor.run_dry_run(fetch_coverage=False)

print('==== 결과 요약 ====')
for k, v in r.items():
    if isinstance(v, (int, str, bool, float, type(None))):
        print(f'  {k}: {v}')
    elif isinstance(v, list):
        print(f'  {k}: (목록 {len(v)}개)')

# 미리보기 그룹(dry-run에서 매칭된 그룹별 공고)
pg = r.get('preview_groups') or r.get('sent_groups') or []
print('\n==== 그룹별 매칭 공고 ====')
if not pg:
    print('  (preview_groups 비어있음 — 키 탐색)')
    print('  result keys:', list(r.keys()))
for g in pg:
    if isinstance(g, dict):
        name = g.get('name') or g.get('group') or '?'
        items = g.get('items') or g.get('notices') or g.get('matched') or []
        print(f'\n[그룹] {name} — 매칭 {len(items)}건')
        for it in (items[:10] if isinstance(items, list) else []):
            title = it.get('title') if isinstance(it, dict) else str(it)
            print(f'   - {title}')
    else:
        print('  raw:', str(g)[:200])
