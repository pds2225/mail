# Auto Dev — 평가 루브릭 (성공의 증거)

> 루프의 **검증** 단계가 참고하는 작업 자산.  
> 에이전트·큐는 “느낌이 좋다”가 아니라 아래 증거로만 DONE을 선언한다.

## 1. 필수 게이트 (L1 모든 coding-fix / gate-repair)

| ID | 명령 / 검사 | 통과 기준 |
|----|-------------|-----------|
| V1 | 보호 파일 diff | `monitor.py`, `streamlit_app.py`, `.env*` 변경 **0** |
| V2 | `python3 -m pytest test_monitor.py -q` | exit 0 |
| V3 | `python3 scripts/recall_zero_gate.py` | exit 0 |
| V4 | Secret/수신자 로그 스캔 | 로그에 API Key·앱비밀번호·수신자 전체주소 없음 |
| V5 | 이메일 발송 경로 | 실제 SMTP/Gmail send 호출 없음 (dry-run only) |

`scripts/loop_verify.py`가 V1–V3을 실행한다. V4–V5는 RULES + 위험 키워드 가드.

## 2. 조건부 게이트

| ID | 언제 | 명령 | 통과 |
|----|------|------|------|
| V6 | TASK가 수집/소스 관련 | `python3 scripts/core_sources_checklist.py` | exit 0 (네트워크 불가 환경은 SKIP 기록) |
| V7 | accuracy/필터 TASK | 관련 회귀 테스트 + matrix diff 악화 없음 | FP↑ 또는 recall 정책 위반 시 FAIL |
| V8 | 문서-only TASK | 마크다운/링크 깨짐만 확인 | V2/V3는 선택(기본은 스모크만) |

## 3. DONE / FAILED / BLOCKED 판정

| 결과 | 조건 |
|------|------|
| **DONE** | 필수 게이트 전부 통과 + (조건부 해당 시 통과) + 의도한 변경 존재 또는 “변경 불필요” 명시 |
| **FAILED** | 게이트 실패 + retry &lt; max → FIX TASK 생성 가능 |
| **BLOCKED** | 보호파일 터치, 발송 위험, Secret 누락, retry≥max, 종료조건 불명 |
| **SKIPPED** | diff 없음 + 이미 요구사항 충족 |

## 4. 품질 원칙 (도메인)

1. **recall 1순위:** 지역 단서 전무 → 버리지 말고 미상. “확실한 타지역”만 제외.
2. **최소 수정:** 한 TASK = 한 빈틈 클러스터. 대규모 리팩토링 금지.
3. **추측 라벨 금지:** 골든라벨 없는 건 L1에서 정답 단정 금지.
4. **대칭:** company_match ↔ monitor 그룹 판정 불일치는 결함 후보.

## 5. 드리프트 신호 (루브릭 자체)

- “게이트 없이 DONE” TASK가 생기면 루브릭/큐 버그.
- SKIP이 남발되면 검증이 너무 약하거나 TASK가 모호함.
- BLOCKED만 쌓이면 종료·권한 설계를 사람이 재검토 (L2).
