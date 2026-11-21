<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r07-review part=1/1 sha256=1ac9ba3793f6ea8e305d52477358adadb68961b6c98aa9a4dc4b93364e788a53 -->
### Codex GPT-6.2 Astra — review — round 7 — candidate `7c963672b1`

**Decision:** `changes_required` — The candidate-bound runs establish that the enrolled developer can push and verify under the production permission profile. Controller-core still has paths that accept obsolete gate evidence, adopt altered permissions, or advance after a verdict was retired. Several recovery tests stop before the state transition where the defect occurs.

#### Findings

**R5-F1** · P1 · defect · blocks readiness — Permission rebinding trusts the contents of an existing destination
- Location: `agent_review/agent_review.py:2336`; acceptance: WF07, WF10
- Trigger: Recovery or reactivation selects a previously created content-addressed settings file.
- Expected: The selected file must match the full digest of the freshly composed permission settings.
- Actual: bind_developer_settings skips writing when the destination exists and pins sha256_file(path). If an inactive or staged settings file changed, that operation adopts its altered contents. Subsequent verification compares against the newly adopted digest and succeeds.
- Why it blocks / does not: A resumed developer can receive permissions different from the reviewed composition.
- Requested correction: Compute the expected digest from the composed bytes, verify any existing destination against it before selection, and persist that expected digest.
- Requested evidence: Stage a binding, leave the old binding selected, alter the staged file, then resume relocation. Show that the altered bytes cannot become the active permissions.

**R7-F1** · P1 · defect · blocks readiness — Activation can persist a new workflow with the previous permissions
- Location: `agent_review/agent_review.py:2435`; acceptance: WF07, WF10
- Trigger: A workflow or project change invalidates a validated round during activation.
- Expected: The activated workflow, project and selected permission file become current together.
- Actual: activate updates the in-memory workflow and project, then calls retire_verdict before bind_developer_settings. Retirement saves state. A process exit after that save leaves the new workflow fingerprint and root paired with the previous permission binding. verify_inputs accepts that old file because it still matches its old digest and the package root already matches.
- Why it blocks / does not: A reviewed permission restriction can be lost across an activation restart.
- Requested correction: Stage the new permission file before any save can expose the new workflow. Commit the binding and invalidation together, or persist an activation intent that must complete before reuse.
- Requested evidence: Activate a stricter permission base with a validated round present. Interrupt after verdict retirement, reload, and demonstrate that the old permissions cannot be used under the new fingerprint.

**R1-F6** · P1 · defect · blocks readiness — Malformed rollout values still escape attempt validation
- Location: `agent_review/agent_review.py:677`; acceptance: WF05, WF08
- Trigger: A selected rollout contains an object payload with malformed fields inside it.
- Expected: Malformed records used to establish model, settings or tool dispatch produce a recorded rejected attempt.
- Actual: The parser checks several enclosing objects but passes their leaf values directly to set and sorted. A nonempty object or list in turn_context.model or approval_policy raises TypeError before validate_review records an attempt outcome. Also, a response_item with an empty object payload has no discriminator and is silently ignored even in an otherwise valid rollout.
- Why it blocks / does not: Malformed provenance can escape bounded attempt handling, and an unidentifiable response item can accompany an accepted review.
- Requested correction: Validate the scalar types and required discriminators of consumed records before collecting observations. Route structural errors through invocation_problems.
- Requested evidence: Supply otherwise valid rollouts with a structured model or approval value and with an untyped response item. Exercise review dispatch and verify recorded rejection, bounded retries and unchanged completed-round count.

**R5-F4** · P1 · defect · blocks readiness — Adjacent developer invocations can share one effort observation
- Location: `agent_review/agent_review.py:877`; acceptance: WF05, WF07
- Trigger: The controller immediately resumes Claude after a report needs correction.
- Expected: Each invocation establishes its own observed effort.
- Actual: ClaudeDeveloper.run subtracts one second from launch time and truncates the result to whole seconds. A preceding invocation's final high-effort record can fall inside that window. If the resumed invocation has no effort record, the scan can still yield high. The regression separates its records by an hour.
- Why it blocks / does not: A headless report can dispatch review without affirmative effort provenance for the invocation that produced it.
- Requested correction: Capture the transcript position or an invocation identifier before launch and read effort from records attributable to that invocation.
- Requested evidence: Run two immediately consecutive invocations in one fixture session. With high recorded only in the first, verify the second cannot dispatch. Add a current high observation and verify acceptance.

