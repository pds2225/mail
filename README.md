# Mail Project (Vercel Ready)

이 프로젝트는 기존 로컬 실행형 Mail 모니터링을 Vercel 배포형 구조로 전환한 버전입니다.

## Project Type

- Runtime: Python
- Frontend entry: `auto_mail_web.html` (정적 페이지)
- API entry: `api/index.py` (Vercel Python Serverless Function)
- Core mail logic: `monitor.py`

## Vercel Deployment

1. Vercel에 저장소 연결
2. Root Directory를 이 프로젝트 루트로 지정
3. Environment Variables 설정
4. 배포 실행

`vercel.json`에서 아래 라우팅을 사용합니다.

- `/` -> `auto_mail_web.html`
- `/api/*` -> `api/index.py`

## Required Environment Variables (Vercel)

- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `SMTP_HOST`
- `SMTP_PORT`
- `IMAP_HOST`
- `IMAP_PORT`

추가로 기존 기능에서 사용하는 키가 필요합니다.

- `BIZINFO_API_KEY`
- `ANTHROPIC_API_KEY`

비밀값은 절대 코드에 하드코딩하지 말고, Vercel Environment Variables로만 관리하세요.

## Safe Mail Sending Rules

- 기본 실행은 `dry_run=true` (미리보기/검증 모드)
- 실제 발송은 `confirm_send="SEND"`를 명시한 경우에만 허용
- 수신자 이메일은 로그에 마스킹되어 기록
- 이메일 본문/첨부 내용은 로그에 출력하지 않음
- 테스트에서 실제 발송 금지

`POST /api/run` 요청 예시:

- 기본(안전): `{"dry_run": true}`
- 실제 발송(명시 승인): `{"dry_run": false, "confirm_send": "SEND"}`

## 지원사업 공고 필터링 기준

`monitor.py`는 수집된 공고를 발송 전에 판정 필드로 보강한 뒤 `is_relevant=true`인 신청 가능 공고만 최종 추천합니다.

- 포함/가점: 베트남, 동남아, 해외, 글로벌, 박람회, 전시회, 소상공인, 지원금, 공장, 스마트 및 스마트공장/제조DX/공정자동화 계열
- 우선 검토: 혁신바우처, 수출바우처, 스마트공장 계열 키워드
- 필수 제외: 행정공지, 지침, 매뉴얼, 교육, 설명회, 공급기업/수행기관 모집, 기선정 기업 절차, 마감 완료, 인천/남동구 신청 불가 공고
- 지역 기준: 신청기업 소재지를 인천광역시 남동구로 보고, 인천 내 특정 구 제한에서 남동구가 빠지면 제외합니다.
- 공장 조건: 공장등록증, 제조시설, 공장 보유, 제조업 영위 등은 점수와 조건 메모에 반영합니다.
- `dry_run`/preview 결과에는 제외 공고 요약과 `exclude_reason_codes`가 포함됩니다.

## 소진공 정책자금 점검 모듈

정책자금 전용 기능은 기존 메일 모니터링과 분리된 `loan/` 패키지에 있습니다.

- 대상 설정: `loan/config/semas.yml`
- 리포트: `reports/loan/semas_loan_scan.md`
- 중복 상태 파일: `reports/loan/semas_seen_notices.json`
- 수동 실행: `python3 -m loan.semas.collector --run-mode dry-run --send-email false`
- 실제 테스트 메일: `ALLOW_SEND_EMAIL=true python3 -m loan.semas.collector --run-mode dry-run --send-email true`

