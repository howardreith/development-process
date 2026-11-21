<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r03-review part=1/2 sha256=5ff7028e616c4df93ab6dbb4dc260384fb244f06c40ad0175b0877f16b56756b -->
_Part 1 of 2._

### Codex GPT-6.2 Astra — review — round 3 — candidate `3fe87d11d9`

**Decision:** `changes_required` — The candidate-bound unit gate passed, and eight prior fixes are verified. Controller-core still has paths that can accept an older gate receipt, attribute a result to the wrong reviewer thread, leave a stale handoff visible, or dispatch work after cancellation or budget exhaustion. The multipart publication test also ends with part of the historical review missing from both the PR and its eventual archive.

#### Findings

**R1-F1** · P1 · defect · blocks readiness — A stale handoff receipt can survive retirement or count toward a later handoff
- Location: `agent_review/agent_review.py:2519`; acceptance: WF04, WF06
- Trigger: A final receipt is visible when the branch moves or the controller exits during receipt retirement.
- Expected: A visible obsolete receipt gets a durable correction. A current handoff requires an intact, posted receipt for that handoff.
- Actual: retire_receipts saves the receipt as superseded before queuing its correction. An exit between those operations makes the next call skip it permanently. There is also an earlier exit when only the remote branch moves: archive raises on the local/remote mismatch before finalize reaches receipt retirement. Finally, missing_publications skips a superseded receipt even when that exact receipt is required for the handoff.
- Why it blocks / does not: The owner's PR can continue to show an obsolete handoff, or the final check can accept a receipt that the controller has already retired.
- Requested correction: Persist the retirement and required correction together, reconcile visible receipts on early stale-head exits, and positively require the named active receipt during the final check.
- Requested evidence: Interrupt after publication and at retirement, including a remote-only head move. Resume and verify the correction, then demonstrate that a retired or absent receipt cannot satisfy readiness.

**R1-F2** · P1 · defect · blocks readiness — A damaged receipt can revive an older pass, and gate failure can strand recovery
- Location: `agent_review/agent_review.py:1943`; acceptance: WF05, WF08, WF12
- Trigger: A newer receipt loses required fields, or required evidence becomes invalid after the report is accepted.
- Expected: The latest evidence for the candidate must be identifiable and valid. Loss of required evidence must leave a recoverable state before a pass is accepted.
- Actual: gate_receipts handles invalid JSON syntax, but silently filters out a parseable damaged receipt such as an empty object. An older pass then wins. When finish_round does detect invalid evidence, it has already posted the pass, accepted the round, cleared active_round, and charged the budget. It leaves the phase at review, where the verify helper is disabled and resume can dispatch another review of the same evidence.
- Why it blocks / does not: One path advances on obsolete evidence. The other consumes reviews without giving the developer an ordinary way to restore the required gate.
- Requested correction: Validate receipt identity and structure against its controller-owned filename before filtering. Check required gates before publishing or accepting a pass and provide a transition that permits a replacement gate run.
- Requested evidence: Replace a newer failing receipt with a valid JSON object missing its identity fields and verify the older pass is unusable. Damage a log during review, recover through verify and resume, and assert the round count and public verdicts throughout.

**R1-F3** · P1 · defect · blocks readiness — The installation interlock misses running helpers and preloaded controller code
- Location: `agent_review/agent_review.py:2135`; acceptance: WF07, WF10
- Trigger: An install overlaps a standalone verify operation or a process that loaded the old module before acquiring its writer lock.
- Expected: Installation and startup interlock for the complete lifetime of operations that use a version, including standalone foreground helpers.
- Actual: A foreground helper releases install.lock after acquiring its enrollment-local helper.lock. install probes only host_dir()/locks, so it can replace the installation during that helper. Also, guarded reloads the on-disk fingerprint under the lock after Python has already loaded the executable module. A process spanning a swap can therefore associate old controller code with the new fingerprint.
- Why it blocks / does not: An operation can run under a version different from the version attributed to it.
- Requested correction: Make active helpers visible to installation and bind the executing controller module to the same version as its schemas, prompts, and permission files.
- Requested evidence: Hold a real foreground helper open while another process attempts installation. Also pause a controller process before writer-lock acquisition, switch versions, and verify it either runs one attributable version or refuses.

**R1-F4** · P1 · defect · blocks readiness — A helper can use authority cached before cancellation
- Location: `agent_review/agent_review.py:3314`; acceptance: WF07, WF10
- Trigger: Cancellation wins the race between helper construction and helper-lock acquisition.
- Expected: Helper authority must be established under the lock that excludes cancellation.
- Actual: Both helper entry points construct Controller and read ACTIVE state before taking helper.lock. Cancellation can finish and release the claims in that interval. The helper then acquires its old lock and checks the cached state without reloading it or confirming registry ownership.
- Why it blocks / does not: A cancelled enrollment can still run a gate or push after another enrollment becomes eligible to own the branch.
- Requested correction: Reload state and verify the current enrollment claims under the helper lock before performing either operation.
- Requested evidence: Pause a real helper after initial lookup, cancel and replace the enrollment, then release the helper. Assert that the old helper produces neither a receipt nor a remote update.

**R1-F6** · P1 · defect · blocks readiness — Reviewer completion and permission provenance can come from different observations
- Location: `agent_review/agent_review.py:645`; acceptance: WF05, WF10
- Trigger: The event stream names two threads, or the rollout contains multiple effective settings records.
- Expected: The completed result must belong to one unambiguous invocation whose relevant permission observations agree throughout.
- Actual: parse_codex_events keeps the first thread ID and accepts a later completion even if another thread.started intervenes. The result can then be checked against the first thread's rollout. Within a rollout, provenance collects all turn sandboxes but overwrites approval_policy and network at each settings event. A later compliant value hides an earlier conflicting one.
- Why it blocks / does not: A valid-looking result can be accepted using provenance from a different thread or incomplete evidence of its effective permissions.
- Requested correction: Reject conflicting thread identities and conflicting approval or network observations. Validate event shapes so malformed records enter the bounded rejection path.
- Requested evidence: Feed the real parsers a two-thread stream, conflicting settings followed by compliant settings, and a non-object event. Verify that no round advances and the failure is recorded.

