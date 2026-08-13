# mail

> 이 파일은 이 GitHub 레포의 유일한 AI 작업지시 기준이다.
> Google Tasks와는 완전히 별개이며 Google Tasks의 항목을 조회·복사·동기화하지 않는다.

---

# 0. TASK LIST

<!--
비개발자가 이 부분만 보고도 현재 작업을 이해·수정·삭제할 수 있어야 한다.
상태: 대기 / 진행 중 / 완료 / 막힘 / 취소 는 아래 기호만 사용한다.
TASK 1개 = 반드시 1줄. LIST의 TASK_ID와 DETAILS의 TASK_ID는 반드시 1:1.
사용자가 "삭제"하면 LIST + DETAILS 모두 삭제. "취소"하면 취소 상태로 보존 가능.
REQUEST_SOLVED=YES가 아닌 작업은 완료 표시 금지.
-->

[~] MAIL-001 | 기존 메일 오류가 남아 있는지 확인하고 있으면 고친다
[ ] MAIL-002 | 공고 안내 메일을 8개 칸 표로 바꾼다


---

# 1. REPOSITORY

REPO: pds2225/mail
BASE: main
REMOTE: https://github.com/pds2225/mail

## 작업지시 파일

실행 기준은 이 파일 하나뿐이다.

- `TASK.md`만 작업지시 파일로 사용한다.
- 별도의 CURRENT_TASK.md / NEW_TASK.md를 만들지 않는다.
- NEXT_TASK.md, 다른 레포 TASK, Google Tasks, 과거 채팅 내용을 임의 실행하지 않는다.
- 사용자의 새 요청은 이 TASK.md에 새로운 TASK 항목으로 등록한다.

---

# 2. GOOGLE TASKS 완전 분리

Google Tasks는 이 개발 TASK 시스템과 무관하다.

금지:

- Google Tasks 조회
- Google Tasks 항목 가져오기
- Google Tasks → TASK.md 자동등록
- TASK.md → Google Tasks 등록
- 상태/제목/완료 여부 동기화
- Google Tasks 내용을 개발 우선순위 판단에 사용

---

# 3. GIT 안전 동기화

원칙: 작업은 로컬에서 한다. 기준과 병합은 원격이다.
로컬이 원격보다 **앞서기만** 하면(갈라지지 않음) 막지 않는다. 커밋된 내용을 **push한 뒤 원격에서 머지**해서 로컬=원격을 맞춘다.

작업 시작 전 반드시:

1. `git fetch --all --prune`
2. `git remote get-url origin` — 이 파일 `# 1. REPOSITORY`의 REPO와 일치하는지 확인
3. `git branch --show-current`
4. `git status --short`
5. ahead / behind / diverged 확인:

`git rev-list --left-right --count HEAD...origin/main`

왼쪽 숫자 = 로컬이 앞선 커밋(ahead). 오른쪽 = 로컬이 뒤처진 커밋(behind).
둘 다 0보다 크면 diverged(갈라짐). 둘 다 0이면 동기화됨.

쉬운 말:

- 나만 앞이면 → 올려서 맞춘다. 막지 않는다.
- 나만 뒤면 → 받아서 맞춘다.
- 서로 갈라졌으면 → 강제로 덮지 말고 합친다. 못 합치면 멈춘다.
- 저장 안 한 수정이 있으면 → 지우지 않는다.
- 남이 같은 브랜치에 올렸으면 → 덮어쓰지 말고 먼저 받고 합친다.

## 판정 (fetch 후, AI가 그대로 실행)

`<BASE>`는 `# 1. REPOSITORY`의 BASE다. 이 레포는 `main`.

동기화됨(ahead=0, behind=0, clean)이면 그대로 작업을 시작한다.

### 1. behind only

조건: 현재 브랜치가 BASE, working tree clean, ahead=0, behind>0.

실행: `git merge --ff-only origin/main`

실패하면 `BLOCKED`. `reset --hard`로 맞추지 않는다.

### 2. ahead only

조건: ahead>0, behind=0 (diverged 아님). **ahead only는 BLOCKED가 아니다.**

실행:

