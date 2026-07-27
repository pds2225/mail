# Auto Dev Queue — TASKS

> 이 파일은 자동개발 큐의 작업 목록입니다.
> `scripts/auto_dev_queue.py`가 순차적으로 처리합니다.
> 1회 실행 시 PENDING 목록에서 1개만 처리합니다.

## PENDING


## RUNNING

## DONE
- TASK-013: loop:accuracy-defect 주간 matrix → s3_defects → G1 승인 후 TASK 분해 훅을 설계만 구체화한다 (코딩 금지, 사람 게이트).
- TASK-007: 정책자금 모듈 안정화 후 중진공 등 추가 기관 확장 가능성을 검토한다.
- TASK-006: 소진공 정책자금 페이지 구조 변경에 대비해 파서 selector 안정화를 검토한다.
- TASK-012: loop:gate-repair AUTO_DEV_AGENT 연동 전 FORCE_DONE 경로를 문서화하고 허위 DONE 회귀 테스트를 유지한다.
- TASK-011: loop:coding-fix GHA auto-dev-queue에 loop_verify 전후 게이트 스텝을 명시하고 Summary에 루프 5요소가 나오게 회귀 확인한다.
- TASK-005: Vercel 환경변수 목록과 GitHub Actions Secret 목록을 README 또는 docs/project/RULES.md에 정리한다.
- TASK-004: 메일 수신자 이메일 주소가 로그에 전체 노출되지 않도록 마스킹 원칙을 문서화한다.
- TASK-003: GitHub Actions Summary에 이번 실행 TASK, 결과, 다음 TASK를 표시하도록 auto_dev_queue 스크립트를 보완한다.
- TASK-002: docs/project/RULES.md에 실제 이메일 자동 발송 금지, preview/dry-run 우선 원칙을 추가한다.

- TASK-001: README에 Mail 프로젝트 Auto Dev Queue 사용법을 5줄로 추가한다.
- TASK-008: 지원사업 공고 필터링에 키워드 우선순위, 제외 사유, 남동구/공장/스마트공장 조건, 회귀 테스트를 추가한다.
- TASK-009: 공고 첨부 다운로더 chrome 필터에 미닫힘 footer/nav(malformed HTML) 가드 추가 — 매치 조상 텍스트가 body의 50% 이상이면 chrome으로 보지 않음(적대리뷰 wf_994a588f #1, 2026-07-08).
- TASK-010: eGov FileDown.do 합성 URL 컨텍스트 패스 폴백 — 루트 404/soft-404 시 상세 URL 첫 세그먼트(/portal 등) 접두로 1회 재시도(egov_context_fallback_url, 2026-07-08).

## FAILED

## BLOCKED
