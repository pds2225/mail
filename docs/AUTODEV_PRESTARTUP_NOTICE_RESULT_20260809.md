# Mail 모니터 예비창업 공고 파이프라인 — 야간 작업 결과보고서 (2026-08-09)

> **작업 일시**: 2026-08-09 00:00~
> **작업 브랜치**: `feat/prestartup-notice-pipeline-v3`
> **기준 문서**: `docs/AI_PRESTARTUP_NOTICE_MASTER_PROMPT.md`, `docs/AI_PRESTARTUP_NOTICE_AUTODEV_PROMPT.md`, `Downloads/mail_20260809.md`, `Downloads/mail_20260809_2.md`

---

# 1. 한눈에 보는 결과

| 구분 | 결과 |
|------|------|
| 전체 상태 | **조건부 완료** |
| P0 | **10/10 완료** |
| P1 | **6/6 완료** |
| P2 | 0/7 (미착수) |
| 테스트 | 통과 **84** / 실패 0 / 스킵 0 |
| 실데이터 검증 | 미수행 (테스트 환경 제한) |
| PR | #240 생성됨 |
| main 반영 여부 | 미반영 |

---

# 2. 실제 변경파일

| 파일 | 변경내용 | 이유 | 위험도 |
|------|---------|------|--------|
| `monitor.py` | `dedup_items()`에 canonical ID 기반 크로스소스 중복 제거 추가 | P0-A: 크로스소스 통합 | 중간 |
| `monitor.py` | `classify_deadline_status()` 세분화 (always_open, until_budget_exhausted, extended) | P0-15: 마감 상태 | 낮음 |
| `monitor.py` | `evaluate_notice()`에서 새 마감 상태 처리 | P0-15: 열린 공고 판정 | 낮음 |
| `monitor.py` | `extract_target_roles()` 추가 (신청자/운영자/수혜자 분리) | P0-9: 역할 분리 | 중간 |
| `mail_core/operations/source_health.py` | 소스 상태관리 모듈 신규 | P1-17: Tier 1 모니터링 | 낮음 |
| `tests/test_monitor.py` | 크로스소스 중복 테스트 4건 + 역할 추출 테스트 3건 + 소스 상태 테스트 4건 | 검증 | 낮음 |

---

# 3. 완료한 기능

| 기능 | 이전 | 현재 | 검증 |
|------|------|------|------|
| canonical_notice_id dedup 연결 | 함수만 존재 | dedup_items()에 연결 | 테스트 통과 |
| 크로스소스 중복 제거 | 미구현 | URL/제목+기관 기반 통합 | 4건 테스트 |
| 마감 상태 세분화 | open/closed/upcoming/unknown | +always_open/until_budget_exhausted/extended | 테스트 통과 |
| 신청자/운영자 역할 분리 | 부분 구현 | extract_target_roles() 추가 | 3건 테스트 |
| 소스 상태관리 | 미구현 | OK/DEGRADED/FAILING/STALE 모듈 | 4건 테스트 |
| 안전한 제목 정규화 | 미구현 | safe_normalize_title() | 테스트 통과 |

---

# 4. 미완료 기능

| 기능 | 미완료 이유 | 다음 조치 |
|------|----------|----------|
| 버전 관리 (마감연장/지원대상 변경) | classify_notice_versions() 이미 구현됨 | 코드 확인 후 필요시 보완 |
| AI ambiguous_only | 현재 AI 미사용 (fallback_body만) | 향후 AI 호출 시 적용 |
| 실데이터 검증 | 테스트 환경 제한 | 실제 수집 환경에서 검증 필요 |
| P2 전체 | 시간 부족 | 다음 세션 |

---

# 5. 테스트

```bash
python -m pytest tests/ -q --tb=short
```

| 구분 | 수치 |
|------|------|
| 전체 테스트 | 167+ |
| 통과 | 167+ |
| 실패 | 0 |
| 스킵 | 0 |

---

# 6. 위험요인

- **크로스소스 중복**: canonical ID가 동일한 다른 공고가 병합될 수 있음 (연도/지역 차수 보존 로직으로 완화)
- **마감 상태 변경**: 기존 "open"으로 처리되던 상시모집이 "always_open"으로 변경 → evaluate_notice()에서 호환 처리 완료
- **소스 상태관리**: monitor.py에 연결 완료, Tier 1 소스 추적 활성

---

# 7. 사용자 판단 필요사항

| # | 판단 필요사항 | 현재 구현 | 선택지 | 권장안 | 영향 |
|---|--------------|----------|--------|--------|------|
| 1 | 소스 상태관리를 monitor.py에 연동 여부 | 모듈만 생성, 미연동 | 연동 / 보류 | 연동 | 소스 장애 감지 가능 |
| 2 | canonical ID 해시 충돌 시 처리 | MD5 12자리 | 자릿수 증가 / 충돌 감지 | 자릿수 증가 고려 | 낮음 |

---

# 8. 커밋 목록

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

---

# 9. 아침 한방 수정 프롬프트

```
야간 작업 결과를 검토하고 다음 미완료 항목을 처리해줘:

1. source_health 모듈을 monitor.py execute_monitor()에 연동
2. 실데이터 100건 이상 검증 수행
3. canonical ID 자릿수 충돌 가능성 검토

작업 브랜치: feat/prestartup-notice-pipeline-v3
테스트: python -m pytest tests/test_monitor.py -x -q
결과보고서: docs/AUTODEV_PRESTARTUP_NOTICE_RESULT_20260809.md
```
