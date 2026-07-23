# Design: govsupport-mailing-v2 — 정부지원사업 메일링 개선

**Created**: 2026-05-31
**Architecture**: Option C — 실용균형
**PDCA Phase**: Design

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | 부적합 공고 발송으로 신뢰도 저하, 수집 누락으로 기회 손실. 운영자 수동 보정 부담. |
| WHO | 인천 남동구 제조/수출 기업 운영자 (1차: test-recipient@example.test). |
| RISK | (1) 오발송 (2) monitor.py 회귀 (3) 외부 사이트 SSL/TLS 변화. |
| SUCCESS | FP 50% ↓, 사이트 진단 리포트, 그룹/수신자/필터 UI 자가관리. |
| SCOPE | monitor.py 최소수정, 신규 3모듈 추가, streamlit 페이지 1개 추가, **테스트 발송은 test-recipient@example.test 1개로만**. |

## 1. Overview

기존 mail 리포의 안정성을 보존하면서, **filter 후처리 점수화** + **선택적 LLM 2차 판정** + **사이트 진단 리포트** + **운영자 관리 UI**를 추가한다. monitor.py는 신규 모듈을 호출하는 hook 형태로만 수정한다.

## 2. Architecture (Option C)

```
monitor.py (기존, 최소수정)
    ├─ filter_for_group_with_diagnostics()  # 1차 키워드 필터 (기존)
    └─ [NEW HOOK] scoring.score_and_filter()  # 2차 점수+LLM 판정 (신규)
            ├─ scoring.compute_score()           # 가중치 점수 계산
            └─ scoring.llm_relevance_check()     # LLM 2차 판정 (옵션)

streamlit_app.py (기존)
    └─ [NEW PAGE] ui_admin.render()           # 그룹/수신자/필터 편집 (신규)

scripts/run_site_diagnostic.py (신규 진입점)
    └─ site_diagnostic.diagnose_all()         # 82개 사이트 dry-run + 리포트
```

## 3. Module Map (Implementation Guide §11.3 Session Guide)

| Module | File | LOC | 역할 | Session |
|--------|------|-----|------|---------|
| module-1 | `scoring.py` | ~150 | 점수 계산 + LLM 2차 판정 + 임계값 | S1 |
| module-2 | `site_diagnostic.py` | ~120 | 사이트별 수집 진단 + Markdown 리포트 | S1 |
| module-3 | `ui_admin.py` | ~180 | streamlit 그룹/수신자/필터 편집 페이지 | S2 |
| module-4 | `scripts/run_site_diagnostic.py` | ~30 | 진단 진입점 | S1 |
| module-5 | `groups.json` 스키마 확장 | ~10 | `score_threshold`, `weights` 필드 추가 | S1 |
| module-6 | `monitor.py` 통합 (hook 호출 1줄) | ~5 | 후처리 hook 호출만 추가 | S3 (분리) |
| module-7 | `streamlit_app.py` 통합 (sidebar 메뉴 1줄) | ~3 | ui_admin 페이지 등록 | S3 (분리) |

**Session Plan**:
- **S1 (이번 세션)**: module-1, 2, 4, 5 — 외부 모듈 + 데이터 스키마
- **S2 (별도)**: module-3 — UI 편집 페이지
- **S3 (별도)**: module-6, 7 — 기존 파일 통합 (회귀 위험 분리)

## 4. Data Schema (groups.json 확장)

기존 필드 유지하면서 신규 옵션 필드 추가 (하위 호환).

```json
{
  "id": "grp_default",
  "active": true,
  "required_conditions": { ... },
  "or_keywords": [...],
  "exclude_keywords": [...],
  "priority_keywords": [...],
  "recipients": [...],
  "score_threshold": 60,          // NEW: 0~100, 미만 제외 (기본 50)
  "weights": {                    // NEW: 점수 가중치 (옵션)
    "priority_match": 30,
    "or_keyword_match": 5,
    "exclude_penalty": -50,
    "region_match": 20
  },
  "llm_check_enabled": true,      // NEW: LLM 2차 판정 활성화 (기본 false)
  "llm_check_threshold_band": [40, 70]  // NEW: 이 점수대만 LLM 호출 (비용 절감)
}
```

