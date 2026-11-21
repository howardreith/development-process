<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r01-dispositions-01ba810838 part=1/1 sha256=01ba810838d0674e508f694ff572810c62e4daf63231853f0d6a3c6b32710cfc -->
### Claude Opus — finding dispositions — round 1

Candidate after corrections: `78868323c00e54e9eb2845faafa7f729619519c6`

- **R1-F1** — `fixed` — commits: `78868323c0`
  settle_publications never sends verdict (rNN-review) or handoff receipt keys; finish_round/finalize re-check prerequisites first. make_historical reconciles a pending verdict against the PR: if it is already visible it posts a correction beside it, otherwise it supersedes the queued verdict and publishes a distinct -historical review. Test: DevProcRoundOneTests.test_resumed_stale_verdict_is_never_published_as_current, test_already_visible_verdict_gets_a_correction_when_stale.
- **R1-F2** — `fixed` — commits: `78868323c0`
  gate_status applies one rule everywhere (acceptance, reviewer inbox, readiness): receipts are grouped by gate and exact argv, the newest (recorded_at) supersedes older runs, and a gate passes only if every latest receipt is valid (declared command, candidate, exit 0, unchanged worktree, intact log digest). Test: DevProcRoundOneTests.test_newest_gate_run_supersedes_and_tampered_logs_fail.
- **R1-F3** — `fixed` — commits: `78868323c0`
  Each controller process loads one MANIFEST-verified in-memory snapshot of prompts/schemas; verify_inputs pauses if disk or snapshot differs from the activated version. install stages a complete copy and swaps directories atomically under a host install lock, refusing while any host writer lock is held, and restores the previous copy if the swap fails. Test: DevProcRoundOneTests.test_install_is_atomic_and_interlocked_with_running_controllers, test_a_controller_uses_one_snapshot_of_its_workflow.
- **R1-F4** — `fixed` — commits: `78868323c0`
  cancel refuses while the developer process (recorded PID or session lookup) or a runtime lock is live, records CANCELLED in a distinct 'cancelled' phase before any publication, treats publication as best effort, and run_loop refuses a cancelled enrollment. Test: DevProcRoundOneTests.test_cancel_is_refused_under_live_work_and_survives_publication_failure.
- **R1-F5** — `fixed` — commits: `78868323c0`
  helper_authority_problems requires status ACTIVE and phase develop, the enrolled worktree root/branch/approved origin, and the installed workflow and process snapshot both equal to the activated fingerprint; push and verify both call it. Test: DevProcRoundOneTests.test_helpers_require_active_development_identity_and_version.
- **R1-F6** — `fixed` — commits: `78868323c0`
  invocation_problems is shared by reviews and preflight: requires a terminal turn.completed without failure events, non-empty per-turn model/effort lists all equal to the requested values, sandbox read-only and approval never affirmatively present. Test: DevProcRoundOneTests.test_reviewer_provenance_must_be_affirmative.
- **R1-F7** — `fixed` — commits: `78868323c0`
  Reviews are parsed with duplicate-key rejection; blank decision_rationale/summary fields and blank finding fields are rejected; passing decisions need inspected evidence; new finding IDs must be R<round>-F<n>. Test: InvalidReviewTests cases 'duplicate JSON keys', 'blank rationale', 'pass without inspected evidence', 'malformed new finding id'.
- **R1-F8** — `fixed` — commits: `78868323c0`
  The tentative POST response is kept separate; without a positively identified author only an authenticated read can verify it, read failures retry or pause without acknowledging, and the comment is never re-posted. Test: DevProcRoundOneTests.test_unconfirmed_post_is_not_acknowledged_after_a_read_failure.
- **R1-F9** — `fixed` — commits: `78868323c0`
  archive_commit_problems (exact parent, exact intended path set, inventory/hash and transcript-only checks) gates both newly created and recovered archive commits; readiness re-verifies every recorded record at the handoff head. Test: DevProcRoundOneTests.test_archive_commit_must_contain_exactly_the_intended_records, test_archive_crash_after_commit_adopts_only_the_exact_commit.
