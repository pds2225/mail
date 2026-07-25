# 공고 누락 탐지 체계 — 보완 개발계획서

| 항목 | 내용 |
|------|------|
| 문서 ID | `PRD-NOTICE-MISS-DETECT-v2` |
| 작성일 | 2026-07-25 |
| 상태 | Draft (문서 산출) |
| 근거 | 누락 4단계 분석 + 기존 `coverage_alert`/`detail_extraction` 코드 현황 |
| 범위 원칙 | **P0 = 수집·추출 누락 탐지·복구**. 판정·기업추천·Claude는 **P1** (본 계획의 완료조건에서 제외) |

---

## 0. 한 줄 결론

핵심 문제는 기능 부족보다 **누락 유형·우선순위·단계별 상태가 분리되지 않은 것**이다.  
이미 존재하는 P0 수집 판정(`mail_core/operations/coverage_alert.py`)과 상세추출 상태(`NOT_SPECIFIED`/`PARSE_FAILED`/`DETAIL_FETCH_FAILED`)를 확장해, **원천 수집 → 정보 추출 → (추후) 판정·전달**을 원인별로 추적 가능하게 만든다.

---

## 1. 문제 정의 (채택)

서비스 최대 위험은 **공고가 실제로 존재함에도 사용자에게 전달되지 않는 것**이다. 누락은 4단계에서 발생한다.

| 구분 | 발생 지점 | 대표 문제 | 본 계획 우선순위 |
|------|-----------|-----------|------------------|
| 원천 수집 누락 | 사이트 접속·목록 수집 | 미실행, 파서 실패, 페이지 누락, 급감 | **P0-A** |
| 정보 추출 누락 | 상세페이지 보강 | 마감일·지역·대상 미추출 / 실패 vs 미기재 혼동 | **P0-B** |
| 판정 누락 | 그룹·기업 적합성 | 키워드·지역·지원유형 오판 | **P1-A/B** |
| 전달 누락 | 요약·메일 | 요약 제외, 그룹·기업별 표시 누락 | **P1-C** |

### 본질

> 프로그램이 오류 없이 종료된 것과 공고를 빠짐없이 수집한 것은 다르다.

따라서 성공/실패 이분법이 아니라 **수집량·페이지 수·필드 추출률·과거 기준선·단계별 상태**로 검증한다.

---

## 2. 현재 코드 기준선 (As-Is)

이미 구현되어 **재사용·확장**해야 하는 자산. 새로 만들지 말고 갭만 메운다.

| 자산 | 위치 | 이미 되는 것 | 아직 부족한 것 |
|------|------|--------------|----------------|
| 수집 이상탐지 | `mail_core/operations/coverage_alert.py` | 상태 5종, P0/P1 사유코드, 7회 중앙값, SUCCESS만 baseline 반영, 실행대장 검증, DEGRADED 요약 | 사이트별 threshold, 전체 FAILED, 재수집 루프, 수동확인 큐 |
| P0 단위테스트 | `tests/test_coverage_p0.py` | 미실행·0건·급감·캡차·스키마·페이지루프 계약 | 사이트별 정책·재시도·수동큐 계약 |
| 실행대장 | `monitor.write_source_coverage_*` / `run_source_coverage_audit` | JSON/MD 산출, 알림 배선 | 공고 단위 lifecycle 미연결 |
| 상세추출 상태 | `monitor.py` `NOT_SPECIFIED`/`PARSE_FAILED`/`DETAIL_FETCH_FAILED` | 필드별 status 기록 | 필수필드 계층·추출률 P0 게이트·운영 리포트 통합 약함 |
| Raw 보존 | `mail_core/storage/raw_store.py` | 누락 재검토용 raw 저장 | 누락기간 재조회 자동화 약함 |
| 정확도 트랙 | `docs/mail_accuracy_orchestrator_plan.md` | 판정 FP/FN 측정 설계 | **본 P0와 분리 유지** (혼선 금지) |

---

## 3. 목표 상태 모델 (To-Be)

### 3.1 실행(Run) 상태 — 개별 소스 P0 ≠ 전체 중단

