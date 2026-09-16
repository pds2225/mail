# MAIL-014 — AI 원자 작업 실행 명세

> 목적: 「정부지원사업 자동화서비스 개발리스크 154개」 Google Sheet의 `AI_TASK_QUEUE`를 저장소 안에서 AI가 직접 실행 가능한 고정 명세로 사용한다.
>
> 원본 시트: https://docs.google.com/spreadsheets/d/1e95jsQ0UfILu6GvUrR3G1E0HNBv3aXOGCsc32YCbh1E/edit
> 원본 탭: `AI_TASK_QUEUE`, `AI_AGENT_RULES`, `사용자 우선순위`, `요약`
> 저장소: `pds2225/mail`
> 스냅샷 기준일: 2026-09-16

## 0. 실행 원칙

1. 실행 시점의 직접 작업지시는 루트 `TASK.md`와 `docs/project/TASKS.md`가 기준이다. Google Sheet를 런타임 필수 의존성으로 만들지 않는다.
2. 이 문서는 MAIL-014의 상세 실행 명세다. 시트의 24개 원자 TASK를 저장소에 고정한 스냅샷이다.
3. `docs/project/TASKS.md`의 PENDING 순서대로 1회 1TASK만 수행한다.
4. 각 TASK 시작 전 `AGENTS.md`, 루트 `TASK.md`, `docs/project/RULES.md`, 이 문서를 읽는다.
5. `DEPENDS_ON`이 있는 TASK는 선행 TASK가 DONE이 아니면 구현하지 말고 BLOCKED 처리한다.
6. 작업 전 최신 `main`, 브랜치, 작업트리, 충돌 가능성을 확인한다. 사용자 변경을 삭제하거나 덮어쓰지 않는다.
7. main 직접 위험 변경, force push, `git reset --hard`, `git clean -fd`, `git add -A`를 금지한다.
8. 기본 실행은 dry-run이다. 실제 메일 발송·삭제·대량 라벨 변경은 금지한다.
9. Gmail 비밀번호·앱 비밀번호·API Key·OAuth 토큰·`.env`·고객정보·메일 원문을 코드/로그/GitHub에 기록하지 않는다.
10. IMPLEMENTATION은 최소 구현 체크리스트다. 범위가 커지면 임의 확장하지 말고 BLOCKED 사유를 남긴다.
11. ACCEPTANCE_CRITERIA가 전부 검증되기 전 DONE 처리하지 않는다.
12. 기본 테스트는 저장소 지침에 맞춰 `python3 -m compileall .` 및 관련 `python3 -m pytest ...`를 사용한다. 전체 pytest가 현실적으로 불가능하면 이유와 대체 검증을 결과에 기록한다.
13. P0를 DONE 또는 근거 있는 BLOCKED로 처리하기 전 P1을 시작하지 않는다.
14. 관련성 점수는 기간·신청대상·지역·기업자격 Hard Gate를 절대 우회하지 않는다.
15. 불명확한 자격정보는 임의 추정하지 않고 `unknown`/`review`로 처리한다.
16. 공고명·기관·기간·지역·지원금·URL 등 사실필드는 정규화 데이터에서 직접 사용하고 LLM 생성값으로 덮어쓰지 않는다.
17. 완료보고는 `작업 목표 / 변경 파일 / 주요 변경 / 실행 명령 / 테스트 결과 / 보안 영향 / 충돌 가능성 / 다음 작업`을 포함한다.
18. 각 코드 TASK는 가능하면 전용 브랜치·PR로 제출하고, PR 본문에 변경 목적·주요 변경·테스트·보안 영향·롤백·미완료 사항을 기록한다.

## 1. 판정 아키텍처 고정 원칙

판정은 다음 4계층을 유지한다.

1. 공고 자체 유효성 확인
2. 신청 자격 Hard Gate 판정
3. 그룹·기업 관련성 점수 판정
4. 최종 발송 안전검증

핵심 원칙:

> 기업 키워드가 아무리 강해도 기간·지역·신청대상·기업 기본자격 Hard Gate 탈락을 무효화할 수 없다.

기업 매칭은 탈락공고를 부활시키는 단계가 아니라 Hard Gate를 통과한 공고의 관련성 점수를 높이는 단계다.

---

## MAIL-P0C-01 — 최근 3영업일 재조회

- **QUEUE_ID:** TASK-021
- **SEQ:** 1
- **PRIORITY:** P0
- **EPIC:** P0-C 날짜·중복·수정·재공고
- **SOURCE_RISK_NO:** 35–48
- **DEPENDS_ON:** 없음
- **OBJECTIVE:** 늦게 색인된 공고가 다음 실행에서 복구되도록 조회범위를 최근 3영업일로 확장하고 발송대상은 미처리 공고로 제한한다.
- **MODIFY_SCOPE:** 수집/날짜 필터 관련 Python, 설정, 테스트
- **FORBIDDEN:** 실제 메일 발송 / main 직접 수정 / 기존 단일일 기준 삭제(호환 유지) / 개인정보 로그
- **IMPLEMENTATION:** Asia/Seoul 기준 최근 3영업일 계산 / `published_at`·`registered_at`·`updated_at` 분리 / 3영업일 후보 재수집 / 이미 처리된 후보는 후속 중복단계로 전달
- **ACCEPTANCE_CRITERIA:** 지연색인 fixture가 다음 실행에서 100% 복구 / 동일 공고 후보 중복 생성 0건 / 주말·공휴일 케이스 통과
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0C-02 — Canonical ID·중복 유형 분류

- **QUEUE_ID:** TASK-022
- **SEQ:** 2
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 12, 46–48
- **DEPENDS_ON:** MAIL-P0C-01
- **OBJECTIVE:** 공고 ID 하나에 의존하지 않고 신규·완전중복·수정·재공고·다기관중복을 안정적으로 구분한다.
- **MODIFY_SCOPE:** 공고 정규화/중복제거 Python, 테스트
- **FORBIDDEN:** 기존 원문 삭제 / 제목만으로 동일공고 확정 / 실제 발송
- **IMPLEMENTATION:** 기관+공고번호+정규화 제목+상세URL 기반 canonical key / 기관 ID 없을 때 fallback / `duplicate_type` 저장
- **ACCEPTANCE_CRITERIA:** 5개 중복유형 fixture 정확 분류 / 동일 차수 완전중복 1건 통합 / 다른 차수·기간 별도 유지
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0C-03 — Notice version·content hash

- **QUEUE_ID:** TASK-023
- **SEQ:** 3
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 32, 46–48, 147
- **DEPENDS_ON:** MAIL-P0C-02
- **OBJECTIVE:** 같은 공고의 내용 변경을 버전으로 추적해 연장·수정공고를 재판정 가능하게 한다.
- **MODIFY_SCOPE:** 공고 저장/상태관리 Python, 테스트
- **FORBIDDEN:** 실행상태 전면 DB 전환 / 기존 식별자 파괴 / 실제 발송
- **IMPLEMENTATION:** 판정 핵심필드 정규화 후 content hash / `notice_version` 증가 규칙 / 이전 버전 보존 / 핵심필드 diff
- **ACCEPTANCE_CRITERIA:** 핵심필드 변경 시 버전 증가 / 동일내용 재수집 시 증가 없음 / 이전값·신규값 diff 조회 가능
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0C-04 — 중요 변경 판정·재처리

- **QUEUE_ID:** TASK-024
- **SEQ:** 4
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 46–48, 147
- **DEPENDS_ON:** MAIL-P0C-03
- **OBJECTIVE:** 단순 오탈자와 신청에 영향을 주는 중요 변경을 구분해 중요 변경만 재판정 대상으로 만든다.
- **MODIFY_SCOPE:** 수정공고 판정 Python, 테스트
- **FORBIDDEN:** 담당자 전화/오탈자만으로 재발송 후보 생성 / 실제 발송
- **IMPLEMENTATION:** 중요필드=마감일·지원금·신청대상·지역·제출서류·접수URL·취소/조기종료 / 중요변경 `reason_code` / 재판정 플래그
- **ACCEPTANCE_CRITERIA:** 중요필드 변경 100% 재판정 후보 / 비중요 변경 재발송 후보 0건 / 변경 reason_code 저장
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0C-05 — P0-C 회귀 테스트