1. 미커밋 변경이 있으면 **이번 작업 파일만** 커밋한다. `git add -A` 금지. 사용자 쓰레기 파일을 올리지 않는다.
2. `git push` (force 금지).
3. 현재가 작업 브랜치면 PR을 만든다. 충돌 없음 + GitHub Checks 초록일 때만 머지한다. 실패 체크를 무시하는 `gh pr merge --admin`은 금지한다.
4. 이미 BASE면 push로 원격을 로컬에 맞춘다. 보호 규칙으로 push가 거절되면 PR로 올린다.
5. 이후 `git fetch`로 로컬=원격을 확인한다.

### 3. diverged

조건: ahead>0 그리고 behind>0. 양쪽이 다 앞선 상태다.

force push 금지.

`git fetch` 후 안전하게 합칠 수 있으면 합친다 (`git merge origin/<현재브랜치>` 또는 해당 원격 브랜치). 충돌을 무조건 ours/theirs로 해결하지 않는다.

합친 뒤 `git push` (force 금지).

안전하게 합칠 수 없으면 `BLOCKED`.

### 4. dirty uncommitted

사용자 변경 삭제 금지. `git reset --hard` / `git clean -fd` / stash drop 금지.

선택:

- 이번 작업 파일이면 커밋한 뒤 **2. ahead only** 경로로 간다.
- 이번 작업이 아니거나 BASE를 더럽히면, 별도 worktree에서 `origin/main` 최신으로 작업한다.

안전하게 분리하지 못하면 `BLOCKED`.

### 5. 남이 같은 브랜치에 올린 뒤

로컬 push 전에 다시 `git fetch`.

behind가 생겼으면 force로 덮지 말고 먼저 받고 합친다. 그다음 push.

## 절대 금지

- `git reset --hard`
- force push (`--force`, `--force-with-lease` 포함)
- `git clean -fd`
- 사용자 변경 삭제
- 임의 stash/drop
- 충돌을 무조건 ours/theirs로 해결
- 로컬 파일을 원격 상태에 강제로 덮어쓰기
- `git add -A`

---

# 4. TASK 실행 계약 고정 — TASK PINNING

AI가 TASK를 시작할 때 반드시 아래 값을 기록한다.

TASK_ID: <현재 [~] TASK ID>
TASK_START_SHA: <작업 시작 시 origin/base commit SHA>
TASK_BLOB_SHA: <그 시점 TASK.md blob SHA>
WORK_BRANCH: <task/TASK-ID 등>

## 목적

작업 도중 `TASK.md`가 새 요청으로 변경되더라도,
이미 시작한 일반 TASK는 최초 실행 계약을 기준으로 완료한다.

필요하면 최초 TASK는:

`git show <TASK_START_SHA>:TASK.md`

로 다시 확인한다.

## 작업 중 TASK.md 변경 감지

새 TASK가 일반적인 후속 요청:

- 현재 ACTIVE TASK에 섞지 않는다.
- 현재 TASK를 최초 TASK_ID 기준으로 계속 수행한다.
- 새 TASK는 다음 실행에서 수행한다.

새 TASK가 아래에 해당:

- STOP
- CANCEL
- 기존 작업 즉시 중단 요청
- 보안 긴급지시
- 데이터 손실 방지 지시

→ 현재 TASK를 즉시 중단하고 상태를 기록한다.

---

# 5. TASK 선택 규칙

기본적으로 `[~]` 상태의 TASK 1개를 ACTIVE TASK로 실행한다.

`[~]`가 없으면 실행 가능한 `[ ]` TASK 중 우선순위가 가장 높은 작업을 선택한다.

## TASK 상태

- `[ ]` READY / 대기
- `[~]` ACTIVE / 진행 중
- `[x]` DONE / 실제 요청 해결 완료
- `[!]` BLOCKED / 현재 진행 불가능
- `[-]` CANCELLED / 사용자 취소

## 동시에 ACTIVE

같은 파일·API·DB·entrypoint를 수정하지 않는 독립 작업만 여러 `[~]` 허용.

---

# 6. TASK 우선순위

상충 시 아래 순서로 판단한다.

1. 데이터 손실 방지 / 보안 / Git 안전규칙
2. 가장 최신 사용자의 명시적 요청
3. 현재 ACTIVE TASK
4. ACTIVE TASK 수행에 필수인 선행조건
5. repo의 필수 보호규칙 / architecture contract
6. 기존 대기 TASK
7. backlog
8. 리팩터링 / 고도화 / 미관 개선

판단할 수 없는 충돌은 임의 선택하지 않는다.

→ `BLOCKED`

---

# 7. TASK 간 충돌·의존성

## 병렬 가능