| Run 상태 | 의미 | 발송 |
|----------|------|------|
| `SUCCESS` | 활성 소스 전부 정상(또는 허용된 SKIPPED) | 정상 발송 |
| `DEGRADED` | 일부 소스 P0/부분수집 | **정상 소스만 발송**, P0 소스 재수집·알림 |
| `FAILED` | 실행대장 자체 붕괴·활성소스 대량 미실행·탐지 파이프 장애 | **발송 보류** + 즉시 알림 |

현재 코드는 `OK`/`DEGRADED`만 있다 → `SUCCESS`/`DEGRADED`/`FAILED`로 명명 정리(호환 alias 유지).

### 3.2 소스(Fetch) 상태 (기존 유지)

`SUCCESS` | `PARTIAL` | `FAILED` | `SKIPPED` | `ZERO_SUSPICIOUS`

### 3.3 공고 lifecycle 상태 (신규 통합 추적 — JSON)

단계별로 **포함/제외가 어디서 났는지** 저장한다. DB 없이 `var/state/` + 일별 로그 JSON.

| 단계 | 저장해야 할 상태 | P0 범위 |
|------|------------------|---------|
| Fetch | 수집 성공·부분·실패, page_stat, item_count | ✅ |
| Enrich | 상세보강 완료·부분·실패 (`DETAIL_*`) | ✅ |
| Normalize | 날짜·지역·금액 파싱 성공 여부 / `NOT_SPECIFIED` vs `PARSE_FAILED` | ✅ |
| Evaluate | 포함·검토·제외 + exclude_reason_codes | ❌ P1 (스키마만 예약) |
| Company Match | 기업별 점수·승격 여부 | ❌ P1 |
| Summarize | 요약 성공·대체템플릿 | ❌ P1 |
| Delivery | 실제 메일 포함 여부 | ❌ P1 (관측 필드만 예약) |

### 3.4 필드 공백 의미 분리 (필수)

| 상태 | 의미 | 운영 해석 |
|------|------|-----------|
| `NOT_SPECIFIED` | 원문에 해당 정보 없음 | 정상 가능 (전국·상시·금액 상이 등) |
| `PARSE_FAILED` | 원문에 있을 가능성 있으나 추출 실패 | **P0-B 후보**, review 유지 |
| `DETAIL_FETCH_FAILED` | 상세페이지 접근 실패 | **P0-B**, 재시도 대상 |

`region_unknown` 하나로 묶지 않는다. UI/리포트는 세 상태를 구분 표시.

### 3.5 필수필드 계층 (과도한 필수 금지)

| 구분 | 항목 | 실패 시 |
|------|------|---------|
| 절대 필수 | 공고명, 기관(또는 소스명), 원문 URL | 스키마 실패 → P0 |
| 판정 필수 | 접수상태(또는 상시), 지원대상 힌트, 지역 **또는** 지역미지정(`NOT_SPECIFIED`) | PARSE/DETAIL 실패면 review, 자동 제외 금지 |
| 선택 | 지원금액, 신청방법, 세부 일정 | 추출률 모니터링만 (P1까지 게이트 금지) |

---

## 4. 우선순위 확정 (범위 가드)

### P0-A. 원천 수집 누락 탐지·복구

1. 활성 사이트 실행대장 (`verify_source_execution`)
2. 소스별 SUCCESS/PARTIAL/FAILED/ZERO_SUSPICIOUS
3. 수집건수 급감·0건 이상탐지 (기준선 있는 경우만 P0)
4. 페이지네이션 누락·중복 페이지 루프
5. 파서/접속/콘텐츠(로그인·점검) 실패
6. **탐지 후 자동 재시도 + 누락기간 재수집 + 수동확인 큐**

### P0-B. 정보 추출 누락 탐지

1. 필수필드 추출률 (절대/판정 계층)
2. `NOT_SPECIFIED` vs `PARSE_FAILED` vs `DETAIL_FETCH_FAILED` 강제 분리
3. 상세보강 실패 공고는 **제외하지 않고 review 유지**
4. 추출 실패율을 소스 리포트에 연결 (소스 PARTIAL/P0 승격 규칙)

