# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Vercel 배포 기반 Mail 프로젝트. 정부지원사업·해외전시회 공고를 자동 수집하고, 조건에 맞는 공고를 이메일로 발송하는 시스템.

### 프로젝트 구조

| 파일 | 역할 |
|------|------|
| `monitor.py` | 핵심 모니터링 엔진 (수집 → 중복제거 → 필터 → AI 요약 → 발송) |
| `streamlit_app.py` | 관리 대시보드 UI (소스/그룹/설정 관리) |
| `test_monitor.py` | pytest 기반 단위 테스트 |
| `test_fetch.py` | 실제 HTTP 요청 통합 테스트 |
| `sites.json` | 수집 소스 설정 |
| `groups.json` | 그룹별 필터/수신자 설정 |
| `settings.json` | 전역 설정 |

### Running Tests

- **Unit tests:** `python3 -m pytest test_monitor.py -v` (API 키 불필요)
- **Integration tests:** `python3 test_fetch.py` (BIZINFO_API_KEY 필요)

### Key Gotchas

- `monitor.py`는 모듈 임포트 시 `os.environ["BIZINFO_API_KEY"]` 등을 읽으므로 환경변수 미설정 시 import 단계에서 크래시. 테스트 파일은 `os.environ.setdefault(...)`로 우회.
- `python3` 사용 (일부 환경에서 `python` 심링크 없음)
- JSON 설정 파일이 데이터 저장소 — DB 불필요.
- `seen_ids.json`은 런타임 생성, git-ignored.

### 환경변수

| 변수 | 용도 | 비고 |
|------|------|------|
| `BIZINFO_API_KEY` | 기업마당 API | monitor.py 필수 |
| `ANTHROPIC_API_KEY` | Claude AI 요약 | monitor.py 필수 |
| `GMAIL_ADDRESS` | 메일 발신 주소 | monitor.py 필수 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 | monitor.py 필수 |
| `OPENAI_API_KEY` | AI 기능 (향후) | 선택 |
| `SMTP_HOST` / `SMTP_PORT` | SMTP 서버 | 선택 |
| `IMAP_HOST` / `IMAP_PORT` | IMAP 서버 | 선택 |
| `AUTO_DEV_PAT` | GitHub PR 생성용 PAT | Auto Dev Queue용 |

### Auto Dev Queue

방치형 자동개발 큐 인프라:

| 파일 | 역할 |
|------|------|
| `TASKS.md` | 작업 큐 (PENDING/RUNNING/DONE/FAILED/BLOCKED) |
| `RULES.md` | Vercel Mail 프로젝트 전용 안전규칙 |
| `scripts/auto_dev_queue.py` | 큐 실행기 (preflight, 상태관리, dry-run) |
| `auto_dev_state.json` | 실행 상태 추적 |
| `.github/workflows/auto-dev-queue.yml` | GHA 워크플로우 |

실행: GitHub Actions → "Auto Dev Queue" → "Run workflow"

**핵심 안전규칙:**
- 기존 앱 파일(`monitor.py`, `streamlit_app.py`) 수정 금지
- Secret/API Key 로그 출력 금지

### Running Services (Cloud)

- **Streamlit dashboard:** `python3 -m streamlit run streamlit_app.py --server.headless true` (headless flag required in Cloud VMs; opens on port 8501)
- **monitor.py:** Requires all 4 env vars (`BIZINFO_API_KEY`, `ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`) set before import. Unit tests mock these automatically.
- **Integration tests (network):** Many Korean gov sites (기업마당, KOTRA 등) use TLS configurations that fail with `UNEXPECTED_EOF_WHILE_READING` in Cloud VMs. ~10/39 html_table sources and KITA succeed; others may fail due to network/SSL restrictions. This does not indicate a code bug.