- **R1-F10** — `fixed` — commits: `78868323c0`
  record_path validates every destination before the first write and before recovery rewrites: this PR's record pattern, no symlink/junction ancestry, plain-file target, resolved parent inside the worktree. Test: DevProcRoundOneTests.test_archive_destinations_are_validated_before_writing.
- **R1-F11** — `fixed` — commits: `78868323c0`
  activate re-checks owner policy, recomposes and re-pins developer-settings.json, and supersedes a ready result or an owner-review handoff produced under the previous version (fresh review); readiness also rejects a ready review whose envelope version differs. Test: DevProcRoundOneTests.test_activation_recomposes_permissions_and_supersedes_handoff.
- **R1-F12** — `fixed` — commits: `78868323c0`
  make_historical queues (persists) the historical or correction publication before leaving the round; settle_publications sends it on resume before development advances. Test: DevProcRoundOneTests.test_resumed_stale_verdict_is_never_published_as_current.
- **R1-F13** — `fixed` — commits: `78868323c0`
  update_pr_body replaces exactly one well-ordered status section, appends one when absent, and pauses on malformed markers without rewriting other text; the handoff stores its section and readiness/status --remote verify it is still present. Test: DevProcRoundOneTests.test_pr_status_section_is_handled_explicitly_and_verified.
- **R1-F14** — `fixed` — commits: `78868323c0`
  A reused round keeps its published H/B/M; target movement is recorded in B_observed only. Test: DevProcRoundOneTests.test_published_request_tuple_stays_fixed_when_the_target_moves.
- **R1-F15** — `fixed` — commits: `78868323c0`
  finish_round persists a BLOCKED cap stop together with the acceptance of the last allowed changes_required review, preserving pending findings for an owner-authorized extension. Test: LimitTests.test_round_cap_blocks_visibly.
- **R1-F16** — `fixed` — commits: `78868323c0`
  Reviewer launches record the Codex PID; an attempt without an end record pauses while that process is alive, otherwise it is recorded as a failed (interrupted, untrusted) attempt and its snapshot removed before a new attempt. Test: DevProcRoundOneTests.test_interrupted_reviewer_attempts_are_reconciled.
- **R1-F17** — `fixed` — commits: `78868323c0`
  guarded_push scans every object newly reachable from HEAD and not from any origin ref (git rev-list --objects HEAD --not --remotes=origin), including intermediate blob versions, and refuses on any read failure. Test: DevProcRoundOneTests.test_push_scans_intermediate_versions.
- **R1-F18** — `fixed` — commits: `78868323c0`
  Delegation is detected from structured identity: function_call names and code-mode calls of tools.[collaboration.]spawn_agent/followup_task; ordinary command arguments no longer count. Test: DevProcRoundOneTests.test_delegation_detection_uses_tool_identity.
- **R1-F19** — `fixed` — commits: `78868323c0`
  Completed archives append to a host ledger of controller-written records per repository/PR; re-enrollment imports entries whose content matches the branch head, so genuine earlier records are recognized and altered or unknown ones still fail. Test: DevProcRoundOneTests.test_re_enrollment_recognizes_the_controllers_earlier_records.
- **R1-F20** — `fixed` — commits: `78868323c0`
  Archive crash tests now run finalize in a real controller subprocess killed from git hooks at deterministic points (pre-commit: records written, no commit; post-commit: commit made, not recorded), with partial-record recovery and exact adoption asserted. Test: DevProcRoundOneTests.test_archive_crash_before_commit_recovers_from_intent, test_archive_crash_after_commit_adopts_only_the_exact_commit.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit (controller-run behavior suite) | yes | pass | 193s | 96 behavior tests (1 live test skipped by design). |
| AGENT_REVIEW_LIVE=1 python -m unittest agent_review/test_live_smoke.py (run 10) | no | pass | 68s | Real models, simulated GitHub. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
