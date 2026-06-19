# Changelog

## 2026-06-19

- Documented the `monitor.py` operations runbook: dotenv loading, dry-run behavior, `--only-to` test-send guard, recipient validation, review reports, and decision-matrix filter coverage.
- Clarified support amount filtering pitfalls, including non-money `만` expressions that must not be treated as grant amounts.

## 2026-05-27

- Added grant notice classification fields, keyword scoring, priority keyword handling, deadline status, Incheon Namdong-gu eligibility, factory/smart-factory matching, and dry-run excluded summaries.
- Added regression tests for administrative notices, guideline/manual/education/info-session exclusions, voucher priority behavior, district restrictions, factory conditions, and smart-factory cases.
- Updated the default Incheon export group keywords and documented the filtering policy.

## 2026-05-26

- Added SEMAS policy loan notice scanner under `loan/`.
- Added Markdown report generation, recent notice filtering, duplicate state handling, and guarded email sending.
- Added manual GitHub Actions workflow and pytest coverage for parser, report, and mail safety behavior.

