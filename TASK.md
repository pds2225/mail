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
[x] MAIL-011 | 비개발자용 공고첨부 원클릭 설치를 마친다
[x] MAIL-012 | AI 사업화지원금 공고를 빠짐없이 수집한다
[x] MAIL-013 | 사이트 활성/비활성 변경이 실제 저장되고 다음 실행에도 유지되게 한다
[ ] MAIL-014 | 154개 리스크 시트 기준으로 미해결 문제를 우선순위대로 점검·개발한다
[x] MAIL-015 | 과거 Git 이력에서 공고 필터 기준을 복원하고 누락분만 통합한다
[x] MAIL-016 | 기업별 업력을 공고 요건과 비교해 명백히 부적격일 때만 제외한다
[x] MAIL-017 | Vercel 웹 미리보기 실행 암호를 없앤다
[x] MAIL-018 | 공고검수 화면에서 O/X 누를 때마다 커밋하지 말고 선택한 것만 한 번에 저장한다
[x] MAIL-019 | 공고검수 선택 저장 시 GitHub URL 길이 초과 오류를 없앤다
[x] MAIL-020 | 공고검수 저장 시 GitHub 일반 오류 화면이 뜨지 않게 한다
[x] MAIL-021 | config-pending 저장 오류가 검수·그룹·설정에서 재발하지 않게 한다
[ ] MAIL-022 | 과거 O/X 판정 이력을 전수 분석해 공고 선별 정확도를 측정·개선한다
[ ] MAIL-023 | 수동 저장의 동시수정 유실을 막고 PR 생성까지 안전하게 완료되게 한다


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

# 7-A. 모든 TASK 공통 안전장치 — DEFAULT GUARDRAILS

아래 규칙은 **모든 현재/미래 TASK에 기본 적용**한다.
각 TASK DETAILS에 매번 반복해서 쓰지 않아도 자동 상속되는 전역 규칙이다.
TASK별로 더 강한 안전조건을 추가할 수는 있지만, 사용자의 명시적 승인 없이 아래 규칙을 약화하지 않는다.

## 자율수행 / 사용자 개입 최소화

- 조사 → 분석 → 구현 → 테스트 → 회귀검증 → 문서화 → commit → push → PR → Checks 확인 → 허용된 자동병합까지 안전하게 가능한 범위는 AI가 연속 수행한다.
- 중간 진행상황 확인만을 이유로 사용자를 호출하지 않는다.
- 개발자가 코드·테스트·Git 근거로 안전하게 결정할 수 있는 선택은 스스로 결정한다.
- 사용자 판단/입력이 정말 필요한 항목은 `HUMAN_BATCH`에 누적해 가능한 한 한 번에 요청한다.
- 개발자가 스스로 해결할 수 있는 오류·테스트 실패·Git 상태는 HUMAN_BATCH에 넣지 않는다.
- 예외적으로 즉시 확인이 필요한 경우:
  - 데이터 손실 위험
  - Secret/보안 문제
  - 실제 비용 발생
  - 외부 시스템에 되돌리기 어려운 운영 변경
  - 제품정책/사업정책을 바꾸는 결정
  - 법적/계약상 사용자 승인 필수 작업

## 중단/재개 안전성

- 장시간·다단계 TASK는 단계별 CHECKPOINT를 남긴다.
- CHECKPOINT는 최소한 현재 TASK_ID, base/code SHA, 완료 단계, 다음 단계, 핵심 산출물 위치를 재구성할 수 있어야 한다.
- 세션 만료, PC 종료, 컨텍스트 손실 후에도 최신 remote 상태와 TASK.md만 읽고 안전하게 재개할 수 있게 한다.
- 가능한 경우 단계 완료마다 필요한 파일만 commit/push한다.
- checkpoint를 남기기 위한 불필요한 임시파일 남발은 금지한다.

## 재실행 / 중복 방지

- 반복 실행 가능성이 있는 작업은 가능한 한 idempotent하게 구현한다.
- 같은 입력을 다시 실행해 데이터 중복 추가, 지표 이중계산, 규칙 중복적용, 동일 파일 중복생성이 발생하지 않게 한다.
- 입력 snapshot/fingerprint와 code/config SHA 등 재현에 필요한 식별정보를 가능한 범위에서 기록한다.
- 이미 완료·적용된 단계를 발견하면 검증 후 재사용하고 불필요하게 다시 수행하지 않는다.

## 무한루프 / 과도한 자동개발 방지

- 자동 반복개선·retry·agent loop는 반드시 종료조건을 둔다.
- TASK에 별도 수치가 없으면 합리적인 bounded retry/cycle을 정해 기록한다.
- 동일 실패를 근거 없이 무한 반복하지 않는다.
- 개선이 없거나 동일 오류가 반복되면 마지막 안전 checkpoint를 보존하고 원인을 기록한다.
- 한 후보/한 실험 실패 때문에 검증된 전체 작업을 되돌리지 않는다. 가능한 경우 실패 단위만 폐기한다.

## Git / 데이터 보존

- 사용자 변경 삭제 금지.
- `git reset --hard`, force push, `git clean -fd`, 무단 stash/drop 금지.
- `git add -A` 금지. 이번 TASK에 필요한 파일만 stage한다.
- main 직접 위험 수정 대신 작업 브랜치/PR을 기본으로 한다.
- 원격 main이 작업 중 바뀌면 최신 상태를 확인하고 안전하게 통합한 뒤 필요한 검증을 다시 한다.
- 충돌을 무조건 ours/theirs로 해결하지 않는다.
- 기존 사용자 데이터·정답 데이터·운영 설정은 명시적 근거 없이 덮어쓰거나 삭제하지 않는다.

## Secret / 외부효과 / 비용

- Secret, 토큰, 비밀번호, 개인정보를 출력·커밋하지 않는다.
- 실제 이메일 발송, 삭제, 라벨 변경, 결제, 유료 API, production 데이터 변경 등 외부효과가 있는 작업은 TASK에서 명시적으로 허용되거나 사용자 승인이 없는 한 dry-run/preview/staging을 우선한다.
- 비용이 발생하거나 되돌리기 어려운 외부 작업은 사용자 승인 전에 실행하지 않는다.

## 검증 / 완료 기준

- 코드 작성, 테스트 PASS, build PASS, PR 생성만으로 DONE 처리하지 않는다.
- 사용자 요청의 실제 결과가 해결됐는지 USER_E2E 또는 그에 준하는 실제 경로로 확인한다.
- 변경한 범위의 정상경로, 경계값, 오류상태, 회귀를 검증한다.
- TASK가 데이터/평가/모델 성능을 다루면 tuning 데이터와 최종 평가 데이터를 가능한 범위에서 분리해 leakage를 방지한다.
- 성능·정확도 수치는 같은 기준 데이터/동일 조건에서 변경 전후를 비교한다.
- 실패·목표 미달 수치를 숨기거나 유리한 표본만 골라 보고하지 않는다.

## 부분 장애

- CI 실패, 외부 사이트 일시 오류, 일부 데이터 미접근 등 부분 장애가 생겨도 안전하게 가능한 독립 작업은 계속한다.
- 이미 검증된 산출물과 checkpoint를 보존한다.
- 정말 사용자 입력이 필요한 항목만 HUMAN_BATCH 또는 BLOCKED_INPUT으로 분리한다.
- 한 의존성의 실패 때문에 관련 없는 독립 작업까지 전부 중단하지 않는다.

## TASK별 적용 원칙

- 단순 문서 수정처럼 checkpoint/idempotency가 의미 없는 TASK에는 형식적으로 억지 구현하지 않는다.
- 대신 해당 TASK에 실질적으로 필요한 안전장치만 적용하고, 적용하지 않은 항목은 N/A로 판단할 수 있다.
- TASK별 DETAILS의 MUST/KEEP/REMOVE/FORBIDDEN/VERIFY/DONE은 이 전역 규칙을 상속한다.

---

# 8. TASK DETAILS

<!--
TASK LIST 한 줄 요약과 아래 상세 TASK는 TASK_ID로 연결한다.
새 사용자 요청을 TASK로 만들 때 반드시 MUST / KEEP / REMOVE / FORBIDDEN / VERIFY / DONE 관점으로 변환한다.
TRACK A(MAIL-001)가 선행이다. MAIL-002는 MAIL-001에 의존한다.
-->

## MAIL-015

### 8-1. 사용자 원문 요청

> 현재 코드만 보고 새 기준을 만들지 말고, 저장소의 전체 Git 이력·과거 브랜치·삭제 파일·이전 설정파일·문서·테스트를 전수 조사해서 과거 기준을 복원한 뒤 현재 시스템에 통합하라.

### 8-2. 비개발자용 1줄 요약

과거에 확정된 공고 필터 기준을 전수 대조해 누락된 것만 복원한다

### 8-3. 사용자가 원하는 최종 결과

- 과거 코드·문서·설정·테스트에서 확인된 기준과 현재 구현을 표로 비교한다.
- 예비창업, 지역 세부 제한, 특별키워드, 공장·스마트공장, 해외·전시회 등 과거 기준의 생존·누락·충돌을 증거와 함께 정리한다.
- 누락이 실제로 확인된 항목만 기존 evaluator/filter 구조에 최소 변경으로 복원한다.
- 신청자격·마감·지역 Hard Gate를 카테고리보다 먼저 적용하고, 카테고리는 마지막 표시값으로만 둔다.

### 8-4. 현재상태

