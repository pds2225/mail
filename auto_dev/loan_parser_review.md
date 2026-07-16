# 정책자금 파서 안정화 — 검토 메모 (Auto Dev)

> TASK-006 / TASK-007 안전 실행기 산출물. 코드 변경 없음 (`loan/`·`monitor.py` 미수정).

## TASK-006 — 소진공(SEMAS) selector 안정화 검토

| 항목 | 내용 |
|------|------|
| 대상 | `loan/` 소진공 정책자금 수집 |
| 위험 | 페이지 DOM/표 구조 변경 시 selector 깨짐 → 수집 공백 |
| 권장 | 1) dry-run 스냅샷 fixture 고정 2) selector를 설정 YAML로 분리 3) 구조 변경 시 FAIL→FIX TASK |
| 사람/에이전트 | 실제 selector 패치는 **코딩 에이전트** 또는 수동 PR (이 문서는 검토만) |
| 관련 | `loan/config/semas.yml`, `docs` loan runbook |

## TASK-007 — 중진공 등 기관 확장 검토

| 항목 | 내용 |
|------|------|
| 전제 | 소진공 모듈 안정화(테스트·dry-run green) 후 |
| 확장 후보 | 중진공 등 유사 표형 공고 |
| 원칙 | 사이트 1개 = 설정+collector 단위. `monitor.py` 직접 수정 최소화 |
| 게이트 | `loop_verify` + (해당 시) core_sources / loan dry-run |
| 다음 | G1에서 확장 우선순위 확정 후 `loop:coding-fix` TASK 생성 |

## 종료

검토 문서 작성으로 TASK-006/007의 **검토** 범위는 충족. 구현 패치는 별도 TASK.
