# Mail 모니터 공고 수집·통합·예비창업 매칭 아키텍처 — 최종 실행계획서

> **작성 근거**: `docs/autodev/AI_PRESTARTUP_NOTICE_MASTER_PROMPT.md` 마스터 프롬프트 §22 출력 형식에 따라 작성  
> **코드 분석 범위**: `monitor.py`(7,434줄), `mail_core/` 전 모듈(24개 파일), `config/` 3개 파일, `tests/test_monitor.py`(887줄)  
> **분석일**: 2026-08-07

---

## 1. 계획 개요

### 추진 배경

현재 시스템은 `monitor.py` 단일 파일(7,434줄)에 수집·중복제거·필터링·AI 요약·발송 로직이 모두 혼재되어 있다. 마스터 프롬프트가 요구하는 4계층 아키텍처(수집 소스 관리·공고 통합·예비창업 매칭·메일 발송)와 구조화된 판정 로직(신청자/모집대상/수혜자/운영자 분리, eligibility 상태, reason code 체계)으로의 전환이 필요하다.

### 최종 목적

> 전국 또는 서울·경기·인천의 예비창업자·사업자 미보유 창업예정자가 실제 신청할 수 있고, 현재 접수 중이며, 사업화자금·시제품 제작비·R&D·바우처·실증비 등 실질적 비용지원이 포함된 공고를 최대한 누락 없이 수집하여 메일로 발송한다.
>
> 교육·멘토링·컨설팅·투자·입주공간만 제공하는 공고, 운영기관·수행기관 모집, 입찰·행정성 공고, 마감공고는 제외한다.
>
> 여러 사이트에 게시된 동일 공고는 하나의 통합 공고로 관리하되, 수정공고·재공고·마감연장 등 중요한 변경은 별도 버전으로 관리하고 필요한 경우 다시 안내한다.

### 적용 범위

- **수집 소스**: `config/sites.json` 414개(활성 225, 비활성 189)
- **그룹 설정**: `config/groups.json` 3개 그룹(`grp_ai_saas`, `grp_bnco`, `grp_prestartup_ai`)
- **핵심 모듈**: `monitor.py`(7,434줄), `mail_core/` 5개 서브모듈
- **상태 파일**: `seen_ids.json`, `notice_versions.json`, `delivery_state.json`, `delivery_outbox.enc`

### 핵심 성공기준

| KPI | 목표치 |
|-----|--------|
| 예비창업 공고 정밀도(Precision) | 95% 이상 |
| 예비창업 공고 재현율(Recall) | 90% 이상 |
| 사이트 간 중복 제거율 | 90% 이상 |
| 잘못된 중복 제거율 | 1% 이하 |
| 사업비+멘토링 오제외 | 0건 |
| 운영기관 모집 오포함 | 0건 |
| `개인` 단독 오포함 | 0건 |
| Tier 1 수집 성공률 | 99% 이상 |
| AI 전달 비율 | 후보 공고의 20% 이하 |
| AI 실패 후 자동 포함·제외 | 0건 |

---

## 2. 현재 상태 진단

### 실제 수집처 현황

| 구분 | 수치 | 비고 |
|------|------|------|
| 활성 소스 (`enabled: true`) | 225개 | sites.json 기준 |
| 비활성 소스 (`enabled: false`) | 189개 | JS 렌더링 필요, 접근 차단, 구조 변경, 중복성 |
| 총 소스 | 414개 | |

### Tier 현황 (실제 코드 대조)

| Tier | 소스 | 수집 방식 | 비고 |
|------|------|-----------|------|
| Tier 1 | `bizinfo`(기업마당, API), `kstartup`(K-Startup, HTML/API) | 전용 fetcher | `core_sources.py`에서 전담 |
| Tier 2 | NIPA, KIAT, KEIT, KOSME, SBA, 테크노파크, 경제진흥원 등 | 범용 HTML fetcher | |
| Tier 3 | `smes24`, `subsidy24`, `ntis`, `g2b` 등 | 비활성 | JS 렌더링 필요 등 |

### `grp_prestartup_ai` 현재 설정

```json
{
  "score_threshold": 1,
  "llm_check_threshold_band": [40, 70],
  "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
  "or_keywords": ["예비창업", "예비창업자", "창업예정자", "개인"],
  "exclude_keywords": ["성료", "지침 안내", "관리지침", "운영지침", "교육일정", "매뉴얼 안내", "유의사항", "설명회", "결과 발표", "보도자료", "기획위원", "심사위원", "운영위원", "사기피해 예방", "채용", "재직자", "입주기업", "멘토링", "컨설팅", "교육 프로그램"]
}
```

### 현재 데이터 흐름

```
수집(fetch_all) → 중복제거(dedup_items) → 버전선택(select_notice_version_candidates)
→ 상세수집(enrich_items) → 버전분류(classify_notice_versions)
→ 날짜필터(partition_posted_dates) → 워치리스트매칭
→ 그룹필터(filter_for_group_with_diagnostics) → 점수필터(score_and_filter)
→ 요약(fallback_body) → 발송(deliver_with_outbox)
```

### 비교표: 현재 동작 vs 목표 동작

