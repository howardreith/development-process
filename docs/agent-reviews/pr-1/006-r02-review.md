<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r02-review part=1/2 sha256=e3c35d69c307dd12db324841ea22609ebf1936ea576bfdf416c0d51642118fbb -->
_Part 1 of 2._

### Codex GPT-6.2 Astra — review — round 2 — candidate `78868323c0`

**Decision:** `changes_required` — The candidate-bound unit gate passed, and the archive commit checks are materially stronger. Controller-core still has paths that accept an empty prior-finding assessment, launch a second reviewer during recovery, or leave an obsolete owner handoff visible. Several regressions exercise an internal method while the documented command takes a different path. These issues affect WF04–WF10 and must be resolved before advancing.

#### Findings

**R1-F1** · P1 · defect · blocks readiness — An interrupted final handoff can leave stale readiness visible
- Location: `agent_review/agent_review.py:2418`; acceptance: WF04, WF06
- Trigger: GitHub stores the final receipt, the controller exits before recording the handoff, and the reviewed conditions change before resume.
- Expected: A visible obsolete verdict receives a correction, and an unsent obsolete verdict stays unsent, for both review and final-handoff messages.
- Actual: On restart, finalize can invalidate the result or stop at its first readiness check without reconciling the already-visible final-status comment. The owner can still see an uncorrected 'awaiting owner review' receipt. Also, the generic outbox exclusion recognizes only two-digit round verdicts, although round numbers can exceed 99.
- Why it blocks / does not: The PR is the owner's handoff surface. A local stop alone leaves a stale public verdict.
- Requested correction: Reconcile any pending or visible final receipt when abandoning its handoff. Persist the correction before leaving finalization. Identify verdict records independently of a two-digit round width.
- Requested evidence: Interrupt after the simulated GitHub service stores the final receipt, move the head, then resume. Assert a visible correction, no current handoff, and no duplicate receipt. Cover a three-digit round key.

**R1-F2** · P1 · defect · blocks readiness — Damaged or superseded gate evidence can still advance a checkpoint
- Location: `agent_review/agent_review.py:1876`; acceptance: WF05, WF08, WF12
- Trigger: A newer receipt becomes unreadable, or required evidence changes after report acceptance and before a preserved intermediate verdict is accepted.
- Expected: The latest required run must be identifiable and verifiable when the checkpoint advances.
- Actual: gate_receipts silently skips unreadable JSON, allowing an older pass to become authoritative again. finish_round also accepts an intermediate pass without rechecking required gates after the report was accepted.
- Why it blocks / does not: An intermediate checkpoint can advance with obsolete or unverifiable required evidence.
- Requested correction: Fail closed on a damaged receipt belonging to the candidate and gate. Recheck the required gate set before accepting a passing round, including a preserved result on resume.
- Requested evidence: Record a pass followed by a failure, truncate the newer receipt, and verify the older pass is unusable. Invalidate a required log between review validation and intermediate acceptance and assert the checkpoint index stays fixed.

**R1-F3** · P1 · defect · blocks readiness — The install lock excludes other installers but cannot exclude a new controller
- Location: `agent_review/agent_review.py:2918`; acceptance: WF07, WF10
- Trigger: A controller starts while install is staging a replacement after checking existing writer locks.
- Expected: Starting a controller and replacing its installation must be mutually exclusive across the handoff between versions.
- Actual: install probes each currently known writer lock and releases it immediately. writer_lock never participates in install.lock. A controller can start after the probe and overlap the directory swap. The two renames also leave a window with no installation at the configured path.
- Why it blocks / does not: An installation can change under a live invocation, including a developer about to call the installed helper.
- Requested correction: Use a shared installation/startup interlock or immutable versioned installations with a recoverable activation switch. Cover writers that start while installation is already in progress.
- Requested evidence: Use separate processes to start a controller after the installer's initial lock check. Verify a single complete version is used and interrupt the installer at the switch to verify recovery.

**R1-F4** · P1 · defect · blocks readiness — Cancellation can release the worktree under a running foreground helper
- Location: `agent_review/agent_review.py:2065`; acceptance: WF07, WF10
- Trigger: The owner cancels while a foreground validation or push helper is running and no configured runtime lock exists.
- Expected: Ownership is released only after in-flight developer operations reach a safe boundary.
- Actual: cancel checks the recorded headless developer and configured runtime lock files. A foreground verify or push helper holds no corresponding enrollment operation lock and has no recorded PID. Cancellation can therefore release the claims while that helper is still executing.
- Why it blocks / does not: A replacement enrollment can acquire the same worktree while a previously authorized operation is still using it.
- Requested correction: Coordinate helper lifetimes with cancellation and re-enrollment while retaining the ability for the owning headless developer to invoke helpers.
- Requested evidence: Hold a real foreground gate process open, request cancellation from another process, and verify that a replacement enrollment cannot take ownership until the helper exits.

**R1-F5** · P1 · defect · blocks readiness — Helper checks authenticate the target but omit the calling developer
- Location: `agent_review/agent_review.py:2042`; acceptance: WF07, WF10
- Trigger: A helper is invoked with the ID of a different active enrollment belonging to the same GitHub account.
- Expected: The developer helper must establish that the caller owns development authority for the chosen enrollment.
- Actual: helper_authority_problems inspects the target worktree through self.git and the shared GitHub login. It never checks the caller against foreground_session. Two active foreground sessions using the same account can operate on one another's enrollments by ID.
- Why it blocks / does not: The globally permitted foreground helper can dispatch another enrollment's validation or publish its branch.
- Requested correction: Bind foreground helper calls to the enrolled developer session, as foreground reports already are. Establish equivalent invocation ownership for headless helpers.
- Requested evidence: Use two enrolled sessions under the same actor. Show each can invoke its own helper and that a cross-enrollment call performs no gate or push.

**R1-F6** · P1 · defect · blocks readiness — An earlier completion can satisfy an unfinished reviewer invocation
- Location: `agent_review/agent_review.py:585`; acceptance: WF05, WF10
- Trigger: A zero-exit invocation supplies structured output and an earlier completion event, followed by an incomplete turn or conflicting profile metadata.
- Expected: The completed result, terminal event, thread and permitted reviewer profile must agree for the invocation being accepted.
- Actual: CodexReviewer.run sets completed when it sees any turn.completed and ignores malformed event lines. A later unfinished turn does not clear that flag. Provenance likewise retains the last nonempty sandbox value across turn contexts, and invocation_problems ignores the observed network setting.
- Why it blocks / does not: A final message can pass validation with an incomplete terminal stream or contradictory execution-profile evidence.
- Requested correction: Validate the terminal state of the actual event sequence. Reject incomplete or contradictory turn/profile observations, including an explicitly wider network profile.
- Requested evidence: Feed the real event and rollout parsers labeled fixtures with a completed turn followed by an unfinished turn, malformed trailing output, and contradictory sandbox/network observations. Assert that none can advance the round.

