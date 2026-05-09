# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Vercel 배포 기반 Mail 프로젝트. 정부지원사업·해외전시회 공고를 자동 수집하고, 조건에 맞는 공고를 이메일로 발송하는 시스템.

### 프로젝트 구조

- `monitor.py` — 핵심 모니터링 엔진 (수집 → 중복제거 → 필터 → AI 요약 → 발송)
- `streamlit_app.py` — 관리 대시보드 UI (소스/그룹/설정 관리)
- `test_monitor.py` — pytest 기반 단위 테스트
- `test_fetch.py` — 실제 HTTP 요청 통합 테스트

### Running Tests

- **Unit tests (no API keys needed):** `python3 -m pytest test_monitor.py -v`
- **Integration fetch tests (needs BIZINFO_API_KEY):** `python3 test_fetch.py`

### Key Gotchas

- `monitor.py`는 모듈 임포트 시 `os.environ["BIZINFO_API_KEY"]` 등을 읽으므로, 환경변수 미설정 시 import 단계에서 크래시 발생. 테스트 파일은 `os.environ.setdefault(...)`로 우회.
- `python3` 사용 (일부 환경에서 `python` 심링크 없음)
- JSON 설정 파일(`sites.json`, `groups.json`, `settings.json`)이 데이터 저장소 — DB 불필요.
- `seen_ids.json`은 런타임 생성, git-ignored.

### 환경변수 (Vercel / GitHub)

| 변수 | 용도 |
|------|------|
| `OPENAI_API_KEY` | AI 기능 |
| `ANTHROPIC_API_KEY` | Claude AI 요약 (선택) |
| `BIZINFO_API_KEY` | 기업마당 API |
| `GMAIL_ADDRESS` | 메일 발신 주소 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 |
| `SMTP_HOST` | SMTP 서버 (기본: smtp.gmail.com) |
| `SMTP_PORT` | SMTP 포트 (기본: 465) |
| `IMAP_HOST` | IMAP 서버 (선택) |
| `IMAP_PORT` | IMAP 포트 (선택) |
| `AUTO_DEV_PAT` | GitHub PR 생성용 PAT |

### Auto Dev Queue

방치형 자동개발 큐 인프라:

- **TASKS.md** — 작업 큐 (PENDING/RUNNING/DONE/FAILED/BLOCKED)
- **RULES.md** — Vercel Mail 프로젝트 전용 안전규칙
- **scripts/auto_dev_queue.py** — 큐 실행기
- **auto_dev_state.json** — 실행 상태 추적
- **.github/workflows/auto-dev-queue.yml** — GHA 워크플로우 (수동 실행 또는 스케줄)

큐 실행: `python3 scripts/auto_dev_queue.py`

**핵심 안전규칙:**
- 기존 앱 파일(`monitor.py`, `streamlit_app.py`) 수정 금지
- 실제 이메일 발송 금지 (dry-run/mock/draft만 허용)
- Mail 관련 Secret은 발송 기능 검증 전까지 미사용
- Secret/API Key 로그 출력 금지
- 자동 merge 금지 (PR 생성까지만)