다음을 모두 만족하면 병렬 가능:

- 수정 파일군이 다름
- 같은 public API를 변경하지 않음
- 같은 DB schema/migration을 변경하지 않음
- 같은 runtime entrypoint를 변경하지 않음
- TASK A 결과가 TASK B의 입력이 아님

## 순차 필수

하나라도 해당하면 순차:

- 같은 파일 수정
- 같은 API contract 변경
- 같은 DB migration 변경
- 같은 entrypoint 변경
- 한 TASK가 다른 TASK의 선행조건

순차 예:

TASK-A
→ 실사용 검증
→ 최신 코드 기준 TASK-B
→ 통합 E2E

---

# 8. TASK DETAILS

<!--
TASK LIST 한 줄 요약과 아래 상세 TASK는 TASK_ID로 연결한다.
새 사용자 요청을 TASK로 만들 때 반드시 MUST / KEEP / REMOVE / FORBIDDEN / VERIFY / DONE 관점으로 변환한다.
TRACK A(MAIL-001)가 선행이다. MAIL-002는 MAIL-001에 의존한다.
-->

## MAIL-001

### 8-1. 사용자 원문 요청

> PR #245/#246 이후 기존 P1/P2 결함이 최신 main에 남아 있는지 재현 확인하고, 남아 있으면 최소 hotfix한다.

원문의 의미를 축약 과정에서 변경하지 않는다.

확인 대상 기존 hotfix:

- fetch outcome scope/NameError
- source_stats 초기화 순서
- 전체 source 실패 source-health 누락
- featureless feedback의 허위 `MEASURED`
- `tests/test_version_delivery_integration.py` 실제 실패 여부
- dedup replacement KPI 누락
- yearless title duplicate recall

### 8-2. 비개발자용 1줄 요약

기존 메일 오류가 남아 있는지 확인하고 있으면 고친다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- 기존 P1/P2가 최신 main에서 재현되지 않거나, 재현되면 최소 수정으로 해결됨
- 문서의 DONE 표시가 아니라 실제 테스트 근거가 있음
- 실제 이메일/알림은 발송되지 않음 (preview/dry-run/mock만)

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

- 현재 구현: 기존 TASK에 PR #245/#246 이후 P1/P2 hotfix가 등록돼 있었음
- 현재 문제: 최신 main에서 이미 해결됐을 수 있음. 문서만 믿지 말 것
- 이미 구현된 부분: 확인 대상 hotfix 목록은 위에 있음
- 확인 필요한 부분: 각 항목의 실제 재현 여부

문서의 DONE 표시만 믿지 말고 실제 코드/runtime을 확인한다.

### 8-5. MUST — 반드시 구현

- [ ] 최신 main에서 기존 targeted tests와 `tests/test_version_delivery_integration.py` 실행
- [ ] 이미 해결됐으면 코드 수정 없이 `ALREADY_FIXED` 근거 기록
- [ ] 재현되는 항목만 최소 수정하고 regression test 추가
- [ ] 실제 alert/email 발송 금지

### 8-6. KEEP — 유지

- [ ] 기존 수집·중복제거·매칭·발송 정책
- [ ] 기존 dry-run/preview 경로
- [ ] 사용자가 변경 요청하지 않은 기존 동작

### 8-7. REMOVE — 제거

없음

### 8-8. FORBIDDEN — 금지

- 사용자 요청에 없는 기능 임의 추가 금지
- 불필요한 대규모 리팩터링 금지
- 관련 없는 DB/API/UI 변경 금지
- 테스트를 통과시키기 위한 기능 삭제 금지
- 기존 실패 테스트 skip 금지
- 근거 없는 값/데이터 생성 금지

TASK별 추가 금지사항:

- 실제 이메일/ntfy 발송
- 공고 수집 소스·크롤러·중복제거·매칭 기준 변경
- DB 구조 변경

### 8-9. 선행조건·의존성

DEPENDS_ON:

- NONE

선행 TASK가 실제로 DONE이 아니면 후속 작업을 완료 처리하지 않는다.

병렬: MAIL-002와 파일군이 겹치지 않으면 병렬 가능. 동일 파일이면 이 TASK를 먼저 끝낸다.

### 8-10. 구현범위

수정 가능 범위:

- 재현된 P1/P2 hotfix 최소 수정
- 관련 regression test
- 관련 문서의 수치/상태가 실제 테스트와 다를 때만 정정

