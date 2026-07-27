# Changelog

## 2026-07-24

- 루트의 핵심 모듈을 `mail_core/` 하위 도메인 패키지로 재구성했습니다.
- 설정 파일은 `config/`, 런타임 상태·로그·리포트는 `var/`로 분리했습니다.
- Python import, Vercel API, GitHub Actions, Streamlit/웹, 자동화 스크립트와 문서 경로를 새 구조에 맞게 갱신했습니다.
- 저장소 구조와 경로 해석을 검증하는 회귀 테스트를 추가했습니다.
- GitHub Actions 실행 간 중복 발송 방지를 위해 필수 발송 상태 파일은 `var/` 아래에서 계속 추적하도록 예외 처리했습니다.

## 2026-05-27

- Added grant notice classification fields, keyword scoring, priority keyword handling, deadline status, Incheon Namdong-gu eligibility, factory/smart-factory matching, and dry-run excluded summaries.
- Added regression tests for administrative notices, guideline/manual/education/info-session exclusions, voucher priority behavior, district restrictions, factory conditions, and smart-factory cases.
- Updated the default Incheon export group keywords and documented the filtering policy.

## 2026-05-26

- Added SEMAS policy loan notice scanner under `loan/`.
- Added Markdown report generation, recent notice filtering, duplicate state handling, and guarded email sending.
- Added manual GitHub Actions workflow and pytest coverage for parser, report, and mail safety behavior.
