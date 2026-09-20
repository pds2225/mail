# MAIL-014 — 154 Risk × MAIL TASK Crosswalk

- Audit phase: **STRUCTURAL_COVERAGE_V1**
- Generated: 2026-09-20T19:20:00+09:00
- Repo main at start: `2b705b1074433dae55dd9398d3611362a11ad344`
- Source rows: **154/154**
- OPEN_WITHOUT_TASK: **0**

## 주의

**COVERED_BY_TASK는 해결 완료가 아니다.** 담당 TASK를 지정했다는 뜻이다.
`ALREADY_DONE`은 실제 코드 + 테스트/E2E 근거를 확인한 다음 pass에서만 부여한다.

## 원본 집계

- P0: 27
- P1: 107
- P2: 20

- 수집: 20
- 상세보강: 14
- 날짜필터: 14
- 그룹판정: 38
- 기업매칭: 12
- 요약: 14
- 발송: 16
- 피드백: 14
- 상태관리: 12

## 기존 TASK로 계속 처리

- Risk 35~48: MAIL-014의 TASK-021~025
- Risk 49~98: MAIL-014 원자 TASK + MAIL-022 정확도 개선
- Risk 99~112: TASK-042~044
- 저장 동시수정: MAIL-023
- 기존 완료 MAIL TASK의 검증 근거는 다음 evidence pass에서 Risk별로 역연결

## 신규 residual TASK

- **MAIL-024**: 수집 Risk 1~20
- **MAIL-025**: 상세보강 Risk 21~34
- **MAIL-026**: 발송 Risk 113~128
- **MAIL-027**: 피드백 Risk 129~142
- **MAIL-028**: 상태관리 Risk 143~154

각 residual TASK는 "전부 새로 개발"이 아니라 **최신 main에서 이미 해결됐는지 먼저 검증하고 남은 문제만 수정**한다.

## 다음 Checkpoint

1. P0 Risk부터 코드·테스트 evidence 확인
2. 근거 충분 → ALREADY_DONE
3. 부분해결 → COVERED_BY_TASK 유지 + gap 기록
4. 재현 안 됨 → NOT_REPRODUCED 근거를 TASK 결과에 기록
5. 외부환경 필요 → BLOCKED/HUMAN_BATCH
6. crosswalk 재생성



---

# P0 Evidence Pass 1 — 2026-09-20

- P0 total: **27**
- ALREADY_DONE: **13**
- 아직 COVERED/PARTIAL: **14**
- OPEN_WITHOUT_TASK: **0**
- 실제 메일 발송·삭제·라벨 변경: **0**

