# monitor.py 분할 계획서

**작성일:** 2026-07-21
**대상:** D:\mail\monitor.py (6,420줄, 함수 223개)
**목적:** 비개발자용 한글 주석 추가 전, 모듈 분할로 설명서 작성 용이성 확보
**원칙:** 원문 1줄도 건드리지 않고 계획만 수립. 실제 분할은 별도 세션에서.

---

## 1. 현재 구조 (라인 경계)

| 구간 | 라인 | 내용 | 줄수 |
|---|---|---|---|
| **A. 임포트·상수** | 1-169 | import, 환경변수, 상수(지역·키워드·라벨 매핑) | 169 |
| **B. 지역 판정** | 170-1027 | 지역 탐지·제외·regex·날짜 파싱·제목 분류 | 858 |
| **C. 상세보강** | 1027-1428 | HTML 파싱·표 추출·상세 페이지 크롤링·보강 | 401 |
| **D. 설정 로딩** | 1428-1530 | seen_ids·sites·groups·settings 로드 | 103 |
| **E. HTTP 헬퍼** | 1531-1624 | SSL 폴백·HTTP GET·BeautifulSoup·_item() | 94 |
| **F. 사이트 수집기** | 1624-3269 | 20개 사이트별 fetch 함수 | 1,646 |
| **G. 커버리지 보고** | 3269-3392 | 커버리지 품질·리스크 레벨 | 124 |
| **H. 중복제거·날짜 필터** | 3392-3640 | dedup·date_filter·unknown 정책 | 249 |
| **I. 분류·필터링** | 3640-4686 | classify_region·evaluate_notice·filter_for_group | 1,047 |
| **J. 렌더링** | 4686-4980 | 이메일 본문 작성·CLAUDE 요약·피드백 블록 | 295 |
| **K. 발송** | 4980-5256 | SMTP·Gmail Draft·수신자별 대기열 | 277 |
| **L. 알림·워치리스트** | 5256-5421 | alert_email·alert_ntfy·워치리스트 | 166 |
| **M. 실행 루프** | 5421-5764 | execute_monitor() 메인 함수 | 344 |
| **N. CLI·리포트** | 5764-6420 | main()·다양한 리포트 작성기 | 657 |

---

## 2. 분할 대상 모듈 (5개)

### 2-1. `_common.py` — 공유 상수·유틸 (~500줄)

**라인 범위:** A(일부) + B(일부) + E(일부)
**의존성:** 독립 (다른 모듈이 이걸 import)

| 함수/상수 | 현재 위치 | 역할 |
|---|---|---|
| `KST`, `HTTP_HEADERS` | A (104-137) | 시간대·HTTP 헤더 |
| `KNOWN_REGIONS`, `SUPPORT_TYPE_RULES` | A (139-168) | 지역·지원유형 상수 |
| `KSTARTUP_DETAIL_LABELS`, `BIZINFO_DETAIL_LABELS` | A (176-195) | 상세보강 라벨 매핑 |
| `_NON_GG_KWON_RE` 등 regex 10종 | A (199-264) | 지역 탐지 정규식 |
| `stable_id()`, `norm()`, `html_pre()` | A (668-674) | 범용 유틸 |
| `_RedactSecretsFilter` | A (643-667) | 로그 비밀정보 가리기 |
| `_hangul_len()` | B (1027) | 한글 글자 수 계산 |
| `_legacy_ssl_ctx()` | E (1541-1551) | SSL 폴백 컨텍스트 |
| `EMAIL_RE` | A (110) | 이메일 정규식 |

**import 할 것:** `datetime`, `re`, `logging`, `ssl`, `hashlib`, `unicodedata`

### 2-2. `_region.py` — 지역 판정 로직 (~850줄)

**라인 범위:** B (170-1027)
**의존성:** `_common.py`에서 `KNOWN_REGIONS`, `_NON_GG_*_RE`, `_APPLICANT_*` 등 import

