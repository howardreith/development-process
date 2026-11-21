<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r03-dispositions-f1743f6c81 part=1/1 sha256=f1743f6c81e068e1eafeba570ac8c4c26398f56d8a5c72b3b2962dd8590a87ee -->
### Claude Opus — finding dispositions — round 3

Candidate after corrections: `1b295b6e70413b024f43645a833dd0e449dd2b20`

- **R1-F1** — `fixed` — commits: `1b295b6e70`
  retire_receipts queues the correction for a visible receipt before marking it superseded and settles it (a failed send stays a pending required operation); finalize retires receipts when archive exits early on a stale head; a named active receipt that is superseded counts as missing. Test: DevProcRoundThreeTests.test_receipt_retirement_survives_a_failed_correction, test_remote_only_movement_retires_the_receipt.
- **R1-F2** — `fixed` — commits: `1b295b6e70`
  Receipts are identified by their controller-written filename (gate-<gate>-<candidate12>-<stamp>.json); unreadable, identity-less or mismatched contents become damaged entries that fail the gate and sort newest. Required gates are checked before a pass is published or accepted; an invalid gate result retires the unsent verdict, is not charged, and returns to development (verify available again after resume). Test: DevProcRoundThreeTests.test_parseable_damaged_receipt_and_gate_check_before_publication.
- **R1-F3** — `fixed` — commits: `1b295b6e70`
  Installs are now immutable versions under versions/<fingerprint>/ behind a launcher and an atomic current.json pointer; no existing version is ever modified or removed, so a running controller or helper keeps exactly the code it loaded, and that code is always the version whose schemas/prompts/fingerprint it verified (the module's own directory). The install interlock and its races are gone. Test: DevProcRoundOneTests.test_install_is_versioned_and_never_disturbs_running_versions.
- **R1-F4** — `fixed` — commits: `1b295b6e70`
  push and verify reload state under the enrollment helper lock and require that the enrollment still holds the host branch claim, besides ACTIVE/develop status; cancellation takes the same lock. Test: DevProcRoundThreeTests.test_helpers_see_current_state_and_claims; DevProcRoundTwoTests.test_cancel_waits_for_running_helpers.
- **R1-F6** — `fixed` — commits: `1b295b6e70`
  parse_codex_events rejects conflicting thread identities and non-object or type-less events; provenance records every approval and network observation and reports conflicts, which invocation_problems rejects. Test: DevProcRoundThreeTests.test_conflicting_threads_and_settings_fail.
- **R1-F11** — `fixed` — commits: `1b295b6e70`
  Activation queues its public updates (receipt retirement and PR status edit) as durable public_ops saved with the activation, and retires any unsuperseded receipt from the previous version regardless of local handoff state; settle_publications completes them on any later command. Test: DevProcRoundThreeTests.test_activation_public_updates_are_durable.
- **R1-F15** — `fixed` — commits: `1b295b6e70`
  The round budget is enforced numerically: resume refuses to reopen development or review while the completed count meets the effective limit, and develop_step refuses to dispatch, independently of the stop reason text. Test: DevProcRoundThreeTests.test_exhausted_budget_is_numeric_not_textual.
- **R1-F16** — `fixed` — commits: `1b295b6e70`
  review_round reconciles the active round's unfinished attempt before any candidate comparison can supersede it (run, review and resume paths). Test: DevProcRoundThreeTests.test_review_round_reconciles_before_superseding.
- **R1-F18** — `fixed` — commits: `1b295b6e70`
  Text scanning was removed: delegation is a recorded dispatch (function/custom tool name) or another session rollout whose metadata names this thread as parent. Test: DevProcRoundOneTests.test_delegation_detection_uses_tool_identity.
- **R1-F19** — `fixed` — commits: `1b295b6e70`
  When enrollment replaces any earlier claim, the replaced enrollment's authenticated archived map is imported into the host ledger under the enrollment lock before the complete inventory is checked. Test: DevProcRoundThreeTests.test_replacing_a_completed_pre_ledger_claim_imports_its_records.
- **R2-F1** — `fixed` — commits: `1b295b6e70`
  retire_verdict publishes a correction for visible parts and the complete review as historical when only part of it reached GitHub; the historical review is archived with its envelope. Test: DevProcRoundTwoTests.test_partially_visible_review_is_retired_not_marked_posted.
- **R2-F2** — `fixed` — commits: `1b295b6e70`
  Legacy finding text is recovered only from envelopes matching their recorded digest; dispatch is refused if any pending finding lacks authenticated complete text. Test: DevProcRoundThreeTests.test_unauthenticated_legacy_findings_block_dispatch.
- **R2-F3** — `fixed` — commits: `1b295b6e70`
  With immutable versioned installs there is no retired-sibling recovery; install refuses destinations with entries it does not own and migrates a legacy flat copy only if every owned file is unchanged. Test: DevProcRoundTwoTests.test_install_owns_only_its_layout_and_migrates_a_legacy_copy.
- **R3-F1** — `fixed` — commits: `1b295b6e70`
  Envelope lookup uses the full round number parsed from the key (r100-review); record names and sequence scanning accept three or more digits consistently. Test: DevProcRoundThreeTests.test_archive_names_and_round_identity_scale.
- **R3-F2** — `fixed` — commits: `1b295b6e70`
  The GitHub actor is re-read immediately before every comment POST (including retries) and before the PR body edit; nothing is written under another login. Test: DevProcRoundThreeTests.test_actor_is_checked_at_each_mutation.
- **R3-F3** — `fixed` — commits: `1b295b6e70`
  Headless launches use --setting-sources "" so only the composed, hash-pinned permission file applies (user, project and local settings are excluded); the composed file carries only the repository's attribution preferences and also denies the launcher path for controller subcommands. Test: DevProcRoundThreeTests.test_headless_permissions_are_isolated.
- **R3-F4** — `fixed` — commits: `1b295b6e70`
  An envelope-binding failure retires the old round's verdict (correction if visible) before the round is replaced and reviewed again. Test: DevProcRoundThreeTests.test_invalid_envelope_retires_a_visible_verdict.
- **R3-F5** — `fixed` — commits: `1b295b6e70`
  Only the generated status section is sanitized; PR description text outside the markers is written back verbatim. Test: DevProcRoundThreeTests.test_pr_description_outside_the_section_is_preserved.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit (controller-run behavior suite) | yes | pass | 233s | 125 behavior tests (1 live test skipped by design). |
| AGENT_REVIEW_LIVE=1 python -m unittest agent_review/test_live_smoke.py (run 12) | no | pass | 64s | Real models, simulated GitHub. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
