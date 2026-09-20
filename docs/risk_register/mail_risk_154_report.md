# MAIL-014 — 154 Risk × MAIL TASK Crosswalk

- Audit phase: **STRUCTURAL_COVERAGE_V1**
- Generated: 2026-09-20T19:20:00+09:00
- Repo main at start: `2b705b1074433dae55dd9398d3611362a11ad344`
- Source rows: **154/154**
- OPEN_WITHOUT_TASK: **0**

## 주의

**COVERED_BY_TASK는 해결 완료가 아니다.** 담당 TASK를 지정했다는 뜻이다.
`ALREADY_DONE`은 실제 코드 + 테스트/E2E 근거를 확인한 다음 pass에서만 부여한다.

## 원본 집계

- P0: 27
- P1: 107
- P2: 20

- 수집: 20
- 상세보강: 14
- 날짜필터: 14
- 그룹판정: 38
- 기업매칭: 12
- 요약: 14
- 발송: 16
- 피드백: 14
- 상태관리: 12

## 기존 TASK로 계속 처리

- Risk 35~48: MAIL-014의 TASK-021~025
- Risk 49~98: MAIL-014 원자 TASK + MAIL-022 정확도 개선
- Risk 99~112: TASK-042~044
- 저장 동시수정: MAIL-023
- 기존 완료 MAIL TASK의 검증 근거는 다음 evidence pass에서 Risk별로 역연결

## 신규 residual TASK

- **MAIL-024**: 수집 Risk 1~20
- **MAIL-025**: 상세보강 Risk 21~34
- **MAIL-026**: 발송 Risk 113~128
- **MAIL-027**: 피드백 Risk 129~142
- **MAIL-028**: 상태관리 Risk 143~154

각 residual TASK는 "전부 새로 개발"이 아니라 **최신 main에서 이미 해결됐는지 먼저 검증하고 남은 문제만 수정**한다.

## 다음 Checkpoint

1. P0 Risk부터 코드·테스트 evidence 확인
2. 근거 충분 → ALREADY_DONE
3. 부분해결 → COVERED_BY_TASK 유지 + gap 기록
4. 재현 안 됨 → NOT_REPRODUCED 근거를 TASK 결과에 기록
5. 외부환경 필요 → BLOCKED/HUMAN_BATCH
6. crosswalk 재생성

