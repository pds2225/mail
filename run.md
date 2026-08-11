# MAIL 1시간 무인 자동개발 프롬프트

## 목적
나는 1시간 이상 PC 앞에 없을 예정이다. 이 세션 동안 사용자 승인·선택·확인을 요구하지 말고, 안전하게 실행 가능한 작업이 남아 있는 동안 스스로 우선순위를 판단하여 연속 개발하라.

금지 문구:
- 계속할까요?
- 다음 작업을 지정해주세요.
- 무엇을 할까요?
- 승인해주세요.
- NEXT만 적고 종료

기능 하나, 테스트 하나, 커밋 하나, PR 하나를 완료했다고 세션을 종료하지 마라.

---

## 0. 시작 시 최신 상태 확인

대상 저장소: `pds2225/mail`

이 프롬프트 작성 시점 원격 main에는 PR #240, #241, #242까지 병합되어 있다. 그러나 반드시 실제 최신 원격을 다시 확인한다.

시작 순서:

```text
git fetch origin
git status
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
```

`origin/main`이 더 최신이면 항상 최신 `origin/main`을 baseline으로 삼아라.

working tree가 clean이면 최신 main에서 새 브랜치를 만든다.

권장 브랜치:

```text
feat/unattended-pipeline-hardening-20260809
```

사용자/다른 세션의 미커밋 변경이 있으면 절대 삭제·덮어쓰기하지 말고 가능한 경우 별도 worktree 또는 안전한 새 브랜치를 사용하라.

---

## 1. 절대 금지

무인 실행 중 다음은 하지 않는다.

```text
main 직접 개발
main 자동 merge
PR 자동 merge
force push
git reset --hard
git clean -fd
사용자 미커밋 파일 삭제
.env 수정
API key / secret 수정 또는 출력
운영 DB destructive migration
운영 데이터 삭제
실제 이메일 대량발송
실제 ntfy 테스트 발송
Vercel /api/run 실발송
외부 유료 API 대량 호출
테스트 삭제/skip으로 통과시키기
기존 안전게이트 제거
```

메일/알림 검증은 preview, dry-run, mock, fixture 범위에서만 한다.

---

## 2. 무정지 실행 규칙

작업 루프:

```text
코드 조사
→ 실제 결함 확인
→ 구현
→ 관련 테스트
→ 실패 수정
→ 커밋
→ 다음 우선순위 자동 선택
→ 계속 반복
```

작업 하나가 BLOCKED여도 전체를 멈추지 말고 해당 항목만 기록한 뒤 다음 독립 작업으로 넘어가라.

사소한 설계 판단이 필요하면 질문하지 말고 다음 우선순위로 결정하라.

1. backward compatibility
2. 누락 방지
3. fail-closed
4. 운영 실발송 방지
5. 기존 public API/return contract 보존
6. 최소 변경

---

# MILESTONE A — PR #242 이후 return contract 회귀 감사/수정

PR #242에서 운영 KPI를 추가하면서 `execute_monitor()` 정상 반환값에서 기존 필드 일부가 제거된 흔적이 있다.

다음 기존 필드의 consumer를 저장소 전체에서 조사하라.

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

`write_today_missing_risk_report()`, `api/`, `scripts/`, `mail_core/`, workflow, tests, docs를 확인한다.

기존 contract가 필요한 필드는 삭제하지 말고 복구하고, 신규 KPI도 유지해서 backward-compatible하게 만든다.

최소 검증:

```text
normal result
empty filtered result
send_hold result
date review queue result
missing-risk report
api/run consumer
monitor_dry_run consumer
```

---

# MILESTONE B — POSSIBLE_DUPLICATE 실제 운영경로 연결

현재 `detect_possible_duplicates()` 함수는 존재하지만 실제 `execute_monitor()` 경로에서 호출되는지 확인한다. 호출되지 않는다면 연결한다.

원칙:

```text
확정 canonical duplicate ≠ POSSIBLE_DUPLICATE
POSSIBLE_DUPLICATE는 자동 merge 금지
자동 삭제 금지
정상 INCLUDE 후보를 조용히 제거 금지
```

권장 흐름:

```text
all_items
→ exact/canonical dedup
→ POSSIBLE_DUPLICATE detection
→ version/enrich/evaluate
→ diagnostics/review metadata
```

가능하면 다음 metadata를 남긴다.

```text
_possible_duplicate
_possible_duplicate_with
_possible_duplicate_score
_possible_duplicate_reason
```

다음은 서로 다른 공고로 보수적으로 유지한다.

```text
2025 vs 2026
서울 vs 부산
1차 vs 2차
본모집 vs 추가모집
명확히 다른 접수기간/차수
```

검토 신호는 HUMAN_REVIEW 또는 기존 diagnostics 체계에 연결하되 자동 제외하지 않는다.

---

# MILESTONE C — POSSIBLE_DUPLICATE 성능 개선

현재 모든 item pair 비교 O(n²)인지 확인한다.

실제 raw corpus 2,000건 이상, 가능하면 전체로 성능을 측정한다.

안전하게 후보를 줄일 수 있으면 다음을 활용한다.

```text
year bucket
normalized issuer
title token prefix
region
round
```

목표는 false merge 증가 없이 비교량을 줄이는 것이다.

보고서에 남길 것:

```text
items
candidate pairs before
after
elapsed
possible duplicate count
```

---

# MILESTONE D — dedup KPI 의미 교정

다음 KPI 계산이 실제 의미와 맞는지 검증한다.

```text
same_source_dedup_count
cross_source_dedup_count
version_change_count
deadline_excluded_count
admin_excluded_count
```

특히 단순히 `len(all_items)-len(deduped)`를 same-source dedup으로 부르거나, canonical id가 있는 kept item 수를 cross-source duplicate count로 부르면 안 된다.

실제 dedup 원인을 계측해서 최소 다음으로 분리한다.

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

동일 item의 중복 double-count를 방지한다.

기존 `dedup_items(items) -> list[dict]` public signature를 깨지 말고 optional stats collector 또는 helper를 사용하라.

---

# MILESTONE E — attachment hash 의미 바로잡기

현재 `attachment_hash()`가 실제 파일 bytes가 아니라 link/title/deadline 조합을 md5 처리하는지 확인한다.

그렇다면 이것은 실제 attachment content hash가 아니다.

저장소에서 실제 attachment URL/metadata/downloaded file/SHA-256/파일크기 등을 먼저 조사한다.

실제 content hash가 존재하면 그 값을 중복 보조 신호로 연결한다.

실제 content hash가 없다면 거짓 이름을 쓰지 말고 의미에 맞게 예를 들어 다음처럼 정리한다.

```text
_notice_signature_hash
metadata_signature
```

persisted state 호환이 필요하면 alias/backward compatibility를 둔다.

---

# MILESTONE F — Source Health 실제 운영 연결 완성

현재 source health는 구현되어 있지만 운영 데이터 연결을 감사한다.

## F-1. hardcoded parse_rate 제거

Tier1 상태 업데이트에서 `parse_rate=1.0` 하드코딩이 있으면 제거한다.

기존 coverage/page_stat 인프라를 재사용해서 가능한 실제 신호를 연결한다.

```text
item_count
valid_record_count
required-field parse rate
missing title
missing URL
processed pages
expected pages
latest notice date
previous item count
fetch error
```

## F-2. fetch failure 전달

`fetch_all()`에서 source별 exception이 로그만 남고 사라지는지 확인한다.

그렇다면 backward compatibility를 유지하면서 source별 outcome을 전달할 수 있게 한다.

```text
source_id
success
item_count
error
parse quality
```

특히 Tier1:

```text
bizinfo
kstartup
```

의 실패가 source_health까지 도달해야 한다.

## F-3. 급감 감지 실제 연결

`classify_source_status()`가 `previous_item_count`를 지원하면서 실행경로에서 전달하지 않는다면 연결한다.

