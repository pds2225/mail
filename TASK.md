# TASK.md — 이 레포 실행 단일 기준

```text
REPO: pds2225/mail
BASE: main
```

## 0. Git 동기화·STOP 게이트
1. `git fetch --all --prune`.
2. origin/branch/dirty 상태 확인.
3. `git rev-list --left-right --count HEAD...origin/main`으로 ahead/behind/diverged 확인.
4. 현재 `main`이 clean이고 `ahead=0, behind>0`일 때만 `git merge --ff-only origin/main`으로 최신화.
5. dirty/ahead/diverged/다른 브랜치 로컬 전용 변경은 보존. 삭제·덮어쓰기·자동 reset 금지.
6. `git reset --hard`, force push, `git clean -fd`, 임의 stash/drop 금지.
7. 로컬 변경이 있으면 최신 `origin/main` 기준 별도 branch/worktree에서 작업. 안전 분리 불가 시 `BLOCKED`.
8. 이 `TASK.md`만 실행. 다른 레포 TASK/NEXT_TASK/옛 채팅 과업 금지.
9. 실제 이메일/ntfy 발송 금지. preview/dry-run/mock만 사용.
10. 구현 → 테스트 → commit → push → PR까지 가능. 이 TASK는 main 자동병합을 허용하지 않는다.

# CURRENT TASK — 안정성 확인 후 공고 이메일 표 개편

## 목표
1. 기존 post-merge P1/P2 결함이 최신 main에 남아 있는지 재현 확인하고, 남아 있으면 최소 hotfix한다.
2. 공고 안내 이메일 표를 아래 8개 컬럼으로 개편한다.

```text
상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감
```

공고명 자체를 원문 링크로 만들고 `추천이유 / 바로가기 / 사이트명` 컬럼은 제거한다. 기존 수집·중복제거·매칭·발송 정책은 변경하지 않는다.

## 현재상태
기존 TASK에는 PR #245/#246 이후 P1/P2 hotfix가 등록돼 있었다. 최신 main에서 이미 해결됐을 수 있으므로 문서만 믿지 말고 실제 테스트로 재현한다.

확인 대상 기존 hotfix:
- fetch outcome scope/NameError
- source_stats 초기화 순서
- 전체 source 실패 source-health 누락
- featureless feedback의 허위 `MEASURED`
- `tests/test_version_delivery_integration.py` 실제 실패 여부
- dedup replacement KPI 누락
- yearless title duplicate recall

최신 사용자 요구:
```text
상태 → 적합 → 공고 → 지원 → 대상 → 기관 → 지역 → 마감
```

## 구현범위
### TRACK A — 기존 P1/P2 재현검증
- 최신 main에서 기존 targeted tests와 `tests/test_version_delivery_integration.py` 실행.
- 이미 해결됐으면 코드 수정 없이 `ALREADY_FIXED` 근거 기록.
- 재현되는 항목만 최소 수정하고 regression test 추가.
- 실제 alert/email 발송 금지.

### TRACK B — 이메일 표 개편
최종 컬럼과 순서는 정확히:
```text
상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감
```

#### 상태
- 기존 D-Day 로직 재사용.
- 예: `🆕 D-2 🔴`, `D-6 🟠`, `D-15 🟢`, `마감`.
- `🆕`는 기존 신규 판정 데이터가 있을 때만.

#### 적합
표시값은 아래 3개만:
```text
지원가능
확인필요
대상아님
```
- 기존 매칭 로직/점수 계산은 변경하지 않는다.
- 정보 부족은 `확인필요`.

#### 공고
- 공고명을 원문 `source_url` 하이퍼링크로 표시.
- 별도 `바로가기` 컬럼 금지.
- URL 없으면 일반 텍스트.

#### 지원
기존 데이터/원문에서 확인된 핵심 지원내용만 짧게 표시.
우선 예:
- 지원금/사업비
- 바우처
- 비용지원
- 시설/입주
- 판로/실증
- 기타 핵심지원
확인 불가 시 `확인필요`. 임의 금액 생성 금지.

#### 대상
핵심 신청대상을 짧게 표시. 확인 불가 시 `확인필요`.

#### 기관
기존 주관/공고기관 데이터 사용. 임의 약칭 금지.

#### 지역
기존 지역 제한 데이터 사용. 명시적 전국 사업이면 `전국`; 판정 불가면 `확인필요`.

#### 마감
현재 연도는 `M/D`, 다른 연도면 `YYYY/M/D`.

### 제거할 표시 컬럼
```text
추천이유
바로가기
사이트명
```
단, 원본 데이터 필드 자체는 수집/로그/추적을 위해 삭제하지 않는다.

