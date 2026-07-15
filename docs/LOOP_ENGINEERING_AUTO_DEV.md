# Mail 프로젝트 — Loop Engineering 자동개발 시스템

> 셀렉트스타 뉴스레터(2026-07 3주차)의 **루프 엔지니어링** 개념을  
> 기존 Auto Dev Queue·정확도 하네스·게이트 스크립트 위에 얹은 설계서.  
> 목표: **사람이 매번 에이전트를 프롬프트하지 않고**, 루프가 에이전트를 프롬프트하게 한다.  
> 사람 개입은 **맥락 우위(context advantage)** 가 필요한 판단 게이트에만 남긴다.

---

## 0. 한 줄 요약

| 기존 | 이후 |
|------|------|
| 사람이 TASK를 쓰고 → 에이전트에 직접 지시 → 결과 확인 | **루프가 TASK를 고르고 → 검증 게이트로 닫고 → 드리프트만 사람에게 올림** |
| 최적화 단위 = 프롬프트 1회 | 최적화 단위 = **반복해서 도는 시스템 전체** |

기존 인프라를 버리지 않는다. `TASKS.md` / `RULES.md` / `scripts/auto_dev_queue.py` /  
`recall_zero_gate.py` / `core_sources_checklist.py` / accuracy harness 를 **루프의 실행·검증·상태 자산**으로 재배치한다.

---

## 1. 왜 루프인가 (이 프로젝트에 맞춘 이유)

Mail 시스템의 실패 모드는 “한 번 잘못 짠 프롬프트”보다 다음이 많다.

1. **소스 HTML/API 변경** → 수집 공백 (coverage drift)
2. **필터·지역·키워드 기준 노후** → FP/FN 누적 (judgment drift)
3. **작업 자산(체크리스트·루브릭·TASK 문구) 변질** → 같은 오류 반복 (asset drift)
4. **종료 조건 없는 자동 수정** → 비싸고 위험한 무한 재시도

루프 엔지니어링은 위 네 가지를 **트리거 → 실행 → 검증 → 상태 → 종료**로 닫는다.

---

## 2. 앤드류 응 3루프 → Mail 매핑

세 루프는 속도가 다르고, 느린 루프가 빠른 루프의 명세를 바꾼다.

```
┌─────────────────────────────────────────────────────────────────┐
│ L3 외부 피드백 루프 (일~주)                                        │
│  수신자 반응 · 오발송 신고 · 신규 고객 intake · 소스 사이트 정책 변경   │
│  → 제품 비전 / groups.json 방향 / “무엇을 좋은 추천으로 볼지” 갱신     │
└────────────────────────────┬────────────────────────────────────┘
                             │ 명세·평가 기준 갱신
┌────────────────────────────▼────────────────────────────────────┐
│ L2 개발자(운영자) 피드백 루프 (수십 분~수 시간)                       │
│  accuracy matrix · FP/FN 클러스터 · 골든라벨 의심분 · BLOCKED 큐      │
│  → TASKS.md / eval rubric / 허용 수정 범위 갱신                      │
└────────────────────────────┬────────────────────────────────────┘
                             │ 코딩 명세 + 게이트
┌────────────────────────────▼────────────────────────────────────┐
│ L1 에이전틱 코딩 루프 (분 단위) — 무인 기본                            │
│  패치 → pytest → recall_zero_gate → core_sources(해당 시) → PR      │
│  통과할 때까지 자체 수정. 실패·위험은 종료 조건으로 L2에 에스컬레이션     │
└─────────────────────────────────────────────────────────────────┘
```

| 루프 | 누가 주로 돈다 | Mail 자산 | 사람 개입 |
|------|----------------|-----------|-----------|
| **L1** | Cursor Cloud / GHA auto-dev | 코드·테스트·게이트 스크립트 | 기본 **0** (안전 게이트만) |
| **L2** | 운영자 + accuracy harness | `TASKS.md`, 루브릭, 골든라벨 | **배치 승인 1회** (빈틈 고칠까?) |
| **L3** | 고객·수신자·사이트 현실 | `groups.json` 방향, intake | **비전 판단만** |

