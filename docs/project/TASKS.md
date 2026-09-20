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
- TASK-031: loop:coding-fix MAIL-P1A-01 [P1] 공고 유효성·quarantine — 신규 모듈
  `mail_core/operations/notice_validity.py`(classify_notice_validity/
  quarantine_invalid_notices). SOURCE_RISK_NO(1, 21, 29–33) 중 실제 미해결 조사
  결과: risk 32·33은 TASK-023/field_status.py가 이미 ALREADY_DONE 감사 완료라
  재개방하지 않음, risk 31(표 구조 손실)은 `_extract_detail_tables()` +
  `tests/test_detail_table_preservation.py`로 이미 커버돼 재구현하지 않음. 실제
  구현한 것: 제목·본문에 로그인/오류/CAPTCHA 신호(`ERROR_PAGE_SIGNAL`, monitor.py의
  기존 `_COVERAGE_ERROR_CONTENT_HINTS`—coverage_alert 집계용—와 동일 신호를 공고
  1건 단위로 재사용, 두 상수는 통합 리팩터하지 않고 문자열만 동기화)와 제목·링크가
  둘 다 없는 경우(`MISSING_REQUIRED_FIELD`)를 quarantine/parse_error로 분리해
  발송 후보(`new_items`)에서 제거. `execute_monitor()`에 `drop_items_from_p0_sources`
  와 동일한 패턴·위치(P0 소스 드롭 직후, 워치리스트/날짜필터 이전 — 워치리스트
  강제포함도 우회 못 함)로 배선했고 `exclude_reason_codes`(비즈니스 규칙 제외)와는
  완전히 분리된 필드(`validity_status`/`validity_reason_code`)로 기록해
  FORBIDDEN(수집실패를 정상 제외로 기록 금지)을 준수한다. **의도적으로 보수적** —
  상세보강 실패(`detail_extraction.status` FAILED)는 quarantine 대상에서 제외했다
  (recall 최우선 정책상 목록 데이터만으로 계속 진행하는 기존 동작을 유지해야
  정상 공고 누락을 막을 수 있음, risk 21은 이 기존 동작으로 충분히 안전하다고
  판단). 테스트: `tests/test_notice_validity.py` 신규 13건(오류페이지 4종 분류·
  parse_error·정상공고 오격리 없음 확인 2건·quarantine_invalid_notices 분리·
  evidence 짧은 근거만 포함·execute_monitor() 통합테스트로 워치리스트 우회 불가
  확인 포함) 전체 통과. 전체 pytest(cp949 무관 실패 1건 제외) 1559건 통과 0 실패,
  회귀 없음(TASK-030 Golden Set 회귀 Harness 포함, 2026-09-20).
- TASK-030: loop:coding-fix MAIL-P0D-05 [P0] Golden Set 회귀 Harness — 신규
  `tests/fixtures/golden_regression_set.json`(비식별·가상 공고 15건 — 실제 고객정보
  아님. FORBIDDEN 준수) + `scripts/golden_regression_check.py`(load_golden_set/
  evaluate_golden_set/compute_recall_summary/run_check, CLI 단독 실행도 가능) +
  `tests/test_golden_regression.py`(pytest 회귀 게이트, 8건). 매 pytest 실행마다
  골든셋 전체를 `evaluate_notice()`로 재평가해 ①핵심소스(`mail_core.matching.
  core_sources.CORE_SOURCE_IDS`=기업마당·K-Startup, 기존 상수 재사용) 재현율
  98% 이상 ②"명백 적합공고"(obvious=true 태그) 재현율 95% 이상을 `assert`로
  강제한다 — 미달 시 pytest가 실패한다(하네스 자기검증 테스트로 실제 FAIL
  발생을 확인함: 핵심소스 항목 1개를 인위로 깨면 10/10→9/10=90%<98%로 정확히
  FAIL). 골든셋 문구는 evaluate_notice()가 현재 규칙으로 실제 100% 통과하는
  것을 확인한 뒤 그대로 담았을 뿐, 임계치를 맞추기 위해 사후 조작하지 않았다
  (FORBIDDEN "목표수치 맞추기 위한 fixture 조작" 준수). 테스트: 신규 8건(fixture
  건전성 2건 + 핵심 게이트 1건 + 하네스 자기검증 2건 + 헬퍼 1건 + CLI 1건 +
  개인정보 미포함 1건) 전체 통과. 전체 pytest(cp949 무관 실패 1건 제외) 1539건
  통과 0 실패, 회귀 없음(2026-09-20).