- **QUEUE_ID:** TASK-025
- **SEQ:** 5
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 35–48, 147
- **DEPENDS_ON:** MAIL-P0C-01~04
- **OBJECTIVE:** 지연색인·수정·재공고·중복 시나리오가 향후 회귀하지 않도록 고정 테스트를 구축한다.
- **MODIFY_SCOPE:** `tests/`, 테스트 fixture
- **FORBIDDEN:** 운영 데이터·실제 고객정보 fixture / 실제 발송
- **IMPLEMENTATION:** 지연색인 / 마감연장 / 지원금변경 / 재공고 / 다기관중복 / 단순오탈자 시나리오
- **ACCEPTANCE_CRITERIA:** P0-C 시나리오 전부 자동 테스트 / 기존 테스트 회귀 없음 / 실패 원인 메시지 명확
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0D-01 — 공고 단계 Trace 모델

- **QUEUE_ID:** TASK-026
- **SEQ:** 6
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 전 단계
- **DEPENDS_ON:** MAIL-P0C-05
- **OBJECTIVE:** 각 공고가 Fetch→Enrich→Normalize→Evaluate→Company Match→Summarize 중 어디까지 갔는지 추적한다.
- **MODIFY_SCOPE:** 상태/추적 Python, 테스트
- **FORBIDDEN:** 메일 원문 전체 로그 / 개인정보·토큰 로그 / 기존 흐름 강제중단
- **IMPLEMENTATION:** `run_id+notice_id` 기준 stage 기록 / `SUCCESS/PARTIAL/FAILED/SKIPPED` / timestamp·error_code
- **ACCEPTANCE_CRITERIA:** 모든 후보 단계이력 존재 / 한 단계 실패해도 원인 추적 / 민감정보 로그 없음
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0D-02 — reason_code·evidence 표준화

- **QUEUE_ID:** TASK-027
- **SEQ:** 7
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 49–98
- **DEPENDS_ON:** MAIL-P0D-01
- **OBJECTIVE:** 포함·검토·제외 결과마다 기계가 읽을 수 있는 사유 코드와 최소 근거를 저장한다.
- **MODIFY_SCOPE:** 판정 결과 모델/상수/테스트
- **FORBIDDEN:** 근거 없이 excluded / 원문 전체 복제
- **IMPLEMENTATION:** reason_code taxonomy / `evidence_text`는 관련 문장만 / source_field·source_url 연결
- **ACCEPTANCE_CRITERIA:** 자동판정 reason_code 100% / evidence 누락 시 review / 기존 결과와 호환
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0D-03 — rule_version·판정 재현성

- **QUEUE_ID:** TASK-028
- **SEQ:** 8
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 59, 151
- **DEPENDS_ON:** MAIL-P0D-02
- **OBJECTIVE:** 규칙 변경 후 과거 판정을 재현할 수 있도록 rule_version과 설정 스냅샷 식별자를 저장한다.
- **MODIFY_SCOPE:** 규칙 로딩/판정결과 Python, 테스트
- **FORBIDDEN:** Secrets·개인정보 스냅샷 / 전체 설정파일 복제
- **IMPLEMENTATION:** 판정 실행 시 rule_version 생성/참조 / 결과에 version / 변경 전후 비교 helper
- **ACCEPTANCE_CRITERIA:** 평가결과 rule_version 100% / 동일 fixture+동일 version 결과 재현 / 민감설정 저장 0건
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0D-04 — 누락 원인 리포트