| 구분 | 현재 동작 | 목표 동작 | 문제점 | 수정 대상 |
|------|-----------|-----------|--------|-----------|
| 아키텍처 | 모놀리식 (1파일 7,434줄) | 4계층 분리 | 수집·필터·발송 혼재 | 전체 재설계 |
| 멘토링/컨설팅/교육 | `exclude_keywords`에 포함 → 본문 포함 시 즉시 제외 | 단독일 때만 제외, 복합지원 시 포함 | 정상 공고 과제외 | `EXCLUSION_RULES`, `evaluate_notice()` |
| `개인` 키워드 | `or_keywords`에 포함 → 예비창업 매칭에 사용 | `개인` 단독은 예비창업 근거 불충분 | 오포함 위험 | `grp_prestartup_ai` 설정 |
| 지원유형 분류 | 4버킷(투자, 지원금/바우처, 컨설팅·교육·상담, 그외) | 주된지원/부가지원 구분, 단독 교육·투자·입주 제외 | 교육·투자 단독 포함 가능 | `SUPPORT_TYPE_RULES` 재설계 |
| 중복 제거 | 동일소스 제목기반(`seen_ids`) | 크로스소스 `canonical_notice_id` | 사이트 간 동일공고 미통합 | Layer B 신규 |
| 버전 관리 | `notice_versions` (변경 감지) | 수정·재공고·마감연장 중요 변경 재발송 | 재발송 정책 없음 | 확장 |
| 발송 이력 | `delivery_state` (recipient 기준) | 발송 이력 분리 + 멱등 | seen_ids와 역할 혼재 | 분리 |
| AI 리뷰 | 점수 밴드(40-70) → LLM | `ambiguous_only` + 사유코드 | 모든 애매한 공고를 점수로만 판단 | AI 호출 전략 변경 |
| 지역 판정 | 기관 소재지 기준 | 신청자 자격조건 기준 | 대구 기관이 게시한 전국공고 탈락 | `evaluate_notice()` 수정 |
| relevance_score | 자동 포함/제외 기준으로 사용 | 1차 구현에서 사용 안 함, 정렬용만 | 점수로 정상 공고 탈락 | 비활성화 |
| 소스 상태 | `enabled` boolean만 | OK/DEGRADED/FAILING/STALE/DISABLED/UNKNOWN | 장애 감지 없음 | Layer A 신규 |

---

## 3. 목표 아키텍처

### 4개 계층 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer A: 수집 소스 관리                     │
│  sites.json 설정 → 소스별 수집 → 데이터 품질 검증               │
│  → 상태 판정(OK/DEGRADED/FAILING/STALE) → 실행이력 저장        │
│  → 장애/복구 알림(쿨다운 적용)                                  │
├─────────────────────────────────────────────────────────────┤
│                Layer B: 공고 통합·중복 제거                     │
│  source_notice_id → 필드 정규화 → 사이트 간 동일 공고 판정       │
│  → canonical_notice_id 생성 → 버전 관리(NEW/EXTENDED/UPDATED)  │
│  → 여러 출처 필드 병합 → 공고 통합본 생성                       │
├─────────────────────────────────────────────────────────────┤
│               Layer C: 예비창업 공고 매칭                       │
│  행정성 공고 1차 제외 → 신청자/모집대상/수혜자/운영자 추출         │
│  → 예비창업 판정(ELIGIBLE/INELIGIBLE/CONDITIONAL)              │
│  → 주된지원/부가지원 분리 → 비용지원 수령주체 확인               │
│  → 지역 적격성 판정 → 마감 상태 판정                            │
│  → 명확한 공고 자동 포함/제외 → 애매한 공고만 AI 판정            │
├─────────────────────────────────────────────────────────────┤
│                Layer D: 메일·리포트 발송                        │
│  그룹별 발송 이력 확인 → 중복 발송 차단                          │
│  → 중요 변경공고 재발송 판단 → 메일 생성                        │
│  → 피드백 링크(O/X) 포함 → 발송 결과 저장                      │
└─────────────────────────────────────────────────────────────┘
```

### 전체 데이터 흐름도

```
[sites.json] ──→ Layer A: 수집
                    │
                    ▼
              원시 공고 리스트
                    │
                    ▼
              Layer B: 통합·중복제거
                    │
                    ▼
              통합 공고 (canonical)
                    │
                    ▼
              Layer C: 예비창업 매칭
                    │
                    ▼
              INCLUDE / EXCLUDE / CONDITIONAL / HUMAN_REVIEW
                    │
                    ▼
              Layer D: 메일 발송
                    │
                    ▼
              [이메일 발송] + [피드백 수집]
