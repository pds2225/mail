# 수신 메일주소 추가 가이드

실제 이메일 주소를 코드에 하드코딩하지 마세요. 설정 파일만 수정합니다.

## 설정 위치

| 용도 | 파일 | 필드 |
|------|------|------|
| 그룹별 발송 | `groups.json` | 각 그룹의 `recipients` (배열) |
| 원본전체 메일 | `settings.json` | `raw_all_recipients` (배열) |

## 추가 방법

1. `groups.json`에서 대상 그룹을 연다.
2. `recipients` 배열에 **검증된** 이메일을 한 줄씩 추가한다.
3. 저장 후 dry-run으로 검증한다.

```bash
python3 scripts/monitor_dry_run.py --skip-coverage-fetch --json
```

출력의 `recipient_audit`에서 `valid` / `rejected` / `masked`를 확인한다.

## 검증 규칙 (monitor.py)

- RFC5322 단순 패턴 검증
- 대소문자 무시 중복 제거
- 잘못된 형식 → `rejected` 목록 (발송 대상 제외)
- 로그·보고서에는 `_mask_email()` 마스킹만 출력 (예: `ab***@example.com`)

## 금지 사항

- `monitor.py` / 테스트 / 스크립트에 수신자 주소 하드코딩
- dry-run 없이 `python monitor.py` 실행 (실발송·seen_ids 저장)
- 승인 없는 `main` / GHA 워크플로 변경

## 운영 발송 (NEEDS_USER)

실발송은 다음이 모두 필요합니다.

- `execute_monitor(allow_send=True, persist_seen=True)` 또는 `python monitor.py`
- Gmail 환경변수 (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`)
- GitHub Actions `.github/workflows/monitor.yml` 정책 확인

자동 에이전트 작업에서는 **dry-run만** 사용합니다.