**R7-F2** · P1 · defect · blocks readiness — Narrowing a gate's allowed filters leaves excluded evidence current
- Location: `agent_review/agent_review.py:3080`; acceptance: WF04, WF08
- Trigger: Project refresh changes the argument policy while retaining the base command.
- Expected: Required evidence satisfies the currently declared gate and its argument restrictions.
- Actual: gate_definition_id hashes only base argv. receipt_problems checks that prefix but never revalidates the extra arguments. After a project refresh narrows extra_args_pattern, a passing receipt for a now-excluded filter still satisfies the required gate on H.
- Why it blocks / does not: A fresh review under the changed project can advance using evidence for a command the current gate would refuse to run.
- Requested correction: Include the argument policy in the gate-definition identity and validate receipt arguments against the active declaration.
- Requested evidence: Pass filter A, refresh the same base command to allow only B, and show that A no longer satisfies the checkpoint. Run B on the same H and verify recovery.

**R6-F3** · P2 · defect · blocks readiness — Readable pre-upgrade receipts permanently block a replacement gate
- Location: `agent_review/agent_review.py:2140`; acceptance: WF07, WF08
- Trigger: A running enrollment upgrades with an existing required-gate receipt for H.
- Expected: An upgrade preserves readable historical evidence and lets the replacement gate establish a pass on the same candidate.
- Actual: Every filename from the preceding controller version has definition=None. gate_status records it as permanent unknown damage, even when the receipt JSON, candidate, command, timestamp and log digest are intact. A passing run of the replacement gate on the same H cannot clear it.
- Why it blocks / does not: An enrolled branch with valid pre-upgrade evidence can remain blocked after running the requested replacement validation.
- Requested correction: Handle intact predecessor-format receipts separately from unreadable ones. Recover their attributable command and scope where possible, while retaining fail-closed handling for genuinely unknown damage.
- Requested evidence: Start with an intact receipt in the immediately preceding release's format, refresh the gate command, rerun on H, and show that the new evidence is accepted while the old record remains intact.

**R7-F3** · P1 · defect · blocks readiness — A required gate in progress is invisible to readiness checks
- Location: `agent_review/agent_review.py:2176`; acceptance: WF07, WF08, WF12
- Trigger: A foreground report overlaps a rerun of a previously passing gate.
- Expected: A newer pending or interrupted required run prevents reuse of the earlier pass for that scope.
- Actual: run_gate leaves no persistent run record until after the subprocess finishes. The verify helper holds helper.lock, while foreground report acceptance and review use the writer lock. A newer gate can therefore be running while each missing_gates check sees only an older pass. An interrupted helper can leave that older pass current indefinitely.
- Why it blocks / does not: An intermediate checkpoint can advance, or finalization can declare readiness, with required validation still pending.
- Requested correction: Persist the gate run identity and pending state before dispatch. Include pending runs in report, acceptance and readiness checks, with recovery through a completed valid rerun.
- Requested evidence: Pass a required gate, start a second run on the same H and hold it open. Submit a foreground report and verify it cannot advance. Interrupt the helper, reload state and verify that a completed rerun restores eligibility.

