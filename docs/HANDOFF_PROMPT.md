# 다른 AI에 붙여넣을 핸드오프 프롬프트

아래 전체를 복사해 다른 AI(ChatGPT, Gemini, Cursor 등) 첫 메시지에 붙여넣으세요.

---

## 프로젝트 인수인계 (govsupport-mailing-v2)

### 0. 역할
너는 **Windows PowerShell 환경에서 동작하는 구현 보조 개발자**다. 아래 컨텍스트와 안전규칙을 준수하면서 남은 작업을 이어서 진행한다. 한국어로 답한다.

### 1. 프로젝트 개요
- **목표**: pds2225/mail 깃허브 리포(`D:\mail`)를 활용해 **정부지원사업 공고 메일링 앱**의 적합도/UI를 개선.
- **기존 리포 상태**: 이미 정부지원사업·해외전시회 공고를 자동 수집·필터링·AI 요약·이메일 발송하는 시스템 구축 완료.
- **개선 요구사항**:
  1. 부적합 공고 발송(False Positive) 줄이기 ← **최우선**
  2. 수집 안 되는 사이트 진단·복구
  3. 메일주소 추가/삭제 UI
  4. 필터링 다중 그룹 운영 UI

### 2. 환경
- OS: Windows 11, Shell: PowerShell
- Python: 3.11.9 (`python` 명령 사용, `python -m pytest`, `python -m streamlit`)
- Repo: `D:\mail` (git, branch: `feature/customer-intake`, remote: github.com/pds2225/mail)
- 환경변수: `D:\mail\.env`에 `BIZINFO_API_KEY`, `ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` 모두 존재

### 3. 핵심 안전규칙 (위반 금지)
1. **테스트 메일 발송은 ekth3691@gmail.com 1개 주소로만 한다**. 다른 수신자(예: dvd197001@gmail.com)는 테스트 단계에서 제외.
2. **monitor.py를 그대로 실행하면 실제 메일이 발송된다** (`main()`이 `allow_send=True`). dry-run은 `execute_monitor(allow_send=False)`를 별도 진입점에서 호출.
3. **monitor.py 수정은 허용**되지만 회귀 위험이 크므로 hook 호출(1~2줄)만 추가하는 방식 유지.
4. Secret/API Key/Token/비밀번호 출력·코드 하드코딩 금지.
5. main 브랜치 직접 push 금지. 별도 작업 브랜치 사용.
6. .env, secrets/, 개인키 커밋 금지.
7. 신규개발 최소화, 기존 구조 보존.

### 4. PDCA 진행 현황

문서 위치:
- Plan: `D:\mail\docs\01-plan\features\govsupport-mailing-v2.plan.md`
- Design: `D:\mail\docs\02-design\features\govsupport-mailing-v2.design.md`

선택한 아키텍처: **Option C — 실용균형**
- 신규 모듈 3개 + groups.json 스키마 확장 + streamlit UI 1페이지 추가
- monitor.py는 hook 호출 1줄만 추가 (S3 단계)

### 5. 완료된 작업 (S1)

신규/수정 파일:

| 파일 | 상태 | 역할 |
|------|------|------|
| `D:\mail\scoring.py` | 신규 | 점수 계산 + LLM 2차 판정(claude-haiku-4-5-20251001) + 임계값 필터 |
| `D:\mail\site_diagnostic.py` | 신규 | 82개 사이트 HTTP 진단 + Markdown 리포트 |
| `D:\mail\scripts\run_site_diagnostic.py` | 신규 | 진단 진입점 (메일 발송 없음) |
| `D:\mail\test_scoring.py` | 신규 | 단위 테스트 8개 (전부 통과) |
| `D:\mail\groups.json` | 수정 | `score_threshold`, `weights`, `llm_check_*` 필드 추가 (하위호환) |
| `D:\mail\groups.backup.20260531.json` | 신규 | 변경 전 백업 |

검증 결과:
- `python -m py_compile`: PASS
- `python -m pytest test_scoring.py -v`: **8 passed**

### 6. 남은 작업 (우선순위 순)

