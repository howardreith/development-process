<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r02-dispositions-1cc71145ae part=1/1 sha256=1cc71145ae6259a052b6fdbc5770ae27c05a3808a07d2e0621027b5cc8271f59 -->
### Claude Opus — finding dispositions — round 2

Candidate after corrections: `3fe87d11d9d9140ab8a368f27a5c7150deea75b0`

- **R1-F1** — `fixed` — commits: `3fe87d11d9`
  retire_receipts marks any unsuperseded final receipt superseded and, if it is visible, publishes a correction; it runs whenever a handoff is abandoned (invalidate_ready, readiness failure in finalize, reopen, activation). VERDICT_KEY_RE accepts any round width (r100-review). Test: DevProcRoundTwoTests.test_stale_handoff_receipt_is_corrected_when_abandoned.
- **R1-F2** — `fixed` — commits: `3fe87d11d9`
  An unreadable receipt named for the candidate and gate becomes a damaged entry that fails the gate (it cannot revive an older pass); finish_round re-checks required gates before accepting checkpoint_passed or ready_for_owner_review (including a preserved result) and blocks without advancing. Test: DevProcRoundTwoTests.test_damaged_receipts_fail_closed_and_passes_recheck_gates.
- **R1-F3** — `fixed` — commits: `3fe87d11d9`
  Every writer lock now first acquires the host install lock (released once the writer locks are held), so no writer can start while an install runs; install holds that lock throughout, refuses while any writer lock is held, and recovers an install interrupted between its two renames. Test: DevProcRoundTwoTests.test_install_interlocks_new_writers_and_owns_what_it_replaces.
- **R1-F4** — `fixed` — commits: `3fe87d11d9`
  push and verify run under an enrollment helper lock (also gated by the install interlock); cancel acquires it non-blocking and pauses while a helper runs. Test: DevProcRoundTwoTests.test_cancel_waits_for_running_helpers.
- **R1-F5** — `fixed` — commits: `3fe87d11d9`
  Helpers verify the caller: foreground calls must come from the enrolled CLAUDE_CODE_SESSION_ID; headless calls must carry the enrollment's secret helper token, which the controller injects only into its own developer process environment. Test: DevProcRoundTwoTests.test_helpers_are_bound_to_the_calling_developer.
- **R1-F6** — `fixed` — commits: `3fe87d11d9`
  parse_codex_events derives the outcome from the last turn event (a later turn.started or failure clears completion; malformed events fail); provenance collects every turn's sandbox and reports conflicts; invocation_problems also requires network 'restricted'. Test: DevProcRoundTwoTests.test_event_sequence_outcome_is_the_last_turn; DevProcRoundOneTests.test_reviewer_provenance_must_be_affirmative.
- **R1-F7** — `fixed` — commits: `3fe87d11d9`
  Blank entries in any evidence list, blank prior-assessment rationales and blank finding explanations (including blocking_rationale and requested_evidence) are rejected; passes need a nonblank inspected entry. Test: InvalidReviewTests 'blank inspected entry'; AssessmentValidation and blank-rationale cases.
- **R1-F11** — `fixed` — commits: `3fe87d11d9`
  activate retires the invalidated round's unsent verdict (superseded, correction queued and settled) and, for an existing handoff, retires its receipt and rewrites the PR status section after verifying identity. Test: DevProcRoundTwoTests.test_activation_retires_unsent_verdicts_and_public_handoff; DevProcRoundOneTests.test_activation_recomposes_permissions_and_supersedes_handoff.
- **R1-F14** — `fixed` — commits: `3fe87d11d9`
  ready_review keeps the reviewed rnd.B; the acceptance-time tip is stored and shown separately as B_at_acceptance. Test: DevProcRoundTwoTests.test_ready_record_keeps_the_reviewed_target_tip.