| Risk | 분류 | 문제 | 판정 | 근거 / 남은 gap |
|---:|---|---|---|---|
| 16 | 수집 | 한 소스 장애가 전체 실행 중단 | ALREADY_DONE | monitor.py::fetch_all — per-future exception isolation; a failed source is recorded in outcomes without aborting other futures<br>tests/test_coverage_p0.py::test_one_failure_does_not_stop_other_classifications<br>tests/test_mail014_p0_risk_regressions.py::test_fetch_all_isolates_one_source_failure |
| 17 | 수집 | 동시 실행 중복 | ALREADY_DONE | .github/workflows/monitor.yml — concurrency group monitor-daily-send, cancel-in-progress=false<br>mail_core/operations/run_lock.py::MonitorRunLock<br>tests/test_p0_hardening.py::test_local_run_lock_allows_only_one_active_sender |
| 20 | 수집 | 링크가 내부망·비정상 URL | ALREADY_DONE | mail_core/security/net_guard.py::check_url<br>tests/test_net_guard.py — scheme/localhost/metadata/private-IP/DNS-private regression coverage |
| 27 | 상세보강 | 악성 첨부파일 | COVERED_BY_TASK | 실행/스크립트 확장자 차단·파일 크기/개수 상한은 있으나 바이러스 스캔/샌드박스 실행 근거는 아직 없음. |
| 28 | 상세보강 | ZIP Bomb | COVERED_BY_TASK | 다운로드 크기 상한은 있으나 ZIP 실제 해제 시 총 팽창크기/압축비 기반 ZIP bomb 방어 E2E 근거는 아직 없음. |
| 96 | 기업매칭 | 개인정보 포함 companies.json | ALREADY_DONE | mail_core/security/private_config.py::split_public_private — removes recipients and company email from public config<br>tests/test_p0_hardening.py::test_private_payload_removes_plaintext_pii_and_enforces_tenant |
| 97 | 기업매칭 | 여러 고객사 데이터 혼합 | COVERED_BY_TASK | tenant별 private recipient 경계는 구현됐으나 matching/storage 전체의 cross-tenant 데이터 격리 E2E를 아직 확정하지 않음. |
| 99 | 요약 | 지원금·기간 환각 | COVERED_BY_TASK | 메일 사실필드는 수집값 기반이지만 LLM 자유텍스트 메모와 facts를 더 엄격히 분리하는 TASK-042가 아직 대기. |
| 101 | 요약 | 여러 공고 정보 혼합 | COVERED_BY_TASK | 공고별 LLM 호출은 분리돼 있으나 구조화 출력/공고 간 혼합 회귀 TASK-043가 아직 대기. |
| 102 | 요약 | 원문 프롬프트 인젝션 | COVERED_BY_TASK | llm_relevance_check가 공고 title/summary를 user prompt에 직접 붙이며 untrusted-data 경계/system instruction 회귀가 아직 없음. |
| 103 | 요약 | 악성 HTML·스크립트 | ALREADY_DONE | monitor.py::_linkify_html — html.escape on body, URL and label<br>tests/test_feedback_loop.py::test_linkify_keeps_notice_links_and_escapes_text |
| 113 | 발송 | 실행 재시도로 중복발송 | ALREADY_DONE | mail_core/delivery/outbox.py::entry_id/upsert<br>monitor.py::deliver_with_outbox<br>tests/test_delivery_checkpoint.py::test_idempotent_skip_on_rerun |
| 114 | 발송 | 일부 수신자 성공 후 오류 | ALREADY_DONE | mail_core/delivery/state.py — recipient-level completion checkpoint<br>mail_core/delivery/outbox.py::settle<br>tests/test_delivery_checkpoint.py::test_partial_failure_retries_only_failed |
| 115 | 발송 | seen_ids를 발송 전에 기록 | ALREADY_DONE | monitor.py::deliver_with_outbox — outbox persisted before SMTP<br>mail_core/delivery/outbox.py::settle/acknowledge_completed — completed row retained until seen_ids acknowledgement<br>tests/test_p0_hardening.py::test_encrypted_outbox_retries_partial_then_waits_for_seen_ack |
| 118 | 발송 | 수신자 이메일 오타 | COVERED_BY_TASK | 이메일 형식 검증·중복 제거는 구현됐으나 bounce 관리/반송 상태 수집까지는 검증되지 않음. |
| 119 | 발송 | To/Cc 사용 오류 | ALREADY_DONE | monitor.py::send_to_list — loops recipients individually<br>monitor.py::_build_mime_message — exactly one To header per message, no Cc<br>tests/test_mail014_p0_risk_regressions.py::test_send_to_list_builds_one_recipient_per_message |
| 120 | 발송 | 그룹 설정 오류 | ALREADY_DONE | monitor.py::guard_group_recipients — tenant-scoped private boundary + allowlist<br>mail_core/security/private_config.py::allowed_recipients — tenant mismatch fails closed<br>tests/test_p0_hardening.py::test_private_payload_removes_plaintext_pii_and_enforces_tenant<br>tests/test_llm_safety.py::test_recipient_allowlist_drops_foreign |
| 126 | 발송 | 테스트 환경 실발송 | ALREADY_DONE | .env.example — ALLOW_SEND_EMAIL=false, DEFAULT_RUN_MODE=dry-run<br>monitor.py::send_email — _ALLOW_SMTP_SEND fail-closed<br>api/run.py — dry-run default; Vercel real-send returns 501<br>tests/test_monitor_ops.py::test_send_to_list_skips_smtp_when_allow_send_false |
| 129 | 피드백 | 이메일 보안봇이 링크 선조회 | ALREADY_DONE | mail_core/delivery/feedback.py — feedback UI is mailto; label is recorded only after signed inbound mail is collected<br>tests/test_feedback_loop.py — feedback roundtrip/readonly collection tests |
| 132 | 피드백 | 토큰 위조 | COVERED_BY_TASK | HMAC 위조 방지는 구현됐지만 토큰 payload에 issued_at/expiry가 없어 '만료시간' 요구가 미충족. |
| 138 | 피드백 | 소수 피드백 즉시 규칙 반영 | COVERED_BY_TASK | 최소 표본수 + 검증셋 통과 후 규칙반영 계약은 MAIL-022에서 구현/검증 예정. |
| 142 | 피드백 | 학습 전 검증 없음 | COVERED_BY_TASK | fixed holdout/Golden regression 기반 승인 배포가 MAIL-022에서 구현/검증 예정. |
| 143 | 상태관리 | JSON 동시쓰기 | COVERED_BY_TASK | 로컬 state는 lock+atomic replace지만 GitHub 수동 저장 동시수정 안전성은 MAIL-023 미완료. |
| 144 | 상태관리 | 실행 중 서버 종료 | COVERED_BY_TASK | recipient delivery checkpoint/outbox는 있으나 전체 monitor pipeline의 단계별 재시작 E2E는 아직 미확정. |
| 149 | 상태관리 | 개인정보가 Git에 포함 | ALREADY_DONE | mail_core/security/private_config.py — tracked JSON is PII-free; private payload stored in encrypted env/SQLite under secrets<br>tests/test_p0_hardening.py::test_private_payload_removes_plaintext_pii_and_enforces_tenant |
| 152 | 상태관리 | 로그에 토큰·메일주소 기록 | COVERED_BY_TASK | 이메일 masking은 다수 경로에 있으나 전체 로그/예외/토큰에 대한 repository-wide 회귀검증이 아직 없음. |
| 153 | 상태관리 | 백업·복구 검증 없음 | COVERED_BY_TASK | state/outbox의 backup recovery 테스트는 있으나 전체 영속상태의 정기 backup+restore drill은 아직 미검증. |

## 다음 순서

1. 실제 gap이 확인된 P0부터 최소 수정한다.
2. 특히 Risk 102(prompt injection), 132(token expiry), 27/28(attachment security), 143/144/153(state/recovery)를 우선한다.
3. MAIL-023/MAIL-022 dependency가 필요한 항목은 기존 TASK 순서를 우회하지 않는다.
4. 각 변경 후 이 crosswalk를 재생성한다.