**R1-F7** · P1 · defect · blocks readiness — Blank evidence and blank fix assessments can still produce readiness
- Location: `agent_review/agent_review.py:1589`; acceptance: WF05, WF08
- Trigger: The reviewer supplies correctly typed strings that contain no substantive text.
- Expected: Passing decisions must identify actual inspected evidence, and each accepted prior disposition must carry a nonblank rationale.
- Actual: A passing review with inspected set to a single whitespace string passes the list-presence check. A fix_verified assessment can have an empty rationale and still close a blocking finding. Several required finding explanations are also allowed to be blank.
- Why it blocks / does not: A blocking issue can be closed without the required reviewer assessment, and an empty evidence statement can satisfy the pass guard.
- Requested correction: Validate nonblank evidence entries, prior-assessment rationales and required finding explanations before applying ledger transitions.
- Requested evidence: Submit a schema-valid final pass containing whitespace-only inspected evidence and a separate pass closing a blocker with an empty rationale. Both must leave the ledger and readiness unchanged.

**R1-F11** · P1 · defect · blocks readiness — Workflow activation leaves old verdict publications unresolved
- Location: `agent_review/agent_review.py:2119`; acceptance: WF04, WF06, WF07
- Trigger: A reviewed workflow is activated while a verdict is pending publication or after an owner handoff has been posted.
- Expected: Invalidating an old-version result reconciles its public and pending records as part of the same recoverable transition.
- Actual: activate clears a validated round without resolving its pending review publication. settle_publications always skips that verdict, while missing_publications still requires it, permanently obstructing a later handoff. In the completed-handoff case activation changes local state but leaves the old PR status section and receipt declaring readiness.
- Why it blocks / does not: An upgrade can strand a required publication or leave owners relying on a handoff the controller has invalidated.
- Requested correction: Retire or correct the old round's outbox record according to what is already visible. Persist and publish the supersession of an existing owner handoff, including its PR description.
- Requested evidence: Activate during a verdict publication outage, then complete a fresh review and finalize. Separately activate after a completed handoff and verify that both the description and comments identify it as superseded.

**R1-F14** · P2 · defect · blocks readiness — The final receipt can replace the captured target tip
- Location: `agent_review/agent_review.py:1698`; acceptance: WF04
- Trigger: The target advances without changing the merge base before a final review is accepted.
- Expected: The captured H/B/M remains immutable through the final receipt. Subsequent target observations are recorded separately.
- Actual: The retried request and envelope now retain B, but ready_review stores B_at_acceptance in the B field. finalize then labels that later value 'target at review B'. The final receipt can therefore identify a different tuple from the published request and accepted envelope.
- Why it blocks / does not: The owner cannot use the handoff tuple to identify the comparison actually requested without reconstructing it from earlier records.
- Requested correction: Keep rnd.B as the reviewed B in ready_review and the handoff. Carry the reconciled target tip and observation time in separate fields.
- Requested evidence: Move the target without changing M during a final round. Assert that the request, envelope, ready result and final receipt show the same original B and separately report the new target tip.

**R1-F15** · P2 · defect · blocks readiness — Resume reopens development even when the round budget is still exhausted
- Location: `agent_review/agent_review.py:2154`; acceptance: WF07, WF08
- Trigger: The owner resumes a cap-stopped enrollment without increasing the limit above the completed count.
- Expected: An exhausted checkpoint stays stopped until an owner supplies a sufficient round extension.
- Actual: The last permitted changes_required now saves BLOCKED immediately. A subsequent resume without a larger limit sets ACTIVE in phase develop and can launch another headless developer or enable foreground helpers. The cap blocks only when that new work reaches review.
- Why it blocks / does not: An exhausted checkpoint can consume another development invocation and change the branch without any remaining review round.
- Requested correction: Check the persisted count against the effective limit before reactivating development after a cap stop.
- Requested evidence: At a one-round cap, resume with no extension and with an unchanged limit. Assert zero additional developer launches and disabled helpers, then demonstrate continuation with a larger limit.

**R1-F16** · P1 · defect · blocks readiness — The documented resume path clears the reviewer attempt it must reconcile
- Location: `agent_review/agent_review.py:2153`; acceptance: WF05, WF07
- Trigger: The controller exits during review and the owner uses resume while the original reviewer is still running.
- Expected: Recovery settles an interrupted invocation before resetting any retry budget, removing its snapshot, or launching another reviewer.
- Actual: resume moves the active attempts to earlier_attempts and resets attempts before review_round calls reconcile_reviewer_attempt. The live PID is therefore invisible to reconciliation. There is also no lookup for a reviewer launched immediately before its PID was saved.
- Why it blocks / does not: The documented host-recovery command can launch a duplicate paid reviewer and leave its predecessor's snapshot behind.
- Requested correction: Reconcile unfinished attempts before resetting, superseding or replacing their round. Make the launch-to-PID-record interval recoverable.
- Requested evidence: Exercise resume with a live reviewer subprocess, then after it exits. Assert one launch while live, cleanup after exit, and monotonic attempt IDs. Include interruption before PID persistence.

**R1-F17** · P1 · defect · blocks readiness — The guarded push can publish a different object from the one it scanned
- Location: `agent_review/agent_review.py:2672`; acceptance: WF10
- Trigger: Local HEAD advances during a long outgoing-history scan, or a credential appears in commit text rather than a file.
- Expected: Only the inspected commit may be published, and the credential check covers newly published history containing user-authored text.
- Actual: The helper scans the captured head but pushes symbolic HEAD. If HEAD changes during the scan, a different commit is transferred before the post-push mismatch is reported. The scan also skips commit objects entirely, including commit messages containing a recognized credential pattern.
- Why it blocks / does not: The guarded route can publish uninspected content. Detecting the mismatch after the remote write cannot retract it.
- Requested correction: Push the verified object ID in the explicit refspec, recheck relevant authority before dispatch, and cover outgoing commit metadata in the credential check.
- Requested evidence: Advance local HEAD between inspection and push against a bare origin and verify the newer object is never published. Include a harmless synthetic credential marker in a commit message.

**R1-F18** · P2 · defect · blocks readiness — A literal source search can still be classified as delegation
- Location: `agent_review/agent_review.py:628`; acceptance: WF05
- Trigger: A code-mode shell search includes the full spelling and opening parenthesis of a delegation call.
- Expected: Delegation detection follows actual tool dispatch. Source literals, strings and comments do not invalidate a review.
- Actual: The code-mode branch searches the entire custom tool input with a regular expression. A quoted search for the literal delegation call syntax matches just as an executed call would.
- Why it blocks / does not: An ordinary read-only review of this controller can exhaust its retries solely because of the source text it searches.
- Requested correction: Use structured dispatch evidence for delegation, or otherwise distinguish executed operations from literals in code-mode input.
- Requested evidence: Pass rollout fixtures for a quoted exact call-signature search and an actual delegation dispatch through provenance. Only the dispatch should invalidate the invocation.