**R1-F11** · P1 · defect · blocks readiness — Activation can lose the public handoff correction after saving local state
- Location: `agent_review/agent_review.py:2227`; acceptance: WF04, WF06, WF07
- Trigger: Activation invalidates a ready result while a handoff is visible, then publication or the process fails.
- Expected: Activating a new version must make public supersession recoverable for both completed and interrupted handoffs.
- Actual: activate clears the ready result and handoff and saves the new fingerprint before it retires the receipt or edits the PR body. A GitHub failure after that save leaves no durable public-update operation for the next activate or resume. A receipt visible just before the original handoff state was saved also misses the 'owner-review handoff' branch entirely.
- Why it blocks / does not: The local enrollment can reopen successfully while the PR still directs the owner to review the superseded candidate.
- Requested correction: Record the required receipt correction and PR body update as durable operations when invalidating the handoff. Reconcile them on retry even when the new fingerprint is already active.
- Requested evidence: Fail the simulated GitHub operation immediately after the activation state save. Restart and verify the receipt and PR description are corrected for both a completed handoff and an interrupted receipt publication.

**R1-F15** · P1 · defect · blocks readiness — Round-cap enforcement on resume depends on the wording of the last stop
- Location: `agent_review/agent_review.py:2257`; acceptance: WF07, WF08
- Trigger: An exhausted checkpoint also meets the no-progress condition or receives a subsequent operational stop.
- Expected: The persisted count and effective limit govern whether work requiring another review may start.
- Actual: resume checks the completed count only when status_reason starts with 'review-round cap'. finish_round gives no-progress reasons precedence over the cap. A round that reaches both limits therefore resumes development with an exhausted budget. A later operational failure can likewise replace the reason string without changing the count.
- Why it blocks / does not: The controller can enable helpers or launch another paid developer invocation before the owner grants more review rounds.
- Requested correction: Enforce the numeric budget before reopening development or dispatching a further review, independently of the displayed stop reason. Preserve finalization of an already accepted pass.
- Requested evidence: Reach no-progress and cap on the same round. Resume with the same limit and verify zero launches and disabled helpers, then extend the limit and demonstrate continuation.

**R1-F16** · P1 · defect · blocks readiness — Candidate replacement can discard an unreconciled reviewer attempt
- Location: `agent_review/agent_review.py:1409`; acceptance: WF05, WF07
- Trigger: The controller exits during review and the comparison input moves before the next normal invocation.
- Expected: Every entry point that replaces an active round must first settle its unfinished process and snapshot.
- Actual: resume now reconciles before resetting attempts. The normal review_round entry point still compares H/M and supersedes the active round before calling reconcile_reviewer_attempt. After a controller exit that leaves status ACTIVE, run or foreground review can take this route. An M-only move with unchanged H can immediately launch a replacement.
- Why it blocks / does not: A live reviewer can be lost from active state while another paid invocation starts.
- Requested correction: Reconcile the previous active attempt before candidate comparison can supersede it, including recovery through run and review.
- Requested evidence: Leave a reviewer subprocess alive, move the comparison input, and enter through the normal review path. Verify a single launch while it is alive and cleanup after it exits, including the pre-PID-save case.

**R1-F18** · P2 · defect · blocks readiness — Delegation detection still classifies source text instead of executed operations
- Location: `agent_review/agent_review.py:622`; acceptance: WF05
- Trigger: A code-mode input includes a call signature in a comment or an executable expression within a template literal.
- Expected: The controller distinguishes actual delegation from inert text in tool inputs.
- Actual: Removing quoted strings fixes the reported shell-search example. JavaScript comments remain in the scanned text, so a comment spelling a delegation call still invalidates the review. Removing an entire template literal also removes its executable interpolation expressions.
- Why it blocks / does not: The provenance decision can both reject a harmless review and miss an actual dispatch.
- Requested correction: Use recorded tool-dispatch identity where available. If code-mode inspection remains necessary, handle comments and executable expressions without treating all text in a template literal alike.
- Requested evidence: Exercise literal search text, an inert comment, direct dispatch, and dispatch in an expression through the rollout parser. Verify the classification for each.

**R1-F19** · P1 · defect · blocks readiness — Direct re-enrollment skips migration from a completed pre-upgrade enrollment
- Location: `agent_review/agent_review.py:2903`; acceptance: WF07, WF09
- Trigger: A completed enrollment with archived records predates the host ledger and is replaced without a separate activate or cancel.
- Expected: Every supported transition to a new enrollment preserves and verifies the prior PR inventory.
- Actual: Activation and cancellation now seed the host ledger. Direct re-enrollment is also allowed from AWAITING_OWNER_REVIEW. That path reads the previous claim to check status, then loads only the host ledger. For a completed pre-ledger enrollment, the authenticated archived map remains in the old state and the replacement claim loses that inventory.
- Why it blocks / does not: Genuine records can prevent the next review as foreign files, or previously recorded deletions can go undetected.
- Requested correction: When replacing a completed claim, import its applicable authenticated PR inventory under the enrollment lock and check the entire inventory before writing the replacement claim.
- Requested evidence: Start with completed pre-upgrade state and no host ledger. Re-enroll directly with intact records, then repeat with a missing record and verify refusal before ownership changes.

**R2-F1** · P1 · defect · blocks readiness — Retiring a partial verdict drops the rest of the historical review
- Location: `agent_review/agent_review.py:1778`; acceptance: WF04, WF06, WF09
- Trigger: The head moves after the service stores one part of a multipart verdict.
- Expected: A stale verdict is visibly historical and its complete substantive content remains available on the PR and in the archive.
- Actual: make_historical marks a partially visible verdict superseded and publishes only a short correction. The remaining review parts are never published. archive skips the superseded publication, including its envelope. The regression asserts that missing_publications is empty, which now succeeds because the incomplete record is excluded.
- Why it blocks / does not: A later handoff can succeed while some independent findings are unavailable in either required public record.
- Requested correction: Persist and publish a complete historical rendering when only part of the current verdict was sent. Archive that historical result with its correct provenance.
- Requested evidence: Interrupt a multipart review after part one, move H, then finish a subsequent handoff. Locate a finding from the last part in both the PR history and the committed records.

**R2-F2** · P1 · defect · blocks readiness — Legacy finding recovery accepts unauthenticated text or silently omits it
- Location: `agent_review/agent_review.py:1519`; acceptance: WF08, WF12
- Trigger: A pending ledger entry predates storage of the full finding and its retained envelope has changed or disappeared.
- Expected: Every pending prior assessment receives the full authenticated finding from its applicable accepted round.
- Actual: The current inbox contains complete findings. For older entries, full_findings reads any available envelope at envelope_path without comparing its recorded digest. It silently leaves the finding incomplete when the file is absent. Either case can dispatch a reviewer without the authenticated finding it must assess.
- Why it blocks / does not: A proposed fix can be judged against altered or incomplete acceptance text.
- Requested correction: Verify the retained envelope against its recorded digest before recovery and require complete recovered text for every pending assessment before dispatch.
- Requested evidence: Use a legacy ledger entry with an intact, altered, and missing accepted envelope. Only the intact case should dispatch with the original trigger and requested evidence.

