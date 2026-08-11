# CURRENT AI TASK — MAIL / OVERNIGHT PARALLEL AUTODEV

> 이 파일은 `pds2225/mail`의 현재 AI 작업지시 단일 기준이다.
> 로컬 프롬프트를 별도로 만들지 말고 항상 원격 `main/TASK.md`를 처음부터 끝까지 읽고 작업한다.

## 목표

사용자는 다음 확인 시점까지 PC 앞에 없을 수 있다. 따라서 작은 작업 1개씩 순차적으로 끝내고 멈추지 말고, **서로 충돌하지 않는 조사·구현·테스트·검증은 최대한 병렬화하여 가능한 작업을 한꺼번에 완료**한다.

내일 사용자가 한 번에 확인할 수 있도록 최종적으로 변경사항, 테스트, 실데이터 검증, 커밋, PR, BLOCKED만 정리한다.

---

# 0. 실행 원칙

- 사용자에게 승인/선택/다음 작업을 묻지 않는다.
- `계속할까요?`, `다음 작업을 지정해주세요`, `무엇을 할까요?`, `NEXT`만 출력하고 종료 금지.
- 기능 하나, 테스트 하나, 커밋 하나, PR 하나 끝났다고 멈추지 않는다.
- 한 항목이 BLOCKED이면 증거를 남기고 다른 독립 작업을 계속한다.
- 안전하게 실행 가능한 작업이 남아 있으면 자동으로 다음 작업을 선택한다.
- 같은 작업을 이미 `run.md` 또는 현재 브랜치에서 완료했다면 중복 구현하지 말고 검증 후 건너뛴다.

## 절대 금지

- main 직접 개발
- main 자동 merge / PR auto-merge
- force push
- `git reset --hard`
- `git clean -fd`
- 사용자 미커밋 파일 삭제/덮어쓰기
- `.env`, API key, secret 수정/출력
- 운영 DB destructive migration
- 운영 데이터 삭제
- 실제 이메일 대량발송
- 실제 ntfy 테스트 발송
- Vercel `/api/run` 실발송
- 외부 유료 API 대량 호출
- 테스트 삭제/skip으로 통과시키기
- 기존 fail-closed/누락방지/발송안전 게이트 제거

메일/알림 검증은 preview/dry-run/mock/fixture로만 한다.

---

# 1. 시작 시 최신 상태 + 기존 작업 흡수

반드시 먼저:

```text
git fetch origin
git status
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git log --oneline -20
```

그리고 현재 로컬 브랜치/작업트리/최근 커밋에서 `run.md` 기반으로 이미 진행 중인 작업이 있는지 확인한다.

- 이미 구현된 항목은 버리지 않는다.
- 사용자/다른 세션 dirty file은 건드리지 않는다.
- clean한 최신 `origin/main` 기준으로 안전한 개발 브랜치 또는 worktree를 사용한다.
- 이미 `run.md` 작업 브랜치가 정상적으로 진행 중이면 그 브랜치를 계속 사용해도 된다.

권장 통합 브랜치명:

```text
feat/overnight-parallel-hardening-20260812
```

---

# 2. 병렬 실행 전략

## 핵심 원칙

**병렬 가능한 것은 전부 병렬로 조사/구현/테스트한다.**

다만 `monitor.py`, 동일 workflow, 동일 state schema처럼 같은 hot file을 동시에 수정하면 충돌 위험이 크므로 다음처럼 처리한다.

### 병렬화 가능

- 저장소 전수 audit
- consumer/producer 검색
- 테스트 설계
- 독립 테스트 파일 추가
- `scripts/` 정확도 도구
- `mail_core/operations/` 독립 모듈
- benchmark/실데이터 분석
- 문서/결과보고
- pre-existing failure 원인분석
- API consumer contract audit
- dedup corpus 분석
- source health state-machine 테스트
- golden/OX label 조사

### 병렬화 주의

다음 파일을 여러 작업이 동시에 수정하려 하면 **조사와 patch 설계는 병렬**, 실제 적용은 충돌 없는 순서로 통합한다.

```text
monitor.py
.github/workflows/monitor.yml
config/groups.json
공용 state schema
```

환경이 subagent/worktree/parallel task를 지원하면 독립 lane으로 실행한다. 지원하지 않으면 사용자의 추가 입력 없이 lane들을 번갈아 진행한다.

---

# 3. PARALLEL LANE A — execute_monitor() 반환계약 + downstream contract

PR #242 이후 확인된 BROKEN CONTRACT를 바로 수정한다.

핵심 필드:

```text
send_hold
send_hold_reason
run_status
date_matched_count
date_unknown_items
date_review_queue
date_review_queue_count
date_excluded_count
```