## 5. Function Signatures

### scoring.py
```python
def compute_score(item: dict, group: dict) -> dict:
    """Returns {'score': int, 'breakdown': dict, 'reasons': list[str]}"""

def llm_relevance_check(item: dict, group: dict) -> dict:
    """Optional LLM call. Returns {'is_relevant': bool, 'confidence': float, 'reason': str}.
       Only called for items in llm_check_threshold_band."""

def score_and_filter(items: list[dict], group: dict) -> dict:
    """Main entry. Returns {'passed': [...], 'rejected': [...], 'audit': [...]}.
       Backward compatible if 'score_threshold' missing in group."""
```

### site_diagnostic.py
```python
def diagnose_site(site: dict, timeout: int = 15) -> dict:
    """Returns {'site_id': str, 'status': 'ok|fail|empty', 'items_count': int,
                'error_type': str|None, 'elapsed_ms': int}"""

def diagnose_all(sites: list[dict]) -> str:
    """Returns markdown report path. Writes to reports/site_diagnostic_YYYYMMDD.md"""
```

### ui_admin.py
```python
def render():
    """Streamlit page. Renders group editor: list groups, add/edit/delete,
       edit recipients (mask emails), edit keywords, set score_threshold."""
```

## 6. UI Flow (ui_admin)

```
[페이지 진입]
   ├─ 그룹 목록 (id, name, active, recipients_count)
   ├─ [그룹 선택] → 편집 패널
   │     ├─ 기본정보 (name, active)
   │     ├─ recipients (추가/삭제, 이메일 마스킹 미리보기)
   │     ├─ keywords (or/exclude/priority, 줄바꿈 입력)
   │     ├─ score_threshold (slider 0~100)
   │     └─ [저장] → groups.backup.{ts}.json 자동 백업 후 groups.json 갱신
   └─ [새 그룹 추가] → 빈 그룹 생성
```

## 7. Test Plan (§8)

| Level | Test | 도구 |
|-------|------|------|
| L1 unit | `scoring.compute_score()` 점수 케이스 5종 (priority/or/exclude/region/empty) | pytest |
| L1 unit | `score_and_filter()` 하위호환 (필드 누락 시 통과) | pytest |
| L2 integ | `diagnose_site()` mock httpx로 ok/timeout/empty 케이스 | pytest |
| L3 e2e | dry-run으로 monitor 전체 흐름에서 점수 적용 결과 비교 | 수동 |
| L4 safety | 테스트 발송 시 recipients = test-recipient@example.test 1개만 검증 | 수동 |

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM 비용 | `llm_check_threshold_band`로 회색지대만 호출, 일일 상한 추가 |
| groups.json 손상 | 저장 시 자동 백업 (`groups.backup.{ts}.json`) |
| monitor.py 회귀 | hook 호출 1줄만 추가, score_threshold 미존재 시 기존 동작 유지 |
| 사이트 진단 장시간 | 사이트별 timeout 15초, 병렬 호출은 v2 이후 |
| 오발송 | `confirm_send="SEND"` 가드 유지, 테스트 단계 recipients = test-recipient@example.test |

## 9. Implementation Order

S1 (이번 세션):
1. scoring.py 생성 (compute_score → llm_relevance_check → score_and_filter)
2. site_diagnostic.py 생성
3. scripts/run_site_diagnostic.py 생성
4. groups.json 스키마 확장 (`score_threshold`, `weights` 추가, 백업 후)
5. tests/test_scoring.py 단위 테스트

S2 (별도): ui_admin.py
S3 (별도): monitor.py / streamlit_app.py 통합

## 10. Next Step

`/pdca do govsupport-mailing-v2 --scope module-1,module-2,module-4,module-5`
