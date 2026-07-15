# 📬 Mail — 정부지원사업 공고를 대신 찾아 메일로 알려주는 프로그램

> 한 줄 요약: **여러 지원사업 사이트를 매일 자동으로 돌아다니며, 우리 회사에 맞는 공고만 골라서 이메일로 보내주는** 자동화 도구입니다.

---

## 1. 이게 뭐예요? (비개발자용 설명)

정부·기관에서 올라오는 **지원사업 공고**(지원금, 바우처, 스마트공장, 수출지원 등)는
사이트마다 흩어져 있고 매일 새로 올라옵니다. 사람이 일일이 들어가서 확인하기 어렵습니다.

이 프로그램은 그 일을 **대신** 해줍니다.

1. 여러 공고 사이트(기업마당, K-Startup, 수출바우처 등)를 **자동으로 돌면서** 새 공고를 모읍니다.
2. 모은 공고 중 **우리 회사에 신청 가능한 것만** 걸러냅니다.
3. 추려진 공고를 **이메일로 정리해서** 보내줍니다.

쉽게 말하면 **"지원사업 공고 자동 비서"** 입니다.

---

## 2. 무엇을 자동으로 해주나요?

이 프로젝트 안에는 서로 독립적인 기능 3가지가 들어 있습니다.

| 기능 | 하는 일 | 비고 |
|------|---------|------|
| **① 공고 수집·필터·메일** | 지원사업 공고를 모아 우리 회사에 맞는 것만 메일로 발송 | 핵심 기능 (`monitor.py`) |
| **② 정책자금 점검** | 소상공인시장진흥공단(소진공) 정책자금 공고를 따로 점검 | `loan/` 폴더 |
| **③ 고객사 서류 자동 입력** | 사업자등록증 등 서류 사진을 읽어 구글 시트에 자동 정리 | `customer_intake` (메일 기능과 별개) |

---

## 3. 어떤 공고를 "우리 회사 것"으로 골라주나요?

우리 회사 기준(**인천광역시 남동구 / 제조업**)에 맞춰 자동으로 판단합니다.

- ✅ **잘 골라줌(가점)**: 베트남·동남아·해외·글로벌, 박람회·전시회, 소상공인, 지원금, 공장·스마트공장·제조 자동화 관련
- ⭐ **특히 우선**: 혁신바우처, 수출바우처, 스마트공장 관련
- ❌ **자동 제외**: 단순 행정공지·지침·매뉴얼·교육·설명회, 수행기관 모집, 이미 마감된 공고, 인천 남동구가 신청 불가인 공고

> 즉, "신청해도 되는 공고"만 메일로 오고, "우리랑 상관없는 공고"는 알아서 걸러집니다.

---

## 4. 실수로 메일이 잘못 나가지 않게 (안전장치)

이 프로그램은 **기본적으로 "미리보기 모드"** 로 동작합니다. 즉, 실제로 메일을 쏘지 않고
"어떤 메일이 나갈지"만 보여줍니다. 진짜 발송은 **사람이 명확히 허락했을 때만** 됩니다.

- 기본값: 미리보기(검증)만 → 실제 발송 안 함
- 실제 발송: 발송 승인을 명시했을 때만 허용
- 받는사람 이메일은 기록에 **가려서(마스킹)** 남고, 메일 본문 내용은 기록에 남기지 않음

---

## 5. 어디서·어떻게 동작하나요?

- 평소에는 **자동으로(서버에서 정해진 시간마다)** 돌도록 만들어져 있습니다.
- 화면(웹페이지)에서 직접 실행해 볼 수도 있습니다. (`auto_mail_web.html`)
- 프로그램의 "두뇌"는 `monitor.py` 파일이고, 인터넷에 올려서 자동 실행하는 구조(Vercel)도 준비돼 있습니다.

---

## 6. 고객사 서류 자동 입력 (③번 기능, 일상 사용법)

사업자등록증 같은 서류를 폴더에 넣기만 하면, 글자를 읽어서 구글 시트에 자동으로 정리해 줍니다.

1. 서류 파일(PDF/사진)을 **`D:\customer_intake_inbox`** 폴더에 넣습니다.
2. PC가 켜져 있으면 백그라운드에서 **자동으로 처리**됩니다.
3. 결과 확인 폴더:
   - 성공 → `D:\customer_intake_done`
   - 실패 → `D:\customer_intake_failed`
   - 보고서 → `D:\customer_intake_reports`

> 자세한 설치·복구 방법은 `docs/CUSTOMER_INTAKE.md` 와 `D:\mail` 폴더의 `install_customer_intake_autostart.ps1` 등 도우미 파일을 참고하세요.

---

## 7. (개발자·운영자용) 기술 정보

평소 사용에는 필요 없습니다. 설치·배포·점검할 때만 참고하세요.

### 구성
- 실행 언어: Python
- 화면: `auto_mail_web.html` (정적 페이지)
- 자동 실행 입구: `api/index.py` (Vercel 서버리스 함수)
- 핵심 로직: `monitor.py`

### 필요한 비밀 설정값 (환경변수)
코드에 직접 적지 말고, 반드시 **환경변수(또는 `.env`)** 로만 관리합니다.

`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`, `IMAP_HOST`, `IMAP_PORT`,
`BIZINFO_API_KEY`, `ANTHROPIC_API_KEY`

### 실행 (Windows PowerShell)
```powershell
cd D:\mail
python monitor.py
```

### 정책자금 점검 모듈 (②번 기능)
```powershell
cd D:\mail
python -m loan.semas.collector --run-mode dry-run --send-email false
```
- 대상 설정: `loan/config/semas.yml`
- 리포트: `reports/loan/semas_loan_scan.md`

### 안전·운영 메모
- 테스트에서 **실제 메일 발송 금지** (항상 미리보기/모의 실행).
- 비밀번호·API 키는 화면에 출력하거나 코드에 넣지 않습니다.
- `main` 브랜치에 바로 올리지 않고, 작업 브랜치 → 검증 → PR 순서로 반영합니다.
- 현재 Gmail 발송 방식은 소규모용입니다. 안정 운영이 필요하면 Resend·SendGrid·Postmark 같은 이메일 API 전환을 권장합니다.
- 개발자용 모니터 파이프라인·사이트 수집기·dry-run 점검 절차는 `docs/MONITOR_ENGINEERING_RUNBOOK.md`를 참고하세요.

### Auto Dev Queue (Loop Engineering)
- 설계: `docs/LOOP_ENGINEERING_AUTO_DEV.md` — 사람이 에이전트를 매번 지시하지 않고 **루프가 지시**한다.
- 실행: GitHub Actions → "Auto Dev Queue" / 로컬 `DRY_RUN=true python3 scripts/auto_dev_queue.py`
- 검증: `python3 scripts/loop_verify.py` · 드리프트 `python3 scripts/loop_verify.py --drift`
- 안전 실행기: 문서·검토 NOOP은 `scripts/auto_dev_executor.py`가 자동 DONE (허위 DONE 아님)
- L2 빈틈: `auto_dev/defects_inbox.md` 작성 → G1 후 `python3 scripts/decompose_defects.py --approve`
- 코딩 슬롯: `AUTO_DEV_AGENT=true` (미설정 시 에이전트 필요 TASK는 PENDING 뒤로 회전)

---

**원격 저장소:** https://github.com/pds2225/mail
