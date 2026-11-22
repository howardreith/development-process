# `resume --guidance` closeout: finding dispositions

Record for the owner's final review of PR #5 (mission Part A.5, and enrollment 57a2's finding R2-F2).

The closeout allowance (five substantive reviews) was spent: three in enrollment `662b`, two in enrollment `57a2`.
`57a2` stopped BLOCKED at its round cap after round 2 (`changes_required` on `86b19e5`). The owner then directed
the supervising Claude to finish the corrections locally, with an independent review by the owner's chosen
reviewer instead of a further Codex round. **The corrections in the commit after `86b19e5` have not been reviewed
by Codex.**

## Enrollment `57a2` round-2 findings (corrected locally after the review budget was spent)

| ID | Defect (round 2 on `86b19e5`) | Correction | Evidence (focused regression, real command path) |
|---|---|---|---|
| 57a2/R1-F2 | A round-directory or capture-write `OSError` was published with its private path | The command guard publishes a filesystem error by type and errno only; the full diagnostic stays in the local `status` reason. A capture write failure is an exit-4 refusal (local message, nothing selected or published). README recovery text points to local `status` | `test_round_directory_failure_publishes_no_private_path` (custom state root outside home; PR comment and archived notice), `test_capture_write_failure_is_a_local_refusal` |
| 57a2/R1-F4 | An unopenable helper lock and a non-object `state.json` produced tracebacks | `Lock` maps an open failure to `LockUnavailable` (a usage refusal); guided admission names it. `reload` refuses a non-object state | `test_guided_setup_failures_on_the_real_command_path_refuse_with_exit_4` (real `main`: directory at `helper.lock`; `[]` state; exit 4, state bytes and STOP unchanged, no posts or launches) |
| 57a2/R1-F6 | A recorded snapshot lost during the remote admission checks was recreated | Capture uses recorded-digest membership: a recorded digest is only reused (intact file required) and never written; only an unrecorded digest is written. The refusal records no note, so state stays byte-identical | `test_a_recorded_snapshot_lost_during_admission_is_not_recreated` (A removed inside the simulated viewer call; exit 4, A absent, B selected; reselection succeeds after supervised restore) |
| 57a2/R1-F7 | A missing reviewer executable left an open, unlaunched attempt | The reviewer boundary is resolved before the attempt is opened; a lookup failure stops BLOCKED with no attempt | `test_missing_reviewer_executable_opens_no_attempt` (lazy construction, PATH lookup of the shipped `codex` name fails; no attempt; one dispatch after restore) |
| 57a2/R1-F8 | A dead developer's PID counted as the next invocation's start | The launch-intent save clears `active_pid`; the start callback records `launch.pid`; status attributes a start only from that invocation's own evidence | `test_a_dead_developers_pid_is_not_the_next_invocations_start` (dead PID retained, pre-start failure, restart; start shows only after its own callback) |
| 57a2/R2-F1 | Reselecting a digest whose historical record lacked `revision` raised `KeyError` | `recorded_revisions` validates the matching records and refuses malformed history | `test_reselecting_a_digest_with_damaged_history_is_refused_unchanged` |
| 57a2/R2-F2 | The historical disposition table was not in the reviewer's inputs | This document | — |
| 57a2/R1-F12 | Optional: fence splitting across comment parts | Deferred (accepted by the reviewer in round 2) | — |

Each regression above was run against the pre-correction controller (`86b19e5`), and all seven failed at the
reported boundary. All pass after the correction.

Pre-existing limitation found while testing, outside this change: archived review envelopes record their private
`path` field, sanitized only by the existing home-directory redaction. With a custom state root outside the home
directory, that path appears in the committed envelope record. It predates PR #5 and is not changed here.

## Enrollment `662b` findings (state after its round 3), against the narrowed design

First published in the developer report of `57a2` round 1 (review request
[comment 7075353638](https://github.com/howardreith/development-process/pull/5#issuecomment-7075353638)). Updated
with Codex's round-2 assessments and the corrections above.

| ID | Behavior still supported? | Change | Evidence | Status |
|---|---|---|---|---|
| 662b/R1-F2 | Controlled refusal: yes. Hostile-private-path branch: removed | Malformed manifest/claim JSON, unavailable worktree, unopenable lock and non-object state are exit-4 refusals; `guidance_dir` link defenses removed | Refusal subtests (manifest, registry, worktree CLI); `test_guided_setup_failures_on_the_real_command_path_refuse_with_exit_4` | Round 2 called it incomplete via 57a2/R1-F4; corrected above (not Codex-reviewed) |
| 662b/R1-F5 | Removed (foreground guidance) | Foreground `--guidance` refused; transcript detection removed | Foreground refusal subtest; foreground suites unchanged | Verified retired, round 2 |
| 662b/R1-F6 | Automatic repair: removed | Capture never overwrites; a recorded digest is never recreated; selection is state-only | A→B→A test, failed-save test, `test_a_recorded_snapshot_lost_during_admission_is_not_recreated` | Round 2 found a remaining recreation path (57a2/R1-F6); corrected above (not Codex-reviewed) |
| 662b/R1-F7 | Yes: null/invalid selection blocks; the newline claim is qualified | `guidance_record` keys off key presence; the prompt says line endings may be adjusted | `test_null_guidance_member_never_launches_unguided_while_a_missing_key_is_legacy` | Verified, round 2 |
| 662b/R1-F8 | Yes | Reviewer input and stream setup failures close the attempt as not launched; executable lookup opens no attempt | `test_reviewer_input_write_failure_leaves_no_unfinished_attempt`, `test_reviewer_stream_setup_failure_closes_the_attempt_as_unlaunched`, `test_missing_reviewer_executable_opens_no_attempt` | Round 2 verified the copy failure; lookup neighbor (57a2/R1-F7) corrected above |
| 662b/R2-F3 | Removed; baseline STOP | `consume_stop` and `stop_identity` deleted | `check_stop_request` identical to `main` | Verified retired, round 2 |
| 662b/R2-F4 | Removed | Plain `atomic_write_bytes` in trusted state | Code | Verified retired, round 2 |
| 662b/R2-F5 | Removed | Publication retries send frozen bodies; no guidance check inside them | `test_queued_request_is_retried_with_its_frozen_rendering_and_review_waits_for_intact_guidance` | Verified retired, round 2 |
| 662b/R3-F1 | Removed (foreground report member) | Report extension removed; revision numbers must be positive JSON integers | Foreground refusal subtest; 57a2/R1-F5 damage cases | Verified retired, round 2 |
| 662b/R3-F2 (optional) | Done | README separates no-progress from an exhausted budget | README recovery table | Verified, round 2 |
