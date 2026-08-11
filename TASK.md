# CURRENT AI TASK — MAIL / POST-MERGE HOTFIX

> 이 파일은 `pds2225/mail`의 현재 AI 작업지시 단일 기준이다.
> 항상 원격 `main/TASK.md`를 처음부터 끝까지 읽고 작업한다.

## 상황

PR #245와 #246은 이미 main에 병합되었다.

- #245 merge commit: `dc137a3721e17ec8f942b6afe4e6618933d04475`
- #246 merge commit: `193e989474e89e4df0e11bceed553a8d5d23e7f0`

병합 후 자동리뷰에서 P1/P2 결함과 테스트 결과 불일치가 확인되었다.
따라서 지금 목표는 **되돌리기보다 최신 main 기준 즉시 hotfix**다.

## 실행 원칙

- 사용자에게 묻지 않는다.
- 가능한 수정/테스트/조사는 병렬로 진행한다.
- 한 항목이 막히면 BLOCKED로 남기고 다음 항목을 계속한다.
- 실제 이메일/ntfy 발송 금지. preview/dry-run/mock만 사용.
- force push, reset --hard, git clean -fd, secret/.env 수정 금지.
- main에서 직접 개발하지 말고 최신 main에서 새 hotfix branch 생성.
- PR 생성까지 가능하지만 main 자동병합 금지.
- 저장소 `AGENTS.md`를 먼저 읽고 보호규칙을 지켜라. `monitor.py` 수정 금지 규칙과 이번 hotfix가 충돌하면 임의로 무시하지 말고, 가능한 우회 구조를 우선 검토하고 불가능한 경우 `BLOCKED_WITH_EVIDENCE`로 기록한다.

권장 브랜치:

`fix/post-merge-245-246-hotfix`

---

# HOTFIX P1 — fetch_all `_fetch_outcomes` NameError

현재 리뷰 지적:

- `fetch_all()`이 `_fetch_outcomes`를 참조하지만 해당 이름은 `execute_monitor()` 로컬에만 존재.
- 정상 fetch 완료 시 `NameError`가 발생하고 collection이 중단될 수 있음.

요구:

- outcome collector를 명시적 인자로 전달하거나 동등한 안전한 구조로 수정.
- 기존 public call 호환 유지.
- 성공/실패 source별 outcome을 실제 source health가 읽을 수 있게 연결.
- 성공 path, 실패 path, mixed source path 테스트 추가.

---

# HOTFIX P1 — `source_stats` 초기화 전 사용

현재 리뷰 지적:

- `dedup_items(..., _stats=...)`에서 `source_stats` 생성 전에 `_stats["source_contribution"] = source_stats`를 실행하여 `UnboundLocalError` 가능.

요구:

- source contribution 계산 후 stats export.
- nonempty dedup path 실제 실행 테스트 추가.
- KPI total과 세부 removal count가 reconcile되는지 검증.

---

# HOTFIX P1 — 전체 source 실패 시 source-health 누락

현재 리뷰 지적:

- 모든 source가 실패하면 `fetch_all()` 결과가 empty가 되고 `no_items` early return이 source-health 처리보다 먼저 발생할 수 있음.
- 가장 중요한 total outage가 health/incidents에 기록되지 않을 수 있음.

요구:

- empty-result return 전에 fetch outcomes 기반 source-health 반영.
- bizinfo/kstartup 모두 실패 시 FAILING/incident 기록 테스트.
- 실제 alert는 mock.

---

# HOTFIX P1 — accuracy 허위 MEASURED 방지

현재 리뷰 지적:

- `feedback_labels.jsonl`의 tracked rows가 title/description 없이 ID/verdict만 가진 경우가 있음.
- 빈 notice를 평가하고 `MEASURED` TP/TN/FN을 계산하면 잘못된 측정.

요구:

- ID를 실제 stored notice snapshot/raw corpus와 join할 수 있으면 join.
- feature를 복원할 수 없으면 해당 benchmark는 `NOT_MEASURABLE`.
- featureless feedback row를 절대 유효 accuracy sample로 계산하지 말 것.
- TP/FP/TN/FN/precision/recall/F1은 실제 relevance truth + 실제 notice feature가 모두 있을 때만 계산.
- 회귀테스트 추가.

---

# HOTFIX P1 — #246 보고서의 허위 테스트 통과 수정

자동리뷰에서 `tests/test_version_delivery_integration.py`가 보고서상 7 PASS와 달리 실제 해당 commit에서 실패가 확인되었다.

지적 예시:

- version fixture가 기대 change가 아니라 `NEW`
- outbox test가 keyword-only `upsert()`를 positional dict로 호출
- return-contract test가 early return에 없는 field를 기대

요구:

1. 실제 최신 main에서 해당 테스트 파일을 직접 실행.
2. 실패가 재현되면 테스트/구현 중 무엇이 잘못인지 판별.
3. 테스트를 억지로 기대값 변경/skip하지 말 것.
4. 수정 후 동일 테스트 재실행.
5. 결과보고서의 PASS/FAIL 수치를 실제 결과로 정정.
6. 전체 관련 테스트를 다시 실행.

---

# HOTFIX P2 — dedup KPI replacement branch 누락

현재 리뷰 지적:

- incoming primary-source item이 기존 aggregator를 교체하는 경우 출력 item 수는 1건 줄었는데 removal counter가 증가하지 않을 수 있음.

요구:

- discard incoming / replace existing 두 경우 모두 실제 제거 1건으로 정확히 계측.
- `duplicate_removed_total == mechanism counts의 정의상 합계`가 맞는지 검증.
- double-count 금지.

---

# HOTFIX P2 — yearless title 비교 누락

현재 POSSIBLE_DUPLICATE 최적화가 year bucket을 분리해:

- `2026 ...`
- 동일 제목이지만 연도 없는 버전

을 아예 비교하지 않을 수 있음.

요구:

- 서로 다른 명시 연도(2025 vs 2026)는 계속 분리.
- 한쪽에만 연도가 있는 경우는 비교 후보에서 제외하지 않도록 설계.
- 성능 최적화는 유지하되 recall 저하 방지.
- regression test 추가.

---

# 통합 검증

위 항목을 가능한 병렬로 수정한 뒤 다음을 반드시 실행:

1. targeted tests for fetch outcomes/source health/dedup/accuracy
2. `tests/test_version_delivery_integration.py`
3. prestartup regression tests
4. monitor import/smoke dry-run
5. 가능하면 전체 `python -m pytest tests/ -q --tb=short`

Windows temp/cp949 PermissionError가 나면 코드 결함과 환경 결함을 분리해서 증거를 남긴다.

## 결과 보고

새 보고서:

`docs/POST_MERGE_HOTFIX_RESULT_20260812.md`

반드시 포함:

- 시작 main SHA
- 수정한 P1/P2 목록
- 실제 재현 여부
- 변경 파일
- 테스트 명령과 정확한 pass/fail 수
- pre-existing/environment failures
- BLOCKED
- commit 목록
- PR URL
- main 미병합 확인

상태는:

`IMPLEMENTED / TESTED / REAL_DATA_VALIDATED / BLOCKED`

만 사용.

## 최종 지시

지금부터 최신 main을 기준으로 위 P1을 최우선으로 전부 수정하고, 이어서 P2까지 처리한다.
사용자 입력을 기다리지 말고 테스트→수정→재테스트→자체리뷰→commit→push→PR 생성까지 진행한다.