**R1-F19** · P1 · defect · blocks readiness — The new record ledger loses pre-upgrade or missing records
- Location: `agent_review/agent_review.py:2843`; acceptance: WF07, WF09
- Trigger: A PR already contains records from before the host ledger existed, or a recorded file is removed before re-enrollment.
- Expected: Re-enrollment preserves the authenticated inventory of the PR, including existing enrollments, and detects missing or altered records.
- Actual: Only new archives populate the new host ledger. Existing authenticated archived maps are never migrated on activation. On re-enrollment, entries missing from HEAD are also silently filtered out, so a record added after M and later deleted can disappear from both inventories.
- Why it blocks / does not: Genuine pre-upgrade records can block continuation, while deletion of a known record can escape the append-only check.
- Requested correction: Migrate authenticated records from earlier enrollment state and verify the complete applicable inventory against the branch. Treat missing expected records as an integrity failure.
- Requested evidence: Re-enroll from pre-upgrade state with genuine archived records and no host ledger. Then delete one known post-base record before re-enrollment and verify the missing path is reported.

**R1-F20** · P2 · required_gap · blocks readiness — Three archive tests still replace an internal controller operation
- Location: `agent_review/test_agent_review.py:508`; acceptance: WF09
- Trigger: The unit gate runs the older archive recovery tests alongside the new subprocess tests.
- Expected: All archive recovery cases use real controller operations, state and Git commits.
- Actual: The new subprocess crash tests ran, but three existing cases still subclass Controller and replace complete_archive, at lines 508, 1267 and 1602. The partial-commit rejection case still relies on that internal replacement.
- Why it blocks / does not: The checkpoint expressly limits stubs to model and GitHub boundaries.
- Requested correction: Remove redundant internally stubbed cases and port any distinct assertions, particularly partial-commit rejection, to the real crash fixture.
- Requested evidence: Run the candidate-bound unit gate with real interruption, exact adoption and partial-commit rejection covered without a Controller override.

**R2-F1** · P1 · defect · blocks readiness — One visible chunk marks an entire stale review as posted
- Location: `agent_review/agent_review.py:1713`; acceptance: WF04, WF06, WF09
- Trigger: Only part of a split verdict reaches GitHub before interruption and the candidate changes before recovery.
- Expected: Every visible part is reconciled and the complete historical review remains available. A partially delivered message must have a recoverable disposition.
- Actual: already_visible returns true when any part exists. make_historical then marks the entire normal verdict posted and sends only a correction. Unsent parts retain null comment IDs, causing missing_publications to fail indefinitely and the public review to remain incomplete.
- Why it blocks / does not: One interrupted long review can prevent every later handoff for the enrollment.
- Requested correction: Track partial publication explicitly. Correct the visible parts and publish the complete historical result under an appropriate marker without requiring nonexistent comment IDs.
- Requested evidence: Interrupt a two-part verdict after part one, move H, resume, and complete a subsequent valid handoff. Verify the full historical result is available and every required publication reconciles.

**R2-F2** · P1 · required_gap · blocks readiness — The reviewer receives a finding title where it needs the original finding
- Location: `agent_review/agent_review.py:1665`; acceptance: WF08, WF12
- Trigger: A later round must verify or reject a developer disposition using the read-only snapshot.
- Expected: Each pending assessment has the original accepted finding and the developer's response available in the fixed review inputs.
- Actual: finish_round retains only a finding's title, classification and counters in the ledger. The next reviewer's inbox omits the original trigger, expected and actual behavior, location, acceptance IDs, requested correction and requested evidence. This round's inbox demonstrates the omission.
- Why it blocks / does not: An independent reviewer cannot reliably assess a proposed fix against the original finding, especially when the developer interprets it differently.
- Requested correction: Include the full authenticated prior finding in the next inbox, with its originating round. Recover it from retained envelopes for existing enrollments.
- Requested evidence: In a two-round fixture, verify that the second reviewer can read the exact trigger and requested evidence of the first review alongside the disposition.

**R2-F3** · P1 · defect · blocks readiness — Installation can delete directories it does not own
- Location: `agent_review/agent_review.py:2923`; acceptance: WF07, WF10
- Trigger: The requested destination or its .staging sibling already contains unrelated files.
- Expected: Installation modifies only a validated controller installation and its own newly allocated staging area.
- Actual: install recursively deletes a predictably named sibling staging directory. It also retires and recursively deletes any existing destination, including a non-install directory or unrelated files within an installation. The previous manifest is never used to establish ownership of what will be removed.
- Why it blocks / does not: A routine setup command can irreversibly delete unrelated workspace or owner data.
- Requested correction: Allocate unique staging storage and verify ownership of an existing destination before replacement. Preserve unrelated files or refuse the operation before mutation.
- Requested evidence: Use temporary directories containing unrelated sentinel files at the destination and conventional staging name. A refused installation must leave both intact, and a genuine upgrade must still succeed.

**R2-F4** · P1 · defect · blocks readiness — Ambient Git configuration can expand a branch push to tags
- Location: `agent_review/agent_review.py:2672`; acceptance: WF10
- Trigger: The owner has enabled push.followTags and the outgoing history has a local annotated tag absent from origin.
- Expected: The built-in push transfers only the authorized branch ref regardless of ambient tag-following preferences.
- Actual: The explicit branch refspec does not disable Git's push.followTags setting. With that setting enabled, a guarded branch push can also publish a reachable annotated tag. The post-push check inspects only the branch.
- Why it blocks / does not: The owner authorized writes to one enrolled branch and retained control of tagging.
- Requested correction: Explicitly disable following tags for this fixed push operation.
- Requested evidence: Enable push.followTags in a temporary repository with a reachable local annotated tag. Verify the enrolled branch advances and the bare origin receives no tag.

**R2-F5** · P1 · defect · blocks readiness — One shipped developer profile permits an entire directory of scripts
- Location: `agent_review/projects/kingmaker-dice-roller.json:34`; acceptance: WF10
- Trigger: A headless enrollment uses the Kingmaker Dice Roller project profile.
- Expected: Project permissions name the actual validation entry points authorized for that repository.
- Actual: The Dice Roller project allows Python execution for every path under tools in both shells. That directory is writable by the developer, so the permission set includes future, unreviewed scripts as well as the intended validation tools.
- Why it blocks / does not: The project profile does not enforce the mission's restriction to specific helper and validation operations.
- Requested correction: Replace the directory-wide Python allowances with the specific supported scripts or declared gates and their necessary arguments.
- Requested evidence: Inspect the composed project profile and demonstrate that the required validation is permitted while an unrelated script under tools is outside the allowance.