기존 구조를 최대한 유지하고 최소 변경한다.

### 8-11. 입력검증

반드시 확인:

- 정상 입력
- 필수값 없음
- 잘못된 형식
- 허용범위 밖 값
- 중복 입력
- 비정상 문자열/빈 문자열

해당되지 않는 항목은 N/A 근거를 남긴다. 이 TASK는 기존 결함 재현·수정이 핵심이다.

### 8-12. 빈상태

검증:

- 데이터 0건
- 결과 없음
- 일부 필드 없음
- 최초 사용 상태

해당되면 기존 empty 정책을 깨지 않는다. 해당 없으면 N/A.

### 8-13. 로딩상태

정적 기능이면 N/A 가능. 비동기 파이프라인이면 기존 loading/processing과 중복 실행 방지를 유지한다.

### 8-14. 오류상태

필요한 경우:

- 외부 API 실패
- DB 실패
- timeout
- 네트워크 실패
- 일부 데이터 실패
- 권한 오류
- 잘못된 요청
- 재시도 가능 상태

오류가 없다는 사실 자체는 DONE 기준이 아니다.

---

## MAIL-002

### 8-1. 사용자 원문 요청

> 상태 → 적합 → 공고 → 지원 → 대상 → 기관 → 지역 → 마감

공고명 자체를 원문 링크로 만들고 `추천이유 / 바로가기 / 사이트명` 컬럼은 제거한다. 기존 수집·중복제거·매칭·발송 정책은 변경하지 않는다.

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

공고 안내 메일을 8개 칸 표로 바꾼다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- 공고 안내 이메일 표 컬럼과 순서가 정확히 `상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감`
- 공고명을 누르면 원문 `source_url`로 이동
- `추천이유 / 바로가기 / 사이트명` 컬럼이 보이지 않음
- 빈값·0건·일부 오류에서도 메일이 깨지지 않음

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

- 현재 구현: 기존 공고 안내 이메일 표가 다른 컬럼 구성을 쓸 수 있음
- 현재 문제: 8컬럼 순서·공고명 링크·제거 컬럼이 최신 사용자 요구와 다를 수 있음
- 이미 구현된 부분: D-Day, 신규 판정, 매칭 점수, source_url, 지역/기관 데이터
- 확인 필요한 부분: 실제 preview HTML의 컬럼·링크

문서의 DONE 표시만 믿지 말고 실제 코드/runtime을 확인한다.

### 8-5. MUST — 반드시 구현

- [ ] 최종 컬럼 순서: `상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감`
- [ ] 상태: 기존 D-Day 로직 재사용. 예: `🆕 D-2 🔴`, `D-6 🟠`, `D-15 🟢`, `마감`. `🆕`는 기존 신규 판정 데이터가 있을 때만
- [ ] 적합 표시값은 `지원가능` / `확인필요` / `대상아님`만. 기존 매칭 로직/점수 계산은 변경하지 않음. 정보 부족은 `확인필요`
- [ ] 공고명을 원문 `source_url` 하이퍼링크로 표시. 별도 `바로가기` 컬럼 금지. URL 없으면 일반 텍스트
- [ ] 지원: 기존 데이터/원문에서 확인된 핵심 지원내용만 짧게. 확인 불가 시 `확인필요`. 임의 금액 생성 금지
- [ ] 대상: 핵심 신청대상을 짧게. 확인 불가 시 `확인필요`
- [ ] 기관: 기존 주관/공고기관 데이터. 임의 약칭 금지
- [ ] 지역: 기존 지역 제한 데이터. 명시적 전국이면 `전국`, 판정 불가면 `확인필요`
- [ ] 마감: 현재 연도는 `M/D`, 다른 연도면 `YYYY/M/D`

### 8-6. KEEP — 유지

- [ ] 공고 수집 소스·크롤러
- [ ] 중복제거 정책
- [ ] 지원사업 포함/제외 정책
- [ ] 사용자 그룹/LLM 매칭 기준
- [ ] 메일 발송 스케줄/수신자
- [ ] 원본 데이터 필드(수집/로그/추적). 표시 컬럼만 제거
- [ ] 기존 D-Day·신규 판정 데이터

### 8-7. REMOVE — 제거

표시 컬럼만 제거한다. 원본 데이터 필드는 삭제하지 않는다.

- [ ] 추천이유
- [ ] 바로가기
- [ ] 사이트명

### 8-8. FORBIDDEN — 금지

