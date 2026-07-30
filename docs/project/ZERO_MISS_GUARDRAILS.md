# 누락제로 가드레일 7원칙 (TASK-06 / TASK-G06)

> Mail digest가 “맞는 공고를 조용히 빠뜨리지 않게” 지키기 위한 운영·개발 계약.
> 세부 구현은 `coverage_alert`·`skip_gate`·`detector_sites.json`·`monitor.yml` 에 흩어져 있고, 이 문서는 **원칙의 정본**이다.

## 7원칙

1. **발송 멱등 기준일 ≠ 재조회창**  
   `delivery_cycle_date` 는 실행 당일(KST, 회차 `#am`/`#pm` 포함). `days_back` 은 재조회에만 쓴다. 설정 변경이 발송을 멈추게 만들지 않는다.

2. **skip 이어도 감시(coverage)는 산다**  
   이미 보낸 회차라도 `SystemExit(0)` 으로 전체 종료하지 않는다. coverage / P0 / artifact / 필드품질은 계속 돌리고, 로그만 `skipped_fetch=true` + duration 을 남긴다.

3. **핵심소스 0건은 fail-closed**  
   기업마당·K-Startup 등 평소 수십~수백 건인 소스가 0건이면 “성공 0”으로 믿지 않는다. 수집실패·P0·send_hold 경로로 올린다. (`BIZINFO_ALLOW_EMPTY` 같은 명시 완화만 예외)

4. **알림·아티팩트 침묵 금지**  
   커버리지 baseline·source_coverage·P0 알림은 Actions artifact/`if-no-files-found: warn` 로 남긴다. “만들었는데 러너와 함께 사라짐”을 사고로 본다. 비정상 short-run 은 로그 경보.

5. **표시 오염이 판정을 흔들지 않는다**  
   제목 badge(file/새글 등), `author == title` 오염, 연도 생략 날짜의 꼬리 재매칭(작년→올해 오판)은 회귀 테스트로 잠근다. 주관기관은 지역 매칭에 쓰지 않는다.

6. **누락 < 누출보다 나쁘다(recall 우선)**  
   애매하면 보낸다(하단에 표시)·막지 않는다. `recall_zero_gate` / core_sources checklist 가 코딩 게이트다. exclude·차단 규칙은 제목 exact / 안전어 동반 시에만.

7. **Secret·실발송은 사람 게이트**  
   API Key/수신자 평문 로그 금지. auto-dev는 dry-run/preview만. 실발송 on/off·스케줄 변경·외부 발송 삭제는 사용자 확인 없이 하지 않는다.

## 빠른 점검

```text
python -m pytest tests/test_mail_review_ops_fixes.py tests/test_digest_fp_hardening.py -v
python scripts/recall_zero_gate.py
```

## 관련 경로

| 원칙 | 위치 |
|------|------|
| 1–2 | `monitor.delivery_cycle_date`, `mail_core/delivery/skip_gate.py`, `__main__` skip 경로 |
| 3 | `fetch_bizinfo`, `config/detector_sites.json`, `coverage_alert.classify_source_status` |
| 4 | `monitor.yml` artifact step, SHORT_RUN_ANOMALY 로그 |
| 5–6 | `strip_title_badges`, `_item`, `_parse_date_candidates`, `recall_zero_gate` |
| 7 | `docs/project/RULES.md` |