**R2-F3** · P1 · defect · blocks readiness — Installation recovery takes ownership of a sibling by name alone
- Location: `agent_review/agent_review.py:3062`; acceptance: WF07, WF10
- Trigger: The install destination is absent and an unrelated sibling matches the retirement naming pattern.
- Expected: Recovery acts only on an identified installation transaction and preserves unrelated paths on refusal.
- Actual: When the destination is absent, install moves the last directory matching dest.retired-* into the destination before validating its manifest or ownership. An unrelated matching sibling is therefore moved even if installation subsequently refuses. The destination inventory also excludes every file below a directory named __pycache__ before recursively removing the retired tree.
- Why it blocks / does not: An install or recovery command can move or delete unrelated owner files.
- Requested correction: Identify and validate the specific retired installation before moving it. Account for unowned contents before recursively removing any retired tree.
- Requested evidence: With an absent destination and unrelated retired-name sibling, verify the sibling stays at its original path. Include an unowned sentinel under a cache directory and a genuine interrupted upgrade.

**R3-F1** · P2 · defect · blocks readiness — Archive numbering can bind a review to another round's envelope
- Location: `agent_review/agent_review.py:2315`; acceptance: WF06, WF09
- Trigger: An enrollment reaches a three-digit round number or exceeds 999 transcript records.
- Expected: Archive lookup uses the exact round identity and its writer and validator agree on supported record numbers.
- Actual: archive extracts the round number using pub['key'][1:3]. For r100-review it looks up round 10 and can commit that round's envelope beside the round 100 review. Separately, the record-name check and sequence scan accept exactly three sequence digits, although the writer can produce sequence 1000.
- Why it blocks / does not: A long enrollment can archive the wrong provenance or become unable to archive otherwise valid records.
- Requested correction: Use the complete round identity for envelope lookup and a consistent sequence format for enumeration, writing, and validation.
- Requested evidence: Archive distinct round 10 and round 100 results and compare their request IDs and response hashes. Exercise the sequence transition from 999 to 1000.

**R3-F2** · P1 · defect · blocks readiness — The GitHub actor check can expire before a mutation
- Location: `agent_review/agent_review.py:1211`; acceptance: WF06, WF10
- Trigger: The active GitHub login changes during a long controller operation.
- Expected: Each external mutation verifies the current enrolled identity immediately before issuing the write and retains available confirmation afterward.
- Actual: verify_inputs checks the actor at command entry. send can POST much later and detects a changed actor only after the comment has been written. update_pr_body checks the PR identity but does not recheck the actor before editing. A long developer invocation or publication retry separates these writes from the initial check.
- Why it blocks / does not: The controller can modify the PR under an account outside the enrollment's authority. The PR body edit can also go undetected.
- Requested correction: Apply the actor and target guard at the mutation boundary for comment posts and PR edits, including retries.
- Requested evidence: Switch the simulated login after command-entry validation and before each mutation. Verify that the foreign account makes zero comment posts and zero PR edits.

**R3-F3** · P1 · required_gap · blocks readiness — The pinned permission file does not establish the headless developer's effective permissions
- Location: `agent_review/agent_review.py:785`; acceptance: WF07, WF10
- Trigger: The personal or project Claude configuration contains an allowance outside the enrolled profile.
- Expected: The developer receives the reviewed enrollment allowances while preserving managed restrictions and the owner's existing authentication.
- Actual: The headless launch supplies the composed --settings file while using the normal personal configuration directory and project working directory. It does not isolate other settings sources. Hashing the composed file therefore establishes the identity of one input without establishing the effective command allowances of the launched developer.
- Why it blocks / does not: The checkpoint requires narrow effective permissions. Ambient user or project allowances can expand the declared enrollment profile.
- Requested correction: Isolate or explicitly constrain the settings sources used by the headless launch and document the resulting effective profile.
- Requested evidence: Give a temporary user or project profile one harmless extra command allowance. Demonstrate that a launched headless developer can use its enrolled helper and that the ambient-only command is denied.

**R3-F4** · P1 · defect · blocks readiness — Envelope integrity failure abandons the verdict publication
- Location: `agent_review/agent_review.py:1700`; acceptance: WF05, WF06, WF07
- Trigger: A preserved result changes after its verdict has been queued but before the round is accepted.
- Expected: Discarding a validated result reconciles every publication that depended on that result.
- Actual: When a preserved envelope fails its binding check, finish_round invalidates the round and recursively starts another review. It leaves any pending or already-visible verdict for the old round untouched. settle_publications excludes the pending verdict, while missing_publications later requires it to have been posted.
- Why it blocks / does not: Recovery can leave an uncorrected public verdict or permanently obstruct handoff even after a fresh valid review.
- Requested correction: Retire the invalidated round's verdict and persist any required correction before replacing the round, using the same recovery rules as other invalidation paths.
- Requested evidence: Queue a verdict during a publication outage, damage its preserved envelope, then resume through a fresh review and final handoff. Cover both an unsent verdict and a stored but unacknowledged one.

**R3-F5** · P2 · defect · blocks readiness — Updating the status section can rewrite unrelated PR description text
- Location: `agent_review/agent_review.py:2665`; acceptance: WF06, WF10
- Trigger: An existing PR description contains owner-authored text that the transcript sanitizer transforms.
- Expected: Only the controller-owned section changes during a PR status update.
- Actual: update_pr_body sanitizes the generated status section, splices it into the PR description, then sanitizes the entire combined description again. Existing owner-authored text outside the status markers can be rewritten, for example when it contains a local home path.
- Why it blocks / does not: The controller's editing authority covers its status section. A routine handoff must preserve unrelated owner content.
- Requested correction: Sanitize the generated section before insertion and preserve the existing text outside its markers. If a safe edit cannot be made, refuse it before submitting a changed body.
- Requested evidence: Place owner text that would be transformed by sanitize on both sides of the status section. Update the section and compare the surrounding text exactly.

#### Prior finding assessments