### P1 (본 문서 Done 조건 제외 — 설계만 명시)

| ID | 내용 | 왜 P1인가 |
|----|------|-----------|
| P1-A | 키워드·지원유형·지역 오판 방지, Hard Exclusion, Golden Set | 추천 정확도. 수집 성공과 무관 |
| P1-B | 기업 매칭 승격·점수·상한 | 누락 방지용 과도 승격 시 오탐↑ |
| P1-C | Claude 요약 품질·실패 시 템플릿 | 요약 실패 ≠ 원천 누락 |

**가드:** 동일 PR/동일 TASK에 P0와 P1을 묶지 않는다. Auto Dev RULES의 보호파일(`monitor.py` 대량 수정)은 훅·스키마 확장 최소선만 허용하고, 판정/Claude 변경은 별도 승인 브랜치.

---

## 5. 아키텍처

```
sites.json (enabled)
    │
    ▼
fetch_all / collectors ──► coverage rows + page_stats
    │
    ▼
coverage_alert.classify_sources + verify_source_execution
    │                         │
    │                         ├─ SUCCESS → baseline 반영
    │                         ├─ P0/P1 → alert + recheck_queue
    │                         └─ run_status SUCCESS|DEGRADED|FAILED
    ▼
enrich (detail) ──► detail_extraction per field
    │
    ▼
normalize ──► NOT_SPECIFIED | PARSE_FAILED | DETAIL_FETCH_FAILED
    │
    ▼
notice_lifecycle.jsonl (공고별 단계 상태)   ← 신규
    │
    ├─ [P0] miss_remediation: retry / window-refetch / manual_queue
    └─ [P1 later] evaluate → company_match → summarize → delivery
```

저장소는 기존 원칙 유지: **JSON 파일, DB 불필요**.

| 파일 | 역할 |
|------|------|
| `var/state/coverage_baseline.json` | 정상 실행만 반영되는 사이트별 이력 (기존) |
| `var/state/source_run_ledger.jsonl` | 실행별 소스 판정 이력 (신규·append) |
| `var/state/notice_lifecycle.jsonl` | 공고별 단계 상태 (신규·append, 일자 롤링) |
| `var/state/miss_manual_queue.json` | 관리자 확인 대기열 (신규) |
| `config/detector_sites.json` | 사이트별 탐지 정책 (신규) |
| `var/logs/source_coverage_YYYYMMDD.{json,md}` | 실행대장 (기존) |

---

## 6. 사이트별 탐지 설정

전 사이트 동일 `80% 급감=P0`는 오경보를 만든다. 기본값 + 사이트 오버라이드.

```json
{
  "defaults": {
    "zero_item_policy": "p0_if_baseline",
    "drop_threshold": 0.8,
    "minimum_baseline": 5,
    "baseline_min_runs": 3,
    "expected_frequency": "daily",
    "auto_retry": 2,
    "retry_backoff_sec": [60, 180]
  },
  "sites": {
    "incheon_tp": {
      "zero_item_policy": "warning",
      "drop_threshold": 0.9,
      "minimum_baseline": 3,
      "expected_frequency": "weekly"
    },
    "bizinfo": {
      "zero_item_policy": "p0_if_baseline",
      "drop_threshold": 0.7,
      "minimum_baseline": 20,
      "expected_frequency": "daily"
    }
  }
}
```

| 정책 값 | 0건일 때 |
|---------|----------|
| `p0_if_baseline` | 기준선 충분·median≥1 → P0 (기본) |
| `warning` | P1만 (지역·월간 사이트) |
| `ignore_zero` | 알림 없음 (명시적 옵트인, 남용 금지) |

`expected_frequency=weekly|monthly`인 사이트는 **연속 N회 0건**일 때만 승격(일일 오경보 억제).

---

## 7. 기준선 오염 방지 (강화)

기존: 실패·이상일은 `update_coverage_baseline`에 미반영.  
추가로 명시:

