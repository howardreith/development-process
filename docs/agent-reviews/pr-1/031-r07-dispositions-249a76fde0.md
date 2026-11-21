<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r07-dispositions-249a76fde0 part=1/1 sha256=249a76fde0b4eff260f900d8f37d6e2b675b9c4a90db383ca07712b24412a432 -->
### Claude Opus — finding dispositions — round 7

Candidate after corrections: `61b50a09921c18f801151511ff7e2d0b5a856a80`

- **R1-F6** — `fixed` — commits: `61b50a0992`
  Consumed leaf values (turn model and effort, sandbox type, model, reasoning effort, approval policy, network, cli version) must be strings; anything else is a provenance problem recorded as <invalid> and never reaches set/sorted. event_msg and response_item records must carry a string type discriminator. Test: DevProcRoundSevenTests.test_rollout_leaf_values_and_discriminators (object model, list approval, empty response payload, each rejected through invocation_problems).
- **R5-F1** — `fixed` — commits: `61b50a0992`
  bind_developer_settings computes the expected digest from the composed bytes. An existing unselected destination that differs is replaced, never adopted; the selected file being altered blocks. The expected digest is what is persisted. Enrollment also uses content-addressed binding. Test: DevProcRoundSixTests.test_interrupted_permission_rebinding_stays_resumable, rebuilt per R7-F5: the interrupted state, with an altered staged file, is constructed on disk and the normal entry point recovers with persistence intact.
- **R5-F2** — `fixed` — commits: `61b50a0992`
  Controller.txn() makes a composite transition a single save: saves inside are deferred, any exception discards the partial in-memory state by reloading from disk, and sends are refused inside, running afterwards from durable intent. reopen computes the effective budget first. In one transaction it queues the receipt corrections, clears the handoff, and sets develop with ACTIVE or BLOCKED; it also queues the REOPENED status and the PR-body update, all settled afterwards. A crash cannot leave ACTIVE at the cap. Test: DevProcRoundSevenTests.test_reopen_at_the_cap_is_blocked_before_any_publication (every publication fails; the state on disk is BLOCKED with the cleared handoff and the queued notice, sent on a later settle).
- **R5-F4** — `fixed` — commits: `61b50a0992`
  ClaudeDeveloper.run records each transcript's byte length before launch. Effort is read only from bytes appended by this invocation, independent of timestamps. Test: DevProcRoundSevenTests.test_effort_comes_from_records_appended_by_this_invocation (same-second adjacent invocations).
- **R6-F1** — `fixed` — commits: `61b50a0992`
  Superseded publications with an unresolved part (posting_since without comment_id after reconciliation) are not archived. readiness reports them, so the handoff is blocked until they resolve or the owner resolves them with --resend-undelivered. Once visible, the publication is archived with its full delivered inventory. Test: DevProcRoundSevenTests.test_unresolved_part_is_not_archived_and_blocks_the_handoff (the part becomes visible after the first archive).
- **R6-F3** — `fixed` — commits: `61b50a0992`
  Intact receipts in the earlier naming scheme are attributed from their bodies. Their argument-list id comes from the recorded argv; their definition is current if the declared base command matches, otherwise replaced (history). Only unreadable predecessor receipts keep unknowable, fail-closed scope. Test: DevProcRoundSevenTests.test_intact_predecessor_receipts_are_attributed.
- **R7-F1** — `fixed` — commits: `61b50a0992`
  Controller.txn() makes a composite transition a single save: saves inside are deferred, any exception discards the partial in-memory state by reloading from disk, and sends are refused inside, running afterwards from durable intent. activate runs as one transaction and stages the new permission file before anything else changes. The workflow, project, permission binding and every invalidation commit together; public updates settle afterwards (settle_after_activation). Test: DevProcRoundSevenTests.test_failed_activation_persists_nothing (a real GitHub failure during verdict retirement leaves the previous fingerprint and binding on disk; a retry commits both).
- **R7-F2** — `fixed` — commits: `61b50a0992`
  gate_definition_id covers the declared argv and extra_args_pattern, so narrowing the policy retires old evidence. receipt_problems also revalidates recorded extra arguments against the active declaration. Test: DevProcRoundSevenTests.test_narrowed_argument_policy_retires_excluded_evidence.
- **R7-F3** — `fixed` — commits: `61b50a0992`
  run_gate writes a pending marker named with the run identity before dispatch and removes it after the receipt is written. gate_receipts treats a pending marker as fail-closed damage for that identity until a newer valid run exists, which covers in-progress and interrupted runs. Test: DevProcRoundSevenTests.test_a_gate_in_progress_or_interrupted_is_visible (the pending marker of an interrupted helper is built on disk).
- **R7-F4** — `fixed` — commits: `61b50a0992`
  Controller.txn() makes a composite transition a single save: saves inside are deferred, any exception discards the partial in-memory state by reloading from disk, and sends are refused inside, running afterwards from durable intent. Every finish_round invalidation persists retirement and invalidation together. A round whose verdict publication is already superseded is invalidated and reviewed again. Acceptance requires the verdict to be posted with every part identified. Test: DevProcRoundSevenTests.test_a_retired_verdict_never_advances_after_restart.
- **R7-F5** — `fixed` — commits: `61b50a0992`
  The stubbed Controller.save is gone. Interrupted-state regressions construct the durable state on disk (staged settings file, pending gate marker, superseded verdict) or use real boundary failures (GitHub listing or publication failures). Nothing internal is replaced. Tests: DevProcRoundSixTests.test_interrupted_permission_rebinding_stays_resumable; DevProcRoundSevenTests (all).

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | 310s | 169 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | about 30s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | about 70s | Real Opus developer and Astra reviewer; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
