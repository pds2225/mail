# Auto Dev Queue — RULES (Vercel Mail 프로젝트 전용)

> 이 파일은 자동개발 큐가 Vercel Mail 프로젝트에서 준수해야 할 안전규칙을 정의합니다.

## 1. Mail 프로젝트 안전규칙

| # | 규칙 | 설명 |
|---|------|------|
| 1 | 실제 이메일 자동 발송 금지 | auto-dev 작업에서 실제 SMTP/Gmail/IMAP 발송 절대 금지 |
| 2 | preview/draft/dry-run만 허용 | 기본 동작은 "preview 생성", "draft 생성", "dry-run"까지만 |
| 3 | 수신자 이메일 마스킹 | 로그에 이메일 주소 전체 출력 금지 (예: `e***@gmail.com`) |
| 4 | 민감정보 로그 금지 | 이메일 본문, 첨부파일, API Key, Token 로그 출력 금지 |
| 5 | Secret 하드코딩 금지 | Gmail/SMTP/IMAP Secret 값을 코드에 하드코딩 금지 |
| 6 | 발송 전 사용자 승인 필수 | send 기능은 사용자 명시 승인 플래그가 있을 때만 허용 |
| 7 | 테스트에서 실제 발송 금지 | 테스트는 mock/dry-run만 허용 |
| 8 | 실패 시 자동 재발송 금지 | 발송 실패 시 자동 재시도 금지 |
| 9 | 중복 발송 방지 | 동일 내용 중복 발송 방지 규칙 필수 |

## 2. 환경변수

### GitHub Actions Secrets

| Secret 이름 | 용도 | 필수 여부 |
|-------------|------|----------|
| `OPENAI_API_KEY` | AI 기능 | 선택 |
| `ANTHROPIC_API_KEY` | Claude AI 요약 | 선택 |
| `AUTO_DEV_PAT` | GitHub PR 생성용 PAT | 선택 (없으면 github.token 사용) |

> **Auto Merge:** 자동 머지가 기본이다. Checks 초록·충돌 없으면 squash-merge 한다.
> 예외는 Draft, `needs-human`/`blocked`, merge conflict, `.env*`.
> `monitor.py` / `streamlit_app.py` 변경도 기본 병합한다. `--admin` 은 금지.
>
> `.github/workflows/auto-merge.yml` 은 checkout/`gh` 에
> `github.token` 만 쓴다. Secret `AUTO_DEV_PAT` 이 만료돼 있어도
> `secrets.AUTO_DEV_PAT || github.token` 은 빈 값이 아니라 만료 토큰을 넘기므로
> checkout 이 `could not read Username for 'https://github.com'` 로 실패한다
> (2026-08-13 run 31660085605). 유효 PAT 가 준비되기 전에는 Auto Merge에 PAT를 넣지 않는다.
>
> PR 번호는 `GET .../actions/runs/{id}/pull-requests` 를 쓰지 않는다. 이 API 는
> GITHUB_TOKEN 에서 404 가 난다 (run 31662894294). `workflow_run.pull_requests`,
> `gh pr list --head`, `gh pr list --search SHA` 순으로 찾는다. 없으면 skip
> (job 실패 아님). 같은 저장소 브랜치 PR만 대상이다.

### Vercel Environment Variables

| 환경변수 이름 | 용도 | dry-run 상태 |
|--------------|------|-------------|
| `GMAIL_ADDRESS` | 메일 발신 주소 | 🚫 발송 기능 검증 전까지 미사용 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 | 🚫 발송 기능 검증 전까지 미사용 |
| `SMTP_HOST` | SMTP 서버 주소 | 🚫 발송 기능 검증 전까지 미사용 |
| `SMTP_PORT` | SMTP 서버 포트 | 🚫 발송 기능 검증 전까지 미사용 |
| `IMAP_HOST` | IMAP 서버 주소 | 🚫 발송 기능 검증 전까지 미사용 |
| `IMAP_PORT` | IMAP 서버 포트 | 🚫 발송 기능 검증 전까지 미사용 |

> **중요:** Mail 관련 환경변수(`GMAIL_*`, `SMTP_*`, `IMAP_*`)는 실제 발송 기능이 검증되기 전까지 필수로 요구하지 않음. 자동개발 큐에서는 dry-run / draft-only 기준으로만 동작.

## 3. 기존 앱 보호 규칙

| # | 규칙 |
|---|------|
| 1 | 기존 앱 기능 파일 수정 금지 (`monitor.py`, `streamlit_app.py`) |
| 2 | 기존 메일 발송 로직 수정 금지 |
| 3 | main 브랜치 직접 수정 금지 — **자동개발 큐 한정** (사람이 지시한 작업은 3-2 참조) |
| 4 | .env 파일 수정 금지 |
| 5 | 대규모 리팩토링 금지 |
| 6 | 불필요한 패키지 설치 금지 |

