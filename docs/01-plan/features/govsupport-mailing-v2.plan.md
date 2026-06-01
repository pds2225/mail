# Plan: govsupport-mailing-v2 — 정부지원사업 공고 메일링 개선

**Created**: 2026-05-31
**Owner**: ekth3691@gmail.com
**PDCA Phase**: Plan
**Base Repo**: pds2225/mail (D:\mail)

## Executive Summary

| 관점 | 내용 |
|------|------|
| Problem | 기존 monitor.py가 부적합 공고를 발송하고(False Positive), 일부 사이트는 수집조차 실패. UI에는 수신자/필터를 다중 그룹으로 관리하는 흐름이 부족. |
| Solution | 신규개발을 최소화하고, monitor.py의 필터 로직 정밀화 + sites.json 수집 어댑터 보강 + groups.json 다중 그룹 운영 + 대시보드(streamlit_app.py)에 수신자/필터 관리 UI 보강. |
| Function/UX | 적합도 점수 강화·LLM 2차 판정, 사이트별 진단 리포트, 수신자/필터 그룹 CRUD UI, 그룹별 다중 발송. |
| Core Value | 부적합 공고 발송 ↓, 신청 가능한 공고 누락 ↓, 운영자가 직접 그룹/수신자/필터를 안전하게 관리. |

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | 잘못된 공고가 발송되어 신뢰도가 떨어지고, 수집 누락으로 기회 손실이 발생. 운영자는 매번 수동 보정 중. |
| WHO | 인천 남동구 제조/수출 기업 운영자 (1차: ekth3691@gmail.com), 추후 그룹별 다중 수신자. |
| RISK | (1) 실제 메일 오발송 (2) monitor.py 수정 시 기존 안정 동작 회귀 (3) 외부 사이트 SSL/TLS 변화로 수집 재실패. |
| SUCCESS | False Positive 50% 감소, 수집 실패 사이트 진단 리포트 생성, 그룹/수신자/필터 UI에서 코드 수정 없이 운영 가능. |
| SCOPE | monitor.py 필터/수집 로직 한정 수정, streamlit_app.py UI 보강(허용), groups.json/sites.json 운영. **테스트 메일은 ekth3691@gmail.com 1개로만**. |

## 1. Requirements

### Functional
- F1. 필터 정확도 향상: 키워드 매칭 + 가중치 점수 + (선택) LLM 2차 판정으로 적합도 0~100 산출, 임계값 미만 제외.
- F2. 그룹별 다중 필터 운영: groups.json에 N개 그룹(현재 2개) 운영, 그룹마다 다른 키워드/지역/수신자.
- F3. 수신자 추가/제거 UI: streamlit_app.py에서 그룹별 recipients 편집 가능.
- F4. 수집 실패 진단: dry-run 1회 실행으로 사이트별 성공/실패/응답시간/에러유형 리포트 생성.
- F5. 수집 어댑터 복구: 진단 결과 기준 상위 실패 사이트 3~5개 우선 복구(셀렉터/헤더/타임아웃 조정).

### Non-Functional
- NF1. monitor.py 기존 함수 시그니처 유지(회귀 방지).
- NF2. **테스트 단계 메일 발송은 ekth3691@gmail.com 1개로만 한정**.
- NF3. 모든 변경은 dry-run으로 우선 검증 후 실발송.
- NF4. Secret/API Key 출력 금지.

## 2. Success Criteria

| ID | Criteria | Verification |
|----|----------|--------------|
| SC1 | 동일 입력 대비 부적합 공고 발송 수 50% 이상 감소 | dry-run 비교 전/후 발송 후보 수 측정 |
| SC2 | 사이트별 진단 리포트 생성(82개 사이트) | reports/site_diagnostic_YYYYMMDD.md 존재 |
| SC3 | 그룹/수신자 UI에서 추가/삭제 후 즉시 dry-run에 반영 | UI 조작 → groups.json 갱신 → preview 확인 |
| SC4 | 기존 monitor.py 단위 테스트(test_monitor.py) 전부 통과 | `python -m pytest test_monitor.py -v` |
| SC5 | 테스트 발송이 ekth3691@gmail.com 외 주소로 가지 않음 | 발송 로그 마스킹 확인 |

## 3. Out of Scope

- 이메일 인프라 교체(Resend/SendGrid 등) — README 권고만 유지
- customer_intake/, loan/ 모듈 변경
- Vercel 배포 구조 변경
- 신규 DB 도입 (JSON 파일 유지)

## 4. Constraints

- D:\mail는 git repo(브랜치: feature/customer-intake). main 직접 push 금지.
- .env, secrets/, 개인키 커밋 금지.
- monitor.py, streamlit_app.py 수정 시 별도 작업 브랜치 사용.
- 모든 외부 호출은 dry-run 검증 우선.

## 5. Approach (요약, 상세는 Design에서)

1. **진단 먼저**: 별도 진입 스크립트로 `execute_monitor(allow_send=False)` 호출, 사이트별 결과를 reports/에 저장.
2. **필터 정밀화**: monitor.py의 `filter_for_group_with_diagnostics` 주변에 점수/임계값/LLM 2차 판정(선택) 추가.
3. **UI 보강**: streamlit_app.py에 그룹/수신자/필터 편집 화면 추가 또는 기존 화면 정리.
4. **수집 어댑터 복구**: sites.json + monitor.py의 수집 함수에서 진단 상위 실패 사이트만 핀포인트 보강.
5. **테스트 안전망**: 변경 전 groups.json 백업, recipients를 ekth3691@gmail.com만 남기는 테스트용 토글.

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| 실제 메일 오발송 | 테스트 단계 recipients = ekth3691@gmail.com 강제, dry-run 우선 |
| monitor.py 회귀 | test_monitor.py 전체 통과 게이트, 함수 시그니처 유지 |
| LLM 비용 폭증 | 2차 판정은 1차 필터 통과한 후보에만 적용, 일일 호출 상한 |
| 외부 사이트 SSL 변화 | 진단 리포트로 가시화, 복구는 상위 N개만 |
| groups.json 손상 | 변경 전 자동 백업 (groups.backup.YYYYMMDD.json) |

## 7. Next Step

- `/pdca design govsupport-mailing-v2` 로 아키텍처 3안 검토