원칙: AI는 빠른 실행·검증, 사람은 느린 방향.  
사람이 L1에 들어가지 않아도 되게 **검증·종료 조건**을 코드로 고정한다.

---

## 3. 사부(Saboo) 루프 해부학 — 공통 스키마

모든 루프(및 개별 TASK)는 아래 다섯 필드를 가진다.  
기계 판독용 정의: [`auto_dev/loops.json`](../auto_dev/loops.json)

| 요소 | 의미 | Mail 구현 |
|------|------|-----------|
| **트리거** | 언제 시작 | cron / workflow_dispatch / coverage 하락 / recall 게이트 실패 / PENDING TASK |
| **실행** | 무엇을 수행 | 에이전트 패치, dry-run 모니터, matrix 채점, FIX TASK 생성 |
| **검증** | 성공의 증거 | `pytest test_monitor.py`, `recall_zero_gate`, `core_sources_checklist`, 문법·보호파일 검사 |
| **메모리/상태** | 다음에 남길 것 | `auto_dev_state.json`, `TASKS.md`, `done/failed/blocked_tasks.md`, matrix·라벨 |
| **종료 조건** | 성공·실패·에스컬레이션 | 최대 재시도 2, 보호파일 터치→BLOCKED, 진전 없음→STOP, Secret 누락→BLOCKED |

종료 조건이 없으면 루프에 **과도한 권한을 주지 않는다** (뉴스레터와 동일).

---

## 4. 사람 개입 최소화 설계 (Human Gates)

맥락 우위가 필요한 곳만 남긴다. 그 외는 자동.

### 4.1 자동 (사람 없음)

| 동작 | 조건 |
|------|------|
| PENDING → RUNNING → 패치 시도 | 이메일 발송 위험 키워드 없음 |
| 단위/리콜 게이트 실행 | Secret 값 로그 금지 |
| docs / `scripts/*` / 테스트 / JSON 설정(비수신자) PR | 게이트 전부 통과 |
| FAILED → FIX TASK 자동 생성 | 재시도 < 2 |
| SKIPPED (변경 없음) | diff empty |
| 상태 파일 커밋 `[skip ci]` | GHA bot |

### 4.2 사람 1회 (배치 가능)

| 게이트 | 이유 |
|--------|------|
| **G1** L2: FP/FN 빈틈 클러스터 “고칠까?” | 무엇을 좋은 추천으로 볼지 = 맥락 |
| **G2** `monitor.py` / `streamlit_app.py` 수정 PR merge | 회귀·발송 경로 위험 |
| **G3** 골든라벨 L1 확정 (추측 라벨링 금지) | 정답지 오염 방지 |
| **G4** 실제 메일 발송 / 수신자 목록 변경 | 안전규칙 #1,#6 |

### 4.3 사람에게만 (자동 금지)

- 실제 SMTP/Gmail 발송
- main 직접 push
- Secret 값 확인·출력
- BLOCKED TASK 강제 재개 (원인 해소 후 PENDING 재투입은 사람이)

상세: [`auto_dev/human_gates.md`](../auto_dev/human_gates.md)

---

## 5. 작업 자산 (Work Assets) — 드리프트 방지

한 번 쓰고 버리는 프롬프트 대신, **재사용되며 에이전트 행동을 누적 규정**하는 자산.

| 자산 | 경로 | 역할 | 드리프트 신호 |
|------|------|------|----------------|
| 안전규칙 | `RULES.md` | 발송·보호파일·재시도 | 규칙과 코드 불일치 |
| 태스크 큐 | `TASKS.md` | L2→L1 명세 | PENDING 적체, RUNNING 고아 |
| 루프 정의 | `auto_dev/loops.json` | 5요소 스키마 | 종료조건 누락 |
| 평가 루브릭 | `auto_dev/eval_rubric.md` | “성공”의 정의 | 게이트 우회 TASK 증가 |
| 종료 조건 | `auto_dev/exit_conditions.md` | 출구 | 무한 FAILED 핑퐁 |
| 사람 게이트 | `auto_dev/human_gates.md` | 판단 잔여 | 자동 범위 침범 |
| 실행 상태 | `auto_dev_state.json` | 메모리 | retry_counts 폭주 |
| 리콜/소스 게이트 | `scripts/*_gate*.py`, checklist | 검증 | 게이트 green인데 실측 악화 |