예: 전회 1000 → 현재 100이면 DEGRADED.

## F-4. 알림 실제 연결

`should_alert() -> log.warning() -> mark_alerted()`만 하고 실제 alert가 없다면 수정한다.

실제 알림 성공 전 `mark_alerted()`하지 마라.

기존 `alert_ntfy`, `alert_email`, coverage alert, MDR 중 적절한 구조를 재사용하고 테스트에서는 mock한다.

실제 외부 알림은 보내지 않는다.

## F-5. 상태정책

```text
0건/파싱률 저하 → DEGRADED
명확한 fetch/parse failure → FAILING
장애 지속 → cooldown
복구 → RECOVERED 1회
```

Tier1 장애를 너무 오래 숨기지 않도록 기존 정책을 점검한다.

---

# MILESTONE G — accuracy 자동화 전면 교정

현재 `scripts/validate_golden.py`가 진짜 TP/FP/TN/FN, precision/recall을 계산하는지 확인한다.

`region_labels.jsonl`은 지역 정답이지 예비창업 공고 relevance 정답이므로 그대로 prestartup accuracy ground truth로 사용하지 마라.

## G-1. ground truth 역할 분리

기존 다음을 조사한다.

```text
data/golden/
feedback_labels.jsonl
review queue
O/X feedback
accuracy matrix
```

라벨 역할을 분리한다.

```text
region ground truth
relevance ground truth
support-type ground truth
applicant-role ground truth
deadline ground truth
```

## G-2. 실제 grp_prestartup_ai 설정 사용

스크립트 내부에 임의 group config를 하드코딩하지 말고 가능하면 `config/groups.json` 등 실제 설정에서 `grp_prestartup_ai`를 읽는다.

## G-3. 진짜 metric

실제 relevance O/X ground truth가 존재할 때만 계산:

```text
TP
FP
TN
FN
precision
recall
F1
```

정답 라벨이 없으면 `NOT_MEASURABLE`이라고 명확히 표시한다.

라벨이 없는데 FP=0, FN=0이라고 보고하지 마라.

## G-4. labeled benchmark와 real-data smoke 분리

Labeled benchmark에서는 precision/recall을 측정한다.

Unlabeled real-data corpus에서는 다음만 집계한다.

```text
INCLUDE
EXCLUDE
CONDITIONAL
HUMAN_REVIEW
POSSIBLE_DUPLICATE
deadline 분포
support 분포
reason 분포
```

unlabeled corpus를 FP/FN이라고 부르지 않는다.

---

# MILESTONE H — 예비창업 실데이터 검증 재수행

기존 200건 검증이 INCLUDE 0 / EXCLUDE 200이었다면 recall 검증으로 충분하지 않다.

실데이터에서 최소 다음 양성 후보를 확보해 검증한다.

```text
예비창업자 사업화자금
시제품 제작비
사업비 + 멘토링
사업화 + 교육
R&D/PoC 비용지원
바우처
IP 비용지원
마케팅/수출 비용지원
```

음성도 포함한다.

```text
교육 only
멘토링 only
컨설팅 only
투자 only
공간 only
운영기관 모집
수행기관 모집
입찰
결과발표
마감공고
```

확정 label이 있으면 사용하고, 없으면 fixture/regression test로 보강하되 실데이터에 임의 정답을 붙여 accuracy라고 주장하지 않는다.

---

# MILESTONE I — grp_prestartup_ai 핵심 회귀테스트 확장

반드시 포함되어야 하는 케이스:

```text
사업화자금 + 멘토링
시제품비 + 교육
사업비 + 입주공간
바우처 + 컨설팅
예비창업 + 기존기업 혼합 모집
전국 대상 지방기관 공고
서울/경기/인천
```

반드시 제외되어야 하는 케이스:

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

역할 판정:

```text
“예비창업자를 지원할 운영기관 모집” → applicant=기관 → 제외
“예비창업자 모집 / 운영기관=OO센터” → applicant=예비창업자 → 후보
```

