> 자동 생성(2026-06-29): mail 추천 정확도 향상 오케스트레이터 설계 계획서 — 4관점(현황진단·아키텍처·측정체계·로드맵) 다각도 설계 → 합의 종합. **구현 없이 계획만**, 코드 미수정.

# mail 추천 정확도 향상 오케스트레이터(accuracy-harness) — 통합 실행 계획서

> **상태: 계획서만 (코드 미수정).** 4개 관점(현황진단·아키텍처·측정체계·로드맵)을 읽기·분석 기반으로 종합. 모든 경로는 절대경로(D:\mail\…). 실제 구현은 별도 작업 브랜치에서 PR 경유.
> **검증 완료(이 세션):** #15 버그 실재(run_company_match.py:133 `evaluate_notice(it)` group 없음) / 2026-06-25 골든풀 874공고·region_field 23건만 채워짐(851건 null) / `_count_hits` substring(mail_core/matching/company_match.py:128) vs mail_core/matching/scoring.py 단어경계 비대칭 / `_METRO_FAMILY` 양쪽 중복(monitor.py:199, mail_core/matching/company_match.py:133) / `explicit_nationwide` 거친 substring(monitor.py:2591) / `exclude_penalty=-60`(mail_core/matching/company_match.py:61) — **전부 사실 확인.**

---

## 1. 목표

> **한 줄 요약(비개발자용):** 지금은 사람이 지역 빈틈을 하나씩 손으로 찾아 고치는데, 이 계획은 "틀린 추천을 자동으로 찾아 → 원인 가설 → 최소수정 → 회귀테스트로 안전 확인 → 사람 1회 승인"하는 컨베이어벨트를 깔아 빈틈이 스스로 줄게 만든다.

