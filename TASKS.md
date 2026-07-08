# Auto Dev Queue — TASKS

> 이 파일은 자동개발 큐의 작업 목록입니다.
> `scripts/auto_dev_queue.py`가 순차적으로 처리합니다.
> 1회 실행 시 PENDING 목록에서 1개만 처리합니다.

## PENDING

- TASK-002: RULES.md에 실제 이메일 자동 발송 금지, preview/dry-run 우선 원칙을 추가한다.
- TASK-003: GitHub Actions Summary에 이번 실행 TASK, 결과, 다음 TASK를 표시하도록 auto_dev_queue 스크립트를 보완한다.
- TASK-004: 메일 수신자 이메일 주소가 로그에 전체 노출되지 않도록 마스킹 원칙을 문서화한다.
- TASK-005: Vercel 환경변수 목록과 GitHub Actions Secret 목록을 README 또는 RULES.md에 정리한다.
- TASK-006: 소진공 정책자금 페이지 구조 변경에 대비해 파서 selector 안정화를 검토한다.
- TASK-007: 정책자금 모듈 안정화 후 중진공 등 추가 기관 확장 가능성을 검토한다.
- TASK-009: 공고 첨부 다운로더 chrome 필터에 미닫힘 footer/nav(malformed HTML) 가드 추가 — 매치된 조상 텍스트가 body의 ~50% 이상이면 chrome으로 보지 않음(적대리뷰 wf_994a588f 확정 #1, 관측 경고 로그는 반영됨).
- TASK-010: eGov FileDown.do 합성 URL의 컨텍스트 패스 배포(사이트가 /portal/ 등 하위에 배포된 경우) 폴백 검토 — 합성 404 시 detail_url 경로 기준 재시도(적대리뷰 #2 잔여).

## RUNNING

## DONE

- TASK-001: README에 Mail 프로젝트 Auto Dev Queue 사용법을 5줄로 추가한다.
- TASK-008: 지원사업 공고 필터링에 키워드 우선순위, 제외 사유, 남동구/공장/스마트공장 조건, 회귀 테스트를 추가한다.

## FAILED

## BLOCKED
