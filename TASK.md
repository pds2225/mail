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

[x] MAIL-001 | 기존 메일 오류가 남아 있는지 확인하고 있으면 고친다
[x] MAIL-002 | 공고 안내 메일을 8개 칸 표로 바꾼다
[x] MAIL-003 | 예비창업 AI 그룹 적합도가 떨어진 원인을 분석한다
[x] MAIL-004 | 모든 작업은 자동 머지가 기본이다
[x] MAIL-005 | 예비창업 본공고가 2차 점수에서 떨어지지 않게 한다
[x] MAIL-006 | 기창업 솔루션 공고는 예비창업 메일에서 뺀다
[x] MAIL-007 | 밤샘 자동개발이 TASK.md를 읽고 남은 결함을 고친다
[x] MAIL-008 | 15건이 넘는 공고가 메일에서 빠지지 않게 한다
[x] MAIL-009 | 일부 그룹만 보낸 채 죽으면 다른 그룹이 못 받는 문제를 고친다
[x] MAIL-010 | 워크플로만 바꾼 PR은 테스트 없이 자동머지되지 않게 한다
[ ] MAIL-011 | 비개발자용 공고첨부 원클릭 설치를 마친다
[~] MAIL-012 | AI 사업화지원금 공고를 빠짐없이 수집한다


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

PINNING (E2E 2026-08-13):
- TASK_ID: MAIL-001
- TASK_START_SHA: 8fc2e7e8e21ddb72b2c76296aed02abd1cc76949
- TASK_BLOB_SHA: ab6b4642ec8b97dd22eb7026b6ed3f4d5960fe01
- WORK_BRANCH: task/MAIL-001-hotfix
- origin: https://github.com/pds2225/mail.git (일치)
- 로컬 D:\mail dirty+behind → worktree D:\tmp\wt-mail-MAIL-001 에서 origin/main 최신으로 작업
- AGENTS.md 충돌: "monitor.py 수정 금지" vs 이 hotfix가 monitor.py를 요구. 최신 사용자 요청(MAIL-001 E2E) 우선. AGENTS.md는 수정하지 않고 TASK가 명시한 hotfix만 수행. 선택지: (1) TASK 우선 hotfix(채택) (2) AGENTS.md 예외 문구 추가(이번 범위 밖) (3) BLOCKED

