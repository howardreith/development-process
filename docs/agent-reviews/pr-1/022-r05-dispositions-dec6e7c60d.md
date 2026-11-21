<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r05-dispositions-dec6e7c60d part=1/1 sha256=dec6e7c60d3f600ce58e886eb9a7ae9ef52c45a708d63df3b36dd6955092495b -->
### Claude Opus — finding dispositions — round 5

Candidate after corrections: `cad9f4fffb98dc434333ae1d2a3afc08c35b223f`

- **R1-F1** — `fixed` — commits: `cad9f4fffb`
  missing_publications requires a complete inventory for every publication it checks, including the named receipt. Parts must be non-empty and numbered 1/n..n/n with n equal to the part count, before each part is authenticated against the PR. Test: DevProcRoundFiveTests.test_receipt_part_inventory_is_validated.
- **R1-F2** — `fixed` — commits: `cad9f4fffb`
  Damage is tied to its run identity. A damaged receipt with a readable argument list fails the gate until a newer valid run of that same list exists. A damaged receipt with an unreadable list fails it until every argument list of the gate has a newer valid run. Test: DevProcRoundFiveTests.test_damage_is_cleared_only_by_the_same_argument_list (filter A damaged, B passing later does not clear it; a newer A does).
- **R1-F6** — `fixed` — commits: `cad9f4fffb`
  Each rollout record and its payload must be objects with a string type; anything else (null, array, untyped) is a provenance problem. Every session_meta record must name the requested thread. Problems flow through invocation_problems into the bounded attempt path and never raise outside it. Test: DevProcRoundFiveTests.test_structurally_malformed_rollout_records_are_problems.
- **R2-F1** — `fixed` — commits: `cad9f4fffb`
  Archived envelopes are now one per publication (<seq>-<publication key>-envelope.json). Their published references are built from the parts of that publication that actually delivered, so a partial original send and the complete historical send keep distinct, correct comment links. Test: DevProcRoundFiveTests.test_archived_envelopes_carry_their_own_publication_links.
- **R3-F3** — `fixed` — commits: `cad9f4fffb`
  Candidate-bound and CLI-recorded: the development-process project now declares a `permissions` gate (probe-permissions). Its controller-written receipt and log for this candidate are among the gate evidence supplied to the reviewer. The log shows the production launch denying the user-level `status` allowance while the enrolled helper (`verify --enrollment ...`) and the composed `git status` ran, and a control launch without --setting-sources running the same user rule. Both launches completed. Decisions come from tool_use/tool_result records and permission_denials tool_use_ids, never from model text; a tool_use with no result is `no_result`. The gate was added to the running enrollment through the new `activate --refresh-project`. Test: DevProcRoundFiveTests.test_probe_outcomes_come_from_cli_records, test_activation_can_refresh_the_pinned_project_config.
- **R3-F4** — `fixed` — commits: `cad9f4fffb`
  archive treats an invalidated round's missing or altered envelope explicitly. It archives a record marked unavailable, with the expected digest and the delivered parts' references, alongside the published text and correction; it never presents damaged bytes as an envelope. Accepted envelopes must still be intact. The regression runs through the final archive. Test: DevProcRoundFiveTests.test_invalidated_damaged_envelope_does_not_block_the_final_archive.
- **R4-F4** — `fixed` — commits: `cad9f4fffb`
  Window expiry no longer authorizes a POST. Definite non-delivery (GitHub 4xx other than 408, or no connection) is classified and may be retried. Any other failure stays ambiguous: the controller waits a bounded window for the marker, then pauses until the owner checks the PR and resumes with --resend-undelivered, which re-reconciles first. Test: DevProcRoundFiveTests.test_ambiguous_delivery_pauses_for_positive_resolution.
- **R5-F1** — `fixed` — commits: `cad9f4fffb`
  verify_inputs detects the same behavioral version loaded from a different package path. Under the writer lock it recomposes the developer permission file from that package and records the new root and digest. Prompts' helper commands use the same self.wf, so commands and allowances always name one package. Test: DevProcRoundFiveTests.test_package_only_install_recomposes_helper_permissions.
- **R5-F2** — `fixed` — commits: `cad9f4fffb`
  reopen persists the cleared handoff, develop phase and ACTIVE status in one save. handoff_superseded and reopen tolerate an already-cleared handoff. A budget refusal after reopening leaves a consistent, resumable state, and a later resume with an extended budget proceeds. Test: DevProcRoundFiveTests.test_reopen_at_the_round_cap_is_consistent_and_resumable.
- **R5-F3** — `fixed` — commits: `cad9f4fffb`
  Before posting a receipt, finalize retires every other current receipt, persisting a correction for any visible one, so a recovered handoff at a new archive head never leaves the earlier receipt current. Test: DevProcRoundFiveTests.test_new_receipt_retires_the_previous_one (the PR body edit fails, the PAUSED status is archived, resume posts the A2 receipt and retires A's).
- **R5-F4** — `fixed` — commits: `cad9f4fffb`
  develop_step requires the transcript-observed effort to equal the configured effort. An empty observation blocks with a precise provenance message. Test: DevProcRoundFiveTests.test_headless_effort_must_be_observed.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | 281s | 152 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | 28s | Two real Claude Opus headless launches (production and control); simulated nothing. |
| AGENT_REVIEW_LIVE=1 python -m unittest agent_review/test_live_smoke.py (run 15) | no | pass | 68s | Real models, simulated GitHub. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