**R2-F6** · P1 · defect · blocks readiness — A transient resume failure can bypass handoff reconciliation on the next attempt
- Location: `agent_review/agent_review.py:2143`; acceptance: WF04, WF07
- Trigger: The first resume of a completed handoff encounters an operational error during verify_inputs, and the owner retries.
- Expected: A persisted handoff is reconciled on recovery even if an operational stop temporarily changed its status label.
- Actual: A transient pre-mutation failure during resume is recorded by guarded as PAUSED while phase remains done. The next resume skips handoff_superseded because status is no longer AWAITING_OWNER_REVIEW, sets ACTIVE, and the headless done branch returns AWAITING_OWNER_REVIEW without checking the handoff. Foreground mode instead returns ACTIVE with no valid next review phase.
- Why it blocks / does not: The documented recovery path can report readiness for a moved head or strand a completed foreground enrollment.
- Requested correction: Use the persisted handoff and phase to identify completed enrollments during recovery. Verify or reopen the handoff before returning readiness and keep phase and status consistent across transient errors.
- Requested evidence: Complete a handoff, cause a transient GitHub failure on guarded resume, move the head, then resume again in both modes. Verify that the old handoff is reopened and no stale readiness is returned.

#### Prior finding assessments

- **R1-F1** — `fix_rejected` — The single-part round-verdict tests cover queued and already-visible reviews. An interrupted final receipt still has no corresponding stale-receipt recovery path.
- **R1-F2** — `fix_rejected` — The suite confirms that a readable newer failure supersedes a pass and a changed log fails verification. An unreadable newer receipt disappears from selection, and intermediate acceptance omits the final gate check.
- **R1-F3** — `fix_rejected` — The recorded test covers a writer already holding its lock. Writers starting after the installer's probe never acquire the install lock.
- **R1-F4** — `fix_rejected` — A recorded developer PID, runtime lock and failed cancellation post are handled. Independently running foreground helpers are absent from the cancellation interlock.
- **R1-F5** — `fix_rejected` — Status, phase, worktree, remote and version checks are present and exercised. They inspect the selected enrollment without binding the calling developer to it.
- **R1-F6** — `fix_rejected` — Missing model and effort lists now fail. The production parsers can still aggregate an earlier completion or permitted sandbox setting into an incomplete or contradictory invocation.
- **R1-F7** — `fix_rejected` — Duplicate JSON keys, missing inspected lists and several blank scalar fields are rejected. Empty prior-assessment rationales and whitespace-only inspected entries still satisfy a pass.
- **R1-F8** — `fix_verified` — send keeps the tentative POST separate from authenticated reconciliation. The recorded anonymous-POST and transient-read fixture finishes with one confirmed comment.
- **R1-F9** — `fix_verified` — Both newly created and recovered archive commits pass through exact parent, path inventory, mode and digest checks before push. The gate includes incomplete-inventory rejection and real post-commit recovery.
- **R1-F10** — `fix_verified` — The initial archive resolves and validates destinations before writing. Recovery checks each destination before using it. The gate exercised the PR path pattern and linked-directory rejection.
- **R1-F11** — `fix_rejected` — Activation recomposes permissions and clears local ready state. It leaves the old public handoff current-looking and an invalidated pending verdict can obstruct the replacement handoff.
- **R1-F12** — `fix_verified` — make_historical persists the historical or correction message before clearing the active round. The recorded outage case settles the preserved correction on restart.
- **R1-F13** — `fix_verified` — The updated code validates marker ordering and count before editing and verifies the generated section after the edit and during remote status. The recorded tests cover malformed markers and removal of the section.
- **R1-F14** — `fix_rejected` — The request and retry envelope retain their original B. The final ready record and receipt still substitute the later observed target tip for the reviewed B.
- **R1-F15** — `fix_rejected` — The last allowed changes_required now atomically records BLOCKED with pending findings. Resume without an adequate extension immediately reopens the development phase.
- **R1-F16** — `fix_rejected` — The new test calls review_round directly. The public resume path empties the attempt list before that method can inspect the live PID.
- **R1-F17** — `fix_rejected` — The recorded intermediate-blob test passes. The actual push still names mutable HEAD, and the outgoing scan skips commit messages.
- **R1-F18** — `fix_rejected` — A bare search term no longer triggers the check. The full call spelling inside a quoted source search still matches the raw-input regular expression.
- **R1-F19** — `fix_rejected` — Re-enrollment with a freshly populated host ledger works. Existing pre-upgrade inventories are not migrated, and missing files are dropped during import.
- **R1-F20** — `fix_rejected` — The real pre-commit and post-commit subprocess tests ran successfully. Three older archive cases continue to override complete_archive, contrary to the checkpoint's test contract.

#### Evidence assessment

- **Inspected:** Fixed request, mission and owner addenda, repository instructions, operating guide, protocol, feature diff, controller, schemas, prompts, permission profiles, plans and behavior tests.; All 20 pending ledger entries and developer dispositions, candidate-bound gate receipt and log, and the foreground transcript notice.
- **Executed verification:** Confirmed the controller's unit receipt for H, exit code 0, unchanged worktree, and matching log SHA-256 130cae38dd7328018eb21ca7808729eaf06b48615c13445e6e72935f6c6e70a2. The log records 96 tests in 192.727 seconds, with 95 passing and the opt-in live smoke skipped.; The recorded suite exercised real temporary Git repositories, archive commits, OS locks, process termination at pre-commit and post-commit hooks, and WF12 checkpoint advancement with simulated model and GitHub responses.; Read-only Git inspection confirmed the detached HEAD. The copied mission's SHA-256 matches the requested mission identity.
- **Source inspection only:** Traced command dispatch through state reload, attempt reconciliation, publication, archive, finalization and handoff recovery.; Inspected the real model/GitHub adapters, installation interlock, helper authority, guarded push and project permission settings. The unit suite simulates the external services.
- **Required gaps:** Candidate-bound behavior evidence for the public resume, activation, cancellation and handoff paths identified below, including interruption during multipart publication.; Fail-closed evidence for ambiguous reviewer output, damaged gate receipts, and preservation of earlier transcript records across upgrade and re-enrollment.; A behavior suite whose archive crash cases all respect the stipulated model/GitHub-only stubbing boundary.
- **Limitations:** The foreground transcript withholds the whole-session log. The separately claimed 68-second live smoke has no candidate-bound execution record in these inputs. It is not counted as executed verification here.; The reviewer performed read-only inspection. The failure paths below are source findings unless the finding explicitly cites recorded test behavior.; The supplied prior ledger contains titles and dispositions but omits the original detailed findings. This limits comparison with the original triggers and requested evidence.

#### Summary

