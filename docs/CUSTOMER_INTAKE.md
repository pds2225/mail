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

**미리보기 (권장·기본)** — Sheets에 안 쓰고 결과만 확인:

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

(실행 전 경고 + `Y` 입력 필요)

### ③ 결과 확인

| 확인 | 위치 |
|------|------|
| 성공한 파일 | `D:\customer_intake_done` |
| 실패한 파일 | `D:\customer_intake_failed` |
| 보고서 | `D:\customer_intake_reports\customer_intake_*.md` |
| 시트 데이터 | Google 스프레드시트 (real 실행 시) |

---

## 3. OCR 모드 표시

실행 시작 시 콘솔에 표시됩니다.

| 표시 | 의미 |
|------|------|
| `[OCR] Mock OCR (테스트)` | `.env`에 CLOVA 미설정 → 샘플 JSON으로 추출 테스트 |
| `[OCR] 실제 CLOVA OCR` | CLOVA API로 실제 문서 인식 |

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
python -m customer_intake.watcher --once --dry-run true
python -m customer_intake.watcher --watch --dry-run true
python -m customer_intake.watcher --once --dry-run false
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

`dry_run=false` 또는 `run_customer_intake_once_real.ps1` 실행 시 필수 값이 없으면 **어떤 변수를 어디에 넣을지** 안내 후 종료합니다.

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
