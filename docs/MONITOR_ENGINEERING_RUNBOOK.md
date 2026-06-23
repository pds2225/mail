# Monitor Engineering Runbook

`monitor.py` is the support-notice pipeline for the Mail project. It collects notices,
deduplicates them, filters them by date and recipient group rules, summarizes matching
items with Claude, and sends email when explicitly run in send mode.

This runbook records source-verified behavior for developers changing collectors,
site configuration, or matching policy.

## Pipeline

1. Load configuration from `sites.json`, `groups.json`, `companies.json`, and `settings.json`.
2. Fetch enabled sites through the collector registered in `FETCHERS`.
3. Enrich detail pages for links under `exportvoucher.com`, `k-startup.go.kr`, and `nipa.kr`
   up to `MAX_DETAIL_ENRICH` items per run.
4. Deduplicate by notice ID and `seen_ids.json`.
5. Apply posted-date policy from `settings.json`.
6. Evaluate each active group into `included`, `region_unknown`, `review`, or `excluded`.
7. In send mode only, summarize included items and send mail. Region-unknown items are
   rendered as a "지역 미상 - 확인 필요" section at the bottom of the same group email.
8. Persist `seen_ids.json` only when persistence is allowed.

## Public Configuration Interfaces

### `sites.json`

Each site entry must have:

- `id`: stable prefix for generated item IDs.
- `name`: display name in logs/reports/email.
- `type`: collector key registered in `FETCHERS`.
- `url`: list or API URL used by the collector.
- `enabled`: false skips the site.
- `is_aggregator`: true for portals that mirror notices from many sources.

Supported collector keys include API/specialized collectors such as `bizinfo_api`,
`kstartup_html`, `nipa_html`, `itp_html`, `semas_loan_ols`, and generic collectors
`html_table` / `html_card`.

### Generic HTML Selectors

For `html_table` and `html_card`, `fetch_html_generic()` reads `selectors`.

Common fields:

```json
{
  "selectors": {
    "row": "table tbody tr",
    "link": "a",
    "title": "td.subject",
    "author": "td.author",
    "description": "td.desc",
    "date": "td.posted",
    "deadline": "td.deadline"
  }
}
```

If a list item uses `javascript:`, `#`, or an otherwise non-detail URL, configure link
synthesis instead of accepting skipped rows:

```json
{
  "type": "html_table",
  "url": "https://example.go.kr/board/list",
  "selectors": {
    "row": "table tbody tr",
    "link": "a.detail",
    "link_template": "/board/view?id={0}",
    "link_arg_re": "goView\\('(\\d+)'\\)"
  }
}
```

Rules:

- `link_template` is formatted with extracted groups and resolved with `urljoin(site["url"], ...)`.
- Use `link_id_attr` when the ID is in an anchor attribute such as `data-id`.
- Use `link_arg_re` when the ID is in `onclick` or `href`.
- If a bad link has no synthesis rule, the row is skipped for backward compatibility.

## Recent Collector Behavior

### NIPA

`fetch_nipa()` uses `type: "nipa_html"` and paginates with `curPage` up to `max_pages`
from the site config, defaulting to `300`. It stops when a page produces no new detail
links. Item IDs prefer `nttNo` when present (`nipa_<nttNo>`). Detail enrichment later
pulls text from `.detail` or `.tab3.bsnsWrap` on `nipa.kr` detail pages.

### Detail Enrichment

Detail enrichment appends detail-page body text to `description`, fills application
period/deadline when parsable, and preserves structured K-Startup fields such as
`support_field`, `target_field`, and `organizer_field` as separate keys.

K-Startup detail labels are intentionally not all flattened into `description`.
`business_age_text`, `target_age_field`, and similar numeric fields stay separate so
the matcher does not misread multi-select values such as `1년미만, 5년미만, 10년미만`.
`support_field` and `target_field` do participate in group keyword matching, which
lets AI/SaaS groups catch list-stub notices whose title/body omit the decisive keyword.

