# CURRENT AI TASK — MAIL

> 이 파일은 `pds2225/mail`의 현재 AI 작업지시 단일 기준이다.
> 로컬 프롬프트를 별도로 만들지 말고, 항상 원격 `main/TASK.md`를 처음부터 끝까지 읽고 작업한다.

## 실행 모드

- 사용자에게 승인/선택/다음 작업을 묻지 않는다.
- `계속할까요?`, `다음 작업을 지정해주세요`, `NEXT`만 출력하고 종료하는 행동 금지.
- 안전하게 실행 가능한 작업이 남아 있으면 자동으로 다음 항목을 계속한다.
- 기능 하나, 테스트 하나, 커밋 하나 끝났다고 멈추지 않는다.
- 특정 항목이 막히면 `BLOCKED`로 기록하고 다음 독립 작업을 계속한다.
- 실제 이메일/ntfy 발송 금지. preview/dry-run/mock만 사용.
- main 직접 개발/자동 merge/force push/reset --hard/git clean -fd/.env·secret 수정 금지.
- 사용자 미커밋 파일을 삭제하거나 덮어쓰지 않는다.
- 새 브랜치에서 작업하고 push/PR 생성까지 가능하지만 main 병합은 금지한다.

---

# TASK MAIL-01 — execute_monitor() 반환계약 복구

## 배경

PR #242 이후 `execute_monitor()` 정상 return path에서 기존 consumer가 기대하는 필드가 빠진 상태가 확인되었다.

현재 감사 결과상 정상 경로에서 누락된 핵심 필드:

- `send_hold`
- `send_hold_reason`
- `run_status`
- `date_matched_count`
- `date_unknown_items`
- `date_review_queue`
- `date_review_queue_count`
- `date_excluded_count`

특히 다음 consumer가 실제값 대신 0/빈 배열을 읽을 수 있다.

- `write_today_missing_risk_report()`
- `_measure_recall_risk()`
- `run_dry_run()`
- main CLI summary/log
- `api/run.py` 직접 caller
- 관련 테스트/리포트

## 구현 요구

`execute_monitor()`의 모든 주요 return path가 일관된 contract를 갖도록 수정한다.

정상 경로에서 최소 다음 값을 실제 내부 상태 기준으로 반환한다.

```text
send_hold = 현재 collection_gate의 send_hold
send_hold_reason = effective_allow_send()에서 계산된 실제 hold_reason
run_status = collection_gate의 run_status 또는 의미상 적절한 기본 상태
date_matched_count = 실제 date_matched 건수
date_unknown_items = len(date_unknown)
date_review_queue = 실제 date_review_queue 배열
date_review_queue_count = len(date_review_queue)
date_excluded_count = len(date_excluded)
```

기존 PR #242의 신규 KPI는 삭제하지 말고 유지한다.

즉 기존 contract + 신규 KPI를 동시에 제공한다.

wrapper(`run_dry_run`, CLI)가 나중에 값을 덧붙이는 것에 의존하지 말고 `execute_monitor()` 직접 호출만으로도 contract가 완전해야 한다.

## 테스트 요구

최소 다음을 검증한다.

1. normal path 반환계약
2. no filtered items early-return 계약
3. send_hold 경로
4. `write_today_missing_risk_report()`가 실제 count/queue를 받는지
5. `api/run.py` 직접 caller 호환
6. `scripts/monitor_dry_run.py` 호환
7. 기존 consumer가 기대하던 field가 빠지지 않는 contract regression test

테스트 기대값만 바꿔 결함을 숨기지 않는다.

완료 후 관련 테스트를 실행하고 의미 있는 단위로 커밋한다.

---

# TASK MAIL-02 — POSSIBLE_DUPLICATE 실제 파이프라인 연결

MAIL-01이 완료되면 사용자에게 묻지 말고 즉시 진행한다.

현재 `detect_possible_duplicates()` 함수는 존재하지만 `execute_monitor()` 운영 경로에 실제 연결되어 있는지 재확인한다.

미연결이면 다음 흐름으로 연결한다.

```text
all_items
→ 확정 canonical/exact dedup
→ POSSIBLE_DUPLICATE detection
→ version/enrich/evaluate
→ diagnostics/review metadata
```

원칙:

- POSSIBLE_DUPLICATE는 자동 merge/삭제하지 않는다.
- 확정 duplicate와 분리한다.
- 2025 vs 2026, 서울 vs 부산, 1차 vs 2차, 본모집 vs 추가모집은 보수적으로 별도 공고 유지.
- 가능하면 `_possible_duplicate`, `possible_duplicate_with`, `possible_duplicate_score`, `possible_duplicate_reason`을 남긴다.
- 정상 INCLUDE 후보를 POSSIBLE_DUPLICATE라는 이유만으로 제거하지 않는다.
- 관련 HUMAN_REVIEW/diagnostic 경로에 노출 가능한지 확인한다.

실데이터 2,000건 이상 가능하면 성능도 측정한다. O(n²) 병목이 확인되면 recall을 해치지 않는 후보 축소를 적용한다.

---

# TASK MAIL-03 — KPI 의미 교정

현재 신규 KPI가 실제 의미와 맞는지 검증하고 수정한다.

특히:

```text
same_source_dedup_count
cross_source_dedup_count
version_change_count
deadline_excluded_count
admin_excluded_count
```

`len(all_items)-len(deduped)`를 same-source로 부르는 식의 잘못된 집계를 허용하지 않는다.

가능하면 실제 dedup 이유 기준으로 다음을 산출한다.

```text
input_count
output_count
duplicate_removed_total
same_source_duplicate_removed
cross_source_duplicate_removed
canonical_duplicate_removed
title_duplicate_removed
attachment_duplicate_removed
possible_duplicate_count
```

