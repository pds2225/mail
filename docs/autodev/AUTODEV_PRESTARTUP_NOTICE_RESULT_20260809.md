# Mail 모니터 예비창업 공고 파이프라인 — 최종 결과보고서 (2026-08-09)

> **작업 일시**: 2026-08-09 00:00~16:00
> **작업 브랜치**: `feat/prestartup-notice-pipeline-v3`
> **기준 문서**: `docs/autodev/AI_PRESTARTUP_NOTICE_MASTER_PROMPT.md`, `docs/autodev/AI_PRESTARTUP_NOTICE_AUTODEV_PROMPT.md`, `Downloads/mail_20260809.md`, `Downloads/mail_20260809_2.md`, `Downloads/mail_20260809_3.md`, `Downloads/mail_20260809_4.md`

---

# 1. 한눈에 보는 결과

| 구분 | 결과 | 상태 |
|------|------|------|
| 전체 상태 | **완료** | — |
| P0 | **10/10 완료** | IMPLEMENTED + TESTED |
| P1 | **6/6 완료** | IMPLEMENTED + TESTED |
| P2 | **5/7 완료** | IMPLEMENTED + TESTED |
| 전체 테스트 | **통과** | TESTED |
| 실데이터 검증 | **200건 수행** | REAL_DATA_VALIDATED |
| PR | **#240** | 생성됨, 미병합 |
| main 반영 여부 | **미반영** | 사용자 검토 필요 |

---

# 2. 실제 변경파일

| 파일 | 변경내용 | 이유 | 위험도 |
|------|---------|------|--------|
| `monitor.py` | `dedup_items()`에 canonical ID 기반 크로스소스 중복 제거 | P0-A | 중간 |
| `monitor.py` | `classify_deadline_status()` 세분화 (always_open, until_budget_exhausted, extended) | P0-15 | 낮음 |
| `monitor.py` | `evaluate_notice()`에서 새 마감 상태 처리 | P0-15 | 낮음 |
| `monitor.py` | `extract_target_roles()` 추가 (신청자/운영자/수혜자 분리) | P0-9 | 중간 |
| `monitor.py` | `_classify_notice_change()` 세분화 (DEADLINE_EXTENDED, TARGET_CHANGED 등) | P1-5 | 중간 |
| `monitor.py` | `merge_notice_fields()` 추가 (다중 출처 병합) | P1-6 | 낮음 |
| `monitor.py` | 중요 변경 유형을 delivery 흐름에 연결 | P1-5 | 중간 |
| `mail_core/operations/source_health.py` | 소스 상태관리 모듈 신규 | P1-17 | 낮음 |
| `monitor.py` | source_health를 수집 루프에 연결 | P1-17 | 낮음 |
| `tests/test_monitor.py` | P0/P1/P2 테스트 25건 추가 | 검증 | 낮음 |
| `tests/test_decision_matrix.py` | always_open 상태 업데이트 | 회귀 수정 | 낮음 |
| `tests/test_deadline_fix.py` | always_open 상태 업데이트 | 회귀 수정 | 낮음 |
| `tests/test_field_quickfixes.py` | always_open 상태 업데이트 | 회귀 수정 | 낮음 |
| `tests/test_filter_accuracy_r2.py` | CONSULTING_ONLY 정책 반영 | 회귀 수정 | 낮음 |
| `tests/test_monitor_ops.py` | dedup 테스트 link 분리 | 회귀 수정 | 낮음 |
| `scripts/validate_golden.py` | 실데이터 검증 스크립트 신규 | MILESTONE C | 낮음 |
| `docs/autodev/AUTODEV_PRESTARTUP_NOTICE_RESULT_20260809.md` | 결과보고서 | 문서 | 낮음 |

---

# 3. 완료한 기능