- **QUEUE_ID:** TASK-029
- **SEQ:** 9
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 전 단계
- **DEPENDS_ON:** MAIL-P0D-01~03
- **OBJECTIVE:** 특정 공고가 왜 메일 후보에 없었는지 단계별 한 줄 요약으로 확인할 수 있게 한다.
- **MODIFY_SCOPE:** 진단 CLI/리포트 Python, 테스트
- **FORBIDDEN:** 운영 메일 발송 기능 추가 / 원문 전체 출력
- **IMPLEMENTATION:** notice_id 입력→마지막 성공단계·실패단계·reason_code·evidence·rule_version 출력 / 마스킹
- **ACCEPTANCE_CRITERIA:** 누락 샘플 5종 원인 식별 / 개인정보 마스킹 / 존재하지 않는 ID 예외처리
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P0D-05 — Golden Set 회귀 Harness

- **QUEUE_ID:** TASK-030
- **SEQ:** 10
- **PRIORITY:** P0
- **SOURCE_RISK_NO:** 49–98
- **DEPENDS_ON:** MAIL-P0D-02, MAIL-P0D-03
- **OBJECTIVE:** 핵심소스 판정 변경이 적합공고 누락을 증가시키는지 자동 측정한다.
- **MODIFY_SCOPE:** `tests/`, fixtures, 검증 스크립트
- **FORBIDDEN:** 실제 고객정보 / 목표수치 맞추기 위한 fixture 조작
- **IMPLEMENTATION:** 비식별 Golden Set 로더 / expected decision·reason 비교 / 재현율 / 임계치 미달 실패
- **ACCEPTANCE_CRITERIA:** 핵심소스 Golden Set 재현율 98% 이상 기준 검사 / 명백 적합공고 재현율 95% 이상 / 결과 요약
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-01 — 공고 유효성·quarantine

- **QUEUE_ID:** TASK-031
- **SEQ:** 11
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 1, 21, 29–33
- **DEPENDS_ON:** MAIL-P0D-05
- **OBJECTIVE:** 로그인/오류/CAPTCHA 등 정상 공고가 아닌 입력을 excluded와 분리해 quarantine/parse_error로 보낸다.
- **MODIFY_SCOPE:** 입력검증/파서 결과 Python, 테스트
- **FORBIDDEN:** 수집실패를 정상 제외로 기록 / 브라우저 우회 자동화 확대
- **IMPLEMENTATION:** 제목·본문·URL·필수구조 검증 / error page signal / quarantine·parse_error
- **ACCEPTANCE_CRITERIA:** 오류페이지 fixture 자동발송 후보 0건 / 정상공고 오격리 최소화 테스트 / 원인코드 저장
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-02 — 기간 Hard Gate

- **QUEUE_ID:** TASK-032
- **SEQ:** 12
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 35–48, 71–80
- **DEPENDS_ON:** MAIL-P1A-01
- **OBJECTIVE:** 접수상태를 open/upcoming/closing_soon/closed/always_open/budget_based/date_unknown으로 표준화한다.
- **MODIFY_SCOPE:** 날짜/기간 판정 Python, 테스트
- **FORBIDDEN:** 마감일 불명 공고 자동 excluded / AI 추정 날짜 확정
- **IMPLEMENTATION:** Asia/Seoul 상태 / 마감시간 보존 / 상시·예산소진·선착순 / date_unknown→review
- **ACCEPTANCE_CRITERIA:** closed 자동포함 0건 / date_unknown 자동제외 0건 / 마감시각 경계테스트
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-03 — 신청대상·공고목적 역할 판정

- **QUEUE_ID:** TASK-033
- **SEQ:** 13
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 81–86
- **DEPENDS_ON:** MAIL-P1A-01
- **OBJECTIVE:** 키워드가 아니라 누가 신청하고 지원받는지 기준으로 수혜기업/공급기업/교육/행사/선정결과 등을 구분한다.
- **MODIFY_SCOPE:** 판정 규칙/분류 Python, 테스트
- **FORBIDDEN:** `교육`·`설명회`·`공급기업` 단어만으로 무조건 제외
- **IMPLEMENTATION:** purpose taxonomy / applicant_role / beneficiary_role / 수혜기업용 Hard·Soft exclusion
- **ACCEPTANCE_CRITERIA:** 수출기업 대상 교육 vs 수행기관 모집 구분 / 선정결과 일반추천 0건 / reason_code 저장
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-04 — 지역 자격 Hard Gate