중복 원인이 여러 개여도 double-count되지 않도록 정의한다.

기존 `dedup_items(items) -> list[dict]` public signature를 깨지 않는 방향을 우선한다.

---

# TASK MAIL-04 — attachment hash 의미 교정

현재 `attachment_hash`라는 이름이 실제 첨부파일 bytes가 아니라 link/title/deadline metadata 조합 hash라면 의미가 잘못되었다.

저장소에 실제 attachment content hash/sha256/다운로드 metadata가 있는지 먼저 조사한다.

- 실제 content hash가 있으면 그것을 dedup 보조 신호로 연결.
- 없다면 가짜로 attachment hash라고 부르지 말고 `metadata_signature` 또는 동등한 의미의 이름으로 정리.
- persisted state/기존 호출과 호환성이 필요하면 alias/backward compatibility 유지.

---

# TASK MAIL-05 — Source Health 실제 운영 연결

현재 Tier1 source health 구현을 실제 수집 결과와 연결한다.

Tier1:

- `bizinfo`
- `kstartup`

반드시 확인/수정:

1. `parse_rate=1.0` 하드코딩 제거
2. 실제 item_count/required-field parse quality/missing title/missing URL 등 기존 coverage 신호 재사용
3. fetch exception이 source health까지 전달되는지
4. previous_item_count를 실제로 전달하여 급감 감지
5. `should_alert()` 후 실제 alert 없이 `mark_alerted()`만 하는 오류가 없는지
6. 장애/쿨다운/복구 상태전이 테스트

실제 외부 alert는 테스트 중 보내지 말고 mock한다.

---

# TASK MAIL-06 — accuracy ground truth 교정

`scripts/validate_golden.py`가 실제 TP/FP/TN/FN/precision/recall을 계산하는지 검증한다.

`region_labels.jsonl`은 region 정답이지 prestartup relevance 정답으로 간주하면 안 된다.

다음을 분리한다.

```text
region ground truth
relevance ground truth
support-type ground truth
applicant-role ground truth
deadline ground truth
```

실제 relevance O/X ground truth가 있는 경우에만:

```text
TP
FP
TN
FN
precision
recall
F1
```

을 계산한다.

라벨이 없으면 `NOT_MEASURABLE`로 명시한다.

unlabeled raw corpus에서는 FP/FN이라고 부르지 말고 INCLUDE/EXCLUDE/HUMAN_REVIEW/POSSIBLE_DUPLICATE/reason 분포만 집계한다.

가능하면 실제 `config/groups.json`의 `grp_prestartup_ai` 설정을 사용하고 스크립트 내부 임의 group config를 제거한다.

---

# TASK MAIL-07 — 실데이터 + 핵심 회귀 검증

최소 200건, 가능하면 기존 2,000~3,000건 이상 raw corpus 사용.

포함 회귀:

- 사업화자금 + 멘토링
- 시제품비 + 교육
- 사업비 + 입주공간
- 바우처 + 컨설팅
- 예비창업 + 기존기업 혼합
- 전국 대상 지방기관 공고
- 서울/경기/인천

제외 회귀:

- 교육 only
- 멘토링 only
- 컨설팅 only
- 투자 only
- 공간 only
- 운영기관/수행기관 모집
- 입찰/위원/행정고지/결과발표/마감

역할 구분:

- `예비창업자를 지원할 운영기관 모집` → applicant=기관 → 제외
- `예비창업자 모집 / 운영기관=OO센터` → applicant=예비창업자 → 후보
- `개인` 단독 표현만으로 예비창업 인정 금지

Dedup/version 회귀:

- 2025 vs 2026 별도
- 서울 vs 부산 별도
- 1차 vs 2차 별도
- 본모집 vs 추가모집 별도
- 마감연장은 중요변경

---

# TASK MAIL-08 — version / delivery / seen_ids 통합회귀

다음 전체 흐름을 mock/dry-run으로 테스트한다.

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

1. 같은 run 재실행
2. 일부 그룹 발송 성공 후 crash
3. retry
4. 다른 delivery_slot
5. deadline extension
6. exact repost
7. FETCH failure 후 다음 정상 enrich

목표:

- 중복 메일 없음
- 미완료 그룹 누락 없음
- thin snapshot 허위 version mail 없음
- 중요변경 재발송 유지

실 SMTP 금지.

---

# 작업 종료/보고

위 TASK MAIL-01~08을 안전하게 처리 가능한 만큼 연속으로 수행한다.

작은 작업 하나 끝났다고 멈추지 않는다.

마지막에:

1. 전체 관련 테스트
2. 가능하면 전체 `python -m pytest tests/ -q --tb=short`
3. 자체 코드리뷰
4. 실데이터 검증
5. 결과보고서 작성
6. commit/push
7. PR 생성

까지 수행한다.

결과보고서:

```text
docs/UNATTENDED_AUTODEV_RESULT_20260812.md
```

상태는 다음 값만 사용한다.

```text
NOT_STARTED
PARTIAL
IMPLEMENTED
TESTED
REAL_DATA_VALIDATED
BLOCKED
```

PR을 만들더라도 main에는 병합하지 않는다.

최종 보고에는 반드시:

- 시작 main SHA
- 작업 branch
- 실제 발견 결함
- 수정 결함
- 변경 파일
- 커밋 목록
- 테스트 결과
- 실데이터 검증 결과
- BLOCKED
- PR URL
- main 미병합 확인
- 다음 우선순위

을 기록한다.

## 최종 지시

지금부터 사용자 입력을 기다리지 말고 `MAIL-01`부터 시작한다.

완료 후 `MAIL-02 → MAIL-03 → ...` 순서로 자동 진행한다.

안전하게 수행 가능한 작업이 남아 있는 동안 계속 개발한다.