- PINNING: TASK_START_SHA=534f680f3198dcf46ce3445717b1f469602f2500
- WORK_BRANCH=feat/mail-015-history-restore (TASK 등록 PR #297 병합 후 구현 브랜치)
- 현재 로컬 main에는 기존 사용자 변경 `web/auto_mail_web.html`이 있어 보존한다.
- 실제 메일 발송·라벨 변경·삭제는 하지 않는다.

### 8-5. MUST — 반드시 구현

- [x] 현재 파일·전체 Git log/log-by-file/blame·브랜치·삭제/이름변경 파일·README/AGENTS/TASKS/DONE/CHANGELOG·설정·키워드 사전·company/group·메일 코드·테스트를 조사한다.
- [x] 지정된 과거 키워드와 지역·공장·신청자격·날짜·제외 기준을 Git 증거와 함께 복원표에 기록한다.
- [x] 특별키워드는 priority/boost/force-review 과거 동작이 확인될 때만 복원하고 Hard Gate는 우회하지 않는다.
- [x] 누락분만 최소 변경하고 주요 판정에 reason_code와 회귀테스트를 남긴다. `TENANT_ONLY` reason_code를 P0-4에 추가해 "입주공간/사무공간 단독, 자금·성장지원·컨설팅·투자 신호 없음" 공고만 제외한다. 명시적 자금 부정 문구("지원금은 없습니다" 등)는 자금 신호로 세지 않되, 사업화·성장지원·바우처 등 다른 실질 지원 신호가 있으면 여전히 제외하지 않아 AI 허브 정상 사례를 보존한다(`docs/PAST_FILTER_CRITERIA_RESTORATION.md` "실제 재현" 절 참조).
- [x] 실제 이메일·라벨 변경·삭제·Secret 출력은 하지 않는다.

### 8-6. KEEP — 유지

- 기존 수집기·중복제거·메일 발송 구조와 사용자 설정
- 지역 unknown은 확실한 타지역과 구분하는 recall 우선 정책
- 과거와 현재가 충돌하면 가장 최근의 명시적 사용자 요구를 우선하되 근거를 기록

### 8-7. REMOVE — 제거

없음. 기존 기준·기능은 근거 없이 삭제하지 않는다.

### 8-8. FORBIDDEN — 금지

- 현재 코드만 보고 새 기준을 임의로 설계하지 않는다.
- 기존 필터 전체 교체·대규모 리팩터링을 하지 않는다.
- `.env`, 토큰, 메일 원문, 개인정보를 출력·커밋하지 않는다.
- 실제 메일 발송·실제 라벨 변경·실제 삭제를 하지 않는다.
- 기존 사용자 변경을 되돌리거나 main에 직접 위험 변경을 하지 않는다.

### 8-9. 선행조건·의존성

DEPENDS_ON: 없음

### 8-10. 구현범위

과거 기준 복원조사 → 차이분석표 → 필요한 설정/보조판정 로직의 최소 복원 → 관련 회귀테스트. 기존 핵심 구조를 재사용한다.

### 8-11. 입력검증

예비창업자/기창업자, 전국/서울/경기/인천 전체/인천 특정 구, 공장 필수/일반, 특별키워드, 설명회·컨설팅·멘토링, 마감·수정·연장·재공고, 중복 공고를 각각 검증한다.

### 8-12. 빈상태

공고 없음·상세 필드 없음·지역 미상은 기존 empty/review 정책을 유지하며 적격으로 추측하지 않는다.

### 8-13. 로딩상태

N/A — 조사·로컬 테스트 작업. 기존 수집 중복 실행 방지 정책은 유지한다.

### 8-14. 오류상태

GitHub 인증·원격 이력·기존 테스트 권한 오류는 숨기지 않고 별도 보고한다. 수집기 외부 오류를 기준 복원 근거로 오인하지 않는다.

### 8-15. VERIFY

- [x] `python -m py_compile monitor.py`
- [x] `python -m json.tool config/groups.json > NUL`
- [x] MAIL-015 회귀 19개 + 관련 스위트 12개 파일(test_monitor, test_digest_fp_hardening, test_5field_casematrix, test_p1_context_exclusions, test_consultant_notices, test_filter_accuracy_r2, test_scoring, test_prestartup_ai_digest_regression, test_digest_eight_columns, test_fetch_notice_attachments, test_mail_digest_mobile, test_nonnotice_title_filter) 총 536개 직접 재실행 통과, 회귀 없음(2026-09-17 최종 검증). 전체 pytest 1,432 passed/6 skipped는 이전 세션 보고치이며 이번 세션에서 전체 재실행은 하지 않음(부분 검증으로 대체).
- [x] 실제 발송 없음, `ALLOW_SEND_EMAIL=false`, `ALLOW_DELETE_EMAIL=false`, `ALLOW_LABEL_CHANGE=false`
- [x] 변경 파일·기존 사용자 변경·Secret 포함 여부 최종 확인

### 8-16. DONE

REQUEST_SOLVED=YES — 복원표·19개 MAIL-015 회귀테스트·TENANT_ONLY 최소 구현을 커밋했고(f878126a), 관련 스위트 536개 재실행으로 회귀 없음을 확인했다. 실제 발송·라벨 변경·삭제 없음. push·PR은 아직(로컬 커밋만).

---

## MAIL-016

### 8-1. 사용자 원문 요청

> 기존 검증 결과를 반영하여 기업별 업력 Hard Gate 작업을 등록·구현한다. 그룹 정책
> `business_years_status(item, group)`/`BUSINESS_YEARS_NOT_ELIGIBLE`을 기업 판정에
> 그대로 재사용하지 말고, 기업 프로필의 실제 업력과 공고의 신청가능 업력 요건을
> 새로 비교하는 함수를 `company_match.py`에 구현한다. unknown은 임의 탈락시키지 않는다.

### 8-2. 비개발자용 1줄 요약

기업이 실제로 창업한 지 얼마나 됐는지와, 공고가 요구하는 업력 조건을 비교해서
"명백히 안 맞을 때만" 그 공고를 빼준다. 애매하면 빼지 않는다.

### 8-3. 사용자가 원하는 최종 결과

- 기존 지역 Hard Gate·판정 순서(마감→지역→업력→기타→스코어링)는 그대로 유지한다.
- 기업 프로필에 `business_stage`/`founded_date` 최소 필드를 추가해 실제 업력을 판단한다.
- 공고 업력 요건은 기존 파싱 유틸(`extract_business_year_requirement`,
  `parse_kstartup_business_buckets`)을 확인 후 재사용하되, 그룹 전용 함수
  (`monitor.business_years_status`)는 기업 판정에 재사용하지 않는다.
- 비교 결과는 eligible/ineligible/unknown 3상태이며, ineligible일 때만 Hard Exclude한다.

### 8-4. 현재상태

- PINNING: TASK_START_SHA=fe8a54bcd0fc7ce128a72baf85b99fc0e4aa31c4 (origin/main, PR #299 병합 직후)
- WORK_BRANCH=feat/mail-016-company-business-years-gate
- 실제 메일 발송·라벨 변경·삭제는 하지 않는다.

### 8-5. MUST — 반드시 구현

- [x] `mail_core/matching/company_match.py`에 `company_business_years_status(item, company)`
      신규 구현 — 기업 실제 업력 vs 공고 신청가능 업력 비교, eligible/ineligible/unknown 반환.
- [x] 기업 프로필에 `business_stage`(예: "예비창업자"/"established")·`founded_date`(YYYY-MM-DD)
      최소 필드를 `_normalize_company()`에 추가(기본값 빈 문자열, 중복 필드 신설 없음).
- [x] `_hard_excluded()`에 company 인자를 추가해 ineligible일 때만 Hard Exclude
      (`COMPANY_BUSINESS_YEARS_NOT_ELIGIBLE`), unknown/eligible은 통과.
- [x] K-Startup 업력 버킷 필드(`business_age_text`)·자유 텍스트(`extract_business_year_requirement`)
      두 경로 모두 지원하고, 그룹 전용 `business_years_status`/`BUSINESS_YEARS_NOT_ELIGIBLE`은
      기업 판정 경로에서 참조하지 않는다.
- [x] 실제 이메일·라벨 변경·삭제·Secret 출력은 하지 않는다.

### 8-6. KEEP — 유지

- 기존 지역 Hard Gate·점수 산정 로직, evaluate_notice 하드 제외 코드(HARD_EXCLUDE_CODES)
- 판정 순서: 마감 Hard Gate → 지역 Hard Gate → 업력 Hard Gate → 기타 절대 제외 → 관련성/기업 스코어링
- unknown은 Hard Exclude하지 않는 recall 우선 정책

### 8-7. REMOVE — 제거

없음. 기존 판정·필드를 근거 없이 삭제하지 않는다.

### 8-8. FORBIDDEN — 금지

- 그룹의 `BUSINESS_YEARS_NOT_ELIGIBLE`을 `company_match.py`의 `HARD_EXCLUDE_CODES`에
  그대로 추가해 기업 판정에 재사용하지 않는다.
- unknown을 ineligible로 변환하지 않는다.
- 기존 지역 판정 로직을 중복 구현하지 않는다(이미 `company_match.py`가 `monitor.py`의
  검증된 지역 판정을 재사용 중).
- `.env`, 토큰, 메일 원문, 개인정보를 출력·커밋하지 않는다.
- 실제 메일 발송·실제 라벨 변경·실제 삭제를 하지 않는다.
- main 직접 수정·push, MAIL-015 수정, 관련 없는 리팩터링을 하지 않는다.

### 8-9. 선행조건·의존성

DEPENDS_ON: MAIL-015 (병합 완료, fe8a54bc 기준)

### 8-10. 구현범위

`mail_core/matching/company_match.py`(신규 함수 3개 + `_normalize_company`/`_hard_excluded`/
`match_for_company` 최소 배선) + `tests/test_company_match_business_years.py`(신규 회귀
14건). `monitor.py`·`config/groups.json`·그룹 판정 로직은 수정하지 않는다(읽기 전용 재사용).

### 8-11. 입력검증

기업 업력 충족/명백한 미충족/unknown, 공고 업력조건 unknown, 지역 부적격+업력 적격,
업력 부적격+강한 키워드 매칭, 그룹 BUSINESS_YEARS_NOT_ELIGIBLE 오전파 여부, K-Startup
업력 버킷(숫자 버킷·"전체"·"예비창업자" 단독 표기), 예비창업자 기업 vs 예비창업자
전용 공고를 각각 검증한다.

### 8-12. 빈상태

기업 프로필에 `business_stage`/`founded_date`가 모두 없으면 unknown(기존처럼 적격으로
추측하지 않고, 동시에 임의 탈락도 시키지 않는다).

### 8-13. 로딩상태

N/A — 로컬 판정 로직 변경. 기존 수집·발송 파이프라인 동작에는 영향 없음.

### 8-14. 오류상태

`founded_date` 파싱 실패(형식 오류)는 정보 없음(unknown)으로 처리하고 예외를 던지지 않는다.
monitor 파싱 유틸 import 실패 시에도 unknown으로 안전 폴백한다.

### 8-15. VERIFY

- [x] `python -m py_compile mail_core/matching/company_match.py monitor.py`
- [x] `python -m pytest tests/test_company_match_business_years.py -v` — 신규 14건 전체 통과
- [x] `python -m pytest tests/test_company_match.py tests/test_company_match_multi_region.py -q` — 기존 39건 회귀 없음
- [x] `python -m pytest tests/test_5field_casematrix.py tests/test_core_sources_specialize.py tests/test_digest_eight_columns.py -q` — 업력 관련 기존 스위트 191건 회귀 없음
- [x] 전체 `python -m pytest -q` — 1446 passed, 6 skipped, 1 failed(542.88s). 실패 1건
      `test_kstartup_collect_policy.py::test_sites_json_public_priority_caps` 은
      `config/sites.json`을 인코딩 미지정으로 읽어 Windows cp949 로 디코딩하다 실패하는
      기존 환경 이슈로, 이 브랜치가 건드리지 않은 파일·테스트다
      (`git log -1 -- tests/test_kstartup_collect_policy.py config/sites.json` = 19079b7f,
      MAIL-016 커밋 이전). MAIL-016과 무관한 기존 실패로 기록하고 이번 범위에서 수정하지 않는다.
- [x] 실제 발송 없음, `ALLOW_SEND_EMAIL=false`, `ALLOW_DELETE_EMAIL=false`, `ALLOW_LABEL_CHANGE=false`

### 8-16. DONE

REQUEST_SOLVED=YES — `company_business_years_status()`를 신규 구현해 그룹 정책과 완전히
분리된 기업별 업력 Hard Gate를 추가했다. 신규 회귀 14건 + 관련 기존 스위트 230건 +
전체 pytest 1446건 통과(무관 기존 실패 1건 별도 기록), 회귀 없음. 실제 발송·라벨 변경·
삭제 없음. PR #304(main 미병합, 지시대로 보류).

---

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

비개발자가 공고 첨부를 원클릭으로 받아 설치할 수 있다.

- Windows에서 `처음설치_한번만.cmd` 한 번 → `지원사업 공고첨부_받기.cmd` 로 URL 붙여넣기
- Python이 없으면 winget으로 설치를 시도한다
- 남에게 줄 때는 `배포용_압축하기.cmd` 가 `.env` 없이 ZIP을 만든다
- 실제 이메일은 발송되지 않는다
- `dist/*.exe` 는 커밋하지 않는다

### 8-4. 현재상태

PINNING:
- TASK_ID: MAIL-011
- TASK_START_SHA: 3bda7763d85e44bac6ccdbd226e099323b96b121
- TASK_BLOB_SHA: 11220bd23c7b97550acf907df304a549b0af99c3
- WORK_BRANCH: cursor/mail011-attach-oneclick-7dc1
- origin: https://github.com/pds2225/mail.git (일치)

선행: MAIL-008~010은 main에 머지됨. UNIQUE_CANDIDATE는 PR #243 (`origin/cursor/easy-attach-downloader-install-2420`). 이번 브랜치는 #243 소스를 최신 main에 이식하되 `dist/*.exe` / `dist/*.zip` 은 커밋하지 않는다. `.github/workflows/build-attach-exe.yml` 은 MAIL-010(워크플로 사람 머지) 때문에 넣지 않는다. 원클릭은 Python+cmd 경로다.

MAIL-012(`[~]` PARTIAL, 슬라이스 2 남음)와 파일군이 달라 병렬 허용. 이 실행의 ACTIVE는 MAIL-011.

구현 (브랜치 `cursor/mail011-attach-oneclick-7dc1`, PR #278):
- 런처 3개 + setup 스크립트 + 최소 requirements + 배포 ZIP 스크립트
- 설정 `out_dir` 비움 → 바탕화면 `지원사업_공고첨부` 기본
- exe/zip 미커밋, workflow YAML 미추가

USER_E2E (Cloud Linux, 실발송 없음):
- `pytest` 설치 7 + 안전 7 + fetch 38 = 52 passed
- `setup_attach_downloader.py` exit 0 (ensurepip 없음 → 시스템 Python 폴백)
- `--check` exit 0
- `fetch --selfcheck` exit 0, URL 없이 `--dry-run` exit 2
- Windows `.cmd` 더블클릭은 이 VM에서 불가

REQUEST_SOLVED: YES
MAIN_MERGED: YES (2026-08-23, #278 squash `ea1ff047`)

Auto Merge는 테스트 완료 시점에 PR이 아직 Draft로 보여 skip 했다. 사용자 「다하고 자동병합」에 따라 Checks 초록 확인 후 squash-merge (`--admin` 없음).

### 8-5. MUST

- [x] 원클릭 설치·배포가 이 브랜치에 있다 (`처음설치_한번만.cmd` / `지원사업 공고첨부_받기.cmd` / `배포용_압축하기.cmd`)
- [x] 실발송 금지
- [x] exe/zip 바이너리 미커밋
- [x] 원클릭 설치·배포가 main 에 있다 (PR #278)

### 8-6. KEEP

- 기존 `scripts/fetch_notice_attachments.py` 첨부 파서·안전가드
- 메일 수집·발송 경로 미변경
- MAIL-012 슬라이스 1 판정 로직 미변경

### 8-8. FORBIDDEN

- 실발송, Secret 로그
- `dist/*.exe` / 설치 zip 커밋
- `monitor.py` / `streamlit_app.py` 수정 (이 TASK는 불필요)
- `.github/workflows/*` 추가 (MAIL-010 사람 머지 회피)

### 8-9. DEPENDS_ON

MAIL-008~010 완료(main). MAIL-012와 병렬 가능.

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
- TASK_START_SHA: f4ee88ad6b405b742109db5254e0edd500798fc7
- TASK_BLOB_SHA: 331f93325304cd234257787a079c66184a5eb332
- WORK_BRANCH: 구현 `cursor/ai-grant-full-recall-b14b` (PR #277) + 수집소스 `cursor/mail012-kised-iitp-collect-7dc1` (PR #281); closeout `docs/mail-012-finalize`
- origin: https://github.com/pds2225/mail.git (일치)
- 현재 기준: `origin/main=36a43c67d464f1e52ec4e0c7cd697326357d1207`; PR #277/#281 및 MAIL-012 closeout PR #302 모두 squash merge 완료
- REQUEST_SOLVED: YES

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

구현 전 구멍 (슬라이스 1·2에서 해결):

- 1차 AND `["AI","사업화"]`는 `AI 사업화지원금`을 통과시킨다
- 2차는 `or_keywords`에 사업화지원금이 없고, MAIL-006 `참여기업` 감점이 keep을 못 만나면 점수 0으로 DROP
- 창업진흥원(KISED) 소스 2개가 `enabled:false`, IITP 소스 없음 → 수집 공백은 슬라이스 2

슬라이스 1 검증 (실발송 없음):
- pytest `test_ai_commercialization_grant_recall.py` + scoring + digest + consultant + `test_monitor.py` → 190 passed
- `recall_zero_gate` 신규 스위트 18 passed. bizinfo/kstartup replay는 환경에 `respx` 없으면 collect error (기존 이슈, 설치 후 통과)
- `auto_dev_overnight_ready.py` → local_agent=True, MAIL-012 pending. GHA cron 꺼짐 유지

슬라이스 2 실측 (2026-08-23, 실발송 없음):
- `kised` 옛 URL `menu.es?mid=a10201000000` → 본문 ERROR 404, table 0행. **실제 목록** `misAnnouncement/index.es?mid=a10302000000` 의 `ul.lstyle_list > li` + `b.ls_tit` → live 30건, 상세는 K-Startup
- `imp_6e8c8360` 은 같은 목록. 셀렉터는 실측했으나 중복 수집 방지로 enabled=false
- IITP `businessPblancList.it` → SPA 홈, table 0건. **공개 목록** `https://ezone.iitp.kr/main/main` `#main_01 li:has(a[onclick*='PMS_TSK_PBNC_ID'])` → live 7건(접수중), 로그인 없음
- NIPA·기업마당·K-Startup replay + recall_zero_gate PASS
- monitor.py 미수정. html_table 셀렉터만 사용

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

슬라이스 2 — 수집 소스 공백

- [x] 창업진흥원 `kised` 셀렉터 실측 후 켜기 (`ul.lstyle_list`). `imp_6e8c8360` 은 동일 목록이라 중복 방지로 꺼 둠
- [x] IITP 사업공고 소스 추가 (`iitp`, ezone 접수중 탭, 로그인 불필요)
- [x] NIPA·기업마당·K-Startup AI 사업화 키워드 재생 테스트가 살아 있는지 확인
- [x] live 수집은 Cloud에서 실측 + replay/fixture로 증거. 실발송 없음

슬라이스 3 — 운영 게이트

- [x] `python3 scripts/auto_dev_overnight_ready.py --require-local` 로 실행 가능 상태를 점검했다 (완료 전 기준에서는 MAIL-012 pending)
- [x] REQUEST_SOLVED는 PR #277/#281의 main 반영 후 YES로 갱신했다

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

슬라이스 2는 `config/sites.json` + replay 테스트이며 구현 PR #281에서 반영했다.

### 8-16. DONE

REQUEST_SOLVED=YES — PR #277(판정 누락 차단)과 PR #281(KISED/IITP 수집소스)이 모두 `origin/main`에 squash merge된 것을 확인했다. 현재 main 기준 focused MAIL-012 회귀검증은 `191 passed`이며, JSON 설정 파싱·Python compile·`recall_zero_gate.py`도 통과했다. 실제 이메일 발송·삭제·대량 라벨 변경·Secret 변경·GHA cron 재활성은 0건이다.

- CLOSEOUT_BRANCH: `docs/mail-012-finalize`
- MAIN_SHA: `36a43c67d464f1e52ec4e0c7cd697326357d1207`
- IMPLEMENTATION_PRS: #277, #281 (merged)
- CLOSEOUT_PR: #302 (merged)
- CLOSEOUT_MERGE_SHA: `36a43c67d464f1e52ec4e0c7cd697326357d1207`
- FOCUSED_TEST: `python -m pytest -q tests/test_ai_commercialization_grant_recall.py tests/test_fetch_kised_replay.py tests/test_fetch_iitp_replay.py tests/test_kised_iitp_dedup_dates.py tests/test_scoring.py tests/test_prestartup_ai_digest_regression.py tests/test_monitor.py` → 191 passed
- SAFETY: `monitor.py`·`streamlit_app.py` 미수정, 실제 발송·삭제·라벨 변경 없음, GHA cron 미활성 유지
- NEXT_READY_TASK: MAIL-013 (이 closeout에서는 시작하지 않음)

---

## MAIL-013

### 8-1. 사용자 원문 요청

> 저장이안되네 활성비황성
>
> Task.md에 추가

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

사이트 활성/비활성 변경이 실제 저장되고 다음 실행에도 유지되게 한다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

사용자가 모바일 웹 관리화면에서 소스의 `활성` 체크를 바꾸고 `저장`했을 때:

- `활성 → 비활성`, `비활성 → 활성`이 실제 운영 설정에 저장됨
- 화면 새로고침 후에도 변경한 상태가 유지됨
- `config/sites.json`의 해당 소스 `enabled` 값과 화면 배지가 일치함
- 이후 GitHub Actions/메일 수집 실행도 저장된 `enabled` 값을 사용함
- 다른 소스의 설정은 같이 바뀌지 않음
- 저장이 아직 GitHub 반영 대기라면 `저장됨`처럼 오인시키지 않고 사용자가 해야 할 다음 동작을 모바일에서 명확히 제공함
- 실제 이메일은 발송되지 않음

이 결과가 달성되지 않으면 DONE이 아니다.

### 8-4. 현재상태

현재 코드 확인:

- `web/app/sites/[id]/edit/page.tsx`에 `enabled` 체크박스와 `저장` 버튼이 있고 `/api/sites/apply`로 POST한다.
- `web/app/api/sites/apply/route.ts`는 GitHub 토큰이 있으면 `config/sites.json`을 직접 커밋하고, 토큰이 없으면 `.apply/pending.json` 생성용 GitHub 웹 URL을 반환한다.
- `.github/workflows/apply-sites.yml`은 사용자가 `.apply/pending.json`을 실제 커밋한 뒤 `scripts/apply_sites_payload.py`로 `config/sites.json`에 반영하고 pending 파일을 제거한다.
- `web/lib/apply-client.ts`는 비토큰 경로에서 비동기 응답 뒤 `window.open()`으로 GitHub 확인 화면을 열려고 한다. 모바일 브라우저의 팝업 차단 가능성은 **원인 후보일 뿐 아직 확정하지 않는다.**
- 편집 화면에는 `githubCommitUrl`이 있으면 `저장 확인하기` 링크도 렌더한다.

사용자 실사용 보고: 활성/비활성 변경이 저장되지 않는다.

따라서 체크박스 UI만 고치지 말고 다음 구간 중 실제 실패 지점을 먼저 재현한다.

`checkbox state → POST body → /api/sites/apply → GitHub web/token fallback → pending commit → apply-sites Action → config/sites.json → /api/config → 새로고침 화면`

REQUEST_SOLVED: YES

현재 실행 기록:

- TASK_START_SHA: `458b22939d0b16c2cefac2e4348178b8ac8ab3d7`
- WORK_BRANCH: `feat/mail-013-site-toggle-persistence`
- IMPLEMENT_COMMIT: `e9ec66d62301d7680837339e8e0ae718436d4618`
- PR: #305 (merged, `068c85878223d6f3eb3243eeef1e8667a3f44afb`)
- 구현: tokenless 반영 응답을 `pending=true`로 구분하고 모바일 팝업 차단과 무관한 `GitHub에서 저장 확정` 명시 링크를 제공한다. pending 적용 단계와 API validation에서 `site.enabled` boolean을 강제한다.
- 검증: Python 10 passed, 웹 Vitest 38 passed, Next build/typecheck PASS, py_compile PASS, diff check PASS
- 안전 브라우저 smoke: 로컬 Chrome에서 `bizinfo` 활성→비활성 payload `enabled=false`, `kotra` 비활성→활성 payload `enabled=true` 및 GitHub `Commit changes` 화면을 확인했다. 실제 Commit은 누르지 않았다.
- 안전: 실제 GitHub pending commit·메일 발송·삭제·대량 라벨 변경·Secret 변경 없음

### 8-5. MUST — 반드시 구현

- [x] 모바일 저장 경로의 실패 후보(비동기 팝업 의존 및 수동 Commit 단계 불명확)를 코드 흐름으로 확인하고 명시적 링크로 보강
- [x] `enabled` boolean이 편집 form → POST → validation/normalized site → GitHub 반영 payload까지 보존되는 회귀 테스트 추가
- [x] 토큰이 있는 경로와 없는 기본 경로를 mock route 테스트로 분리해서 검증
- [x] 토큰 없는 기본 경로에서는 `.apply/pending.json` → `apply-sites` → `config/sites.json` 반영이 끝나야 실제 저장 완료로 판정
- [x] 모바일에서 자동 새창이 차단돼도 사용자가 한 번 탭해서 GitHub 반영 화면으로 이동할 수 있는 명시적 링크/버튼을 보강
- [x] `Commit changes` 등 추가 사용자 동작이 필요한 상태를 `저장 확정 필요`와 구분해서 표시
- [x] 안전한 임시 저장소에서 `pending → config/sites.json → pending 삭제` 후 재조회가 유지되는지 검증
- [x] 해당 소스 한 건만 변경되고 다른 소스 필드는 보존되는 회귀 테스트 추가
- [x] `enabled=true → false`, `false → true` 양방향 테스트 추가
- [x] malformed boolean(400)·GitHub read failure(500)·기존 auth 401 경로에서 성공 상태를 표시하지 않는 것을 검증
- [x] 실제 이메일/알림 발송 금지

### 8-6. KEEP — 유지

- Vercel에 장기 GitHub PAT/토큰을 코드로 넣지 않는 현재 보안 원칙
- `config/sites.json`을 운영 source of truth로 쓰는 구조
- 기존 사이트 ID·URL·collector·selector·note 등 사용자가 바꾸지 않은 필드
- 기존 `/api/sites/update` 검증 기능
- 기존 `.apply/pending.json` + GitHub Actions 적용 구조가 정상이라면 그대로 유지하고 최소 수정
- dry-run/preview 및 수신자/발송 설정

### 8-7. REMOVE — 제거

- 화면에서 체크 상태만 바뀌고 실제 운영 설정에는 반영되지 않는 동작
- GitHub 반영 대기 상태를 실제 저장 완료처럼 보이게 하는 표현
- 새로고침 시 이전 `enabled` 값으로 되돌아가는 원인이 확인되면 해당 원인만 최소 제거

### 8-8. FORBIDDEN — 금지

- GitHub PAT/API Key/Secret을 코드·로그·TASK에 기록
- `main`에 직접 위험한 변경
- 사용자 확인 없이 실제 메일 발송
- 다른 사이트를 대량 활성/비활성 처리
- `config/sites.json`의 unrelated source를 테스트 목적으로 임의 변경
- 기존 수집·판정·메일 로직 대규모 리팩터링
- 원인 확인 없이 `apply-sites.yml`을 임의 수정
- 모바일에서 PC 로컬 사용을 요구하는 해결책

### 8-9. 선행조건·의존성

DEPENDS_ON: 논리적 기능 의존성은 없음.

다만 MAIL-012가 `config/sites.json`을 변경할 수 있으므로 MAIL-013 구현 시작 시 반드시 최신 `origin/main`을 다시 받아 충돌 여부를 확인한다. MAIL-012가 아직 ACTIVE면 현재 작업에 섞지 않고 MAIL-013은 READY로 유지한다.

### 8-10. 구현범위

원인에 따라 최소 범위만 수정:

- `web/app/sites/[id]/edit/page.tsx`
- `web/app/api/sites/apply/route.ts`
- `web/lib/apply-client.ts`
- `web/lib/github-commit-url.ts`
- `scripts/apply_sites_payload.py`
- 관련 web/Python regression tests
- 필요한 경우에만 `.github/workflows/apply-sites.yml` (워크플로 변경이면 사람 머지 규칙 준수)

### 8-11. 입력검증

- 기존 `enabled=true`를 false로 변경
- 기존 `enabled=false`를 true로 변경
- 변경 없음
- 존재하지 않는 site id
- 잘못된 boolean/누락 payload
- GitHub token 있음/없음
- pending 파일 존재/충돌 상태

### 8-12. 빈상태

- 사이트 목록 0건이면 저장 대상 없음 상태를 명확히 표시
- 대상 site가 없으면 다른 site를 수정하지 않고 오류 처리

### 8-13. 로딩상태

- 저장 중 중복 클릭 방지
- GitHub 반영 대기와 실제 적용 완료를 구분
- 적용 완료 후 화면 상태를 서버 source of truth와 재동기화

### 8-14. 오류상태

반드시 검증:

- `/api/sites/apply` 401/400/500
- GitHub 새창/팝업 차단
- GitHub commit 미완료
- `apply-sites` Action 실패
- `config/sites.json` commit 충돌
- 네트워크 중단
- 적용 후 `/api/config` stale 응답

오류가 있어도 다른 사이트 상태를 훼손하지 않는다.

### 8-15. VERIFY / DONE

최소 검증:

1. Preview 또는 안전한 테스트 데이터에서 활성 → 비활성 저장
2. 실제 source of truth 재조회에서 `enabled=false` 확인
3. 새로고침 후 비활성 배지 유지
4. 비활성 → 활성 역방향 반복 후 `enabled=true` 확인
5. 다른 source 값 변경 0건 확인
6. 모바일 브라우저에서 자동 팝업이 막혀도 명시적 링크로 GitHub 반영 절차 진행 가능 확인
7. 실메일 발송 0건

다음이 모두 만족될 때만 `REQUEST_SOLVED: YES`:

- 양방향 저장 지속성 PASS
- 새로고침 지속성 PASS
- 수집기가 저장된 enabled 값을 사용함을 확인
- 실패 상태가 성공으로 표시되지 않음
- 회귀 테스트 PASS

### 8-16. DONE

REQUEST_SOLVED=YES — MAIL-013 구현 PR #305가 `origin/main`에 squash merge되었고, 후속 mock route/boolean 검증과 TASK 완료기록을 이 closeout PR에 담는다. 실제 운영 `config/sites.json`은 테스트 목적으로 변경하지 않았으며, 안전한 임시 저장소와 로컬 브라우저 preview로 양방향 저장 payload·명시적 Commit 단계·다른 소스 보존을 확인했다.

- TASK_START_SHA: `458b22939d0b16c2cefac2e4348178b8ac8ab3d7`
- IMPLEMENT_BRANCH: `feat/mail-013-site-toggle-persistence`
- IMPLEMENT_COMMIT: `e9ec66d62301d7680837339e8e0ae718436d4618`
- IMPLEMENT_PR: #305 (merged)
- IMPLEMENT_MERGE_SHA: `068c85878223d6f3eb3243eeef1e8667a3f44afb`
- CLOSEOUT_BRANCH: `docs/mail-013-closeout`
- TEST: Python 10 passed; web Vitest 38 passed; Next build/typecheck PASS; py_compile/diff check PASS
- SAFETY: 실제 메일·삭제·대량 라벨·Secret·실제 GitHub Commit 0건
- NEXT_READY_TASK: MAIL-014 (이 closeout에서는 시작하지 않음)

---

## MAIL-014

### 8-1. 사용자 원문 요청

> 뭉제점 엑셀시트 민들었던거
> 이거task에 등록

대상 시트:

- 정부지원사업 자동화서비스 개발리스크 154개
- Google Sheets: https://docs.google.com/spreadsheets/d/1e95jsQ0UfILu6GvUrR3G1E0HNBv3aXOGCsc32YCbh1E/edit
- 기준 탭: `사용자 우선순위`, `요약`, 기존 154개 리스크 원본

원문의 의미를 축약 과정에서 변경하지 않는다.

### 8-2. 비개발자용 1줄 요약

154개 리스크 시트 기준으로 미해결 문제를 우선순위대로 점검·개발한다

이 문장이 상단 TASK LIST에 그대로 표시된다.

### 8-3. 사용자가 원하는 최종 결과

최신 `main` 코드와 154개 리스크 시트를 대조해서 이미 해결된 항목은 다시 만들지 않고, 실제로 남아 있는 문제만 우선순위대로 개발한다.

개발 순서:

1. P0-A 활성 소스 미실행·0건·부분수집 탐지
2. P0-B 상세정보 접근·파싱·판정필수 필드 추출 누락 탐지
3. P0-C 최근 3영업일 재조회·연장·수정·재공고 복구
4. P0-D 공고별 단계이력·제외사유·근거 추적 및 회귀검증
5. P1-A 키워드·지역·지원유형 오판 개선
6. P1-B 그룹 미매칭 공고의 기업별 재승격
7. P1-C Claude 요약 사실정보 안정화

한 번에 154개를 대규모 수정하지 않는다. 각 항목은 `재현 → 최소 수정 → 테스트 → dry-run/preview 검증 → 다음 항목` 순서로 처리한다.

### 8-4. 현재상태

- 등록 시점에 MAIL-012가 `[~]` ACTIVE, MAIL-013이 `[ ]` READY이므로 MAIL-014는 `[ ]` READY로 등록한다.
- 처음 실행할 때 최신 `main`과 시트 항목을 1:1 대조해 `ALREADY_DONE / REPRODUCED / NOT_REPRODUCED / BLOCKED`로 분류한다.
- 문서에 해결 표시가 있더라도 실제 코드·테스트 근거 없이 완료 처리하지 않는다.

REQUEST_SOLVED: NO — 이번 슬라이스는 `docs/project/TASKS.md` PENDING 1순위(DEPENDS_ON 없음) `TASK-021 = MAIL-P0C-01(최근 3영업일 재조회)` 하나만 착수한다.
PINNING: TASK_START_SHA=7e9ce43870da7a7457650d76b9ba387f6d50efc3 (origin/main)
WORK_BRANCH=feat/mail-p0c01-recent-3bizdays (새 격리 worktree `mail-014-p0c01`)
MAIL-016(PR #304, feat/mail-016-company-business-years-gate)과 `mail_core/matching/company_match.py`는 건드리지 않는다.

**슬라이스 진행상황·병합 증거 (2026-09-18):**
- TASK-021 = MAIL-P0C-01(최근 3영업일 재조회) — 구현·테스트 완료. 구현 PR #307이 저장소 자동머지 봇(`app/github-actions`)에 의해 squash-merge되어 `origin/main`에 반영됨. **MAIN_SHA=202c7df70a65ea864455b704f32776ba1d9f24d8**.
- 구현 중 발견: 다른 세션이 "Auto Dev Controller 하드닝" 작업 도중 이 TASK를 이미 상당 부분 구현해 두고(커밋 `163518f3`, dangling·미푸시·미병합) 일시중단한 상태였다. 코드를 검토한 뒤 재구현 대신 그 패치를 그대로 적용해 중복 작업을 피했다(기존 미반영 작업 보존 원칙).
- FOCUSED_TEST: `test_notice_version_recovery.py` 23건(신규 4건) + focused 관련 스위트 185건 통과. 전체 `python -m pytest -q` 1456 passed/1 skipped/1 failed(무관 기존 실패 `test_sites_json_public_priority_caps`, cp949 이슈). 신규 회귀 없음.
- 참고: PR #307은 두 커밋(구현 86508c77 + 문서 e6ba27fd)이 있었으나, 자동머지 봇이 첫 커밋 기준 CI 통과 직후 곧바로 squash-merge해 두 번째(전체 pytest 기록) 커밋 내용은 main에 반영되지 않았다. 이 closeout 커밋이 그 기록을 main에 보완한다.
- MAIL-014의 나머지 23개 원자 TASK(TASK-022~044)는 이번 슬라이스에서 시작하지 않는다. MAIL-014 전체는 계속 `[~]` 진행 중으로 유지한다.

**슬라이스 2 (2026-09-19):** TASK-022 = MAIL-P0C-02(Canonical ID·중복 유형 분류) 구현·테스트 완료.
WORK_BRANCH=feat/mail-p0c02-canonical-dedup (새 격리 워크트리 `mail-022-canonical-dedup`).
TASK_START_SHA=e6a4d79e772387464cf2704de8723bd5ffc41b3d (origin/main). 회귀 179건(신규 10건 포함)
통과. 사용자 지시(2026-09-19)로 승인 요청 없이 MAIL-014 P0 큐(TASK-023~030)를 계속 진행하며,
P1 시작 전(TASK-030 완료 시)에는 반드시 멈추고 보고한다.

### 8-5. MUST — 반드시 구현

- [ ] 시트의 `사용자 우선순위`·`요약` 탭과 최신 코드/테스트를 대조
- [ ] 이미 해결된 리스크는 실제 코드·테스트 근거가 있을 때만 `ALREADY_DONE` 처리
- [ ] P0-A: 활성 소스 실행대장, 0건·급감·부분수집·페이지네이션·파서 실패 탐지
- [ ] P0-B: 상세 접근 실패와 실제 미기재를 구분하고 판정필수 필드 추출 실패 탐지
- [ ] P0-C: 최근 3영업일 재조회와 content/version 기반 연장·수정·재공고 복구
- [ ] P0-D: Fetch→Enrich→Normalize→Evaluate→Company Match→Summarize→Delivery 단계별 상태·제외사유·근거 추적
- [ ] P1-A: 자격 Hard Gate와 관련성 점수를 분리하고 키워드·지역·지원유형 오판 회귀검증
- [ ] P1-B: 기업 매칭이 Hard Gate를 우회하지 않으면서 그룹 누락 공고를 기업별로 재검토
- [ ] P1-C: 지원금·마감일·지역·대상·원문URL 같은 사실필드는 구조화 데이터에서만 출력하고 요약 실패 fallback 유지
- [ ] 각 슬라이스마다 최소 1개 재현 테스트와 관련 regression test 추가
- [ ] 실제 이메일 발송 없이 `dry-run/preview`로 사용자 E2E 검증
- [ ] 완료 항목을 시트 리스크 번호/우선순위와 코드·테스트 근거로 연결해 보고

### 8-6. KEEP — 유지

- 기존 MAIL-001~013에서 이미 검증된 동작
- 기본 `DEFAULT_RUN_MODE=dry-run`
- `ALLOW_SEND_EMAIL=false`, `ALLOW_DELETE_EMAIL=false`, `ALLOW_LABEL_CHANGE=false`
- 기존 수신자·스케줄·Secrets 구조
- 공고 원문·개인정보·토큰 마스킹
- 실패 소스가 있어도 안전하게 나머지를 계속 처리하는 장애격리 원칙

### 8-7. REMOVE — 제거

- 문서에 적혀 있다는 이유만으로 실제 코드 확인 없이 DONE 처리하는 방식
- `HTTP 200 = 정상 수집`, `0건 = 정상`으로 단정하는 방식
- 파싱 실패와 원문 미기재를 같은 `unknown`으로 숨기는 방식
- 기업 키워드가 맞는다는 이유로 Hard Gate 탈락 공고를 무조건 승격하는 방식
- Claude 요약 실패 때문에 공고 자체를 누락시키는 방식

### 8-8. FORBIDDEN — 금지

- 154개 리스크를 한 PR에서 전면 리팩터링
- 실제 이메일 발송·삭제·대량 라벨 변경
- `.env`, API Key, OAuth 토큰, 고객정보, 메일 원문 커밋/로그
- 기존 MAIL-012 ACTIVE 범위에 MAIL-014 변경을 섞기
- 근거 없는 신규 수집처 추가
- 테스트 실패를 skip/삭제해서 통과시키기
- `git add -A`, force push, `reset --hard`
- 사용자 요청 없이 DB 전면 전환·스키마 대수술

### 8-9. 선행조건·의존성

DEPENDS_ON:

- 기본적으로 MAIL-012 완료 후 시작한다.
- MAIL-014의 독립 조사·재현은 파일/API/entrypoint가 겹치지 않을 때만 병렬 가능하다.
- `config/sites.json`, 수집기, 판정기 등 MAIL-012와 겹치는 코드는 MAIL-012 머지 후 최신 `main`에서 시작한다.
- MAIL-013과 파일 충돌이 없으면 독립 진행 가능하다.

### 8-10. 구현범위

첫 실행은 진단 슬라이스로 시작한다.

1. 시트 154개와 최신 main 대조
2. 이미 해결/미해결/중복/현 단계 제외 분류
3. 미해결 P0-A~D를 각각 독립 작업 단위로 분해
4. 각 단위는 최소 변경·테스트·dry-run 검증
5. P0 완료 뒤 P1-A~C 순차 진행

수정 가능 파일은 각 슬라이스 시작 시 재현 결과로 확정한다. 처음부터 `monitor.py`나 DB를 수정 대상으로 고정하지 않는다.

### 8-11. VERIFY — 해결 여부 검증

최소 기준:

- 활성 소스 실행대장 기록률 100%
- P0 장애 시나리오 탐지율 100%
- 핵심소스 판정필수 필드 추출률 95% 이상
- 핵심소스 Golden Set 재현율 98% 이상
- 실제 이메일 발송 0건
- 모든 포함·제외·검토 결과에 추적 가능한 reason/evidence 존재

실제 측정 불가능한 항목은 근거와 대체 검증 방법을 기록한다.

### 8-12. DONE 기준

다음 모두 충족할 때만 `REQUEST_SOLVED = YES`:

- P0-A~D 실제 미해결분 해결 및 회귀검증 완료
- P1-A~C 실제 미해결분 해결 또는 근거 있는 `ALREADY_DONE` 판정
- dry-run/preview 사용자 E2E PASS
- 실제 메일 발송·삭제·라벨 변경 없음
- 변경 파일·테스트 결과·보안 영향·남은 리스크가 최종보고에 연결됨

---

## MAIL-017

### 8-1. 사용자 원문 요청

> 실행암호 없애

### 8-2. 비개발자용 1줄 요약

Vercel 웹 미리보기 실행 암호를 없앤다.

### 8-3. 사용자 최종 결과

- https://mail-cyan-sigma.vercel.app/run 에서 별도 실행 암호 입력 없이 미리보기를 실행한다.
- 웹 실행은 계속 dry_run=true, persist_seen=false로 유지한다.
- Vercel에서 실제 메일 발송은 기존처럼 501로 차단한다.
- 실발송용 MONITOR_SECRET 보호 로직은 삭제하지 않는다.

### 8-4. 현재상태

- TASK_ID: MAIL-017
- TASK_START_SHA: ebcbb2927ea77e406758359b03d547cb35373202
- TASK_BLOB_SHA: 07ddf4a75457f35fb4cb063af7e3a98bd69069b8
- WORK_BRANCH: feat/mail-017-remove-run-password

### 8-5. MUST

- [x] dry-run 요청은 MONITOR_SECRET 설정 여부와 관계없이 인증 없이 통과한다.
- [x] 실행 화면에서 암호 입력 UI와 Authorization 헤더 전송을 제거한다.
- [x] 실발송 요청은 기존 인증·persist_seen·Vercel 501 차단을 유지한다.
- [ ] CI 및 실제 Vercel Preview에서 암호 없는 dry-run을 확인한다.

### 8-6. KEEP

- 실제 메일 발송 금지
- dry_run=true, persist_seen=false
- GitHub Actions 실발송 경로와 Secret 정책
- 기존 수집·판정 로직

### 8-7. REMOVE

- 웹 미리보기 실행 암호 입력란
- dry-run에서의 MONITOR_SECRET 인증 요구

### 8-8. FORBIDDEN

- MONITOR_SECRET 평문 출력·커밋
- Vercel 실발송 허용
- 실제 이메일 발송
- 관련 없는 수집·판정 규칙 변경

### 8-9. VERIFY

- python -m pytest tests/test_api_run_auth.py
- 웹 빌드/CI
- Vercel Preview /run 에서 암호 입력 없이 dry-run
- 실발송 경로 501 차단 회귀 확인

### 8-10. DONE

REQUEST_SOLVED=NO — 코드 변경 완료. CI와 실제 Vercel Preview 검증 후 완료 처리한다.

---

## MAIL-018

### 8-1. 사용자 원문 요청

> 누를때마다 커밋하지말고 사이트에 한번 선택 체크한거만에 커밋
> 공고검수 사이트카테고리

### 8-2. 비개발자용 1줄 요약

공고검수 화면에서 O/X 누를 때마다 따로따로 저장하지 말고, 여러 개 고른 뒤 한 번에 저장한다.

### 8-3. 사용자 최종 결과

- `/review`(공고 검수) 화면에서 O/X를 누르면 일단 화면에만 표시(선택 상태)되고, 그 즉시 GitHub에
  커밋되지 않는다.
- 여러 건을 O/X로 선택한 뒤 "선택 저장" 버튼을 한 번 누르면, 선택한 것 전부가 한 번의 GitHub
  커밋으로 저장된다.
- 토큰이 없는 게스트 모드(pending 커밋 URL 안내)도 배치로 동작한다.
- 기존에 이미 저장된 단일 항목 pending 페이로드(`resource: "review", item: {...}`)도 계속
  처리 가능해야 한다(하위호환).

### 8-4. 현재상태

- TASK_ID: MAIL-018
- TASK_START_SHA: ea426e81512c77364b2827ef0e95831964fd1200 (origin/main)
- WORK_BRANCH: feat/mail-018-review-batch-save

### 8-5. MUST

- [ ] `web/app/review/page.tsx`: O/X 클릭은 로컬 선택 상태만 바꾸고, "선택 저장" 버튼으로만
      실제 저장(커밋) 요청을 보낸다.
- [ ] `web/app/api/review/apply/route.ts`: 여러 항목(`items: []`)을 받아 GitHub 파일을
      한 번만 읽고 한 번만 커밋한다(항목마다 별도 커밋 금지).
- [ ] `scripts/apply_admin_payload.py`의 `_apply_review()`: 토큰 없는 게스트 모드의 pending
      payload도 여러 항목을 한 번에 적용할 수 있게 하고, 기존 단일 `item` 형태도 계속 처리한다.
- [ ] 실제 이메일 발송·라벨 변경·삭제는 하지 않는다.

### 8-6. KEEP

- 기존 단일 항목 저장 payload 형태(`item`)도 계속 읽을 수 있게 한다(하위호환, REMOVE 금지).
- 검수 화면의 O/X 판정 의미·데이터 저장 위치(`data/golden/feedback_labels.jsonl`)는 그대로.
- 관리 암호(`apply` 인증) 흐름은 그대로 유지.

### 8-7. REMOVE

없음.

### 8-8. FORBIDDEN

- 실제 이메일 발송·삭제·대량 라벨 변경.
- 관련 없는 화면·API 리팩터링.
- Secret/토큰 출력.

### 8-9. VERIFY

- [x] `python -m pytest tests/test_apply_admin_payload.py` — 5건 통과(신규 배치 2건 포함)
- [x] `cd web && npx vitest run __tests__/review-apply-route.test.ts` — 신규 5건 통과
- [x] `cd web && npx vitest run` — 전체 10개 파일 43건 통과, 회귀 없음
- [x] `cd web && npx tsc --noEmit` — 통과
- [x] `cd web && npx next build` — 프로덕션 빌드 통과(`/review`, `/api/review/apply` 포함)

### 8-10. DONE

REQUEST_SOLVED=YES — `/review` 화면 O/X 클릭은 이제 로컬 선택만 바꾸고, "선택 저장" 버튼을
눌러야 실제 GitHub 커밋 1건으로 저장된다(여러 건을 골라도 커밋은 1번). 토큰 없는 게스트
모드·기존 단일 항목 pending 페이로드 하위호환도 유지. 실제 이메일 발송·라벨 변경·삭제 없음.

---

## MAIL-019

### 8-1. 사용자 원문 요청

> # Whoa there!
>
> Your request URL is too long.
>
> 공고검수후 저장시

### 8-2. 비개발자용 1줄 요약

공고검수에서 여러 건을 선택 저장해도 GitHub URL 길이 제한 오류가 나지 않게 한다.

### 8-3. 사용자 최종 결과

- `/review`에서 여러 건을 선택하고 `선택 저장`을 눌러도 GitHub `request URL is too long` 페이지가 열리지 않는다.
- 서버 GitHub 토큰이 있는 경우 기존처럼 선택한 항목 전체를 한 번의 커밋으로 저장한다.
- 토큰이 없는 GitHub-web fallback은 검수 배치 데이터를 압축해 짧은 URL로 전달한다.
- 압축 후에도 안전 길이를 넘는 예외 상황은 긴 GitHub URL을 열지 않고 화면에서 오류를 안내한다.

### 8-4. 현재상태

- TASK_ID: MAIL-019
- TASK_START_SHA: 61d4089cc3e19cd062e020f736a5959e1d302e2e
- TASK_BLOB_SHA: 6c61a8f47b9a71fdcece88d4cceeec2302be8ad8
- WORK_BRANCH: fix/mail-019-review-save-url-too-long

### 8-5. MUST

- [x] guest fallback에서 검수 배치 payload를 압축해 GitHub URL 길이를 줄인다.
- [x] apply_admin_payload.py가 압축된 review payload를 안전하게 복원·적용한다.
- [x] 기존 비압축 `items` 및 단일 `item` pending payload 하위호환을 유지한다.
- [x] URL 안전 길이 초과 시 GitHub 페이지를 열지 않고 명시적 오류를 반환한다.
- [x] 실제 이메일 발송·삭제·라벨 변경 없음.

### 8-6. KEEP

- MAIL-018의 여러 건 선택 후 한 번에 저장 UX
- `data/golden/feedback_labels.jsonl` 저장 위치
- O/X 의미와 기존 인증 흐름
- 서버 토큰이 있는 경우 한 번의 GitHub commit

### 8-7. REMOVE

- 긴 JSON 배치 payload를 그대로 GitHub URL query에 넣는 review fallback

### 8-8. FORBIDDEN

- Secret/토큰 출력 또는 코드 커밋
- 실제 이메일 발송·삭제·라벨 변경
- 관련 없는 필터/수집 로직 변경

### 8-9. VERIFY

- `python -m pytest tests/test_apply_admin_payload.py`
- `cd web && npx vitest run __tests__/review-apply-route.test.ts`
- `cd web && npx vitest run`
- `cd web && npx tsc --noEmit`
- `cd web && npx next build`
- 40건 긴 제목 guest fallback URL이 안전 길이 이하인지 회귀검증

### 8-10. DONE

REQUEST_SOLVED=YES — PR #321로 main 병합(345a2c82cc4b01db6d7edcfb5eb6ce67a050bc5b). GitHub CI 1532 passed/6 skipped, web-test 44 passed, Next.js production build PASS. Vercel Production dpl_5gGiJ2RfVCAzQY7qTYQiAVdracds READY 및 mail-cyan-sigma.vercel.app alias 반영 확인. Preview `/api/apply/status`는 github-web 모드(hasApplySecret=false, hasGithubToken=false)로 확인되어 이번 오류가 발생한 fallback 경로와 일치한다. 실제 이메일 발송·삭제·라벨 변경 없음.

---

## MAIL-020

### 8-1. 사용자 원문 요청

> Looks like something went wrong!
>
> We track these errors automatically, but if the problem persists feel free to contact us. In the meantime, try refreshing.

### 8-2. 비개발자용 1줄 요약

공고검수 저장 시 GitHub의 불안정한 본문 prefill URL을 쓰지 않고, 복사 후 정상 새 파일 화면에서 저장하게 한다.

### 8-3. 사용자 최종 결과

- 선택 저장 후 GitHub 일반 오류 화면이 자동으로 열리지 않는다.
- Vercel에 GitHub 저장 토큰이 없을 때는 검수 payload를 사이트에서 복사할 수 있다.
- GitHub는 짧은 일반 새 파일 화면만 열고, 사용자가 파일명/본문을 붙여넣어 Commit changes 한다.
- GitHub 저장 토큰이 있는 경우 기존 서버 직접 저장 1커밋 경로는 그대로 유지한다.

### 8-4. 현재상태

- TASK_ID: MAIL-020
- TASK_START_SHA: c37f388585975534affe2feb39f96c93f35cb0c0
- TASK_BLOB_SHA: 37cd24edb2170813a1587cc6795d8bffced5b534
- WORK_BRANCH: fix/mail-020-review-github-manual-fallback

### 8-5. MUST

- [ ] review guest fallback에서 GitHub URL의 `value` query를 제거한다.
- [ ] API가 복사 가능한 pending payload와 파일명을 반환한다.
- [ ] /review 화면에서 "검수 데이터 복사"와 "GitHub 저장 화면 열기"를 분리한다.
- [ ] 저장 링크는 짧은 일반 GitHub new-file URL이어야 한다.
- [ ] 서버 토큰이 있는 직접 저장 경로와 기존 pending payload 처리 하위호환 유지.
- [ ] 실제 이메일 발송·삭제·라벨 변경 없음.

### 8-6. KEEP

- MAIL-018 배치 선택 UX
- MAIL-019 gzip payload 포맷 및 Python 복원 지원
- data/golden/feedback_labels.jsonl 저장 위치
- O/X 의미와 기존 인증 흐름

### 8-7. REMOVE

- review fallback에서 GitHub 새 파일 본문을 URL query `value`로 prefill하는 동작
- fallback 결과를 즉시 window.open 하는 동작

### 8-8. FORBIDDEN

- Secret/토큰 출력 또는 코드 커밋
- 실제 이메일 발송·삭제·라벨 변경
- 관련 없는 필터/수집 로직 변경

### 8-9. VERIFY

- `cd web && npx vitest run __tests__/review-apply-route.test.ts`
- `cd web && npx vitest run`
- `cd web && npx tsc --noEmit`
- `cd web && npx next build`
- GitHub URL에 `value=` 없음 및 짧은 URL 회귀검증

### 8-10. DONE

REQUEST_SOLVED=YES — PR #323에서 긴 prefill URL을 제거했고, 후속 PR #324에서 이미 존재하는 `.apply/config-pending.json`을 GitHub 새 파일 화면이 아니라 기존 파일 편집 화면으로 열도록 수정했다. GitHub Actions web-test/docs-gate/Python test 통과 후 main에 병합했고, Production deployment `dpl_99E3bsLMW1oJr3VXKcvMzcE8rTPc`가 READY이며 stable alias `mail-cyan-sigma.vercel.app`에 반영됐다. 실제 이메일 발송·삭제·라벨 변경 및 Secret 변경 없음.

---

## MAIL-021

### 8-1. 사용자 원문 요청

> 재발방지

### 8-2. 비개발자용 1줄 요약

config-pending 임시파일과 apply-admin direct push 의존을 웹 저장 경로에서 제거해 검수·그룹·설정 저장 오류가 재발하지 않게 한다.

### 8-3. 사용자 최종 결과

- 공고검수는 최종 `data/golden/feedback_labels.jsonl`을 직접 편집한다.
- 그룹은 최종 `config/groups.json`, 설정은 최종 `config/settings.json`을 직접 편집한다.
- GitHub URL에는 본문 payload를 넣지 않는다.
- 웹 저장은 `.apply/config-pending.json` 및 `apply-admin` 성공 여부에 의존하지 않는다.
- stale `.apply/config-pending.json`은 제거한다.

### 8-4. 최종상태

- TASK_ID: MAIL-021
- IMPLEMENTATION_PR: #327
- MERGE_SHA: 15fb2513dd260dc8e514c94d0dc5db7dd9e9d834
- RESULT: config-pending 기반 저장 경로 제거 완료
- VERCEL_PREVIEW: Ready 확인
- POST_MERGE_REVIEW: 동시수정 시 stale full-file snapshot 유실 위험과 protected-main에서 Create pull request 안내 누락이 별도 발견됨
- FOLLOW_UP: MAIL-023으로 분리. MAIL-021의 원래 config-pending 재발방지 요청과 혼합하지 않는다.

### 8-5. MUST

- [x] review tokenless 저장은 최종 feedback_labels.jsonl 전체 결과를 생성해 직접 편집 링크/본문을 반환한다.
- [x] group/settings tokenless 저장은 최종 config 파일 전체 결과를 생성해 직접 편집 링크/본문을 반환한다.
- [x] URL에 `value=` payload query 및 `.apply/config-pending.json` 사용 금지.
- [x] 공고검수·그룹·설정은 공통 manual GitHub 저장 UI 사용.
- [x] stale `.apply/config-pending.json` 제거.
- [x] 기존 서버 token 직접 저장 및 legacy apply-admin 처리기는 하위호환으로 유지하되 웹 저장이 의존하지 않게 한다.
- [x] 실제 메일 발송·삭제·라벨 변경 없음.

### 8-6. KEEP

- MAIL-018 배치 O/X 선택 UX
- 기존 O/X 저장 형식과 feedback_labels.jsonl
- config/groups.json / config/settings.json 형식
- 서버 token이 있는 직접 1커밋 저장 경로
- apply-admin workflow/script는 legacy 호환용으로 유지

### 8-7. REMOVE

- 웹 저장의 config-pending 임시파일 생성/편집 의존
- config-pending 존재/미존재 분기
- config pending payload를 GitHub URL query에 넣는 경로
- stale `.apply/config-pending.json`

### 8-8. FORBIDDEN

- Secret/토큰 출력·커밋
- branch protection 우회
- 실패한 필수 체크 무시
- 실제 이메일 발송·삭제·라벨 변경
- 관련 없는 수집·판정 로직 변경

### 8-9. VERIFY

- [x] PR #327에서 review/config route가 최종 파일 경로를 사용
- [x] URL에 `value=` 및 `.apply/config-pending.json` 미사용
- [x] stale pending 파일 삭제
- [x] Vercel Preview Ready
- [x] main 병합 완료
- [ ] 동시수정 안전성 및 protected-main PR 생성 UX는 MAIL-023에서 검증

### 8-10. DONE

REQUEST_SOLVED=YES — config-pending/apply-admin direct-push 의존으로 저장이 깨지던 원래 문제는 PR #327로 제거됐다. 병합 후 발견된 수동 full-file 저장의 동시수정 안전성과 Create pull request 안내 문제는 별도 MAIL-023으로 이관한다.

---


---

## MAIL-023

### 8-1. 사용자 원문 요청

> MAIL-021 Conclusion. 남은 저장 안전 문제는 별도 후속으로 분리해 재발하지 않게 한다.

### 8-2. 비개발자용 1줄 요약

수동 저장 중 다른 변경을 지우지 않고, protected main에서도 PR 생성·병합까지 완료되게 한다.

### 8-3. 최종 결과

- 사용자가 O/X·그룹·설정을 저장하려는 사이에 원격 파일이 바뀌어도 새 데이터를 덮어쓰거나 삭제하지 않는다.
- full-file snapshot을 그대로 붙여넣는 방식이면 source SHA를 확인하고 충돌 시 최신본에 재적용하거나 REVIEW_REQUIRED로 fail-closed 한다.
- 가능하면 patch/rebase 또는 서버측 compare-and-swap(CAS) 방식으로 안전하게 적용한다.
- protected main에서 GitHub 편집 후 `Propose changes → Create pull request → Checks → auto-merge`까지 사용자가 저장 완료를 명확히 이해한다.
- 저장 완료/미완료/충돌 상태가 UI에 분명히 표시된다.

### 8-4. 현재상태

- STATUS: READY
- SOURCE: PR #327 post-merge Codex review P1/P2
- DEPENDS_ON: MAIL-021
- 실제 메일 발송·삭제·라벨 변경 없음

### 8-5. MUST

- [ ] manualContent 생성 시 source file SHA/version을 함께 반환한다.
- [ ] 저장 직전 또는 적용 시 source SHA가 최신 원격과 동일한지 확인한다.
- [ ] 원격 변경이 있으면 기존 최신 변경을 보존한 채 O/X/config patch만 재적용하거나 충돌로 중단한다.
- [ ] concurrent writer가 추가한 feedback row가 사라지지 않는 회귀테스트를 추가한다.
- [ ] protected-main 수동저장 안내에 Create pull request 단계를 포함한다.
- [ ] PR 생성 후 merge 전 상태를 저장완료로 표시하지 않는다.
- [ ] 기존 token direct-save 경로도 stale SHA 충돌을 안전하게 처리하는지 확인한다.

### 8-6. KEEP

- MAIL-021의 direct-final-file 경로
- MAIL-018 배치 O/X UX
- 기존 branch protection / CI / auto-merge
- 기존 파일 형식

### 8-7. FORBIDDEN

- 최신 원격 파일을 확인하지 않고 stale 전체 snapshot으로 덮어쓰기
- concurrent row/config 삭제
- branch protection 우회
- 실제 이메일 발송·삭제·라벨 변경
- Secret 출력

### 8-8. VERIFY

- [ ] A가 snapshot 생성 후 B가 원격 파일 수정 → A 저장 시 B 변경 보존
- [ ] feedback_labels.jsonl 동시 append 보존
- [ ] groups/settings 동시 수정 충돌 처리
- [ ] protected-main에서 Propose → PR 생성 → Checks → merge 흐름 확인
- [ ] 사용자 UI가 SAVED / PR_PENDING / CONFLICT / FAILED를 구분
- [ ] 관련 web tests + build + 실제 preview E2E

### 8-9. DONE

REQUEST_SOLVED=NO — 동시수정 데이터 보존과 PR 완료 UX를 실제 preview에서 검증한 뒤 YES.

---

## MAIL-022

### 8-1. 사용자 원문 요청

> Mail 정확도를 올리기 위해 과거 전체 판정 데이터 추출 → O/X 정답셋 통합 → 키워드별 Precision/Recall 계산 → 오탐 유발 키워드 제거 → 유효 복합키워드 추출 → Golden Set 회귀테스트 → 필터 반영 순서로 진행한다.
>
> 사용자가 직접 해야 하는 일은 접근 불가능한 운영 데이터가 있을 때 1회 export와, 자동으로 확정할 수 없는 애매한 공고의 최종 O/X 판정으로 최소화한다.
>
> 정답 데이터는 Gold / Silver / Review 3계층으로 운영하고, AI는 Gold를 임의 수정하지 않은 채 Silver·Review를 이용해 규칙을 반복 개선한다. 애매한 공고는 건별로 사용자를 중단시키지 말고 한 사이클이 끝난 뒤 배치로 모아 한 번에 검수받는다.

### 8-2. 비개발자용 1줄 요약

과거에 사용자가 실제로 O/X한 공고를 정답지로 삼아, 현재 Mail이 무엇을 잘 맞히고 무엇을 놓치는지 수치로 측정한 뒤 필터를 개선한다.

### 8-3. 사용자가 원하는 최종 결과

- 과거 O/X·검수·판정 이력을 가능한 범위에서 전수 수집해 하나의 정규화된 정답셋으로 통합한다.
- 현재 Mail 판정기를 동일 데이터에 재실행해 TP/FP/FN/TN, Precision, Recall, F1, support를 산출한다.
- FP를 많이 만드는 단어·문맥과 FN에서 반복되는 누락 신호를 자동 추출한다.
- 단일 키워드 나열보다 "키워드 + 신청자격 + 사업유형 + 문맥"의 복합 규칙을 우선한다.
- 개선 전/후 성능을 같은 고정 평가셋에서 비교하고, Golden Set 회귀테스트로 고정한다.
- 정답 데이터는 Gold / Silver / Review 3계층으로 분리한다.
  - Gold: 사용자 확정 O/X 또는 명백한 Hard Eligibility 근거가 있는 고정 정답. AI 자동 수정·삭제 금지.
  - Silver: 높은 확신도의 자동 판정 후보. 반복개선·분석에는 사용 가능하지만 Gold로 자동 승격 금지.
  - Review: 충돌·불확실·신규 유형. 사용자 검수 대상.
- AI는 Gold를 기준으로 후보 규칙을 반복 생성·검증하고, 동일 holdout에서 성능이 개선되는 규칙만 채택한다.
- 성능이 악화되거나 기존 Gold 회귀가 생기면 후보 규칙을 폐기/롤백한다.
- 사용자는 자동 판정이 불가능한 Review 사례만 O/X로 확인하되, 건별 요청이 아니라 한 분석 사이클 종료 후 한 번에 묶어서 검수한다.
- 실제 메일 발송 없이 dry-run/fixture/검수 데이터로 정확도를 검증한다.

### 8-4. 현재상태

- TASK_ID: MAIL-022
- STATUS: READY
- WORK_BRANCH: 실행 시 새 task 브랜치 생성
- BASELINE: 실행 시작 시 origin/main과 현재 O/X 데이터 기준으로 새로 측정
- 실제 이메일 발송·삭제·라벨 변경은 하지 않는다.

### 8-5. MUST — 반드시 구현

- [ ] 데이터 위치 전수조사: `data/golden/feedback_labels.jsonl`, 관련 fixture/test data, 과거 Git 이력, 기존 accuracy/feedback 산출물, 저장 가능한 검수 로그를 조사한다.
- [ ] 같은 공고의 중복 O/X, 수정공고, 재공고, 제목변형을 정규화하고 충돌 라벨은 자동 덮어쓰지 않고 REVIEW_REQUIRED로 분리한다.
- [ ] 과거 라벨을 최소 `notice_id/source/title/url/label/reason/date` 단위로 정규화한다. 신규 라벨은 `group_id`와 판정 당시의 그룹/기업 프로필·설정 snapshot 식별정보를 함께 보존한다. 없는 필드는 null/unknown으로 남기고 추측하지 않는다.
- [ ] legacy O/X에 group context가 없으면 전체 공통 분석에는 사용할 수 있어도 그룹별 ground truth로 임의 재사용하지 않는다. 그룹별 Precision/Recall 계산에는 group_id/profile snapshot이 확인되는 라벨만 사용한다.
- [ ] 현재 판정기를 정답셋에 재실행하여 TP/FP/FN/TN 및 Precision/Recall/F1/support를 전체·그룹·주요 카테고리별로 산출한다.
- [ ] 키워드/복합문맥별 TP/FP/FN 기여도를 집계한다. 표본 수가 너무 적은 신호는 자동 규칙 변경 근거로 사용하지 않는다.
- [ ] FP 원인코드를 최소 신청자격 불일치/지역 불일치/업력 불일치/단순교육·행사/입주공간 단독/관심분야 불일치/중복·재공고/기타로 분류한다.
- [ ] FN에서 반복되는 유효 신호와 동의어·복합표현을 추출하고, Hard Eligibility보다 앞서 키워드가 통과시키는 구조를 만들지 않는다.
- [ ] 분석용 데이터와 최종 평가용 고정 holdout을 분리해 같은 데이터로 튜닝하고 성능을 주장하는 leakage를 방지한다.
- [ ] Gold / Silver / Review 3계층 데이터셋을 구현한다. Gold는 사용자 확정값 또는 명백한 Hard Eligibility 근거에 의한 고정 정답으로 취급하고 AI가 자동으로 수정·삭제·재라벨링하지 않는다.
- [ ] Silver는 높은 확신도의 자동판정 후보로 관리하되 Gold로 자동 승격하지 않는다. Review는 충돌·경계·신규 유형을 모으는 사용자 검수 큐다.
- [ ] 반복개선 루프를 구현한다: baseline → FP/FN 분석 → 후보 복합규칙 생성 → Gold/holdout 검증 → 성능 개선 후보만 채택 → 재측정. 성능 저하 또는 Gold 회귀 발생 시 후보를 폐기/롤백한다.
- [ ] Golden Set 회귀테스트를 추가해 대표 TP/FP/FN 경계사례가 향후 변경에서 다시 깨지지 않게 한다.
- [ ] Review는 공고 1건마다 사용자에게 질문하지 않는다. 분석 사이클이 끝날 때까지 누적한 뒤 한 번의 배치 검수 화면/목록으로 제공하고, 사용자가 O/X를 연속 처리한 결과를 한 번에 저장·반영한다.
- [ ] 필터 반영은 기존 evaluator/filter 구조를 재사용하고 최소 변경으로 수행한다. 기존 정상 TP를 떨어뜨리는 규칙은 근거 없이 반영하지 않는다.
- [ ] 변경 전/후 동일 holdout 기준 성능표를 생성한다.
- [ ] 운영 데이터가 GitHub 밖에 있어 접근할 수 없는 경우 그 부분만 명확히 BLOCKED_INPUT으로 기록하고, 사용자가 해야 할 export 작업을 파일명·형식·1회 절차로 최소화한다.
- [ ] 애매한 공고는 `REVIEW_REQUIRED` 목록으로 따로 만들고 사용자에게 최종 O/X만 요청할 수 있게 한다.
- [ ] 세션 중단·컨텍스트 만료·PC 종료 후에도 이어서 할 수 있도록 단계별 CHECKPOINT를 남긴다. 최소 단계는 DATA_AUDIT / BASELINE / DATASET_SPLIT / CANDIDATE_RULES / GOLDEN_TEST / REVIEW_BATCH / FINAL_COMPARE 이며, 각 단계 완료 시 작업 브랜치에 필요한 파일만 커밋·push한다.
- [ ] 재실행은 idempotent해야 한다. 같은 입력 snapshot/run_id로 다시 실행해도 Gold 중복 추가, Review 중복 누적, 지표 이중계산, 규칙 중복적용이 발생하지 않아야 한다.
- [ ] 입력 데이터 fingerprint와 evaluator/config commit SHA를 기록해 어떤 데이터·코드 기준으로 나온 지표인지 재현 가능하게 한다.
- [ ] 반복개선은 무한 루프 금지. 한 실행에서 최대 5 cycle, 또는 2회 연속 holdout F1 개선이 0.5%p 미만이면 자동 종료하고 남은 항목을 다음 실행으로 넘긴다.
- [ ] 후보 규칙은 가능하면 각각 독립적으로 평가·기록한다. 후보 하나가 테스트/성능 기준을 깨면 그 후보만 폐기하고 이미 검증된 checkpoint까지 되돌리지 않는다.
- [ ] 원격 main 변경, CI 실패, 외부 사이트 오류, 일부 데이터 누락 등 부분 장애가 발생해도 안전하게 가능한 분석은 계속하고, 정말 필요한 입력/결정만 HUMAN_BATCH에 누적한다.
- [ ] 실제 이메일 발송·실제 라벨 변경·실제 삭제·Secret 출력은 하지 않는다.

### 8-6. KEEP — 유지

- 마감·지역·업력·사업자 상태 등 기존 Hard Gate 우선 원칙
- unknown을 임의로 부적격 처리하지 않는 recall 우선 정책
- MAIL-015에서 복원한 과거 필터 기준과 reason_code
- MAIL-018~021의 O/X 검수 데이터 의미와 저장 형식
- 기존 수집기·중복제거·메일 발송 구조
- 사용자 판정이 이미 존재하는 O/X는 가장 중요한 Gold 정답 근거로 사용하되, 충돌·오입력 가능성은 REVIEW_REQUIRED로 분리
- Gold 정답의 불변성: AI 반복개선 과정에서 자동 변경·자동 삭제·자동 승격으로 덮어쓰지 않음
- 신규 라벨의 group_id 및 판정 당시 profile/config context 보존

### 8-7. REMOVE — 제거/완화 후보

- 과거 데이터에서 반복적으로 FP를 만드는 것이 충분한 표본으로 확인된 단독 키워드·과도한 boost 규칙
- 동일 의미의 중복 키워드/규칙
- Hard Eligibility를 우회해 관련성 키워드만으로 적합 처리되는 경로

단, REMOVE는 분석 결과와 회귀검증 근거가 있을 때만 수행한다. 단순 빈도만으로 기존 규칙을 삭제하지 않는다.

### 8-8. FORBIDDEN — 금지

- O/X 정답 없이 AI 추측만으로 과거 공고 라벨을 Gold로 확정하지 않는다.
- Silver를 AI가 스스로 Gold로 자동 승격하지 않는다.
- Review 공고를 건별로 사용자에게 계속 질문해 작업을 중단시키지 않는다. 배치 검수가 원칙이다.
- 분석에 사용한 전체 데이터를 그대로 최종 성능 검증셋으로 사용하지 않는다.
- 1~2건의 사례만 보고 키워드/Hard Gate를 추가·삭제하지 않는다.
- Precision만 높이기 위해 Recall을 크게 희생하거나, 반대로 Recall만 높이기 위해 FP를 무제한 허용하지 않는다.
- 사용자 프로필을 코드에 하드코딩하지 않는다. 그룹/회사 설정 구조를 사용한다.
- 기존 정상 판정 경로를 대규모 리팩터링하지 않는다.
- 실제 메일 발송·삭제·라벨 변경을 하지 않는다.
- `.env`, 토큰, 메일 원문 개인정보를 출력·커밋하지 않는다.

### 8-9. 선행조건·의존성

DEPENDS_ON: MAIL-015, MAIL-021, MAIL-023 (MAIL-023 저장 안전성 완료 후 정확도 반복개선 실행)

실행 우선순위:
1. 데이터 위치/완전성 조사
2. O/X 정답셋 정규화
3. 현재 baseline 측정
4. FP/FN 원인분석
5. 유효 키워드·복합문맥 후보 도출
6. Golden Set/holdout 고정
7. 필터 최소 변경
8. 동일 holdout 재측정
9. 실제 사용자 관점 dry-run 검증

### 8-10. 구현범위

- 분석 스크립트/리포트: O/X history → normalized labels → confusion matrix → keyword/context stats
- Gold / Silver / Review 데이터 계층 및 반복개선 루프
- Golden Set 및 회귀테스트
- 필요 최소 범위의 evaluator/filter/config 수정
- 애매한 사례 REVIEW_REQUIRED 배치 큐 및 일괄 O/X 반영
- 신규 라벨 group_id + profile/config snapshot 보존
- 성능 전후 비교 리포트 및 성능 악화 시 후보 규칙 롤백/폐기
- 단계별 checkpoint + 재개 상태(run_id, input fingerprint, code/config SHA, 완료 phase, 다음 phase)
- 동일 입력 재실행 안전성(idempotency)과 중복 방지

구체 파일 경로는 실행 시 현재 main 구조를 조사한 뒤 기존 구조를 우선 재사용한다. 불필요한 새 프레임워크는 만들지 않는다.

### 8-11. 정확도 지표

필수 보고:
- 전체 labeled sample 수
- O/X 비율
- TP / FP / FN / TN
- Precision
- Recall
- F1
- 중복률
- REVIEW_REQUIRED 건수
- 주요 FP/FN reason_code별 건수
- 키워드/복합문맥별 support와 Precision

목표:
- 먼저 현재 baseline을 실제 데이터로 확정한다.
- 충분한 표본이 있는 범위에서 Precision/Recall 각각 95% 이상을 지향한다.
- 목표 미달이어도 수치를 숨기지 않고 원인과 남은 FN/FP를 보고한다.
- 명백한 신청자격 Hard Gate 오판은 0건을 목표로 한다.

### 8-12. 사용자 개입 최소화

정상적인 정확도 개선 흐름에서 사용자에게 요청 가능한 것은 아래 두 종류로 제한한다.

1. GitHub/현재 실행환경에서 접근할 수 없는 운영 O/X 데이터가 있을 경우 1회 export
2. 자동 확정할 수 없는 REVIEW_REQUIRED 공고의 최종 O/X 판정

예외: 데이터 손실 위험, 보안/Secret, 실제 비용 발생, 되돌리기 어려운 운영 변경, 제품정책 변경은 안전을 위해 즉시 사용자 승인을 요청할 수 있으며 위 2종 제한의 예외로 본다.

사용자 개입 방식:
- 공고 1건마다 질문하지 않는다.
- 한 분석/개선 사이클 동안 REVIEW_REQUIRED를 계속 누적한다.
- 사이클 종료 시 가능한 한 전체 Review를 한 화면/목록으로 한 번에 제공한다.
- 사용자는 각 행에서 O/X만 연속 선택하고 마지막에 1회 저장한다.
- 저장 결과를 Gold에 반영한 뒤 다음 자동 개선 사이클을 진행한다.
- 새 Review가 소수 발생하더라도 즉시 호출하지 않고 다음 배치까지 누적하는 것을 기본으로 한다.
- Review가 많아도 사용자 호출 횟수를 늘리지 않는다. 중복/동일공고/동일 canonical notice를 먼저 제거하고, UI 내부 pagination·필터·일괄 O/X를 사용하되 마지막 저장은 1회로 유지한다.
- 사용자에게 보여줄 HUMAN_BATCH에는 개발자가 알아서 해결할 수 있는 오류·테스트 실패·Git 상태를 넣지 않는다. 사용자의 판단 또는 외부 입력이 실제로 필요한 항목만 넣는다.
- 개발 중 선택지가 여러 개여도 기존 구조·테스트·데이터 근거로 안전하게 결정할 수 있으면 AI가 스스로 결정하고 계속 진행한다.
- 조사·분석·코드수정·테스트·회귀검증·문서화·PR 생성·Checks 확인·허용된 자동병합까지 가능한 범위는 AI가 연속 수행한다.
- 중간 진행상황 확인을 위해 사용자를 반복 호출하지 않는다. 사용자에게 필요한 결정·검수·입력은 가능한 한 하나의 배치로 합친다.
- 사용자 개입이 필요한 항목은 누적하여 `HUMAN_BATCH`로 한 번에 제시하고, 각 항목에 추천 기본값·영향·필요한 선택만 짧게 표시한다.
- 단, 명백한 데이터 손실 위험, 보안/Secret, 비용이 발생하는 외부 실행, 되돌리기 어려운 운영 변경, 제품정책을 바꾸는 결정만 즉시 중단 요청할 수 있다.

키워드 후보 추출, 통계 계산, 후보 규칙 생성, Golden Set/holdout 검증, 성능 전후 비교, 성능 악화 후보 폐기뿐 아니라 구현·테스트·회귀검증·PR까지 가능한 범위는 자동화한다.

### 8-13. VERIFY

- [ ] 전체 정답셋 건수와 중복/충돌 처리 결과 확인
- [ ] baseline confusion matrix 재현 가능
- [ ] keyword/context 통계에 support 포함
- [ ] train/analysis와 fixed holdout 분리 확인
- [ ] 대표 TP/FP/FN Golden Set 회귀테스트 PASS
- [ ] Gold 자동변경/삭제/승격이 불가능한지 검증
- [ ] Silver/Review 분리와 Review 일괄 저장 동작 검증
- [ ] 신규 라벨에 group_id + profile/config context가 보존되고 legacy context 없는 라벨이 그룹별 지표에서 제외되는지 검증
- [ ] 후보 규칙 적용 후 holdout 성능 악화 또는 Gold 회귀 시 자동 채택되지 않는지 검증
- [ ] 중간 강제종료 후 최신 remote checkpoint에서 중복 없이 재개되는지 검증
- [ ] 동일 run/input을 2회 실행해 Gold/Review/지표/규칙이 중복 생성되지 않는지 검증
- [ ] 최대 5 cycle 및 2회 연속 개선 <0.5%p 자동 종료 조건 검증
- [ ] main 변경/CI 실패/외부 데이터 일부 누락 시 안전한 부분 작업은 보존되고 HUMAN_BATCH에는 실제 사용자 필요 항목만 남는지 검증
- [ ] 기존 관련 테스트 PASS
- [ ] 개선 전/후 동일 holdout 성능 비교
- [ ] 실제 메일 발송 없음
- [ ] Secret/개인정보 노출 없음
- [ ] 실제 사용자 dry-run에서 적합/부적합/검토필요 결과와 근거 확인

### 8-14. DONE

REQUEST_SOLVED=NO — 계획 등록 상태. 데이터 전수조사·baseline 측정·FP/FN 분석·Golden Set 구축·필터 반영·동일 holdout 재검증, 중단/재개·idempotency 검증이 완료되고 실제 사용자 dry-run이 PASS일 때만 YES로 변경한다.

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
11. `# 7-A. 모든 TASK 공통 안전장치`를 자동 상속시킨다.
12. TASK 특성상 필요한 추가 안전장치(checkpoint/resume, idempotency, bounded retry, rollback, HUMAN_BATCH, dry-run, reproducibility)를 DETAILS에 보강한다.
13. 전역 안전장치를 약화하거나 예외 처리하려면 사용자의 명시적 요청과 이유를 TASK에 기록한다.

새 TASK를 만들 때 전역 안전장치 문구를 매번 장황하게 복사할 필요는 없다.
대신 해당 TASK가 어떤 추가 안전장치를 요구하는지 VERIFY/DONE에 필요한 범위만 구체화한다.

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