- **무엇을 만드나:** mail 추천의 오탐(타지역인데 추천)·누락(적격인데 차단)을 **숫자(precision/recall)로 측정**하고, 결함을 자동 색출해 최소수정·회귀검증까지 묶는 **오케스트레이터(스킬 1 + 에이전트 6) + 측정 인프라(읽기전용 스크립트 + 골든셋)**.
- **불변 원칙(이 도메인의 헌법):**
  1. **recall 1순위(평생목표):** 지역 단서 전무 → 버리지 말고 `REGION_UNKNOWN`(미상 surface). "확실한 타지역"만 제외. `test_region_unknown_policy.py` 5/5 green이 **모든 단계 차단 게이트**.
  2. **대칭 원칙:** company_match(기업단위) ↔ monitor(그룹단위)가 같은 공고에 같은 verdict.
  3. **앱 핵심파일(monitor.py·streamlit_app.py) 직접수정 최소화:** 가능하면 보조모듈·`mail_core/matching/company_match.py`·`config/groups.json`·`config/companies.json` 데이터로 해결. 핵심파일 수정은 사람 승인 게이트 필수(AGENTS.md RULES).
  4. **검증된 함수 재사용:** `_applicant_restricted_regions`·`_resolve_applicant_region_scope`·`_applicant_target_text`·`_short_region`·`_other_region_block`(이번 PR #111~114로 확립).
  5. **안전:** SMTP 발송 금지(드라이런 전용)·수신자 마스킹·Secret 미출력·main 직접 push 금지·위험9종 자동병합 금지.

---

## 2. 현황 요약

> **한 줄 요약:** 지역 매칭은 PR #111~114로 견고해졌지만, 부정확의 무게중심이 ① **#15 인천 고정 오염**(기업매칭 전체 오염, 최우선)과 ② **두 채점엔진 비대칭**(같은 공고를 그룹/기업이 다르게 판정)으로 옮겨갔고, ③ **정답지가 비어 향상을 숫자로 못 잰다**.

**(A) 추천을 부정확하게 만드는 핵심 결함 — 우선순위 종합(중복 제거)**

| 순위 | 결함 | 유형 | 근거(검증됨) | 영향 |
|---|---|---|---|---|
| **P0-1** | **#15 run_company_match가 evaluate_notice를 group 없이 호출 → 인천 고정 오염** | precision+recall 전방위 | run_company_match.py:133, monitor.py(group 없으면 인천 classify) | 인천 외 全기업 추천이 인천 적격성으로 1차 오염 |
| **P0-2** | **권역 일반화 미완(경상/호남/충청권 — 현재 수도권만 처리)** | precision+recall | company_match._METRO_FAMILY만 분기, `_REGION_CLUSTER` 부재 | 비수도권 권역 한정 공고가 타지역 기업에 누출 / 권역=적격 케이스 환원 못함 |
| **P1-1** | **채점엔진 이원화(ASCII 단어경계 비대칭)** | precision | mail_core/matching/company_match.py:128 substring vs mail_core/matching/scoring.py 단어경계 | 영어약어(AI·MES·ERP·DX) 기업일수록 오추천↑ |
| **P1-2** | **#14 `_other_region_block` explicit_nationwide 거친 substring 면제** | precision | monitor.py:2591 `"전국" in title` | '[부산] 전국행사(부산한정)'이 '전국'으로 누출 |
| **P1-3** | **exclude -60 + substring 오매칭** | recall | mail_core/matching/company_match.py:61,128,311 | 제외어 substring 1히트로 적합공고 0점 추락 |
| **P1-4** | **마감 unknown 누출 + open-term 우회** | precision | classify_deadline_status(monitor.py) / company_match `_hard_excluded`는 "closed"만 차단 | 마감/미상 공고가 추천 노출 |
| **P2-1** | dedup substring 오병합 | recall | dedup_items(monitor.py) | 적격 공고 소실 |
| **P2-2** | 공장/수출 비대칭 페널티(공장 미스매치 -20, 수출은 보너스만) | recall | mail_core/matching/company_match.py:284-297 | 비제조 기업 과소평가 |

**(B) 측정 자산 현황(실측)**

| 자산 | 실측 | 측정 가용성 |
|---|---|---|
| `data\raw\2026-06-25\notices\*\meta.json` | **874건**(="875공고" 전수풀) | 입력풀 O, 정답지 아님 |
| `meta.json.region_field` | **874 중 23건만** 채워짐, 851건 null | 부분 정답(weak label). recall 직접측정 불가 |
| 판정함수 | `monitor.evaluate_notice(item, group)`·`classify_region_for_group`·`company_match.compute_match_score`·`match_for_company` | 전수검사 엔진으로 직접 호출 가능 O |
| 회귀테스트 | `test_region_multi_group.py`·`test_company_match_multi_region.py`·`test_region_unknown_policy.py`·`test_accuracy_improve.py` | 합성 가드 O, 실데이터 지표 없음 |
| 게이트 스크립트 | `scripts/recall_zero_gate.py`·`scripts/core_sources_checklist.py`·`coverage_alert.py` | 재사용 가능 O |

→ **핵심 측정 공백:** 정답 라벨이 사실상 비어(23/874) "추천이 맞았나"를 숫자로 못 잰다. **오케스트레이터 1순위 = 골든셋 구축 + 전수검사 상설화.**

---

## 3. 오케스트레이터 설계 (단계·에이전트·흐름)

> **한 줄 요약:** 수집검증 → 정답지 구축 → 전수채점(두 경로 동시) → FP/FN 헌터 팀(교차검증) → [사람 승인1] → 최소수정+회귀테스트 작성 → 회귀검증 → [사람 승인2] → PR. 사람 개입은 단 2곳.

### 3.1 파이프라인 흐름

```
[S0 수집검증] coverage-sentinel ──(high-severity 사고 시 폰알림·중단)──▶ 사람
      │ OK
[S1 정답지구축] truth-curator ──▶ labels/golden.jsonl(L1) + weak_labels(L2)
      │
[S2 전수채점] match-runner ──▶ matrix.json (874 × 그룹전체 × 기업전체, 두 경로 동시)
      │
   ┌──┴──┐  ← 에이전트 팀(Fan-out, 서로 통신)
[S3a FP헌터] ⇄ [S3b FN헌터]   (precision↔recall 길항 실시간 교차검증)
   └──┬──┘
      │ 결함후보 클러스터(s3_defects.md)
  ★G1 사람승인#1: "이 빈틈들 고칠까?"(배치 일괄, 정답지 의심분만 개별)
      │
[S4 최소수정] fix-architect ──▶ 패치초안 + 새 회귀테스트(작성만)
      │
[S5 회귀검증] regression-verifier ──▶ pytest + recall_zero_gate + 전/후 matrix diff
      │  (regressed 있으면 S4로 루프백, 최대 N회 후 사람보고)
  ★G2 사람승인#2: PR 병합(핵심파일·위험9종이면 필수, 아니면 자동병합)
      │
   Git 브랜치 → PR → MEMORY/wiki "before→after" 기록
```

### 3.2 에이전트 명세 (`~/.claude/agents/mail-acc-*` 신설)

| 에이전트 | 모델 | 역할 | 입력 | 출력 |
|---|---|---|---|---|
| **mail-acc-coverage-sentinel** (S0) | sonnet | 측정 전 데이터 건전성 확인 | `data/raw/{date}/`, baseline | `s0_coverage.json{ok,anomalies,blocking}`. high-severity→**중단+ntfy** |
| **mail-acc-truth-curator** (S1) | opus | 3-tier 정답지 집결. **라벨 없는 건 추측 라벨링 금지** | meta.json, 테스트매트릭스, `config/groups.json`·`config/companies.json` | `labels/golden.jsonl`(L1, append-only) + `s1_weak_labels.json`(L2) |
| **mail-acc-match-runner** (S2) | sonnet | 874 × (그룹전체+기업전체) **두 경로 동시 채점**. ★group **명시 전달**(#15 회피) | raw, `config/groups.json`·`config/companies.json`, s1라벨 | `matrix.json{group결정,기업결정,region_status,score,breakdown,약라벨,자기모순플래그}` |
| **mail-acc-fp-hunter** (S3a) | opus | 오탐 색출(타지역인데 추천) | matrix, 약라벨 | `s3_fp.json` |
| **mail-acc-fn-hunter** (S3b) | opus | 누락 색출(적격인데 차단·저점) | matrix, 약라벨 | `s3_fn.json` |
| **mail-acc-fix-architect** (S4) | opus | 승인된 빈틈마다 최소수정 + 새 회귀테스트(작성). 한 PR=한 빈틈클러스터 | s3_defects(승인분), 소스 | 패치(브랜치) + 회귀테스트 + `s4_plan.md` |
| **mail-acc-regression-verifier** (S5) | opus | **작성자와 분리된 검증레인**(self-approve 금지). 고친 것+안 깬 것 증거판정 | 패치브랜치, 전/후 matrix | `s5_verdict.json{pass,fixed,regressed,recall_gate,fp_delta,fn_delta}` |

**탐지 규칙(헌터):**
- **FP헌터:** ①약라벨 region이 타지역인데 matched ②restricted에 own 없는데 통과 ③exclude 히트인데 score≥임계 ④경로불일치 "그룹=BLOCK·기업=PASS" → 곧 #15 신호.
- **FN헌터:** ①약라벨 region이 own인데 rejected ②제목 [지역]태그 own인데 BLOCK ③진짜 전국공고인데 차단 ④권역 일반화 빈틈(경상/호남/충청) 패턴 ⑤경로불일치 "그룹=PASS·기업=BLOCK".
- **팀 공유 산출물 `s3_defects.md`:** FP/FN 통합 + 같은 함수·원인끼리 클러스터링. 알려진 3빈틈(#권역·#14·#15)을 **시드 가설**로 주입.

### 3.3 OMC 패턴 결합

| OMC 패턴 | 적용 구간 | 이유 |
|---|---|---|
| `/team`(Agent Teams) | S3 FP/FN 헌터 | Fan-out+교차검증 핵심(precision↔recall 길항). "Fan-out=반드시 팀" |
| `/ralph` | S4↔S5 자기참조루프 | "회귀0 + 빈틈fixed" 종료조건까지. verifier=리뷰어 지정으로 self-approve 방지 |
| `/ultraqa` | S5 회귀검증 | "테스트→검증→수정→반복" |
| `/ralplan` | 모호 트리거 게이팅 | "정확도 올려줘"처럼 막연하면 먼저 범위합의 |
| 경량 서브에이전트 | S0·S1·S2 | 순차·통신불요, 결과만 파일반환→토큰절약 |
| `problem-solver` | S4 단건 디버깅 | 근본원인 모호한 빈틈 위임 |
| `skill-harvester` | 사이클 종료후 | 새 검출/수정 패턴 스킬 수확 |
| `coverage_alert`+ntfy | S0 알림 | 수집사고는 정확도 트랙과 분리·즉시 폰통보 |

**트리거:** `mail-accuracy-orchestrator` 스킬을 `~/.claude/skills/`에 신설. "정확도 점검", "추천 정확도 올려줘", "오탐 찾아줘", "누락 찾아줘", "지역 빈틈 점검", "전수검사 돌려줘", "accuracy harness". 부분 재실행("FP만", "검증만 다시", "권역 빈틈만")도 같은 스킬이 단계 진입점으로 처리.

---

## 4. 정확도 측정체계

> **한 줄 요약:** (공고, 타깃) 쌍을 TP/FP/FN/TN으로 분류해 precision/recall을 찍는다. 정답지는 비었으니 3-tier(자동→규칙→사람확인)로 키우고, 라벨러와 채점기는 절대 같은 코드를 공유하지 않는다(공허한 100% 방지).

### 4.1 지표 정의 (recall 우선)
- **TP**: 추천∧적합 / **FP**: 추천∧부적합(=잘못된 메일, precision의 적) / **FN**: 미추천∧적합(=놓친 기회, **가장 비싼 오류** — "누락 제로>정확도") / **TN**: 정상 거름.
- `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`.
- **FP를 사유코드별로 쪼갠다**(4건 빈틈과 1:1 매핑→어디서 새는지 즉시 보임): `fp_nationwide_override`·`fp_operator_addr`·`fp_partial_metro`·`fp_metro_leak`·`fp_권역`(경상/호남/충청)·`fp_industry`(ASCII 오매칭).

### 4.2 골든셋 3-tier (라벨러≠채점기)

| Tier | 출처 | 신뢰도 | 용도 |
|---|---|---|---|
| **A 자동약라벨** | meta.json `region_field` 23건 + own지역 매핑 | 중(부분) | 지역 FP **1차 정답**. "추천했는데 region_field와 모순"=확실 FP |
| **B 규칙유도** | 명시 지역태그(`[대구]`·'○○ 소재 한정')만 문자열 최소규칙으로 추출, 모호한 건 null 유지 | 약 | precision 측정엔 사용, recall 분모엔 신중 |
| **C 사람확인** | A/B에서 판정기≠라벨로 어긋난 의심후보를 `review_queue.md`로 큐잉, 사용자 O/X | 최고 | 게이트 판정의 법적 기준. 하루 20~30건씩 누적→점점 강해짐 |

> **핵심 원칙:** Tier B 라벨은 점수·가중치 로직을 쓰지 않고 *문자열 매칭 최소규칙*만 쓴다(순환 자기채점 위험 차단). 게이트 판정은 **L1 골든셋만** 사용.
> **L3 자기모순 탐지(라벨 불요):** 같은 공고에 대해 그룹경로 vs 기업경로 verdict **불일치**를 자동 surface. #15가 바로 이걸로 잡히는 전형.

### 4.3 전수검사·매트릭스(읽기전용 측정, 신규 파일 제안)
`D:\mail\scripts\accuracy_eval.py`(가칭) — 판정함수를 **호출만** 한다(코드 수정 아님).
- **전수 sweep:** 874 × (그룹3 + 기업3) ≈ 5,244 판정. ★그룹경로는 group **명시 전달**(#15 회피). #15 영향은 "group 명시 vs 미전달" **diff**로 몇 건 오판인지 숫자 증명.
- **지역 confusion matrix:** 공고지역 × 타깃지역 교차표. **빨간 셀(FP) 위치 = 다음 고칠 빈틈**. 권역 누락이 부산/대구/광주 행으로 드러남.
- **recall 분모 처리:** `recall@labeled`로 명시(분모=라벨수 같이 리포트, "23건 100%" 과장 방지). 단 "own/명시적전국 신호 있는데 BLOCK"은 라벨 없이도 **무조건 FN 후보**로 카운트.

### 4.4 KPI + 게이트

| 지표 | 목표 | 게이트 종류 |
|---|---|---|
| **region_FP**(지역 오추천) | **0 유지**(Tier A 23건 대비) | 하드 |
| FN후보(own·전국 BLOCK) | **0**(불변) | 하드 |
| `recall@labeled` | **≥ baseline**(평생목표) | 하드(하락시 PR 차단) |
| precision@labeled | ≥ 0.90, 추세 비하락 | 소프트 |
| 전체 추천량 drift | 직전 대비 ±N% 경보 | 경보(silent regression 탐지) |

**원칙:** recall·FN후보는 하드(0 아니면 실패), precision은 소프트(baseline 대비). 트레이드오프에서 **recall 우선**.

### 4.5 "향상됐다" 증명 절차 (매 사이클)
```
[before] 수정 전 전수검사 → before.json
[after]  수정 후 전수검사 → after.json
[diff]   region_FP: 7→0 (fp_권역 7건 제거) / FN후보 0→0(recall 무손상) / precision 0.91→0.95 / 추천량 -0.6%(정상)
[gate]   region_FP==0 ∧ FN후보==0 ∧ precision≥baseline → 병합
[track]  trend.csv에 날짜별 1행 append → 시계열로 "계속 좋아지는 중" 증명
```
→ 사용자 번역: "전에는 부산 기업한테 경상권 한정 공고가 잘못 갔는데 이제 안 갑니다. 놓치는 공고는 안 늘었어요."

### 4.6 산출물 레이아웃
```
D:\mail\.omc\accuracy\
  ├─ runs\{date}\  s0_coverage.json · s1_weak_labels.json · matrix.json
  │               · s3_fp.json · s3_fn.json · s3_defects.md · s4_plan.md · s5_verdict.json
  ├─ labels\golden.jsonl        (L1 고정 정답지, append-only)
  ├─ baseline_metrics.json      (게이트 ratchet 기준선)
  ├─ trend.csv                  (날짜별 precision/recall/region_FP 시계열)
  └─ RESUME.md                  (다음 액션·미해결 빈틈)
D:\mail\data\golden\region_labels.jsonl · review_queue.md
D:\mail\scripts\accuracy_eval.py            (읽기전용 측정엔진)
D:\mail\test_accuracy_regression.py         (CI 회귀 가드)
```
각 `sN_*.json`이 있으면 그 단계 스킵→부분 재실행·이어가기(work-cockpit 패턴).

---

## 5. 단계별 로드맵 (P0~P3)

> **한 줄 요약:** P0는 측정 토대를 깐 직후 #15·권역 두 고효과 결함을 잡고, P1에서 비대칭(채점·면제·구조)을 정밀화, P2에서 측정을 CI에 영구화, P3는 데이터로 엣지 확장. **오늘 먼저: P0-0(측정) → P0-1(#15) ∥ P0-2(권역).**

### P0 — 토대 + 즉시·저위험·고효과 (당일)
충돌 조정: 로드맵 관점은 #15·권역을 P0로, 측정체계 관점은 측정을 먼저 깔자고 함 → **측정을 P0-0으로 선행**해 P0 수정 효과를 즉시 숫자로 증명(껍데기 방지).

- **P0-0 측정 토대 (먼저, 비용 낮음):** Tier A 23건 라벨 추출 → `accuracy_eval.py`로 region_FP **첫 측정**("23건 중 타지역 누출 0" = PR #111~114 효과 1차 확정). #15 "group 명시 vs 미전달" diff로 인천고정 영향 건수 확정. **이게 P0-1/P0-2의 before 스냅샷.**
- **P0-1 #15 인천 고정 해소:** `_enrich_with_evaluate`를 **기업별 합성 group 호출**로 변경(기업 city → 임시 group dict → `evaluate_notice(it, synth_group)` → `use_generic_region=True`). enrich를 전역 1회에서 **기업 루프 내부**로 이동. 인천 기업은 합성 group city=인천으로 회귀 무변. 합성 group엔 키워드 안 넣음(region 판정만 빌림). 신규 `test_run_company_match_region.py`(부산기업+부산공고=통과, +인천한정=하드제외, 인천기업=회귀동일).
- **P0-2 권역 일반화:** `_REGION_CLUSTER` 매핑 신설(수도권/충청권/호남권/경상권(영남)/강원권/제주권). company_match 권역 분기를 수도권 전용→일반 권역으로 확장(`kwon_notice`=권역토큰∧own∉권역→차단, `kwon_eligible`=own∈권역→적격). **차단을 좁게**(매핑 없는 모호 광역은 차단 제외 — 누출보다 누락이 더 큰 위반). 보일러플레이트(개최지/문의처)는 `_strip_contact_spans` 후 판정. 매트릭스 4권역행 추가(충청/호남/경상 PASS·BLOCK + 문의처면제).

### P1 — 정밀화·구조 통합 (같은 주)
- **P1-1 채점엔진 비대칭 제거:** company_match `_count_hits`의 ASCII 키워드(AI·MES·ERP·SaaS·DX)에 mail_core/matching/scoring.py와 **동일한 단어경계 매칭** 도입(영어약어 오매칭 차단). 한글 키워드는 substring 유지. → 그룹/기업 채점 일치.
- **P1-2 #14 explicit_nationwide 정밀화:** `_other_region_block` 면제를 본체와 대칭으로. **보수적 1차안:** substring 면제는 두되 `_applicant_restricted_regions`가 타지역 강신호로 잡히면 면제 취소(restricted 우선). nationwide-교체(`_resolve_applicant_region_scope`)는 P2 전수측정 후 결정.
- **P1-3 exclude 과민 완화:** -60 단일 가중치 + substring 오매칭 점검. exclude도 ASCII 단어경계 적용 검토, 가중치 균형 재조정은 전수측정으로 영향 확인 후.
- **P1-4 마감 누수:** `classify_deadline_status` unknown·open-term 우회 점검. company_match `_hard_excluded`가 unknown을 어떻게 다룰지 측정 후 결정(recall 영향 큼).
- **P1-5 권역↔광역 매핑 단일 정본화:** P0-2의 `_REGION_CLUSTER`를 공용 모듈(`mail_core/matching/region_clusters.py` 신규)로 올려 monitor·company_match가 **한 소스** 공유(drift 방지). `test_region_cluster_parity`로 두 경로 verdict 일치 박기. ★company_match는 monitor를 top-level import 안 함이 원칙 → **별도 파일**로 둬 순환 import 회피.

### P2 — 측정 자산 CI 영구화 (지속)
- **P2-1 전수 회귀 하네스 상설화:** `test_accuracy_regression.py`(가칭)가 `labels/golden.jsonl` 읽어 전수검사→**region_FP==0 ∧ FN후보==0** 단언, precision은 baseline 대비 ≥ 단언. `baseline_metrics.json` ratchet(좋아지면 갱신, 나빠지면 빨강). **단독 foreground 실행**(MEMORY: mail pytest 동시실행 MemoryError 거짓실패 회피).
- **P2-2 Tier B/C 누적:** review_queue로 정답 키워 recall@labeled 분모 확대.
- **P2-3 night-autodev recall-zero gate 연동:** 야간 훅으로 PR마다 "precision X→Y, recall 보존" 한 줄 자동 출력.

### P3 — 데이터 기반 엣지 확장
- 복합권역(영남=경북+경남+부산+대구+울산)·'○○권 제외' 부정형·모호 광역(강원=독립? 세종=충청권?) → **P2 전수 수치로 각 매핑의 recall 영향 측정 후에만** 반영(추측 금지).
- dedup substring 오병합(P2-1 결함B) · 공장/수출 비대칭 페널티 → 측정으로 빈도 확인 후 우선순위 결정.

**첫 사이클 시드:** 하네스를 빈손이 아니라 **알려진 3빈틈(#권역·#14·#15)**으로 출범 검증. 이 3건이 G1→G2 통과하면 "실제로 빈틈을 줄인다"가 증명되고, 이후 약라벨 전수검사로 신규 빈틈을 스스로 발굴.

---

## 6. 사람 개입(승인) — 단 2곳

| 게이트 | 시점 | 무엇을 승인 | 자동 진행 조건 |
|---|---|---|---|
| **G1** | S3 후 | "이 결함 후보들을 고칠 대상으로 확정" | 명백 FP/FN은 배치 일괄. 정답지 의심분만 개별 확인 |
| **G2** | S5 후 | "PR 병합" | 보조모듈/데이터/테스트만 수정 + S5 all-pass면 자동병합. **핵심파일(monitor.py)·위험9종은 사람 필수** |

그 외 전 구간(수집검증·전수채점·후보탐지·패치작성·회귀검증) 무인. 중간보고·"계속할까요" 금지(실제사용승인루프 정신). 단 S0 high-severity 수집사고는 즉시 중단·통보(안전 우선).

---

## 7. 위험·완화

| 위험 | 완화 |
|---|---|
| **약라벨 부정확**(851건 null) | L2는 후보 surface용. **게이트 판정은 L1 골든셋만** 사용 → 거짓결함으로 코드 안 망가뜨림 |
| **라벨러=채점기 순환**(공허한 100%) | Tier B는 문자열 최소규칙만, 점수·가중치 로직 미사용. 라벨러와 판정기 코드경로 완전 분리 |
| **권역 매핑 과함→정당공고 누락** | **차단을 좁게**(모호 광역 제외) 1차, P2 전수측정으로 확장 결정. 누출<누락 원칙 |
| **#14 면제 과하게 좁힘→전국공고 누락** | restricted-우선(보수적) 1차 채택, nationwide-교체는 전수측정 후 |
| **리팩토링 순환 import**(P1-5) | `mail_core/matching/region_clusters.py` 별도 파일, 지연 import 없이 양쪽 사용 |
| **전수검사 시간**(874×N) | S2 `run_in_background` + 캐시. 테스트는 **단독 foreground**(MemoryError 회피) |
| **두 경로 통합 비용** | match-runner가 어댑터 책임(핵심파일 미수정, 보조모듈) |
| **합성 케이스 편향**(FN헌터 권역) | 약라벨 실데이터 케이스 점진 병행 |
| **recall 회귀**(평생목표 위반) | `test_region_unknown_policy.py` 5/5 + recall_zero_gate를 매 단계 차단 게이트 |

---

## 8. 다음 단계 (오늘 먼저 할 순서)

1. **P0-0(측정 토대):** `accuracy_eval.py`(읽기전용) + Tier A 23건 라벨 추출 → region_FP 첫 측정 + #15 group diff 영향 건수 확정. **이게 모든 before 스냅샷.**
2. **P0-1(#15) ∥ P0-2(권역):** 저위험·고효과·서로 독립이라 병렬. 각각 회귀테스트 동반, `test_region_unknown_policy` 5/5 green 유지.
3. **before/after diff로 효과 증명** → G2 통과 시 첫 사이클 성공 = "하네스가 빈틈을 실제로 줄인다" 입증.
4. **P2-1(CI 박기):** `baseline_metrics.json` + `test_accuracy_regression.py`로 회귀 영구 차단.
5. **하네스 자동 발굴 전환:** 약라벨 전수검사로 신규 빈틈을 스스로 surface → P1·P3 순환.

**산출물 위치(이 계획서가 정의):** 오케스트레이터 스킬 `~/.claude/skills/mail-accuracy-orchestrator/`, 에이전트 `~/.claude/agents/mail-acc-{coverage-sentinel,truth-curator,match-runner,fp-hunter,fn-hunter,fix-architect,regression-verifier}.md`, 측정 인프라 `D:\mail\scripts\accuracy_eval.py`·`D:\mail\test_accuracy_regression.py`·`D:\mail\data\golden\`·`D:\mail\.omc\accuracy\`.

---

🧾 **방금 한 일 (쉬운 말 요약)**
- 네 개의 설계안을 하나의 실행 계획서로 합치면서, 핵심 주장(인천 고정 버그 #15, 정답 라벨이 874건 중 23건뿐, 채점기 두 개가 다르게 동작 등)을 **실제 코드·데이터로 직접 확인**해 사실임을 검증했다.
- 전에는 "지역 추천이 좋아졌다"를 내가 만든 테스트 통과로만 말했는데, 이제 **874개 실제 공고로 잘못 추천·놓친 공고를 숫자로 재고, 자동으로 빈틈을 찾아 고치는 컨베이어벨트(오케스트레이터) 설계**가 한 장으로 정리됐다.
- 👉 다음: 계획대로 측정 토대부터 깔고(P0-0) #15·권역 차단(P0-1·P0-2)을 병렬로 — 코드 수정은 이 계획서 범위 밖(읽기·분석만 수행함).
