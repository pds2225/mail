# 4대 핵심 소스 완성 체크리스트

**기업마당 · K-Startup · NIPA · KITA** — mail 파이프라인에서 우선 완성해야 하는 4곳.

> 기준: 기능이 「있다」가 아니라 **이 체크리스트 PASS** = 실무 사용 가능.

## 실행

**프로그램:** PowerShell · **폴더:** `D:\mail`

```powershell
cd D:\mail
python scripts\core_sources_checklist.py
python scripts\core_sources_checklist.py --live   # 실수집 포함 (BIZINFO_API_KEY 필요)
python scripts\core_sources_checklist.py --json
```

`core_sources_checklist.py`는 4대 소스 **수집·상세보강** 전용이다.
`recall_zero_gate.py`는 판정 로직 게이트이지만, 최우선인 기업마당·K-Startup
파서 재생과 서울 AI 예비창업자 전달 경로는 의도적으로 중복 검사한다.

---

## 기업마당 (bizinfo)

| # | 항목 | 완성 기준 |
|---|------|-----------|
| 1 | config/sites.json | `bizinfo` enabled, `type=bizinfo_api` |
| 2 | API 설정 | `api_page_unit`≥100, `api_max_pages`≥20 (안전캡, 미달페이지면 종료) |
| 3 | 상세 보강 | `bizinfo.go.kr` ∈ `DETAIL_ENRICH_HOSTS`, 핵심 상세예산 우선 |
| 4 | 회귀 테스트 | `test_fetch_bizinfo_replay.py` · `test_core_sources_specialize.py` |
| 5 | 상세 파서 | `test_bizinfo_detail_enrich.py` (사업개요·신청기간) |
| 6 | 구조화 분류 | API 부가필드 → `support_field`/`target_field`/`region_field` 승격 |
| 7 | live (선택) | 수집 ≥100건, `bizinfo.go.kr` 상세링크 다수 |

**미완(v2):** API JSON 원문 저장, HTML 중복 소스 완전 제거 검증

---

## K-Startup (kstartup)

| # | 항목 | 완성 기준 |
|---|------|-----------|
| 1 | config/sites.json | `kstartup` enabled, `type=kstartup_html` |
| 2 | 다페이지 | 공공≥200 · 민간≥100 안전캡(공공 우선). 키=`page`. 종료=신규0×2 |
| 3 | 상세 보강 | `k-startup.go.kr` ∈ `DETAIL_ENRICH_HOSTS`, 핵심 상세예산 우선 |
| 4 | 회귀 테스트 | `test_fetch_kstartup_replay.py` (공공+민간) · `test_core_sources_specialize.py` |
| 5 | 목록 분류 | 카드 flag → `support_field` 조기부여, `kstartup_class` |
| 6 | live (선택) | 수집 ≥10건, k-startup 링크 존재 |

**미완(v2):** 외부「사업안내 바로가기」첨부 추적을 monitor 본선 통합

---

## NIPA (nipa)

| # | 항목 | 완성 기준 |
|---|------|-----------|
| 1 | config/sites.json | `nipa` enabled, `type=nipa_html` |
| 2 | 페이지 순회 | `max_pages` 상한 (전량 순회, 중복 시 종료) |
| 3 | 상세 보강 | `nipa.kr` ∈ `DETAIL_ENRICH_HOSTS` |
| 4 | 회귀 테스트 | `test_fetch_nipa_replay.py` (멀티페이지·중복종료) |
| 5 | live (선택) | 수집 ≥50건, **게시일 파싱률 ≥5%** (병목 가시화) |

**미완(v2):** 목록 게시일·상세 보강으로 날짜필터 누락 해소 (현재 병목)

---

## KITA (kita)

| # | 항목 | 완성 기준 |
|---|------|-----------|
| 1 | config/sites.json | `kita` enabled, `type=kita_html` |
| 2 | 공개 상세링크 | 로그인 전용 `OngoingView?sn=`을 공개 `OngoingDetail?bizAltkey=`로 정규화 |
| 3 | 상세 보강 | runtime adapter에서 `kita.net` ∈ `DETAIL_ENRICH_HOSTS`, 기타 핵심 예산(기본 40건) 초과분은 범용조회 제외 |
| 4 | 회귀 테스트 | `test_fetch_kita_replay.py` · `test_core_sources_specialize.py` (예산 우회 방지 포함) |
| 5 | 필드 계측 | 본문·날짜·신청기간·지원대상 읽기율을 매 실행 표본검사 |
| 6 | live (선택) | 수집 ≥3건, 공개 상세링크 ≥3건 |

---

## 숫자 요약

| 게이트 | PASS 의미 |
|--------|-----------|
| `core_sources_checklist` | 4소스의 설정+상세보강+pytest 전체 통과 |
| `+ --live` | 위 + 실수집 4항목 |
| `recall_zero_gate` | 알려진 recall 패턴 + 기업마당·K-Startup 재생 + 서울 AI 예비창업자 경로 전부 통과 |

## 최우선 페르소나 4중 방어

서울 거주 AI 예비창업자가 신청 가능한 공고는 아래 네 층을 모두 통과해야 한다.

1. 매일 `monitor.yml` 실수집과 P0 커버리지 탐지로 기업마당·K-Startup 장애·급락을 알린다.
2. `test_fetch_bizinfo_replay.py`와 `test_fetch_kstartup_replay.py`로 API/HTML 파서 회귀를 막는다.
3. `test_priority_recall_paths.py`로 두 소스의 구조화 필드가 `grp_prestartup_ai`의
   `included` 버킷까지 도달하는지 고정한다. K-Startup은 공공·민간을 모두 검사한다.
4. `test_prestartup_ai_digest_regression.py`의 실수신 기반 정·오추천 사례를
   기본 `recall_zero_gate.py`에 포함해 자동개발의 필수 차단 게이트로 사용한다.

---

## 권장 순서 (매일·야간)

1. `python scripts\core_sources_checklist.py`
2. `python scripts\recall_zero_gate.py`
3. (주 1회) `python scripts\core_sources_checklist.py --live`