Already Done 실코드 확인 (문서 DONE 불신):
- fetch_all outcomes / source_stats 초기화: 이미 있음 (#248). 런타임 재확인 대상.
- 남은 결함: yearless possible-duplicate 버킷 누락, dedup replacement KPI 미기록, featureless feedback 허위 MEASURED, source-health error 필드 미저장.

USER_E2E (preview, 실발송 없음): `execute_monitor(allow_send=False, persist_seen=False)` mock 수집 2건 → dedup 1건, mode=preview, mail_sent=false, NameError/UnboundLocalError 없음. 산출물 `D:\tmp\MAIL-001-e2e-smoke.json`. local pytest 133 passed. GitHub `test`+`docs-gate` 초록 후 PR #259 squash-merge (`7ba5383ba`). MAIL-002는 선행 완료 후 다음 실행.
MAIN_MERGED: YES (2026-08-13T08:00:25Z)

- 현재 구현: 기존 TASK에 PR #245/#246 이후 P1/P2 hotfix가 등록돼 있었음
- 현재 문제: 최신 main에서 이미 해결됐을 수 있음. 문서만 믿지 말 것
- 이미 구현된 부분: 확인 대상 hotfix 목록은 위에 있음
- 확인 필요한 부분: 각 항목의 실제 재현 여부

문서의 DONE 표시만 믿지 말고 실제 코드/runtime을 확인한다.

### 8-5. MUST — 반드시 구현

- [x] 최신 main에서 기존 targeted tests와 `tests/test_version_delivery_integration.py` 실행
- [x] 이미 해결됐으면 코드 수정 없이 `ALREADY_FIXED` 근거 기록 (`fetch_all` outcomes / `source_stats` 초기화는 #248)
- [x] 재현되는 항목만 최소 수정하고 regression test 추가
- [x] 실제 alert/email 발송 금지

### 8-6. KEEP — 유지

- [x] 기존 수집·중복제거·매칭·발송 정책
- [x] 기존 dry-run/preview 경로
- [x] 사용자가 변경 요청하지 않은 기존 동작

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

- 현재 구현: `fallback_body` + `mail_core/delivery/digest_table.py` 가 8컬럼 Gmail 표를 렌더한다 (PR #263, main 미머지)
- 현재 문제: 해결됨 — 컬럼 순서·공고명 `source_url` 링크·제거 컬럼 확인
- 이미 구현된 부분: D-Day, 신규 판정(`_change_type==NEW`만 🆕), 적합 3값, 지원 종류 매핑
- 확인 결과: `execute_monitor` preview는 미발송, mocked send 경로 본문/HTML에 8컬럼·제목 링크. pytest 1323 passed / 1 skipped. 실발송 없음

문서의 DONE 표시만 믿지 말고 실제 코드/runtime을 확인한다.

### 8-5. MUST — 반드시 구현

- [x] 최종 컬럼 순서: `상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감`
- [x] 상태: 기존 D-Day 로직 재사용. 예: `🆕 D-2 🔴`, `D-6 🟠`, `D-15 🟢`, `마감`. `🆕`는 기존 신규 판정 데이터가 있을 때만
- [x] 적합 표시값은 `지원가능` / `확인필요` / `대상아님`만. 기존 매칭 로직/점수 계산은 변경하지 않음. 정보 부족은 `확인필요`
- [x] 공고명을 원문 `source_url` 하이퍼링크로 표시. 별도 `바로가기` 컬럼 금지. URL 없으면 일반 텍스트
- [x] 지원: 기존 데이터/원문에서 확인된 핵심 지원내용만 짧게. 확인 불가 시 `확인필요`. 임의 금액 생성 금지
- [x] 대상: 핵심 신청대상을 짧게. 확인 불가 시 `확인필요`
- [x] 기관: 기존 주관/공고기관 데이터. 임의 약칭 금지
- [x] 지역: 기존 지역 제한 데이터. 명시적 전국이면 `전국`, 판정 불가면 `확인필요`
- [x] 마감: 현재 연도는 `M/D`, 다른 연도면 `YYYY/M/D`

### 8-6. KEEP — 유지

- [x] 공고 수집 소스·크롤러
- [x] 중복제거 정책
- [x] 지원사업 포함/제외 정책
- [x] 사용자 그룹/LLM 매칭 기준
- [x] 메일 발송 스케줄/수신자
- [x] 원본 데이터 필드(수집/로그/추적). 표시 컬럼만 제거
- [x] 기존 D-Day·신규 판정 데이터

### 8-7. REMOVE — 제거

표시 컬럼만 제거한다. 원본 데이터 필드는 삭제하지 않는다.

- [x] 추천이유
- [x] 바로가기
- [x] 사이트명

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

## MAIL-003

### 8-1. 사용자 원문 요청

> ai예비창업 그룹 정확도가 떨어지는데 원인을 모르겠어 분석해줘
>
> 정확도라기보다 적합도

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

예비창업 AI 그룹 적합도가 떨어진 원인을 분석한다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- 예비창업 AI 메일에 안 맞는 공고가 들어오는 **원인**이 코드·설정·런타임 근거로 설명됨
- 분류 지표(정확도)가 아니라 **신청 적합도**(예비창업자가 신청 가능한가) 기준으로 설명됨
- 이번 작업은 분석. 매칭 정책 수정은 별도 요청(MAIL-005)에서 진행

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-003
- TASK_START_SHA: baea70403bef9ac101fb9931a8cc55b74ae3b49b
- TASK_BLOB_SHA: 020942051696f1e9653b3aaa1aaf3916a920f8fc
- WORK_BRANCH: cursor/prestartup-or-keywords-e101

선행 Draft PR #264는 `TASK.md` 충돌(DIRTY)로 main에 못 들어갔다. 최신 main에서 같은 4건을 다시 돌렸다.

런타임 재현 (실발송 없음, `evaluate_notice` + `score_and_filter`, main `baea7040` 설정 기준):

| 샘플 | 1차 포함 | 점수 | 2차 |
|---|---|---|---|
| AI 예비창업패키지(사업자 없음) | 포함 | 0 | DROP |
| AI 솔루션 도입 참여기업(기창업) | 포함 | 5 | PASS |
| 서울 AI 허브 입주 | 포함 | 5 | PASS |
| 생성형AI 솔루션 실증기업 | 포함 | 5 | PASS |

원인: 1차는 AND(`AI`+`창업`/`사업화` 등)로 넓게 통과, 2차는 OR 문구(`AI 솔루션` 등)만 점수에 넣어 예비창업 본공고는 떨어지고 기창업 솔루션 공고는 남음. `business_years` 없음. LLM 밴드 40~70인데 실제 점수는 0 또는 5라 2차 LLM이 안 돈다.

수정은 MAIL-005. 기창업 솔루션 제외는 이 분석 범위 밖(별도 요청).

REQUEST_SOLVED: YES (원인 분석 + 런타임 재현. 코드 수정은 MAIL-005)

### 8-5. MUST — 반드시 구현

- [x] `grp_prestartup_ai` 설정(키워드·점수·업력·지원유형)을 실제 JSON에서 확인
- [x] 1차 `evaluate_notice`와 2차 `score_and_filter`가 같은 기준으로 도는지 런타임 확인
- [x] 예비창업 적합 vs 기창업/솔루션도입 샘플로 적합도 왜곡 재현
- [x] 실제 이메일/알림 발송 금지

### 8-6. KEEP — 유지

- [x] 수집·중복제거·매칭 코드 미수정 (분석만)
- [x] 수신자·스케줄 미변경

### 8-7. REMOVE — 제거

없음 (분석 TASK)

### 8-8. FORBIDDEN — 금지

- 사용자 요청에 없는 기능 임의 추가 금지
- 이번 분석에서 매칭 정책/키워드를 임의로 바꾸지 않음
- 실제 이메일/알림 발송

### 8-9. 선행조건·의존성

DEPENDS_ON: 없음. 수정 구현은 MAIL-005.

### 8-10. 구현범위

- 원인 분석 및 TASK.md 기록
- 관련 설정/코드 읽기, 로컬 런타임 재현
- 매칭 수정은 MAIL-005

### 8-11. 입력검증

N/A — 분석 TASK.

### 8-12. 빈상태

N/A

### 8-13. 로딩상태

N/A

### 8-14. 오류상태

분석 근거가 코드와 불일치하면 FAIL. 추측만으로 DONE 금지.

---

## MAIL-004

### 8-1. 사용자 원문 요청

> 모든작업은 자동머지가 기본이다

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

모든 작업은 자동 머지가 기본이다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- Checks 초록인 작업 PR은 물어보지 않고 squash-merge 된다
- `monitor.py` 변경만으로 자동 머지가 막히지 않는다
- Draft / `needs-human` / `blocked` / 충돌 / `.env*` 만 예외다
- 실패 체크를 무시하는 `--admin` 머지는 없다

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-004
- TASK_START_SHA: 55f3251f15a4780f490b291afffef37a93211de8
- TASK_BLOB_SHA: 4d98899ae105381195dbff04ba383b9469a947b7
- WORK_BRANCH: cursor/auto-merge-default-e94f

- 현재 구현: Auto Merge는 Checks 초록이면 기본 squash-merge. `allowed_profiles` 빈 목록. `monitor.py` 포함
- 현재 문제: 해결됨 (PR #265 `8dbc98c1`, MAIL-002는 #263 `f2f34c7f`)
- 이미 구현된 부분: squash, Checks 초록, Draft/라벨/충돌/.env* 스킵, github.token, PR 번호 해석
- 확인 필요한 부분: 없음 — 단위 테스트 21건 + test_monitor 회귀 통과 후 병합

문서의 DONE 표시만 믿지 말고 실제 코드/runtime을 확인한다.

USER_E2E: `match_profile(["monitor.py"])` eligible, `.env` blocked, Draft/needs-human skip. Open PR 평가: #263/#265 merge, #264/#262 draft skip, #243 test fail skip, #260 `--auto` queued (base 최신화 필요).
MAIN_MERGED: YES (2026-08-14T02:00:16Z, #265)

### 8-5. MUST — 반드시 구현

- [x] 자동 머지를 기본으로 바꾼다 (`allowed_profiles` 빈 목록 = 제한 없음)
- [x] `monitor.py` / `streamlit_app.py` 변경 PR도 Checks 초록이면 병합
- [x] Draft, `needs-human`, `blocked`, 충돌, `.env*` 는 계속 스킵
- [x] TASK.md §17을 “자동 머지 기본”으로 고친다
- [x] `--admin` 머지 금지 유지

### 8-6. KEEP — 유지

- [x] squash merge
- [x] GitHub Checks 초록 필수
- [x] 실제 이메일/알림 발송 금지
- [x] Auto Merge 워크플로의 `github.token` (만료 PAT 우회 금지)

### 8-7. REMOVE — 제거

- [x] `monitor.py` 자동병합 금지
- [x] 프로필 allowlist로 인한 기본 스킵
- [x] “명시 없으면 기본 브랜치 병합 금지” 규칙

### 8-8. FORBIDDEN — 금지

- 사용자 요청에 없는 기능 임의 추가 금지
- 불필요한 대규모 리팩토링 금지
- 관련 없는 DB/API/UI 변경 금지
- 테스트를 통과시키기 위한 기능 삭제 금지
- 기존 실패 테스트 skip 금지
- 근거 없는 값/데이터 생성 금지

TASK별 추가 금지사항:

- `gh pr merge --admin`
- 실제 이메일/ntfy 발송
- `.env` 내용 커밋·로그

### 8-9. 선행조건·의존성

DEPENDS_ON:

- NONE

최신 사용자 요청이 기존 TASK.md 머지 금지보다 우선한다.

### 8-10. 구현범위

수정 가능 범위:

- `scripts/auto_merge_pr.py`
- `auto_dev/loop_config.json`, `auto_dev/task_profiles.json`
- `.github/workflows/auto-merge.yml` 주석
- 관련 테스트·TASK.md·게이트 문서

기존 구조를 최대한 유지하고 최소 변경한다.

### 8-11. 입력검증

- 정상 PR + Checks 초록 → eligible
- Draft / 차단 라벨 / 충돌 / `.env` → not eligible
- `monitor.py` 포함 diff → eligible
- `auto_merge.enabled=false` → not eligible
- 빈 allowlist → 프로필 제한 없음

### 8-12. 빈상태

- 열린 PR 0건: 스크립트 성공 종료, merge 없음
- 변경 파일 없음: not eligible

### 8-13. 로딩상태

Checks pending이면 기존처럼 병합하지 않는다 (워크플로는 테스트 성공 후에만 돈다).

### 8-14. 오류상태

- `gh` 실패는 merge 실패로 남기고 `--admin`으로 우회하지 않는다
- PR 번호 없으면 skip (잡 실패 아님)

---

## MAIL-005

### 8-1. 사용자 원문 요청

> ㅇㅇ
>
> (직전 제안: #264를 최신 main에 다시 올리고, OR 키워드만 최소 PR로 분리해 올린다. 기창업 솔루션 제외는 결정 필요라 이번 범위 밖.)

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

예비창업 본공고가 2차 점수에서 떨어지지 않게 한다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- `AI 예비창업패키지` 같은 진짜 예비창업 공고가 2차 점수 컷에서 메일 대상에 남음
- MAIL-003 원인 분석이 최신 `TASK.md`에 기록됨
- 기창업 `AI 솔루션 도입` 공고를 이번에 제외하지 않음
- `monitor.py`는 수정하지 않음

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-005
- TASK_START_SHA: baea70403bef9ac101fb9931a8cc55b74ae3b49b
- TASK_BLOB_SHA: 020942051696f1e9653b3aaa1aaf3916a920f8fc
- WORK_BRANCH: cursor/prestartup-or-keywords-e101

- 현재 구현: `config/groups.json` `grp_prestartup_ai.or_keywords`에 `예비창업`/`예비창업자`/`창업예정자` 추가. 1차·2차가 같은 OR를 보므로 예비창업 본공고 점수가 0에서 10으로 올라 `score_threshold` 1을 통과
- 현재 문제: 해결됨 (패키지 공고 stage2 `passed`). 기창업 솔루션은 의도적으로 그대로 PASS
- 확인: `refine_included_by_score_llm` + `score_and_filter` 회귀 테스트. 실발송 없음

REQUEST_SOLVED: YES

### 8-5. MUST — 반드시 구현

- [x] MAIL-003 분석을 최신 main `TASK.md`에 기록 (#264 충돌 해소)
- [x] `grp_prestartup_ai` OR에 예비창업 적합 단어 3개 추가
- [x] `AI 예비창업패키지`가 2차 점수 컷을 통과하는 회귀 테스트
- [x] `monitor.py` 미수정
- [x] 실제 이메일/알림 발송 금지

### 8-6. KEEP — 유지

- [x] 기존 AI OR 키워드(`AI 솔루션`, `서울 AI 허브` 등)
- [x] AND 키워드 그룹
- [x] 기창업 솔루션 제외 정책(별도 요청 전 변경 금지)
- [x] 수신자·스케줄

### 8-7. REMOVE — 제거

없음

### 8-8. FORBIDDEN — 금지

- `monitor.py` / `streamlit_app.py` 수정
- 기창업 솔루션 공고를 이번 PR에서 제외
- 실제 이메일/알림 발송
- Secret/API Key 로그

### 8-9. 선행조건·의존성

DEPENDS_ON: MAIL-003 원인 분석 (같은 브랜치에 기록).

### 8-10. 구현범위

- `config/groups.json`
- `tests/test_prestartup_ai_digest_regression.py`
- `tests/test_scoring.py`
- `TASK.md`

### 8-11. 입력검증

- 예비창업패키지 제목+본문 → 2차 PASS
- 기존 OR만 맞는 AI 솔루션 공고 → 기존처럼 PASS
- groups.json JSON 유효

### 8-12. 빈상태

N/A — 키워드 추가만.

### 8-13. 로딩상태

N/A

### 8-14. 오류상태

점수 컷 회귀가 깨지면 FAIL. 테스트를 skip으로 숨기지 않음.

---

## MAIL-006

### 8-1. 사용자 원문 요청

> ㅇㅇ 지금 task.md 읽고 하고있나?
>
> (직전 제안 ③: 기창업 솔루션을 2차에서 걸러 적합도를 맞춘다. MAIL-005는 예비창업 본공고 회복만 했고 기창업 `AI 솔루션 도입`은 그대로 PASS.)

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

기창업 솔루션 공고는 예비창업 메일에서 뺀다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- 예비창업자가 신청할 수 없는 `AI 솔루션 도입 참여기업` 같은 기창업 공고가 예비창업 AI 메일 대상에서 빠짐
- `AI 예비창업패키지` 같은 진짜 예비창업 공고는 계속 남음
- 예비창업 신호와 솔루션 도입이 같이 있으면 포함 (동시 모집)
- `monitor.py`는 수정하지 않음

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-006
- TASK_START_SHA: ccc6a1b4b03d3d52bf1720bd248ac449716acf80
- TASK_BLOB_SHA: 733d796c7b3026b5de068033e86a21a338ff1136
- WORK_BRANCH: cursor/prestartup-fit-exclude-e101
- origin: https://github.com/pds2225/mail.git (일치)
- 작업 시작 시 ahead=0 behind=0 (origin/main `ccc6a1b4`, MAIL-005 squash-merge 반영)

- 현재 구현: `scoring.compute_score`가 `precision_exclude_keywords`를 `precision_keep_keywords` 없을 때만 감점. `grp_prestartup_ai`에 솔루션 도입/기창업/참여기업 vs 예비창업 유지 키워드 설정
- 현재 문제: 해결됨 — 기창업 솔루션 도입은 2차 `rejected_by_score`, 예비창업패키지는 PASS
- 확인: pytest 215 passed. 실발송 없음. `monitor.py` 미수정

REQUEST_SOLVED: YES

### 8-5. MUST — 반드시 구현

- [x] 기창업 솔루션 도입 공고는 `grp_prestartup_ai` 2차에서 DROP
- [x] 예비창업패키지 공고는 2차 PASS 유지
- [x] 예비창업 신호가 있으면 솔루션 도입이 있어도 포함
- [x] 회귀 테스트
- [x] `monitor.py` 미수정
- [x] 실제 이메일/알림 발송 금지

### 8-6. KEEP — 유지

- MAIL-005 OR 키워드 (예비창업/예비창업자/창업예정자, AI 솔루션, 서울 AI 허브)
- AND 키워드 그룹
- 1차 `evaluate_notice` 광역 통과 (2차에서 적합도 컷)
- 수신자·스케줄

### 8-7. REMOVE — 제거

예비창업 신호가 없는 기창업 솔루션 도입 공고의 2차 통과

### 8-8. FORBIDDEN — 금지

- `monitor.py` / `streamlit_app.py` 수정
- 실제 이메일/알림 발송
- Secret/API Key 로그
- 예비창업 본공고 recall 후퇴
- 기존 실패 테스트 skip

### 8-9. 선행조건·의존성

DEPENDS_ON: MAIL-003 원인, MAIL-005 OR 키워드 (main에 머지됨 #271).

### 8-10. 구현범위

- `mail_core/matching/scoring.py`
- `config/groups.json`
- `tests/test_scoring.py`
- `tests/test_prestartup_ai_digest_regression.py`
- `TASK.md`

### 8-11. 입력검증

- 기창업 `AI 솔루션 도입 참여기업` → 2차 DROP
- 예비창업패키지 → 2차 PASS
- 예비창업 + 솔루션 도입 동시 → 2차 PASS
- precision 설정 없는 그룹 → 기존 점수 그대로

### 8-12. 빈상태

precision 키 없음 = 감점 없음 (하위호환).

### 8-13. 로딩상태

N/A

### 8-14. 오류상태

점수 컷 회귀가 깨지면 FAIL. skip 금지.

---

## MAIL-007

### 8-1. 사용자 원문 요청

> 밤샘자동개발 task./md

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

밤샘 자동개발이 TASK.md를 읽고 남은 결함을 고친다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- 밤샘 준비 판정(`auto_dev_overnight_ready.py`)이 루트 `TASK.md`의 `[ ]`/`[~]` 를 대기 작업으로 본다
- `docs/project/TASKS.md` PENDING만 비어 있어도, `TASK.md`에 할 일이 있으면 로컬 에이전트 준비는 참
- MAIL-006 이후 `예비 창업`(띄어쓰기) 본공고가 2차 점수에서 떨어지지 않는다
- 기창업 `AI 솔루션 도입`만 있는 공고는 예비창업 메일에서 계속 빠진다
- GHA cron 은 켜지지 않는다
- `monitor.py`는 수정하지 않는다
- 실제 이메일은 발송되지 않는다

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-007
- TASK_START_SHA: 08a18e7d33d993cc90ed5cdea57ba8b1f6af2a23
- TASK_BLOB_SHA: b4d2efc683fc52f4958339fecae3a43733267f07
- WORK_BRANCH: cursor/overnight-task-md-7dc1
- origin: https://github.com/pds2225/mail.git (일치)
- 작업 시작 시 ahead=0 behind=0 (origin/main `08a18e7d`)

- 현재 구현: 밤샘 판정이 `TASK.md` `[ ]`/`[~]` 와 `docs/project/TASKS.md` PENDING을 합친다. `_kw_hit` 비ASCII는 공백 제거본도 본다.
- 현재 문제: 해결됨. GHA cron은 의도적으로 꺼 둠. UNIQUE_CANDIDATE(첨부다운로더·prestartup P0 문서)와 V9 `respx` 미설치는 기존 이슈라 이번 범위 밖.
- 확인: pytest 180 passed. 실발송 없음. `monitor.py` 미수정. overnight `[~]` 상태에서 pending=1, `[x]` 후 NO_ACTIVE_TASK.

REQUEST_SOLVED: YES
USER_E2E: PASS (`score_and_filter` preview: `예비 창업`+솔루션 도입 → passed score 30 keep=2; 기창업 솔루션 → rejected_by_score; mail_sent=false)
MAIN_MERGED: YES (2026-08-19, #274 squash `9581950b`)

문서의 DONE 표시만 믿지 말고 실제 코드/runtime을 확인한다.

### 8-5. MUST — 반드시 구현

- [x] `auto_dev_overnight_ready.py`가 `TASK.md` `[ ]`/`[~]` 를 pending에 합친다
- [x] `--require-local`이 TASK.md READY가 있으면 통과한다
- [x] `예비 창업` 띄어쓰기 본공고는 2차 PASS
- [x] 기창업 솔루션 도입만 있으면 2차 DROP 유지
- [x] ASCII 키워드 단어경계는 유지 (`email` 안의 `ai` 오매칭 없음)
- [x] `monitor.py` / `streamlit_app.py` 미수정
- [x] GHA `auto-dev-queue.yml` cron 미활성 유지
- [x] 실제 이메일/알림 발송 금지

### 8-6. KEEP — 유지

- `TASK.md`가 유일한 AI 작업지시
- `docs/project/TASKS.md`는 GHA 결정적 큐
- MAIL-005 OR 키워드, MAIL-006 precision_exclude
- 스케줄/수신자
- 허위 DONE 금지 (AUTO_DEV_AGENT 없으면 AWAITING_AGENT)

### 8-7. REMOVE — 제거

밤샘 판정이 `TASK.md` 대기 작업을 무시하는 동작. `예비창업` keep이 공백 때문에 빗나가는 동작.

### 8-8. FORBIDDEN — 금지

- `monitor.py` / `streamlit_app.py` 수정
- GHA cron 재활성 (`schedule_enabled` true로 바꾸지 않음)
- 실제 이메일/알림 발송
- Secret/API Key 로그
- 기존 실패 테스트 skip
- `git add -A` / force push / reset --hard

### 8-9. 선행조건·의존성

DEPENDS_ON: MAIL-006 (precision_keep/exclude 가 main에 있음).

### 8-10. 구현범위

- `scripts/auto_dev_overnight_ready.py`
- `scripts/auto_dev_queue.py` (TASK.md READY 안내만, TASK.md 체크박스 자동 변경 금지)
- `mail_core/matching/scoring.py` (`_kw_hit` 공백 정규화)
- `tests/test_scoring.py`
- `tests/test_outstanding_dev_audit.py`
- `docs/project/RULES.md` §9
- `auto_dev/work_assets.json`
- `TASK.md`

### 8-11. 입력검증

- `[ ]`/`[~]` → pending, `[x]`/`[!]`/`[-]` → 무시
- TASKS.md PENDING + TASK.md READY 병합
- 둘 다 비면 local_agent_ready false
- `예비 창업` + 솔루션 도입 → keep hit, PASS
- 기창업 솔루션만 → DROP
- ASCII `ai` in `email` → miss

### 8-12. 빈상태

TASK.md 리스트에 `[x]`만 있으면 overnight local ready 아님 (NO_ACTIVE_TASK). GHA cron은 그대로 끔.

### 8-13. 로딩상태

N/A

### 8-14. 오류상태

parser가 DONE 항목을 READY로 세면 FAIL. 점수 컷 회귀가 깨지면 FAIL.

---

## MAIL-008

### 8-1. 사용자 원문 요청

> 과거사용자가 요청했ㄷ너것중 미완료된거 task에추가하고 개발
>
> (미완료 원문 — 메일 누락제로 / 열린 Draft #269: 그룹 매칭이 15건을 넘으면 표에는 15행만 나오고 나머지는 seen_ids 에 잠겨 다시 안 온다)

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

15건이 넘는 공고가 메일에서 빠지지 않게 한다

### 8-3. 사용자가 원하는 최종 결과

- 그룹 매칭 20건이면 메일 표에도 20행
- 16번째 이후가 seen 만 되고 본문에서 빠지지 않음
- 실제 이메일 발송 없음
- `claude_summarize` / `fallback_body` 경로

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-008
- TASK_START_SHA: 41fdd39123d1e21f86cbe80c4317db01e9bc3724
- TASK_BLOB_SHA: 016b0e803d7d0790298325c96483d8d9f8141d85
- WORK_BRANCH: cursor/unfinished-past-requests-7dc1

- 현재 문제: 해결됨. `claude_summarize` 가 전량 렌더. pytest + 20건 E2E 행수=20, mail_sent=false.
REQUEST_SOLVED: YES

### 8-5. MUST

- [x] 매칭 N건이면 본문 행도 N건 (N>15 포함)
- [x] 회귀 테스트
- [x] 실발송 금지

### 8-6. KEEP

MAIL-002 8칸 표, 수집·매칭 정책, 수신자·스케줄

### 8-8. FORBIDDEN

실발송, Secret 로그, 기존 실패 테스트 skip

### 8-9. DEPENDS_ON

없음. MAIL-009/010과 monitor.py가 겹치면 이 TASK를 먼저.

### 8-10. 구현범위

`monitor.py` `claude_summarize`, `tests/test_mail_body_truncation.py`

---

## MAIL-009

### 8-1. 사용자 원문 요청

> 과거사용자가 요청했ㄷ너것중 미완료된거 task에추가하고 개발
>
> (미완료 원문 — 발송 누락 / 열린 Draft #270: 그룹 A만 보낸 채 죽으면 나중에 전체 실행이 stale outbox 를 seen_ids 로 올려 그룹 B가 영원히 못 받는다)

### 8-2. 비개발자용 1줄 요약

일부 그룹만 보낸 채 죽으면 다른 그룹이 못 받는 문제를 고친다

### 8-3. 사용자가 원하는 최종 결과

- 어제 A만 완료된 공유 공고가 오늘 전체 실행에서 seen 으로 잠기지 않음
- 오늘 날짜 전체 그룹 완료분은 정상 승격
- 실발송 없음

### 8-4. 현재상태

PINNING: MAIL-009 / 동일 브랜치 `cursor/unfinished-past-requests-7dc1`
- 현재 문제: 해결됨. `trust_dates={target_date}` + skip 경로 cycle 게이트. stale A-only 는 seen 에 안 들어감.
REQUEST_SOLVED: YES

### 8-5. MUST

- [x] 전체 그룹 end-of-run 은 `trust_dates={target_date}`
- [x] skip 경로 flush 는 `only_if_cycle_complete=True`
- [x] stale A-only 가 seen_ids 에 안 들어감
- [x] 실발송 금지

### 8-8. FORBIDDEN

실발송, Secret 로그, MAIL-008 본문 전량 발송 회귀 후퇴

### 8-9. DEPENDS_ON

MAIL-008과 같은 `monitor.py` — 순차.

### 8-10. 구현범위

`monitor.py` `persist_completed_outbox` / end-of-run / skip flush, `tests/test_outbox_seen_ids_multigroup.py`

---

## MAIL-010

### 8-1. 사용자 원문 요청

> 과거사용자가 요청했ㄷ너것중 미완료된거 task에추가하고 개발
>
> (미완료 원문 — MAIL-004 자동머지 기본 이후 / Draft #269: `.github/workflows/*` 만 바꾼 PR이 docs-only 로 pytest 를 건너뛰고도 자동머지된다)

### 8-2. 비개발자용 1줄 요약

워크플로만 바꾼 PR은 테스트 없이 자동머지되지 않게 한다

### 8-3. 사용자가 원하는 최종 결과

- `.github/workflows/*` 변경은 auto-merge 스킵 (사람 머지)
- test.yml 이 워크플로를 docs-only 로 취급하지 않음
- Draft / needs-human / .env* 예외 유지

### 8-4. 현재상태

PINNING: MAIL-010 / 동일 브랜치
- 현재 문제: 해결됨. workflow 경로 auto-merge 거부, test.yml docs-only 제외. #267 SHA 핀은 유지.
REQUEST_SOLVED: YES

### 8-5. MUST

- [x] workflow 경로 auto-merge 거부
- [x] test.yml 에서 workflow 를 docs-only 에서 제외
- [x] 회귀 테스트
- [x] `--admin` 머지 금지

### 8-8. FORBIDDEN

`gh pr merge --admin`, 실발송, SHA 핀(#267) 제거

### 8-9. DEPENDS_ON

MAIL-004. 파일군이 MAIL-008/009와 다름 → 같은 브랜치에 넣되 독립 검증.

### 8-10. 구현범위

`scripts/auto_merge_pr.py`, `tests/test_auto_merge_pr.py`, `.github/workflows/test.yml`, `.github/workflows/auto-merge.yml` 주석, `docs/project/RULES.md`

---

## MAIL-011

### 8-1. 사용자 원문 요청

> 비개발자용 공고첨부 받기 — 원클릭 설치·배포
>
> (열린 PR #243, UNIQUE_CANDIDATE. MAIL-008~010과 파일군이 다름)

### 8-2. 비개발자용 1줄 요약

비개발자용 공고첨부 원클릭 설치를 마친다

### 8-3. 사용자가 원하는 최종 결과

비개발자가 공고 첨부를 원클릭으로 받아 설치할 수 있다. 이번 실행의 ACTIVE는 MAIL-008~010(누락·발송 안전)이 우선이라 이 TASK는 READY로 등록만 한다.

### 8-4. 현재상태

열린 PR #243. 이번 브랜치에서 구현하지 않음 (순차: 누락제로 먼저).

### 8-5. MUST

- [ ] 원클릭 설치·배포가 main 에 있다
- [ ] 실발송 금지

### 8-9. DEPENDS_ON

MAIL-008~010 완료 후. 병렬 가능하나 이번 실행은 누락제로 우선.

---

## MAIL-012

### 8-1. 사용자 원문 요청

> ㅇ예비창업자 ai공고수집 개선 pr어디갔어
> 적용된거? 우선 AI 사업화지원금 공고 모두수집원함
> 그러기위한 개발방안 task에 추가하고 밤샘개발

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

AI 사업화지원금 공고를 빠짐없이 수집한다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 실제로 사용했을 때:

- 제목에 AI/인공지능 + 사업화지원금(또는 사업화자금·사업화 지원)이 있는 공고는 예비창업 AI 메일에서 빠지지 않는다
- `참여기업`이 제목에 있어도 사업화지원금이면 유지한다 (MAIL-006의 기창업 솔루션 제외는 그대로)
- 기창업 `AI 솔루션 도입`만 있는 공고는 예비창업 메일에서 계속 빠진다
- 워치리스트가 `AI 사업화지원금` 변형을 강제포함한다
- 이전 예비창업 PR 상태가 TASK에 사실대로 적혀 있다
- GHA cron은 켜지지 않는다
- `monitor.py`는 수정하지 않는다
- 실제 이메일은 발송되지 않는다

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-012
- TASK_START_SHA: 8a048dd6
- WORK_BRANCH: cursor/ai-grant-full-recall-b14b
- origin: https://github.com/pds2225/mail.git (일치)

이전 예비창업자 AI 공고 PR (적용 여부):

| PR | 내용 | 상태 | main 적용 |
|---|---|---|---|
| #271 | 예비창업 본공고가 2차 점수에서 떨어지지 않게 OR 키워드 추가 | MERGED 2026-08-19 | 예 |
| #272 | 기창업 솔루션 공고는 예비창업 메일에서 뺀다 | MERGED 2026-08-19 | 예 |
| #274 | 밤샘이 TASK.md를 읽고 `예비 창업` 띄어쓰기를 살린다 | MERGED 2026-08-19 | 예 |
| #239/#240 | P0/P1 예비창업 공고 파이프라인 | MERGED 2026-08-08 | 예 |
| #179 | 예비창업 AI digest 정밀도 | MERGED 2026-07-24 | 예 |
| #264 | MAIL-003 원인 분석 문서 | Draft, 충돌로 미머지. 분석은 #271이 TASK에 흡수 | 아니오 (내용 흡수) |
| #260 | 로컬 P0 잔여분(키워드·판정사유·계획서, monitor.py 포함) | OPEN | 아니오 |
| #273 | spaced 예비 창업 precision_keep | Draft. #274가 scoring 공백무시로 대체 | 아니오 (내용 대체) |

핵심: 개선 PR은 사라지지 않았고 **#271/#272/#274가 main에 들어가 있다.** 다만 그건 **적합도(2차 점수·기창업 제외)** 패치다. **AI 사업화지원금 전수 수집**은 별 문제였다.

현재 구멍 (슬라이스 1에서 막음):

- 1차 AND `["AI","사업화"]`는 `AI 사업화지원금`을 통과시킨다
- 2차는 `or_keywords`에 사업화지원금이 없고, MAIL-006 `참여기업` 감점이 keep을 못 만나면 점수 0으로 DROP
- 창업진흥원(KISED) 소스 2개가 `enabled:false`, IITP 소스 없음 → 수집 공백은 슬라이스 2

슬라이스 1 검증 (실발송 없음):
- pytest `test_ai_commercialization_grant_recall.py` + scoring + digest + consultant + `test_monitor.py` → 190 passed
- `recall_zero_gate` 신규 스위트 18 passed. bizinfo/kstartup replay는 환경에 `respx` 없으면 collect error (기존 이슈, 설치 후 통과)
- `auto_dev_overnight_ready.py` → local_agent=True, MAIL-012 pending. GHA cron 꺼짐 유지

슬라이스 2 실측 (켜지 않음):
- `kised` URL `menu.es?mid=a10201000000` → HTTP 200이지만 본문 ERROR 404, table row 0
- `imp_6e8c8360` 사업공고 페이지는 메뉴 HTML만 있고 `table tbody tr` 0건 (목록은 JS/다른 엔드포인트)
- IITP `businessPblancList.it` → `/web/index.do` 홈으로 리다이렉트, SPA `{{item.title}}` 템플릿만. html_table로 켜면 0건
- FORBIDDEN 준수: 셀렉터 실측 없이 enabled 하지 않음. 슬라이스 2는 공개 API/목록 URL을 찾은 다음 실행

### 8-5. MUST — 반드시 구현

밤샘 슬라이스 (순서 고정, 한 슬라이스 실패해도 허위 DONE 금지):

슬라이스 1 — 판정 누락 차단 (이번 실행)

- [x] `grp_prestartup_ai` OR에 `AI 사업화` / `인공지능 사업화` / 사업화지원금·자금 복합어 추가
- [x] AND에 `AI+지원금`, `AI+사업화자금`, `인공지능+지원금`, `인공지능+사업화자금` 추가
- [x] `precision_keep_keywords`에 `사업화지원금` / `사업화자금` / `사업화지원` 추가 (참여기업 감점 무력화)
- [x] 워치리스트에 AI 사업화지원금·자금 제목 변형 추가 (기존 컨설턴트 키워드 유지)
- [x] 회귀 테스트: 사업화지원금은 2차 PASS, 기창업 솔루션은 2차 DROP, 비AI 사업화지원금은 예비창업 그룹 미통과
- [x] `recall_zero_gate.py`에 해당 테스트 편입
- [x] `monitor.py` / `streamlit_app.py` 미수정
- [x] GHA cron 미활성 유지
- [x] 실제 이메일/알림 발송 금지

슬라이스 2 — 수집 소스 공백 (후속, 이 TASK 미완료 조건)

- [ ] 창업진흥원 `kised` / `imp_6e8c8360` 셀렉터 실측 후 켜기. 메뉴·사진뉴스면 원복
- [ ] IITP(정보통신기획평가원) 사업공고 소스 추가. 로그인 전용 링크면 공개 URL로 정규화
- [ ] NIPA·기업마당·K-Startup AI 사업화 키워드 재생 테스트가 살아 있는지 확인
- [ ] live 수집은 Cloud TLS 제한이 있으면 replay/fixture로 증거. 실발송 없음

슬라이스 3 — 운영 게이트

- [x] `python3 scripts/auto_dev_overnight_ready.py --require-local` 가 MAIL-012를 pending으로 본다
- [ ] REQUEST_SOLVED는 슬라이스 1+2가 끝난 뒤에만 YES. 지금은 PARTIAL (판정 누락은 막음, KISED/IITP 수집 공백은 남음)

### 8-6. KEEP — 유지

- MAIL-005 OR(예비창업/예비창업자/창업예정자)
- MAIL-006 기창업 솔루션 도입 제외
- 컨설턴트 워치리스트 키워드
- 기존 수집 소스 enabled 상태 (슬라이스 2에서 고른 소스만 켬)
- preview/dry-run, 수신자 목록

### 8-7. REMOVE — 제거

AI 사업화지원금이 `참여기업` 감점만으로 2차에서 점수 0 탈락하는 동작.

### 8-8. FORBIDDEN — 금지

- `monitor.py` / `streamlit_app.py` 수정
- GHA cron 재활성
- 실제 이메일/알림 발송
- Secret/API Key 로그
- 기존 실패 테스트 skip
- 비AI 사업화지원금까지 예비창업 AI 그룹에 넣는 것
- KISED를 셀렉터 실측 없이 enabled:true

### 8-9. 선행조건·의존성

DEPENDS_ON: MAIL-005, MAIL-006 (main 머지됨). MAIL-011과 파일군이 달라 병렬 가능. 이번 실행은 MAIL-012가 최신 사용자 요청이므로 우선.

### 8-10. 구현범위

- `config/groups.json` `grp_prestartup_ai`
- `config/watchlist.json` keywords 추가만
- `tests/test_ai_commercialization_grant_recall.py` (신규)
- `tests/test_scoring.py` / `tests/test_prestartup_ai_digest_regression.py` 보강
- `scripts/recall_zero_gate.py` RECALL_SUITES
- `TASK.md` / `docs/project/TASKS.md`

슬라이스 2는 `config/sites.json` + replay 테스트. 이번 커밋에 소스 활성화 넣지 않는다.

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

머지는 기본이다. Checks 초록 + 충돌 없으면 squash-merge 한다.
TASK에 “머지 금지”가 없는 한 작업 브랜치 PR은 자동 병합한다.

예외(opt-out)만 머지하지 않는다:

- Draft
- 라벨 `needs-human` 또는 `blocked`
- merge conflict
- `.env` / `.env.local` / `.env.example`
- `.github/workflows/*` (CI 게이트는 사람 머지)

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