- **Delivered behavior:** The controller captures detached candidates, requests the selected models, validates structured reviews, records candidate-bound gate evidence, advances intermediate checkpoints, and verifies exact archive commits. The recorded suite demonstrates those paths and several real crash-recovery cases.
- **Scope reviewed:** Controller-core for draft PR #1 at 78868323c00e54e9eb2845faafa7f729619519c6, including all 20 pending dispositions and WF04–WF10/WF12 behavior evidence.
- **Pending later-phase work:** At setup-final, complete the operating documentation, effective permission and installation evidence, Black Tentacles binding and start command, and the setup acceptance report for the real pilot.
- **Unresolved questions:** none
- **Remaining owner review:** Final acceptance of the completed workflow and any later merge or release decision remain with the owner.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `high` | `high` (turns ['high']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Codex CLI `0.170.0`, thread `01a1fb9a-472a-7f50-9a43-dba43e73e8db`, duration 351.0s, response sha256 `79d73307a01a29525b5d2382f1de65cda551d5b51f6517169ec5dca57f79eeb4`, request `devproc-claude-agent-review-controller-20261120192057-9024-r02-34d555`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "78868323c00e54e9eb2845faafa7f729619519c6",
  "checkpoint_id": "controller-core",
  "checkpoint_type": "intermediate",
  "decision": "changes_required",
  "decision_rationale": "The candidate-bound unit gate passed, and the archive commit checks are materially stronger. Controller-core still has paths that accept an empty prior-finding assessment, launch a second reviewer during recovery, or leave an obsolete owner handoff visible. Several regressions exercise an internal method while the documented command takes a different path. These issues affect WF04\u2013WF10 and must be resolved before advancing.",
  "evidence_assessment": {
    "executed_verification": [
      "Confirmed the controller's unit receipt for H, exit code 0, unchanged worktree, and matching log SHA-256 130cae38dd7328018eb21ca7808729eaf06b48615c13445e6e72935f6c6e70a2. The log records 96 tests in 192.727 seconds, with 95 passing and the opt-in live smoke skipped.",
      "The recorded suite exercised real temporary Git repositories, archive commits, OS locks, process termination at pre-commit and post-commit hooks, and WF12 checkpoint advancement with simulated model and GitHub responses.",
      "Read-only Git inspection confirmed the detached HEAD. The copied mission's SHA-256 matches the requested mission identity."
    ],
    "inspected": [
      "Fixed request, mission and owner addenda, repository instructions, operating guide, protocol, feature diff, controller, schemas, prompts, permission profiles, plans and behavior tests.",
      "All 20 pending ledger entries and developer dispositions, candidate-bound gate receipt and log, and the foreground transcript notice."
    ],
    "limitations": [
      "The foreground transcript withholds the whole-session log. The separately claimed 68-second live smoke has no candidate-bound execution record in these inputs. It is not counted as executed verification here.",
      "The reviewer performed read-only inspection. The failure paths below are source findings unless the finding explicitly cites recorded test behavior.",
      "The supplied prior ledger contains titles and dispositions but omits the original detailed findings. This limits comparison with the original triggers and requested evidence."
    ],
    "required_gaps": [
      "Candidate-bound behavior evidence for the public resume, activation, cancellation and handoff paths identified below, including interruption during multipart publication.",
      "Fail-closed evidence for ambiguous reviewer output, damaged gate receipts, and preservation of earlier transcript records across upgrade and re-enrollment.",
      "A behavior suite whose archive crash cases all respect the stipulated model/GitHub-only stubbing boundary."
    ],
    "source_inspection_only": [
      "Traced command dispatch through state reload, attempt reconciliation, publication, archive, finalization and handoff recovery.",
      "Inspected the real model/GitHub adapters, installation interlock, helper authority, guarded push and project permission settings. The unit suite simulates the external services."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "WF04",
        "WF06"
      ],
      "actual": "On restart, finalize can invalidate the result or stop at its first readiness check without reconciling the already-visible final-status comment. The owner can still see an uncorrected 'awaiting owner review' receipt. Also, the generic outbox exclusion recognizes only two-digit round verdicts, although round numbers can exceed 99.",
      "blocking_rationale": "The PR is the owner's handoff surface. A local stop alone leaves a stale public verdict.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A visible obsolete verdict receives a correction, and an unsent obsolete verdict stays unsent, for both review and final-handoff messages.",
      "id": "R1-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2418
      },
      "priority": "P1",
      "requested_correction": "Reconcile any pending or visible final receipt when abandoning its handoff. Persist the correction before leaving finalization. Identify verdict records independently of a two-digit round width.",
      "requested_evidence": "Interrupt after the simulated GitHub service stores the final receipt, move the head, then resume. Assert a visible correction, no current handoff, and no duplicate receipt. Cover a three-digit round key.",
      "title": "An interrupted final handoff can leave stale readiness visible",
      "trigger": "GitHub stores the final receipt, the controller exits before recording the handoff, and the reviewed conditions change before resume."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF08",
        "WF12"
      ],
      "actual": "gate_receipts silently skips unreadable JSON, allowing an older pass to become authoritative again. finish_round also accepts an intermediate pass without rechecking required gates after the report was accepted.",
      "blocking_rationale": "An intermediate checkpoint can advance with obsolete or unverifiable required evidence.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The latest required run must be identifiable and verifiable when the checkpoint advances.",
      "id": "R1-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1876
      },
      "priority": "P1",
      "requested_correction": "Fail closed on a damaged receipt belonging to the candidate and gate. Recheck the required gate set before accepting a passing round, including a preserved result on resume.",
      "requested_evidence": "Record a pass followed by a failure, truncate the newer receipt, and verify the older pass is unusable. Invalidate a required log between review validation and intermediate acceptance and assert the checkpoint index stays fixed.",
      "title": "Damaged or superseded gate evidence can still advance a checkpoint",
      "trigger": "A newer receipt becomes unreadable, or required evidence changes after report acceptance and before a preserved intermediate verdict is accepted."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "install probes each currently known writer lock and releases it immediately. writer_lock never participates in install.lock. A controller can start after the probe and overlap the directory swap. The two renames also leave a window with no installation at the configured path.",
      "blocking_rationale": "An installation can change under a live invocation, including a developer about to call the installed helper.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Starting a controller and replacing its installation must be mutually exclusive across the handoff between versions.",
      "id": "R1-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2918
      },
      "priority": "P1",
      "requested_correction": "Use a shared installation/startup interlock or immutable versioned installations with a recoverable activation switch. Cover writers that start while installation is already in progress.",
      "requested_evidence": "Use separate processes to start a controller after the installer's initial lock check. Verify a single complete version is used and interrupt the installer at the switch to verify recovery.",
      "title": "The install lock excludes other installers but cannot exclude a new controller",
      "trigger": "A controller starts while install is staging a replacement after checking existing writer locks."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "cancel checks the recorded headless developer and configured runtime lock files. A foreground verify or push helper holds no corresponding enrollment operation lock and has no recorded PID. Cancellation can therefore release the claims while that helper is still executing.",
      "blocking_rationale": "A replacement enrollment can acquire the same worktree while a previously authorized operation is still using it.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Ownership is released only after in-flight developer operations reach a safe boundary.",
      "id": "R1-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2065
      },
      "priority": "P1",
      "requested_correction": "Coordinate helper lifetimes with cancellation and re-enrollment while retaining the ability for the owning headless developer to invoke helpers.",
      "requested_evidence": "Hold a real foreground gate process open, request cancellation from another process, and verify that a replacement enrollment cannot take ownership until the helper exits.",
      "title": "Cancellation can release the worktree under a running foreground helper",
      "trigger": "The owner cancels while a foreground validation or push helper is running and no configured runtime lock exists."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "helper_authority_problems inspects the target worktree through self.git and the shared GitHub login. It never checks the caller against foreground_session. Two active foreground sessions using the same account can operate on one another's enrollments by ID.",
      "blocking_rationale": "The globally permitted foreground helper can dispatch another enrollment's validation or publish its branch.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The developer helper must establish that the caller owns development authority for the chosen enrollment.",
      "id": "R1-F5",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2042
      },
      "priority": "P1",
      "requested_correction": "Bind foreground helper calls to the enrolled developer session, as foreground reports already are. Establish equivalent invocation ownership for headless helpers.",
      "requested_evidence": "Use two enrolled sessions under the same actor. Show each can invoke its own helper and that a cross-enrollment call performs no gate or push.",
      "title": "Helper checks authenticate the target but omit the calling developer",
      "trigger": "A helper is invoked with the ID of a different active enrollment belonging to the same GitHub account."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF10"
      ],
      "actual": "CodexReviewer.run sets completed when it sees any turn.completed and ignores malformed event lines. A later unfinished turn does not clear that flag. Provenance likewise retains the last nonempty sandbox value across turn contexts, and invocation_problems ignores the observed network setting.",
      "blocking_rationale": "A final message can pass validation with an incomplete terminal stream or contradictory execution-profile evidence.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The completed result, terminal event, thread and permitted reviewer profile must agree for the invocation being accepted.",
      "id": "R1-F6",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 585
      },
      "priority": "P1",
      "requested_correction": "Validate the terminal state of the actual event sequence. Reject incomplete or contradictory turn/profile observations, including an explicitly wider network profile.",
      "requested_evidence": "Feed the real event and rollout parsers labeled fixtures with a completed turn followed by an unfinished turn, malformed trailing output, and contradictory sandbox/network observations. Assert that none can advance the round.",
      "title": "An earlier completion can satisfy an unfinished reviewer invocation",
      "trigger": "A zero-exit invocation supplies structured output and an earlier completion event, followed by an incomplete turn or conflicting profile metadata."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF08"
      ],
      "actual": "A passing review with inspected set to a single whitespace string passes the list-presence check. A fix_verified assessment can have an empty rationale and still close a blocking finding. Several required finding explanations are also allowed to be blank.",
      "blocking_rationale": "A blocking issue can be closed without the required reviewer assessment, and an empty evidence statement can satisfy the pass guard.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Passing decisions must identify actual inspected evidence, and each accepted prior disposition must carry a nonblank rationale.",
      "id": "R1-F7",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1589
      },
      "priority": "P1",
      "requested_correction": "Validate nonblank evidence entries, prior-assessment rationales and required finding explanations before applying ledger transitions.",
      "requested_evidence": "Submit a schema-valid final pass containing whitespace-only inspected evidence and a separate pass closing a blocker with an empty rationale. Both must leave the ledger and readiness unchanged.",
      "title": "Blank evidence and blank fix assessments can still produce readiness",
      "trigger": "The reviewer supplies correctly typed strings that contain no substantive text."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF07"
      ],
      "actual": "activate clears a validated round without resolving its pending review publication. settle_publications always skips that verdict, while missing_publications still requires it, permanently obstructing a later handoff. In the completed-handoff case activation changes local state but leaves the old PR status section and receipt declaring readiness.",
      "blocking_rationale": "An upgrade can strand a required publication or leave owners relying on a handoff the controller has invalidated.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Invalidating an old-version result reconciles its public and pending records as part of the same recoverable transition.",
      "id": "R1-F11",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2119
      },
      "priority": "P1",
      "requested_correction": "Retire or correct the old round's outbox record according to what is already visible. Persist and publish the supersession of an existing owner handoff, including its PR description.",
      "requested_evidence": "Activate during a verdict publication outage, then complete a fresh review and finalize. Separately activate after a completed handoff and verify that both the description and comments identify it as superseded.",
      "title": "Workflow activation leaves old verdict publications unresolved",
      "trigger": "A reviewed workflow is activated while a verdict is pending publication or after an owner handoff has been posted."
    },
    {
      "acceptance_ids": [
        "WF04"
      ],
      "actual": "The retried request and envelope now retain B, but ready_review stores B_at_acceptance in the B field. finalize then labels that later value 'target at review B'. The final receipt can therefore identify a different tuple from the published request and accepted envelope.",
      "blocking_rationale": "The owner cannot use the handoff tuple to identify the comparison actually requested without reconstructing it from earlier records.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The captured H/B/M remains immutable through the final receipt. Subsequent target observations are recorded separately.",
      "id": "R1-F14",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1698
      },
      "priority": "P2",
      "requested_correction": "Keep rnd.B as the reviewed B in ready_review and the handoff. Carry the reconciled target tip and observation time in separate fields.",
      "requested_evidence": "Move the target without changing M during a final round. Assert that the request, envelope, ready result and final receipt show the same original B and separately report the new target tip.",
      "title": "The final receipt can replace the captured target tip",
      "trigger": "The target advances without changing the merge base before a final review is accepted."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF08"
      ],
      "actual": "The last permitted changes_required now saves BLOCKED immediately. A subsequent resume without a larger limit sets ACTIVE in phase develop and can launch another headless developer or enable foreground helpers. The cap blocks only when that new work reaches review.",
      "blocking_rationale": "An exhausted checkpoint can consume another development invocation and change the branch without any remaining review round.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "An exhausted checkpoint stays stopped until an owner supplies a sufficient round extension.",
      "id": "R1-F15",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2154
      },
      "priority": "P2",
      "requested_correction": "Check the persisted count against the effective limit before reactivating development after a cap stop.",
      "requested_evidence": "At a one-round cap, resume with no extension and with an unchanged limit. Assert zero additional developer launches and disabled helpers, then demonstrate continuation with a larger limit.",
      "title": "Resume reopens development even when the round budget is still exhausted",
      "trigger": "The owner resumes a cap-stopped enrollment without increasing the limit above the completed count."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF07"
      ],
      "actual": "resume moves the active attempts to earlier_attempts and resets attempts before review_round calls reconcile_reviewer_attempt. The live PID is therefore invisible to reconciliation. There is also no lookup for a reviewer launched immediately before its PID was saved.",
      "blocking_rationale": "The documented host-recovery command can launch a duplicate paid reviewer and leave its predecessor's snapshot behind.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Recovery settles an interrupted invocation before resetting any retry budget, removing its snapshot, or launching another reviewer.",
      "id": "R1-F16",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2153
      },
      "priority": "P1",
      "requested_correction": "Reconcile unfinished attempts before resetting, superseding or replacing their round. Make the launch-to-PID-record interval recoverable.",
      "requested_evidence": "Exercise resume with a live reviewer subprocess, then after it exits. Assert one launch while live, cleanup after exit, and monotonic attempt IDs. Include interruption before PID persistence.",
      "title": "The documented resume path clears the reviewer attempt it must reconcile",
      "trigger": "The controller exits during review and the owner uses resume while the original reviewer is still running."
    },
    {
      "acceptance_ids": [
        "WF10"
      ],
      "actual": "The helper scans the captured head but pushes symbolic HEAD. If HEAD changes during the scan, a different commit is transferred before the post-push mismatch is reported. The scan also skips commit objects entirely, including commit messages containing a recognized credential pattern.",
      "blocking_rationale": "The guarded route can publish uninspected content. Detecting the mismatch after the remote write cannot retract it.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Only the inspected commit may be published, and the credential check covers newly published history containing user-authored text.",
      "id": "R1-F17",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2672
      },
      "priority": "P1",
      "requested_correction": "Push the verified object ID in the explicit refspec, recheck relevant authority before dispatch, and cover outgoing commit metadata in the credential check.",
      "requested_evidence": "Advance local HEAD between inspection and push against a bare origin and verify the newer object is never published. Include a harmless synthetic credential marker in a commit message.",
      "title": "The guarded push can publish a different object from the one it scanned",
      "trigger": "Local HEAD advances during a long outgoing-history scan, or a credential appears in commit text rather than a file."
    },
    {
      "acceptance_ids": [
        "WF05"
      ],
      "actual": "The code-mode branch searches the entire custom tool input with a regular expression. A quoted search for the literal delegation call syntax matches just as an executed call would.",
      "blocking_rationale": "An ordinary read-only review of this controller can exhaust its retries solely because of the source text it searches.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Delegation detection follows actual tool dispatch. Source literals, strings and comments do not invalidate a review.",
      "id": "R1-F18",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 628
      },
      "priority": "P2",
      "requested_correction": "Use structured dispatch evidence for delegation, or otherwise distinguish executed operations from literals in code-mode input.",
      "requested_evidence": "Pass rollout fixtures for a quoted exact call-signature search and an actual delegation dispatch through provenance. Only the dispatch should invalidate the invocation.",
      "title": "A literal source search can still be classified as delegation",
      "trigger": "A code-mode shell search includes the full spelling and opening parenthesis of a delegation call."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF09"
      ],
      "actual": "Only new archives populate the new host ledger. Existing authenticated archived maps are never migrated on activation. On re-enrollment, entries missing from HEAD are also silently filtered out, so a record added after M and later deleted can disappear from both inventories.",
      "blocking_rationale": "Genuine pre-upgrade records can block continuation, while deletion of a known record can escape the append-only check.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Re-enrollment preserves the authenticated inventory of the PR, including existing enrollments, and detects missing or altered records.",
      "id": "R1-F19",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2843
      },
      "priority": "P1",
      "requested_correction": "Migrate authenticated records from earlier enrollment state and verify the complete applicable inventory against the branch. Treat missing expected records as an integrity failure.",
      "requested_evidence": "Re-enroll from pre-upgrade state with genuine archived records and no host ledger. Then delete one known post-base record before re-enrollment and verify the missing path is reported.",
      "title": "The new record ledger loses pre-upgrade or missing records",
      "trigger": "A PR already contains records from before the host ledger existed, or a recorded file is removed before re-enrollment."
    },
    {
      "acceptance_ids": [
        "WF09"
      ],
      "actual": "The new subprocess crash tests ran, but three existing cases still subclass Controller and replace complete_archive, at lines 508, 1267 and 1602. The partial-commit rejection case still relies on that internal replacement.",
      "blocking_rationale": "The checkpoint expressly limits stubs to model and GitHub boundaries.",
      "blocks_readiness": true,
      "category": "required_gap",
      "expected": "All archive recovery cases use real controller operations, state and Git commits.",
      "id": "R1-F20",
      "location": {
        "file": "agent_review/test_agent_review.py",
        "line": 508
      },
      "priority": "P2",
      "requested_correction": "Remove redundant internally stubbed cases and port any distinct assertions, particularly partial-commit rejection, to the real crash fixture.",
      "requested_evidence": "Run the candidate-bound unit gate with real interruption, exact adoption and partial-commit rejection covered without a Controller override.",
      "title": "Three archive tests still replace an internal controller operation",
      "trigger": "The unit gate runs the older archive recovery tests alongside the new subprocess tests."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF09"
      ],
      "actual": "already_visible returns true when any part exists. make_historical then marks the entire normal verdict posted a