- TASK-029: loop:coding-fix MAIL-P0D-04 [P0] 누락 원인 리포트 — 신규 진단 CLI
  `scripts/diagnose_notice.py`(이 저장소의 monitor.py-import 스크립트 관례를 따름,
  `mail_core/operations/`가 아님 — mail_core는 monitor.py를 역참조하지 않는 기존 설계
  유지). notice_id를 입력하면 (1) `notice_pipeline_trace`(TASK-026) JSONL을 최근
  30일 역순으로 훑어 마지막 성공단계·첫 실패단계·reason_code를 찾고, (2) `RawStore`
  원문 메타(있으면)를 다시 `evaluate_notice()`에 태워 "지금 규칙 기준" reason_code·
  evidence·rule_version·config_snapshot_id(TASK-027/028)를 함께 보여준다 — 과거
  trace와 현재 재현 결과를 나란히 비교 가능. "실패단계"는 FAILED뿐 아니라 PARTIAL/
  SKIPPED(예: COMPANY_MATCH BELOW_THRESHOLD·EVALUATE REGION_UNKNOWN 리뷰버킷)도
  포함 — 이런 상태도 "왜 최종 후보에 없었는지"의 실제 원인이기 때문. 이메일·전화번호
  패턴은 evidence 표시 전 마스킹(`mask_pii`)하고, 원문 전체(description/상세HTML)는
  어떤 출력에도 포함하지 않는다(FORBIDDEN 준수). trace·원문 메타 어디에도 없는
  notice_id는 `NoticeNotFoundError`를 던지고 CLI는 종료코드 1을 반환한다. 부수
  발견·수정: `RawStore.load_meta()`가 raw_store 루트 폴더가 아예 없을 때(한 번도
  활성화 안 된 경우) `FileNotFoundError`로 죽는 기존 동작을 호출부에서 OSError로
  감싸 진단 도구가 계속 동작하게 함(raw_store.py 자체는 수정하지 않음 — MODIFY_SCOPE
  최소화). 테스트: `tests/test_diagnose_notice.py` 신규 13건 — 누락 샘플 5종(ENRICH
  실패·REGION_NOT_ELIGIBLE·TENANT_ONLY·COMPANY_MATCH 임계치미달·지역미상 리뷰버킷)
  원인 식별 + 그룹별 혼재 결과 + PII 마스킹 2건 + 원문 미노출 + 존재하지 않는 ID
  예외/CLI 종료코드 포함. 전체 pytest(cp949 무관 실패 1건 제외) 1529건 통과 0 실패,
  회귀 없음(2026-09-19). skip 건수가 실행마다 1↔6건으로 흔들리는 기존 특성은
  TASK-028에서 이미 무관 사항으로 기록됨(이번 실행 6건도 동일 특성).
- TASK-028: loop:coding-fix MAIL-P0D-03 [P0] rule_version·판정 재현성 — 신규 모듈
  `mail_core/operations/rule_version.py`(compute_version_hash/config_snapshot_id/
  diff_versions). `evaluate_notice()` 모듈 import 시 자신의 함수 소스(inspect.getsource)
  + 규칙 정의 테이블(EXCLUSION_RULES·키워드 alias 3종)을 합쳐 sha256 16자로 캐싱한
  `rule_version`을 계산 — 판정 로직(코드)이 실제로 바뀌면 자동으로 값이 바뀐다(사람이
  수동으로 버전을 올릴 필요 없음, 잊어버려서 안 올리는 실수 원천 차단). 판정에 쓰인 그룹
  설정(or_keywords/and_keyword_groups/exclude_keywords/priority_keywords/지역조건)만
  골라 해시한 `config_snapshot_id`도 결과에 추가 — 수신자(recipients)·이름 등 개인정보는
  해시 입력에서 명시적으로 제외(FORBIDDEN 준수, "민감설정 저장 0건"). 두 값 모두 결과 dict에
  100% 채워짐(제외 판정 공고도 동일). `diff_versions(before, after)` 헬퍼로 같은
  rule_version+config_snapshot_id인데 판정 결과가 달라지면(`is_relevant`/
  `exclude_reason_codes`/`notice_type`/`target_type` 비교) 비결정성 신호(`nondeterministic`)를
  드러낸다. 테스트: `tests/test_rule_version_reproducibility.py` 신규 12건(재현성·
  config_snapshot 결정성·개인정보 미포함·diff_versions 3종 포함) + 전체 pytest(cp949 무관
  실패 1건 제외) 1521건 통과 0 실패(회귀 없음, 2026-09-19). 참고: skip 건수가 실행마다
  1건↔6건으로 흔들리는 기존 특성 발견 — 실패는 0건으로 동일해 TASK-028과 무관한 사전
  존재 flaky-skip으로 판단(원인 미상, 별도 조사 필요시 후속 과제).
