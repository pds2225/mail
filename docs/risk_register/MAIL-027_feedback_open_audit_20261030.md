# MAIL-027: confirmed feedback gaps, 2026-10-30

Verified at 2026-10-30 04:55–04:58 Asia/Seoul against main
`59e311843c58611fb187e957fd4c8a3e831a99ca`.
TASK blob: `7d90b2dc736fec5ad3e9ab3910163b9253ed214d`.
Branch: `docs/mail-027-feedback-open-evidence-20261030`.

Only directly demonstrated gaps are marked OPEN. This audit does not implement
new behavior or claim that MAIL-027 is solved. Risk 132 remains ALREADY_DONE;
its TTL does not establish recipient isolation or one-time consumption.

| Risk | Code evidence | Fixture result | Status |
|---|---|---|---|
| 130: forwarded link | `feedback_token._signature` signs verdict, notice ID and issued_at; `feedback_mailto` does not include the recipient in that payload. | With fixed time, links to `a@example.test` and `b@example.test` have identical signed subjects. `verify` has no recipient argument. A shared valid token is not bound to the intended recipient. | OPEN |
| 131: replay | `verify` is stateless; `merge_feedback_labels` uses arrival/iteration order and does not compare the incoming `received` timestamp to the stored `last_seen`. | Repeated verification of the same unexpired token succeeds. Merge O received 2026-10-30, then X received 2026-10-29: stored verdict becomes X and last_seen moves backward. Neither one-time use nor latest-time-only behavior is enforced. | OPEN |
| 135: automated reply | `collect_feedback.fetch_feedback_mails` requests only SUBJECT and DATE, and passes the decoded subject directly to `parse_feedback_subject`; that parser accepts reply prefixes. | Fake read-only IMAP returns `Re: <valid signed subject>` plus `Auto-Submitted: auto-replied`; the collector accepts one O record. Production's requested headers omit Auto-Submitted, so it cannot exclude that automated reply by this header. | OPEN |
| 141: user/group isolation | `load_feedback_labels` and `merge_feedback_labels` key rows only by notice ID; new records persist no recipient/group/company identity. | Merge group-a/user-a O and group-b/user-b X for the same notice: one X row remains, with neither group_id nor recipient retained. | OPEN |

The probes used a fixed fixture secret (never printed), fixture addresses under
example.test, fixture HTTP/IMAP only, and explicit JSONL paths under
`var/overnight/mail027-audit-20261030-0455/`. No production labels, settings,
mailbox or external network were used. Local `results.json` contains four true
gap assertions, external_network_calls=0 and production_writes=0.

Reproduce the token and merge observations in an isolated process with a fixture
MAIL_FEEDBACK_SECRET and an explicit temporary label path:

1. Freeze `feedback_token.time.time` to 1800000000, create O links for the same
   notice to two fixture recipients, then compare their decoded subject values.
2. Verify that signed subject twice at the same time; both checks succeed.
3. Merge O with received `2026-10-30T00:00:00Z`, then X with received
   `2026-10-29T00:00:00Z`; read the explicit fixture file and assert X.
4. In a second fixture file merge two records with the same id, opposite
   verdicts, and different group_id/recipient; assert one row and absent context.
5. Patch `collect_feedback.imaplib.IMAP4_SSL` with an IMAP fixture returning a
   single header containing a valid signed reply subject and Auto-Submitted.
   Assert read-only SELECT/BODY.PEEK and one accepted record.

Related regression validation:

```text
python -m pytest tests/test_feedback_token.py tests/test_feedback_loop.py \
  tests/test_feedback_collection_wired.py -q \
  --basetemp=var/overnight/pytest-feedback-audit-20261030
35 passed in 1.44s
```

These passing tests preserve existing behavior; the separate probes demonstrate
the missing guarantees. Risks 133–134 and 136–140/142 keep their prior status;
no conclusion is inferred merely from a passing test or a keyword search.
