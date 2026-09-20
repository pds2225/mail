# MAIL-014 — 154 Risk × MAIL TASK Crosswalk

- Audit phase: **EVIDENCE_PASS_V2**
- Generated: 2026-09-20 19:33 KST
- Repo main at start: `f023d23d235e4c74b12833fb14ce3c25996f820f`
- Source rows: **154/154**
- Invalid MAIL Task refs: **0**
- Duplicate Risk rows: **0**
- OPEN_WITHOUT_TASK: **0**

## 현재 집계

| 상태 | 건수 |
|---|---:|
| ALREADY_DONE | 18 |
| COVERED_BY_TASK | 136 |
| OPEN | 0 |
| BLOCKED | 0 |
| DEFERRED | 0 |
| N_A | 0 |

| 위험도 | 전체 | 미해결/진행 |
|---|---:|---:|
| P0 | 27 | 21 |
| P1 | 107 | 95 |
| P2 | 20 | 20 |

## 이번 evidence pass에서 ALREADY_DONE 확정한 Risk

| Risk | 위험도 | 문제점 | 근거 |
|---:|:---:|---|---|
| 12 | P1 | 중복 소스 수집 | docs/project/TASKS.md#TASK-022<br>tests/test_duplicate_type_classification.py<br>tests/test_kised_iitp_dedup_dates.py |
| 18 | P1 | 비정상적으로 적은 수집건수 | mail_core/operations/coverage_alert.py<br>mail_core/operations/detector_config.py<br>tests/test_coverage_p0.py |
| 19 | P1 | 비정상적으로 많은 수집건수 | mail_core/operations/coverage_alert.py<br>mail_core/operations/detector_config.py<br>tests/test_coverage_p0.py |
| 32 | P1 | 원문 수정 후 캐시가 유지됨 | docs/project/TASKS.md#TASK-023<br>tests/test_notice_version_recovery.py |
| 33 | P1 | 상세보강 실패를 빈 값으로 저장 | mail_core/operations/field_status.py<br>tests/test_field_blank_surface.py |
| 39 | P1 | 공고가 늦게 색인됨 | docs/project/TASKS.md#TASK-021<br>PR #307<br>tests/test_notice_version_recovery.py |
| 46 | P1 | 연장공고를 기존 ID로 차단 | docs/project/TASKS.md#TASK-023<br>docs/project/TASKS.md#TASK-024<br>tests/test_notice_version_recovery.py |
| 47 | P1 | 재공고가 같은 제목으로 등록 | docs/project/TASKS.md#TASK-022<br>docs/project/TASKS.md#TASK-024<br>tests/test_duplicate_type_classification.py<br>tests/test_notice_version_recovery.py |
| 59 | P1 | 규칙 수정 이력 없음 | docs/project/TASKS.md#TASK-028<br>mail_core/operations/rule_version.py<br>tests/test_rule_version_reproducibility.py |
| 67 | P1 | 지역 미상 과다 | mail_core/operations/field_status.py<br>tests/test_field_blank_surface.py |
| 96 | P0 | 개인정보 포함 companies.json | mail_core/security/private_config.py<br>tests/test_streamlit_settings_save.py<br>tests/test_p0_hardening.py |
| 113 | P0 | 실행 재시도로 중복발송 | mail_core/delivery/state.py<br>mail_core/delivery/outbox.py<br>tests/test_p0_hardening.py |
| 114 | P0 | 일부 수신자 성공 후 오류 | mail_core/delivery/state.py<br>mail_core/delivery/outbox.py<br>tests/test_p0_hardening.py |
| 115 | P0 | seen_ids를 발송 전에 기록 | mail_core/delivery/outbox.py<br>mail_core/delivery/state.py<br>tests/test_p0_hardening.py |
| 116 | P1 | 공고 ID만 전역 기록 | mail_core/delivery/state.py<br>mail_core/delivery/outbox.py<br>tests/test_p0_hardening.py |
| 143 | P0 | JSON 동시쓰기 | mail_core/storage/state_store.py<br>mail_core/delivery/state.py<br>tests/test_p0_hardening.py |
| 147 | P1 | 동일 ID의 수정공고 | docs/project/TASKS.md#TASK-023<br>docs/project/TASKS.md#TASK-024<br>tests/test_notice_version_recovery.py |
| 149 | P0 | 개인정보가 Git에 포함 | mail_core/security/private_config.py<br>tests/test_streamlit_settings_save.py<br>tests/test_p0_hardening.py |