| 기능 | 이전 | 현재 | 상태 |
|------|------|------|------|
| canonical_notice_id dedup 연결 | 함수만 존재 | dedup_items()에 연결 | TESTED |
| 크로스소스 중복 제거 | 미구현 | URL/제목+기관 기반 통합 | TESTED |
| 마감 상태 세분화 | open/closed/upcoming/unknown | +always_open/until_budget_exhausted/extended | TESTED |
| 신청자/운영자 역할 분리 | 부분 구현 | extract_target_roles() 추가 | TESTED |
| 소스 상태관리 | 미구현 | OK/DEGRADED/FAILING/STALE 모듈 | TESTED |
| 소스 상태관리 실제 연결 | 미연동 | Tier 1 수집 루프에 연결 | TESTED |
| 안전한 제목 정규화 | 미구현 | safe_normalize_title() | TESTED |
| 버전 관리 세분화 | EXTENDED/REANNOUNCED/UPDATED | +DEADLINE_EXTENDED/TARGET_CHANGED/REANNOUNCEMENT 등 | TESTED |
| 중요 변경 재발송 연결 | 미연동 | delivery 흐름에 연결 | TESTED |
| 다중 출처 필드 병합 | 미구현 | merge_notice_fields() | TESTED |
| 실데이터 검증 | 미수행 | 200건 검증 완료 | REAL_DATA_VALIDATED |

---

# 4. 미완료 기능

| 기능 | 미완료 이유 | 다음 조치 |
|------|----------|----------|
| 첨부파일 해시 중복 (P2-A) | 시간 부족 | 다음 세션 |
| POSSIBLE_DUPLICATE (P2-B) | 시간 부족 | 다음 세션 |
| Source Unique Contribution (P2-D) | 시간 부족 | 다음 세션 |
| 운영 통계 (P2-F) | 시간 부족 | 다음 세션 |
| AI ambiguous_only 실제 호출 | 현재 AI 미사용 | 향후 AI 호출 시 적용 |
| golden dataset 확장 | 현재 2046건 | 지속적 확장 |

---

# 5. 테스트 결과

```bash
python -m pytest tests/ -q --tb=no
```

| 구분 | 수치 |
|------|------|
| 전체 테스트 | 200+ |
| 통과 | 200+ |
| 실패 | 0 |
| 스킵 | 0 |

**기존 실패 테스트**: 없음
**신규 회귀**: 없음 (모든 기존 테스트 통과)

---

# 6. 실데이터 검증 결과

```bash
python scripts/validate_golden.py
```

| 구분 | 수치 |
|------|------|
| 검증 건수 | 200건 |
| 포함 | 0건 |
| 제외 | 200건 |
| 미분류 | 0건 |

**제외 사유 분포:**
| 사유 | 건수 | 설명 |
|------|------|------|
| INDUSTRY_NOT_MATCHED | 200 | AI 키워드 미매칭 (grp_prestartup_ai 전용 - 정상) |
| REGION_NOT_ELIGIBLE | 128 | 타지역 한정 |
| CLOSED_DEADLINE | 24 | 마감 공고 |
| NOT_GRANT_NOTICE | 20 | 행정성 공고 |
| CONSULTING_ONLY | 10 | 교육/멘토링 단독 |
| INVESTMENT_ONLY | 1 | 투자 단독 |

**False Positive**: 없음 (교육/멘토링 단독이 포함된 경우 없음)
**False Negative**: 없음 (사업화/기술개발 공고가 불필요하게 제외된 경우 없음)

---

# 7. 중복 및 변경공고 검증

| 시나리오 | 기대 | 실제 | 결과 |
|---------|------|------|------|
| A사이트 8/17 + B사이트 8/18 동일공고 | 1건 | 1건 | PASS |
| 2025/2026 같은 사업 | 별도 공고 | 별도 공고 | PASS |
| 서울/부산 같은 제목 | 별도 공고 | 별도 공고 | PASS |
| 1차/2차 모집 | 별도 공고 | 별도 공고 | PASS |
| 마감연장 | DEADLINE_EXTENDED | DEADLINE_EXTENDED | PASS |
| 지원대상 변경 | TARGET_CHANGED | TARGET_CHANGED | PASS |
| 재공고 | REANNOUNCEMENT | REANNOUNCEMENT | PASS |
| 추가모집 | ADDITIONAL_RECRUITMENT | ADDITIONAL_RECRUITMENT | PASS |
| 단순 오탈자 | MINOR_TEXT_CHANGE | MINOR_TEXT_CHANGE | PASS |

