# 3대 핵심 소스 완성 체크리스트

**기업마당 · K-Startup · NIPA** — mail 파이프라인에서 우선 완성해야 하는 3곳.

> 기준: 기능이 「있다」가 아니라 **이 체크리스트 PASS** = 실무 사용 가능.

## 실행

**프로그램:** PowerShell · **폴더:** `D:\mail`

```powershell
cd D:\mail
python scripts\core_sources_checklist.py
python scripts\core_sources_checklist.py --live   # 실수집 포함 (BIZINFO_API_KEY 필요)
python scripts\core_sources_checklist.py --json
```

`recall_zero_gate.py`(판정 로직 5/5)와 **별도** — 3대 소스 **수집·상세보강** 전용.

---

## 기업마당 (bizinfo)

| # | 항목 | 완성 기준 |
|---|------|-----------|
| 1 | config/sites.json | `bizinfo` enabled, `type=bizinfo_api` |
| 2 | API 설정 | `api_page_unit`≥100, `api_max_pages`≥1 |
| 3 | 상세 보강 | `bizinfo.go.kr` ∈ `DETAIL_ENRICH_HOSTS` |
| 4 | 회귀 테스트 | `test_fetch_bizinfo_replay.py` |
| 5 | 상세 파서 | `test_bizinfo_detail_enrich.py` (사업개요·신청기간) |
| 6 | live (선택) | 수집 ≥100건, `bizinfo.go.kr` 상세링크 다수 |

**미완(v2):** API JSON 원문 저장, HTML 중복 소스 완전 제거 검증

---

## K-Startup (kstartup)

| # | 항목 | 완성 기준 |
|---|------|-----------|
| 1 | config/sites.json | `kstartup` enabled, `type=kstartup_html` |
| 2 | 다페이지 | `max_pages`≥2 (공공 PBC010 + 민간 PBC020) |
| 3 | 상세 보강 | `k-startup.go.kr` ∈ `DETAIL_ENRICH_HOSTS` |
| 4 | 회귀 테스트 | `test_fetch_kstartup_replay.py` (공공+민간) |
| 5 | live (선택) | 수집 ≥10건, k-startup 링크 존재 |

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

## 숫자 요약

| 게이트 | PASS 의미 |
|--------|-----------|
| `core_sources_checklist` | 3소스 × (설정+상세보강+pytest) = **오프라인 13항목** |
| `+ --live` | 위 + 실수집 3항목 |
| `recall_zero_gate` | 알려진 recall 패턴 **5/5** (별도) |

---

## 권장 순서 (매일·야간)

1. `python scripts\core_sources_checklist.py`
2. `python scripts\recall_zero_gate.py`
3. (주 1회) `python scripts\core_sources_checklist.py --live`