요구:

- `execute_monitor()`의 normal/early/no-items/send-hold 경로 contract를 일관되게 만든다.
- wrapper가 나중에 값을 덧붙이는 데 의존하지 않는다.
- 기존 KPI는 삭제하지 않는다.
- `write_today_missing_risk_report`, `_measure_recall_risk`, `run_dry_run`, CLI, `api/run.py`, scripts consumer를 전수검사한다.
- result payload contract regression test를 추가한다.
- 가능하면 TypedDict/dataclass까지는 과도하면 하지 말고 최소 contract test로 고정한다.

실제 값:

```text
send_hold = collection_gate send_hold
send_hold_reason = effective_allow_send() 결과
run_status = gate status 또는 의미상 올바른 기본 상태
date_matched_count = 실제 date_matched
date_unknown_items = len(date_unknown)
date_review_queue = 실제 queue
date_review_queue_count = len(date_review_queue)
date_excluded_count = len(date_excluded)
```

테스트 기대값만 바꿔 결함을 숨기지 않는다.

---

# 4. PARALLEL LANE B — POSSIBLE_DUPLICATE + dedup/KPI/성능

## B1. 실제 파이프라인 연결

`detect_possible_duplicates()`가 `execute_monitor()`에 실제 연결되지 않았으면 연결한다.

권장 흐름:

```text
all_items
→ exact/canonical dedup
→ POSSIBLE_DUPLICATE detection
→ version/enrich/evaluate
→ diagnostics/review metadata
```

원칙:

- POSSIBLE_DUPLICATE 자동 merge 금지
- 자동 삭제 금지
- 정상 INCLUDE 후보 자동 제외 금지
- 확정 canonical duplicate와 분리

metadata 후보:

```text
_possible_duplicate
_possible_duplicate_with
_possible_duplicate_score
_possible_duplicate_reason
```

별도 공고 유지:

```text
2025 vs 2026
서울 vs 부산
1차 vs 2차
본모집 vs 추가모집
명확히 다른 접수기간/차수
```

## B2. KPI 의미 교정

다음을 실제 의미로 재정의/계측한다.

```text
input_count
output_count
duplicate_removed_total
same_source_duplicate_removed
cross_source_duplicate_removed
canonical_duplicate_removed
title_duplicate_removed
attachment_or_signature_duplicate_removed
possible_duplicate_count
```

`len(all_items)-len(deduped)`를 same-source라고 부르거나, canonical id가 있는 kept item 수를 cross-source duplicate count라고 부르지 않는다.

동일 제거건 double-count 금지.

기존 `dedup_items(items) -> list[dict]` public signature는 가능하면 유지한다.

## B3. 성능

기존 raw corpus 최소 2,000건 이상 가능하면 전체로 benchmark한다.

O(n²) 병목이 있으면 recall을 해치지 않는 안전한 후보 축소를 적용한다.

가능한 bucket:

```text
year
issuer
region
round
title token
```

기록:

```text
items
candidate pairs before/after
elapsed
possible duplicate count
```

---

# 5. PARALLEL LANE C — attachment/signature + source contribution

## C1. attachment hash 의미 교정

현재 `attachment_hash`가 실제 파일 bytes가 아니라 link/title/deadline metadata 조합이라면 실제 content hash가 아니다.

저장소에서 먼저 조사:

```text
attachment URL
attachment metadata
downloaded file
sha256
content hash
filename
size
```

- 실제 content hash가 있으면 그것을 dedup 보조신호로 사용.
- 없으면 `metadata_signature`/`notice_signature_hash` 등 실제 의미에 맞게 명명.
- 기존 persistence/API 호환이 필요하면 alias를 둔다.

## C2. source contribution

실제 수집 전/후 기준으로 최소:

```text
collected_total
kept_total
removed_duplicate
canonical_unique
cross_source_duplicate
possible_duplicate
unique_contribution_rate
```

을 산출한다.

로그만 찍고 버리지 말고 기존 운영 result/report 구조에서 사용 가능하게 한다. 새로운 DB는 만들지 않는다.

---

# 6. PARALLEL LANE D — Tier1 Source Health 운영연결

Tier1:

```text
bizinfo
kstartup
```

병렬로 조사/테스트하고 독립 모듈 수정은 가능한 즉시 구현한다.

필수:

1. `parse_rate=1.0` 하드코딩 제거
2. 실제 item_count/required-field quality/missing title/missing URL 등 기존 coverage 신호 재사용
3. fetch exception이 source health까지 도달
4. `previous_item_count` 실제 전달로 급감감지
5. 실제 alert 없이 `mark_alerted()`만 하는 문제 금지
6. FAILING/DEGRADED/STALE/RECOVERED/cooldown 상태전이 테스트
7. alert 성공 후에만 alert timestamp 기록

