# 문제발생 가능성 재점검 보고서

- **레포**: `pds2225/mail` (GitHub 원격 기준)
- **브랜치(작업)**: `feat/mail-coverage-recipient-safety`
- **점검일**: 2026-05-28
- **원칙**: HIGH → 코드 자동 수정 금지, NEEDS_USER 분리 / MEDIUM → 안전 보완 / LOW → 가능 시 수정

---

## 요약

| 위험도 | 건수 | 조치 |
|--------|------|------|
| HIGH | 4 | NEEDS_USER — 운영 워크플로·API 진입점 |
| MEDIUM | 9 | 본 브랜치에서 dry-run·review queue·커버리지 보완 |
| LOW | 5 | 문서·로그 형식 보완 |

---

## 1. 메일 발송 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| M-01 | `execute_monitor(allow_send=False)` 시 `send_to_list` 미호출 | LOW | `allow_send`가 True일 때만 그룹·원본 발송 | 유지 |
| M-02 | `send_email()` 자체는 가드 없이 SMTP 직접 호출 | **HIGH** | 테스트/스크립트가 `send_email`을 직접 호출하면 발송 가능 | **NEEDS_USER**: 운영 전 SMTP 가드 플래그 검토. 본 브랜치: `allow_send` 연동 가드 추가 |
| M-03 | `python monitor.py` → `main()`이 `allow_send=True` | **HIGH** | 로컬/CI에서 실수 실행 시 실발송 | **NEEDS_USER**: GHA `monitor.yml`이 `python monitor.py` 사용. 워크플로 변경은 승인 후 |
| M-04 | `api/run.py` → `monitor.main()` 실발송 | **HIGH** | Vercel HTTP 트리거 시 발송 | **NEEDS_USER** — API 엔드포인트 정책 변경 |
| M-05 | dry-run 테스트에서 mock 없이 `execute_monitor(allow_send=True)` | MEDIUM | 테스트 파일은 대부분 False | 신규 테스트는 `allow_send=False` 고정 |

---

## 2. seen_ids 저장 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| S-01 | `persist_seen=False` 시 저장 안 함 | LOW | 조건부 `save_seen_ids` | 유지 + dry-run 명시 로그 |
| S-02 | `save_seen_ids` 직접 호출 시 우회 | MEDIUM | streamlit 등 다른 진입점 가능 | dry-run: `MONITOR_NO_PERSIST_SEEN=1` 가드 추가 |
| S-03 | GHA가 `var/state/seen_ids.json` 커밋·푸시 | **HIGH** | `.github/workflows/monitor.yml` | **NEEDS_USER** — 운영 정책. 본 브랜치에서 변경 안 함 |
| S-04 | dry-run 중 파일 touch | MEDIUM | `.tmp` 저장 경로 | 가드 + 테스트로 미변경 검증 |

---

## 3. 오늘 공고 누락 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| D-01 | `include_date_unknown=false` 시 unknown 전량 제외 | **MEDIUM** | settings 기본값은 `true` | review queue 분리·보고서 기록 |
| D-02 | `posted_date` 없으면 D-1 매칭 불가 | **MEDIUM** | exportvoucher 등 상세 보강 후에도 빈 경우 존재 | unknown → review queue, 위험도 라벨 |
| D-03 | 날짜 파싱 실패 → unknown | MEDIUM | `ValueError` 시 unknown | review queue + `today_notice_missing_risk_report` |
| D-04 | D-1 = 직전 영업일 (오늘 등록 공고 제외) | MEDIUM | 의도된 설계 | 보고서에 기준일 명시 |
| D-05 | 타임존 KST vs 사이트 UTC | LOW | KST 고정 | 문서화 |

---

