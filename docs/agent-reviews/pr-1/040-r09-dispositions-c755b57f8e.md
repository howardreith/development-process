<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r09-dispositions-c755b57f8e part=1/1 sha256=c755b57f8e67837a43cd773c775ebf11ee48b7b7b0f184b34c8277676a8005d8 -->
### Claude Opus — finding dispositions — round 9

Candidate after corrections: `7c58a2b6d30c87ea011752bc01a28e0aa7140be4`

- **R9-F1** — `fixed` — commits: `7c58a2b6d3`
  finish_round no longer clears acknowledged IDs because a listing omits them. It looks each acknowledged part up authoritatively (GitHub.comment, GET issues/comments/<id>); only a 404 clears that part's ID and returns the record to pending for a replacement POST. Otherwise it pauses with the IDs kept (listing lag) and re-checks on the next attempt. Test: DevProcRoundNineTests.test_lagging_listing_never_causes_a_duplicate_verdict (lagging listing across two attempts; exactly one verdict comment; accepted once visible).
- **R7-F3** — `fixed` — commits: `7c58a2b6d3`
  admit_report runs report acceptance and the durable transition out of develop under the enrollment helper lock, which push and verify hold from their authority check through their run marker and receipt. This applies to both foreground `review --report` and headless develop_step. A helper therefore either completes before admission or is refused afterwards (phase is review). Permanent run markers remain for interrupted runs. Test: DevProcRoundNineTests.test_report_admission_waits_for_a_running_helper; DevProcRoundEightTests.test_gate_completing_during_checks_never_exposes_the_older_pass.
- **R8-F3** — `fixed` — commits: `7c58a2b6d3`
  Ledger entries carry correctness_obligation, set once any statement is a defect and kept across restatements until a positive assessment resolves the finding. Semantic validation, the ledger update and final readiness all use it, so a fix_rejected defect restated as optional_polish still blocks ready_for_owner_review. Test: DevProcRoundNineTests.test_restated_defect_keeps_its_correctness_obligation.
- **R6-F1** — `fixed` — commits: `7c58a2b6d3`
  Supplements now state each late part's original number (part i of n), authenticated comment ID and URL alongside its text. Partial envelopes use original inventory positions (part, of). unarchived_parts reads coverage from the committed tree at HEAD. Test: DevProcRoundEightTests.test_late_confirmed_part_is_appended_and_required (asserts the committed supplement in HEAD contains `part n of n: comment <id> (<url>)`).
- **R1-F6** — `fixed` — commits: `7c58a2b6d3`
  Rollout headers, consumed rollout records and reviewer event records are parsed with the duplicate-key-rejecting hook used for results. A duplicate member makes the record malformed, so it is a provenance problem or a non-completed outcome, propagated through invocation validation. Test: DevProcRoundNineTests.test_duplicate_members_are_rejected (event stream, settings record, header).
- **R6-F3** — `fixed` — commits: `7c58a2b6d3`
  The regressions now construct each predecessor format's real inventory: receipts renamed to the format and no run markers, since neither format had them. The unchanged declaration and the narrowed filter are exercised separately. The preceding hashed format's own failing receipt decides the gate until A passes. An earliest-format failing receipt decides it while in scope and becomes history once the filter is narrowed and B passes. Tests: DevProcRoundEightTests.test_preceding_hashed_receipts_keep_their_failing_scope, test_earliest_format_with_a_narrowed_filter_is_history.
- **R9-F2** — `fixed` — commits: `7c58a2b6d3`
  review_attempt persists a fatal attempt together with status BLOCKED in one save. review_round refuses to dispatch from a round with a recorded fatal attempt. Owner resume moves attempts to earlier_attempts and grants a fresh budget. Test: DevProcRoundNineTests.test_recorded_fatal_attempt_is_never_retried_after_restart (durable state built on disk; no reviewer call).
- **R9-F3** — `fixed` — commits: `7c58a2b6d3`
  commit_checks paginates the commit statuses list endpoint (`--paginate .../statuses`) and keeps the newest status per context before evaluating required contexts and failures. Test: DevProcRoundNineTests.test_commit_statuses_are_paginated_and_current (real GitHub client against a gh shim).

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | about 340s | 187 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | about 30s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | about 70s | Real Opus developer and Astra reviewer; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
