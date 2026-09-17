# Mail Daily Review — 2026-07-30 (am)

- generated_at: 2026-09-17T13:40:24+0900
- cycle_key: `2026-07-30#am`
- overall: **FAIL**

## Checks (MDR = L규칙 스타일 일일 가드레일)

- [PASS] `MDR-001` 무증상 스킵(skip/coverage): PASS - coverage OK (source_coverage_20260730.json)
- [FAIL] `MDR-002` 핵심소스 0건: FAIL - 핵심소스 0건: bizinfo=0
- [PASS] `MDR-003` 08:54 외부발송 징후: PASS - 외부 머리글 미검출(로그/draft 기준; IMAP 본문 미검수)
- [FAIL] `MDR-004` delivery_state 당일키: FAIL - 2026-07-30#am (또는 legacy 2026-07-30) 키 0개 - 발송 미기록/무증상 스킵 의심
- [PASS] `MDR-005` 제목 badge 품질: PASS - 스캔 텍스트에 제목 badge 잔재 없음

## Inputs

- delivery_state: `D:\mail\.tmp\pytest-mail015-full\test_fail_core_zero_and_missin0\delivery_state.json`
- delivery_keys_total: `1`
- coverage: `D:\mail\.tmp\pytest-mail015-full\test_fail_core_zero_and_missin0\logs\source_coverage_20260730.json`
- run_duration_sec: `None`
- scan_files: `['D:\\mail\\.tmp\\pytest-mail015-full\\test_fail_core_zero_and_missin0\\logs\\source_coverage_20260730.json']`