- **QUEUE_ID:** TASK-034
- **SEQ:** 14
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 61–70
- **DEPENDS_ON:** MAIL-P1A-01
- **OBJECTIVE:** 전국/시도 키워드가 아니라 본사·사업장·공장 기준과 필수/우대를 구분해 지역자격을 판정한다.
- **MODIFY_SCOPE:** 지역 판정 Python, 설정, 테스트
- **FORBIDDEN:** 기관 주소를 지원지역으로 사용 / unknown을 부적격 확정
- **IMPLEMENTATION:** eligible/ineligible/preferred/conditional/unknown / 본사·사업장·공장 기준 / 기업 다중소재지
- **ACCEPTANCE_CRITERIA:** 명백 타지역 자동추천 0건 / 지역판정 정확도 97% 이상 Golden Set / unknown→review
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-05 — 기업 기본자격 Hard Gate

- **QUEUE_ID:** TASK-035
- **SEQ:** 15
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 87–98
- **DEPENDS_ON:** MAIL-P1A-01
- **OBJECTIVE:** 기업형태·규모·업력·수출실적·고용·인증·사업단계·수혜이력 등 명백한 신청자격을 판정한다.
- **MODIFY_SCOPE:** 기업 프로필/판정 Python, 테스트
- **FORBIDDEN:** 데이터 없음=부적격 / 실제 고객 개인정보 fixture
- **IMPLEMENTATION:** qualification fields 표준화 / pass·fail·unknown / 단위 정규화 / unknown→review
- **ACCEPTANCE_CRITERIA:** 명백 규모·업력 부적격 자동추천 0건 / unknown 자동탈락 0건 / 단위 경계 테스트
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-06 — Hard Gate 조합·우선순위

- **QUEUE_ID:** TASK-036
- **SEQ:** 16
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 49–98
- **DEPENDS_ON:** MAIL-P1A-02, MAIL-P1A-03, MAIL-P1A-04, MAIL-P1A-05
- **OBJECTIVE:** 기간→신청대상/목적→지역→기업자격을 하나의 eligibility 판정으로 결합한다.
- **MODIFY_SCOPE:** `evaluate_notice` 관련 Python, 테스트
- **FORBIDDEN:** 관련성 점수로 fail 덮어쓰기 / 불명확 필드 임의 pass
- **IMPLEMENTATION:** 각 gate pass·fail·unknown / fail 1개 이상 excluded / unknown review / 전부 pass만 scoring
- **ACCEPTANCE_CRITERIA:** Hard Gate 우회 포함 0건 / 조합테스트 통과 / reason_code 100%
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1A-07 — Hard/Soft Exclusion 분리

- **QUEUE_ID:** TASK-037
- **SEQ:** 17
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 81–86
- **DEPENDS_ON:** MAIL-P1A-06
- **OBJECTIVE:** 절대 제외와 선호상 제외를 분리해 누락과 오탐을 동시에 줄인다.
- **MODIFY_SCOPE:** 제외규칙 설정/판정 Python, 테스트
- **FORBIDDEN:** Soft 제외만으로 신청가능 공고 영구 excluded
- **IMPLEMENTATION:** Hard=마감·명백 부적격·선정전용 등 / Soft=정보성·교육 등 그룹별 정책 / 우선순위 고정
- **ACCEPTANCE_CRITERIA:** Hard·Soft 충돌 fixture 결과 고정 / exclusion_type 저장 / Soft 후보 review 가능
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1B-01 — 관련성 점수 엔진