> **적용 범위 (2026-08-04 명시):** 위 보호 규칙은 이 문서 제목대로 **자동개발 큐(무인 AI 실행)** 에 적용된다.
> 사람이 직접 지시하고 결과를 검증하는 작업은 아래 «예외 절차» 를 따른다.

### 3-1. 예외 절차 — 사람이 지시한 계획적 구조 개선 (규칙 1·5 한정)

`monitor.py` 분할처럼 규칙 **1(앱 기능 파일 수정)·5(대규모 리팩토링)** 에 걸리는 작업은
아래 5가지를 **모두** 충족할 때만 허용한다. 하나라도 빠지면 금지 그대로다.

| # | 조건 |
|---|------|
| 1 | 사용자가 명시적으로 지시했고, 대상·범위가 문서로 특정돼 있다 |
| 2 | **동작 변경 없는 이동(move)만** — 로직·조건·출력 문구를 한 줄도 바꾸지 않는다 |
| 3 | 원래 위치에 재수출(re-export)을 남겨 기존 호출부·테스트가 그대로 동작한다 |
| 4 | 전용 브랜치 진행을 **권장**한다 (main 직접 작업은 3-2 조건을 추가로 지킨다) |
| 5 | 단계마다 `python -c "import monitor"` + 관련 pytest 통과를 증거로 남긴다 |

- 규칙 **2(발송 로직)·4(.env)·6(패키지 설치)** 에는 **예외가 없다.**
- 자동개발 큐(무인 실행)는 이 예외를 스스로 적용할 수 없다. 사람이 지시한 건에 한한다.

### 3-2. main 브랜치 직접 수정 (2026-08-04 사용자 지정 — 허용)

사람이 지시한 작업은 `main` 을 직접 수정할 수 있다. 단 **이 저장소의 `main` 은 매일
07:30 / 18:30 KST 에 GitHub Actions 가 그대로 실행해 실제 메일을 발송하는 브랜치**이므로,
아래를 지킨다.

| # | 조건 |
|---|------|
| 1 | 밀기 전 `git fetch` 후 최신 `main` 위에서 작업한다 (다중 세션 충돌 방지) |
| 2 | `python -c "import monitor"` 가 통과하지 않으면 절대 밀지 않는다 |
| 3 | 발송 스케줄 직전(07:00~07:40 / 18:00~18:40 KST)에는 밀지 않는다 |
| 4 | 다른 세션의 미커밋 변경을 되돌리거나 함께 커밋하지 않는다 |
| 5 | 되돌릴 방법(직전 커밋 해시)을 확인한 뒤 민다 |

- 자동개발 큐(무인 실행)에는 이 허용이 **적용되지 않는다** — 규칙 3 원문 그대로 금지.

## 4. TASK 처리 규칙

| # | 규칙 |
|---|------|
| 1 | 1회 실행 시 기본 1개 TASK만 처리 |
| 2 | 실패한 TASK 때문에 전체 큐가 멈추지 않음 |
| 3 | 실패 TASK는 FAILED 또는 BLOCKED로 이동 |
| 4 | 자동 수정 가능한 실패는 FIX TASK 생성 |
| 5 | 다음 실행에서는 다음 PENDING TASK를 계속 처리 |
| 6 | 동일 TASK 무한 재시도 금지 |
| 7 | 동일 TASK는 최대 2회까지만 재시도 |
| 8 | BLOCKED TASK는 자동 재시도하지 않음 |

## 5. 실패 처리 규칙

| 상황 | 처리 |
|------|------|
| Secret 누락 | → BLOCKED |
| GitHub 권한 부족 | → BLOCKED |
| API Key 없음 | → BLOCKED |
| Mail credential 없음 | → BLOCKED |
| AI 응답 오류 | → FAILED_RETRY (최대 2회) |
| 문법검증 실패 | → FAILED + FIX TASK 생성 |
| 테스트 실패 | → FAILED + FIX TASK 생성 |
| 실제 이메일 발송 위험 감지 | → BLOCKED |
| 변경사항 없음 | → SKIPPED 또는 DONE |
| PR 중복 | → 기존 PR 링크 출력 |

## 7. 수정 가능 파일

자동개발 큐가 수정할 수 있는 파일:

```
docs/project/TASKS.md
docs/project/RULES.md
AGENTS.md
README.md
var/state/auto_dev_state.json
docs/project/done_tasks.md
docs/project/failed_tasks.md
docs/project/blocked_tasks.md
auto_dev/*
docs/autodev/LOOP_ENGINEERING_AUTO_DEV.md
scripts/*
.github/workflows/auto-dev-queue.yml
.github/workflows/monitor.yml
docs/project/mail_daily_reviews/*
```