| 함수 | 역할 |
|---|---|
| `_applicant_restricted_regions()` | 신청자 지역 한정 탐지 |
| `_strip_contact_spans()` | 문의/운영 구간 제거 |
| `is_admin_noise()` | 행정공지 필터 |
| `is_report_junk()` | 보고서/매뉴얼 필터 |
| `non_notice_reason()` | 비공고 판별 |
| `normalize_title()` | 제목 정규화 |
| `is_imminent()` | 마감 임박 판별 |
| `extract_date_from_text()` | 텍스트→날짜 추출 |
| `_parse_date_candidates()` | 날짜 후보 파싱 |
| `_parse_period_dates()` | 신청기간 파싱 |
| `_posted_date()` | 게시일 추출 |
| `_deadline_shortform()` | 마감 약식 |
| `extract_application_period()` | 신청기간 추출 |
| `resolve_item_deadline()` | 마감 확정 |
| `_detect_target_regions()` | 대상 지역 탐지 |
| `_resolve_applicant_region_scope()` | 신청자 범위 해석 |

**export:** 전부 `_region.py`에서 `from _region import ...` 로 monitor.py에 재노출

### 2-3. `_fetchers.py` — 사이트 수집기 (~1,700줄)

**라인 범위:** E(일부) + F (1554-3269)
**의존성:** `_common.py` (상수), `net_guard` (SSRF 가드), `httpx` (HTTP)

| 함수 | 역할 |
|---|---|
| `_http_get()` | HTTP GET (SSL 폴백) |
| `_soup()` | HTML 파싱 |
| `_item()` | 아이템 생성 유틸 |
| `fetch_bizinfo()` | 기업마당 API |
| `fetch_kstartup()` | K-Startup HTML |
| `fetch_html_generic()` | 범용 HTML 수집 |
| `fetch_semas_loan_ols()` | 소진공 정책자금 |
| `fetch_smart_factory()` | 스마트공장 |
| `fetch_ripc()` | RIPC |
| `fetch_kotra_biz()` | KOTRA |
| `fetch_kosme()` | KOSME |
| `fetch_kita()` | KITA |
| `fetch_iris()` | IRIS |
| `fetch_smtech()` | SMTECH |
| `fetch_tipa()` | TIPA |
| `fetch_kocca_pims()` | KOCCA 공고 |
| `fetch_kocca_bbs()` | KOCCA 금융 |
| `fetch_gtp()` | 경기TP |
| `fetch_gsp()` | 경기스타트업 |
| `fetch_ccei()` | 창조경제혁신센터 |
| `fetch_itp()` | 인천테크노파크 |
| `fetch_nipa()` | NIPA |
| `fetch_mss()` | 중기부 |
| `fetch_bizok()` | 비즈오케이 |
| `fetch_incheon_city()` | 인천시 |
| `fetch_mssmiv()` | MSSMIV |
| `fetch_exportvoucher()` | 수출바우처 |
| `fetch_keit()` | KEIT |
| `fetch_sba()` | SBA |
| `fetch_myfair()` | 마이페어 |
| `fetch_hanyang_startup()` | 한양대 |
| + Playwright 6개 | `_pw_fetch_*` |

**의존성 고려사항:**
- `net_guard.check_url()` / `net_guard.is_safe()` — SSRF 가드
- `BIZINFO_API_KEY`, `DATA_GO_KR_KEY` — 환경변수 (monitor.py에서 주입)
- `_HTTP_RETRIES`, `_HTTP_RETRY_BACKOFF` — 재시도 설정
- `HTTP_HEADERS` — 요청 헤더
- `_page_stat()` — 페이지네이션 계측 (G에서 정의)
- `KSTARTUP_DETAIL_LABELS`, `BIZINFO_DETAIL_LABELS` — _common에서

**해결 방안:** `_fetchers.py`는 `fetch_all()` 호출 시 `monitor.py`가 환경변수·설정을 파라미터로 전달

### 2-4. `_classify.py` — 분류·필터링 (~1,050줄)

**라인 범위:** H(일부) + I (3549-4686)
**의존성:** `_common.py` (상수), `_region.py` (지역 함수)

| 함수 | 역할 |
|---|---|
| `classify_support_type()` | 지원유형 분류 |
| `classify_deadline_status()` | 마감 상태 분류 |
| `classify_region_for_group()` | 그룹별 지역 분류 |
| `classify_region()` | 범용 지역 분류 |
| `keyword_match()` | 키워드 매칭 |
| `region_match()` | 지역 매칭 |
| `support_match()` | 지원유형 매칭 |
| `evaluate_notice()` | **핵심**: 공고 종합 판정 |
| `filter_for_group()` | 그룹별 필터링 |
| `split_unknown_by_policy()` | 날짜 미상 정책 |
| `extract_business_year_requirement()` | 업력 추출 |
| `extract_support_amount()` | 지원금액 추출 |