**R5-F2** · P1 · defect · blocks readiness — An interrupted handoff reopen can leave development active at the cap
- Location: `agent_review/agent_review.py:2988`; acceptance: WF07, WF08
- Trigger: The controller exits during public updates for a superseded last-round handoff.
- Expected: Reopening at the cap durably disables development until the owner extends the budget.
- Actual: reopen saves ACTIVE/develop before publishing the reopen notice and editing the PR body. resume checks the exhausted budget only after reopen returns. A process exit in between leaves helpers available. On restart the local reopened flag is false, so the ordinary exhausted-budget path raises UsageError and retains ACTIVE.
- Why it blocks / does not: Recovery can re-enable foreground push and verification at the exhausted cap without the owner's extension.
- Requested correction: Compute the effective budget before persisting the reopen transition. Save the cleared handoff and resulting blocked status together, and make its public updates resumable.
- Requested evidence: Interrupt the simulated GitHub boundary during reopen after the local transition. Reload, verify helper refusal and a recoverable visible budget stop, then extend the limit and resume.

**R6-F1** · P1 · defect · blocks readiness — Archiving a partial verdict can discard a later delivery
- Location: `agent_review/agent_review.py:2550`; acceptance: WF06, WF09
- Trigger: A superseded multipart verdict has a known first part and an uncertain later part.
- Expected: Every delivered verdict part is reconciled before the archive inventory is declared complete.
- Actual: The new archive scan reconciles an uncertain part once. If one part is known and another stored part is still absent from the listing, archive commits the partial inventory and marks the entire key archived. Later archive calls skip the key, and handoff checks skip superseded publications. A late-visible part never acquires its archived reference.
- Why it blocks / does not: The controller can certify a complete public record while its committed account of a multipart verdict omits a delivered part.
- Requested correction: Keep unresolved parts pending across archive attempts, or support append-only completion of their inventory when they appear. Require resolution before certifying the handoff.
- Requested evidence: Lose the response for the second part of a two-part verdict. Keep it hidden through the first archive, then restore visibility. Verify one original per part, one correction and authenticated archive references for both parts.

**R7-F4** · P1 · defect · blocks readiness — A retired verdict can still advance its checkpoint after restart
- Location: `agent_review/agent_review.py:1852`; acceptance: WF04, WF06, WF08
- Trigger: A process exit separates publication retirement from round invalidation.
- Expected: Retiring a verdict durably prevents acceptance of that round.
- Actual: The pre-publication gate-failure branch calls retire_verdict, which saves the superseded publication before the caller invalidates the round. If the controller exits between saves and the gate evidence becomes readable again, finish_round can publish the same key. send returns immediately for a superseded record, and finish_round accepts it without requiring posted state.
- Why it blocks / does not: A pass can advance after its public verdict has been retired, including when the preserved verdict was never fully delivered.
- Requested correction: Persist round invalidation with verdict retirement on every path. Require a current, fully posted verdict before committing acceptance.
- Requested evidence: Preserve a validated round with an uncertain verdict, make its gate log temporarily unavailable, and reload the state saved at retirement. Restore the log and verify that only a fresh review can advance.

**R7-F5** · P2 · required_gap · blocks readiness — The rebinding regression stubs the controller's state writer
- Location: `agent_review/test_agent_review.py:3126`; acceptance: WF07
- Trigger: The unit suite exercises interruption before the new binding is saved.
- Expected: The permission-rebinding regression uses real state files and the production save and reload paths.
- Actual: The new recovery test replaces Controller.save with a lambda that raises KeyboardInterrupt. This substitutes an internal persistence operation explicitly covered by the checkpoint's model/GitHub-only stubbing rule.
- Why it blocks / does not: The required behavior evidence must exercise real controller persistence through recovery.
- Requested correction: Construct the durable interrupted state with a staged settings file and the previously selected state file, then invoke the normal recovery entry point with persistence intact.
- Requested evidence: Run the revised temporary-repository test in the candidate-bound unit gate and check the selected file, full digest, helper path and altered-file rejection after reload.

#### Prior finding assessments