1. **SUCCESS로 검증된 실행만** 반영 (PARTIAL/P0/P1/ZERO_SUSPICIOUS 제외 — 이미 근접, 계약 테스트로 고정)
2. 관리자 `confirmed_healthy=true` 표시가 있는 날만 장기 평균에 편입(선택 게이트)
3. 단기(최근 7회 SUCCESS 중앙값) + 장기(최근 30 SUCCESS 평균) **동시 비교** — 단기만 오염돼도 장기 괴리로 P1 경고
4. 수동 확인 완료(`manual_ack`) 기록 후 해당 장애일을 정상으로 재분류하지 않음(별도 confirmed 플래그 필요)

---

## 8. 탐지 후 후속조치 (탐지만으로는 복구 불가)

| 단계 | 규칙 |
|------|------|
| 자동 재시도 | 소스 P0(FETCH/PARSER/CONTENT) → `auto_retry`회, backoff |
| 재시도 성공 | 해당 소스 P0 해제, baseline 후보 가능, 알림에 resolved 표기 |
| 재시도 실패 | `miss_manual_queue`에 enqueue |
| 누락기간 재조회 | `recheck_site_ids` + 최근 성공일~오늘 윈도우 refetch (raw_store 연계) |
| 발송 | DEGRADED: 정상 소스만 / FAILED: 보류 |
| 관리자 확인 | 큐에서 `ack`/`false_alarm`/`fixed` 처리 → 오경보율 KPI에 반영 |

---

## 9. 예상 발생 가능 문제와 해결방안

| ID | 예상 문제 | 원인 | 해결 | 심각도 |
|----|-----------|------|------|--------|
| E01 | HTTP 200인데 점검/로그인 페이지 → 성공 오인 | 상태코드만 신뢰 | `suspicious_content_*` + CONTENT_VALIDATION P0 유지·확대 | P0 |
| E02 | 첫 페이지만 수집 | pagination stop 미계측 | `page_stat.stop_reason` 필수화, MAX_PAGES/DUPLICATE → PARTIAL | P0 |
| E03 | 평소 30→2건인데 정상 처리 | 급감 미비교 | baseline median + 사이트별 drop_threshold | P0 |
| E04 | 실제 신규 0건 vs 수집실패 0건 혼동 | 0건 일괄 P0 | baseline 충분할 때만 P0, 부족 시 P1/`warning` 정책 | P0 |
| E05 | 파서 오류 지속 → baseline이 2건으로 고착 | 이상일 반영 | SUCCESS만 반영 + 장기평균 괴리 경고 | P0 |
| E06 | 전 사이트 동일 80% 임계 → 오경보 폭증 | 사이트 이질성 | `detector_sites.json` 오버라이드 | P0 |
| E07 | 지역 빈값 = region_unknown 단일화 | 미기재/파싱실패 미분리 | 3상태 enum 강제, 리포트 분리 | P0 |
| E08 | 금액·신청방법 필수로 정상공고를 실패 처리 | 필수 과다 | 절대/판정/선택 계층 | P0 |
| E09 | P0인데 발송 계속 vs 중단 모호 | 소스P0≠런P0 | SUCCESS/DEGRADED/FAILED 발송 매트릭스 | P0 |
| E10 | 탐지 후 방치 → 누락 미복구 | remediation 부재 | retry→refetch→manual_queue | P0 |
| E11 | 재시도 폭풍으로 대상 사이트 차단 | 무제한 retry | 횟수·backoff·사이트당 일일 상한 | P0 |
| E12 | lifecycle 로그 폭증·디스크 | 전 공고 전문 저장 | jsonl + 필드 요약만, 14~30일 롤링 | P0 |
| E13 | P0 범위에 판정·Claude 혼입 | 요구사항 비대화 | 본 문서 Done 게이트에서 P1 명시 제외 | 관리 |
| E14 | 키워드 확대로 FP↑ (AI 제외문 매칭 등) | P1을 P0처럼 취급 | P1-A에서 구역·제외키워드·규칙/LLM 분리 | P1 |
| E15 | 기업 승격 남발 → 메일 피로 | 약한 승격 기준 | 필수/선택 키워드·최소점수·일일 상한·Hard Exclusion 우선 | P1 |
| E16 | coverage_alert와 monitor 이중판정 불일치 | 알림용 vs 게이트용 병행 | 게이트는 `classify_*`만, 알림은 그 결과를 소비 | P0 |
| E17 | Cloud VM TLS로 정상 사이트 실패 오경보 | 환경 제약 | fetch_error 분류에 `ENV_TLS` 태그, 사이트 정책 `ignore_env_tls` | P0 |
| E18 | Auto Dev가 monitor.py 대량 수정 | 보호파일 | 훅 1줄·스키마만, 로직은 `mail_core/` | 관리 |
| E19 | 허위 DONE (문서만 쓰고 탐지 미배선) | 검증 부재 | Done 게이트 = pytest + 샘플 ledger 산출물 | 관리 |
| E20 | recall_zero_gate와 수집 P0 혼동 | 게이트 목적 상이 | checklist(수집) / recall(판정) / miss-detect(본체계) 문서에 분리 명시 | 관리 |