**의존성 고려사항:**
- `evaluate_notice()`가 `_region.py`, `_common.py`, `scoring.py`의 `DEFAULT_WEIGHTS`를 참조
- `filter_for_group()`이 `company_match.py`의 `match_for_company()`를 선택적으로 호출

### 2-5. `_render.py` — 렌더링 + 발송 (~570줄)

**라인 범위:** J + K + L (4686-5421)
**의존성:** `_common.py`, `_classify.py` (결과 dict)

| 함수 | 역할 |
|---|---|
| `render_all()` | 메일 본문 생성 |
| `mail_topic()` | 메일 제목 |
| `claude_summarize()` | AI 요약 |
| `_render_feedback_block()` | 피드백 블록 |
| `send_email()` | SMTP 발송 |
| `save_draft_to_gmail()` | Gmail 초안 |
| `draft_to_list()` | 초안 일괄 발송 |
| `send_to_list()` | 메일 일괄 발송 |
| `deliver_with_outbox()` | 대기열 발송 |
| `alert_email()` | 오류 알림 |
| `alert_ntfy()` | 모바일 알림 |
| `load_watchlist()` | 워치리스트 |

---

## 3. 남는 monitor.py (~2,200줄)

모든 모듈을 빼고 나면 monitor.py에는 남는 것:

```
- imports (모든 모듈을 여기서 import)
- 환경변수 로드 (BIZINFO_API_KEY, ANTHROPIC_API_KEY 등)
- 설정 로딩 (load_sites, load_groups, load_settings, seen_ids)
- 커버리지 보고 (write_coverage_report 등)
- execute_monitor() — 메인 실행 루프
- main() — CLI 진입점
```

이게 **"오케스트레이터"** 역할 — 각 모듈을 호출하는 흐름만 남습니다.

---

## 4. 검증 전략

분할 시 **반드시 확인할 것:**

| 검증 | 방법 |
|---|---|
| 기존 테스트 739개 통과 | `python -m pytest -q` |
| CI 워크플로 경로 확인 | `tests/test_monitor.py`가 여전히 `from monitor import ...` 가능 |
| import 체인 깨짐 | `python -c "import monitor"` (환경변수 설정 후) |
| 70곳 `import monitor` 호환 | monitor.py에서 `_region`, `_fetchers` 등을 `from X import *` 로 재노출 |
| 자동 발송 동작 | `--dry-run` 모드로 1회 실행 |

---

## 5. 리스크 평가

| 리스크 | 수준 | 대응 |
|---|---|---|
| 70곳 import 깨짐 | **높음** | monitor.py에 모든 public 이름을 재노출 (별칭) |
| CI 빨간불 | **중간** | test.yml 미수정 (import 경로 동일) |
| 환경변수 누락 | **중간** | _fetchers.py에 BIZINFO_API_KEY 등 파라미터로 전달 |
| 테스트 실패 | **낮음** | 각 모듈별 독립 테스트 + 전체 회귀 테스트 |
| 발송 정지 | **낮음** | 분할은 "라인 이동"이지 "로직 변경" 아님 → 동작 동일 |

---

## 6. 실행 순서 (별도 세션)

```
1단계: _common.py 추출 → py_compile + import 검증
2단계: _region.py 추출 → test_region_* 테스트
3단계: _fetchers.py 추출 → test_fetch_* 테스트
4단계: _classify.py 추출 → test_monitor.py 핵심 테스트
5단계: _render.py 추출 → test_mail_* 테스트
6단계: 전체 회귀 테스트 739개
7단계: PR 생성 + CI green 확인 + 병합
```

각 단계마다 **`python -m py_compile`** + **관련 테스트**를 반드시 통과해야 다음 단계로.

---

## 7. 분할 후 예상 효과

```
현재:  monitor.py 6,420줄 (모든 것이 한 파일)
분할:  _common.py    ~500줄  (상수·유틸)
       _region.py    ~850줄  (지역 판정)
       _fetchers.py ~1,700줄  (수집기)
       _classify.py ~1,050줄  (분류·필터)
       _render.py    ~570줄  (렌더링·발송)
       monitor.py  ~2,200줄  (오케스트레이터)
```

각 모듈을 비개발자용으로 **독립 설명**할 수 있게 됩니다.