- **R1-F2** — `fix_verified` — For current-format receipts, the filename preserves the argument identity even when the first body is unreadable. The candidate regression confirms B cannot clear damaged A and a subsequent valid A can.
- **R1-F6** — `fix_rejected` — Header discovery and null top-level payload handling improved. Consumed leaf values and response-item discriminators still escape structural validation.
- **R3-F3** — `fix_verified` — The probe distinguishes errors from successful tool results. The separate candidate-bound live fixture supplies the missing operational evidence: an enrolled developer successfully pushed and produced a passing receipt for its own reviewed commit.
- **R5-F1** — `fix_rejected` — Staging a separate file preserves the old selection across an ordinary interruption. Recovery still pins whatever bytes occupy an existing destination without verifying the intended composition.
- **R5-F2** — `fix_rejected` — The uninterrupted guarded resume now reaches a visible BLOCKED state. The earlier persistent ACTIVE transition remains recoverable as ACTIVE after a crash.
- **R5-F4** — `fix_rejected` — Time filtering excludes distant history. Its backward margin still includes preceding-invocation records during immediate continuation.
- **R6-F1** — `fix_rejected` — Retirement queues a correction for uncertain delivery. The passing test restores visibility before archiving. Multipart delivery that becomes visible after the first archive remains unresolved.
- **R6-F2** — `fix_verified` — Project refresh now invalidates a validated round and clears a ready review or handoff when the project digest changes. New envelopes carry the project digest, and reviewer prompts read the refreshed instruction list. The unit log covers handoff invalidation.
- **R6-F3** — `fix_rejected` — The replacement-base-command regression passes for new-format receipts. Existing enrollments with intact predecessor-format receipts cannot recover on the same H.
- **R6-F4** — `fix_verified` — The exemption now matches actual handoff receipt keys. A retirement correction goes through ordinary remote body and author checks, and the candidate regression detects its removal.

#### Evidence assessment

- **Inspected:** Fixed request, mission and owner addenda, repository instructions, protocol, feature diff, changed-file inventory, developer dispositions and prior-findings ledger.; Controller source, schemas, prompt templates, permission base, project and checkpoint definitions, temporary-Git behavior fixtures, live-smoke implementation and candidate-bound evidence.
- **Executed verification:** Read-only Git inspection confirmed HEAD equals H and the merge base equals M. I independently hashed the three supplied gate logs. Each SHA-256 matches its controller receipt, and each receipt names the full candidate H, exit code 0 and an unchanged worktree.; The unit log records 160 tests run with one live test skipped. It includes the round-six regressions for rollout parsing, permission rebinding, budget exhaustion, effort provenance, retirement and project refresh.; The permissions log records two real Claude launches. The production launch denied the ambient status command and allowed the composed helper and git status. The control launch allowed the ambient command.; The separate live-smoke log records real model invocations with simulated GitHub. The developer transcript shows a successful guarded push and unit verification on fixture commit 14309477c7609bb675ffa7303ddc76b78c3b85cd. The helper receipt names that commit and records two passing calculator tests. The fixture reached owner handoff.
- **Source inspection only:** The failure paths below follow from the candidate's control flow, persistence order and receipt-selection rules. The supplied passing logs do not exercise those particular sequences.
- **Required gaps:** Candidate-bound behavior coverage is still needed for the interrupted transitions, malformed provenance, gate-definition changes and late publication reconciliation described in the findings.
- **Limitations:** The snapshot is read-only. I inspected the controller-recorded executions and did not rerun the suite or contact GitHub.; The foreground transcript is withheld. The live-smoke helper results apply to its named fixture commit, and its PR publications use simulated GitHub.

#### Summary