- 사용자 요청에 없는 기능 임의 추가 금지
- 불필요한 대규모 리팩터링 금지
- 관련 없는 DB/API/UI 변경 금지
- 테스트를 통과시키기 위한 기능 삭제 금지
- 기존 실패 테스트 skip 금지
- 근거 없는 값/데이터 생성 금지

TASK별 추가 금지사항:

- 공고 수집 소스 변경, 크롤러 변경, 중복제거 정책 변경
- 지원사업 포함/제외 정책 변경, 사용자 그룹/LLM 매칭 기준 변경
- 메일 발송 스케줄/수신자 변경, DB 구조 변경, 원문 데이터 삭제
- 근거 없는 지원금·대상·지역·적합 판정 생성
- 실제 이메일/알림 발송

### 8-9. 선행조건·의존성

DEPENDS_ON:

- MAIL-001

MAIL-001이 실제로 DONE(또는 ALREADY_DONE)이 아니면 이 작업을 완료 처리하지 않는다. TRACK A 선행, B는 A에 의존.

### 8-10. 구현범위

수정 가능 범위:

- 공고 안내 이메일 표 렌더러/템플릿
- 컬럼 매핑·표시 로직
- HTML preview (Gmail-compatible)
- 관련 테스트

기존 구조를 최대한 유지하고 최소 변경한다.

### 8-11. 입력검증

반드시 확인:

- 공고명은 필수. 없으면 기존 invalid notice 정책으로 처리
- URL은 비어 있으면 링크를 만들지 않는다
- 마감일은 기존 parser 결과를 사용하고 invalid date가 한 행 때문에 전체 메일을 깨지 않게 한다
- 적합/지원/대상/기관/지역 값은 허용된 기존 데이터에서만 매핑
- 정상 입력 / 필수값 없음 / 잘못된 형식 / 허용범위 밖 값 / 중복 입력 / 비정상 문자열

해당되지 않는 항목은 N/A 근거를 남긴다.

### 8-12. 빈상태

검증:

- 공고 0건이면 빈 table을 렌더링하지 않고 기존 empty 문구 또는 `현재 조건에 맞는 신규 공고가 없습니다.` 표시
- 지원/대상/지역 값 없음 → `확인필요`
- URL 없음 → 공고명 plain text
- 데이터 0건 / 결과 없음 / 일부 필드 없음 / 최초 사용 상태

사용자가 빈 화면을 오류로 오해하지 않게 한다.

### 8-13. 로딩상태

이메일 자체는 정적 렌더링이므로 별도 UI loading은 만들지 않는다. 단, preview 생성/렌더링 파이프라인이 비동기라면 기존 loading/processing 상태를 유지하고 중복 실행을 방지한다. 정적 기능이면 N/A 가능.

### 8-14. 오류상태

필요한 경우:

- 한 공고 일부 필드 오류가 전체 이메일 생성을 실패시키지 않게 field-level fallback
- 전체 renderer 실패는 명시적 FAIL
- 데이터 없음과 parser 오류를 같은 값으로 숨기지 않는다
- 외부 API 실패 / DB 실패 / timeout / 네트워크 실패 / 일부 데이터 실패 / 잘못된 요청 / 재시도 가능 상태

오류가 없다는 사실 자체는 DONE 기준이 아니다.

최소 검증 예: 정상 1건, 여러 공고, 🆕, D-Day, 지원가능/확인필요/대상아님, URL 있음/없음, 지원·대상·지역 없음, 0건, 한 행 일부 오류, Gmail-compatible HTML preview, 기존 메일 발송 regression(실제 발송 없음).

---

# 9. 실제사용 시나리오

TASK 완료 전에 반드시 실제 사용자 관점으로 검증한다.

해당 TASK DETAILS의 최종 결과·구현범위와 함께 적용한다.

## USER FLOW

사용자 시작점:
화면 / CLI / 이메일 / API / 파일 등 실제 진입점

사용자 행동:
1. 사용자가 실제로 하는 행동
2. 다음 행동
3. 다음 행동

시스템 처리:
실제 production 경로 (mock-only로 대체하지 않음)

사용자 최종 결과:
사용자가 실제 보게 되는 것

## 핵심 질문

`이 결과가 사용자의 최초 요청을 실제로 해결했는가?`

YES가 아니면 DONE 금지.

---

# 10. VERIFY — 해결 여부 검증

