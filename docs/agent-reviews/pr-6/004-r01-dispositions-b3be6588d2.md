<!-- agent-review:v1 enrollment=devproc-claude-continuation-handoff-20261122025808-720e key=r01-dispositions-b3be6588d2 part=1/1 sha256=b3be6588d23159d7ef71791d2d71496cb3502a74f9cef0a5e64566b7d7cc7a14 -->
### Claude Opus — finding dispositions — round 1

Candidate after corrections: `257c2cdc2cd7e2cf23b7fceca357918d14b12b04`

- **R1-F1** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. A declared pending restoration is now refused. The runtime lock is checked again inside the application transaction after the PR lookups, and STOP is consumed only after commit. Test: AmendmentBoundaryTests.test_a_pending_restoration_and_a_late_runtime_lock_keep_the_update_pending.
- **R1-F2** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. Admission now reconciles uncertain deliveries read-only after the identity guard; still-ambiguous ones are refused. Test: test_a_lost_post_response_is_reconciled_before_application_and_the_obsolete_request_is_withdrawn; a mutation that disables reconciliation makes it fail.
- **R1-F3** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. A superseded request is always retired: unsent parts are never sent, delivered parts get a public withdrawal correction and are archived. A published ready verdict gets a 'not current' correction. Tests: the partial multipart request test and the finalize subtest.
- **R1-F4** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. queue() now normalizes line endings before hashing. The private envelope keeps the exact rationale, and the README wording is corrected. Test: ContinuationCrlfTests; the mutation check fails without the fix.
- **R1-F5** — `fixed` — commits: `bf3c3e6`, `257c2cd`
  Local commits, not pushed. Amendment and guidance text is now checked with the strict publication sanitizer during admission. Test: refusal-matrix subtest with a delimiter assembled at run time.
- **R1-F6** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. Only a replay of the same saved file with the same digest is refused; a new file with identical words becomes its own labeled entry. Test: test_identical_words_received_again_become_a_new_entry_while_a_replay_is_refused.
- **R1-F7** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. A stopped done phase with its handoff recorded is now eligible, and PIDs are checked only for attempts that have not ended. Test: test_a_handoff_paused_by_an_operational_failure_and_an_ended_attempt_with_a_reused_pid_are_eligible.
- **R1-F8** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. Each stored report now keeps its invocation's instruction bindings, and last_report_instructions follows last_report. Test: test_report_history_keeps_bindings_and_status_distinguishes_reviewer_delivery.
- **R1-F9** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. The README now describes delivery evidence per role. The same report-history test asserts that latest_attempt is null before reviewer dispatch, and that process_start_recorded, ok and ended_at are set after a completed review.
- **R1-F10** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. The README now covers the post-activation branch (`run` pauses at once on STOP, then the amendment applies) and states which budget each remedy affects. Tests: test_activation_at_a_handoff_reaches_a_stopped_boundary_without_dispatching_the_old_review and test_an_exhausted_invocation_budget_is_not_lifted_by_max_rounds.
- **R1-F11** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. The reviewer prompt now requires the assessment rationale to name the amendment and the withdrawn requirement. The fixture's assessment cites OWNER AMENDMENT 1; it is retained in the ledger, published and archived, and the unrelated finding R1-F2 stays blocking.
- **R1-F12** — `fixed` — commits: `bf3c3e6`
  Local commit, not pushed. The withdrawal fixture now uses a real required project gate 'check'. An amended report without a receipt is rejected before any reviewer dispatch; the correction prompt carries the amendment; the candidate proceeds once the receipt exists.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/7e8bb030d54a1f439a4eebb537110bd52f9dc3ade47ef31cc62c399adab86aca/agent_review.py verify --enrollment devproc-claude-continuation-handoff-20261122025808-720e --gate unit | yes | pass | 543.0s | Run by the controller on local HEAD 257c2cd, which is not pushed. The receipt does not carry over to the squashed commit needed for the push, so the gate must be re-run on that commit. |
| python -m unittest agent_review.test_agent_review.ReviewerContinuationTests agent_review.test_agent_review.ContinuationCrlfTests agent_review.test_agent_review.OwnerAmendmentTests agent_review.test_agent_review.AmendmentBoundaryTests | no | pass | 72.9s | 18 focused behavior tests, run before the two later test-only edits. The edited tests were re-run individually and passed. Two mutation checks were also done: removing the F4 fix made its test fail, and removing the F2 fix made its test fail. |
| python C:/Dev/agent-review/versions/7e8bb030d54a1f439a4eebb537110bd52f9dc3ade47ef31cc62c399adab86aca/agent_review.py push --enrollment devproc-claude-continuation-handoff-20261122025808-720e | yes | fail | seconds | Refused twice: 'possible credential in agent_review/test_agent_review.py (an outgoing version)', from the bf3c3e6 version of that file. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
