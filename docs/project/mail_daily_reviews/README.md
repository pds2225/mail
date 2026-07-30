# Mail Daily Reviews — 발송 후 검수 컨텍스트

매일(회차별) digest 발송 **이후**에 남는 메타·로그·draft만으로 검수하고,
결과를 쌓아 L규칙(lessons-audit)처럼 매일 대조한다.

SMTP/IMAP **추가 발송·수신함 삭제 없음**. Secret 미출력.

## 경로 규약

| 경로 | 역할 | Git |
|------|------|-----|
| `var/reviews/YYYY-MM-DD/review_{am\|pm}.json` | 당일·회차 기계 판독 결과 | ignore (`var/reviews/`) |
| `var/reviews/YYYY-MM-DD/review_{am\|pm}.md` | 사람용 요약 | ignore |
| `var/reviews/YYYY-MM-DD/review.json` | 최신 회차 포인터 | ignore |
| `var/reviews/YYYY-MM-DD/inbox_sample.txt` | (선택) 사람이 붙인 본문 샘플 — 외부발송 징후 검사용 | ignore |
| `docs/project/mail_daily_reviews/rules.md` | MDR-001… 규칙 정의 (L규칙 대응) | track |
| `docs/project/mail_daily_reviews/context/ledger.jsonl` | append-only 누적 컨텍스트 | track |
| `docs/project/mail_daily_reviews/README.md` | 본 문서 | track |

기존 `var/reports/review/`(review_pipeline 초안) · `var/logs/source_coverage_*.json`(커버리지) ·
`var/state/delivery_state.json`(멱등 키)를 **입력**으로 재사용한다. 중복 파이프라인을 만들지 않는다.

## ledger.jsonl 스키마 (한 줄 = 1회 검수)

```json
{
  "ts": "2026-07-30T08:45:00+0900",
  "date": "2026-07-30",
  "slot": "am",
  "cycle_key": "2026-07-30#am",
  "overall": "PASS",
  "fails": [],
  "pass_ids": ["MDR-001", "MDR-002", "MDR-003", "MDR-004", "MDR-005"],
  "skip_ids": []
}
```

`fails[].id` / `fails[].detail` 만으로 재발 패턴을 집계한다(본문·수신자·Secret 없음).

## 매일 체크 명령

```powershell
cd D:\mail   # 또는 worktree
python scripts/mail_daily_review.py
python scripts/mail_daily_review.py --date 2026-07-30 --slot am --json
```

### 30초 체크 (운영)

1. `python scripts/mail_daily_review.py --json` → `overall` / `fails`
2. FAIL이면 `rules.md` MDR ID → ZERO_MISS 7원칙 표로 원인 좁힘
3. 재발이면 `context/ledger.jsonl` 최근 줄에서 같은 `fails[].id` 빈도 확인

GHA: `.github/workflows/monitor.yml` 발송 step 이후 `mail_daily_review` step.
기본은 **warn-only**(아티팩트+Summary, workflow red 강제 아님). `--fail-on-error`로 엄격화 가능.

### 문서 연결

| 문서 | 역할 |
|------|------|
| `docs/project/RULES.md` §7b | Auto Dev 허용 경로·매일 검수 계약 |
| `docs/project/TASKS.md` TASK-019 | 큐 완료 기록 |
| `docs/project/ZERO_MISS_GUARDRAILS.md` | 누락제로 7원칙(PR #218). MDR은 발송 후 재확인 |
| `docs/project/mail_daily_reviews/rules.md` | MDR-001…005 + ZERO_MISS 매핑 |

PR #218(`cursor/skipgate-ops-hardening`)과 `monitor.yml`·`TASKS.md`만 겹친다.
MDR는 아티팩트 step **아래**에 훅을 추가하고 `if-no-files-found` 줄은 건드리지 않음 → #218의 `warn` 변경과 수동 머지 용이.

## 한계

- **IMAP 본문 미검수**: 실제 수신함 HTML을 읽지 않는다. 외부 08:54 메일은
  `var/reviews/.../inbox_sample.txt`에 머리글을 붙여야 MDR-003이 잡는다.
- outbox 암호문(`delivery_outbox.enc`)은 해독하지 않는다.
- 제목 badge는 로그/draft에 남은 텍스트만 스캔한다.
