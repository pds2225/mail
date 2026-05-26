# 고객사 서류 OCR → Google Sheets (실사용 가이드)

메일 모니터링(`monitor.py`)과 **완전히 별개**입니다.  
**파일만 inbox에 넣고 PowerShell 스크립트 한 번 실행**하면 됩니다.

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

## 2. 매일 쓰는 방법 (3단계)

### ① 파일 넣기

사업자등록증 PDF/이미지를 복사:

```
D:\customer_intake_inbox
```

(폴더 없으면 실행 시 자동 생성)

### ② 실행

**자동 모드 (권장·기본)** — `.env`에 Sheets 설정이 완성되어 있으면 실제 기록, 없으면 미리보기:

```powershell
cd D:\mail
.\run_customer_intake_once.ps1
```

**계속 감시** — inbox에 넣을 때마다 자동 처리:

```powershell
cd D:\mail
.\run_customer_intake_watch.ps1
```

**실제 Google Sheets 기록**:

```powershell
cd D:\mail
.\run_customer_intake_once_real.ps1
```

(실행 전 경고 + `Y` 입력 필요. Sheets 설정이 부족하면 중단하지 않고 dry_run으로 전환됩니다.)

### ③ 결과 확인

| 확인 | 위치 |
|------|------|
| 성공한 파일 | `D:\customer_intake_done` |
| 실패한 파일 | `D:\customer_intake_failed` |
| 보고서 | `D:\customer_intake_reports\customer_intake_*.md` |
| 시트 데이터 | Google 스프레드시트 (real 실행 시) |

---

## 3. 실행 모드와 자동 폴백

실행 시작 시 콘솔에 표시됩니다.

| 표시 | 의미 |
|------|------|
| `[OCR] Mock OCR` | `CLOVA_OCR_URL`, `CLOVA_OCR_SECRET`가 둘 다 없으면 `mock_ocr_result.json`으로 추출 테스트 |
| `[OCR] 실제 CLOVA OCR` | CLOVA API로 실제 문서 인식 |
| `[Sheets] 미기록 (dry_run=true)` | Google Sheets에 쓰지 않고 보고서와 파일 이동만 수행 |
| `[Sheets] 실제 기록 (dry_run=false)` | `GOOGLE_SHEET_ID`와 서비스 계정 JSON이 확인되어 Sheets에 기록 |

`--dry-run auto`가 기본입니다. Sheets 설정이 준비되어 있으면 실제 기록, 부족하면 dry_run으로 계속 처리합니다. `--dry-run false`를 직접 지정해도 Sheets 설정이 부족하면 실패 종료 대신 dry_run으로 폴백하고 시작 배너와 보고서에 누락 항목을 남깁니다.

---

## 4. 고정 폴더

| 경로 | 용도 |
|------|------|
| `D:\customer_intake_inbox` | 넣는 곳 |
| `D:\customer_intake_done` | 성공 |
| `D:\customer_intake_failed` | 실패 |
| `D:\customer_intake_reports` | Markdown 보고서 |

---

## 5. Python 직접 실행

```powershell
cd D:\mail
python -m customer_intake.watcher --once --dry-run auto
python -m customer_intake.watcher --watch --dry-run auto
python -m customer_intake.watcher --once --dry-run false
```

레거시 경로 지정 실행도 유지됩니다. 단일 파일이나 폴더를 직접 지정할 때만 사용하세요.

```powershell
python -m customer_intake.main --path D:\some_folder --dry-run true
```

---

## 6. Google Sheets 컬럼

### 고객사_마스터DB

고객사명, 대표자명, 사업자등록번호(**중복 시 신규 행 안 함**), 법인등록번호, 사업장주소, 개업일, 업태, 종목, 과세유형, 확인상태, 확인필요사항, 추출일시

### 제출서류DB

고객사명, 사업자등록번호, 서류종류, 파일명, 파일경로, 추출일시, 확인상태, 확인필요사항

### 실행로그

실행일시, 입력경로, dry_run, 처리파일수, 마스터신규, 마스터스킵, 서류기록수, 오류수, 보고서경로, 비고

---

## 7. 환경변수 누락 시

필수 값이 없어도 기본적으로 처리는 계속됩니다.

| 누락 항목 | 동작 |
|-----------|------|
| CLOVA OCR URL/Secret 전체 또는 일부 | Mock OCR 사용 |
| `GOOGLE_SHEET_ID` | dry_run으로 전환, Sheets 미기록 |
| Google 서비스 계정 JSON | dry_run으로 전환, Sheets 미기록 |