- **R1-F1** — `fix_rejected` — The ordinary retirement case and three-digit verdict recognition work. The correction is still saved after retirement, and remote-only movement can exit before retirement.
- **R1-F11** — `fix_rejected` — Activation retires a queued round verdict. Public handoff invalidation can still be lost after the local activation save.
- **R1-F14** — `fix_verified` — ready_review now copies the original rnd.B. The final receipt renders that B and the separately recorded acceptance-time observation.
- **R1-F15** — `fix_rejected` — The explicit cap-stop test passes. A simultaneous no-progress stop takes precedence and bypasses the reason-string guard on resume.
- **R1-F16** — `fix_rejected` — Resume checks the active attempt before resetting it and performs a pre-PID lookup. Direct review-round recovery can still supersede the attempt before reconciliation.
- **R1-F17** — `fix_verified` — The helper checks the captured object, scans commit objects as well as blobs, rechecks the worktree, and pushes that exact SHA. The gate exercised the synthetic commit-message credential case against a bare origin.
- **R1-F18** — `fix_rejected` — The quoted search fixture passes. Comments and executable template expressions still receive incorrect classifications under the source-text scan.
- **R1-F19** — `fix_rejected` — Activation and cancellation seed the ledger, and known missing records now cause refusal. Direct replacement of completed pre-ledger state bypasses both seed paths.
- **R1-F2** — `fix_rejected` — The recorded tests cover syntactically truncated receipts and a changed log. A parseable receipt missing its identity is still discarded, and the gate-failure transition leaves verify unavailable.
- **R1-F20** — `fix_verified` — The archive-interruption cases use a killed controller subprocess and real Git commits. The gate exercised exact adoption and partial-commit rejection without replacing complete_archive.
- **R1-F3** — `fix_rejected` — Writer startup now participates in install.lock. Standalone helper locks remain outside the installer's active-lock inventory, and the refreshed fingerprint can describe different code from the loaded module.
- **R1-F4** — `fix_rejected` — Cancellation refuses while a helper holds its lock. A helper that loaded state immediately before cancellation can acquire the old lock afterward and act on stale authority.
- **R1-F5** — `fix_verified` — The helper entry points check foreground session identity or the enrollment-specific headless token. The headless launcher passes that token, and the recorded authority tests exercise mismatching callers.
- **R1-F6** — `fix_rejected` — The last-turn check and per-turn sandbox collection address the tested cases. Conflicting thread identities or earlier network and approval settings can still escape validation.
- **R1-F7** — `fix_verified` — Semantic validation now rejects blank evidence entries, assessment rationales, blocking explanations, and requested evidence. The recorded invalid-review suite covers whitespace-only inspected evidence.
- **R2-F1** — `fix_rejected` — Superseding the multipart verdict removes the permanent missing-publication error. The remaining review parts still never reach GitHub or the archive.
- **R2-F2** — `fix_rejected` — New ledger entries and this review's inbox contain complete findings. Legacy recovery still reads unverified envelopes and permits dispatch with missing finding text.
- **R2-F3** — `fix_rejected` — Unique staging and checks on ordinary existing destinations work. Recovery still moves a matching retired sibling before establishing ownership and excludes some unowned contents from its removal check.
- **R2-F4** — `fix_verified` — The push explicitly disables follow-tags. The gate enabled push.followTags, created a reachable annotated tag, pushed the branch, and verified the bare origin received no tag.
- **R2-F5** — `fix_verified` — The shipped Dice Roller profile removes both tools-wide Python allowances. Its named domain validation script remains available directly and through the declared gate.
- **R2-F6** — `fix_verified` — Resume recognizes a completed enrollment by phase done, rechecks its handoff before returning readiness, and sends a moved handoff through reopen. That branch precedes the foreground/headless split.

#### Evidence assessment

- **Inspected:** Fixed request, mission, owner addenda, repository instructions, operating guide, protocol, feature diff, round-two corrective diff, controller, schemas, prompts, permission profiles, behavior tests, and live-smoke fixture.; All 21 pending findings and dispositions, the supplied foreground transcript notice, gate receipt, and matching test log.
- **Executed verification:** Read-only Git checks confirmed HEAD at 3fe87d11d9d9140ab8a368f27a5c7150deea75b0 and the merge base at 79ab7af62729c2e329f267796780ce36fdffd07c. The mission file's SHA-256 matched the request.; The controller receipt binds the unit gate to H, records exit code 0 and an unchanged worktree, and names a log whose independently computed SHA-256 matches 49e3948236e7e265fb3b3bf5b295a64c198af00311c4b3f7c6df87212a02da06. The log reports 110 tests in 207.444 seconds, with 109 passing and the live smoke skipped.; The recorded suite includes real temporary Git repositories, OS locks, archive commits, and pre-commit and post-commit process interruption. It also exercised malformed review results, stale heads, lost publication responses, gate rejection, tag suppression, and intermediate-to-final continuation with simulated service boundaries.
- **Source inspection only:** Traced state writes, lock acquisition, subprocess dispatch, publication reconciliation, gate selection, reviewer provenance, legacy ledger recovery, archive selection, and PR body edits through their callers.; Inspected the model launch arguments and shipped permission files. The effective permissions of a running headless CLI were not observed in this snapshot.
- **Required gaps:** Demonstrate recovery through the next successful handoff after receipt retirement, activation, multipart publication, and lost gate evidence.; Exercise the reported process interleavings, exhausted-budget paths, upgrade cases, and conflicting provenance with the real controller and persistent state.; Verify that the effective headless permission profile matches the enrolled allowances and that every external mutation uses the current enrolled identity.
- **Limitations:** The review used the detached read-only snapshot. The recorded unit gate supplies execution evidence for its assertions. The failure paths identified by inspection are distinguished below from cases that the gate exercised.; The foreground transcript contains the controller's gate pointer. It supplies no command output for the separately claimed live-smoke run 11. That run is unconfirmed here and is not a reason for the intermediate decision.

#### Summary

