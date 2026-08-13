<!-- BEGIN OPS HEADER: 실행 게이트. 본문보다 우선. -->

# TASK.md — 이 레포 실행 단일 기준

```text
REPO:   pds2225/mail
REMOTE: https://github.com/pds2225/mail.git
BASE:   main
```

## 0. STOP 게이트 (하나라도 실패 → 코드 수정 금지, 즉시 중단)

아래를 **맨 처음** 실행한다. 실패하면 구현하지 않는다.

1. `git fetch --all --prune`  
   - 실패 → **STOP**. 로컬에 있는 옛 TASK로 진행 금지.
2. `git remote get-url origin`  
   - 위 `REMOTE`와 **문자 완전 일치**가 아니면 **STOP**. (다른 레포/worktree 오실행 방지)
3. 실행 파일은 **이 `TASK.md`만**.  
   - `NEXT_TASK.md` / 다른 레포 TASK / 옛 채팅 / AGENTS 외 지시서로 구현 시작 → **STOP** 로그 남기고 중단.  
   - `NEXT_TASK.md`는 큐·참고다. TASK가 “읽어라”고 쓰지 않으면 열지 마라.
4. 허용 범위: 이 파일 + 이 파일이 지명한 코드/테스트/문서.  
   - 지명되지 않은 레포·폴더를 고치기 시작하면 **STOP**.
5. Must 순서: 아래 TRACK에 `depends_on`이 있으면 **선행 TRACK이 DONE일 때만** 후속 TRACK 착수.  
   - 선행 미완료인데 후속 파일을 열면 **STOP**.
6. DONE 금지 (하나라도 해당하면 FAIL, 머지 금지):  
   - 구현 코드 diff 없이 **테스트/픽스처만** 변경  
   - 지정 **smoke 산출물 파일** 없음  
   - 보고에 **커밋 SHA + 실행한 명령 + 테스트 요약 원문(10줄 이내)** 없음
7. `AGENTS.md`와 이 TASK가 충돌:  
   - 코드 수정 중단. `BLOCKED_WITH_EVIDENCE`만 남긴다.  
   - 사용자에게 선택지 3개만: `예외 승인` / `우회(다른 파일)` / `보류`. 선택 전 코드 금지.
8. 머지: 이 TASK 본문이 머지를 **명시**한 경우에만. 그래도 아래 아니면 merge 명령 실행 금지.  
   - GitHub Checks **초록**  
   - 필수 테스트 job 통과  
   - 6번 DONE 금지 항목 없음  
   - 충돌 미해결이면 머지 금지
9. 로컬 dirty / 다른 브랜치: 기본 브랜치(`BASE`)에서 직접 수정 금지. **새 브랜치**에서만 작업.
10. 시크릿: 값은 `D:\_secure\.env.shared`만. TASK에는 키 이름만.  
    시작 시 `D:\_secure\sync.ps1 check` (원격이 앞설 때만 pull). 키를 바꿨으면 `push`.

## 우선순위

1. 사용자 요청  
2. 그중 **가장 최신** 요청  
3. 데드라인 / 막힘 / 버그  

Must = 지금 안 하면 막히거나, 데드라인이거나, 버그이거나, **사용자 요청**인 것.

## 하다 만 작업

브랜치 유지 + 이 파일에 체크포인트 한 줄 (`어디까지 했는지`). 기본 브랜치에 미완성 커밋 금지.

## 최종 보고 최소 항목

```text
REPO: (origin URL)
SHA: (구현 커밋)
CMD: (테스트/smoke 명령)
SMOKE: (산출물 경로 또는 N/A 이유)
TEST: (요약 원문 10줄 이내 붙여넣기)
DIFF: (구현 파일 목록 — 테스트만이면 FAIL)
STATUS: DONE | BLOCKED_WITH_EVIDENCE | FAIL
```

<!-- END OPS HEADER -->

---

# TRACK 순서 (mail)