```

### 계층별 입출력·상태값

| 계층 | 입력 | 출력 | 상태값 |
|------|------|------|--------|
| A | sites.json, 수집 URL | 원시 공고 리스트 + 상태 리포트 | OK/DEGRADED/FAILING/STALE/DISABLED/UNKNOWN |
| B | 원시 공고 리스트 | 통합 공고(canonical) + 버전 정보 | NEW/EXTENDED/REANNOUNCED/UPDATED |
| C | 통합 공고 + groups.json | 판정 결과 + reason codes | INCLUDE/EXCLUDE/CONDITIONAL_INCLUDE/HUMAN_REVIEW |
| D | 판정 결과 + 발송 이력 | 메일 + 발송 결과 | 발송완료/건너뜀/실패 |

---

## 4. 수집 소스 관리 계획

### 4-1. Tier 구조 (source/collector 단위)

동일 기관의 서로 다른 게시판이 각각 다른 Tier가 될 수 있다. `source_id` 단위로 관리한다.

| Tier | 기준 | 예시 | 상세 enrichment 예산 |
|------|------|------|---------------------|
| 1 | 핵심 공식 소스, API 또는 고품질 HTML | bizinfo(기업마당 API), kstartup(K-Startup) | 400건 |
| 2 | 신뢰 가능한 기관, 범용 HTML | NIPA, KIAT, KEIT, KOSME, SBA, 테크노파크 | 40건 |
| 3 | 보조 소스, aggregator 포함 | 기타 민간·재가공 사이트 | 0건 |

### 4-2. 수집 품질 검증

HTTP 성공만으로 판단하지 않는다. 다음을 종합 검증:

- HTTP/API 응답 성공 여부
- 예상 페이지 수 처리 여부
- 필수 필드 파싱률 (title, link, deadline)
- 수집 건수 급감 여부 (전일 대비)
- 제목·URL·접수기간 빈값 비율
- 최신 공고 날짜 신선도
- K-Startup 공공/민간 영역 각각의 성공 여부

### 4-3. 소스 상태 판정

| 상태 | 의미 | 전환 조건 |
|------|------|-----------|
| `OK` | 정상 수집 및 파싱 완료 | 기본 |
| `DEGRADED` | 일부 페이지·필드·영역 실패 | 파싱률 < 80% |
| `FAILING` | 수집 실행 실패 | 연속 3회 실패 |
| `STALE` | 마지막 성공 이후 허용시간 초과 | 24시간 미수집 |
| `DISABLED` | 운영자 비활성화 | 수동 설정 |
| `UNKNOWN` | 초기 상태 또는 판정 불가 | 최초 실행 |

### 4-4. Tier별 장애 정책

| 구분 | Tier 1 | Tier 2 |
|------|--------|--------|
| 최초 실패 | 즉시 알림 | 로그 기록 |
| 연속 실패 | 추적 + 쿨다운 후 재알림 | 임계값 도달 시 경고 |
| 복구 | 1회 복구 알림 | 필요 시 복구 로그 |

알림 쿨다운: `alert_cooldown_minutes = 360` (6시간)

### 4-5. 실행이력·현재상태·장애이력 분리

```
var/state/source_registry.json      — 소스 기본 정보 + 현재 상태
var/state/source_run_history.jsonl   — 실행별 이력 (append-only)
var/state/source_incident_history.jsonl — 장애·복구 이력 (append-only)
```

단일 `source_health.json`에 모든 것을 넣지 않는다.

동시 실행 안전성: `state_store.FileLock` (O_CREAT|O_EXCL) 사용
상태 영속화: `state_store.atomic_write_json()` 사용, `.bak` 백업 자동 생성

---

## 5. 공고 통합·중복 제거 계획

### 5-1. 세 가지 ID/이력 분리

| 항목 | 의미 | 현행 | 변경 |
|------|------|------|------|
| `source_notice_id` | 사이트별 원본 공고 ID | `seen_ids.json` | 유지 (동일소스 재처리 방지) |
| `canonical_notice_id` | 여러 사이트의 동일 사업 통합 ID | 없음 | **신규** |
| `delivery_history` | 특정 그룹에 이미 발송했는지 여부 | `delivery_state.json` | 분리 강화 |

### 5-2. 사이트 간 중복 판정 우선순위

1. 공식 공고번호 비교 (bizinfo PBLN, kstartup 공고번호)
2. 정규화한 공식 원문 URL 비교
3. 실제 신청 URL 비교
4. 안전한 제목 + 기관 + 연도 + 차수 + 접수기간 결합 비교
5. 첨부파일 내용 해시 (P2)
6. 핵심 필드 유사도 비교 (P2)
7. 게시일 차이는 보조정보만

### 5-3. 안전한 제목 정규화

**보존할 정보**: 사업연도, 지역, 모집 차수, 재공고 여부, 추가모집 여부, 수정공고 여부, 접수기간, 주관기관, 사업명 핵심 고유어

**정규화 대상**: 중복 공백, 특수문자, 괄호·구분기호, URL 추적 파라미터

**오중복 방지**: 2025 예비창업패키지 ≠ 2026 예비창업패키지, 서울 공고 ≠ 부산 공고, 1차 모집 ≠ 2차 모집

### 5-4. 버전 관리

수정·재공고·마감연장을 일반 중복으로 삭제하지 않는다:

```
canonical_notice
 ├─ version 1: 최초 공고
 ├─ version 2: 마감연장 (EXTENDED)
 └─ version 3: 지원대상 변경 (UPDATED)