---

## 10. KPI (초기 운영 가정)

| KPI | 목표 | 측정 |
|-----|------|------|
| 활성 소스 실행률 | 100% | `executed / active_expected` |
| 명백한 신규공고 수집 재현율 | ≥ 98% | Golden list / 수동 샘플 |
| 상세 절대필수 추출률 | ≥ 95% | lifecycle Normalize |
| 판정필수 중 PARSE/DETAIL 실패율 | ≤ 5% (실패를 미기재로 위장 0) | 상태 분리 리포트 |
| 관리자 오경보율 | ≤ 15% | manual_queue false_alarm 비율 |
| review 비율 | ≤ 20% (후보 대비) | P1과 공유 관측, P0 실패 조건 아님 |
| 중복공고율 | ≤ 2% | dedup 리포트 |

누락률만 보면 오탐·리뷰 부담이 증가한다 → **재현율 + 오경보율**을 같이 본다.

---

## 11. WBS

| Wave | 산출물 | Done 증거 | P0/P1 |
|------|--------|-----------|-------|
| **W0** | 상태 enum ADR, `source_run` JSON 스키마, `detector_sites.json` 초안, Run FAILED 정의 | 스키마 예시 + ADR md, 단위테스트 스텁 | P0 |
| **W1** | 사이트별 threshold 주입 (`classify_source_status(thresholds=…)`) | `test_coverage_p0` 사이트정책 케이스 green | P0-A |
| **W2** | remediation: retry / recheck window / manual_queue | dry-run에서 큐 파일 생성·해제 테스트 | P0-A |
| **W3** | 필드 3상태 리포트 + 필수계층 추출률을 source report에 연결 | `test_detail_extraction_status` + 신규 추출률 테스트 | P0-B |
| **W4** | `notice_lifecycle.jsonl` Fetch/Enrich/Normalize 기록 | 샘플 런 1회 산출물 존재 | P0 |
| **W5** | 대시보드/로그: DEGRADED·수동큐·오경보 ack UI 또는 MD 워크플로 | 운영 runbook 절 추가 | P0 |
| **W6** | Evaluate/Company/Summarize/Delivery 스키마 예약만 | 필드 null 허용, 로직 미구현 | 스키마만 |
| **W7+** | 판정·기업·Claude | 별도 PRD / accuracy orchestrator | P1 |

### W0 착수 상세 (다음 구현 프롬프트용)

1. **ADR**: Run/Source/Field/Lifecycle enum 확정, `OK`→`SUCCESS` alias
2. **source_run 레코드 스키마** (JSONL 1행):

```json
{
  "run_id": "20260725T090000Z",
  "site_id": "nipa",
  "status": "PARTIAL",
  "risk_level": "P0",
  "reason_codes": ["COLLECTION_DROP_HIGH"],
  "item_count": 4,
  "baseline_median": 24,
  "page_stat": {"stop_reason": "MAX_PAGES_HIT"},
  "extraction_rates": {"absolute_ok": 1.0, "decision_ok": 0.75},
  "retry": {"attempt": 0, "max": 2},
  "baseline_eligible": false
}
```