- **QUEUE_ID:** TASK-038
- **SEQ:** 18
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 49–60, 87–95
- **DEPENDS_ON:** MAIL-P1A-07
- **OBJECTIVE:** Hard Gate 통과 공고에 한해 그룹·기업 관련성을 0~100점으로 계산한다.
- **MODIFY_SCOPE:** scoring Python, 설정, 테스트
- **FORBIDDEN:** 점수로 Hard Gate fail 승격 / AI 자유생성 점수
- **IMPLEMENTATION:** 그룹키워드20 + 지원유형20 + 업종/제품20 + 관심사업15 + 지역10 + 기업자격10 + 긴급도5 기본배점 / 설정화
- **ACCEPTANCE_CRITERIA:** 동일 입력 점수 재현 / 합계 0~100 / Hard Gate fail이면 `delivery_allowed=false`
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1B-02 — 문서구역·동의어 기반 매칭

- **QUEUE_ID:** TASK-039
- **SEQ:** 19
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 49–60
- **DEPENDS_ON:** MAIL-P1B-01
- **OBJECTIVE:** 제목·신청대상·지원내용·본문 등 위치별 가중치와 동의어/부정문맥을 반영한다.
- **MODIFY_SCOPE:** 키워드/텍스트 매칭 Python, 사전 설정, 테스트
- **FORBIDDEN:** 단순 부분문자열 매칭만 사용 / 키워드 무제한 확장
- **IMPLEMENTATION:** 제목·신청대상1.0 / 지원내용0.8 / 본문0.5 / 첨부명0.4 / 기관명0.2 / 동의어 cluster / 부정문맥
- **ACCEPTANCE_CRITERIA:** `AI 기업 제외` 긍정매칭 0건 / 제목 직접일치가 본문 1회보다 높은 점수 / 다중 지원유형
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1B-03 — 기업별 추가 적합성 판정

- **QUEUE_ID:** TASK-040
- **SEQ:** 20
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 87–98
- **DEPENDS_ON:** MAIL-P1B-01, MAIL-P1B-02
- **OBJECTIVE:** 그룹 키워드가 약해도 특정 기업의 업종·제품·관심사업과 직접 맞는 공고를 해당 기업에만 추천한다.
- **MODIFY_SCOPE:** 기업매칭 Python, 테스트
- **FORBIDDEN:** 그룹 전체 승격 / Hard Gate 우회 / 회사명 자체를 업종키워드로 사용
- **IMPLEMENTATION:** 회사 프로필 필드별 점수 / 기업별 후보 / 기업필드·매칭근거 저장
- **ACCEPTANCE_CRITERIA:** Hard Gate 통과 후보 재평가 100% / 동일기업 중복표시 0건 / 모든 추천에 기업필드·근거
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1B-04 — 버킷·신뢰도 결합

- **QUEUE_ID:** TASK-041
- **SEQ:** 21
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 87–98
- **DEPENDS_ON:** MAIL-P1B-03
- **OBJECTIVE:** 관련성 점수와 정보 신뢰도를 분리해 included/review/region_unknown/excluded/suppressed를 결정한다.
- **MODIFY_SCOPE:** 버킷 판정 Python, 테스트
- **FORBIDDEN:** 점수 높음만으로 unknown 자격 자동발송
- **IMPLEMENTATION:** 기본 70+ & High→included / 50~69→review / 지역 unknown→region_unknown / Hard fail→excluded / 기발송·중복→suppressed / 임계값 설정화
- **ACCEPTANCE_CRITERIA:** High 아닌 공고 자동 included 0건 / 89점이어도 필수자격 unknown이면 review / 버킷 중복 0건
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1C-01 — 사실필드 직접출력

