# 고객사 서류 OCR → Google Sheets (실사용 가이드)

메일 모니터링(`monitor.py`)과 **완전히 별개**입니다.
고객사 서류(PDF/PNG/JPG/JPEG)를 고정 inbox에서 읽어 OCR → 필드 추출 → 보고서/Google Sheets 기록까지 처리합니다.

> 중요: 기본 PowerShell 스크립트는 `--dry-run auto`로 실행됩니다. `.env`에 Google Sheets 설정이 완비되어 있으면 실제 시트에 기록하고, Sheets 설정이 없으면 dry_run으로 보고서만 생성합니다. OCR은 별도로 CLOVA 설정이 있으면 실제 OCR, 없으면 Mock OCR을 사용합니다.

---

## 1. 처음 한 번만 (설치)

### 1-1. Python 패키지

PowerShell에서:

```powershell
cd D:\mail
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 1-2. 환경변수 파일 (.env)

```powershell
cd D:\mail
copy .env.example .env
notepad .env
```

| 변수 | 언제 필요? | 넣는 값 |
|------|------------|---------|
| `GOOGLE_SHEET_ID` | **실제 시트 기록** 시 | 스프레드시트 URL의 `/d/` ~ `/edit` 사이 ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | **실제 시트 기록** 시 | `D:\mail\secrets\google_service_account.json` |
| `CLOVA_OCR_URL` | **실제 OCR** 시 | NAVER CLOVA Document OCR Invoke URL |
| `CLOVA_OCR_SECRET` | **실제 OCR** 시 | `X-OCR-SECRET` 값 |

- **미리보기만** 할 때: `.env` 없어도 됨 (Mock OCR + dry_run)
- **실제 OCR**: `CLOVA_OCR_URL` + `CLOVA_OCR_SECRET` 둘 다
- **실제 Sheets**: `GOOGLE_SHEET_ID` + 서비스 계정 JSON

### 1-3. Google 서비스 계정 JSON

1. Google Cloud에서 서비스 계정 키(JSON) 다운로드  
2. 아래 경로에 저장 (폴더는 자동 생성됨):

```
D:\mail\secrets\google_service_account.json
```

3. Google 스프레드시트 → **공유** → 서비스 계정 이메일에 **편집자** 권한

자세히: [secrets/README.md](../secrets/README.md)

### 1-4. Google 스프레드시트

- 스프레드시트 하나 준비
- `.env`의 `GOOGLE_SHEET_ID`에 ID 입력
- 시트(탭) `고객사_마스터DB`, `제출서류DB`, `실행로그` 가 없으면 **첫 실제 기록 시 자동 생성**됩니다.

---

## 2. 실행 모드 먼저 이해

| 모드 | 실행 방법 | 동작 |
|------|----------|------|
| 자동(`auto`) | `run_customer_intake_once.ps1`, `run_customer_intake_watch.ps1` | Sheets 설정이 있으면 실제 기록, 없으면 dry_run |
| 강제 미리보기 | `python -m customer_intake.watcher --once --dry-run true` | OCR/추출/보고서만 수행, Sheets 미기록 |
| 실제 기록 요청 | `run_customer_intake_once_real.ps1` 또는 `--dry-run false` | 실행 전 확인을 받고, Sheets 설정이 완비된 경우만 기록 |

`--dry-run false`를 요청해도 `GOOGLE_SHEET_ID` 또는 서비스 계정 JSON이 없으면 중단하지 않고 dry_run으로 계속 처리합니다. 누락 항목은 콘솔과 보고서에 표시됩니다.

---

## 3. 매일 쓰는 방법 (3단계)

### ① 파일 넣기

사업자등록증 PDF/이미지를 복사:

```
D:\customer_intake_inbox
```

(폴더 없으면 실행 시 자동 생성)

### ② 실행

**자동 모드(기본)** — 설정이 없으면 미리보기, 설정이 있으면 Sheets 기록:

```powershell
cd D:\mail
.\run_customer_intake_once.ps1
```

**계속 감시** — inbox에 넣을 때마다 자동 처리:

```powershell
cd D:\mail
.\run_customer_intake_watch.ps1
```

**항상 미리보기만** — Sheets에 쓰지 않고 결과만 확인:

```powershell
cd D:\mail
python -m customer_intake.watcher --once --dry-run true
```

**실제 Google Sheets 기록 요청**:

```powershell
cd D:\mail
.\run_customer_intake_once_real.ps1
```

(실행 전 경고 + `Y` 입력 필요)

### ③ 결과 확인

| 확인 | 위치 |
|------|------|
| 성공한 파일 | `D:\customer_intake_done` |
| 실패한 파일 | `D:\customer_intake_failed` |
| 보고서 | `D:\customer_intake_reports\customer_intake_*.md` |
| 시트 데이터 | Google 스프레드시트 (Sheets 설정이 있고 dry_run=false인 실행 시) |

---

## 4. OCR 모드 표시

실행 시작 시 콘솔에 표시됩니다.

| 표시 | 의미 |
|------|------|
| `[OCR] Mock OCR (테스트)` | `.env`에 CLOVA 미설정 → 샘플 JSON으로 추출 테스트 |
| `[OCR] 실제 CLOVA OCR` | CLOVA API로 실제 문서 인식 |

---

## 5. 입력 파일과 처리 규칙

| 항목 | 규칙 |
|------|------|
| 지원 확장자 | `.pdf`, `.png`, `.jpg`, `.jpeg` |
| 탐색 범위 | inbox 폴더 **직하위 파일만** 처리 (`scan_inbox`) |
| 처리 순서 | 파일명에 `사업자등록증`, `사업자등록`, `business_registration`, `biz_reg` 포함 시 우선 |
| 복사 중 파일 | 크기가 안정될 때까지 대기 후 처리 |
| 중복 파일 | 파일 내용 SHA-256 기준으로 `processed_files.json`에 기록, 재투입 시 이전 상태에 따라 done/failed로 이동 |
| 결과 파일명 충돌 | 같은 이름이 있으면 `_1`, `_2` suffix를 붙여 이동 |

추출기는 사업자등록번호, 법인등록번호, 날짜 형식을 정규화합니다. 필수 항목(고객사명, 대표자명, 사업자등록번호, 사업장주소, 개업일, 업태, 종목)이 빠지면 `확인상태=확인필요`로 남기고, 임의로 값을 추정하지 않습니다.

---

## 6. 고정 폴더

| 경로 | 용도 |
|------|------|
| `D:\customer_intake_inbox` | 넣는 곳 |
| `D:\customer_intake_done` | 성공 |
| `D:\customer_intake_failed` | 실패 |
| `D:\customer_intake_reports` | Markdown 보고서 |

아래 환경변수로 경로를 바꿀 수 있습니다.

| 환경변수 | 기본값 |
|----------|--------|
| `CUSTOMER_INTAKE_INBOX` | `D:\customer_intake_inbox` |
| `CUSTOMER_INTAKE_DONE` | `D:\customer_intake_done` |
| `CUSTOMER_INTAKE_FAILED` | `D:\customer_intake_failed` |
| `CUSTOMER_INTAKE_REPORTS` | `D:\customer_intake_reports` |

---

## 7. Python 직접 실행

```powershell
cd D:\mail
python -m customer_intake.watcher --once --dry-run auto
python -m customer_intake.watcher --once --dry-run true
python -m customer_intake.watcher --once --dry-run false
python -m customer_intake.watcher --watch --dry-run auto
```

CLI 제약:

- `--once`와 `--watch` 중 하나는 반드시 선택합니다.
- `--dry-run` 값은 `auto`, `true`, `false`를 사용합니다.
- `auto`는 Sheets 자격 증명 상태에 따라 실제 기록 여부를 결정합니다.

---

## 8. Google Sheets 컬럼

### 고객사_마스터DB

고객사명, 대표자명, 사업자등록번호(**중복 시 신규 행 안 함**), 법인등록번호, 사업장주소, 개업일, 업태, 종목, 과세유형, 확인상태, 확인필요사항, 추출일시

### 제출서류DB

고객사명, 사업자등록번호, 서류종류, 파일명, 파일경로, 추출일시, 확인상태, 확인필요사항

### 실행로그

실행일시, 입력경로, dry_run, 처리파일수, 마스터신규, 마스터스킵, 서류기록수, 오류수, 보고서경로, 비고

Sheets 처리 제약:

- 탭이 없으면 `고객사_마스터DB`, `제출서류DB`, `실행로그`를 자동 생성합니다.
- 기존 1행 헤더가 기대값과 다르면 기존 헤더를 유지하고 경고만 남깁니다.
- `고객사_마스터DB`는 사업자등록번호 숫자만 비교해 중복 신규 행을 막습니다.
- 사업자등록번호가 `확인필요`인 행은 중복 키로 보지 않습니다.

---

## 9. 환경변수 누락 시

환경변수가 부족해도 기본적으로 중단하지 않습니다.

| 누락 항목 | 폴백 |
|-----------|------|
| `CLOVA_OCR_URL` 또는 `CLOVA_OCR_SECRET` | `customer_intake/mock_ocr_result.json` 사용 |
| `GOOGLE_SHEET_ID` 또는 서비스 계정 JSON | dry_run으로 계속 처리 |

누락 항목은 시작 배너와 Markdown 보고서의 `환경변수 (.env) 미설정 항목`에 기록됩니다.

---

## 10. 감시 모드 운영 메모

`run_customer_intake_watch.ps1`는 `D:\customer_intake_reports\watch.log`에 로그를 추가하고, 시작 시 inbox에 남아 있는 파일을 먼저 한 번 처리합니다.

- `watchdog` 설치 시 OS 파일 이벤트를 사용합니다.
- `watchdog`을 import할 수 없으면 폴더 스냅샷 비교 방식으로 폴링합니다.
- 관련 튜닝값: `CUSTOMER_INTAKE_DEBOUNCE_SEC`, `CUSTOMER_INTAKE_FALLBACK_POLL_SEC`, `CUSTOMER_INTAKE_STABLE_SEC`, `CUSTOMER_INTAKE_STABLE_RETRIES`

진단:

```powershell
cd D:\mail
.\doctor_customer_intake.ps1
```

확인 항목: `.env`, Python 경로, 고정 폴더, 작업 스케줄러 `MailRepo_CustomerIntakeWatch`, `watch.log` 최근 내용.

---

## 11. 실사용 전 최종 체크리스트

- [ ] `pip install -r requirements.txt` 완료
- [ ] `D:\customer_intake_inbox`에 테스트 PDF 1건 넣고 `python -m customer_intake.watcher --once --dry-run true` 성공
- [ ] 보고서·done 폴더 이동 확인
- [ ] Mock → CLOVA 실 OCR 전환 후 샘플 1건 재검수
- [ ] `.env` + `secrets\google_service_account.json` 준비
- [ ] 스프레드시트에 서비스 계정 **편집 권한**
- [ ] `.\run_customer_intake_once_real.ps1`로 1건 시험 입력 후 시트 수동 검수
- [ ] `확인필요` 필드는 시트에서 수동 보정

---

## 12. 모듈 구조

```
D:\mail\
  .env                    ← 직접 생성 (gitignore)
  .env.example
  secrets\
    google_service_account.json   ← 직접 배치 (gitignore)
  run_customer_intake_once.ps1
  run_customer_intake_watch.ps1
  run_customer_intake_once_real.ps1
  customer_intake\
    config.py             ← .env 자동 로드
    env_check.py          ← 환경 검증·OCR 모드 표시
    file_scanner.py       ← inbox 직하위 문서 탐색·우선순위
    inbox_watch.py        ← watchdog 또는 폴링 감시
    clova_ocr_client.py   ← CLOVA API / Mock OCR
    extractor.py          ← OCR 결과 → 고객사 레코드
    sheets_writer.py      ← Sheets 생성·중복 스킵·행 추가
    processed_store.py    ← 파일 해시 기반 중복 처리 이력
    report.py             ← Markdown 보고서
```