- TASK-027: loop:coding-fix MAIL-P0D-02 [P0] reason_code·evidence 표준화 — 신규 모듈
  `mail_core/operations/reason_code_taxonomy.py`(REASON_CODE_TAXONOMY 29개 코드+설명,
  known_reason_codes/missing_from_taxonomy/describe — 정적 소스 스캔으로 "자동판정
  reason_code 100%" 완전성 검증 가능). `evaluate_notice()`에 `_add_reason(code, evidence)`
  헬퍼를 신설해 기존 `reason_codes.append("X")` 26개 호출부 전부를 교체(판정 로직·조건
  분기는 전혀 바꾸지 않음, 기존 `_extraction_evidence()`(160자 절단, 원문 전체 금지)를
  재사용해 근거를 짧게 자름). 결과 dict에 `reason_evidence: dict[code, str]` 신규 필드
  추가(기존 필드는 그대로, 하위호환). **알려진 갭(의도적 미구현, 정직하게 기록):**
  ① 근거가 지역/마감/입주공간/그룹제외/재공고 등 이해하기 쉬운 코드(~10개)에만 실제 텍스트를
  채웠고, INDUSTRY_NOT_MATCHED 류처럼 "매칭 부재"를 나타내는 코드는 근거가 빈 문자열(코드는
  여전히 기록됨) — 매칭 부재는 보여줄 근거 자체가 없어 자연스러운 상태다. ② "evidence 누락
  시 review로 격하"는 판정 결과(is_relevant)를 바꾸는 동작이라, 26개 호출부 전체의 회귀
  안전성을 이번 세션에서 충분히 검증하기 어려워 **구현하지 않았다** — 다음 후속 TASK에서
  사람 검토와 함께 진행 권장. 테스트: `tests/test_reason_code_evidence.py` 신규 11건(정적
  완전성 검사 3건 포함) + 전체 pytest(cp949 무관 실패 1건 제외) 1498건 통과, 회귀
  없음(2026-09-19).
- TASK-026: loop:coding-fix MAIL-P0D-01 [P0] 공고 단계 Trace 모델 — 신규 구현. 새 모듈
  `mail_core/operations/notice_pipeline_trace.py`(record_stage/flatten_records/
  append_notice_traces/iter_notice_traces, source_run_ledger.py·filter_trace.py와
  동일한 best-effort JSONL append 패턴)를 `execute_monitor()` 6곳에 배선했다: 중복제거
  직후(FETCH+NORMALIZE, NORMALIZE는 별도 단계 함수가 없어 FETCH와 함께 기록), 상세추출
  재시도 직후(ENRICH, detail_extraction.status 기반), 그룹별 diagnostics 직후(EVALUATE,
  included=SUCCESS/review·region_unknown=PARTIAL/excluded=FAILED+reason_code), 기업매칭
  직후(COMPANY_MATCH, 미연결/비활성=SKIPPED·매칭=SUCCESS·강등=PARTIAL — 기존
  refine_included_by_company의 하위호환 pass-through 시맨틱 그대로 반영), 다이제스트
  조립 직후(SUMMARIZE, 미리보기=SKIPPED·실제발송조립=SUCCESS). 저장은 기존
  commit_notice_versions 와 동일하게 `effective_send and persist_seen` 게이트를
  공유해 dry-run/테스트에서 디스크에 아무것도 쓰지 않는다(기존 발송 안전정책과 일치).
  기존 흐름(반환값·제어흐름)은 변경 없음, 모든 기록 지점을 try/except로 감싸 실패해도
  발송을 막지 않는다. 민감정보 없음(notice_id/stage/status/error_code(80자 절단)/
  timestamp만). 테스트: `tests/test_notice_pipeline_trace.py` 신규 12건(모듈 단위 8건 +
  파이프라인 통합 2건: 전체 단계 기록 확인·EVALUATE FAILED reason_code 확인) + 관련
  스위트 220건 통과, 회귀 없음(2026-09-19).
- TASK-025: loop:coding-fix MAIL-P0C-05 [P0] P0-C 회귀 테스트 — **ALREADY_DONE**(코드 변경
  없음). TASK-021~024를 TDD로 진행하며 P0-C 6개 시나리오가 이미 각각 고정 회귀테스트로
  구축돼 있음을 확인했다: 지연색인→`test_three_business_day_window_recovers_delayed_index_and_weekend`,
  마감연장→`test_deadline_extension_creates_versioned_delivery_id`(+`test_real_deadline_extension_still_versions_after_reliable_enrich`),
  지원금변경→`tests/test_monitor.py`의 SUPPORT_AMOUNT_CHANGED 테스트(1457행대),
  재공고→`tests/test_monitor.py`의 REANNOUNCEMENT 테스트(1305·1433행대) +
  `test_repost_marker_added_is_reposted`(교차공고 duplicate_type),
  다기관중복→`test_same_title_different_source_is_multi_agency_duplicate` +
  `test_kised_kstartup_same_pbancsn_cross_dedup` + `test_dedup_keeps_primary_source`,
  단순오탈자→`tests/test_monitor.py`의 MINOR_TEXT_CHANGE 테스트(1367·1449행대) +
  `test_plain_typo_fix_is_not_cancelled`. 6개 시나리오를 한 번에 재실행해 실패 메시지가
  명확한지 확인: `test_notice_version_recovery.py test_monitor.py
  test_duplicate_type_classification.py test_kised_iitp_dedup_dates.py
  test_version_delivery_integration.py test_monitor_ops.py` 178건 통과, 회귀 없음
  (2026-09-19). 이미 분산 구축된 테스트를 하나의 파일로 재조직하는 작업은 실질 가치가
  없어 하지 않는다(관련 없는 리팩터링 금지).
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