정책:

```text
0건 또는 품질저하 → DEGRADED
명확한 fetch/parse failure → FAILING
장애 지속 → cooldown 후 재알림 가능
복구 → RECOVERED 1회
```

실제 외부 alert는 보내지 않고 mock한다.

기존 coverage_alert/MDR/ntfy/email 구조를 재사용한다.

---

# 7. PARALLEL LANE E — accuracy/golden/OX 검증체계 교정

`scripts/validate_golden.py` 및 관련 accuracy 도구를 독립 lane으로 개선한다.

## E1. ground truth 분리

다음을 조사:

```text
data/golden/
feedback_labels.jsonl
review_queue
O/X feedback
accuracy matrix
```

라벨 역할을 섞지 않는다.

```text
region ground truth
relevance ground truth
support-type ground truth
applicant-role ground truth
deadline ground truth
```

`region_labels.jsonl`을 prestartup relevance truth로 사용 금지.

## E2. 실제 group config

가능하면 실제 `config/groups.json`의 `grp_prestartup_ai`를 사용하고 임의 하드코딩 group config 제거.

## E3. metric

실제 relevance O/X truth가 있을 때만:

```text
TP
FP
TN
FN
precision
recall
F1
```

truth가 없으면 `NOT_MEASURABLE`.

unlabeled corpus는:

```text
INCLUDE
EXCLUDE
CONDITIONAL
HUMAN_REVIEW
POSSIBLE_DUPLICATE
reason/support/deadline 분포
```

만 측정.

라벨 없는 데이터를 FP=0/FN=0으로 보고 금지.

---

# 8. PARALLEL LANE F — grp_prestartup_ai 회귀 + 실데이터

독립 테스트 fixture와 corpus 검증을 가능한 병렬로 진행한다.

## 포함 잠금

```text
사업화자금 + 멘토링
시제품비 + 교육
사업비 + 입주공간
바우처 + 컨설팅
예비창업 + 기존기업 혼합 모집
전국 대상 지방기관 공고
서울/경기/인천
R&D/PoC 비용지원
IP/마케팅/수출 비용지원
```

## 제외 잠금

```text
교육 only
멘토링 only
컨설팅 only
투자 only
공간 only
운영기관 모집
수행기관 모집
입찰
위원 모집
행정고지
결과발표
마감
```

역할:

```text
예비창업자를 지원할 운영기관 모집 → applicant=기관 → 제외
예비창업자 모집 / 운영기관=OO센터 → applicant=예비창업자 → 후보
개인 단독 표현 → 예비창업 확정 금지
```

실데이터 최소 200건, 가능하면 2,000~3,000건 이상.

labeled truth가 없으면 accuracy라고 부르지 않는다.

---

# 9. PARALLEL LANE G — version / delivery / outbox / seen_ids 통합회귀

mock/dry-run 전용.

```text
수집
→ canonical dedup
→ version
→ filtering
→ outbox
→ recipient checkpoint
→ delivery cycle complete
→ seen_ids
```

시나리오:

```text
같은 run 재실행
일부 그룹 성공 후 crash
retry
다른 delivery_slot
deadline extension
exact repost
FETCH/PARSE failure 후 다음 정상 enrich
multi-group shared notice
```

목표:

- 중복메일 없음
- 미완료 그룹 누락 없음
- thin snapshot 허위 version mail 없음
- 중요변경 재발송 유지

실 SMTP 금지.

---

# 10. PARALLEL LANE H — pre-existing 실패 + 운영안정화

핵심 lane들이 진행되는 동안 독립적으로 원인분석 가능.

현재/과거 후보:

```text
test_core_sources_checklist
test_kstartup_collect_policy
test_send_health_guard
Windows cp949/UTF-8
```

최신 main에서 실제 재현 여부부터 확인.

재현되면 원인을 고치고 회귀테스트를 추가한다.

환경 의존이라 확실히 고칠 수 없으면 `BLOCKED_WITH_EVIDENCE`로 기록한다.

추가로 안전한 범위에서:

```text
unused/dead code
stale TODO/FIXME
report-code mismatch
잘못된 완료표기
duplicate helper
import smoke
workflow YAML parse
state atomic write/concurrency
```

를 조사하고 명확한 결함은 수정한다.

대규모 미관 리팩터링은 하지 않는다.

---

# 11. CORE LANES 이후 자동 확장 — 저장소 전체 SAFE BACKLOG HARVEST