---

<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r02-review part=2/2 sha256=029b76f11eb88410637ddb56cae095e13fda8124a6f029fce7d08167d6b742da -->
_Part 2 of 2._

nd sends only a correction. Unsent parts retain null comment IDs, causing missing_publications to fail indefinitely and the public review to remain incomplete.",
      "blocking_rationale": "One interrupted long review can prevent every later handoff for the enrollment.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every visible part is reconciled and the complete historical review remains available. A partially delivered message must have a recoverable disposition.",
      "id": "R2-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1713
      },
      "priority": "P1",
      "requested_correction": "Track partial publication explicitly. Correct the visible parts and publish the complete historical result under an appropriate marker without requiring nonexistent comment IDs.",
      "requested_evidence": "Interrupt a two-part verdict after part one, move H, resume, and complete a subsequent valid handoff. Verify the full historical result is available and every required publication reconciles.",
      "title": "One visible chunk marks an entire stale review as posted",
      "trigger": "Only part of a split verdict reaches GitHub before interruption and the candidate changes before recovery."
    },
    {
      "acceptance_ids": [
        "WF08",
        "WF12"
      ],
      "actual": "finish_round retains only a finding's title, classification and counters in the ledger. The next reviewer's inbox omits the original trigger, expected and actual behavior, location, acceptance IDs, requested correction and requested evidence. This round's inbox demonstrates the omission.",
      "blocking_rationale": "An independent reviewer cannot reliably assess a proposed fix against the original finding, especially when the developer interprets it differently.",
      "blocks_readiness": true,
      "category": "required_gap",
      "expected": "Each pending assessment has the original accepted finding and the developer's response available in the fixed review inputs.",
      "id": "R2-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1665
      },
      "priority": "P1",
      "requested_correction": "Include the full authenticated prior finding in the next inbox, with its originating round. Recover it from retained envelopes for existing enrollments.",
      "requested_evidence": "In a two-round fixture, verify that the second reviewer can read the exact trigger and requested evidence of the first review alongside the disposition.",
      "title": "The reviewer receives a finding title where it needs the original finding",
      "trigger": "A later round must verify or reject a developer disposition using the read-only snapshot."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "install recursively deletes a predictably named sibling staging directory. It also retires and recursively deletes any existing destination, including a non-install directory or unrelated files within an installation. The previous manifest is never used to establish ownership of what will be removed.",
      "blocking_rationale": "A routine setup command can irreversibly delete unrelated workspace or owner data.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Installation modifies only a validated controller installation and its own newly allocated staging area.",
      "id": "R2-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2923
      },
      "priority": "P1",
      "requested_correction": "Allocate unique staging storage and verify ownership of an existing destination before replacement. Preserve unrelated files or refuse the operation before mutation.",
      "requested_evidence": "Use temporary directories containing unrelated sentinel files at the destination and conventional staging name. A refused installation must leave both intact, and a genuine upgrade must still succeed.",
      "title": "Installation can delete directories it does not own",
      "trigger": "The requested destination or its .staging sibling already contains unrelated files."
    },
    {
      "acceptance_ids": [
        "WF10"
      ],
      "actual": "The explicit branch refspec does not disable Git's push.followTags setting. With that setting enabled, a guarded branch push can also publish a reachable annotated tag. The post-push check inspects only the branch.",
      "blocking_rationale": "The owner authorized writes to one enrolled branch and retained control of tagging.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The built-in push transfers only the authorized branch ref regardless of ambient tag-following preferences.",
      "id": "R2-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2672
      },
      "priority": "P1",
      "requested_correction": "Explicitly disable following tags for this fixed push operation.",
      "requested_evidence": "Enable push.followTags in a temporary repository with a reachable local annotated tag. Verify the enrolled branch advances and the bare origin receives no tag.",
      "title": "Ambient Git configuration can expand a branch push to tags",
      "trigger": "The owner has enabled push.followTags and the outgoing history has a local annotated tag absent from origin."
    },
    {
      "acceptance_ids": [
        "WF10"
      ],
      "actual": "The Dice Roller project allows Python execution for every path under tools in both shells. That directory is writable by the developer, so the permission set includes future, unreviewed scripts as well as the intended validation tools.",
      "blocking_rationale": "The project profile does not enforce the mission's restriction to specific helper and validation operations.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Project permissions name the actual validation entry points authorized for that repository.",
      "id": "R2-F5",
      "location": {
        "file": "agent_review/projects/kingmaker-dice-roller.json",
        "line": 34
      },
      "priority": "P1",
      "requested_correction": "Replace the directory-wide Python allowances with the specific supported scripts or declared gates and their necessary arguments.",
      "requested_evidence": "Inspect the composed project profile and demonstrate that the required validation is permitted while an unrelated script under tools is outside the allowance.",
      "title": "One shipped developer profile permits an entire directory of scripts",
      "trigger": "A headless enrollment uses the Kingmaker Dice Roller project profile."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF07"
      ],
      "actual": "A transient pre-mutation failure during resume is recorded by guarded as PAUSED while phase remains done. The next resume skips handoff_superseded because status is no longer AWAITING_OWNER_REVIEW, sets ACTIVE, and the headless done branch returns AWAITING_OWNER_REVIEW without checking the handoff. Foreground mode instead returns ACTIVE with no valid next review phase.",
      "blocking_rationale": "The documented recovery path can report readiness for a moved head or strand a completed foreground enrollment.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A persisted handoff is reconciled on recovery even if an operational stop temporarily changed its status label.",
      "id": "R2-F6",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2143
      },
      "priority": "P1",
      "requested_correction": "Use the persisted handoff and phase to identify completed enrollments during recovery. Verify or reopen the handoff before returning readiness and keep phase and status consistent across transient errors.",
      "requested_evidence": "Complete a handoff, cause a transient GitHub failure on guarded resume, move the head, then resume again in both modes. Verify that the old handoff is reopened and no stale readiness is returned.",
      "title": "A transient resume failure can bypass handoff reconciliation on the next attempt",
      "trigger": "The first resume of a completed handoff encounters an operational error during verify_inputs, and the owner retries."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F1",
      "rationale": "The single-part round-verdict tests cover queued and already-visible reviews. An interrupted final receipt still has no corresponding stale-receipt recovery path."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F2",
      "rationale": "The suite confirms that a readable newer failure supersedes a pass and a changed log fails verification. An unreadable newer receipt disappears from selection, and intermediate acceptance omits the final gate check."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F3",
      "rationale": "The recorded test covers a writer already holding its lock. Writers starting after the installer's probe never acquire the install lock."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F4",
      "rationale": "A recorded developer PID, runtime lock and failed cancellation post are handled. Independently running foreground helpers are absent from the cancellation interlock."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F5",
      "rationale": "Status, phase, worktree, remote and version checks are present and exercised. They inspect the selected enrollment without binding the calling developer to it."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F6",
      "rationale": "Missing model and effort lists now fail. The production parsers can still aggregate an earlier completion or permitted sandbox setting into an incomplete or contradictory invocation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F7",
      "rationale": "Duplicate JSON keys, missing inspected lists and several blank scalar fields are rejected. Empty prior-assessment rationales and whitespace-only inspected entries still satisfy a pass."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F8",
      "rationale": "send keeps the tentative POST separate from authenticated reconciliation. The recorded anonymous-POST and transient-read fixture finishes with one confirmed comment."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F9",
      "rationale": "Both newly created and recovered archive commits pass through exact parent, path inventory, mode and digest checks before push. The gate includes incomplete-inventory rejection and real post-commit recovery."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F10",
      "rationale": "The initial archive resolves and validates destinations before writing. Recovery checks each destination before using it. The gate exercised the PR path pattern and linked-directory rejection."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F11",
      "rationale": "Activation recomposes permissions and clears local ready state. It leaves the old public handoff current-looking and an invalidated pending verdict can obstruct the replacement handoff."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F12",
      "rationale": "make_historical persists the historical or correction message before clearing the active round. The recorded outage case settles the preserved correction on restart."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F13",
      "rationale": "The updated code validates marker ordering and count before editing and verifies the generated section after the edit and during remote status. The recorded tests cover malformed markers and removal of the section."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F14",
      "rationale": "The request and retry envelope retain their original B. The final ready record and receipt still substitute the later observed target tip for the reviewed B."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F15",
      "rationale": "The last allowed changes_required now atomically records BLOCKED with pending findings. Resume without an adequate extension immediately reopens the development phase."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F16",
      "rationale": "The new test calls review_round directly. The public resume path empties the attempt list before that method can inspect the live PID."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F17",
      "rationale": "The recorded intermediate-blob test passes. The actual push still names mutable HEAD, and the outgoing scan skips commit messages."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F18",
      "rationale": "A bare search term no longer triggers the check. The full call spelling inside a quoted source search still matches the raw-input regular expression."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F19",
      "rationale": "Re-enrollment with a freshly populated host ledger works. Existing pre-upgrade inventories are not migrated, and missing files are dropped during import."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F20",
      "rationale": "The real pre-commit and post-commit subprocess tests ran successfully. Three older archive cases continue to override complete_archive, contrary to the checkpoint's test contract."
    }
  ],
  "request_id": "devproc-claude-agent-review-controller-20261120192057-9024-r02-34d555",
  "round": 2,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "The controller captures detached candidates, requests the selected models, validates structured reviews, records candidate-bound gate evidence, advances intermediate checkpoints, and verifies exact archive commits. The recorded suite demonstrates those paths and several real crash-recovery cases.",
    "pending_later_phase_work": [
      "At setup-final, complete the operating documentation, effective permission and installation evidence, Black Tentacles binding and start command, and the setup acceptance report for the real pilot."
    ],
    "remaining_owner_review": [
      "Final acceptance of the completed workflow and any later merge or release decision remain with the owner."
    ],
    "scope_reviewed": "Controller-core for draft PR #1 at 78868323c00e54e9eb2845faafa7f729619519c6, including all 20 pending dispositions and WF04\u2013WF10/WF12 behavior evidence.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
