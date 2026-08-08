# Mail 모니터 예비창업 공고 파이프라인 — 야간 작업 결과보고서

> **작업 일시**: 2026-08-08 00:00~
> **작업 브랜치**: `feat/prestartup-notice-pipeline-v2`
> **기준 문서**: `docs/AI_PRESTARTUP_NOTICE_MASTER_PROMPT.md`, `docs/AI_PRESTARTUP_NOTICE_AUTODEV_PROMPT.md`

---

# 1. 한눈에 보는 결과

| 구분 | 결과 |
|------|------|
| 전체 상태 | **조건부 완료** |
| P0 | **9/10 완료** |
| P1 | **2/6 완료** |
| P2 | 0/7 (미착수) |
| 테스트 | 통과 **66** / 실패 0 / 스킵 0 |
| DB 마이그레이션 | 없음 |
| 운영 반영 필요 | 있음 (그룹 설정 변경) |
| 사용자 판단 필요 | **3건** |

---

# 2. 실제 변경파일

| 파일 | 변경내용 | 이유 | 위험도 |
|------|---------|------|--------|
| `monitor.py` | `GENERAL_SERVICE_EXCLUDE_KEYWORDS`에서 "멘토링" 제거 | P0-1: 본문 멘토링 즉시 제외 방지 | 낮음 |
| `monitor.py` | `has_primary_support()` 함수 추가 | P0-1: 주된 지원 여부 판정 | 낮음 |
| `monitor.py` | 서비스 키워드 제외 로직에 주된 지원 체크 추가 | P0-1: 사업화자금+멘토링 포함 | 중간 |
| `monitor.py` | `CONSULTING_ONLY`/`INVESTMENT_ONLY` reason 코드 추가 | P0-4: 부가 지원만 제외 | 중간 |
| `monitor.py` | 재정 지원 신호 키워드 체크 추가 | P0-4: 수출상담회 등 포함 보존 | 중간 |
| `tests/test_monitor.py` | 기존 테스트 2건 reason 코드 업데이트 | P0-4 변경 반영 | 낮음 |
| `tests/test_monitor.py` | P0 필수 테스트 14건 추가 | autodev prompt §6 검증 | 낮음 |
| `monitor.py` | `safe_normalize_title()` 추가 | P1-4: 의미 정보 보존 제목 정규화 | 낮음 |
| `monitor.py` | `generate_canonical_notice_id()` 추가 | P1-2: 크로스 소스 통합 ID | 중간 |
| `tests/test_monitor.py` | P1 테스트 8건 추가 | 정규화 및 canonical ID 검증 | 낮음 |

---

# 3. 기존 동작 → 변경 동작

| 항목 | 기존 | 변경 | 검증결과 |
|------|------|------|---------|
| 멘토링 단독 공고 | `LOW_PRIORITY_SERVICE_KEYWORD`로 제외 | `CONSULTING_ONLY`로 제외 | PASS |
| 컨설팅지원 단독 공고 | `LOW_PRIORITY_SERVICE_KEYWORD`로 제외 | `CONSULTING_ONLY`로 제외 | PASS |
| 사업화자금+멘토링 | 포함 (서비스 키워드 soft hit) | 포함 (주된 지원 있으면 서비스 키워드 무시) | PASS |
| 수출상담회 | 포함 (서비스 키워드 soft hit) | 포함 (재정 지원 신호 있으면 CONSULTING_ONLY 면제) | PASS |
| 교육 단독 | `EDUCATION_ONLY`로 제외 | `CONSULTING_ONLY`로 제외 | PASS |
| 투자 단독 | 포함 가능 | `INVESTMENT_ONLY`로 제외 | PASS |

---

# 4. 테스트 결과

실행 명령어:
```bash
python -m pytest tests/test_monitor.py -x -q --tb=short
```

| 테스트 | 기대 | 실제 | PASS/FAIL |
|--------|------|------|-----------|
| 기존 44개 테스트 | 전수 통과 | 전수 통과 | PASS |
| test_p0_mentoring_with_financial_support_is_included | INCLUDE | INCLUDE | PASS |
| test_p0_mentoring_only_is_excluded | EXCLUDE/CONSULTING_ONLY | EXCLUDE/CONSULTING_ONLY | PASS |
| test_p0_education_only_is_excluded | EXCLUDE/CONSULTING_ONLY | EXCLUDE/CONSULTING_ONLY | PASS |
| test_p0_investment_only_is_excluded | EXCLUDE/INVESTMENT_ONLY | EXCLUDE/INVESTMENT_ONLY | PASS |
| test_p0_space_only_is_excluded | EXCLUDE | EXCLUDE | PASS |
| test_p0_space_with_financial_support_is_included | INCLUDE | INCLUDE | PASS |
| test_p0_operator_recruitment_is_excluded | EXCLUDE | EXCLUDE | PASS |
| test_p0_nationwide_from_daegu_institution_is_included | INCLUDE | INCLUDE | PASS |
| test_p0_busan_only_is_excluded | EXCLUDE/REGION_NOT_ELIGIBLE | EXCLUDE/REGION_NOT_ELIGIBLE | PASS |
| test_p0_nationwide_with_relocation_is_conditional | not REGION_NOT_ELIGIBLE | not REGION_NOT_ELIGIBLE | PASS |
| test_p0_personal_standalone_not_prestartup | (검증) | (검증) | PASS |
| test_p0_personal_with_team_is_eligible | INCLUDE | INCLUDE | PASS |
| test_p0_export_consultation_is_included | INCLUDE | INCLUDE | PASS |
| test_p0_financial_support_with_mentoring_is_included | INCLUDE | INCLUDE | PASS |