메일 발송은 기존 변수명인 `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, 선택 변수 `SMTP_HOST`, `SMTP_PORT`를 재사용합니다. 수신자는 `MAIL_TO`가 있으면 우선 사용하고, 없으면 기존 `settings.json`의 `raw_all_recipients`와 `groups.json`의 `recipients`를 사용합니다.

GitHub Actions에서는 **소진공 정책자금 수동 점검** workflow를 실행하고 `run_mode`, `send_email`, `lookback_days`를 선택합니다. 외부 사이트 접속 또는 SMTP 설정이 실패해도 Markdown 리포트 artifact는 생성됩니다.

## Local Notes

- 기존처럼 `python monitor.py` 실행 시에는 실제 발송 경로를 유지합니다.
- Vercel serverless 환경은 로컬 파일 영구 저장을 보장하지 않으므로, `seen_ids.json` 기반 중복 방지는 제한적입니다.
  - 권장 대체안: Redis/DB/KV 같은 영구 저장소로 전환

## 운영 안정성 권고

현재 Gmail SMTP 방식은 임시/소규모 운영에는 사용 가능하지만, 운영 안정성을 위해 아래 이메일 API로 전환을 권장합니다.

- Resend
- SendGrid
- Postmark

이번 변경에서는 발송 인프라를 Gmail SMTP에서 이메일 API로 전환하지 않았습니다.

## Auto Dev Queue

1. `TASKS.md`의 `## PENDING` 섹션에 `TASK-NNN: <작업 설명>` 형식으로 태스크를 추가합니다.
2. `python3 scripts/auto_dev_queue.py`를 실행하면 PENDING 목록에서 1개를 자동으로 처리합니다.
3. 처리 중인 태스크는 `## RUNNING`으로, 완료되면 `## DONE`으로 이동합니다.
4. 실패하거나 조건 미충족 시 `## FAILED` / `## BLOCKED`로 이동하며 사유가 기록됩니다.
5. GitHub Actions에서 자동 실행 시 Summary에 실행 TASK, 결과, 다음 TASK가 표시됩니다.

## Customer Intake 자동화

고객사 서류(PDF/PNG/JPG)를 OCR로 읽어 Google Sheets `고객사_마스터DB` 등에 기록하는 **inbox 자동 처리**입니다.  
**기존 메일 모니터링(`monitor.py`)·실제 메일 발송과는 연결되지 않습니다.** 점수화·랭킹 기능이 아닙니다.

### 사용 방법 (일상)

1. 사업자등록증 등 파일을 **`D:\customer_intake_inbox`** 에 넣기만 하면 됩니다.
2. PC 로그인 후 백그라운드 감시가 파일을 자동 처리합니다.
3. 결과는 아래 폴더에서 확인합니다.
   - **`D:\customer_intake_done`** — 처리 성공
   - **`D:\customer_intake_failed`** — 처리 실패
   - **`D:\customer_intake_reports`** — Markdown 보고서·`watch.log`

환경 설정은 **`D:\mail\.env`** 를 그대로 사용합니다 (Python이 자동 로드).

### 스크립트 (PowerShell, `D:\mail`에서 실행)

| 용도 | 파일 |
|------|------|
| **최초 1회** — 로그인 시 자동 감시 등록 | `D:\mail\install_customer_intake_autostart.ps1` |
| **실패/멈춤 시** — 폴더 복구·감시 재등록·1회 처리 | `D:\mail\repair_customer_intake.ps1` |
| **진단** — Python·폴더·스케줄러·로그 확인 | `D:\mail\doctor_customer_intake.ps1` |
| 수동 1회 처리 | `D:\mail\run_customer_intake_once.ps1` |
| 자동시작 해제 | `D:\mail\uninstall_customer_intake_autostart.ps1` |

`install` / `repair` 는 **관리자 PowerShell**에서 실행하세요.

```powershell
cd D:\mail
.\install_customer_intake_autostart.ps1
```

### 보장하지 않는 항목 (외부 권한·서비스)

아래는 이 레포만으로 보장할 수 없습니다. 계정·콘솔·스프레드시트에서 직접 확인해야 합니다.

- Google Cloud 서비스 계정 키 유효성·만료
- Google Sheets 스프레드시트 **편집 권한** (서비스 계정 이메일 공유)
- NAVER CLOVA OCR API 할당량·요금·URL/Secret 정확성
- Windows 작업 스케줄러 정책(회사 PC 보안 정책으로 차단되는 경우)

`.env`에 `GOOGLE_SHEET_ID`·서비스 계정·`CLOVA_OCR_*` 가 없으면 **중단하지 않고** Mock OCR + dry_run 으로 처리하며, 보고서에 미설정 항목만 표시합니다.

자세한 내용: `docs/CUSTOMER_INTAKE.md`