`개인`이라는 단어만으로 예비창업자 인정 금지.

Dedup 회귀:

```text
2025 vs 2026 별도
서울 vs 부산 별도
1차 vs 2차 별도
본모집 vs 추가모집 별도
마감연장은 중요변경
```

---

# MILESTONE J — version / delivery / seen_ids 통합 회귀

최근 여러 PR이 동시에 수정한 영역:

```text
canonical_notice_id
notice versions
outbox
seen_ids
delivery_slot
multi-group delivery cycle
FETCH/PARSE unreliable handling
```

통합 흐름을 테스트한다.

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
부분 그룹 발송 성공 후 crash
retry
다른 delivery_slot
deadline extension
exact repost
FETCH failure 후 다음 정상 enrich
```

목표:

```text
중복 메일 없음
미완료 그룹 누락 없음
thin snapshot으로 허위 version mail 없음
중요변경 재발송 유지
```

실제 SMTP는 사용하지 않는다.

---

# MILESTONE K — pre-existing 테스트 실패 조사

주요 작업이 안정화된 뒤에도 시간이 남으면 기존 보고서에 기록된 실패를 조사한다.

```text
test_core_sources_checklist
test_kstartup_collect_policy
test_send_health_guard
```

Windows cp949/UTF-8 환경 문제도 실제 재현 가능하면 안전하게 수정한다.

테스트 기대값만 바꿔 결함을 숨기지 않는다.

확실한 수정이 불가능하면 `BLOCKED_WITH_EVIDENCE`로 기록하고 다음으로 넘어간다.

---

# MILESTONE L — result payload contract audit

저장소 전체에서 `execute_monitor()`, `main()`, `result.get(...)` 주요 consumer를 조사한다.

이번처럼 반환 필드가 실수로 사라져 downstream이 깨지는 일을 막기 위해 최소 contract regression test 또는 가능한 범위의 TypedDict/dataclass를 검토한다.

대규모 구조개편은 하지 않는다.

---

# MILESTONE M — source contribution 지표 교정

소스별 최소 다음을 올바른 분모로 계산한다.

```text
collected_total
kept_total
removed_duplicate
canonical_unique
cross_source_duplicate
possible_duplicate
unique_contribution_rate
```

로그만 찍고 버리지 말고 기존 KPI/report 구조에서 활용 가능하게 한다.

새 DB는 만들지 않는다.

---

# 테스트 전략

각 milestone마다 관련 테스트를 실행하되 중간 통과 후 멈추지 않는다.

마지막에는 저장소 공식 명령을 우선 확인하고 전체 테스트를 실행한다.

최소 후보:

```text
python -m pytest tests/ -q --tb=short
accuracy harness
golden integrity
monitor import smoke
workflow/YAML validation
dedup performance smoke
grp_prestartup_ai targeted regression
```

실패는 이번 변경으로 발생한 것과 pre-existing을 구분한다.

이번 변경으로 발생한 실패는 수정한다.

---

# 실데이터 정책

로컬에 이미 존재하는 다음을 우선 사용한다.

```text
var/raw
data/golden
feedback labels
accuracy artifacts
```

실데이터 검증은 최소 200건 이상, 가능하면 기존 전체 raw corpus를 사용한다.

unlabeled corpus에서 FP/FN 수치를 만들어내지 않는다.

---

# 커밋 정책

관련 기능군 단위로 커밋한다.

예:

```text
fix(contract): restore monitor result compatibility after P2 KPI changes
fix(dedup): wire possible-duplicate detection into monitor pipeline
fix(metrics): make dedup and source contribution KPIs truthful
fix(source-health): wire real Tier1 collection outcomes and alerts
fix(accuracy): separate labeled metrics from unlabeled corpus validation
test(integration): harden version delivery and prestartup pipeline
```

매 파일마다 커밋하지 않는다.

커밋 후 사용자 입력을 기다리지 않는다.

---

# 원격 정책

작업 브랜치 push 허용.

모든 작업 후 PR 생성 허용.

권장 PR 제목:

```text
fix: harden P2 monitor pipeline and accuracy validation
```

하지만 main merge / auto-merge는 금지한다.

GitHub 인증 문제로 push/PR이 안 되면 로컬 커밋까지 완료하고 BLOCKED로 기록한 뒤 다른 개발은 계속한다.

---

# 최종 보고서

다음 파일 작성:

```text
docs/UNATTENDED_AUTODEV_RESULT_20260809.md
```

반드시 포함:

```text
시작 main SHA
작업 branch
발견한 실제 결함
수정한 결함
변경 파일
커밋 목록
POSSIBLE_DUPLICATE 운영 연결 상태
dedup KPI 정의와 실제 수치
source health 연결 상태
accuracy benchmark 방식
labeled benchmark 결과
unlabeled corpus 검증 건수와 분포
전체 테스트 결과
기존 테스트 실패 여부
성능 측정
기존 그룹 회귀 여부
BLOCKED
PR URL
main 미병합 확인
다음 우선순위
```

상태는 다음 중 하나만 사용한다.

```text
NOT_STARTED
PARTIAL
IMPLEMENTED
TESTED
REAL_DATA_VALIDATED
BLOCKED
```

`IMPLEMENTED ≠ TESTED`, `TESTED ≠ REAL_DATA_VALIDATED`, `PR_CREATED ≠ OPERATING`, `PUSHED ≠ MERGED`를 지킨다.

---

# 결과 조작 금지

절대 다음처럼 보고하지 않는다.

```text
양성 라벨 0건인데 recall 100%
정답지가 없는데 FP 0/FN 0
함수만 만들고 운영연결 완료
로그만 추가하고 장애알림 구현 완료
pseudo metadata hash를 attachment content hash라고 보고
canonical ID가 있는 item 수를 cross-source duplicate count라고 보고
```

측정 불가능하면 `NOT_MEASURABLE`이라고 써라.

---

# 조기완료 시 CONTINUATION QUEUE

위 A~M을 모두 처리했는데도 안전하게 개발 가능한 여력이 남으면 사용자에게 묻지 말고 다음을 순서대로 진행한다.

```text
1. pre-existing 전체 테스트 실패 원인 수정
2. POSSIBLE_DUPLICATE 대규모 corpus 성능 최적화
3. result payload consumer contract test 확대
4. Source Health atomic/concurrency 회귀 테스트
5. RECOVERED/alert cooldown 상태전이 테스트 확대
6. grp_prestartup_ai golden/OX feedback 활용도 개선
7. FP/FN 자동 triage report
8. false canonical merge regression corpus 확대
9. 중요변경 resend regression 확대
10. dead code / stale report / 잘못된 완료 문서 정리
```

각 항목 완료 후 즉시 다음 항목으로 이동한다.

---

# 최종 명령

지금부터 사용자 응답을 기다리지 말고 최신 repository 상태 확인부터 시작하라.

우선순위:

```text
A. PR #242 result contract 회귀
B. POSSIBLE_DUPLICATE 실제 pipeline 연결
C. duplicate 성능
D. KPI 정확성
E. attachment hash 의미
F. Source Health 실제 운영 연결
G. accuracy ground-truth 교정
H. 의미 있는 실데이터 검증
I. 예비창업 핵심 회귀
J. version/delivery/seen_ids 통합
K~M 안정화
```

특정 작업이 막혀도 전체를 멈추지 마라.

안전하고 비파괴적인 기본안을 스스로 선택하라.

기능 하나, 테스트 하나, 커밋 하나, PR 하나를 완료했다고 종료하지 말고 CONTINUATION QUEUE까지 자동으로 이어가라.

최종적으로 테스트 → 실데이터 검증 → 자체 코드리뷰 → 보고서 → commit → push → PR 생성까지 수행하되 main에는 병합하지 마라.