3. **detector_sites.json** 초안: defaults + 핵심 대형포털/지역기관 10개 오버라이드
4. **P1 금지**: evaluate/company/Claude 코드 변경 없음

---

## 12. Done 게이트 (P0 완료 정의)

다음을 **모두** 만족해야 P0 Done. 하나라도 없으면 AWAITING / 문서만 DONE 금지.

1. `python3 -m pytest tests/test_coverage_p0.py tests/test_detail_extraction_status.py -v` green
2. 사이트별 detector 설정이 판정에 실제 주입됨 (동일 0건이 사이트 A=P0, B=warning로 갈림 테스트)
3. P0 발생 시 `miss_manual_queue.json` 또는 동등 큐에 항목 생성
4. 재시도 성공 시 해당 소스 risk 해제 경로 테스트
5. 필드 공백이 `NOT_SPECIFIED`/`PARSE_FAILED`/`DETAIL_FETCH_FAILED`로만 기록 (region_unknown 단일화 경로 제거 또는 매핑)
6. Run 상태가 SUCCESS/DEGRADED/FAILED로 요약되고, FAILED일 때만 발송 보류 플래그
7. baseline에 P0/PARTIAL/실패일 미반영 회귀 테스트 유지
8. **P1 기능(판정 키워드·기업승격·Claude) 변경 없음** (diff 가드)

---

## 13. 충돌 정리 (요구사항 해석)

### 13.1 “발송 계속” vs “누락 P0”

- 소스 P0 → 런은 보통 `DEGRADED` → **정상 소스 발송 계속**
- 런 `FAILED` → **발송 보류**
- 문서/알림에 이 매트릭스를 고정해 운영 논쟁을 제거

### 13.2 정확도 vs 재현율

- P0는 재현율(수집) 우선
- review·오경보율 상한으로 알람 피로 관리
- 판정 precision은 P1 + accuracy orchestrator

### 13.3 기존 요청서와의 관계

기존에 ④·⑤·⑧·⑨를 한 P0로 묶은 요청이 있으면 **본 문서를 우선순위 기준으로 삼는다.**  
요청서 문구 정렬이 필요하면 별도 합의 TASK로 처리한다.

---

## 14. 비범위 (Out of Scope)

- DB/DDL 도입 (JSON 유지; “source_run DDL” 요청은 **JSON Schema로 대체**)
- Claude 프롬프트·요약 품질 개선
- 기업 매칭 승격 알고리즘 변경
- 키워드 사전 대량 확장
- Vercel/인프라 교체
- `monitor.py`/`streamlit_app.py` 대규모 리팩터 (훅·리포트 호출 최소선만)

---

## 15. 리스크 & 롤백

| 리스크 | 완화 | 롤백 |
|--------|------|------|
| 오경보로 운영 무시 | 사이트별 정책·오경보율 KPI | detector 오버라이드를 warning으로 |
| remediation이 사이트 부하 | retry 상한 | auto_retry=0 즉시 |
| lifecycle I/O 장애가 본수집 중단 | try/except, best-effort 기록 | 플래그로 lifecycle off |
| 보호파일 회귀 | pytest + Auto Dev 보호규칙 | 브랜치 revert |

---

## 16. 다음 실행 프롬프트 (1개)

> 개발계획서 §4·§7·§11 W0을 코드/스키마로 착수해 줘.  
> 산출: (1) 상태 enum ADR (`docs/prd/` 또는 `docs/02-design/`), (2) `source_run` JSONL 스키마 + 쓰기 헬퍼(`mail_core/`), (3) `config/detector_sites.json` 초안, (4) Run `FAILED` 판정 초안 + 단위테스트.  
> **P1(판정·기업·Claude) 포함 금지. `monitor.py` 대량 수정 금지.**

---

## 17. 변경 이력

| 버전 | 일자 | 내용 |
|------|------|------|
| v1 | (선행) | P0/P1 분리·상태모델·E01~E15 초안 방향 |
| v2 | 2026-07-25 | As-Is 코드 매핑, E16~E20, remediation·사이트정책·Done 게이트·W0 상세, JSON Schema로 DDL 대체, 발송 매트릭스 고정 |