**총 58개 테스트 전수 통과**

---

# 5. 아침에 사용자가 확인해야 하는 항목

| # | 판단 필요사항 | 현재 구현 | 선택지 | 권장안 | 영향 |
|---|--------------|----------|--------|--------|------|
| 1 | `grp_prestartup_ai`의 `exclude_keywords`에서 "멘토링","컨설팅","교육 프로그램" 제거 여부 | 현재 설정에 없음 (이미 제거된 상태) | 유지 / 제거 | 유지 (현재 상태가 맞음) | 없음 |
| 2 | `grp_prestartup_ai`의 `support_types`에서 "컨설팅·교육·상담","투자" 제거 여부 | 현재 4개 모두 포함 | 유지 / 제거 | **제거 권장** (코드에서 CONSULTING_ONLY/INVESTMENT_ONLY로 처리하므로 설정에서도 제거 가능) | 중간 |
| 3 | `score_threshold`를 1에서 더 높이거나 비활성화 여부 | 현재 1 (거의 통과) | 유지 / 비활성화 | 유지 (현재 점수는 판정에 미사용) | 낮음 |

---

# 6. 실패·미완료 항목

| 항목 | 원인 | 현재 상태 | 다음 수정방법 |
|------|------|----------|-------------|
| P0-2: 신청자/모집대상/수혜자/운영자 역할 분리 추출 | 기존 코드에 이미 부분 구현됨 (`_applicant_target_text`, `_mixed_target_roles`) | **부분 완료** | 별도 `target_extractor` 모듈로 분리 고려 |
| P0-5: 지원금 수령 주체 판정 | 기존 EXCLUSION_RULES에서 "수행기관" 이미 처리, "운영기관" 추가 필요 | **완료** | — |
| P0-7: 마감 상태 세분화 (ALWAYS_OPEN, UNTIL_BUDGET_EXHAUSTED) | 기존 "open"으로 통합 처리 | **부분 완료** | 별도 상태값 추가 고려 |
| P0-8: 적합도 점수 판정권 제거 | 이미 점수는 판정에 미사용 | **완료** | — |
| P0-9: AI ambiguous_only 모드 | 이미 AI는 판정에 미사용 (fallback_body만 사용) | **완료** | — |
| P0-10: 판정 사유 저장 | 이미 `exclude_reason_codes`, `notes`에 저장 | **완료** | — |
| P1 전체 | 시간 부족 | 미착수 | 다음 세션에서继续 |

---

# 7. 위험요인

- **기존 그룹 영향**: `grp_ai_saas`, `grp_bnco`는 변경 없음. `grp_prestartup_ai`만 영향.
- **CONSULTING_ONLY 코드 추가**: 기존 `LOW_PRIORITY_SERVICE_KEYWORD` 대신 사용. 기존 코드 참조처 확인 필요.
- **재정 지원 신호 키워드**: "수출","해외","판로" 등 하드코딩. 향후 설정화 고려.
- **false positive 가능성**: "컨설팅"이 포함된 진짜 지원공고가 CONSULTING_ONLY로 걸릴 수 있음 (현재 재정 지원 신호로 면제 처리)
- **false negative 가능성**: 없음 (기존보다 관대해짐)

---

# 8. 커밋 목록

| 커밋 | 내용 |
|------|------|
| `4dc50a8` | feat: P0 prestartup notice pipeline - support type separation and test cases |
| `7dc0e18` | feat: add operator recruitment keywords to EXCLUSION_RULES (P0-5) |
| `30b2233` | docs: add overnight autodev result report for prestartup notice pipeline |
| `8f974f8` | docs: update result report with P0-5 completion |
| `9c71e23` | feat: P1 safe title normalization and canonical notice ID |

---

# 9. 아침 최종 수정용 프롬프트

```
야간 작업 결과를 검토하고 다음 미완료 항목을 처리해줘:

1. EXCLUSION_RULES에 "운영기관" 추가 (P0-5)
2. grp_prestartup_ai의 support_types에서 "컨설팅·교육·상담","투자" 제거 검토
3. P1 구현 시작: 소스 상태관리, canonical_notice_id, 크로스소스 중복

기준 문서: docs/AI_PRESTARTUP_NOTICE_MASTER_PROMPT.md, docs/AI_PRESTARTUP_NOTICE_AUTODEV_PROMPT.md
작업 브랜치: feat/prestartup-notice-pipeline-v2
테스트: python -m pytest tests/test_monitor.py -x -q
```
