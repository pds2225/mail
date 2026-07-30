# 08:54 발송처 추적 (TASK-01 계약 TASK-02 / TASK-G02)

> 조사만. 외부 발송을 실제로 삭제·정지하지 않는다. 끄기 절차만 기록.

## 결론 (2026-07-30)

**주체:** GitHub Actions 워크플로 `수출지원 모니터링 자동 실행` (`.github/workflows/monitor.yml`)

| 항목 | 값 |
|------|-----|
| 트리거 | `schedule` cron (KST 환산) |
| 기존 | `0 23 * * *` → **매일 08:00 KST** 1회 |
| 변경(PR #217 계열) | `30 22 * * *`(07:30 KST), `30 9 * * *`(18:30 KST) |
| 실행 명령 | `python scripts/monitor_runtime.py --send --persist-seen --coverage-alert` |
| 동시성 | `concurrency.group: monitor-daily-send` (중복 발송 대기열) |

**왜 08:54인가:** GitHub Actions 예약은 혼잡 시 지연된다. 이 저장소 실측으로 08:00 예약이 **~50분 늦게** 도착하는 경우가 있어, 수신함 시각이 **08:50~09:00대**로 보인다. 08:54는 별도 발송 스크립트가 아니라 **지연된 동일 monitor 워크플로**로 보는 것이 타당하다.

**다른 후보 배제:**
- `auto-dev-queue.yml` — 자동개발 큐. 실제 digest 발송 없음(RULES: 실발송 금지).
- 로컬 PC 스케줄러 / 수동 `workflow_dispatch` — 일상 08:54 패턴의 주원인으로 보기 어렵다.

## 끄기 절차 (실행하지 말 것 — 참고만)

1. **일시 중지(권장):** GitHub → Actions → `수출지원 모니터링 자동 실행` → `...` → Disable workflow
2. **dry-run만:** `monitor.yml` 의 `--send` 를 제거하고 `--dry-run` 으로 교체(코드 PR 필요, 사람 승인)
3. **스킵 게이트만 강제:** 환경변수 `MONITOR_SKIP_IF_DELIVERED=1`(기본 on) — 이미 보낸 회차 재발송만 막음. **발송 자체를 끄지 않음**
4. **Secret 제거로 끄기 금지:** `GMAIL_*` 삭제 시 크래시/알림만 늘고 원인 추적이 어려워짐

⚠️ 이 세션에서는 위 끄기 절차를 **실행하지 않았다**.

## 잔여 리스크

- GHA 지연은 제어 불가 → 수신 시각이 매일 흔들림.
- 하루 2회 발송 병합 후 수신 시각대가 둘로 나뉨 (`DELIVERY_PM_CUTOFF_HOUR=14`).
