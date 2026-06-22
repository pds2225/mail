# Streamlit Cloud 배포 가이드

`streamlit_app.py`(수출지원 모니터링 관리 대시보드)를 Streamlit Community Cloud에
올리는 절차입니다. 대시보드 자체는 **시크릿 없이도 구동**되며, `▶ 실행` 탭에서
`monitor.py`를 호출할 때만 API 키가 필요합니다.

## 1. 사전 확인 (이미 레포에 준비됨)
- `streamlit_app.py` — 엔트리포인트 (5개 탭: 소스/그룹/설정/실행/검수)
- `requirements.txt` — 의존성 (streamlit 등)
- `.streamlit/config.toml` — 테마·서버 기본값
- 시크릿(API 키)은 커밋하지 않으며, 아래 3단계에서 Cloud Secrets로 등록합니다.

검증: 로컬에서 아래로 정상 구동 확인됨.
```bash
python -m streamlit run streamlit_app.py
```

## 2. Streamlit Cloud에서 1회 연결 (사용자가 직접)
1. https://share.streamlit.io 에 GitHub 계정으로 로그인
2. **Create app → Deploy a public app from GitHub** 선택
3. 설정값:
   - **Repository**: `pds2225/mail`
   - **Branch**: `claude/mail-test-personal-atz17w` (또는 머지 후 `main`)
   - **Main file path**: `streamlit_app.py`
4. **Deploy** 클릭 → 빌드 후 `https://<앱이름>.streamlit.app` 으로 공개됨

> 이후 해당 브랜치에 push할 때마다 자동 재배포됩니다.

## 3. 시크릿 등록 (실행 탭을 쓰려면)
앱 → **Settings → Secrets** 에 아래를 붙여넣고 저장:
```toml
BIZINFO_API_KEY   = "..."
ANTHROPIC_API_KEY = "..."
GMAIL_ADDRESS     = "you@gmail.com"
GMAIL_APP_PASSWORD = "..."
```
Cloud는 시크릿을 **환경변수로도 주입**하므로, 서브프로세스로 실행되는
`monitor.py`(`os.environ`으로 키를 읽음)가 정상 동작합니다.

## 4. 알려진 클라우드 제약
- **파일 영속성 없음**: `sites.json` / `groups.json` / `settings.json` 수정은
  컨테이너 재시작 시 초기화됩니다(에페메럴 FS). 영구 보관이 필요하면 변경분을
  GitHub에 커밋하거나 외부 저장소(DB)로 옮겨야 합니다.
- **메일 발송(SMTP)**: Streamlit Cloud는 아웃바운드 SMTP를 보장하지 않습니다.
  발송이 막히면 API 기반 발송(예: Resend/SendGrid)으로 전환을 검토하세요.
- **실행 탭 서브프로세스**: `monitor.py`는 시크릿이 등록돼야 import 단계 통과합니다.