A~H가 끝났거나 독립 작업이 대기 중이면 사용자에게 새 기능을 묻지 않는다.

저장소에서 다음을 조사한다.

```text
TASKS.md
TODO
FIXME
PARTIAL
BLOCKED
최근 결과보고서
최근 PR 리뷰 지적
pre-existing failing tests
accuracy defect artifacts
MDR/coverage warnings
source health incidents
```

그중 **현재 mail 프로젝트 목적과 직접 관련되고, 안전하며, secret/운영승인이 필요 없는 P0/P1/P2 작업**을 추출해 계속 구현한다.

우선순위:

```text
P0 실제 누락/중복발송/데이터손실/실발송안전
→ P1 정확도/수집건전성/상태추적/회귀
→ P2 성능/관측성/코드안정화/테스트
```

새로운 상품기능, UI 대개편, 운영정책 변경처럼 사용자 의사결정이 필요한 것은 임의 구현하지 않는다.

---

# 12. 병렬 작업 통합 규칙

여러 lane이 별도 branch/worktree에서 수정됐다면:

1. 각 lane 테스트 통과
2. 변경사항 자체 리뷰
3. hot file 충돌을 의미 기준으로 해결
4. 한 통합 브랜치로 모음
5. lane 간 상호작용 테스트
6. 전체 회귀

단순히 Git conflict marker만 제거하지 말고 양쪽 의미를 보존한다.

특히 `monitor.py` 충돌 시:

```text
return contract
POSSIBLE_DUPLICATE
dedup metrics
source health
version/delivery
```

기능이 서로 사라지지 않았는지 확인한다.

---

# 13. 테스트/검증

각 lane별 targeted tests는 병렬 실행 가능하면 병렬로 실행한다.

최종 통합 후 반드시 가능한 범위에서:

```text
python -m pytest tests/ -q --tb=short
```

추가:

```text
monitor import smoke
accuracy harness
golden integrity
dedup benchmark
workflow YAML validation
grp_prestartup_ai regression
version/delivery integration
source health state transition
```

실패는:

```text
new regression
pre-existing
환경 BLOCKED
```

으로 구분한다.

테스트를 삭제/skip해서 맞추지 않는다.

---

# 14. 커밋/PR

기능군 단위로 커밋한다.

예:

```text
fix(contract): restore monitor result compatibility
fix(dedup): wire possible duplicates and truthful metrics
fix(source-health): use real Tier1 outcomes and alerts
fix(accuracy): separate relevance truth from region labels
test(integration): harden delivery and prestartup regressions
```

작은 commit 하나 후 멈추지 않는다.

완료된 통합 브랜치는 push하고 PR 생성/업데이트까지 한다.

**main 병합 금지.**

내일 사용자가 PR 하나 또는 명확히 분리된 소수 PR을 한 번에 검토할 수 있게 한다.

---

# 15. 최종 보고서

작성:

```text
docs/UNATTENDED_AUTODEV_RESULT_20260812.md
```

반드시 실제 사실만 기록:

```text
시작 main SHA
통합 branch
병렬 lane별 상태
실제 발견 결함
수정 결함
변경 파일
커밋 목록
테스트 결과
실데이터 건수/결과
benchmark
accuracy measurable 여부 및 지표
source health 상태
version/delivery 회귀
pre-existing failure 처리
BLOCKED_WITH_EVIDENCE
PR URL
main 미병합 확인
남은 작업
```

상태값:

```text
NOT_STARTED
PARTIAL
IMPLEMENTED
TESTED
REAL_DATA_VALIDATED
BLOCKED
```

다음 혼동 금지:

```text
IMPLEMENTED ≠ TESTED
TESTED ≠ REAL_DATA_VALIDATED
PR_CREATED ≠ MERGED
unlabeled corpus ≠ accuracy truth
함수 존재 ≠ 운영 연결
```

---

# 16. 최종 지시

지금부터 `MAIL-01 → MAIL-08` 식으로 하나씩 기다리는 방식으로 일하지 마라.

**A~H lane을 동시에 진행 가능한 만큼 병렬로 착수**한다.

- 독립 조사/테스트/모듈은 병렬
- 같은 hot file 실제 patch만 안전하게 통합
- 한 lane이 BLOCKED여도 나머지는 계속
- core lane 완료 후 SAFE BACKLOG HARVEST까지 자동 진행
- 사용자 입력을 기다리지 않음
- 실제 외부발송/파괴작업 금지
- 마지막에 통합테스트 + 보고서 + push + PR
- main은 병합하지 않음

사용자가 다음에 확인할 때는 선택 질문이 아니라 **완료된 결과와 검토할 PR**을 보여줘야 한다.