**드리프트 점검 루프 (L2 주간):**

1. `scripts/loop_verify.py --drift` 가 자산 신선도·게이트 일치·PENDING 적체 보고  
2. 오래된 exclude/priority 키워드, 과도하게 길어진 체크리스트, 이전 프로젝트 지시 혼입 탐지  
3. 악화된 자산만 G1으로 올려 수정 (전체 재작성 금지)

---

## 6. 대상 루프 카탈로그 (Mail 특화)

### L1-A `coding-fix` — 기본 코딩 루프

| 요소 | 내용 |
|------|------|
| 트리거 | `TASKS.md` PENDING 1건 / GHA daily 09:00 KST |
| 실행 | 허용 파일만 수정하는 에이전트 세션 (Cloud Agent / 로컬) |
| 검증 | `loop_verify.py` → unit + recall(+ core sources if scoped) |
| 상태 | TASK → DONE/FAILED/BLOCKED, state.json, PR 링크 |
| 종료 | 게이트 pass → DONE; retry≥2 → BLOCKED; 보호파일 diff → BLOCKED |

### L1-B `gate-repair` — 게이트 실패 자동 복구

| 요소 | 내용 |
|------|------|
| 트리거 | CI 또는 `loop_verify` non-zero |
| 실행 | 실패 스위트만 대상으로 FIX TASK 생성·처리 |
| 검증 | 동일 게이트 재실행; 회귀(이전 green → red)면 롤백 |
| 상태 | failed_tasks.md + FIX TASK id |
| 종료 | green 복구 / 2회 실패 / “진전 없음”(동일 에러 해시) |

### L1-C `coverage-sentinel` — 수집 건전성 (기존 S0)

| 요소 | 내용 |
|------|------|
| 트리거 | monitor dry-run / raw store 일자 롤 |
| 실행 | coverage·3대 소스 checklist (네트워크 허용 환경) |
| 검증 | baseline 대비 high-severity면 **즉시 STOP** |
| 상태 | 리포트 아티팩트 |
| 종료 | OK 계속 / high-severity → 사람 통보(G1) — 자동 패치 금지 |

### L2-A `accuracy-defect` — FP/FN 빈틈 (기존 accuracy orchestrator)

| 요소 | 내용 |
|------|------|
| 트리거 | 주간 matrix / 골든풀 갱신 |
| 실행 | match-runner → FP/FN hunter → `s3_defects` 클러스터 |
| 검증 | 라벨 없는 건 추측 금지; recall 1순위 정책 유지 |
| 상태 | defects.md, matrix.json |
| 종료 | **G1 승인 전 L1 코딩 금지**; 승인분만 coding-fix TASK로 분해 |

### L3-A `product-vision` — 외부 피드백

| 요소 | 내용 |
|------|------|
| 트리거 | 고객 intake, 오추천 신고, 신규 기관 요청 |
| 실행 | 사람이 비전·그룹 방향 문서화 → L2 루브릭/TASK 반영 |
| 검증 | “이 변경이 수신자 가치인가?” (자동화 불가) |
| 상태 | HANDOFF / CUSTOMER_INTAKE / groups 방향 |
| 종료 | 방향 확정 시 L2 명세 갱신 후 루프 종료 |

---

## 7. 실행 아키텍처