- **Delivered behavior:** The controller demonstrated an enrolled headless helper cycle and improved receipt attribution, project-refresh invalidation and authentication of public corrections. The outstanding defects affect evidence selection, permission integrity and restart behavior.
- **Scope reviewed:** Intermediate controller-core checkpoint for draft PR #1 at 7c963672b127f5bdb9c007693c9d1c4bfd9405a7, including all ten pending findings.
- **Pending later-phase work:** The setup-final checkpoint covers the completed workflow documentation, effective permissions and installation, Black Tentacles binding and start command, and the setup acceptance report.
- **Unresolved questions:** none
- **Remaining owner review:** Final acceptance of the completed setup and any later merge or release decision remain with the owner.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `high` | `high` (turns ['high']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Codex CLI `0.170.0`, thread `01a1fc5a-0015-7fb3-9e84-1c7f6639a02c`, duration 253.9s, response sha256 `d64d694090d9e732f2e39f7183926b20f135b02cb4ab298aebb7db0fe1797be9`, request `devproc-claude-agent-review-controller-20261120192057-9024-r07-099cc4`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "7c963672b127f5bdb9c007693c9d1c4bfd9405a7",
  "checkpoint_id": "controller-core",
  "checkpoint_type": "intermediate",
  "decision": "changes_required",
  "decision_rationale": "The candidate-bound runs establish that the enrolled developer can push and verify under the production permission profile. Controller-core still has paths that accept obsolete gate evidence, adopt altered permissions, or advance after a verdict was retired. Several recovery tests stop before the state transition where the defect occurs.",
  "evidence_assessment": {
    "executed_verification": [
      "Read-only Git inspection confirmed HEAD equals H and the merge base equals M. I independently hashed the three supplied gate logs. Each SHA-256 matches its controller receipt, and each receipt names the full candidate H, exit code 0 and an unchanged worktree.",
      "The unit log records 160 tests run with one live test skipped. It includes the round-six regressions for rollout parsing, permission rebinding, budget exhaustion, effort provenance, retirement and project refresh.",
      "The permissions log records two real Claude launches. The production launch denied the ambient status command and allowed the composed helper and git status. The control launch allowed the ambient command.",
      "The separate live-smoke log records real model invocations with simulated GitHub. The developer transcript shows a successful guarded push and unit verification on fixture commit 14309477c7609bb675ffa7303ddc76b78c3b85cd. The helper receipt names that commit and records two passing calculator tests. The fixture reached owner handoff."
    ],
    "inspected": [
      "Fixed request, mission and owner addenda, repository instructions, protocol, feature diff, changed-file inventory, developer dispositions and prior-findings ledger.",
      "Controller source, schemas, prompt templates, permission base, project and checkpoint definitions, temporary-Git behavior fixtures, live-smoke implementation and candidate-bound evidence."
    ],
    "limitations": [
      "The snapshot is read-only. I inspected the controller-recorded executions and did not rerun the suite or contact GitHub.",
      "The foreground transcript is withheld. The live-smoke helper results apply to its named fixture commit, and its PR publications use simulated GitHub."
    ],
    "required_gaps": [
      "Candidate-bound behavior coverage is still needed for the interrupted transitions, malformed provenance, gate-definition changes and late publication reconciliation described in the findings."
    ],
    "source_inspection_only": [
      "The failure paths below follow from the candidate's control flow, persistence order and receipt-selection rules. The supplied passing logs do not exercise those particular sequences."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "bind_developer_settings skips writing when the destination exists and pins sha256_file(path). If an inactive or staged settings file changed, that operation adopts its altered contents. Subsequent verification compares against the newly adopted digest and succeeds.",
      "blocking_rationale": "A resumed developer can receive permissions different from the reviewed composition.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The selected file must match the full digest of the freshly composed permission settings.",
      "id": "R5-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2336
      },
      "priority": "P1",
      "requested_correction": "Compute the expected digest from the composed bytes, verify any existing destination against it before selection, and persist that expected digest.",
      "requested_evidence": "Stage a binding, leave the old binding selected, alter the staged file, then resume relocation. Show that the altered bytes cannot become the active permissions.",
      "title": "Permission rebinding trusts the contents of an existing destination",
      "trigger": "Recovery or reactivation selects a previously created content-addressed settings file."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "activate updates the in-memory workflow and project, then calls retire_verdict before bind_developer_settings. Retirement saves state. A process exit after that save leaves the new workflow fingerprint and root paired with the previous permission binding. verify_inputs accepts that old file because it still matches its old digest and the package root already matches.",
      "blocking_rationale": "A reviewed permission restriction can be lost across an activation restart.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The activated workflow, project and selected permission file become current together.",
      "id": "R7-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2435
      },
      "priority": "P1",
      "requested_correction": "Stage the new permission file before any save can expose the new workflow. Commit the binding and invalidation together, or persist an activation intent that must complete before reuse.",
      "requested_evidence": "Activate a stricter permission base with a validated round present. Interrupt after verdict retirement, reload, and demonstrate that the old permissions cannot be used under the new fingerprint.",
      "title": "Activation can persist a new workflow with the previous permissions",
      "trigger": "A workflow or project change invalidates a validated round during activation."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF08"
      ],
      "actual": "The parser checks several enclosing objects but passes their leaf values directly to set and sorted. A nonempty object or list in turn_context.model or approval_policy raises TypeError before validate_review records an attempt outcome. Also, a response_item with an empty object payload has no discriminator and is silently ignored even in an otherwise valid rollout.",
      "blocking_rationale": "Malformed provenance can escape bounded attempt handling, and an unidentifiable response item can accompany an accepted review.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Malformed records used to establish model, settings or tool dispatch produce a recorded rejected attempt.",
      "id": "R1-F6",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 677
      },
      "priority": "P1",
      "requested_correction": "Validate the scalar types and required discriminators of consumed records before collecting observations. Route structural errors through invocation_problems.",
      "requested_evidence": "Supply otherwise valid rollouts with a structured model or approval value and with an untyped response item. Exercise review dispatch and verify recorded rejection, bounded retries and unchanged completed-round count.",
      "title": "Malformed rollout values still escape attempt validation",
      "trigger": "A selected rollout contains an object payload with malformed fields inside it."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF07"
      ],
      "actual": "ClaudeDeveloper.run subtracts one second from launch time and truncates the result to whole seconds. A preceding invocation's final high-effort record can fall inside that window. If the resumed invocation has no effort record, the scan can still yield high. The regression separates its records by an hour.",
      "blocking_rationale": "A headless report can dispatch review without affirmative effort provenance for the invocation that produced it.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Each invocation establishes its own observed effort.",
      "id": "R5-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 877
      },
      "priority": "P1",
      "requested_correction": "Capture the transcript position or an invocation identifier before launch and read effort from records attributable to that invocation.",
      "requested_evidence": "Run two immediately consecutive invocations in one fixture session. With high recorded only in the first, verify the second cannot dispatch. Add a current high observation and verify acceptance.",
      "title": "Adjacent developer invocations can share one effort observation",
      "trigger": "The controller immediately resumes Claude after a report needs correction."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF08"
      ],
      "actual": "gate_definition_id hashes only base argv. receipt_problems checks that prefix but never revalidates the extra arguments. After a project refresh narrows extra_args_pattern, a passing receipt for a now-excluded filter still satisfies the required gate on H.",
      "blocking_rationale": "A fresh review under the changed project can advance using evidence for a command the current gate would refuse to run.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Required evidence satisfies the currently declared gate and its argument restrictions.",
      "id": "R7-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3080
      },
      "priority": "P1",
      "requested_correction": "Include the argument policy in the gate-definition identity and validate receipt arguments against the active declaration.",
      "requested_evidence": "Pass filter A, refresh the same base command to allow only B, and show that A no longer satisfies the checkpoint. Run B on the same H and verify recovery.",
      "title": "Narrowing a gate's allowed filters leaves excluded evidence current",
      "trigger": "Project refresh changes the argument policy while retaining the base command."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF08"
      ],
      "actual": "Every filename from the preceding controller version has definition=None. gate_status records it as permanent unknown damage, even when the receipt JSON, candidate, command, timestamp and log digest are intact. A passing run of the replacement gate on the same H cannot clear it.",
      "blocking_rationale": "An enrolled branch with valid pre-upgrade evidence can remain blocked after running the requested replacement validation.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "An upgrade preserves readable historical evidence and lets the replacement gate establish a pass on the same candidate.",
      "id": "R6-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2140
      },
      "priority": "P2",
      "requested_correction": "Handle intact predecessor-format receipts separately from unreadable ones. Recover their attributable command and scope where possible, while retaining fail-closed handling for genuinely unknown damage.",
      "requested_evidence": "Start with an intact receipt in the immediately preceding release's format, refresh the gate command, rerun on H, and show that the new evidence is accepted while the old record remains intact.",
      "title": "Readable pre-upgrade receipts permanently block a replacement gate",
      "trigger": "A running enrollment upgrades with an existing required-gate receipt for H."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF08",
        "WF12"
      ],
      "actual": "run_gate leaves no persistent run record until after the subprocess finishes. The verify helper holds helper.lock, while foreground report acceptance and review use the writer lock. A newer gate can therefore be running while each missing_gates check sees only an older pass. An interrupted helper can leave that older pass current indefinitely.",
      "blocking_rationale": "An intermediate checkpoint can advance, or finalization can declare readiness, with required validation still pending.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A newer pending or interrupted required run prevents reuse of the earlier pass for that scope.",
      "id": "R7-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2176
      },
      "priority": "P1",
      "requested_correction": "Persist the gate run identity and pending state before dispatch. Include pending runs in report, acceptance and readiness checks, with recovery through a completed valid rerun.",
      "requested_evidence": "Pass a required gate, start a second run on the same H and hold it open. Submit a foreground report and verify it cannot advance. Interrupt the helper, reload state and verify that a completed rerun restores eligibility.",
      "title": "A required gate in progress is invisible to readiness checks",
      "trigger": "A foreground report overlaps a rerun of a previously passing gate."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF08"
      ],
      "actual": "reopen saves ACTIVE/develop before publishing the reopen notice and editing the PR body. resume checks the exhausted budget only after reopen returns. A process exit in between leaves helpers available. On restart the local reopened flag is false, so the ordinary exhausted-budget path raises UsageError and retains ACTIVE.",
      "blocking_rationale": "Recovery can re-enable foreground push and verification at the exhausted cap without the owner's extension.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Reopening at the cap durably disables development until the owner extends the budget.",
      "id": "R5-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2988
      },
      "priority": "P1",
      "requested_correction": "Compute the effective budget before persisting the reopen transition. Save the cleared handoff and resulting blocked status together, and make its public updates resumable.",
      "requested_evidence": "Interrupt the simulated GitHub boundary during reopen after the local transition. Reload, verify helper refusal and a recoverable visible budget stop, then extend the limit and resume.",
      "title": "An interrupted handoff reopen can leave development active at the cap",
      "trigger": "The controller exits during public updates for a superseded last-round handoff."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF09"
      ],
      "actual": "The new archive scan reconciles an uncertain part once. If one part is known and another stored part is still absent from the listing, archive commits the partial inventory and marks the entire key archived. Later archive calls skip the key, and handoff checks skip superseded publications. A late-visible part never acquires its archived reference.",
      "blocking_rationale": "The controller can certify a complete public record while its committed account of a multipart verdict omits a delivered part.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every delivered verdict part is reconciled before the archive inventory is declared complete.",
      "id": "R6-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2550
      },
      "priority": "P1",
      "requested_correction": "Keep unresolved parts pending across archive attempts, or support append-only completion of their inventory when they appear. Require resolution before certifying the handoff.",
      "requested_evidence": "Lose the response for the second part of a two-part verdict. Keep it hidden through the first archive, then restore visibility. Verify one original per part, one correction and authenticated archive references for both parts.",
      "title": "Archiving a partial verdict can discard a later delivery",
      "trigger": "A superseded multipart verdict has a known first part and an uncertain later part."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF08"
      ],
      "actual": "The pre-publication gate-failure branch calls retire_verdict, which saves the superseded publication before the caller invalidates the round. If the controller exits between saves and the gate evidence becomes readable again, finish_round can publish the same key. send returns immediately for a superseded record, and finish_round accepts it without requiring posted state.",
      "blocking_rationale": "A pass can advance after its public verdict has been retired, including when the preserved verdict was never fully delivered.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Retiring a verdict durably prevents acceptance of that round.",
      "id": "R7-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1852
      },
      "priority": "P1",
      "requested_correction": "Persist round invalidation with verdict retirement on every path. Require a current, fully posted verdict before committing acceptance.",
      "requested_evidence": "Preserve a validated round with an uncertain verdict, make its gate log temporarily unavailable, and reload the state saved at retirement. Restore the log and verify that only a fresh review can advance.",
      "title": "A retired verdict can still advance its checkpoint after restart",
      "trigger": "A process exit separates publication retirement from round invalidation."
    },
    {
      "acceptance_ids": [
        "WF07"
      ],
      "actual": "The new recovery test replaces Controller.save with a lambda that raises KeyboardInterrupt. This substitutes an internal persistence operation explicitly covered by the checkpoint's model/GitHub-only stubbing rule.",
      "blocking_rationale": "The required behavior evidence must exercise real controller persistence through recovery.",
      "blocks_readiness": true,
      "category": "required_gap",
      "expected": "The permission-rebinding regression uses real state files and the production save and reload paths.",
      "id": "R7-F5",
      "location": {
        "file": "agent_review/test_agent_review.py",
        "line": 3126
      },
      "priority": "P2",
      "requested_correction": "Construct the durable interrupted state with a staged settings file and the previously selected state file, then invoke the normal recovery entry point with persistence intact.",
      "requested_evidence": "Run the revised temporary-repository test in the candidate-bound unit gate and check the selected file, full digest, helper path and altered-file rejection after reload.",
      "title": "The rebinding regression stubs the controller's state writer",
      "trigger": "The unit suite exercises interruption before the new binding is saved."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F2",
      "rationale": "For current-format receipts, the filename preserves the argument identity even when the first body is unreadable. The candidate regression confirms B cannot clear damaged A and a subsequent valid A can."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F6",
      "rationale": "Header discovery and null top-level payload handling improved. Consumed leaf values and response-item discriminators still escape structural validation."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R3-F3",
      "rationale": "The probe distinguishes errors from successful tool results. The separate candidate-bound live fixture supplies the missing operational evidence: an enrolled developer successfully pushed and produced a passing receipt for its own reviewed commit."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R5-F1",
      "rationale": "Staging a separate file preserves the old selection across an ordinary interruption. Recovery still pins whatever bytes occupy an existing destination without verifying the intended composition."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R5-F2",
      "rationale": "The uninterrupted guarded resume now reaches a visible BLOCKED state. The earlier persistent ACTIVE transition remains recoverable as ACTIVE after a crash."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R5-F4",
      "rationale": "Time filtering excludes distant history. Its backward margin still includes preceding-invocation records during immediate continuation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R6-F1",
      "rationale": "Retirement queues a correction for uncertain delivery. The passing test restores visibility before archiving. Multipart delivery that becomes visible after the first archive remains unresolved."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R6-F2",
      "rationale": "Project refresh now invalidates a validated round and clears a ready review or handoff when the project digest changes. New envelopes carry the project digest, and reviewer prompts read the refreshed instruction list. The unit log covers handoff invalidation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R6-F3",
      "rationale": "The replacement-base-command regression passes for new-format receipts. Existing enrollments with intact predecessor-format receipts cannot recover on the same H."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R6-F4",
      "rationale": "The exemption now matches actual handoff receipt keys. A retirement correction goes through ordinary remote body and author checks, and the candidate regression detects its removal."
    }
  ],
  "request_id": "devproc-claude-agent-review-controller-20261120192057-9024-r07-099cc4",
  "round": 7,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "The controller demonstrated an enrolled headless helper cycle and improved receipt attribution, project-refresh invalidation and authentication of public corrections. The outstanding defects affect evidence selection, permission integrity and restart behavior.",
    "pending_later_phase_work": [
      "The setup-final checkpoint covers the completed workflow documentation, effective permissions and installation, Black Tentacles binding and start command, and the setup acceptance report."
    ],
    "remaining_owner_review": [
      "Final acceptance of the completed setup and any later merge or release decision remain with the owner."
    ],
    "scope_reviewed": "Intermediate controller-core checkpoint for draft PR #1 at 7c963672b127f5bdb9c007693c9d1c4bfd9405a7, including all ten pending findings.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
