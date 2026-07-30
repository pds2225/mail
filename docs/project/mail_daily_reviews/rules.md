# MDR 규칙 — Mail Daily Review (L규칙 스타일)

`D:\.omc\agent-learning\lessons.md` 의 L규칙처럼, **매일 발송 산출물**을 규칙 ID로 전수 대조한다.
구현: `mail_core/operations/daily_review.py` / `scripts/mail_daily_review.py`.

| ID | 이름 | FAIL 조건 | 근거 사고 |
|----|------|-----------|-----------|
| MDR-001 | 무증상 스킵 | `source_coverage_YYYYMMDD.json` 없음, 또는 skip 마커+coverage 없음, 또는 단시간 실행+당일키 없음 | days_back↔멱등키 혼동으로 2~3분 success·메일 미발송 |
| MDR-002 | 핵심소스 0건 | coverage 상 `bizinfo`/`kstartup`/`nipa` 중 `item_count==0` | 기업마당 0건인데 Actions success |
| MDR-003 | 08:54 외부발송 징후 | 텍스트에 `기업마당 API + 마이페어 + K-Startup` 있고 `수집일시:`/`재조회범위:` 없음 | repo 밖 스케줄/구클론 이중발송 |
| MDR-004 | delivery_state 당일키 | 당일 회차(`YYYY-MM-DD#am`/`#pm`) 키 0개 | 발송 미기록·스킵 |
| MDR-005 | 제목 badge 품질 | 스캔 텍스트에 `새로운게시글`/`file` 등 badge 꼬리 | digest 제목 오염 |

## 보고 형식 (lessons-audit 대응)

```
## MDR 일일 점검 (mail_daily_review)
✅ 준수: MDR-001 · MDR-003 · MDR-004 · MDR-005
❌ 위반: MDR-002 — bizinfo=0
— 해당없음/SKIP: 0
```

## 연결

- Auto Dev 안전규칙: `docs/project/RULES.md` §7b
- 발송 훅: `.github/workflows/monitor.yml` → `mail_daily_review` step
- 누적 컨텍스트: `docs/project/mail_daily_reviews/context/ledger.jsonl`
