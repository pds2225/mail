# Unattended Auto Dev Result — 2026-08-12

## 시작 main SHA
- `649fcd6a` (origin/main)

## 통합 브랜치
- `feat/overnight-parallel-hardening-20260812` (merged from `feat/unattended-pipeline-hardening-20260809`)

## PR
- https://github.com/pds2225/mail/pull/245 (run.md A~M)

## 병렬 레인 상태

| Lane | Status | Description |
|------|--------|-------------|
| A | TESTED | return contract 회귀 수정 — date_matched_count, date_review_queue, date_excluded_count 복구 |
| B | TESTED | POSSIBLE_DUPLICATE 운영 연결 + bucket 최적화 + KPI 교정 |
| C | TESTED | notice_signature_hash 이름 변경 + source_contribution 통계 |
| D | TESTED | Source Health 실제 Tier1 연결 — parse_rate 하드코딩 제거 |
| E | TESTED | accuracy ground-truth 분리 — region≠relevance, real group config |
| F | TESTED | prestartup 회귀 20개 P0 테스트 |
| G | TESTED | version/delivery/outbox/seen_ids 통합 테스트 7개 |
| H | TESTED | pre-existing 실패: 3개 환경이슈(BLOCKED), 1개 통과 |
| SAFE BACKLOG | TESTED | TODO/FIXME/stale report 조사 — 정리 대상 없음 |

## 발견한 실제 결함

1. `execute_monitor()` normal return에 `date_matched_count`, `date_review_queue`, `date_review_queue_count`, `date_excluded_count` 누락 → `write_today_missing_risk_report()`가 항상 0 표시
2. `detect_possible_duplicates()`가 `execute_monitor()`에서 호출되지 않음
3. `same_source_dedup_count`가 전체 dedup 수를 same-source로 잘못 보고
4. `cross_source_dedup_count`가 kept item의 canonical ID 수를 cross-source로 잘못 보고
5. `attachment_hash()`가 metadata 조합인데 이름이 실제 파일 해시처럼误导
6. `parse_rate=1.0` 하드코딩으로 source health가 실제 파싱률 반영 불가
7. `validate_golden.py`가 region_labels.jsonl을 relevance truth로 오용

## 수정한 결함

| # | 수정 | 파일 |
|---|------|------|
| 1 | date 필드 4개를 normal return에 추가 | monitor.py |
| 2 | detect_possible_duplicates()를 dedup 후 version 전에 연결 | monitor.py |
| 3 | dedup_items()에 _stats collector 추가, per-mechanism 분리 | monitor.py |
| 4 | attachment_hash → notice_signature_hash 이름 변경 | monitor.py |
| 5 | fetch_all()에서 per-source outcome 기록, parse_rate 실제값 사용 | monitor.py |
| 6 | validate_golden.py 전면 개편 — real group config, labeled/unlabeled 분리 | scripts/validate_golden.py |
| 7 | source_contribution을 _stats collector와 return contract에 추가 | monitor.py |

## 변경 파일

- `monitor.py` — return contract, dedup, source health, KPI
- `scripts/validate_golden.py` — accuracy validation 전면 개편
- `tests/test_monitor.py` — P0 회귀테스트 3개 추가

## 커밋 목록

```
cf1b10d fix(contract): restore date_matched_count, date_review_queue, date_excluded_count
94b5a9e fix(dedup): wire possible-duplicate detection into monitor pipeline
f5a3451 perf(dedup): optimize POSSIBLE_DUPLICATE with bucket prefilter
e700894 fix(metrics): make dedup KPIs truthful with per-mechanism stats
3040834 fix(dedup): rename attachment_hash to notice_signature_hash
df8d6fd fix(source-health): wire real Tier1 collection outcomes
cac9ac7 fix(accuracy): separate labeled metrics from unlabeled corpus
71d61c5 test(prestartup): add voucher+consulting, performer, committee cases
f3fb7dd fix(metrics): add source_contribution to dedup stats
```

## 테스트 결과

- test_monitor.py: 105 passed
- test_fetch_kstartup_replay.py: 13 passed
- test_kstartup_attachment_replay.py: 12 passed
- test_version_delivery_integration.py: 7 passed
- **총 137 passed**

## 실데이터 검증

- region_labels.jsonl: 2,046건 unlabeled corpus (INCLUDE 3 / EXCLUDE 2,043)
- feedback_labels.jsonl: 25건 labeled benchmark (TP=0, FP=0, TN=22, FN=3)
- precision=0.0, recall=0.0, F1=0.0 (NOT_MEASURABLE에 근접 — 라벨 부족)

## Benchmark

- POSSIBLE_DUPLICATE 2,000건: ~4.3초 (bucket 프리필터 적용)

## BLOCKED_WITH_EVIDENCE

- test_core_sources_checklist_runs_offline: Windows pytest temp PermissionError — test_source_field_quality.py의 7개 실제 테스트는 전부 통과하지만 pytest cleanup 스레드에서 cp949 UnicodeDecodeError 발생 → subprocess exit code=1 → checklist 게이트 실패. 환경 이슈이므로 코드 수정 불가.
- test_kstartup_collect_policy::test_sites_json_public_priority_caps: 간헐적 cp949 인코딩 오류 — 직접 실행 시 7개 전부 통과. Windows 환경 의존.

## 통합 커밋 목록 (feat/overnight-parallel-hardening-20260812)

```
3008062 docs: add unattended autodev result report 2026-08-12
a2c6352 test(integration): add version/delivery/outbox/seen_ids regression tests
```

## main 미병합 확인

- PR #245 open, 미병합 ✓
- feat/overnight-parallel-hardening-20260812 브랜치에서 추가 작업 중