서비스 계정 JSON은 아래 순서로 확인합니다.

1. `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`
2. `GOOGLE_SERVICE_ACCOUNT_JSON`이 파일 경로인 경우
3. `D:\mail\secrets\google_service_account.json`

---

## 8. 실사용 전 최종 체크리스트

- [ ] `pip install -r requirements.txt` 완료
- [ ] `D:\customer_intake_inbox`에 테스트 PDF 1건 넣고 `.\run_customer_intake_once.ps1` 성공
- [ ] 보고서·done 폴더 이동 확인
- [ ] Mock → CLOVA 실 OCR 전환 후 샘플 1건 재검수
- [ ] `.env` + `secrets\google_service_account.json` 준비
- [ ] 스프레드시트에 서비스 계정 **편집 권한**
- [ ] `.\run_customer_intake_once_real.ps1`로 1건 시험 입력 후 시트 수동 검수
- [ ] `확인필요` 필드는 시트에서 수동 보정

---

## 9. 모듈 구조

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
    watcher.py
    ...
```

### 처리 흐름

1. `watcher.py`가 inbox에서 지원 파일(`.pdf`, `.png`, `.jpg`, `.jpeg`)을 찾습니다.
2. 파일 크기가 안정될 때까지 잠시 대기해 복사 중인 파일을 피합니다.
3. `clova_ocr_client.py`가 CLOVA OCR 또는 Mock OCR을 실행합니다.
4. `extractor.py`가 사업자등록번호, 고객사명, 대표자명 등 Sheets 컬럼에 맞는 레코드를 만듭니다.
5. `sheets_writer.py`가 dry_run이면 미리보기만 만들고, 실제 모드면 Google Sheets에 기록합니다.
6. `processed_store.py`가 파일 내용 SHA-256을 `customer_intake/processed_files.json`에 저장해 같은 파일 재처리를 막습니다.
7. 처리 결과에 따라 파일을 done/failed 폴더로 이동하고 `report.py`가 Markdown 보고서를 저장합니다.

### Watch 모드 운영 메모

- `watchdog`가 설치되어 있으면 OS 파일 이벤트를 사용하고, 없으면 폴더 스냅샷을 주기적으로 비교합니다.
- 연속 파일 이벤트는 `CUSTOMER_INTAKE_DEBOUNCE_SEC` 동안 모아 한 번만 처리합니다.
- 느린 OCR/Sheets 처리 중 새 이벤트가 와도 동시에 두 번 실행되지 않도록 내부 실행 락을 사용합니다.
- 기동 직후 inbox에 이미 있던 파일도 1회 처리합니다.

### 중복 처리 기준

같은 파일명 기준이 아니라 파일 내용 해시 기준입니다. 이름을 바꿔 다시 넣어도 내용이 같으면 신규 Sheets 행을 만들지 않고 기존 처리 상태에 따라 done 또는 failed 폴더로 이동합니다. 재처리가 꼭 필요하면 파일 내용을 수정하거나, 운영자가 `customer_intake/processed_files.json`에서 해당 항목을 신중히 정리해야 합니다.

---

## 10. 문제 해결 Runbook

| 증상 | 확인할 것 | 조치 |
|------|-----------|------|
| Sheets에 기록되지 않음 | 시작 배너의 `[Sheets] 미기록`, 보고서의 `.env` 누락 항목 | `.env`의 `GOOGLE_SHEET_ID`, 서비스 계정 JSON 경로, 스프레드시트 공유 권한 확인 |
| 실제 문서를 넣었는데 샘플처럼 추출됨 | 시작 배너의 `[OCR] Mock OCR` | `CLOVA_OCR_URL`과 `CLOVA_OCR_SECRET`를 둘 다 설정 |
| watch가 반응하지 않음 | `D:\customer_intake_reports\watch.log`, `watchdog` 설치 여부 | `.\doctor_customer_intake.ps1` 실행 후 필요 시 `.\repair_customer_intake.ps1` |
| 파일이 failed로 이동됨 | 해당 실행 보고서와 watch 로그 | 원본 파일 열림/복사 중 여부, OCR API 오류, Sheets 권한 오류 확인 |
| 같은 파일이 계속 스킵됨 | `customer_intake/processed_files.json`의 동일 해시 처리 이력 | 정상 동작입니다. 재처리가 필요한 경우 처리 이력을 백업 후 정리 |

운영 점검 명령:

```powershell
cd D:\mail
.\doctor_customer_intake.ps1
```
