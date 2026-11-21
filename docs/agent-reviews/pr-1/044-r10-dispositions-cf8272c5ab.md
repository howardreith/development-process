<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r10-dispositions-cf8272c5ab part=1/1 sha256=cf8272c5abdb5c767ef0c230cc68cf659d3b2c114249edf82c7cc5ebc96f21f3 -->
### Claude Opus — finding dispositions — round 10

Candidate after corrections: `c67a6f72985d45f94db543ee6bb2018f2c1b6a99`

- **R8-F3** — `fixed` — commits: `c67a6f7298`
  accept_report refuses a deferred_optional disposition, and semantic validation refuses a deferral_accepted assessment, for any finding that blocks readiness, carries a correctness_obligation, or is categorized as a defect. An actionable correctness finding therefore cannot be closed by deferral, and final readiness keeps it open. Test: FirstReleaseTests.test_correctness_obligation_cannot_be_deferred; DevProcRoundNineTests.test_restated_defect_keeps_its_correctness_obligation.
- **R10-F1** — `fixed` — commits: `c67a6f7298`
  ClaudeDeveloper.run returns the models recorded in the current invocation's transcript records (transcript_models), and develop_step validates them together with the stream's init and main models against the allowed pattern. A conflicting transcript model blocks report admission. Test: FirstReleaseTests.test_conflicting_transcript_model_is_refused.
- **R6-F1** — `rebutted` — commits: —
  Owner addendum 3 (planning/AGENT-REVIEW-SETUP-OWNER-ADDENDUM-3.md, 2026-11-21) changes the release scope: migration of experimental predecessor state formats is not supported in this release, and ambiguous crashes or uncertain publication may end in a clear safe pause with work preserved. The finding concerns supplements committed by a predecessor controller version, which only exist after an upgrade during an active run. Under addendum 3 that is outside this release: the controller version stays fixed during a run, and continuous reconciliation of superseded fragments and supplements is not a condition of source-code correctness. Records created within one version carry the original part numbers and authenticated references (DevProcRoundEightTests.test_late_confirmed_part_is_appended_and_required). The limitation is documented in agent_review/README.md (First-release scope and limitations). No capability was added.
- **R6-F3** — `rebutted` — commits: —
  Owner addendum 3 (planning/AGENT-REVIEW-SETUP-OWNER-ADDENDUM-3.md, 2026-11-21) changes the release scope: migration of experimental predecessor state formats is not supported in this release, and ambiguous crashes or uncertain publication may end in a clear safe pause with work preserved. The finding asks for stronger evidence that predecessor gate-receipt formats are migrated correctly. Predecessor-format migration is a deferred capability in this release. Within a fixed controller version, receipts carry their full run identity (definition, argument list, stamp), and the supported-path behavior is covered by DevProcRoundFiveTests.test_unreadable_first_run_keeps_its_identity, test_damage_is_cleared_only_by_the_same_argument_list, test_replaced_gate_definition_is_history and DevProcRoundEightTests.test_gate_completing_during_checks_never_exposes_the_older_pass. The limitation is documented in the README. No capability was added.
- **R10-F2** — `rebutted` — commits: —
  Owner addendum 3 (planning/AGENT-REVIEW-SETUP-OWNER-ADDENDUM-3.md, 2026-11-21) changes the release scope: migration of experimental predecessor state formats is not supported in this release, and ambiguous crashes or uncertain publication may end in a clear safe pause with work preserved. After a crash between persisting the fatal attempt and posting the PR notice, the enrollment is durably BLOCKED with the reason recorded (status shows it), no further attempt is dispatched without the owner's resume (DevProcRoundNineTests.test_recorded_fatal_attempt_is_never_retried_after_restart), and no work is lost. That is the safe pause addendum 3 accepts for ambiguous crashes. The owner's resume is an explicit decision taken after reading status. The limitation is documented in the README.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | about 340s | 189 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | about 30s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | about 70s | Real Opus developer and Astra reviewer; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