- **QUEUE_ID:** TASK-042
- **SEQ:** 22
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 99–112
- **DEPENDS_ON:** MAIL-P1B-04
- **OBJECTIVE:** 공고명·기관·기간·지역·금액·URL은 LLM이 생성하지 않고 정규화 데이터에서 직접 출력한다.
- **MODIFY_SCOPE:** 요약/메일 템플릿 Python, 테스트
- **FORBIDDEN:** 실제 메일 발송 / LLM이 URL·마감·지원금 생성
- **IMPLEMENTATION:** facts payload와 narrative 분리 / 템플릿 facts 직접삽입 / Claude에는 적합사유·확인사항만 요청
- **ACCEPTANCE_CRITERIA:** 기간·지역·지원금 원데이터 일치율 100% fixture / LLM이 다른 값을 내도 facts 불변
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1C-02 — 구조화 출력·fallback

- **QUEUE_ID:** TASK-043
- **SEQ:** 23
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 99–112
- **DEPENDS_ON:** MAIL-P1C-01
- **OBJECTIVE:** Claude 장애나 형식오류가 공고 누락으로 이어지지 않게 구조화 출력과 기본 템플릿 fallback을 적용한다.
- **MODIFY_SCOPE:** LLM wrapper/요약 Python, 테스트
- **FORBIDDEN:** 무한 재시도 / 실패 공고 삭제·제외 / 원문 전체 프롬프트 전달
- **IMPLEMENTATION:** JSON schema 검증 / 공고별 독립처리 / 제한 재시도 / deterministic fallback
- **ACCEPTANCE_CRITERIA:** Claude timeout·invalid JSON 시 후보 유지 / 공고 간 정보혼합 0건 / fallback에 facts 포함
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

## MAIL-P1C-03 — P1 통합 회귀·dry-run

- **QUEUE_ID:** TASK-044
- **SEQ:** 24
- **PRIORITY:** P1
- **SOURCE_RISK_NO:** 49–112
- **DEPENDS_ON:** MAIL-P1A-07, MAIL-P1B-04, MAIL-P1C-02
- **OBJECTIVE:** Hard Gate→점수→버킷→요약까지 실제 발송 없이 통합 검증한다.
- **MODIFY_SCOPE:** 통합 테스트/fixture/문서
- **FORBIDDEN:** `ALLOW_SEND_EMAIL=true` / 실제 수신자 / main 직접 수정
- **IMPLEMENTATION:** 대표 적합·부적합·unknown·수정공고 fixture / dry-run output / 단계 trace와 결과 일치
- **ACCEPTANCE_CRITERIA:** 실제 발송 0건 / Hard Gate 우회 0건 / 사실필드 오류 0건 / 전체 관련 pytest 통과
- **TEST:** `python3 -m compileall .` / 관련 `python3 -m pytest ...`

---

## 2. 큐 상태 갱신 규칙

- 시작: 해당 `TASK-xxx`를 `PENDING → RUNNING`으로 이동한다.
- 완료: ACCEPTANCE_CRITERIA 검증 후 `DONE`으로 이동하고 코드·테스트·PR 근거를 남긴다.
- 실패: 재현 가능한 코드/테스트 실패면 `FAILED`; 외부 조건·선행조건 미충족이면 `BLOCKED`.
- 선행 TASK가 실패/차단된 경우 의존 TASK는 구현하지 않는다.
- Sheet의 상태값을 자동으로 덮어쓰지 않는다. 필요 시 GitHub 결과를 근거로 별도 동기화한다.

## 3. 최종 완료 조건

MAIL-014는 다음을 모두 충족할 때만 완료로 본다.

- MAIL-P0C-01~05 실제 미해결분 해결 및 회귀검증
- MAIL-P0D-01~05 실제 미해결분 해결 및 추적 가능
- MAIL-P1A-01~07 Hard Gate·제외 규칙 검증
- MAIL-P1B-01~04 관련성 점수·기업매칭이 Hard Gate를 우회하지 않음
- MAIL-P1C-01~03 사실필드 안정화 및 dry-run 통합검증
- 이미 구현된 항목은 코드·테스트 근거가 있는 경우에만 `ALREADY_DONE`으로 대체 가능
- 실제 이메일 발송·삭제·라벨 변경 0건
- 변경 파일·테스트 결과·보안 영향·충돌 가능성·남은 리스크 보고
