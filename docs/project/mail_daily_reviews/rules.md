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

## 핵심 소스 계층 (사람 판정 vs 코딩 게이트)

| 계층 | 소스 | 어디에 쓰이나 | FAIL/무시 |
|------|------|---------------|-----------|
| **핵심 3** | bizinfo · kstartup · nipa | MDR-002 · 사람 일일 판정 1차 | `item_count==0` → FAIL |
| **2군** | kita 등 | `docs/ops/CORE_SOURCES_CHECKLIST.md` **4대**·`PRIORITY_SOURCE_IDS` | 사람 리뷰에서 핵심과 동급 FAIL 금지 · `send_hold=false`면 한 줄만 |
| **비핵심 P0** | mof·kosme·지역·imp 등 | coverage/P0 알림 | 매일 ignore 가능 · 주 1회 클러스터만 |

PARTIAL(spike·DATE_PARSE 등)은 0건이 아니면 MDR overall FAIL이 아니다. 리포트 **WARN** 섹션에만 남긴다.

로컬 경로: GHA `mail-daily-review-*` 를 `_gha_<run_id>`에 받은 뒤  
`python scripts/promote_mdr_artifact.py var/reviews/_gha_<run_id>` 로 `var/reviews/YYYY-MM-DD/` 승격  
(`var/reviews/*`는 gitignore — ledger만 커밋).

## 보고 형식 (lessons-audit 대응)

```
## MDR 일일 점검 (mail_daily_review)
✅ 준수: MDR-001 · MDR-003 · MDR-004 · MDR-005
❌ 위반: MDR-002 — bizinfo=0
— 해당없음/SKIP: 0
```

## ZERO_MISS 7원칙 매핑 (PR #218 / TASK-G06)

`docs/project/ZERO_MISS_GUARDRAILS.md`(skip_gate 계열)의 운영 계약을 **발송 후 자동 검수**로 재확인한다.
본 MDR 브랜치는 그 파일을 새로 쓰지 않는다(#218과 충돌 회피). #218 머지 후 아래 표가 문서·실측을 잇는다.

| ZERO_MISS 원칙 | MDR |
|----------------|-----|
| 1. 멱등 기준일 ≠ 참조창 | MDR-001 · MDR-004 |
| 2. skip 이후에도 감시(coverage) | MDR-001 |
| 3. 핵심소스 0건 fail-closed | MDR-002 |
| 4. 알림·아티팩트 침묵 금지 | GHA `mail-daily-review-*` 아티팩트 + Step Summary |
| 5. 표시 오염 ≠ 설정 | MDR-005 |
| 6. 누락 < 과출 (recall) | `recall_zero_gate` / core_sources (코딩 게이트; MDR 외) |
| 7. Secret·실발송 = 사람 게이트 | SMTP/IMAP 미호출 · Secret 미출력 (설계 계약) |

## 30초 체크 (사람)

```text
python scripts/mail_daily_review.py --json
# overall=PASS 이면 종료. FAIL 이면 fails[].id 만 읽고 RULES §7b / ZERO_MISS 표로 원인 좁힘.
# 누적 패턴: docs/project/mail_daily_reviews/context/ledger.jsonl 끝 3~5줄
```

목표: 30초 안에 PASS/FAIL·위반 ID만 확인. 본문·수신자·Secret은 보지 않는다.

## 연결

- Auto Dev 안전규칙: `docs/project/RULES.md` §7b
- 누락제로 가드레일: `docs/project/ZERO_MISS_GUARDRAILS.md` (PR #218)
- TASKS: TASK-019 (본 작업) · TASK-G01~G06 (#218)
- 발송 훅: `.github/workflows/monitor.yml` → `mail_daily_review` step
- 누적 컨텍스트: `docs/project/mail_daily_reviews/context/ledger.jsonl`
