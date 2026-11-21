<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r06-dispositions-bf405d4083 part=1/1 sha256=bf405d4083ec4aa915e1a18d8a6c2cae5d4e7c75477f75112d7b7403d998ee42 -->
### Claude Opus — finding dispositions — round 6

Candidate after corrections: `7c963672b127f5bdb9c007693c9d1c4bfd9405a7`

- **R1-F2** — `fixed` — commits: `7c963672b1`
  The run identity is now persisted independently of the receipt body: run_gate names each receipt gate-<gate>-<candidate12>-d<definition id>-a<argument-list id>-<stamp>.json. gate_receipts parses identity from the name, so an unreadable first run of filter A remains A's damage. Only a newer valid run of A clears it, and a pass of B cannot. Receipts named under the earlier scheme have unknowable scope and leave the gate failing for that commit. Tests: DevProcRoundFiveTests.test_unreadable_first_run_keeps_its_identity (including the legacy case), test_damage_is_cleared_only_by_the_same_argument_list.
- **R1-F6** — `fixed` — commits: `7c963672b1`
  Discovery and the sibling scan use _rollout_header, which accepts only an object session_meta header with an object payload. In the selected rollout, session_meta, turn_context, event_msg and response_item records must carry object payloads. Nested sandbox_policy, thread_settings, permission_profile, info and rate_limits must be objects when present. Every violation becomes provenance_problem, which goes through invocation_problems; nothing raises. Test: DevProcRoundSixTests.test_rollout_headers_and_payloads_are_validated.
- **R3-F3** — `fixed` — commits: `7c963672b1`
  There is now a successful enrolled helper result under the production profile, candidate-bound: the project's `live-smoke` gate runs the real headless Opus developer and real Astra reviewer on the fixture repository. Its controller-written log for this candidate contains the developer's CLI-recorded tool transcript, in which its own `push --enrollment` and `verify --enrollment --gate unit` helpers ran ok. It also contains the passing receipt that helper wrote for the reviewed fixture candidate, and no permission denials. The gate asserts all three. The `permissions` gate keeps the isolation observation and now distinguishes tool errors (`error`) from successes (`ran`). It uses `status --help` and `verify --help`, which succeed when permitted: production denied the user rule while the helper and `git status` ran, and the control ran the user rule. Test: DevProcRoundFiveTests.test_probe_outcomes_come_from_cli_records.
- **R5-F1** — `fixed` — commits: `7c963672b1`
  Permission files are content-addressed (developer-settings-<digest16>.json) and selected by developer_settings_file in state. bind_developer_settings writes the new file first, then the selection, digest and package root change in one state save. An interruption leaves the previous intact file selected, the next command completes the rebinding, and unrelated edits are still rejected. Test: DevProcRoundSixTests.test_interrupted_permission_rebinding_stays_resumable.
- **R5-F2** — `fixed` — commits: `7c963672b1`
  When resume reopens a superseded handoff and the budget is exhausted, it raises a BLOCKED stop. guarded persists and publishes it, so helpers are unavailable. A later resume with --max-rounds continues. Test: DevProcRoundFiveTests.test_reopen_at_the_round_cap_is_consistent_and_resumable (BLOCKED persisted, helpers refused, stop visible on the PR, extension resumes).
- **R5-F4** — `fixed` — commits: `7c963672b1`
  ClaudeDeveloper.run records launched_at (1s margin) and reads effort only from transcript records of the current invocation. session_history stays available without since. Test: DevProcRoundSixTests.test_effort_is_bound_to_the_current_invocation.
- **R6-F1** — `fixed` — commits: `7c963672b1`
  retire_verdict and retire_receipts treat a part with an unresolved POST (posting_since without comment_id) as possibly visible, queuing the correction in advance. archive reconciles uncertain parts of superseded publications before recording what was public. Test: DevProcRoundSixTests.test_uncertain_delivery_is_corrected_on_retirement.
- **R6-F2** — `fixed` — commits: `7c963672b1`
  Envelopes record project_sha256. finish_round retires and reruns a result produced under another project config. activate --refresh-project that changes the config runs the existing retirement path: validated result, ready review and handoff are invalidated, receipts retired, and review reopened. Test: DevProcRoundSixTests.test_project_refresh_that_changes_review_inputs_reopens_review.
- **R6-F3** — `fixed` — commits: `7c963672b1`
  Receipts are bound to their gate-definition id. Runs of a replaced definition are history and never decide the gate, and argument-list supersession applies within the active definition. Test: DevProcRoundFiveTests.test_replaced_gate_definition_is_history.
- **R6-F4** — `fixed` — commits: `7c963672b1`
  missing_publications exempts only actual receipt keys (final-status-<10 hex>) other than the active one. Retirement and supersession corrections are authenticated as substantive publications. Test: DevProcRoundSixTests.test_receipt_corrections_are_substantive.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | 300s | 160 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | 27s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | 71s | Real Opus developer and Astra reviewer on a fixture repo; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