사용자 요청과 결과를 1:1로 대조한다.

| 사용자 요구 | 실제 결과 | 판정 |
|---|---|---|
| DETAILS의 MUST 항목 | 실제 결과 | PASS/FAIL |

하나라도 필수 요구가 FAIL이면:

`REQUEST_SOLVED = NO`

---

# 11. 실사용 E2E

최소 1개의 실제 사용자 흐름을 처음부터 끝까지 실행한다.

원칙:

- 단위 테스트만으로 대체 금지
- mock-only 검증만으로 DONE 금지
- 가능한 실제 runtime/production entrypoint 사용
- 실제 외부 유료 호출이나 위험 작업은 안전한 staging/dry-run/preview 사용

E2E 결과:

USER_E2E: PASS | FAIL | BLOCKED

근거:
명령 / 화면 / 산출물 / preview / API 결과

---

# 12. 테스트

실사용 검증을 보조하는 테스트를 수행한다.

최소:

- 정상경로
- 주요 경계값
- 입력검증
- 빈상태
- 주요 오류
- 변경한 기능 단위 테스트
- 관련 integration test

테스트 PASS만으로 DONE 처리하지 않는다.

---

# 13. 회귀검증

이번 변경 때문에 기존 핵심 기능이 깨지지 않았는지 확인한다.

- [ ] 기존 핵심 사용자 흐름
- [ ] 관련 API
- [ ] 인증/권한
- [ ] DB 계약
- [ ] 기존 사용자 데이터
- [ ] 기존 자동화
- [ ] 기존 주요 테스트

관련 없는 전체 제품 고도화는 하지 않는다.

---

# 14. 문서동기화

실제 구현과 문서가 달라진 경우에만 최소 수정:

- README
- TASK 관련 문서
- ARCHITECTURE
- 운영문서
- 테스트/사용법 문서

거짓 DONE 기록을 남기지 않는다.

---

# 15. DONE 기준 — 실제 사용자 요청 해결 기준

## 절대 원칙

다음은 단독으로 DONE 근거가 아니다.

- 코드 작성 완료
- 테스트 PASS
- build PASS
- 오류 없음
- commit 존재
- PR 생성
- 화면이 열림

## DONE

다음을 모두 만족해야 한다.

- [ ] 사용자의 필수 요청사항 전부 해결
- [ ] `REQUEST_SOLVED = YES`
- [ ] 실제 사용자 E2E PASS
- [ ] 사용자가 원하는 최종 결과 확인
- [ ] 필요한 입력/빈/로딩/오류상태 사용 가능
- [ ] 기존 핵심 기능 회귀 없음
- [ ] 금지사항 위반 없음
- [ ] 필요한 문서 동기화
- [ ] commit 완료
- [ ] push 완료

## ALREADY_DONE

새 코드를 만들지 않아도 이미 요청사항이 해결되어 있고
실제사용 E2E로 이를 확인한 경우.

## PARTIAL

일부 구현했지만:

`REQUEST_SOLVED = NO`

인 경우.

작업량이 많아도 DONE 금지.

## BLOCKED

외부 의존성/권한/정책/Git 충돌/검증환경 때문에
안전하게 사용자의 요청을 해결할 수 없는 경우.

## FAIL

구현을 시도했으나 사용자 요청 해결에 실패한 경우.

---

# 16. 작업 종료 전 Git 최신 상태 재확인

작업 완료 직전 다시:

1. `git fetch --all --prune`
2. 현재 `origin/main` 확인
3. `TASK_START_SHA`와 최신 base 비교

## base가 작업 중 변경된 경우

코드를 최신 base와 안전하게 통합한다.

필요하면:

- conflict 해결
- 관련 test 재실행
- USER E2E 재실행
- regression 재실행

단:

최신 TASK.md의 새로운 일반 작업을 현재 ACTIVE TASK에 섞지 않는다.

코드는 최신화할 수 있지만,
ACTIVE TASK의 목적과 DONE 조건은 최초 TASK snapshot을 유지한다.

---

# 17. 작업 완료 후 Git 동기화

TASK 구현 완료:

1. 변경 파일 확인
2. 필요한 파일만 stage (`git add -A` 금지)
3. commit
4. remote work branch에 push

확인:

WORK_BRANCH_PUSHED: YES | NO

## PR/merge가 TASK 범위인 경우

- 필요한 검사 통과
- PR
- merge

