# ADR: 공고 누락 탐지 상태 enum

| 항목 | 내용 |
|------|------|
| 상태 | Accepted (W0) |
| 일자 | 2026-07-25 |
| 관련 | `PRD-NOTICE-MISS-DETECT` §3·§11, `mail_core/operations/coverage_alert.py` |

## 결정

### 1. Canonical detector

발송 보류·P0 등급·`recheck_site_ids`·ledger·baseline 자격의 **유일한 권한**은  
`classify_sources` / `summarize_run_status` / `verify_source_execution` 이다.

`detect_coverage_anomalies`는 **보조 알림**만 하며 hold/등급을 뒤집지 않는다.

### 2. Run 상태

| 값 | 의미 | send_hold |
|----|------|-----------|
| `SUCCESS` | 활성 소스 정상(또는 SKIPPED만), P0=0 | false |
| `DEGRADED` | 일부 소스 P0, FAILED 조건 아님 | false (정상 소스만 발송 — W1 필터) |
| `FAILED` | 실행대장 붕괴·대량 미실행 | **true** (실발송 보류 — W1 배선) |

**Alias:** 기존 `"OK"` ≡ `SUCCESS`. 신규 코드는 `SUCCESS`만 기록한다.  
`normalize_run_status("OK") == "SUCCESS"`.

### 3. Run FAILED 수치 (고정)

다음 중 **하나**라도 만족하면 `FAILED`:

1. `exec_ok == false` **그리고** (`missing_count / active_expected >= 0.30` **또는** `missing_count >= 5`)  
2. `active_expected >= 1` 이고 `missing_count / active_expected >= 0.30`  
3. `missing_count >= 5`

상수:

- `RUN_FAILED_MISSING_RATIO = 0.30`
- `RUN_FAILED_MISSING_ABS = 5`

`exec_check`가 skip되었거나 `active_expected==0`이면 missing 비율로 FAILED를 만들지 않는다(근거 없는 보류 금지).

P0 소스만 있고 실행대장은 완전하면 → `DEGRADED` (FAILED 아님).

### 4. Source 상태 (기존 유지)

`SUCCESS` | `PARTIAL` | `FAILED` | `SKIPPED` | `ZERO_SUSPICIOUS`

### 5. Field 공백 상태 (기존 유지, P0-B에서 surface)

`SUCCESS` | `NOT_SPECIFIED` | `PARSE_FAILED` | `DETAIL_FETCH_FAILED`

| 상태 | 표면 라벨(운영·메일) | region_unknown 버킷 |
|------|----------------------|---------------------|
| `NOT_SPECIFIED` | `원문 미기재` / 지역=`지역 제한 없음` | **금지** (전국·미지정 경로) |
| `PARSE_FAILED` | `추출 실패(검수)` | 매핑 가능(레거시). 판정은 **review 강제·exclude 금지** |
| `DETAIL_FETCH_FAILED` | `상세 접속 실패(재시도)` | 매핑 가능(레거시). 판정은 **review 강제·exclude 금지** |
| `SUCCESS` | `확보` | — |

구현: `mail_core/operations/field_status.py`
(`field_blank_kind`, `surface_label_for_field`, `should_force_review_for_extraction`,
`compute_extraction_rates`, `allow_region_unknown_bucket`).

`region_unknown` 심볼/경로는 **삭제하지 않는다**. 실패 2종만 매핑 가능, NOT_SPECIFIED 는 진입 금지.

### 6. baseline_eligible

classify 결과 소스 상태가 `SUCCESS`이고 risk_level이 비어 있을 때만 True.  
PARTIAL/P0/P1/ZERO_SUSPICIOUS/FAILED → False.

## 결과

- W0: `summarize_run_status`가 SUCCESS/DEGRADED/FAILED + `send_hold` 플래그 산출
- W1: `execute_monitor`가 `send_hold` 소비 (본 ADR 범위 밖, 훅만)
