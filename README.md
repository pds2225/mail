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

