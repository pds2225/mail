# 소진공 정책자금 점검 모듈

`loan/`은 기존 `monitor.py` 메일 기능과 분리된 정책자금 전용 모듈입니다.

## 실행

- 미리보기: `python3 -m loan.semas.collector --run-mode dry-run --send-email false`
- 메일 테스트: `ALLOW_SEND_EMAIL=true python3 -m loan.semas.collector --run-mode dry-run --send-email true`
- 최근 기간 변경: `python3 -m loan.semas.collector --lookback-days 3`

## 환경변수

- `SEMAS_LOAN_URL`: 대상 URL override. 기본값은 `loan/config/semas.yml`을 사용합니다.
- `LOOKBACK_DAYS`: 최근 N일 판단 기준.
- `MAIL_TO`: 테스트 메일 수신자. 없으면 기존 `settings.json`/`groups.json` 수신자를 사용합니다.
- `ALLOW_SEND_EMAIL`: `true`일 때만 실제 발송 안전장치 통과.
- 기존 메일 변수 재사용: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, 선택 `SMTP_HOST`, `SMTP_PORT`.

## 산출물

- 리포트: `reports/loan/semas_loan_scan.md`
- 상태 파일: `reports/loan/semas_seen_notices.json`

외부 사이트 접속 실패 또는 SMTP 실패가 있어도 리포트에는 실패 사유가 기록됩니다.