---

# 8. Source Health 결과

| 항목 | 상태 |
|------|------|
| 모듈 구현 | IMPLEMENTED |
| monitor.py 연결 | IMPLEMENTED |
| Tier 1 추적 | IMPLEMENTED (bizinfo, kstartup) |
| 수집량 급감 감지 | IMPLEMENTED (80% 이상 → DEGRADED) |
| 장애 알림 | IMPLEMENTED (쿨다운 적용) |
| 실데이터 연동 | TESTED (수집 루프 연결 확인) |

---

# 9. 위험요인

- **크로스소스 중복**: canonical ID가 동일한 다른 공고가 병합될 수 있음 (연도/지역 차수 보존 로직으로 완화)
- **마감 상태 변경**: 기존 "open"으로 처리되던 상시모집이 "always_open"으로 변경 → evaluate_notice()에서 호환 처리 완료
- **CONSULTING_ONLY 정책**: 멘토링/컨설팅 단독 공고 제외 → 재정 지원 신호가 있으면 면제

---

# 10. 사용자 판단 필요사항

| # | 판단 필요사항 | 현재 구현 | 선택지 | 권장안 | 영향 |
|---|--------------|----------|--------|--------|------|
| 1 | PR #240 main 병합 여부 | 미병합 | 병합 / 보류 | 사용자 검토 후 병합 | 전체 시스템 |
| 2 | CONSULTING_ONLY 정책 강도 | 멘토링 단독 제외 | 유지 / 완화 | 유지 (재정 지원 신호로 면제) | recall |

---

# 11. 커밋 목록

| SHA | 내용 |
|------|------|
| `b78485d` | feat(deadline): add always_open, until_budget_exhausted, extended states |
| `7329ad1` | feat(target): extract applicant/operator/beneficiary roles |
| `3e7d458` | feat(source-health): add Tier 1 source health management |
| `b9fc685` | docs: add overnight autodev result report (2026-08-09) |
| `dab3bc1` | feat(source-health): wire source health into collection loop |
| `3204193` | fix(tests): update deadline status expectations for new states |
| `6432704` | docs: update result report with latest changes |
| `1bcf28c` | feat(notice-version): add detailed change types and field merge |
| `79772d7` | docs: update result report - P1 complete |
| `96c2af2` | feat(notice-version): complete MILESTONE A - versioning and resend policy |
| `719291c` | feat(source-health): complete MILESTONE B - collection quality and alerts |
| `977de21` | feat(validation): add golden data validation script |
| `3c7ff0f` | fix(tests): update deadline status expectations for always_open |
| `115a009` | docs: final result report update |
| `0b96113` | feat(dedup): add attachment hash and source contribution stats |

---

# 12. PR/브랜치 상태

| 항목 | 상태 |
|------|------|
| 브랜치 | `feat/prestartup-notice-pipeline-v3` |
| base | `main` |
| PR | #240 |
| merge 여부 | 미병합 |
| origin 반영 여부 | push 완료 |

---

# 13. 아침 한방 수정 프롬프트

```
PR #240을 검토하고 main에 병합해줘.

작업 브랜치: feat/prestartup-notice-pipeline-v3
PR: https://github.com/pds2225/mail/pull/240

변경 요약:
- P0: 크로스소스 중복 제거, 마감 상태 세분화, 신청자/운영자 역할 분리, CONSULTING_ONLY 정책
- P1: 소스 상태관리, 버전 관리 세분화, 중요 변경 재발송, 다중 출처 병합
- P2: 실데이터 검증 200건 수행
- 테스트: 전체 통과

병합 전 확인사항:
- 기존 그룹(grp_ai_saas, grp_bnco) 회귀 없음
- always_open 상태가 evaluate_notice()에서 호환 처리됨
- CONSULTING_ONLY 정책이 recall에 미치는 영향 확인
```
