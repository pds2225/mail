# Auto Dev Queue — TASKS

> 이 파일은 자동개발 큐의 작업 목록입니다.
> `scripts/auto_dev_queue.py`가 순차적으로 처리합니다.
> 1회 실행 시 PENDING 목록에서 1개만 처리합니다.

## META (하이브리드 계약 2026-07-30 — 누락제로 가드레일)

- 저장소: `D:\mail` (작업 워크트리 `D:\mail-wt-skipgate`)
- 금지: Secret/API Key 로그 출력, 허위 DONE, force push, 사용자 확인 없이 외부 발송 삭제/정지
- 순서: TASK-G01 → TASK-G03. TASK-G02는 조사만(병렬 가능). TASK-G04∥G05는 G01 이후. TASK-G06은 P2 문서.
- 별칭: G01=계약TASK-01 … G06=계약TASK-06 (기존 DONE TASK-001~018과 충돌 방지)
- MAIL-014 원자 큐: `TASK-021~044` ↔ Google Sheet `AI_TASK_QUEUE`의 `MAIL-P0C-01~MAIL-P1C-03`.
- MAIL-014 상세 실행계약: `docs/project/MAIL014_AI_TASK_SPEC.md`. 각 TASK는 반드시 해당 섹션의 OBJECTIVE / MODIFY_SCOPE / FORBIDDEN / IMPLEMENTATION / ACCEPTANCE_CRITERIA / TEST를 읽고 실행한다.
- 의존 TASK가 DONE이 아니면 구현하지 않고 BLOCKED 처리한다. P0가 DONE 또는 근거 있는 BLOCKED가 되기 전 P1을 시작하지 않는다.

