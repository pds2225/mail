# 수출·지원사업 공고 모니터링 시스템

정부지원사업·해외전시회 공고를 자동 수집하고, 조건에 맞는 공고를 이메일로 발송하는 시스템입니다.

## 주요 기능

- **80개 소스** 자동 수집 (기업마당·KITA·IRIS·NIPA·KOCCA·인천TP 등)
- **중복 제거** — 통합포털(기업마당 등)과 주관기관 중복 시 주관기관 우선 유지
- **날짜 필터** — 어제(D-1) 올라온 공고만 수신
- **그룹별 발송** — 지역·키워드·지원유형 조건을 그룹으로 설정, 수신자별 맞춤 발송
- **Claude AI 요약** — 공고 선별 및 요약
- **Streamlit 관리 UI** — 소스·그룹·키워드 웹에서 관리

## 설치

```bash
pip install -r requirements.txt
```

## 환경변수 설정

`.env.example`을 복사해서 `.env` 파일을 만들고 실제 키를 입력합니다.

```bash
cp .env.example .env
# .env 파일을 열어서 키 입력
```

```
BIZINFO_API_KEY=기업마당_API_키
ANTHROPIC_API_KEY=Claude_API_키
GMAIL_ADDRESS=발신_Gmail_주소
GMAIL_APP_PASSWORD=Gmail_앱비밀번호
```

> **Gmail 앱비밀번호** 발급: Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호

## 실행

### 모니터링 실행 (메일 발송)
```bash
# Windows
run_monitor.bat

# Mac/Linux
python monitor.py
```

### 관리 UI
```bash
# Windows
run_dashboard.bat

# Mac/Linux
python -m streamlit run streamlit_app.py
# 브라우저에서 http://localhost:8501 접속
```

## 설정 파일

| 파일 | 설명 |
|------|------|
| `sites.json` | 수집할 사이트 목록 (UI에서 편집 가능) |
| `groups.json` | 그룹별 조건 + 수신자 (UI에서 편집 가능) |
| `settings.json` | 날짜필터·원본전체 메일 설정 |
| `seen_ids.json` | 중복방지 DB (자동 생성, Git 제외) |

## 관리 UI 탭 구성

| 탭 | 기능 |
|------|------|
| 📡 소스 관리 | 사이트 추가/수정/삭제, URL 자동 분석 |
| 👥 그룹 관리 | 지역·키워드·지원유형·수신자 설정 |
| ⚙️ 설정 | 날짜필터·원본전체 메일 설정 |
| ▶ 실행 | 현황 확인 + 즉시 실행 |

## 자동 실행 설정 (매일)

**Windows 작업 스케줄러:**
1. 작업 스케줄러 열기
2. 기본 작업 만들기
3. 트리거: 매일 오전 8시
4. 동작: `D:\auto_mail\run_monitor.bat` 실행

## 수집 소스 현황

| 구분 | 사이트 수 |
|------|---------|
| 전용 크롤러 (IRIS·MSS·NIPA·KITA·KOCCA·ITP 등) | 14개 |
| 표준 HTML 크롤러 | 66개 |
| **합계 (활성)** | **70개** |

> 일부 정부기관 사이트는 서버 IP 차단 정책으로 인해 개인 PC에서 실행 시 정상 동작합니다.