```

| 변경 유형 | 재발송 여부 | 메일 표시 |
|----------|------------|----------|
| 접수기간 연장 | 재발송 또는 변경 알림 | "[마감연장]" |
| 지원대상 변경 | 중요 변경 재발송 | "[업데이트]" |
| 지원금액 변경 | 중요 변경 재발송 | "[업데이트]" |
| 단순 오탈자 | 재발송 안 함 | — |
| 타사이트 재게시 | 재발송 안 함 | — |

### 5-5. 필드 병합

여러 출처 중 하나만 남기지 않고 필드별 최적 출처를 선택:

| 필드 | 우선 출처 |
|------|----------|
| 대표 제목 | 주관기관 공식 제목 |
| 공식 공고문 | 주관기관 URL |
| 신청 링크 | 실제 신청 가능한 공식/K-Startup URL |
| 지원대상 | 최신·신뢰도 높은 구조화 필드 |
| 접수기간 | 최신 수정공고 기준 |
| 추가 출처 | 기업마당, 지역기관 등 (목록으로 표시) |

출처 우선순위: 주관기관 공식 사이트 > 공식 접수 사이트 > K-Startup > 기업마당 > 지역기관 재게시 > 기타 민간

---

## 6. 예비창업 공고 판정 계획

### 6-1. 행정성 공고 제외

**제외 가능 유형** (자동):
- 입찰, 용역, 구매계약
- 심사위원·평가위원·운영위원 모집
- 직원 채용, 재직자 모집
- 결과 발표, 선정 결과, 보도자료, 행정고지
- 운영기관·수행기관·주관기관 모집
- 단순 설명회, 단순 행사 안내

**제외하지 않을 것**: 본문에 `멘토링`, `컨설팅`, `교육`, `입주기업`이 있다는 이유만으로 즉시 제외하지 않는다. 공고의 주된 목적을 기준으로 판정한다.

판정 우선순위: ① 공고의 주된 목적 → ② 제목 → ③ 실제 신청자/모집대상 → ④ 주된 지원내용 → ⑤ 본문 키워드(보조)

### 6-2. 신청자/모집대상/수혜자/운영자 추출

| 역할 | 의미 | 매칭 우선순위 |
|------|------|--------------|
| 신청자 | 실제 신청서를 제출하는 주체 | 최우선 |
| 모집대상 | 공고가 직접 모집하는 대상 | 최우선 |
| 수혜자 | 최종적으로 지원을 받는 주체 | 보조 |
| 운영자 | 프로그램을 운영하는 기관 | 제외 대상 |

추출 우선순위: ① 구조화된 `target_field` → ② 본문 지원대상/신청자격 문단 → ③ 첨부 공고문 → ④ 제목/요약 → ⑤ AI

### 6-3. 예비창업 판정

**인정 가능 표현**: 예비창업자, 창업예정자, 신규 창업 준비자, 사업자등록 미보유자, 선정 후 사업자등록 예정자, 개인 또는 팀 단위의 창업 준비자, 법인설립 전 대표자

**`개인` 단독 인정 금지**: "개인" 단독은 예비창업 근거가 아니다. "개인 또는 팀" AND "창업예정/사업자 미등록"과 결합 시에만 인정.

**명확한 제외 대상**: 사업자등록증 보유기업만 가능, 기존 법인만 가능, 재직자, 컨설턴트·멘토, 교육기관

**예비창업자와 기존 창업기업 동시 모집 시**: 포함

### 6-4. 기존사업자·폐업 조건 (CONDITIONAL)

별도 추출하여 조건부 판정:
- 기존 사업자 보유 여부
- 동일/이종 업종 사업자
- 폐업 이력, 폐업 후 경과기간
- 법인 대표이력, 공동대표 이력
- 선정 전/협약 전 폐업 조건

### 6-5. 주된 지원과 부가 지원 분리

**자동 포함 가능** (주된 지원):
- 사업화자금, 창업지원금, 시제품 제작비, R&D 자금
- 바우처(수출바우처, 마케팅 바우처 등)
- 실증·PoC 비용, 테스트베드 비용
- 입주공간 + 사업화자금 결합

**단독이면 제외** (부가 지원만):
- 교육, 멘토링, 코칭, 상담, 컨설팅, 역량강화
- 세미나, 워크숍, 네트워킹
- 투자·IR·데모데이
- 입주공간만 제공

**복합지원은 포함**: 사업화자금+멘토링, 시제품비+교육, 바우처+컨설팅, 입주공간+사업화자금

### 6-6. 비용지원 수령 주체 확인

`사업비`, `지원금`이 있다고 포함하지 않는다:
- 운영기관 사업비 → 예비창업자 지원금이 아님
- 수행기관 위탁비 → 예비창업자 지원금이 아님
- 대출·융자 안내 → 기본 목적상 제외

핵심 질문: **예비창업자인 신청자가 직접 또는 서비스 형태로 실질적 비용지원을 받는가?**

### 6-7. 지역 판정

**기준**: 게시기관 소재지가 아닌 **신청자의 자격조건 기준**

| 조건 | 처리 |
|------|------|
| 전국 대상 | INCLUDE |
| 서울·경기·인천 대상 | INCLUDE |
| 특정 타지역 거주자만 가능 | EXCLUDE |
| 전국 신청 가능, 선정 후 타지역 이전 필수 | CONDITIONAL_INCLUDE |

### 6-8. 마감 상태 판정

| 상태 | 처리 |
|------|------|
| OPEN | 포함 가능 |
| CLOSED | EXCLUDE |
| ALWAYS_OPEN | 포함 가능 |
| UNTIL_BUDGET_EXHAUSTED | 접수 중으로 처리 |
| EXTENDED | 최신 마감일 적용, 중요 변경으로 관리 |
| UNKNOWN | AI/사람 검토 |

---

## 7. AI 판정 계획

### 7-1. 호출 모드

```text
llm_review_mode = "ambiguous_only"
```

모든 공고를 AI에 보내지 않는다. 규칙 기반으로 명확한 공고는 자동 처리하고, 애매한 공고만 AI에 전달한다.

### 7-2. AI 호출 사유코드

| 사유코드 | 의미 |
|---------|------|
| `TARGET_NOT_FOUND` | 지원대상 추출 실패 |
| `APPLICANT_BENEFICIARY_CONFLICT` | 신청자와 수혜자가 다름 |
| `FINANCIAL_SUPPORT_UNCLEAR` | 비용지원 여부 불명확 |
| `PRIMARY_SUPPORT_MIXED` | 주된지원/부가지원 구분 불명확 |
| `REGION_CONFLICT` | 지역 정보 충돌 |
| `POST_SELECTION_RELOCATION` | 선정 후 이전 조건 |
| `DEADLINE_CONFLICT` | 마감 정보 충돌 |
| `OPERATOR_OR_PARTICIPANT_UNCLEAR` | 운영자/참여자 구분 불명확 |
| `BUSINESS_HISTORY_CONDITION` | 기존사업자/폐업 조건 |
| `ATTACHMENT_ONLY_REQUIREMENT` | 첨부파일에만 자격요건 |
| `POSSIBLE_DUPLICATE` | 중복 의심 |

### 7-3. AI 입력 구조

전체 HTML을 보내지 않고 구조화:
- 제목, 본문 요약, 신청대상 문단, 신청자/수혜자 추출 결과
- 지원내용 문단, 지역조건 문단, 접수기간, 주관기관, 공식 공고번호
- 규칙 기반 판정 결과, 애매함 사유코드

### 7-4. AI 출력 schema

```json
{
  "decision": "INCLUDE | EXCLUDE | CONDITIONAL_INCLUDE | HUMAN_REVIEW",
  "is_prestartup_eligible": true,
  "primary_support_type": "GRANT | VOUCHER | RD | PROTOTYPE | POC | MIXED",
  "financial_support_confirmed": true,
  "region_status": "ELIGIBLE | INELIGIBLE | CONDITIONAL | UNKNOWN",
  "deadline_status": "OPEN | CLOSED | ALWAYS_OPEN | EXTENDED | UNKNOWN",
  "is_participant_recruitment": true,
  "is_operator_recruitment": false,
  "reason_codes": ["PRESTARTUP_EXPLICIT", "FINANCIAL_SUPPORT_CONFIRMED"],
  "evidence": [{"field": "target", "quote": "..."}],
  "summary_reason": "...",
  "confidence": "HIGH | MEDIUM | LOW"
}
```

### 7-5. 캐시·timeout·retry·실패 처리

| 항목 | 설정 |
|------|------|
| 캐시 | 동일 `canonical_notice_id` + 동일 그룹 → 해시 기반, 24시간 TTL |
| timeout | 30초 |
| retry | 2회 |
| 실패 처리 | `HUMAN_REVIEW` (자동 포함/제외 절대 금지) |
| 하루 최대 호출 | 설정 가능 |
| 모델명/버전 | 결과에 저장 |

---

## 8. 메일·리포트 계획

### 8-1. 중복 발송 차단

- `delivery_history`: `(date, tenant, group, recipient)` 조합으로 멱등성 보장
- `delivery_outbox.enc`: 발송 전 암호화 저장 → 크래시 시 재시도
- `acknowledge_completed()`: seen_ids 저장 후 아웃박스 정리

### 8-2. 중요 변경 재발송

- EXTENDED(마감연장), REANNOUNCED(재공고), UPDATED(중요 필드 변경) → 자동 재발송
- 재발송 시 메일에 "[업데이트]" 배지 표시
- `notice_change_delivery`에 기록

### 8-3. 필드 병합 결과 표시

메일에 표시할 필수 정보:

| 항목 | 내용 |
|------|------|
| 공고명 | 공식 또는 통합 제목 |
| 주관기관 | 공식 기관 |
| 신청대상 | 핵심 원문/요약 |
| 예비창업 판정 | 가능/불가/조건부 |
| 주된 지원내용 | 사업화자금, R&D 등 |
| 지원금액 | 확인 가능한 경우 |
| 지역조건 | 전국/수도권/조건부 이전 등 |
| 접수기간 | 시작일·마감일 |
| 판정사유 | 실제 신청 가능 근거 |
| 공식 원문 | 대표 URL |
| 실제 신청링크 | 가능한 경우 |

### 8-4. 조건부 표시

- `CONDITIONAL_INCLUDE` 공고: "[조건부]" 배지 + 조건 설명
- `region_unknown_review` 공고: "[확인 필요]" 표시

### 8-5. 추가 출처

메일 하단에 "다른 출처" 섹션으로 표시:
- 기업마당, K-Startup, 지역기관 등 재게시 URL 목록

---

## 9. 데이터 구조 및 마이그레이션

### 9-1. 논리 데이터 모델

#### Layer A: 소스 관리

| 구조 | 목적 | 핵심 필드 |
|------|------|----------|
| `source_registry` | 소스 설정 | source_id, name, tier, enabled, url, adapter |
| `source_run_history` | 실행 이력 | source_id, timestamp, status, items_count, parse_rate |
| `source_current_health` | 현재 상태 | source_id, status, last_success, last_failure, consecutive_failures |
| `source_incident_history` | 장애 이력 | source_id, event, timestamp, error_message |

#### Layer B: 공고 관리

| 구조 | 목적 | 핵심 필드 |
|------|------|----------|
| `source_notice` | 소스별 원본 공고 | source_notice_id, source_id, title, url, posted_date |
| `canonical_notice` | 통합 공고 | canonical_notice_id, representative_title, official_url, apply_url |
| `notice_version` | 버전 관리 | canonical_notice_id, version, change_type, change_fields, change_timestamp |
| `notice_source_link` | 출처 연결 | canonical_notice_id, source_notice_id, source_id |
| `notice_change_history` | 변경 이력 | canonical_notice_id, version, field, old_value, new_value |

#### Layer C: 판정 관리

| 구조 | 목적 | 핵심 필드 |
|------|------|----------|
| `notice_classification` | 최종 판정 | canonical_notice_id, group_id, decision, reason_codes |
| `notice_target_extraction` | 대상 추출 | canonical_notice_id, applicant_type, target_type, beneficiary_type |
| `notice_support_classification` | 지원 분류 | canonical_notice_id, primary_support, secondary_support, financial_flag |
| `notice_region_eligibility` | 지역 판정 | canonical_notice_id, region_status, region_condition |
| `notice_deadline_status` | 마감 판정 | canonical_notice_id, deadline_status, deadline_date |
| `notice_llm_review` | AI 리뷰 | canonical_notice_id, reason_code, ai_decision, confidence |

#### Layer D: 발송 관리

| 구조 | 목적 | 핵심 필드 |
|------|------|----------|
| `group_delivery_history` | 발송 이력 | date, tenant, group, recipient_token, notice_ids |
| `notice_change_delivery` | 변경 재발송 | canonical_notice_id, version, delivery_date, recipient |

### 9-2. 현행 구조와 매핑

| 논리 모델 | 현행 구현 | 마이그레이션 |
|-----------|----------|-------------|
| `source_registry` | `sites.json` 일부 필드 | `health_status`, `tier` 필드 추가 |
| `source_run_history` | 없음 | 신규 생성 |
| `canonical_notice` | 없음 | 신규 생성 |
| `notice_version` | `notice_versions.json` | `canonical_notice_id` 연결 추가 |
| `notice_classification` | `evaluate_notice()` 반환 dict | 별도 저장으로 분리 |
| `group_delivery_history` | `delivery_state.json` | 구조 유지, 필드 보강 |

### 9-3. 신규 필드/테이블/파일

| 신규 | 위치 |
|------|------|
| `var/state/source_registry.json` | Layer A |
| `var/state/source_run_history.jsonl` | Layer A |
| `var/state/source_current_health.json` | Layer A |
| `var/state/source_incident_history.jsonl` | Layer A |
| `var/state/canonical_notices.json` | Layer B |
| `var/state/notice_classifications.json` | Layer C |
| `var/state/notice_change_delivery.json` | Layer D |

### 9-4. 하위 호환성

- `seen_ids.json`: 동일소스 중복제거 용도로 유지 (역할 축소)
- `delivery_state.json`: 발송 멱등 용도로 유지
- `notice_versions.json`: 버전 관리 용도로 유지 (canonical 연결 추가)
- 기존 메일 형식: 호환 유지, 필드 추가만

### 9-5. 롤백

- 모든 상태 파일은 JSON 기반 → 파일 백업으로 롤백
- `state_store`의 롤링 백업(`.bak` 파일, 최대 14개) 활용
- 신규 파일은 삭제만으로 롤백 가능
- `sites.json` 스키마 확장은 하위 호환 (기존 필드 유지)

---

## 10. 단계별 구현계획

### P0 — 매칭 정확도 즉시 개선

| 작업 | 목적 | 수정 대상 | 선행조건 | 산출물 | 완료조건 |
|------|------|----------|---------|--------|---------|
| 본문 `멘토링/컨설팅/교육` 단독 즉시 제외 제거 | 정상 공고 과제외 방지 | `EXCLUSION_RULES`, `evaluate_notice()` | 없음 | 수정된 필터 로직 | 사례 A 통과 |
| `개인` 단독 예비창업 인정 차단 | 오포함 방지 | `grp_prestartup_ai.or_keywords` | 없음 | 수정된 설정 | 사례 C 통과 |
| 신청자와 수혜자 분리 | 정확한 대상 판정 | `evaluate_notice()` | 없음 | 추출 로직 | 사례 A,C 통과 |
| 교육·멘토링·컨설팅·투자 단독 공고 제외 | 부가 지원만인 공고 제외 | `SUPPORT_TYPE_RULES`, `support_match()` | 없음 | 재설계된 지원유형 | 사례 B,I 통과 |
| 사업화자금+멘토링 복합공고 포함 | 복합지원 포함 | `evaluate_notice()` | 위 2개 | 복합 판정 로직 | 사례 A 통과 |
| 입주공간 단독과 공간+사업비 구분 | 입주 구분 | `EXCLUSION_RULES` | 없음 | 수정된 규칙 | 사례 J 통과 |
| 지원금 수령 주체 구분 | 운영자 사업비 오인 방지 | `evaluate_notice()` | 없음 | 수령주체 로직 | 사례 K 통과 |
| 게시기관이 아닌 신청자 지역 기준 | 지역 판정 수정 | `evaluate_notice()` 지역 부분 | 없음 | 수정된 지역 로직 | 사례 F,G 통과 |
| 점수 기반 자동 포함·제외 중단 | 점수 미사용 | `is_relevant` 판정 로직 | 없음 | 상태값 기반 판정 | 전체 |
| `ambiguous_only` AI 호출 | AI 호출 최소화 | AI 호출 로직 | 없음 | 사유코드 기반 호출 | |
| 판정사유 저장 | 추적 가능 | `evaluate_notice()` 반환값 | 없음 | reason_text | |
| 필수 테스트 15건 작성 | 회귀 방지 | `tests/test_monitor.py` | P0 완료 | 테스트 코드 | 전체 통과 |

### P1 — 소스 안정성과 중복 정확도

| 작업 | 목적 | 수정 대상 | 선행조건 | 산출물 | 완료조건 |
|------|------|----------|---------|--------|---------|
| Tier 필드 추가 | 소스 분류 | `sites.json` | 없음 | Tier 설정 | |
| 데이터 품질 검증 | 수집 품질 확인 | `monitor.py` 수집 후처리 | 없음 | 검증 로직 | |
| 소스 실행이력 관리 | 이력 추적 | 신규 모듈 | 없음 | `source_run_history` | |
| 장애 알림 쿨다운 | 중복 알림 방지 | 알림 로직 | 없음 | 쿨다운 로직 | |
| `canonical_notice_id` 생성 | 크로스소스 통합 | Layer B 모듈 | 없음 | 통합 ID | 사례 D |
| 공식 공고번호 비교 | 중복 판정 | `dedup_items()` 확장 | canonical | 공고번호 매칭 | 사례 D |
| URL 정규화 | 중복 판정 | `normalize_title()` 확장 | 없음 | URL 정규화 | |
| 안전한 제목 비교 | 의미 보존 | `normalize_title()` | 없음 | 수정된 정규화 | 사례 D,E |
| `delivery_history` 분리 | 이력 분리 | Layer D 모듈 | canonical | 분리된 이력 | |
| 버전관리 확장 | 변경 감지 | `notice_versions.json` | canonical | 버전 로직 | 사례 E |
| 중요 변경 재발송 | 재발송 | 발송 로직 | 버전관리 | 재발송 로직 | 사례 E |

### P2 — 고급 중복 및 운영 최적화

| 작업 | 목적 | 수정 대상 | 선행조건 | 산출물 | 완료조건 |
|------|------|----------|---------|--------|---------|
| 첨부파일 해시 | 고급 중복 | Layer B | P1 | 해시 비교 | |
| 핵심 필드 유사도 | 유사 공고 | Layer B | P1 | 유사도 로직 | |
| 필드 병합 정교화 | 다출처 통합 | Layer B | canonical | 병합 로직 | |
| 소스별 고유공고 기여도 | 운영 지표 | 통계 모듈 | 실행이력 | 기여도 통계 | |
| 저효율 소스 비활성 후보 | 최적화 | 대시보드 | 기여도 | 후보 목록 | |
| 운영 대시보드 | 모니터링 | `streamlit_app.py` | 전 모듈 | 대시보드 | |
| 적합도 정렬 점수 | 메일 정렬 | 메일 렌더링 | P0 | 정렬 점수 | |

---

## 11. 테스트 및 검증계획

### 11-1. 단위 테스트

현재 `tests/test_monitor.py`에 47개 테스트 존재. P0에서 15건 이상 추가:
- `evaluate_notice()` 확장 케이스: 복합지원, 단독교육 제외, 입주 구분, 수령주체
- `classify_support_type()` 확장: 주된지원/부가지원 분류
- 지역 판정: 신청자 기준 케이스

### 11-2. 통합 테스트

- 전체 파이프라인: 수집 → 중복제거 → 판정 → 발송 (mock 데이터)
- 크로스소스 중복: 2개 소스에서 동일 공고 수집 → 1건 통합
- 버전 관리: 최초 공고 → 마감연장 → 재발송 플로우

### 11-3. 회귀 테스트

- 기존 47개 테스트 전수 통과 보장
- `EXCLUSION_RULES` 변경 시 기존 케이스 자동 검증

### 11-4. 고정 사례 (테이블)

| 사례 | 공고 내용 | 기대 결과 |
|------|----------|----------|
| A | 사업화자금+멘토링, 예비창업자, 전국 | INCLUDE |
| B | 멘토링만, 예비창업자 | EXCLUDE (MENTORING_ONLY) |
| C | 운영기관 모집, 대학/협회 | EXCLUDE (OPERATOR_RECRUITMENT) |
| D | A사이트 8/17, B사이트 8/18 동일 공고번호 | canonical 1건, 중복 재발송 없음 |
| E | 마감 8/20 → 수정 8/27 | IMPORTANT_UPDATE, 필요 시 재발송 |
| F | 대구 기관 + 전국 예비창업자 대상 | INCLUDE (게시기관 무시) |
| G | 부산 거주자만 가능 | EXCLUDE (REGION_INELIGIBLE) |
| H | 시제품비 + 교육 | INCLUDE |
| I | VC 투자, 데모데이 | EXCLUDE (INVESTMENT_ONLY) |
| J | 입주공간 + 사업화자금 | INCLUDE |
| K | 운영기관 사업비 | EXCLUDE (NOT_PARTICIPANT_SUPPORT) |

### 11-5. Gold set

- 규모: 100~200건 실제 공고
- 라벨링: INCLUDE/EXCLUDE/CONDITIONAL_INCLUDE/HUMAN_REVIEW/DUPLICATE/IMPORTANT_UPDATE
- 측정: Precision, Recall, F1, 사이트 간 중복 제거율, 잘못된 중복 제거율

### 11-6. KPI

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| 정밀도(Precision) | 95%+ | Gold set 대비 |
| 재현율(Recall) | 90%+ | Gold set 대비 |
| 사이트 간 중복 제거율 | 90%+ | Gold set 대비 |
| 잘못된 중복 제거율 | 1% 이하 | Gold set 대비 |
| 사업비+멘토링 오제외 | 0건 | 고정 사례 |
| 운영기관 모집 오포함 | 0건 | 고정 사례 |
| `개인` 단독 오포함 | 0건 | 고정 사례 |
| Tier 1 수집 성공률 | 99%+ | 운영 통계 |
| AI 전달 비율 | 20% 이하 | 운영 통계 |
| AI 실패 자동 처리 | 0건 | 운영 통계 |

---

## 12. 운영 및 모니터링

### 12-1. 운영 통계

일별/주별 최소 통계:
- 소스별 실행 횟수, 성공/부분실패/실패 건수
- 소스별 수집 공고 수, 고유공고 기여 건수, 중복 비율
- 행정성 제외 건수, 사이트 내부/간 중복 건수
- 수정·연장공고 감지 건수
- 예비창업 대상 불일치, 교육·멘토링·투자 단독 제외, 지역 제외, 마감 제외 건수
- 규칙 자동 포함/제외, 조건부 포함 건수
- AI 검토 건수, 포함/제외/실패 건수, 사람확인 건수
- 메일 발송 건수, 중요 변경 재발송 건수

### 12-2. 장애 대응

- Tier 1 즉시 알림 + 쿨다운 후 재알림 + 복구 알림
- Tier 2 로그 기록 + 임계값 경고
- 실행이력과 장애이력을 분리하여 관리

### 12-3. 오탐 분석

- 피드백 O/X 라벨 수집 → 주간 분석
- 오포함/과제외 패턴 식별 → 규칙 개선

### 12-4. 누락 분석

- 미수집 소스 감지: 활성 소스 중 0건 수집
- 미발송 감지: Gold set 중 시스템이 놓친 공고

### 12-5. 소스 효율 관리

- 소스별 고유공고 기여도, 중복률 측정
- 고유공고 기여도가 낮고 중복률이 높은 소스 → 자동 삭제하지 않고 **비활성 후보**로 표시

---

## 13. 위험요인 및 대응

| 위험 | 발생 가능성 | 영향 | 대응방안 |
|------|------------|------|---------|
| 멘토링 포함 공고 과제외 | 높음 | 높음 | P0 우선 수정 + Gold set 검증 |
| `개인` 단독 오포함 | 높음 | 높음 | P0 설정 변경 + 테스트 |
| 크로스소스 오중복 | 중간 | 높음 | 보수적 판정 + HUMAN_REVIEW |
| AI hallucination | 중간 | 높음 | `llm_safety` URL 검증 + fallback_body |
| 소스 구조 변경 | 높음 | 중간 | 상태 모니터링 + 자동 비활성 |
| Gold set 부족 | 중간 | 중간 | 피드백 수집 지속 + 점진적 확대 |
| PII 유출 | 낮음 | 크리티컬 | `private_config` 분리 + git pre-commit |
| 마이그레이션 데이터 유실 | 낮음 | 높음 | 백업 + 원자적 저장 |
| 점수 미사용 시 정렬 어려움 | 중간 | 낮음 | P2에서 정렬용 점수 재도입 |

---

## 14. 최종 완료조건

### §24 자체 누락검사 체크리스트

- [x] 활성 225개 / 비활성 189개 현황을 실제 코드와 대조했는가 → §2
- [x] Tier 1 `bizinfo`, `kstartup` 실제 구현을 확인했는가 → §2, `core_sources.py` 확인
- [x] Tier를 기관명이 아닌 source/collector 단위로 설계했는가 → §4-1
- [x] 수집 성공을 HTTP 성공이 아닌 데이터 품질까지 검증하는가 → §4-2
- [x] `OK/DEGRADED/FAILING/STALE/DISABLED/UNKNOWN` 상태가 있는가 → §4-3
- [x] Tier 1·2 장애정책과 알림 쿨다운이 있는가 → §4-4
- [x] 실행이력·현재상태·incident 이력을 분리했는가 → §4-5
- [x] `seen_ids`, `source_notice_id`, `canonical_notice_id`, 발송이력을 역할별로 분리했는가 → §5-1
- [x] 8/17 A사이트, 8/18 B사이트 동일공고를 하나로 묶는가 → §5-2, 사례 D
- [x] 연도·지역·차수·재공고 정보를 제목 정규화에서 보존하는가 → §5-3
- [x] 수정·재공고·연장공고를 버전 관리하는가 → §5-4
- [x] 중요 변경 재발송 정책이 있는가 → §5-4, §8-2
- [x] 여러 출처의 정보를 병합하는가 → §5-5
- [x] 본문 `멘토링/컨설팅/교육` 단독 즉시 제외를 제거했는가 → §6-1, P0
- [x] `입주기업` 단어 단독 제외를 제거하고 공간 단독/사업비 결합을 구분하는가 → §6-5, P0
- [x] 지원대상 문단을 구조화 필드 → 본문 → 첨부 → 제목/요약 → AI 순으로 추출하는가 → §6-2
- [x] 신청자/모집대상/수혜자/운영자를 구분하는가 → §6-2
- [x] `개인` 단독 예비창업 인정을 차단했는가 → §6-3, P0
- [x] 기존사업자·폐업·대표이력 조건을 조건부 판정할 수 있는가 → §6-4
- [x] 사업화자금+멘토링 같은 복합공고를 포함하는가 → §6-5, 사례 A
- [x] 교육·멘토링·컨설팅·투자·입주 단독 공고를 제외하는가 → §6-5, 사례 B,I
- [x] 운영기관 사업비를 예비창업자의 지원금으로 오인하지 않는가 → §6-6, 사례 K
- [x] 지원금의 실제 수령 주체를 확인하는가 → §6-6
- [x] 게시기관 소재지가 아닌 신청자 지역 기준인가 → §6-7, 사례 F
- [x] 전국 신청 후 타지역 이전조건을 조건부로 표시하는가 → §6-7
- [x] 마감연장을 중요 변경으로 처리하는가 → §5-4, 사례 E
- [x] relevance score를 초기 자동판정 기준으로 사용하지 않는가 → P0
- [x] AI는 `ambiguous_only`가 기본인가 → §7-1
- [x] AI 호출 사유코드가 정의됐는가 → §7-2
- [x] AI 실패 시 `HUMAN_REVIEW`인가 → §7-5
- [x] 실제 공고 100~200건 gold set 검증계획이 있는가 → §11-5
- [x] 정밀도와 재현율을 모두 KPI로 측정하는가 → §11-6
- [x] 사이트 간 잘못된 중복 제거율을 측정하는가 → §11-6
- [x] 소스별 고유공고 기여도와 중복률을 운영지표로 관리하는가 → §12-5
- [x] P0/P1/P2 구현 우선순위가 있는가 → §10
- [x] 최종 계획서에 요구사항 반영 매핑표가 있는가 → §15

---

## 15. 요구사항 반영 매핑표

| 마스터 프롬프트 요구사항 | 반영 절 |
|------------------------|---------|
| §3 4개 계층 분리 | §3 목표 아키텍처 |
| §4-1 Tier는 collector 단위 | §4-1 |
| §4-2 수집 품질 검증 | §4-2 |
| §4-3 소스 상태값 6개 | §4-3 |
| §4-4 Tier별 장애 정책 | §4-4 |
| §4-5 알림 상태 전환 | §4-4 |
| §4-7 상태 저장 분리 | §4-5 |
| §5-1 source/canonical/delivery 분리 | §5-1 |
| §5-2 사이트 간 중복 우선순위 | §5-2 |
| §5-4 제목 정규화에서 정보 보존 | §5-3 |
| §5-5 버전 관리 | §5-4 |
| §5-6 중요 변경 재발송 | §5-4, §8-2 |
| §5-7 필드 병합 | §5-5 |
| §6 행정성 공고 제외 | §6-1 |
| §6-1 멘토링 즉시 제외 제거 | §6-1, P0 |
| §7-2 지원대상 추출 우선순위 | §6-2 |
| §7-3 신청자/모집대상/수혜자/운영자 분리 | §6-2 |
| §7-5 `개인` 단독 인정 금지 | §6-3, P0 |
| §7-7 기존사업자·폐업 조건 | §6-4 |
| §8-1~8-4 주된지원/부가지원 분리 | §6-5 |
| §8-5 입주기업 키워드 일괄 제외 금지 | §6-5, P0 |
| §8-6 수령 주체 확인 | §6-6 |
| §8-7 support_types 재설계 | §6-5, P0 |
| §9-1 신청자 기준 지역 | §6-7 |
| §9-2 지역 판정 기준 | §6-7 |
| §10 마감 상태 | §6-8 |
| §11 relevance_score 비활성 | P0 |
| §12-1 ambiguous_only | §7-1 |
| §12-2 AI 사유코드 | §7-2 |
| §12-3 AI 입력 구조화 | §7-3 |
| §12-4 AI 출력 schema | §7-4 |
| §12-5 AI 운영 통제 | §7-5 |
| §13 판정 상태/사유코드 | §6, §7 |
| §14 데이터 구조 | §9 |
| §15 메일 출력 정보 | §8-3 |
| §16 최종 파이프라인 | §3 데이터 흐름도 |
| §17 P0/P1/P2 | §10 |
| §18 테스트 계획 | §11 |
| §19 KPI | §11-6 |
| §20 운영 통계 | §12 |
| §21 금지사항 | §6, §7, P0 |
| §22 출력 형식 | 본 문서 전체 |
| §23 품질 기준 | 본 문서 전체 |
| §24 자체 검사 | §14 |