| TRACK | 상태 | 내용 | 착수 조건 |
|-------|------|------|-----------|
| A | Must | POST-MERGE HOTFIX (#245/#246 P1/P2) | 즉시 |
| B | Must | 공고 안내 이메일 8컬럼 표 | **A = DONE 일 때만**. A 미완료면 B 코드 열지 말 것 → STOP |

A smoke 산출물: `docs/POST_MERGE_HOTFIX_RESULT_20260812.md` + monitor dry-run 로그 파일.
B smoke 산출물: 생성된 HTML 이메일 파일 1개 이상 저장.

---

# TRACK B — 공고 안내 이메일 표 형식 개편

> depends_on: TRACK A = DONE  
> A가 DONE이 아니면 이 섹션은 읽기만 하고 구현하지 마라.

## 목표

현재 공고 안내 이메일의 공고 목록을 아래 8개 컬럼 표로 변경한다.

상태 → 적합 → 공고 → 지원 → 대상 → 기관 → 지역 → 마감

기존 공고 수집·중복제거·매칭·발송 로직은 유지하고, **이메일 렌더링과 필요한 데이터 매핑만** 최소 수정한다.

## 최종 이메일 표

| 상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감 |
|------|------|------|------|------|------|------|------|
| 🆕 D-8 🟠 | 지원가능 | 2026년 수출바우처 참여기업 모집 | 최대 7,000만원 해외마케팅 | 수출 중소기업 | 중기부 | 전국 | 8/20 |
| D-13 🟢 | 지원가능 | 해외전시회 개별참가 지원 | 부스비·운송비 | 중소기업 | KOTRA | 전국 | 8/25 |
| D-6 🟠 | 확인필요 | AI 제조혁신 기술개발 | R&D 최대 2억원 | 제조 중소기업 | 중기부 | 전국 | 8/18 |

## 컬럼 정의

### 1. 상태
마감일까지 남은 기간. 예: `🆕 D-2 🔴` / `D-6 🟠` / `D-15 🟢` / `마감`  
기존 D-Day 로직이 있으면 재사용. 🆕는 기존 신규공고 판정값이 있을 때만. 임의 추정 금지.

### 2. 적합
허용값만: `지원가능` / `확인필요` / `대상아님`  
기존 매칭 점수·판정 로직 변경 금지. UI 표시값만 매핑. 정보 부족이면 `확인필요`.

### 3. 공고
제목 표시 정책 유지. 바로가기 컬럼 만들지 않음. 공고명 자체를 원문 URL 하이퍼링크.  
원문 URL 없으면 일반 텍스트. 링크 오류 만들지 말 것.

### 4. 지원
핵심 지원내용 짧게. 우선순위: 지원금/사업비 → 바우처 → 비용지원 → 시설/입주 → 판로/실증 → 기타.  
원문에 없으면 `확인필요`. 임의 금액/혜택 생성 금지.

### 5. 대상
핵심 신청대상 짧게. 없으면 `확인필요`.

### 6. 기관
주관/공고 기관명. 기존 데이터 있으면 그대로. 임의 약칭 금지.

### 7. 지역
예: 전국/서울/인천/경기/부산. 제한 없으면 전국. 판단 불가면 `확인필요`.

### 8. 마감
짧게 `8/20`. 연도가 현재와 다르면 `2027/1/15`.

## 제거할 항목 (이메일 UI만)

추천이유 컬럼 / 바로가기 컬럼 / 사이트명 컬럼.  
사이트명·출처 **데이터는 삭제하지 않음** (수집·추적·로그 유지).

## 필수 상태 처리

- 빈값: 이메일 생성 실패 금지. 표시는 `확인필요`. 공고명 자체 없음은 기존 오류 정책.
- 링크 없음: 공고명 일반 텍스트.
- 공고 0건: 빈 `<table>` 금지. 기존 문구 유지, 없으면 `현재 조건에 맞는 신규 공고가 없습니다.`
- 오류: 한 공고 일부 필드 오류로 전체 발송 실패 금지. 해당 필드만 fallback.
- 모바일: 컬럼 순서 변경 금지. 셀에 긴 설명 넣지 말 것. 신규 UI 라이브러리 금지. 공고명 링크 클릭 가능.

## 수정 금지

공고 수집 소스, 크롤러, 중복제거, 포함/제외 정책, 그룹 매칭, LLM 판정 기준, 발송 스케줄, 수신자, DB 구조, 공고 원문 데이터. 불필요 리팩터링 금지.

## 테스트

정상 1건 / 여러 건 / 🆕 / D-Day / 지원가능 / 확인필요 / 대상아님 / URL 있음(링크) / URL 없음(텍스트) / 지원·대상·지역 없음 / 0건 / 일부 필드 오류 / 기존 발송 regression.  
생성된 HTML 저장 또는 테스트에서 확인.

## TRACK B 완료 조건

8컬럼 정확. 공고명 클릭 시 원문. 추천이유/바로가기/사이트명 컬럼 없음. 빈값·0건 정상. 매칭·발송 로직 변화 없음. 관련 테스트 PASS. 전체 regression PASS. smoke HTML 파일 존재.

이 TRACK만 수행하고 다른 기능으로 확장하지 마라.

---

# CURRENT AI TASK — MAIL / POST-MERGE HOTFIX

> 이 파일은 `pds2225/mail`의 현재 AI 작업지시 단일 기준이다.
> 항상 원격 `main/TASK.md`를 처음부터 끝까지 읽고 작업한다.

## 상황

PR #245와 #246은 이미 main에 병합되었다.

- #245 merge commit: `dc137a3721e17ec8f942b6afe4e6618933d04475`
- #246 merge commit: `193e989474e89e4df0e11bceed553a8d5d23e7f0`

병합 후 자동리뷰에서 P1/P2 결함과 테스트 결과 불일치가 확인되었다.
따라서 지금 목표는 **되돌리기보다 최신 main 기준 즉시 hotfix**다.

## 실행 원칙

- 사용자에게 묻지 않는다.
- 가능한 수정/테스트/조사는 병렬로 진행한다.
- 한 항목이 막히면 BLOCKED로 남기고 다음 항목을 계속한다.
- 실제 이메일/ntfy 발송 금지. preview/dry-run/mock만 사용.
- force push, reset --hard, git clean -fd, secret/.env 수정 금지.
- main에서 직접 개발하지 말고 최신 main에서 새 hotfix branch 생성.
- PR 생성까지 가능하지만 main 자동병합 금지.
- 저장소 `AGENTS.md`를 먼저 읽고 보호규칙을 지켜라. `monitor.py` 수정 금지 규칙과 이번 hotfix가 충돌하면 임의로 무시하지 말고, 가능한 우회 구조를 우선 검토하고 불가능한 경우 `BLOCKED_WITH_EVIDENCE`로 기록한다.

권장 브랜치:

`fix/post-merge-245-246-hotfix`

---

# HOTFIX P1 — fetch_all `_fetch_outcomes` NameError

현재 리뷰 지적:

- `fetch_all()`이 `_fetch_outcomes`를 참조하지만 해당 이름은 `execute_monitor()` 로컬에만 존재.
- 정상 fetch 완료 시 `NameError`가 발생하고 collection이 중단될 수 있음.

요구:

- outcome collector를 명시적 인자로 전달하거나 동등한 안전한 구조로 수정.
- 기존 public call 호환 유지.
- 성공/실패 source별 outcome을 실제 source health가 읽을 수 있게 연결.
- 성공 path, 실패 path, mixed source path 테스트 추가.

---

# HOTFIX P1 — `source_stats` 초기화 전 사용

현재 리뷰 지적:

- `dedup_items(..., _stats=...)`에서 `source_stats` 생성 전에 `_stats["source_contribution"] = source_stats`를 실행하여 `UnboundLocalError` 가능.

요구:

- source contribution 계산 후 stats export.
- nonempty dedup path 실제 실행 테스트 추가.
- KPI total과 세부 removal count가 reconcile되는지 검증.

---

# HOTFIX P1 — 전체 source 실패 시 source-health 누락

현재 리뷰 지적:

- 모든 source가 실패하면 `fetch_all()` 결과가 empty가 되고 `no_items` early return이 source-health 처리보다 먼저 발생할 수 있음.
- 가장 중요한 total outage가 health/incidents에 기록되지 않을 수 있음.

요구:

- empty-result return 전에 fetch outcomes 기반 source-health 반영.
- bizinfo/kstartup 모두 실패 시 FAILING/incident 기록 테스트.
- 실제 alert는 mock.

---

# HOTFIX P1 — accuracy 허위 MEASURED 방지

현재 리뷰 지적:

- `feedback_labels.jsonl`의 tracked rows가 title/description 없이 ID/verdict만 가진 경우가 있음.
- 빈 notice를 평가하고 `MEASURED` TP/TN/FN을 계산하면 잘못된 측정.

요구:

- ID를 실제 stored notice snapshot/raw corpus와 join할 수 있으면 join.
- feature를 복원할 수 없으면 해당 benchmark는 `NOT_MEASURABLE`.
- featureless feedback row를 절대 유효 accuracy sample로 계산하지 말 것.
- TP/FP/TN/FN/precision/recall/F1은 실제 relevance truth + 실제 notice feature가 모두 있을 때만 계산.
- 회귀테스트 추가.

---

# HOTFIX P1 — #246 보고서의 허위 테스트 통과 수정

자동리뷰에서 `tests/test_version_delivery_integration.py`가 보고서상 7 PASS와 달리 실제 해당 commit에서 실패가 확인되었다.

지적 예시:

- version fixture가 기대 change가 아니라 `NEW`
- outbox test가 keyword-only `upsert()`를 positional dict로 호출
- return-contract test가 early return에 없는 field를 기대

요구:

1. 실제 최신 main에서 해당 테스트 파일을 직접 실행.
2. 실패가 재현되면 테스트/구현 중 무엇이 잘못인지 판별.
3. 테스트를 억지로 기대값 변경/skip하지 말 것.
4. 수정 후 동일 테스트 재실행.
5. 결과보고서의 PASS/FAIL 수치를 실제 결과로 정정.
6. 전체 관련 테스트를 다시 실행.

---

# HOTFIX P2 — dedup KPI replacement branch 누락

현재 리뷰 지적:

- incoming primary-source item이 기존 aggregator를 교체하는 경우 출력 item 수는 1건 줄었는데 removal counter가 증가하지 않을 수 있음.

요구:

- discard incoming / replace existing 두 경우 모두 실제 제거 1건으로 정확히 계측.
- `duplicate_removed_total == mechanism counts의 정의상 합계`가 맞는지 검증.
- double-count 금지.

---

# HOTFIX P2 — yearless title 비교 누락

현재 POSSIBLE_DUPLICATE 최적화가 year bucket을 분리해:

- `2026 ...`
- 동일 제목이지만 연도 없는 버전

을 아예 비교하지 않을 수 있음.

요구:

- 서로 다른 명시 연도(2025 vs 2026)는 계속 분리.
- 한쪽에만 연도가 있는 경우는 비교 후보에서 제외하지 않도록 설계.
- 성능 최적화는 유지하되 recall 저하 방지.
- regression test 추가.

---

# 통합 검증

위 항목을 가능한 병렬로 수정한 뒤 다음을 반드시 실행:

1. targeted tests for fetch outcomes/source health/dedup/accuracy
2. `tests/test_version_delivery_integration.py`
3. prestartup regression tests
4. monitor import/smoke dry-run
5. 가능하면 전체 `python -m pytest tests/ -q --tb=short`

Windows temp/cp949 PermissionError가 나면 코드 결함과 환경 결함을 분리해서 증거를 남긴다.

## 결과 보고

새 보고서:

`docs/POST_MERGE_HOTFIX_RESULT_20260812.md`

반드시 포함:

- 시작 main SHA
- 수정한 P1/P2 목록
- 실제 재현 여부
- 변경 파일
- 테스트 명령과 정확한 pass/fail 수
- pre-existing/environment failures
- BLOCKED
- commit 목록
- PR URL
- main 미병합 확인

상태는:

`IMPLEMENTED / TESTED / REAL_DATA_VALIDATED / BLOCKED`

만 사용.

## 최종 지시

지금부터 최신 main을 기준으로 위 P1을 최우선으로 전부 수정하고, 이어서 P2까지 처리한다.
사용자 입력을 기다리지 말고 테스트→수정→재테스트→자체리뷰→commit→push→PR 생성까지 진행한다.
