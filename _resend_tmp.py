"""임시: NIPA 2026 AI 공고를 온전 링크 + 자격/대상/내용(enrich)과 함께 ekth3691에게 재발송."""
import re
import monitor

site = {'url': 'https://www.nipa.kr/home/bsnsAll/0/nttList?bbsNo=4&tab=2',
        'name': '정보통신산업진흥원(NIPA)', 'max_pages': 3}
items = monitor.fetch_nipa(site)

ai = re.compile('AI|인공지능|머신러닝|딥러닝|LLM|생성형|SaaS|클라우드|데이터센터|메타버스|SW')
skip = re.compile('결과|입찰|평가위원|선정 공고|인테리어|용역|재직자|채용|후보자|발표평가|서류평가|쇼케이스')
cands, seen = [], set()
for it in items:
    t = it.get('title', '')
    if '2026' in t and ai.search(t) and not skip.search(t) and t not in seen:
        seen.add(t)
        cands.append(it)
cands = cands[:15]

body = "[예비창업 AI] 2026년 AI 지원사업 — 개선판 (온전한 링크 + 지원대상·내용)\n"
body += "각 공고의 신청자격(예비창업/개인 가능 여부)을 내용에서 확인하세요.\n\n"
for i, it in enumerate(cands, 1):
    e = monitor.enrich_item_from_detail(it)
    desc = re.sub(r'\n{2,}', '\n', (e.get('description') or '').strip())[:600]
    body += f"[{i}] {it['title']}\n링크: {it['link']}\n{desc or '(상세 본문 없음)'}\n\n{'='*42}\n\n"

monitor._ONLY_TO = 'ekth3691@gmail.com'
monitor.send_email(f"[예비창업 AI] 2026 AI 지원사업 {len(cands)}건 (링크·내용 개선판)", body, 'ekth3691@gmail.com')
print('발송 완료:', len(cands), '건')
for it in cands:
    print('  -', it['title'][:50])
