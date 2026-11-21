<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r08-dispositions-922ad90100 part=1/1 sha256=922ad90100aacd0ef3a30b0b1a65f91c4a27bd2005dfdc07f5255d2e39d2ffe6 -->
### Claude Opus — finding dispositions — round 8

Candidate after corrections: `9559d739910e9180d2fecaf78d7c17dea3db8ede`

- **R7-F3** — `fixed` — commits: `9559d73991`
  Each run's pending marker (named with its identity) is now permanent. gate_receipts lists markers before receipts, and a marker is answered only by a valid receipt of the same identity with a later stamp. A run that completes between the two listings is therefore seen as its receipt or as a started run (fail closed), never as neither. A run that starts after a check begins was not evidence at decision time, and the acceptance re-check immediately before commit covers it. Test: DevProcRoundEightTests.test_gate_completing_during_checks_never_exposes_the_older_pass (a real failing gate runs in a thread while missing_gates is polled continuously; every observation fails closed).
- **R1-F6** — `fixed` — commits: `9559d73991`
  Every thread_settings_applied model and effort is retained, and observed_model and observed_effort report conflicts, so a later matching setting cannot erase an earlier contradictory one. Tool-call records used for delegation checks must carry a nonblank string name. Test: DevProcRoundEightTests.test_conflicting_applied_settings_and_unnamed_tool_calls.
- **R7-F4** — `fixed` — commits: `9559d73991`
  Before committing acceptance, finish_round authenticates that specific verdict on the PR with publication_problems (shared with missing_publications): complete numbered inventory, markers, author, body and uniqueness. A missing or altered part returns the record to pending (missing parts cleared) and pauses; the next attempt reconciles, re-sends and re-checks. Atomic retirement is unchanged. Test: DevProcRoundEightTests.test_verdict_removed_from_github_is_not_accepted.
- **R5-F2** — `fixed` — commits: `9559d73991`
  resume passes the owner's --max-rounds to reopen, which persists the new limit in the same transaction as the cleared handoff and the ACTIVE or BLOCKED status it justifies. Test: DevProcRoundEightTests.test_extension_is_persisted_with_the_reopen (settlement fails afterwards; disk shows ACTIVE with the extended limit).
- **R6-F3** — `fixed` — commits: `9559d73991`
  Both predecessor formats are attributed with the pinned declaration and recorded arguments. Timestamp-only receipts are attributed from their body. Preceding hashed receipts, whose definition id covered argv only, are mapped to the current definition when the declared command is unchanged, preserving failing scopes. In both, positively excluded arguments are classified as history. Test: DevProcRoundEightTests.test_preceding_hashed_receipts_keep_their_failing_scope; DevProcRoundSevenTests.test_intact_predecessor_receipts_are_attributed.
- **R6-F1** — `fixed` — commits: `9559d73991`
  archive compares delivered parts with the markers present in a key's committed records, and appends a supplement record for parts confirmed after the key was archived. readiness requires coverage (committed records lacking delivered parts block the handoff), alongside unresolved deliveries. Test: DevProcRoundEightTests.test_late_confirmed_part_is_appended_and_required.
- **R8-F1** — `fixed` — commits: `9559d73991`
  Only actual receipt keys (final-status-<10 hex>) are exempt from the archive; corrections are archived. finalize retires older receipts and archives the corrections before posting the receipt for the final archive head, looping at most three times until no other current receipt remains. Test: DevProcRoundEightTests.test_receipt_corrections_are_archived.
- **R8-F2** — `fixed` — commits: `9559d73991`
  Review rounds record their contract (workflow fingerprint and project digest) at request creation, and reuse requires the same contract. Activation that changes either reconciles any running attempt and supersedes an outstanding requested or reviewing round, so a new request is created. Test: DevProcRoundEightTests.test_activation_supersedes_an_outstanding_request.
- **R8-F3** — `fixed` — commits: `9559d73991`
  Semantic validation rejects ready_for_owner_review while any actionable correctness finding (category defect, new or prior) lacks an accepted disposition, whatever its blocks_readiness value. readiness enforces the same rule from the ledger (protocol section 11). Test: DevProcRoundEightTests.test_final_pass_with_an_open_correctness_finding_is_invalid.
- **R8-F4** — `fixed` — commits: `9559d73991`
  parse_codex_events carries structured error messages from error and turn.failed events. validate_review classifies usage-limit and model-availability failures from stderr or those messages as fatal. Test: DevProcRoundEightTests.test_quota_error_in_json_events_is_fatal.
- **R8-F5** — `fixed` — commits: `9559d73991`
  Both test modules add their own folder to sys.path and drop a namespace-package shadow of agent_review before importing the controller. The documented `python -m unittest agent_review/test_live_smoke.py` and the gate's script path both import correctly. Test: DevProcRoundEightTests.test_documented_module_invocation_imports.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | about 320s | 180 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | about 30s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | about 70s | Real Opus developer and Astra reviewer; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