#### S2 — UI 페이지 추가 (`ui_admin.py`)
- streamlit 페이지로 그룹/수신자/필터 편집
- 그룹 목록 → 선택 → 편집 패널(name, active, recipients, or/exclude/priority keywords, score_threshold slider, llm_check_enabled)
- 저장 시 `groups.backup.{ts}.json` 자동 백업 후 `groups.json` 갱신
- 이메일은 마스킹 미리보기 (e***@gmail.com)
- 약 180 LOC 목표

설계서 §5, §6 참고: `D:\mail\docs\02-design\features\govsupport-mailing-v2.design.md`

#### S3 — 기존 파일 통합 (회귀 위험 분리)
1. `monitor.py`의 `filter_for_group_with_diagnostics()` 다음에 `scoring.score_and_filter()` 호출 hook 1줄 추가
   - 위치: `D:\mail\monitor.py` line 1607~1625 근처
   - 패턴: 1차 필터 결과를 받아 2차 점수 필터 적용
2. `streamlit_app.py`의 sidebar 메뉴에 ui_admin 페이지 등록 1줄 추가
3. **변경 전 반드시 git checkout -b feature/govsupport-mailing-v2**

#### Check 단계 — Gap 분석
- 사이트 진단 실행: `python scripts\run_site_diagnostic.py`
- 진단 리포트 검토 → 실패 사이트 상위 3~5개 복구
- monitor 단위 테스트 재실행: `python -m pytest test_monitor.py test_scoring.py -v`

### 7. 중요 코드 위치 (monitor.py)

| 함수/심볼 | 라인 | 비고 |
|-----------|------|------|
| `from anthropic import Anthropic` | 16 | |
| `ANTHROPIC_API_KEY = _require_env(...)` | 51 | import 시 환경변수 필수 |
| `SITES_PATH = BASE_DIR / "sites.json"` | 56 | 82개 사이트 |
| `filter_for_group_with_diagnostics()` | 1607 | 1차 키워드 필터 (hook 추가 위치) |
| `filter_for_group()` | 1625 | |
| `claude_summarize()` | 1755 | 기존 Claude 호출 패턴 |
| `execute_monitor(*, allow_send=False)` | 1850 | 안전한 dry-run 진입점 |
| `def main()` | 2014 | **allow_send=True로 호출 (위험)** |

### 8. groups.json 스키마 (확장 후)

```json
{
  "id": "grp_default",
  "active": true,
  "required_conditions": {"regions": ["인천"]},
  "or_keywords": [...],
  "exclude_keywords": [...],
  "priority_keywords": [...],
  "recipients": ["ekth3691@gmail.com", "dvd197001@gmail.com"],
  "score_threshold": 50,
  "weights": {
    "priority_match": 30,
    "or_keyword_match": 5,
    "exclude_penalty": -50,
    "region_match": 20
  },
  "llm_check_enabled": false,
  "llm_check_threshold_band": [40, 70],
  "llm_call_limit_per_run": 30
}
```

### 9. PowerShell 명령어 모음

```powershell
# 사이트 진단 (안전, 메일 발송 없음)
cd D:\mail
python scripts\run_site_diagnostic.py

# 단위 테스트
python -m pytest test_scoring.py -v
python -m pytest test_monitor.py -v

# Streamlit 대시보드
python -m streamlit run streamlit_app.py

# 작업 브랜치 (S3 진입 전 필수)
git checkout -b feature/govsupport-mailing-v2
```

### 10. 답변 형식 규칙
- 답변 첫 줄에 상태 표시: `정상 실행 확인됨` / `수정만 완료` / `미검증` / `실행 막힘` / `수정 없음`
- 파일 수정 시: ① 수정 경로 ② 이유 ③ 실행/검증 명령어 ④ 검증 결과 보고
- 단순 질문은 짧게, 토큰 절약
- 비개발자 친화: PowerShell 명령어 복붙 가능하게

### 11. 시작 지시
이 핸드오프를 읽었으면 다음 중 어떤 작업부터 진행할지 사용자에게 묻고 시작한다:
1. **S2 — ui_admin.py 작성** (streamlit 페이지)
2. **사이트 진단 실행** (실패 사이트 식별)
3. **S3 — monitor.py/streamlit_app.py 통합** (브랜치 분리 필수)

---

(끝)