머지는 이 TASK가 허용한 경우만 한다. 명시가 없으면 기본 브랜치 병합 금지.

조건:

- 충돌 없음
- GitHub Checks 초록

실패면 merge 명령 실행 금지.

문제: 머지 규칙이 TASK 글뿐이라 `gh pr merge`로 문서 PR을 Checks 빨강인데도 머지할 수 있었다. 예외 머지는 폐지한다.

머지는 GitHub Checks가 초록일 때만 한다. 문서만(`TASK.md`, `*.md`, `docs/**`) 바뀌면 무거운 테스트 대신 `docs-gate`가 초록이면 된다. `gh pr merge --admin` 및 실패 체크를 무시하는 머지는 금지한다.


merge 후:

1. `git fetch`
2. local base clean 확인
3. `git merge --ff-only origin/main`
4. local base와 remote base 일치 확인

절대 reset --hard로 맞추지 않는다.

---

# 18. TASK LIST 상태 갱신 규칙

TASK LIST의 상태는 실제 결과와 반드시 일치한다.

### `[x]`

다음일 때만:

`REQUEST_SOLVED = YES`

### `[~]`

현재 실행 중.

### `[!]`

BLOCKED.

### `[-]`

사용자가 취소.

### `[ ]`

아직 시작하지 않음.

LIST와 DETAILS가 불일치하면 TASK 파일 오류로 간주한다.

---

# 19. TASK 수정/삭제 규칙

## 사용자가 TASK 설명을 수정

TASK LIST 1줄 요약과 해당 DETAILS를 함께 수정한다.

## 사용자가 "삭제"

- TASK LIST 행 삭제
- TASK DETAILS 전체 삭제

## 사용자가 "취소"

- LIST를 `[-]`로 변경
- 상세에는 취소 이유 최소 기록 가능

## 완료 TASK

사용자가 목록에서 완료 TASK도 계속 보고 싶다면 `[x]` 유지.

별도 요청으로 정리할 때만 제거한다.

---

# 20. 새 사용자 요청 등록 규칙

새 요청:

1. 기존 TASK와 동일한 요청인지 확인
2. 이미 해결됐으면 중복 생성 금지
3. 새 TASK_ID 발급
4. 사용자 원문 보존
5. 비개발자용 1줄 요약 생성
6. TASK LIST에 `[ ]` 추가
7. TASK DETAILS 생성
8. MUST/KEEP/REMOVE/FORBIDDEN/VERIFY/DONE 변환
9. 기존 TASK와 dependency/충돌 검사
10. 실행 순서 결정

기존 ACTIVE TASK에 새 요청을 임의 합치지 않는다.

---

# 21. TASK 완료 후 다음 TASK

현재 TASK가 DONE된 후:

- TASK LIST에서 다음 READY 작업 확인
- dependency가 해결된 작업 우선
- 독립 작업은 병렬 가능
- BLOCKED 작업은 건너뛰되 이유 유지

새 TASK가 없으면:

`NO_ACTIVE_TASK`

를 보고하고 개발을 중단한다.

---

# 22. 최종보고

반드시 아래 형식으로 보고한다.

REPO:
TASK_ID:

USER_REQUEST:
REQUEST_SOLVED: YES | NO

TASK_START_SHA:
TASK_BLOB_SHA:
WORK_BRANCH:

USER_E2E: PASS | FAIL | BLOCKED
USER_RESULT:
VERIFY_RESULT:

TEST:
REGRESSION:

COMMIT:
WORK_BRANCH_PUSHED: YES | NO

PR:
MAIN_MERGED: YES | NO | N/A

REMOTE_BASE_SYNC:
LOCAL_BASE_SYNC:

TASK_STATUS:
DONE | ALREADY_DONE | PARTIAL | BLOCKED | FAIL

NEXT_READY_TASK:
PENDING_TASKS:

---

# 23. 최종 STOP 조건

아래 중 하나면 임의 개발을 계속하지 않는다.

- ACTIVE TASK 없음
- 사용자 요청과 TASK 내용이 명백하게 불일치
- repo/origin 불일치
- 안전한 Git 작업공간 확보 불가
- 사용자 데이터를 잃을 위험
- 최신 CANCEL/STOP 지시 발견
- 해결방법 선택이 제품정책을 바꾸며 사용자의 결정이 반드시 필요함

상태를 `BLOCKED` 또는 `NO_ACTIVE_TASK`로 보고한다.