## 금지사항
- 공고 수집 소스 변경.
- 크롤러 변경.
- 중복제거 정책 변경.
- 지원사업 포함/제외 정책 변경.
- 사용자 그룹/LLM 매칭 기준 변경.
- 메일 발송 스케줄/수신자 변경.
- DB 구조 변경.
- 원문 데이터 삭제.
- 근거 없는 지원금·대상·지역·적합 판정 생성.
- 실제 이메일/알림 발송.

## 입력검증
- 공고명은 필수. 없으면 기존 invalid notice 정책으로 처리.
- URL은 비어 있으면 링크를 만들지 않는다.
- 마감일은 기존 parser 결과를 사용하고 invalid date가 한 행 때문에 전체 메일을 깨지 않게 한다.
- 적합/지원/대상/기관/지역 값은 허용된 기존 데이터에서만 매핑.

## 빈상태
- 공고 0건이면 빈 table을 렌더링하지 않고 기존 empty 문구 또는 `현재 조건에 맞는 신규 공고가 없습니다.` 표시.
- 지원/대상/지역 값 없음 → `확인필요`.
- URL 없음 → 공고명 plain text.

## 로딩상태
이메일 자체는 정적 렌더링이므로 별도 UI loading은 만들지 않는다. 단, preview 생성/렌더링 파이프라인이 비동기라면 기존 loading/processing 상태를 유지하고 중복 실행을 방지한다.

## 오류상태
- 한 공고 일부 필드 오류가 전체 이메일 생성을 실패시키지 않게 field-level fallback.
- 전체 renderer 실패는 명시적 FAIL.
- 데이터 없음과 parser 오류를 같은 값으로 숨기지 않는다.

## 테스트
최소 검증:
1. 정상 공고 1건
2. 여러 공고
3. 신규공고 `🆕`
4. D-Day
5. 지원가능/확인필요/대상아님
6. URL 존재 → 공고명 링크
7. URL 없음 → plain text
8. 지원 없음
9. 대상 없음
10. 지역 없음
11. 공고 0건
12. 한 행 일부 데이터 오류
13. Gmail-compatible HTML preview
14. 기존 메일 발송 regression
15. TRACK A targeted tests + `tests/test_version_delivery_integration.py`
16. 가능하면 전체 `python -m pytest tests/ -q --tb=short`

## 회귀검증
- bizinfo/kstartup 등 기존 source 수집.
- seen_ids/중복제거.
- 예비창업/지원유형 매칭.
- source health.
- outbox/version delivery.
- 기존 dry-run/preview 생성.
- 실제 발송은 하지 않는다.

## 문서동기화
- 이메일 포맷을 설명하는 README/TASKS/관련 문서가 있으면 8개 컬럼 기준으로 최소 수정.
- 기존 hotfix 결과 문서는 실제 테스트 결과와 다르면 수치/상태만 정정.

## Git 규칙
- 최신 origin/main 기준 새 작업 branch/worktree 사용.
- TRACK A와 B가 파일군이 겹치지 않으면 병렬 가능.
- 동일 파일을 건드리면 한 owner branch에서 순차 처리.
- 테스트 통과 후 commit/push/PR 생성.
- main 자동병합 금지.

## DONE/BLOCKED
DONE:
- 기존 P1/P2가 해결됐거나 재현된 항목을 수정하고 근거 확보.
- 이메일 8개 컬럼 순서 정확.
- 공고명 하이퍼링크 동작.
- 추천이유/바로가기/사이트명 컬럼 없음.
- 빈값/오류/0건 정상.
- 기존 수집·매칭·발송 정책 회귀 없음.
- 관련 테스트 통과.

BLOCKED:
- 최신 main 자체가 diverged/dirty라 안전한 분리 불가.
- AGENTS.md 보호규칙과 필수 수정이 충돌하고 우회 불가.
- 테스트/환경 실패로 완료 검증 불가.

## 최종보고
```text
REPO: pds2225/mail
BASE_SYNC: CLEAN_CURRENT | FAST_FORWARDED | LOCAL_CHANGES_PRESERVED | DIVERGED | BLOCKED
TRACK_A: ALREADY_FIXED | DONE | BLOCKED
TRACK_B: DONE | BLOCKED
EMAIL_COLUMNS: 상태 | 적합 | 공고 | 지원 | 대상 | 기관 | 지역 | 마감
BRANCH:
COMMIT:
PUSH:
PR:
TEST:
REGRESSION:
STATUS: DONE | BLOCKED | FAIL
```

## 실행지시
원격 상태를 안전하게 확인·동기화한 뒤 이 `TASK.md`만 처음부터 끝까지 읽고 실행한다. 최신 main에서 이미 해결된 작업을 중복 구현하지 말고, 재현되는 결함과 현재 이메일 표 개편만 수행한다.