## 7b. 매일 메일 발송 후 검수 (MDR)

발송 직후 `python scripts/mail_daily_review.py` 로 당일 메타를 검수하고,
`docs/project/mail_daily_reviews/context/ledger.jsonl` 에 append 한다.
규칙 정의: `docs/project/mail_daily_reviews/rules.md` (MDR-001… — L규칙 스타일).
상세 산출물: `var/reviews/YYYY-MM-DD/`. SMTP 추가 발송·Secret 출력 금지.
매일 체크(30초): `python scripts/mail_daily_review.py --json` → overall/fails 만 확인 후,
재발은 ledger + `ZERO_MISS_GUARDRAILS.md`(PR #218) 원칙 표로 좁힌다.

## 8. Loop Engineering 규칙

설계서: `docs/autodev/LOOP_ENGINEERING_AUTO_DEV.md`  
작업 자산: `auto_dev/loops.json`, `eval_rubric.md`, `exit_conditions.md`, `human_gates.md`

| # | 규칙 |
|---|------|
| 1 | 최적화 단위는 단일 프롬프트가 아니라 **루프(트리거·실행·검증·상태·종료)** |
| 2 | 종료 조건이 없는 루프에는 write 권한 부여 금지 |
| 3 | `scripts/loop_verify.py` 통과 전 DONE 선언 금지 |
| 4 | `AUTO_DEV_AGENT` 미설정 시 허위 DONE 금지 → `AWAITING_AGENT` (PENDING 유지) |
| 5 | L2 `accuracy-defect` / L3 `product-vision` 은 사람 게이트(G1/G3/G4) 전 코딩 금지 |
| 6 | 작업 자산 드리프트는 `--drift`로 점검하고, 변질 자산만 수정 |
| 7 | 사람 개입은 G1~G4만 (L1 무인 기본) |
| 8 | `AUTO_DEV_FORCE_DONE` 는 비상용(기본 금지). 슬롯 없으면 `AWAITING_AGENT` | 허위 DONE 회귀 방지 |
| 9 | `AUTO_DEV_SAFE_EXECUTOR` 기본 true — 문서 NOOP·허용 패치만 자동 DONE | 파서/핵심코드는 에이전트 |

## 9. 야간 자동개발 schedule 복구 체크리스트

GHA `auto-dev-queue.yml` 의 cron 을 다시 켜기 **전에** 모두 충족:

1. GitHub Secret `AUTO_DEV_PAT` 가 유효하고 `contents`/`pull-requests` 권한이 있다.
2. 워크플로에서 `AUTO_DEV_AGENT=true` 로 코딩 슬롯이 실제로 연결되어 있다 (아니면 AWAITING_AGENT만 반복).
3. `auto_dev/loop_config.json` → `trigger.schedule_enabled=true` 와 워크플로 `schedule:` 블록이 동시에 활성이다 (`loop_verify --drift` D5).
4. `docs/project/TASKS.md` PENDING **또는** 루트 `TASK.md` 의 `[ ]`/`[~]` 가 비어 있지 않다 (TASK.md 우선, user-priority TASK 다음).
5. `python3 scripts/auto_dev_overnight_ready.py --require-live` 가 exit 0 이다.
6. `python3 scripts/outstanding_dev_audit.py --strict` 가 UNIQUE_CANDIDATE 없이 통과한다.

위가 하나라도 실패하면 cron 을 복구하지 말고 `workflow_dispatch` / 로컬 에이전트로 PENDING 을 소진한다.

## 10. Agent 순환 호출 · Polling Timeout 가드

| # | 규칙 |
|---|------|
| 1 | 동일 TASK에서 동일 역할 agent(orchestrator/runner/verifier/fixer 등) 호출은 최대 1회. 허용 예: orchestrator → verifier → fixer → verifier. 두 번째 verifier에서도 동일 failure signature(에러 해시)면 같은 방식으로 다시 시도하지 않고 BLOCKED 종료 — 동일 failure signature 재시도는 최대 2회(§4-7, exit_conditions.md `FAIL_NO_PROGRESS`와 동일 원칙) |
| 2 | `verifier → fixer → verifier → fixer → verifier ...` 형태의 무한 핑퐁 금지 |
| 3 | 배포 상태·외부 API 등 polling이 필요한 코드를 추가할 경우 반드시 유한 조건(MAX_POLLS, TOTAL_TIMEOUT)을 둔다. `while status != success: check()` 같은 polling timeout 없는 무한 대기 금지 |
| 4 | 하나의 검증 실패로 전체 체인(coding-fix → gate-repair → coverage-sentinel …)을 처음부터 재실행하지 않는다. 실패한 단계만 제한적으로 재검증한다 |