- **Delivered behavior:** The controller provides fixed-candidate review, explicit model launches, structured validation, persistent rounds, guarded publication, gate receipts, and transcript archive checks. Verified improvements include exact-SHA pushes, tag suppression, preserved review-time B, complete new finding records, and real archive crash tests.
- **Scope reviewed:** Intermediate controller-core implementation and its evidence for WF04–WF10 and WF12 at the fixed candidate.
- **Pending later-phase work:** At setup-final, review the complete workflow documentation, installation and effective permissions, Black Tentacles binding, live pilot record, and setup acceptance report.
- **Unresolved questions:** none
- **Remaining owner review:** At final handoff, the owner judges operational suitability for their repositories and decides whether to merge or release.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `high` | `high` (turns ['high']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Codex CLI `0.170.0`, thread `01a1fbba-03dd-78a1-8261-05ea4e715d04`, duration 373.5s, response sha256 `58f4d9cc5ee97fc34a7f1f2925549c12ebdca0efaa463069087952b3c8b72f06`, request `devproc-claude-agent-review-controller-20261120192057-9024-r03-fb02b0`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "3fe87d11d9d9140ab8a368f27a5c7150deea75b0",
  "checkpoint_id": "controller-core",
  "checkpoint_type": "intermediate",
  "decision": "changes_required",
  "decision_rationale": "The candidate-bound unit gate passed, and eight prior fixes are verified. Controller-core still has paths that can accept an older gate receipt, attribute a result to the wrong reviewer thread, leave a stale handoff visible, or dispatch work after cancellation or budget exhaustion. The multipart publication test also ends with part of the historical review missing from both the PR and its eventual archive.",
  "evidence_assessment": {
    "executed_verification": [
      "Read-only Git checks confirmed HEAD at 3fe87d11d9d9140ab8a368f27a5c7150deea75b0 and the merge base at 79ab7af62729c2e329f267796780ce36fdffd07c. The mission file's SHA-256 matched the request.",
      "The controller receipt binds the unit gate to H, records exit code 0 and an unchanged worktree, and names a log whose independently computed SHA-256 matches 49e3948236e7e265fb3b3bf5b295a64c198af00311c4b3f7c6df87212a02da06. The log reports 110 tests in 207.444 seconds, with 109 passing and the live smoke skipped.",
      "The recorded suite includes real temporary Git repositories, OS locks, archive commits, and pre-commit and post-commit process interruption. It also exercised malformed review results, stale heads, lost publication responses, gate rejection, tag suppression, and intermediate-to-final continuation with simulated service boundaries."
    ],
    "inspected": [
      "Fixed request, mission, owner addenda, repository instructions, operating guide, protocol, feature diff, round-two corrective diff, controller, schemas, prompts, permission profiles, behavior tests, and live-smoke fixture.",
      "All 21 pending findings and dispositions, the supplied foreground transcript notice, gate receipt, and matching test log."
    ],
    "limitations": [
      "The review used the detached read-only snapshot. The recorded unit gate supplies execution evidence for its assertions. The failure paths identified by inspection are distinguished below from cases that the gate exercised.",
      "The foreground transcript contains the controller's gate pointer. It supplies no command output for the separately claimed live-smoke run 11. That run is unconfirmed here and is not a reason for the intermediate decision."
    ],
    "required_gaps": [
      "Demonstrate recovery through the next successful handoff after receipt retirement, activation, multipart publication, and lost gate evidence.",
      "Exercise the reported process interleavings, exhausted-budget paths, upgrade cases, and conflicting provenance with the real controller and persistent state.",
      "Verify that the effective headless permission profile matches the enrolled allowances and that every external mutation uses the current enrolled identity."
    ],
    "source_inspection_only": [
      "Traced state writes, lock acquisition, subprocess dispatch, publication reconciliation, gate selection, reviewer provenance, legacy ledger recovery, archive selection, and PR body edits through their callers.",
      "Inspected the model launch arguments and shipped permission files. The effective permissions of a running headless CLI were not observed in this snapshot."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "WF04",
        "WF06"
      ],
      "actual": "retire_receipts saves the receipt as superseded before queuing its correction. An exit between those operations makes the next call skip it permanently. There is also an earlier exit when only the remote branch moves: archive raises on the local/remote mismatch before finalize reaches receipt retirement. Finally, missing_publications skips a superseded receipt even when that exact receipt is required for the handoff.",
      "blocking_rationale": "The owner's PR can continue to show an obsolete handoff, or the final check can accept a receipt that the controller has already retired.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A visible obsolete receipt gets a durable correction. A current handoff requires an intact, posted receipt for that handoff.",
      "id": "R1-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2519
      },
      "priority": "P1",
      "requested_correction": "Persist the retirement and required correction together, reconcile visible receipts on early stale-head exits, and positively require the named active receipt during the final check.",
      "requested_evidence": "Interrupt after publication and at retirement, including a remote-only head move. Resume and verify the correction, then demonstrate that a retired or absent receipt cannot satisfy readiness.",
      "title": "A stale handoff receipt can survive retirement or count toward a later handoff",
      "trigger": "A final receipt is visible when the branch moves or the controller exits during receipt retirement."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF08",
        "WF12"
      ],
      "actual": "gate_receipts handles invalid JSON syntax, but silently filters out a parseable damaged receipt such as an empty object. An older pass then wins. When finish_round does detect invalid evidence, it has already posted the pass, accepted the round, cleared active_round, and charged the budget. It leaves the phase at review, where the verify helper is disabled and resume can dispatch another review of the same evidence.",
      "blocking_rationale": "One path advances on obsolete evidence. The other consumes reviews without giving the developer an ordinary way to restore the required gate.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The latest evidence for the candidate must be identifiable and valid. Loss of required evidence must leave a recoverable state before a pass is accepted.",
      "id": "R1-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1943
      },
      "priority": "P1",
      "requested_correction": "Validate receipt identity and structure against its controller-owned filename before filtering. Check required gates before publishing or accepting a pass and provide a transition that permits a replacement gate run.",
      "requested_evidence": "Replace a newer failing receipt with a valid JSON object missing its identity fields and verify the older pass is unusable. Damage a log during review, recover through verify and resume, and assert the round count and public verdicts throughout.",
      "title": "A damaged receipt can revive an older pass, and gate failure can strand recovery",
      "trigger": "A newer receipt loses required fields, or required evidence becomes invalid after the report is accepted."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "A foreground helper releases install.lock after acquiring its enrollment-local helper.lock. install probes only host_dir()/locks, so it can replace the installation during that helper. Also, guarded reloads the on-disk fingerprint under the lock after Python has already loaded the executable module. A process spanning a swap can therefore associate old controller code with the new fingerprint.",
      "blocking_rationale": "An operation can run under a version different from the version attributed to it.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Installation and startup interlock for the complete lifetime of operations that use a version, including standalone foreground helpers.",
      "id": "R1-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2135
      },
      "priority": "P1",
      "requested_correction": "Make active helpers visible to installation and bind the executing controller module to the same version as its schemas, prompts, and permission files.",
      "requested_evidence": "Hold a real foreground helper open while another process attempts installation. Also pause a controller process before writer-lock acquisition, switch versions, and verify it either runs one attributable version or refuses.",
      "title": "The installation interlock misses running helpers and preloaded controller code",
      "trigger": "An install overlaps a standalone verify operation or a process that loaded the old module before acquiring its writer lock."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "Both helper entry points construct Controller and read ACTIVE state before taking helper.lock. Cancellation can finish and release the claims in that interval. The helper then acquires its old lock and checks the cached state without reloading it or confirming registry ownership.",
      "blocking_rationale": "A cancelled enrollment can still run a gate or push after another enrollment becomes eligible to own the branch.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Helper authority must be established under the lock that excludes cancellation.",
      "id": "R1-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3314
      },
      "priority": "P1",
      "requested_correction": "Reload state and verify the current enrollment claims under the helper lock before performing either operation.",
      "requested_evidence": "Pause a real helper after initial lookup, cancel and replace the enrollment, then release the helper. Assert that the old helper produces neither a receipt nor a remote update.",
      "title": "A helper can use authority cached before cancellation",
      "trigger": "Cancellation wins the race between helper construction and helper-lock acquisition."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF10"
      ],
      "actual": "parse_codex_events keeps the first thread ID and accepts a later completion even if another thread.started intervenes. The result can then be checked against the first thread's rollout. Within a rollout, provenance collects all turn sandboxes but overwrites approval_policy and network at each settings event. A later compliant value hides an earlier conflicting one.",
      "blocking_rationale": "A valid-looking result can be accepted using provenance from a different thread or incomplete evidence of its effective permissions.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The completed result must belong to one unambiguous invocation whose relevant permission observations agree throughout.",
      "id": "R1-F6",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 645
      },
      "priority": "P1",
      "requested_correction": "Reject conflicting thread identities and conflicting approval or network observations. Validate event shapes so malformed records enter the bounded rejection path.",
      "requested_evidence": "Feed the real parsers a two-thread stream, conflicting settings followed by compliant settings, and a non-object event. Verify that no round advances and the failure is recorded.",
      "title": "Reviewer completion and permission provenance can come from different observations",
      "trigger": "The event stream names two threads, or the rollout contains multiple effective settings records."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF07"
      ],
      "actual": "activate clears the ready result and handoff and saves the new fingerprint before it retires the receipt or edits the PR body. A GitHub failure after that save leaves no durable public-update operation for the next activate or resume. A receipt visible just before the original handoff state was saved also misses the 'owner-review handoff' branch entirely.",
      "blocking_rationale": "The local enrollment can reopen successfully while the PR still directs the owner to review the superseded candidate.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Activating a new version must make public supersession recoverable for both completed and interrupted handoffs.",
      "id": "R1-F11",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2227
      },
      "priority": "P1",
      "requested_correction": "Record the required receipt correction and PR body update as durable operations when invalidating the handoff. Reconcile them on retry even when the new fingerprint is already active.",
      "requested_evidence": "Fail the simulated GitHub operation immediately after the activation state save. Restart and verify the receipt and PR description are corrected for both a completed handoff and an interrupted receipt publication.",
      "title": "Activation can lose the public handoff correction after saving local state",
      "trigger": "Activation invalidates a ready result while a handoff is visible, then publication or the process fails."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF08"
      ],
      "actual": "resume checks the completed count only when status_reason starts with 'review-round cap'. finish_round gives no-progress reasons precedence over the cap. A round that reaches both limits therefore resumes development with an exhausted budget. A later operational failure can likewise replace the reason string without changing the count.",
      "blocking_rationale": "The controller can enable helpers or launch another paid developer invocation before the owner grants more review rounds.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The persisted count and effective limit govern whether work requiring another review may start.",
      "id": "R1-F15",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2257
      },
      "priority": "P1",
      "requested_correction": "Enforce the numeric budget before reopening development or dispatching a further review, independently of the displayed stop reason. Preserve finalization of an already accepted pass.",
      "requested_evidence": "Reach no-progress and cap on the same round. Resume with the same limit and verify zero launches and disabled helpers, then extend the limit and demonstrate continuation.",
      "title": "Round-cap enforcement on resume depends on the wording of the last stop",
      "trigger": "An exhausted checkpoint also meets the no-progress condition or receives a subsequent operational stop."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF07"
      ],
      "actual": "resume now reconciles before resetting attempts. The normal review_round entry point still compares H/M and supersedes the active round before calling reconcile_reviewer_attempt. After a controller exit that leaves status ACTIVE, run or foreground review can take this route. An M-only move with unchanged H can immediately launch a replacement.",
      "blocking_rationale": "A live reviewer can be lost from active state while another paid invocation starts.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every entry point that replaces an active round must first settle its unfinished process and snapshot.",
      "id": "R1-F16",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1409
      },
      "priority": "P1",
      "requested_correction": "Reconcile the previous active attempt before candidate comparison can supersede it, including recovery through run and review.",
      "requested_evidence": "Leave a reviewer subprocess alive, move the comparison input, and enter through the normal review path. Verify a single launch while it is alive and cleanup after it exits, including the pre-PID-save case.",
      "title": "Candidate replacement can discard an unreconciled reviewer attempt",
      "trigger": "The controller exits during review and the comparison input moves before the next normal invocation."
    },
    {
      "acceptance_ids": [
        "WF05"
      ],
      "actual": "Removing quoted strings fixes the reported shell-search example. JavaScript comments remain in the scanned text, so a comment spelling a delegation call still invalidates the review. Removing an entire template literal also removes its executable interpolation expressions.",
      "blocking_rationale": "The provenance decision can both reject a harmless review and miss an actual dispatch.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The controller distinguishes actual delegation from inert text in tool inputs.",
      "id": "R1-F18",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 622
      },
      "priority": "P2",
      "requested_correction": "Use recorded tool-dispatch identity where available. If code-mode inspection remains necessary, handle comments and executable expressions without treating all text in a template literal alike.",
      "requested_evidence": "Exercise literal search text, an inert comment, direct dispatch, and dispatch in an expression through the rollout parser. Verify the classification for each.",
      "title": "Delegation detection still classifies source text instead of executed operations",
      "trigger": "A code-mode input includes a call signature in a comment or an executable expression within a template literal."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF09"
      ],
      "actual": "Activation and cancellation now seed the host ledger. Direct re-enrollment is also allowed from AWAITING_OWNER_REVIEW. That path reads the previous claim to check status, then loads only the host ledger. For a completed pre-ledger enrollment, the authenticated archived map remains in the old state and the replacement claim loses that inventory.",
      "blocking_rationale": "Genuine records can prevent the next review as foreign files, or previously recorded deletions can go undetected.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every supported transition to a new enrollment preserves and verifies the prior PR inventory.",
      "id": "R1-F19",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2903
      },
      "priority": "P1",
      "requested_correction": "When replacing a completed claim, import its applicable authenticated PR inventory under the enrollment lock and check the entire inventory before writing the replacement claim.",
      "requested_evidence": "Start with completed pre-upgrade state and no host ledger. Re-enroll directly with intact records, then repeat with a missing record and verify refusal before ownership changes.",
      "title": "Direct re-enrollment skips migration from a completed pre-upgrade enrollment",
      "trigger": "A completed enrollment with archived records predates the host ledger and is replaced without a separate activate or cancel."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF09"
      ],
      "actual": "make_historical marks a partially visible verdict superseded and publishes only a short correction. The remaining review parts are never published. archive skips the superseded publication, including its envelope. The regression asserts that missing_publications is empty, which now succeeds because the incomplete record is excluded.",
      "blocking_rationale": "A later handoff can succeed while some independent findings are unavailable in either required public record.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A stale verdict is visibly historical and its complete substantive content remains available on the PR and in the archive.",
      "id": "R2-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1778
      },
      "priority": "P1",
      "requested_correction": "Persist and publish a complete historical rendering when only part of the current verdict was sent. Archive that historical result with its correct provenance.",
      "requested_evidence": "Interrupt a multipart review after part one, move H, then finish a subsequent handoff. Locate a finding from the last part in both the PR history and the committed records.",
      "title": "Retiring a partial verdict drops the rest of the historical review",
      "trigger": "The head moves after the service stores one part of a multipart verdict."
    },
    {
      "acceptance_ids": [
        "WF08",
        "WF12"
      ],
      "actual": "The current inbox contains complete findings. For older entries, full_findings reads any available envelope at envelope_path without comparing its recorded digest. It silently leaves the finding incomplete when the file is absent. Either case can dispatch a reviewer without the authenticated finding it must assess.",
      "blocking_rationale": "A proposed fix can be judged against altered or incomplete acceptance text.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every pending prior assessment receives the full authenticated finding from its applicable accepted round.",
      "id": "R2-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1519
      },
      "priority": "P1",
      "requested_correction": "Verify the retained envelope against its recorded digest before recovery and require complete recovered text for every pending assessment before dispatch.",
      "requested_evidence": "Use a legacy ledger entry with an intact, altered, and missing accepted envelope. Only the intact case should dispatch with the original trigger and requested evidence.",
      "title": "Legacy finding recovery accepts unauthenticated text or silently omits it",
      "trigger": "A pending ledger entry predates storage of the full finding and its retained envelope has changed or disappeared."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "When the destination is absent, install moves the last directory matching dest.retired-* into the destination before validating its manifest or ownership. An unrelated matching sibling is therefore moved even if installation subsequently refuses. The destination inventory also excludes every file below a directory named __pycache__ before recursively removing the retired tree.",
      "blocking_rationale": "An install or recovery command can move or delete unrelated owner files.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Recovery acts only on an identified installation transaction and preserves unrelated paths on refusal.",
      "id": "R2-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3062
      },
      "priority": "P1",
      "requested_correction": "Identify and validate the specific retired installation before moving it. Account for unowned contents before recursively removing any retired tree.",
      "requested_evidence": "With an absent destination and unrelated retired-name sibling, verify the sibling stays at its original path. Include an unowned sentinel under a cache directory and a genuine interrupted upgrade.",
      "title": "Installation recovery takes ownership of a sibling by name alone",
      "trigger": "The install destination is absent and an unrelated sibling matches the retirement naming pattern."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF09"
      ],
      "actual": "archive extracts the round number using pub['key'][1:3]. For r100-review it looks up round 10 and can commit that round's envelope beside the round 100 review. Separately, the record-name check and sequence scan accept exactly three sequence digits, although the writer can produce sequence 1000.",
      "blocking_rationale": "A long enrollment can archive the wrong provenance or become unable to archive otherwise valid records.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Archive lookup uses the exact round identity and its writer and validator agree on supported record numbers.",
      "id": "R3-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2315
      },
      "priority": "P2",
      "requested_correction": "Use the complete round identity for envelope lookup and a consistent sequence format for enumeration, writing, and validation.",
      "requested_evidence": "Archive distinct round 10 and round 100 results and compare their request IDs and response hashes. Exercise the sequence transition from 999 to 1000.",
      "title": "Archive numbering can bind a review to another round's envelope",
      "trigger": "An enrollment reaches a three-digit round number or exceeds 999 transcript records."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF10"
      ],
      "actual": "verify_inputs checks the actor at command entry. send can POST much later and detects a changed actor only after the comment has been written. update_pr_body checks the PR identity but does not recheck the actor before editing. A long developer invocation or publication retry separates these writes from the initial check.",
      "blocking_rationale": "The controller can modify the PR under an account outside the enrollment's authority. The PR body edit can also go undetected.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Each external mutation verifies the current enrolled identity immediately before issuing the write and retains available confirmation afterward.",
      "id": "R3-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1211
      },
      "priority": "P1",
      "requested_correction": "Apply the actor and target guard at the mutation boundary for comment posts and PR edits, including retries.",
      "requested_evidence": "Switch the simulated login after command-entry validation and before each mutation. Verify that the foreign account makes zero comment posts and zero PR edits.",
      "title": "The GitHub actor check can expire before a mutation",
      "trigger": "The active GitHub login changes during a long controller operation."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "The headless launch supplies the composed --settings file while using the normal personal configuration directory and project working directory. It does not isolate other settings sources. Hashing the composed file therefore establishes the identity of one input without establishing the effective command allowances of the launched developer.",
      "blocking_rationale": "The checkpoint requires narrow effective permissions. Ambient user or project allowances can expand the declared enrollment profile.",
      "blocks_readiness": true,
      "category": "required_gap",
      "expected": "The developer receives the reviewed enrollment allowances while preserving managed restrictions and the owner's existing authentication.",
      "id": "R3-F3",
      "location": {
      

---

<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r03-review part=2/2 sha256=97e1e008a9a8ac6ef7c7e608c96f24f235423ebd61fd01c0cb46318886105c96 -->
_Part 2 of 2._

  "file": "agent_review/agent_review.py",
        "line": 785
      },
      "priority": "P1",
      "requested_correction": "Isolate or explicitly constrain the settings sources used by the headless launch and document the resulting effective profile.",
      "requested_evidence": "Give a temporary user or project profile one harmless extra command allowance. Demonstrate that a launched headless developer can use its enrolled helper and that the ambient-only command is denied.",
      "title": "The pinned permission file does not establish the headless developer's effective permissions",
      "trigger": "The personal or project Claude configuration contains an allowance outside the enrolled profile."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF06",
        "WF07"
      ],
      "actual": "When a preserved envelope fails its binding check, finish_round invalidates the round and recursively starts another review. It leaves any pending or already-visible verdict for the old round untouched. settle_publications excludes the pending verdict, while missing_publications later requires it to have been posted.",
      "blocking_rationale": "Recovery can leave an uncorrected public verdict or permanently obstruct handoff even after a fresh valid review.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Discarding a validated result reconciles every publication that depended on that result.",
      "id": "R3-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1700
      },
      "priority": "P1",
      "requested_correction": "Retire the invalidated round's verdict and persist any required correction before replacing the round, using the same recovery rules as other invalidation paths.",
      "requested_evidence": "Queue a verdict during a publication outage, damage its preserved envelope, then resume through a fresh review and final handoff. Cover both an unsent verdict and a stored but unacknowledged one.",
      "title": "Envelope integrity failure abandons the verdict publication",
      "trigger": "A preserved result changes after its verdict has been queued but before the round is accepted."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF10"
      ],
      "actual": "update_pr_body sanitizes the generated status section, splices it into the PR description, then sanitizes the entire combined description again. Existing owner-authored text outside the status markers can be rewritten, for example when it contains a local home path.",
      "blocking_rationale": "The controller's editing authority covers its status section. A routine handoff must preserve unrelated owner content.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Only the controller-owned section changes during a PR status update.",
      "id": "R3-F5",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2665
      },
      "priority": "P2",
      "requested_correction": "Sanitize the generated section before insertion and preserve the existing text outside its markers. If a safe edit cannot be made, refuse it before submitting a changed body.",
      "requested_evidence": "Place owner text that would be transformed by sanitize on both sides of the status section. Update the section and compare the surrounding text exactly.",
      "title": "Updating the status section can rewrite unrelated PR description text",
      "trigger": "An existing PR description contains owner-authored text that the transcript sanitizer transforms."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F1",
      "rationale": "The ordinary retirement case and three-digit verdict recognition work. The correction is still saved after retirement, and remote-only movement can exit before retirement."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F11",
      "rationale": "Activation retires a queued round verdict. Public handoff invalidation can still be lost after the local activation save."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F14",
      "rationale": "ready_review now copies the original rnd.B. The final receipt renders that B and the separately recorded acceptance-time observation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F15",
      "rationale": "The explicit cap-stop test passes. A simultaneous no-progress stop takes precedence and bypasses the reason-string guard on resume."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F16",
      "rationale": "Resume checks the active attempt before resetting it and performs a pre-PID lookup. Direct review-round recovery can still supersede the attempt before reconciliation."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F17",
      "rationale": "The helper checks the captured object, scans commit objects as well as blobs, rechecks the worktree, and pushes that exact SHA. The gate exercised the synthetic commit-message credential case against a bare origin."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F18",
      "rationale": "The quoted search fixture passes. Comments and executable template expressions still receive incorrect classifications under the source-text scan."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F19",
      "rationale": "Activation and cancellation seed the ledger, and known missing records now cause refusal. Direct replacement of completed pre-ledger state bypasses both seed paths."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F2",
      "rationale": "The recorded tests cover syntactically truncated receipts and a changed log. A parseable receipt missing its identity is still discarded, and the gate-failure transition leaves verify unavailable."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F20",
      "rationale": "The archive-interruption cases use a killed controller subprocess and real Git commits. The gate exercised exact adoption and partial-commit rejection without replacing complete_archive."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F3",
      "rationale": "Writer startup now participates in install.lock. Standalone helper locks remain outside the installer's active-lock inventory, and the refreshed fingerprint can describe different code from the loaded module."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F4",
      "rationale": "Cancellation refuses while a helper holds its lock. A helper that loaded state immediately before cancellation can acquire the old lock afterward and act on stale authority."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F5",
      "rationale": "The helper entry points check foreground session identity or the enrollment-specific headless token. The headless launcher passes that token, and the recorded authority tests exercise mismatching callers."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F6",
      "rationale": "The last-turn check and per-turn sandbox collection address the tested cases. Conflicting thread identities or earlier network and approval settings can still escape validation."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F7",
      "rationale": "Semantic validation now rejects blank evidence entries, assessment rationales, blocking explanations, and requested evidence. The recorded invalid-review suite covers whitespace-only inspected evidence."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F1",
      "rationale": "Superseding the multipart verdict removes the permanent missing-publication error. The remaining review parts still never reach GitHub or the archive."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F2",
      "rationale": "New ledger entries and this review's inbox contain complete findings. Legacy recovery still reads unverified envelopes and permits dispatch with missing finding text."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F3",
      "rationale": "Unique staging and checks on ordinary existing destinations work. Recovery still moves a matching retired sibling before establishing ownership and excludes some unowned contents from its removal check."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F4",
      "rationale": "The push explicitly disables follow-tags. The gate enabled push.followTags, created a reachable annotated tag, pushed the branch, and verified the bare origin received no tag."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F5",
      "rationale": "The shipped Dice Roller profile removes both tools-wide Python allowances. Its named domain validation script remains available directly and through the declared gate."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F6",
      "rationale": "Resume recognizes a completed enrollment by phase done, rechecks its handoff before returning readiness, and sends a moved handoff through reopen. That branch precedes the foreground/headless split."
    }
  ],
  "request_id": "devproc-claude-agent-review-controller-20261120192057-9024-r03-fb02b0",
  "round": 3,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "The controller provides fixed-candidate review, explicit model launches, structured validation, persistent rounds, guarded publication, gate receipts, and transcript archive checks. Verified improvements include exact-SHA pushes, tag suppression, preserved review-time B, complete new finding records, and real archive crash tests.",
    "pending_later_phase_work": [
      "At setup-final, review the complete workflow documentation, installation and effective permissions, Black Tentacles binding, live pilot record, and setup acceptance report."
    ],
    "remaining_owner_review": [
      "At final handoff, the owner judges operational suitability for their repositories and decides whether to merge or release."
    ],
    "scope_reviewed": "Intermediate controller-core implementation and its evidence for WF04\u2013WF10 and WF12 at the fixed candidate.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
