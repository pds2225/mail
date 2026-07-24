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
| 3 | main 브랜치 직접 수정 금지 |
| 4 | .env 파일 수정 금지 |
| 5 | 대규모 리팩토링 금지 |
| 6 | 불필요한 패키지 설치 금지 |

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
docs/LOOP_ENGINEERING_AUTO_DEV.md
scripts/*
.github/workflows/auto-dev-queue.yml
```

## 8. Loop Engineering 규칙

설계서: `docs/LOOP_ENGINEERING_AUTO_DEV.md`  
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