**완료 확정 Risk:** 12, 18, 19, 32, 33, 39, 46, 47, 59, 67, 96, 113, 114, 115, 116, 143, 147, 149

## 남은 실행 구조

- MAIL-023: 수동 저장 동시수정/PR 완료 안전성
- MAIL-022: O/X 정확도·Gold/Silver/Review·holdout
- MAIL-024: 수집 Risk 1~20 잔여 evidence + 구현
- MAIL-025: 상세보강 Risk 21~34 잔여 evidence + 구현
- MAIL-026: 발송 Risk 113~128 잔여 evidence + 구현
- MAIL-027: 피드백 Risk 129~142 잔여 evidence + 구현
- MAIL-028: 상태관리 Risk 143~154 잔여 evidence + 구현

COVERED_BY_TASK는 해결 완료를 의미하지 않는다. 각 담당 TASK에서 재현 → 최소 수정 → 테스트/E2E 후 crosswalk를 다시 계산한다.

## 154개 Crosswalk

| Risk | 위험도 | 대분류 | 문제점 | 상태 | MAIL TASK | Atomic TASK |
|---:|:---:|---|---|---|---|---|
| 1 | P1 | 수집 | HTTP 200 응답을 성공으로 판정 | COVERED_BY_TASK | MAIL-014, MAIL-024 | TASK-031 |
| 2 | P1 | 수집 | 사이트 HTML 구조 변경 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 3 | P1 | 수집 | API 스키마 변경 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 4 | P1 | 수집 | 페이지네이션 누락 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 5 | P1 | 수집 | 무한 페이지네이션 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 6 | P1 | 수집 | API 호출 한도 초과 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 7 | P1 | 수집 | 사이트별 차단정책 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 8 | P1 | 수집 | JavaScript 렌더링 의존 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 9 | P1 | 수집 | 인증키·쿠키 만료 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 10 | P2 | 수집 | 인증서·리다이렉트 오류 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 11 | P2 | 수집 | 한글 인코딩 오류 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 12 | P1 | 수집 | 중복 소스 수집 | ALREADY_DONE | MAIL-014, MAIL-024 |  |
| 13 | P1 | 수집 | 소스가 오래된 캐시 제공 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 14 | P2 | 수집 | 활성 사이트 설정 오류 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 15 | P1 | 수집 | 사이트 응답 지연 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 16 | P0 | 수집 | 한 소스 장애가 전체 실행 중단 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 17 | P0 | 수집 | 동시 실행 중복 | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 18 | P1 | 수집 | 비정상적으로 적은 수집건수 | ALREADY_DONE | MAIL-014, MAIL-024 |  |
| 19 | P1 | 수집 | 비정상적으로 많은 수집건수 | ALREADY_DONE | MAIL-014, MAIL-024 |  |
| 20 | P0 | 수집 | 링크가 내부망·비정상 URL | COVERED_BY_TASK | MAIL-014, MAIL-024 |  |
| 21 | P1 | 상세보강 | 목록 URL과 상세 URL 연결 실패 | COVERED_BY_TASK | MAIL-014, MAIL-025 | TASK-031 |
| 22 | P1 | 상세보강 | 상세페이지 N+1 호출 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 23 | P1 | 상세보강 | 상세페이지와 목록 정보 불일치 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 24 | P1 | 상세보강 | 첨부파일에만 핵심정보 존재 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 25 | P1 | 상세보강 | 이미지형 공고문 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 26 | P2 | 상세보강 | 압축파일·암호파일 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 27 | P0 | 상세보강 | 악성 첨부파일 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 28 | P0 | 상세보강 | ZIP Bomb | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 29 | P1 | 상세보강 | 상세페이지 접근 시 세션 필요 | COVERED_BY_TASK | MAIL-014, MAIL-025 | TASK-031 |
| 30 | P1 | 상세보강 | 공고내용 일부만 접혀 있음 | COVERED_BY_TASK | MAIL-014, MAIL-025 | TASK-031 |
| 31 | P1 | 상세보강 | HTML 태그 제거 과정에서 의미 손실 | COVERED_BY_TASK | MAIL-014, MAIL-025 | TASK-031 |
| 32 | P1 | 상세보강 | 원문 수정 후 캐시가 유지됨 | ALREADY_DONE | MAIL-014, MAIL-025 | TASK-031, TASK-023 |
| 33 | P1 | 상세보강 | 상세보강 실패를 빈 값으로 저장 | ALREADY_DONE | MAIL-014, MAIL-025 | TASK-031 |
| 34 | P2 | 상세보강 | 재시도 폭주 | COVERED_BY_TASK | MAIL-014, MAIL-025 |  |
| 35 | P1 | 날짜필터 | 서버 타임존이 UTC | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 36 | P1 | 날짜필터 | 공휴일 데이터 누락 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 37 | P1 | 날짜필터 | 게시일과 등록일 혼동 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 38 | P1 | 날짜필터 | 게시일과 수정일 혼동 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 39 | P1 | 날짜필터 | 공고가 늦게 색인됨 | ALREADY_DONE | MAIL-014 | TASK-021, TASK-025 |
| 40 | P2 | 날짜필터 | 게시일이 날짜만 있고 시간 없음 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 41 | P2 | 날짜필터 | 불완전 날짜 표기 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 42 | P1 | 날짜필터 | 접수개시일을 게시일로 오인 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 43 | P1 | 날짜필터 | 첨부파일 생성일을 게시일로 사용 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 44 | P1 | 날짜필터 | stub 살리기 조건이 과도함 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 45 | P1 | 날짜필터 | stub 살리기 조건이 약함 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025 |
| 46 | P1 | 날짜필터 | 연장공고를 기존 ID로 차단 | ALREADY_DONE | MAIL-014 | TASK-021, TASK-025, TASK-022, TASK-023, TASK-024 |
| 47 | P1 | 날짜필터 | 재공고가 같은 제목으로 등록 | ALREADY_DONE | MAIL-014 | TASK-021, TASK-025, TASK-022, TASK-023, TASK-024 |
| 48 | P1 | 날짜필터 | 날짜 기준이 소스별 상이 | COVERED_BY_TASK | MAIL-014 | TASK-021, TASK-025, TASK-022, TASK-023, TASK-024 |
| 49 | P1 | 그룹판정 | OR/AND 우선순위 불명확 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 50 | P1 | 그룹판정 | 부분문자열 오탐 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 51 | P1 | 그룹판정 | 한글 형태변화 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 52 | P1 | 그룹판정 | 약어·영문명 누락 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 53 | P1 | 그룹판정 | 부정문맥 미처리 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 54 | P1 | 그룹판정 | 제목만 판정 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 55 | P1 | 그룹판정 | 본문 전체 단순매칭 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 56 | P1 | 그룹판정 | 지원유형 분류체계 불명확 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 57 | P1 | 그룹판정 | 복수 지원유형 처리 불가 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 58 | P2 | 그룹판정 | 우선키워드가 너무 강함 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 59 | P1 | 그룹판정 | 규칙 수정 이력 없음 | ALREADY_DONE | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044, TASK-028 |
| 60 | P1 | 그룹판정 | 그룹별 규칙 충돌 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-036, TASK-038, TASK-039, TASK-044 |
| 61 | P1 | 그룹판정 | 전국과 지역제한이 동시에 기재 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 62 | P1 | 그룹판정 | 본사·사업장·공장 기준 혼동 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 63 | P2 | 그룹판정 | 이전 조건 미처리 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 64 | P1 | 그룹판정 | 수도권·비수도권 표현 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 65 | P1 | 그룹판정 | 인천 제외·도서지역 제외 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 66 | P1 | 그룹판정 | 복수지역 공동사업 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 67 | P1 | 그룹판정 | 지역 미상 과다 | ALREADY_DONE | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 68 | P1 | 그룹판정 | 공고기관 주소를 지원지역으로 오인 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 69 | P1 | 그룹판정 | 기업 지역정보 노후화 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 70 | P1 | 그룹판정 | 사업장 다수 기업 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-034, TASK-036, TASK-044 |
| 71 | P1 | 그룹판정 | 종료일만 있고 종료시간 없음 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 72 | P1 | 그룹판정 | 18시·24시 표현 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 73 | P1 | 그룹판정 | 우편접수·도착기준 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 74 | P1 | 그룹판정 | 예산 소진 시 조기마감 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 75 | P2 | 그룹판정 | 선착순 접수 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 76 | P1 | 그룹판정 | 접수기간 연장 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 77 | P1 | 그룹판정 | 상시접수 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 78 | P1 | 그룹판정 | 차수별 모집 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 79 | P1 | 그룹판정 | 마감일이 첨부파일에만 존재 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 80 | P2 | 그룹판정 | 서버 실행 중 날짜 변경 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-032, TASK-036, TASK-044 |
| 81 | P1 | 그룹판정 | 공급기업 키워드만으로 제외 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-033, TASK-037, TASK-044 |
| 82 | P1 | 그룹판정 | 교육·설명회 포함 복합공고 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-033, TASK-037, TASK-044 |
| 83 | P1 | 그룹판정 | 선정기업 전용 문구 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-033, TASK-037, TASK-044 |
| 84 | P1 | 그룹판정 | 제외규칙의 우선순위 불명확 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-033, TASK-037, TASK-044 |
| 85 | P1 | 그룹판정 | 제외규칙 과도 적용 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-033, TASK-037, TASK-044 |
| 86 | P1 | 그룹판정 | 제외 근거 저장 안 함 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-033, TASK-037, TASK-044 |
| 87 | P1 | 기업매칭 | 회사명 자체가 키워드에 매칭 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 88 | P1 | 기업매칭 | 일반적인 키워드 사용 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 89 | P1 | 기업매칭 | 기업정보가 오래됨 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 90 | P1 | 기업매칭 | 기업별 제외조건 없음 | COVERED_BY_TASK | MAIL-014, MAIL-022, MAIL-016 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 91 | P1 | 기업매칭 | 매출·업력 단위 오류 | COVERED_BY_TASK | MAIL-014, MAIL-022, MAIL-016 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 92 | P1 | 기업매칭 | 기업 하나가 여러 그룹 소속 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 93 | P2 | 기업매칭 | 공고 하나가 수십 개 기업에 매칭 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 94 | P1 | 기업매칭 | 기업 키워드와 그룹 규칙 충돌 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 95 | P1 | 기업매칭 | 키워드 매칭 사유 불명확 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 96 | P0 | 기업매칭 | 개인정보 포함 companies.json | ALREADY_DONE | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 97 | P0 | 기업매칭 | 여러 고객사 데이터 혼합 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 98 | P1 | 기업매칭 | 대표자 선호를 기업 적합도로 오인 | COVERED_BY_TASK | MAIL-014, MAIL-022 | TASK-027, TASK-030, TASK-035, TASK-036, TASK-038, TASK-040, TASK-041, TASK-044 |
| 99 | P0 | 요약 | 지원금·기간 환각 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 100 | P1 | 요약 | 조건 일부 생략 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 101 | P0 | 요약 | 여러 공고 정보 혼합 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 102 | P0 | 요약 | 원문 프롬프트 인젝션 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 103 | P0 | 요약 | 악성 HTML·스크립트 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 104 | P1 | 요약 | 잘못된 URL 생성 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 105 | P1 | 요약 | 출력형식 불안정 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 106 | P1 | 요약 | 모델 장애 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 107 | P2 | 요약 | API 비용 폭증 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 108 | P1 | 요약 | 컨텍스트 길이 초과 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 109 | P1 | 요약 | 동일 공고 요약 불일치 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 110 | P1 | 요약 | 최신 수정내용 미반영 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 111 | P1 | 요약 | 모델 버전 변경 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 112 | P1 | 요약 | 공고문 내 개인정보 요약 | COVERED_BY_TASK | MAIL-014 | TASK-042, TASK-043, TASK-044 |
| 113 | P0 | 발송 | 실행 재시도로 중복발송 | ALREADY_DONE | MAIL-014, MAIL-026, MAIL-009 |  |
| 114 | P0 | 발송 | 일부 수신자 성공 후 오류 | ALREADY_DONE | MAIL-014, MAIL-026, MAIL-009 |  |
| 115 | P0 | 발송 | seen_ids를 발송 전에 기록 | ALREADY_DONE | MAIL-014, MAIL-026, MAIL-009 |  |
| 116 | P1 | 발송 | 공고 ID만 전역 기록 | ALREADY_DONE | MAIL-014, MAIL-026, MAIL-009 |  |
| 117 | P1 | 발송 | Gmail Rate Limit | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 118 | P0 | 발송 | 수신자 이메일 오타 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 119 | P0 | 발송 | To/Cc 사용 오류 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 120 | P0 | 발송 | 그룹 설정 오류 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 121 | P2 | 발송 | HTML 템플릿 오류 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 122 | P2 | 발송 | 메일 크기 과다 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 123 | P1 | 발송 | 링크 만료·세션 필요 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 124 | P2 | 발송 | 발송 성공응답만 신뢰 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 125 | P1 | 발송 | 초안 중복생성 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 126 | P0 | 발송 | 테스트 환경 실발송 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 127 | P2 | 발송 | 이메일 제목 중복 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 128 | P1 | 발송 | 수신거부·휴면관리 없음 | COVERED_BY_TASK | MAIL-014, MAIL-026 |  |
| 129 | P0 | 피드백 | 이메일 보안봇이 링크 선조회 | COVERED_BY_TASK | MAIL-014, MAIL-027 |  |
| 130 | P1 | 피드백 | 링크 공유 | COVERED_BY_TASK | MAIL-014, MAIL-027 |  |
| 131 | P1 | 피드백 | 토큰 재사용 | COVERED_BY_TASK | MAIL-014, MAIL-027 |  |
| 132 | P0 | 피드백 | 토큰 위조 | COVERED_BY_TASK | MAIL-014, MAIL-027 |  |
| 133 | P1 | 피드백 | O/X 의미가 불명확 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-018 |  |
| 134 | P1 | 피드백 | 오클릭 수정 불가 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-018 |  |
| 135 | P1 | 피드백 | 자동회신·부재중메일 오인 | COVERED_BY_TASK | MAIL-014, MAIL-027 |  |
| 136 | P1 | 피드백 | 긍정·부정 편향 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 137 | P1 | 피드백 | 탈락공고 피드백 부재 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 138 | P0 | 피드백 | 소수 피드백 즉시 규칙 반영 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 139 | P1 | 피드백 | 그룹 선호와 기업 적격성 혼합 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 140 | P2 | 피드백 | 시간경과에 따른 선호 변화 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 141 | P1 | 피드백 | 사용자별 피드백 혼합 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 142 | P0 | 피드백 | 학습 전 검증 없음 | COVERED_BY_TASK | MAIL-014, MAIL-027, MAIL-022 |  |
| 143 | P0 | 상태관리 | JSON 동시쓰기 | ALREADY_DONE | MAIL-014, MAIL-028, MAIL-023 |  |
| 144 | P0 | 상태관리 | 실행 중 서버 종료 | COVERED_BY_TASK | MAIL-014, MAIL-028 |  |
| 145 | P2 | 상태관리 | seen ID 무한 증가 | COVERED_BY_TASK | MAIL-014, MAIL-028 |  |
| 146 | P1 | 상태관리 | ID 체계 변경 | COVERED_BY_TASK | MAIL-014, MAIL-028 |  |
| 147 | P1 | 상태관리 | 동일 ID의 수정공고 | ALREADY_DONE | MAIL-014, MAIL-028 | TASK-023, TASK-024 |
| 148 | P1 | 상태관리 | Git 커밋 충돌 | COVERED_BY_TASK | MAIL-014, MAIL-028, MAIL-023 |  |
| 149 | P0 | 상태관리 | 개인정보가 Git에 포함 | ALREADY_DONE | MAIL-014, MAIL-028 |  |
| 150 | P1 | 상태관리 | 커밋 실패를 알리지 않음 | COVERED_BY_TASK | MAIL-014, MAIL-028, MAIL-023 |  |
| 151 | P1 | 상태관리 | 롤백 불가 | COVERED_BY_TASK | MAIL-014, MAIL-028 | TASK-028 |
| 152 | P0 | 상태관리 | 로그에 토큰·메일주소 기록 | COVERED_BY_TASK | MAIL-014, MAIL-028 |  |
| 153 | P0 | 상태관리 | 백업·복구 검증 없음 | COVERED_BY_TASK | MAIL-014, MAIL-028 |  |
| 154 | P2 | 상태관리 | 오래된 피드백 누적 | COVERED_BY_TASK | MAIL-014, MAIL-028 |  |
