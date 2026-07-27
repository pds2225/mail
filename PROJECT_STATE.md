# Mail 프로젝트 공유 상태

> 이 파일은 GitHub에 올리는 공유용 작업 상태입니다.
> 로컬 자동복원용 메모는 `RESUME.md`에 따로 두며, `RESUME.md`는 `.gitignore` 대상입니다.
> Secret, API Key, 비밀번호, `.env` 값은 이 파일에 적지 않습니다.

## 현재 기준

- 기준일: 2026-06-17
- 저장소: `D:\mail`
- 원격 저장소: `https://github.com/pds2225/mail.git`
- 현재 브랜치: `main`
- 현재 커밋: `a77c1f4`
- 동기화 상태: `main`과 `origin/main`이 같은 커밋

## 프로젝트 목적

정부지원사업과 해외전시회 공고를 자동 수집하고, 조건에 맞는 공고를 이메일로 보내는 Vercel 기반 Mail 프로젝트입니다.

주요 파일:

| 파일 | 역할 |
|---|---|
| `monitor.py` | 공고 수집, 중복 제거, 필터, AI 요약, 메일 발송 흐름 |
| `streamlit_app.py` | 관리 대시보드 |
| `config/sites.json` | 수집 대상 사이트 설정 |
| `config/groups.json` | 그룹별 필터와 수신자 설정 |
| `config/settings.json` | 전체 설정 |
| `docs/project/RULES.md` | 메일 발송과 자동개발 안전규칙 |
| `AGENTS.md` | 이 repo에서 Codex가 따라야 할 작업 규칙 |

## 공유해야 할 규칙

- `AGENTS.md`와 `docs/project/RULES.md`를 먼저 확인합니다.
- 기존 앱 핵심 파일인 `monitor.py`, `streamlit_app.py`는 임의로 크게 바꾸지 않습니다.
- 실제 이메일 발송은 사용자 명시 승인 없이 하지 않습니다.
- 테스트나 자동개발에서는 preview, draft, dry-run을 우선합니다.
- Secret, API Key, 비밀번호, `.env` 값은 코드, 로그, 문서에 남기지 않습니다.
- `RESUME.md`는 로컬 이어가기 메모라서 GitHub 공유 대상이 아닙니다.

## 최근 완료된 주요 작업

- 시크릿 단일 허브를 `D:\_secure\.env.shared` 중심으로 정리한 이력이 있습니다.
- 공고 정확도 개선 PR들이 병합된 이력이 있습니다.
- 행정고지 같은 불필요한 공고를 줄이는 필터가 반영된 이력이 있습니다.
- 집중 모니터링 워치리스트 기능이 반영된 이력이 있습니다.
- 사이트 파서가 깨졌는지 확인하는 녹화-재생 테스트 하네스 1차가 반영된 이력이 있습니다.

## 현재 로컬에서 Git에 아직 안 올라간 파일

- `PROJECT_STATE.md`: 이번에 만든 Git 공유용 상태 파일입니다.
- `README.ko.md`: 로컬에만 있는 새 파일입니다. 내용 확인 후 별도 커밋 여부를 결정해야 합니다.
- `_ai_diag_tmp.py`: 로컬에만 있는 임시 진단 파일로 보입니다. 출처 확인 전에는 커밋하지 않습니다.
- `RESUME.md`: `.gitignore` 대상이므로 GitHub에 올리지 않는 로컬 자동복원 파일입니다.

## 다음 작업 후보

1. K스타트업(`fetch_kstartup`) 녹화-재생 테스트 확장
   - 공공 공고 PBC010과 민간 공고 PBC020이 둘 다 수집되는지 검증합니다.

2. AI 공고 1회 발송
   - 실제 발송 작업입니다.
   - 수신자 제한, 날짜/중복 조건, dry-run 확인 후 사용자 명시 승인으로만 진행합니다.

3. recall 보강
   - 지원공고 키워드와 AI/SaaS 그룹 키워드를 보강합니다.
   - 상시모집 같은 마감 표현을 더 안전하게 처리합니다.

4. Vercel 웹 관리 화면 개선
   - `web/` 영역에서 sites/recipients 설정을 읽기전용이 아니라 편집 가능하게 만드는 작업입니다.
   - GitHub의 JSON 설정 파일을 원본으로 삼아야 합니다.

## 재개 시 확인 명령

```powershell
cd D:\mail
git status --short --branch
Get-Content .\AGENTS.md -Raw
Get-Content .\docs/project/RULES.md -Raw
Get-Content .\PROJECT_STATE.md -Raw
```

## 커밋 전 체크

```powershell
cd D:\mail
git status --short
git diff -- PROJECT_STATE.md
git check-ignore -v -- PROJECT_STATE.md
```

`git check-ignore`에서 아무 출력이 없으면 `PROJECT_STATE.md`는 Git에 올릴 수 있는 파일입니다.