## Date And Recall Policy

`settings.json` controls posted-date filtering:

- `date_filter_enabled`: when true, only the target business-day window plus allowed
  date-unknown notices continue to group matching.
- `days_back`: business-day lookback used by `previous_business_day()`.
- `date_unknown_policy`: explicit policy for notices without parsed `posted_date`.
  - `strict`: keep all date-unknown items out of email and place them in review queue.
  - `recall`: include medium/high-risk date-unknown items in email candidates and leave
    low-risk items in review queue.
  - `all`: include all date-unknown items.
- If `date_unknown_policy` is missing, legacy `include_date_unknown` decides:
  `true -> all`, `false -> strict`.
- `max_posted_age_days`: optional hard cap for old posted dates.

The current checked-in `settings.json` sets `date_unknown_policy` to `recall`.

## Group Matching Buckets

`filter_for_group_with_diagnostics()` returns four buckets:

- `included`: relevant, open/upcoming, region-eligible, group-keyword matched notices.
- `region_unknown`: notices that otherwise look eligible but lack region evidence.
- `review`: priority notices that need manual review.
- `excluded`: hard failures such as closed deadlines, confirmed other region, supplier-only
  notices, manuals, or non-grant notices.

Important constraints:

- Region-unknown notices are not counted as automatic matches; they are surfaced for
  manual review to avoid missed opportunities.
- Confirmed other-region notices remain excluded with `REGION_NOT_ELIGIBLE`.
- Support-amount status is still computed for display, but amount filtering is disabled
  unless a group sets `"enforce_amount_filter": true`.

## Seoul/AI Recall Smoke

`grp_ai_saas` has dedicated recall coverage because many Seoul AI notices arrive as
short list stubs before detail enrichment is complete. The smoke script exercises the
same `evaluate_notice()` path used by the monitor:

```bash
python3 scripts/seoul_ai_recall_check.py
python3 scripts/seoul_ai_recall_check.py --json
```

Current source-backed expectations:

- `서울소재` without spacing is treated as Seoul-region evidence.
- `support_field` values such as `AI/데이터` can satisfy AI/SaaS keyword matching.
- Nationwide AI notices remain eligible for the Seoul group.
- Confirmed other-region notices, for example 부산-only notices, stay blocked for
  precision.

Use this smoke check with `test_seoul_ai_recall.py` when changing region parsing,
structured K-Startup fields, or group keyword matching.

## Safe Operations

Use dry-run commands for automation and development. They set placeholder environment
variables and disable `seen_ids.json` persistence.

```bash
python3 scripts/monitor_dry_run.py --skip-coverage-fetch
python3 scripts/monitor_dry_run.py --skip-coverage-fetch --json
```

Use the full coverage fetch when changing collectors or `sites.json` selectors:

```bash
python3 scripts/monitor_dry_run.py
```

Generated reports:

- `logs/site_collection_coverage_report.md`
- `logs/today_notice_missing_risk_report.md`
- `logs/review_queue_YYYYMMDD.md`

For unit-level regression coverage:

```bash
python3 -m pytest test_monitor.py test_region_unknown_policy.py test_decision_matrix.py test_seoul_ai_recall.py -v
```

Do not run `python3 monitor.py` for verification unless an operator explicitly approves
real email sending.

## Common Pitfalls

- `monitor.py` reads required environment variables at import time. Test files and
  `scripts/monitor_dry_run.py` set safe placeholders before importing it.
- Some Korean public sites fail TLS negotiation from cloud VMs. This can appear in
  integration/coverage fetches even when parser logic is correct.
- `seen_ids.json` is runtime state. Do not delete it casually; doing so can allow old
  notices to be treated as new.
- For static list pages with `javascript:` links, add `link_template` plus `link_id_attr`
  or `link_arg_re`; otherwise generic collection intentionally skips those rows.