- **R1-F15** — `fixed` — commits: `3fe87d11d9`
  resume after a round-cap stop refuses unless the effective limit (current or --max-rounds) exceeds the completed count. Test: DevProcRoundTwoTests.test_resume_respects_an_exhausted_round_budget.
- **R1-F16** — `fixed` — commits: `3fe87d11d9`
  resume reconciles the active round's unfinished attempt before resetting attempts; reconciliation also finds a reviewer launched before its PID was saved by looking up processes whose command line contains the attempt's snapshot path. Test: DevProcRoundTwoTests.test_resume_reconciles_a_live_reviewer_before_resetting.
- **R1-F17** — `fixed` — commits: `3fe87d11d9`
  The push sends the verified object ID (sha:refs/heads/branch) after re-checking HEAD, cleanliness and branch, and the outgoing scan covers commit objects (messages, identities) as well as blobs. Test: DevProcRoundTwoTests.test_push_scans_commit_messages_and_never_follows_tags.
- **R1-F18** — `fixed` — commits: `3fe87d11d9`
  Code-mode inputs have string literals removed before the delegation-call pattern is applied. Test: DevProcRoundTwoTests.test_literal_delegation_text_is_not_a_call.
- **R1-F19** — `fixed` — commits: `3fe87d11d9`
  seed_records_ledger carries authenticated archived maps into the host ledger on activation, cancellation and archive completion (pre-upgrade enrollments included); re-enrollment requires every ledger record to exist with matching content and refuses on any missing or altered record. Test: DevProcRoundTwoTests.test_missing_earlier_records_block_re_enrollment; DevProcRoundOneTests.test_re_enrollment_recognizes_the_controllers_earlier_records.
- **R1-F20** — `fixed` — commits: `3fe87d11d9`
  The three tests that replaced complete_archive were removed; partial-commit rejection was ported to the real subprocess crash fixture (pre-commit kill, then a commit with only part of the records). Test: DevProcRoundTwoTests.test_partial_archive_commit_is_not_adopted.
- **R2-F1** — `fixed` — commits: `3fe87d11d9`
  A pending verdict with any visible part is marked superseded (never 'posted') and corrected; missing_publications ignores superseded records, so unsent parts cannot obstruct the handoff. Test: DevProcRoundTwoTests.test_partially_visible_review_is_retired_not_marked_posted.
- **R2-F2** — `fixed` — commits: `3fe87d11d9`
  The ledger keeps each finding's complete text and originating round; prior-findings.json is built by full_findings(), which recovers complete text from accepted envelopes for older entries. Test: DevProcRoundTwoTests.test_reviewer_inbox_carries_complete_prior_findings.
- **R2-F3** — `fixed` — commits: `3fe87d11d9`
  install refuses an existing destination without a MANIFEST or containing files the manifest does not own, stages into a unique directory, and only removes the copy it retired. Test: DevProcRoundTwoTests.test_install_interlocks_new_writers_and_owns_what_it_replaces.
- **R2-F4** — `fixed` — commits: `3fe87d11d9`
  The push runs with -c push.followTags=false and --no-follow-tags. Test: DevProcRoundTwoTests.test_push_scans_commit_messages_and_never_follows_tags.
- **R2-F5** — `fixed` — commits: `3fe87d11d9`
  The Dice Roller project no longer allows python tools/*; validation runs through its declared domain gate.
- **R2-F6** — `fixed` — commits: `3fe87d11d9`
  resume recognizes a completed enrollment by phase 'done' even if a transient error left status PAUSED, re-verifies the handoff and restores AWAITING_OWNER_REVIEW, or reopens it if superseded. Test: DevProcRoundTwoTests.test_resume_of_a_completed_enrollment_rechecks_the_handoff.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit (controller-run behavior suite) | yes | pass | 208s | 110 behavior tests (1 live test skipped by design). |
| AGENT_REVIEW_LIVE=1 python -m unittest agent_review/test_live_smoke.py (run 11) | no | pass | 70s | Real models, simulated GitHub. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