```
GitHub Actions (cron/dispatch)
        │
        ▼
scripts/auto_dev_queue.py          ← 오케스트레이터(큐·상태·안전)
        │  select 1 PENDING
        ▼
auto_dev/loops.json                ← 루프 타입·종료조건 로드
        │
        ├─ dry-run? → Summary만, 파일 미변경
        │
        ▼
(에이전트 실행 슬롯)                 ← Cursor Cloud / 향후 API
  · RULES + eval_rubric + task 주입
  · 허용 경로만 수정
        │
        ▼
scripts/loop_verify.py             ← 검증 단일 진입점
  · protected-file guard
  · pytest test_monitor.py
  · recall_zero_gate
  · (옵션) core_sources_checklist
        │
        ├─ pass → DONE + PR (허용 파일)
        ├─ fail + retry < 2 → FAILED + FIX TASK
        └─ danger / retry≥2 / secret → BLOCKED (사람)
```

현재 `auto_dev_queue.py`의 placeholder DONE을 **검증 연동 + 루프 스키마 인식**으로 교체한다.  
실제 에이전트 코딩 슬롯은 Cursor Cloud Agent / 수동 워크플로와 결합하며, 큐는 **언제 돌리고 언제 멈출지**를 소유한다.

---

## 8. 안전 불변식 (루프에 권한을 주기 전)

1. 실제 이메일 발송 경로 호출 금지 (dry-run / draft only)  
2. `monitor.py`, `streamlit_app.py`, `.env` 자동 수정 금지 → 변경 시 BLOCKED  
3. Secret/본문/수신자 전체 주소 로그 금지  
4. 동일 TASK 최대 2회 재시도, BLOCKED 자동 재개 금지  
5. main 직접 push 금지, PR 경유  
6. 종료 조건 없는 루프에는 write 권한 부여 금지  
7. recall 정책: 지역 미상 → 버리지 않음; “확실한 타지역”만 제외  

---

## 9. 단계적 도입 (구현 로드맵)

코드 침습을 최소화한 순서. 각 단계는 자체 검증 가능.

| Phase | 산출물 | 사람 |
|-------|--------|------|
| **P0** (본 문서) | `docs/LOOP_ENGINEERING_AUTO_DEV.md`, `auto_dev/*` 작업 자산, `loop_verify.py`, 큐·RULES 연동 | 리뷰 1회 |
| **P1** | GHA에서 `loop_verify`를 auto-dev 전/후 게이트로 실행; Summary에 루프 5요소 표시 | 없음 |
| **P2** | PENDING TASK 메타(`loop:` / `verify:`) 파싱; FIX TASK 자동 생성 강화 | 없음 |
| **P3** | L2 accuracy-defect → TASK 자동 분해 (G1 승인 훅만 사람) | G1 |
| **P4** | 에이전트 코딩 슬롯 API/Cloud 연동 (큐가 프롬프트 루프 소유) | G2 only |

---

## 10. 성공 지표

| 지표 | 목표 |
|------|------|
| L1 무인 완료율 (DONE / (DONE+FAILED+BLOCKED)) | 상승 추세 |
| BLOCKED 중 “종료조건 부재” 비율 | → 0 |
| 사람 개입 횟수 / 주 | G1~G4만; L1 개입 ≈ 0 |
| recall_zero_gate | 항상 green (회귀 시 L1-B 자동) |
| 작업 자산 드리프트 리포트 미해결 항목 | 주간 감소 |
| 실제 메일 오발송 | 0 (자동 경로) |

---

## 11. 관련 문서

- `RULES.md` — 안전규칙  
- `TASKS.md` — L1 입력 큐  
- `docs/mail_accuracy_orchestrator_plan.md` — L2 accuracy 파이프라인  
- `docs/CORE_SOURCES_CHECKLIST.md` — 3대 소스 게이트  
- `AGENTS.md` — Cloud Agent 운영 메모  

---

## 12. 설계 결론

> 앞으로 이 레포에서 AI를 가장 잘 쓰는 방식은  
> **어떤 작업을 반복 가능한 루프로 만들지**,  
> **어떤 작업 자산으로 그 루프를 이끌지**,  
> **어떤 결정을 끝까지 사람의 몫으로 남길지**를 아는 것이다.

루프는 설계하되, **판단하는 자리(G1~G4)는 지킨다.**
