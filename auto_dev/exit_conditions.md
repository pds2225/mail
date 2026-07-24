# Auto Dev — 종료 조건

> AI 시스템이 실패하는 이유의 상당수는 모델이 아니라 **출구 없는 루프**다.  
> 아래를 만족하지 못하면 write 권한을 유지한 채 반복하지 않는다.

## 1. 성공 종료

| 코드 | 의미 | 다음 |
|------|------|------|
| `SUCCESS_VERIFIED` | `loop_verify` 통과 + TASK DONE | 다음 PENDING |
| `SUCCESS_NOOP` | 변경 불필요 확인 | DONE 또는 SKIPPED |
| `SUCCESS_PR_OPEN` | 게이트 통과 PR 생성 | 사람 G2(핵심파일) 또는 자동 병합 정책 |

## 2. 실패 후 재시도

| 코드 | 조건 | 동작 |
|------|------|------|
| `FAIL_RETRY` | 게이트 실패 ∧ retry &lt; 2 | FAILED + FIX TASK, retry_counts++ |
| `FAIL_NO_PROGRESS` | 동일 에러 해시 2회 | 재시도 중단 → BLOCKED |

## 3. 에스컬레이션 (사람)

| 코드 | 조건 | 게이트 |
|------|------|--------|
| `ESC_PROTECTED` | 보호 파일 수정 시도/감지 | G2 |
| `ESC_EMAIL` | 실제 발송·연결 위험 키워드 | G4 |
| `ESC_SECRET` | 필수 토큰/권한 없음 | 설정 담당 |
| `ESC_MAX_RETRY` | retry ≥ 2 | G1 |
| `ESC_COVERAGE` | high-severity 수집 공백 | G1 |
| `ESC_LABEL` | 골든라벨 충돌·추측 요구 | G3 |
| `ESC_UNKNOWN_EXIT` | 종료 조건을 루프 정의에서 못 찾음 | **즉시 STOP, write 회수** |

## 4. 하드 스톱 (권한 회수)

다음이면 루프를 계속 돌리지 않는다.

1. `allow_email_send` 가 false인데 발송 API 호출 경로가 실행됨  
2. `loops.json`에 해당 루프의 `exit` 필드 누락  
3. 비용/시간 한도: GHA job timeout (15분) 또는 에이전트 세션 한도  
4. “의미 있는 변화 없음”인데 패치만 반복 (동일 diff hash)

## 5. 한도 (기본값)

| 한도 | 값 | 설정 위치 |
|------|-----|-----------|
| TASK 재시도 | 2 | `docs/project/RULES.md`, `loops.json` defaults.max_retry |
| 1회 실행 TASK 수 | 1 | `docs/project/RULES.md` |
| GHA timeout | 15분 | `auto-dev-queue.yml` |
| BLOCKED 자동 재개 | 금지 | `docs/project/RULES.md` |

## 6. 운영 메모

- 종료 조건이 불분명한 실험 루프에는 **읽기 전용**만 허용.
- FIX TASK는 원본 TASK id를 본문에 인용해 핑퐁을 추적한다.
- 사람에게 넘길 때는 “무엇을 판단해 달라” 한 줄 + 로그 요약(시크릿 제외).