## 4. 중복 제거 오탐 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| U-01 | 제목 유사도(10자 부분일치)로 다른 공고 병합 | **MEDIUM** | `dedup_items` | 테스트·보고서에 제거 건수 기록 |
| U-02 | `stable_id(title+link)` — URL 변경 시 다른 ID | MEDIUM | 사이트별 상이 | 문서화, URL 우선 ID 사이트는 안전 |
| U-03 | 공고 ID 없을 때 `stable_id(title)` 충돌 | MEDIUM | html_table 일부 | 커버리지 리포트 `missing_id` 카운트 |
| U-04 | `MAX_SEEN_IDS=1000` 초과 시 오래된 ID evict | MEDIUM | 재발송 가능 | **NEEDS_USER** 정책 검토 |

---

## 5. 수집 누락 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| C-01 | `fetch_all` 병렬 — 사이트 실패가 로그만 | **MEDIUM** | 전체 성공처럼 보일 수 있음 | 사이트별 커버리지 리포트 추가 |
| C-02 | `enabled:false` 사이트 미수집 | LOW | 의도 | 리포트에 enabled/disabled 구분 |
| C-03 | 알 수 없는 `type` → 0건 | MEDIUM | 경고 로그만 | 리포트 `높음` 위험 |
| C-04 | Playwright 미설치 시 pw_* 0건 | MEDIUM | `_pw_noop` | 리포트에 playwright 상태 |
| C-05 | Cloud VM TLS 일부 사이트 실패 | MEDIUM | AGENTS.md 기재 | 리포트 failure 사유 |

---

## 6. 수신자 설정 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| R-01 | 수신자: `config/groups.json` / `config/settings.json` | LOW | 설정 파일 기반 | `ADD_RECIPIENT_GUIDE.md` |
| R-02 | 이메일 형식 검증 없음 | MEDIUM | 잘못된 주소 SMTP 실패 | `validate_recipients()` 추가 |
| R-03 | 중복 수신자 | LOW | 미제거 | dedupe 추가 |
| R-04 | 로그 마스킹 `_mask_email` | LOW | monitor.py 존재 | dry-run 출력에 적용 |
| R-05 | config/groups.json에 실주소 하드코딩 | MEDIUM | 레포에 포함됨 | **임의 추가 금지** — 가이드만 제공 |

---

## 7. GitHub 개발 위험

| ID | 항목 | 위험도 | 현황 | 조치 |
|----|------|--------|------|------|
| G-01 | `D:\mail` 경로 (customer_intake) | MEDIUM | `customer_intake/sheets_writer.py` 안내 문구 | monitor 경로는 `Path(__file__)` — 안전 |
| G-02 | `api/run.py` → `/tmp/monitor_ws` | LOW | Vercel 전용 | monitor 본편과 분리 |
| G-03 | `run_monitor.bat` Windows 로컬 | LOW | 사용 안 함(원격 작업) | 무시 |
| G-04 | `var/logs/` 미존재 | LOW | — | `var/logs/.gitkeep` + gitignore |

---

## NEEDS_USER (HIGH — 자동 수정 안 함)

1. **`.github/workflows/monitor.yml`**: `python monitor.py` 실발송 + `seen_ids` 커밋. dry-run 워크플로 분리 또는 `scripts/monitor_dry_run.py` 사용 여부 결정.
2. **`api/run.py`**: HTTP 트리거 실발송 정책.
3. **`monitor.main()` 기본값**: `allow_send=True` — CLI/환경변수로 분리 검토.
4. **`MAX_SEEN_IDS` eviction** 정책.

---

## 본 브랜치에서 진행하는 안전 작업

- `scripts/monitor_dry_run.py` — `allow_send=False`, `persist_seen=False`, 커버리지·review 리포트
- `date_unknown` review queue 분리 및 `var/logs/review_queue_YYYYMMDD.md` 생성
- `validate_recipients()` + 테스트
- SMTP/seen_ids 가드 (dry-run 플래그)
- 문서: `ADD_RECIPIENT_GUIDE.md`, 커버리지 리포트 샘플

---

## 롤백

```bash
git checkout main
git branch -D feat/mail-coverage-recipient-safety
```

생성된 `var/logs/*.md`는 커밋하지 않아도 됨 (로컬/CI 산출물).