## PENDING
- TASK-020: user-priority overnight: MAIL-012 AI 사업화지원금 전수 수집. 예비창업 AI 그룹에서 사업화지원금이 2차 점수·참여기업 제외로 빠지지 않게 하고 워치리스트로 강제포함. KISED/IITP 소스 공백은 후속 슬라이스. monitor.py 수정 금지. 실발송 금지.
- TASK-025: loop:coding-fix MAIL-P0C-05 [P0] P0-C 회귀 테스트 — DEPENDS=TASK-021~024 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-026: loop:coding-fix MAIL-P0D-01 [P0] 공고 단계 Trace 모델 — DEPENDS=TASK-025 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-027: loop:coding-fix MAIL-P0D-02 [P0] reason_code·evidence 표준화 — DEPENDS=TASK-026 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-028: loop:coding-fix MAIL-P0D-03 [P0] rule_version·판정 재현성 — DEPENDS=TASK-027 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-029: loop:coding-fix MAIL-P0D-04 [P0] 누락 원인 리포트 — DEPENDS=TASK-026~028 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-030: loop:coding-fix MAIL-P0D-05 [P0] Golden Set 회귀 Harness — DEPENDS=TASK-027~028 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-031: loop:coding-fix MAIL-P1A-01 [P1] 공고 유효성·quarantine — DEPENDS=TASK-030 DONE + 모든 P0 종료 — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-032: loop:coding-fix MAIL-P1A-02 [P1] 기간 Hard Gate — DEPENDS=TASK-031 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-033: loop:coding-fix MAIL-P1A-03 [P1] 신청대상·공고목적 역할 판정 — DEPENDS=TASK-031 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-034: loop:coding-fix MAIL-P1A-04 [P1] 지역 자격 Hard Gate — DEPENDS=TASK-031 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-035: loop:coding-fix MAIL-P1A-05 [P1] 기업 기본자격 Hard Gate — DEPENDS=TASK-031 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-036: loop:coding-fix MAIL-P1A-06 [P1] Hard Gate 조합·우선순위 — DEPENDS=TASK-032~035 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-037: loop:coding-fix MAIL-P1A-07 [P1] Hard/Soft Exclusion 분리 — DEPENDS=TASK-036 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-038: loop:coding-fix MAIL-P1B-01 [P1] 관련성 점수 엔진 — DEPENDS=TASK-037 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-039: loop:coding-fix MAIL-P1B-02 [P1] 문서구역·동의어 기반 매칭 — DEPENDS=TASK-038 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-040: loop:coding-fix MAIL-P1B-03 [P1] 기업별 추가 적합성 판정 — DEPENDS=TASK-038~039 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-041: loop:coding-fix MAIL-P1B-04 [P1] 버킷·신뢰도 결합 — DEPENDS=TASK-040 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-042: loop:coding-fix MAIL-P1C-01 [P1] 사실필드 직접출력 — DEPENDS=TASK-041 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-043: loop:coding-fix MAIL-P1C-02 [P1] 구조화 출력·fallback — DEPENDS=TASK-042 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`
- TASK-044: loop:coding-fix MAIL-P1C-03 [P1] 통합 회귀·dry-run — DEPENDS=TASK-037,TASK-041,TASK-043 DONE — spec `docs/project/MAIL014_AI_TASK_SPEC.md`

## RUNNING

## DONE
- TASK-024: loop:coding-fix MAIL-P0C-04 [P0] 중요 변경 판정·재처리 — 기존 material-field
  diff 메커니즘(`_NOTICE_VERSION_MATERIAL_FIELDS`: title/deadline/application_period/
  target/support/region/application_url — MAIL-P0C-01/03에서 이미 구현)이 스펙 material
  필드 7개 중 마감일·지원금·신청대상·지역·접수URL 5개를 이미 커버하고 있었다. 신규로
  `_classify_notice_change()`에 "취소/조기종료" 제목 마커 감지(`_CANCELLATION_MARKER_RE`:
  공고취소/사업취소/모집취소/선정취소/접수취소/조기마감/조기종료/직권취소)를 추가해
  `CANCELLED` reason_code로 최우선 판정하게 했다(단순 오탈자와 구분). **알려진 갭(의도적
  미구현):** "제출서류"(구비서류) 필드는 현재 어떤 수집기도 구조화된 형태로 추출하지 않아
  (grep 0건) diff 대상 자체가 없다 — 새로 만들려면 ~40개 수집기 각각의 HTML 구조 조사가
  필요한 별도 규모의 작업이라 이번 TASK 범위(수정공고 판정 로직) 밖으로 남겨둔다. 회귀:
  `tests/test_notice_version_recovery.py` 신규 3건(CANCELLED 판정 2건 + 오탈자 오탐 방지
  1건) + 관련 스위트 178건 통과, 회귀 없음(2026-09-19).
- TASK-023: loop:coding-fix MAIL-P0C-03 [P0] Notice version·content hash — **ALREADY_DONE**(코드
  변경 없음). `_notice_version_snapshot()`(monitor.py:846)이 판정 핵심필드를 정규화하고
  `_notice_snapshot_hash()`(863)로 content hash를 만들며, `classify_notice_versions()`
  (1121)가 hash·material 필드 diff(`_snapshot_changed_fields`, 979) 기준으로만
  `notice_version`을 증가시키고(1174-1177), `commit_notice_versions()`(1185)가 이전 확정
  스냅샷(`delivered_snapshot`/`delivered_hash`)을 보존해 이전값·신규값 diff 조회가
  가능하다 — MAIL-P0C-01(TASK-021)에서 이미 구현·검증된 인프라가 이 TASK의 3개
  ACCEPTANCE_CRITERIA를 전부 충족한다. 근거 테스트(현재도 통과):
  `test_deadline_extension_creates_versioned_delivery_id`(핵심필드 변경→버전 증가),
  `test_unchanged_seen_notice_is_not_delivered_again`(동일내용 재수집→증가 없음),
  `test_unreliable_observation_commit_preserves_delivered_snapshot`(이전 스냅샷 보존).
  재구현하지 않음(2026-09-19).
- TASK-022: loop:coding-fix MAIL-P0C-02 [P0] Canonical ID·중복 유형 분류 — 기존 `generate_canonical_notice_id`(공고번호>URL>제목+기관+연도+마감)를 그대로 재사용하고, `classify_duplicate_type()`을 신규 구현해 `dedup_items()`의 3개 충돌판정 지점(canonical_id/첨부해시/제목유사도)에 배선했다. 살아남는 item마다 `duplicate_type`(NEW/EXACT_DUPLICATE/MODIFIED/REPOSTED/MULTI_AGENCY_DUPLICATE)을 기록. REPOSTED 판정은 `_classify_notice_change()`와 동일한 재공고/추가모집 리터럴 재사용. 판정 로직 자체(어느 쪽 유지)는 변경 없음. 회귀: `tests/test_duplicate_type_classification.py` 신규 10건 + test_monitor/test_monitor_ops/test_kised_iitp_dedup_dates/test_notice_version_recovery 169건 통과, 회귀 없음(2026-09-19).
- TASK-021: loop:coding-fix MAIL-P0C-01 [P0] 최근 3영업일 재조회 — 주말만 걸러내던 영업일 계산에 설정 가능한 공휴일 목록(`business_holidays`, `MONITOR_BUSINESS_HOLIDAYS` env)을 추가하고, `load_settings()`의 `days_back` 기본값을 1→3으로 맞춰 `execute_monitor()`의 실제 런타임 폴백과 불일치를 없앴다. 기존 dangling WIP 커밋(`163518f3`, 다른 세션이 컨트롤러 하드닝으로 중단)을 검토 후 재사용해 재구현을 피했다. `application_url`/`region` 변경도 버전 판정 대상 필드로 추가. 회귀: `test_notice_version_recovery.py` 23건(신규 4건 포함) + focused 185건 + 전체 pytest 1456 passed/1 skipped(무관 기존 실패 1건 `test_sites_json_public_priority_caps`, config/sites.json cp949 이슈, 이 작업과 무관) 통과, 신규 회귀 없음(2026-09-18). PR #307 squash-merge → `origin/main` `202c7df70a65ea864455b704f32776ba1d9f24d8`.
- TASK-G01 [P0]: skip_gate 기준일 분리 + skip 시 SystemExit(0) 제거·coverage 유지 + am/pm 회차. PR #217 계열. pytest test_mail_review_ops_fixes 통과 (2026-07-30).
- TASK-G02 [P0]: 08:54 발송처 추적 → `docs/project/SENDER_0854_TRACE.md` (주체=monitor.yml schedule, 끄기 절차 기록, 실삭제 없음).
- TASK-G03 [P0]: 기업마당 0건 fail-closed + DATA_GO_KR_KEY 경고 + detector `p0_always`. 테스트 추가.
- TASK-G04 [P1]: short-run 이상치 로그 + coverage artifact `if-no-files-found: warn`.
- TASK-G05 [P1]: 품질 3이슈 회귀(제목 badge / org=title / 연도 꼬리 오판) 테스트·가드.
- TASK-G06 [P2]: 누락제로 가드레일 7원칙 `docs/project/ZERO_MISS_GUARDRAILS.md`.
- TASK-019: mail-daily-review — 발송 후 MDR 검수·`var/reviews/`·`docs/project/mail_daily_reviews/context/` 컨텍스트 적재·monitor.yml 후단 훅·ZERO_MISS/30초 체크 연결 (L규칙 스타일 매일 체크). PR #219.
- TASK-017: user-priority: source_field_quality·monitor_runtime P0 알림/빈필드/KITA 예산 회귀가 유지되는지 테스트로 확인하고 빠지면 보강한다.
- TASK-018: overnight: AUTO_DEV_PAT·AUTO_DEV_AGENT 준비 전제와 schedule 복구 체크리스트를 docs/project/RULES.md에 추가한다 (스케줄 자체는 켜지 않음).
- TASK-016: user-priority: outstanding_dev_audit UNIQUE_CANDIDATE 발견 시 병합 PR 초안 절차를 docs/autodev/LOOP_ENGINEERING_AUTO_DEV.md에 짧게 문서화한다 (monitor.py 수정 금지).
- TASK-015: user-priority overnight readiness — `scripts/auto_dev_overnight_ready.py`로 야간 실행 가능 여부를 판정한다.
- TASK-014: user-priority outstanding merge audit — `scripts/outstanding_dev_audit.py`로 원격/worktree/stash 미반영 개발을 분류한다.
- TASK-013: loop:accuracy-defect 주간 matrix → s3_defects → G1 승인 후 TASK 분해 훅을 설계만 구체화한다 (코딩 금지, 사람 게이트).
- TASK-007: 정책자금 모듈 안정화 후 중진공 등 추가 기관 확장 가능성을 검토한다.
- TASK-006: 소진공 정책자금 페이지 구조 변경에 대비해 파서 selector 안정화를 검토한다.
- TASK-012: loop:gate-repair AUTO_DEV_AGENT 연동 전 FORCE_DONE 경로를 문서화하고 허위 DONE 회귀 테스트를 유지한다.
- TASK-011: loop:coding-fix GHA auto-dev-queue에 loop_verify 전후 게이트 스텝을 명시하고 Summary에 루프 5요소가 나오게 회귀 확인한다.
- TASK-005: Vercel 환경변수 목록과 GitHub Actions Secret 목록을 README 또는 docs/project/RULES.md에 정리한다.
- TASK-004: 메일 수신자 이메일 주소가 로그에 전체 노출되지 않도록 마스킹 원칙을 문서화한다.
- TASK-003: GitHub Actions Summary에 이번 실행 TASK, 결과, 다음 TASK를 표시하도록 auto_dev_queue 스크립트를 보완한다.
- TASK-002: docs/project/RULES.md에 실제 이메일 자동 발송 금지, preview/dry-run 우선 원칙을 추가한다.
- TASK-001: README에 Mail 프로젝트 Auto Dev Queue 사용법을 5줄로 추가한다.
- TASK-008: 지원사업 공고 필터링에 키워드 우선순위, 제외 사유, 남동구/공장/스마트공장 조건, 회귀 테스트를 추가한다.
- TASK-009: 공고 첨부 다운로더 chrome 필터에 미닫힘 footer/nav(malformed HTML) 가드 추가 — 매치 조상 텍스트가 body의 50% 이상이면 chrome으로 보지 않음(적대리뷰 wf_994a588f #1, 2026-07-08).
- TASK-010: eGov FileDown.do 합성 URL 컨텍스트 패스 폴백 — 루트 404/soft-404 시 상세 URL 첫 세그먼트(/portal 등) 접두로 1회 재시도(egov_context_fallback_url, 2026-07-08).

## FAILED

## BLOCKED
