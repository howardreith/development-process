<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r10-review part=1/1 sha256=805208fbe4443d2526cdc6f1ca3becec1698bebc81393044dee97856f6d9d8db -->
### Codex GPT-6.2 Astra — review — round 10 — candidate `7c58a2b6d3`

**Decision:** `changes_required` — The required unit gate and both supplemental gates passed on H. The controller can still reach final readiness after deferring an outstanding correctness finding or overlooking a missing publication reference in an existing archive. The review also identified a developer provenance check, a crash-recovery gap in PR notification, and a legacy gate test that cannot distinguish the intended behavior from ignoring every legacy receipt.

#### Findings

**R8-F3** · P1 · defect · blocks readiness — An optional deferral can still close a retained correctness obligation
- Location: `agent_review/agent_review.py:1903`; acceptance: WF05, WF08
- Trigger: A developer proposes deferring a previously rejected defect after the reviewer restated it as nonblocking polish.
- Expected: An outstanding correctness obligation requires a verified fix or an accepted rebuttal. Optional deferral applies to genuinely optional work.
- Actual: A rejected nonblocking defect now retains correctness_obligation when restated as polish. On the next round, accept_report permits deferred_optional because it checks only blocks_readiness. semantic_problems likewise permits deferral_accepted and removes the ID from open_after. The ledger then records it as resolved, so final readiness accepts it.
- Why it blocks / does not: A required correctness disposition can still be replaced with an optional deferral before handoff.
- Requested correction: Check the retained correctness obligation at both developer disposition admission and reviewer assessment validation. Preserve the deferral path for genuine optional findings.
- Requested evidence: Persist a rejected nonblocking defect restated as polish in a changes-required round. Attempt to defer it in the next round and verify final readiness remains unavailable. Include a genuine optional finding whose deferral succeeds.

**R6-F1** · P2 · defect · blocks readiness — Previously committed supplements remain permanently missing their references
- Location: `agent_review/agent_review.py:2702`; acceptance: WF06, WF09
- Trigger: An enrollment activates the new controller after the preceding version committed a late-part supplement.
- Expected: At handoff, each confirmed review part maps to its original part number, GitHub comment ID and URL, including parts archived before an upgrade.
- Actual: New supplements contain the correct references, but unarchived_parts decides coverage solely by finding the marker anywhere in a committed record. A supplement written by the preceding version already contains that marker and omits the ID and URL. After activation, archive skips the part and readiness reports it covered.
- Why it blocks / does not: A resumed enrollment can hand off an archive that still lacks the authenticated reference for a delivered review part.
- Requested correction: Check committed reference coverage for the delivered parts. When an older record contains the text but lacks or misnumbers its reference, append the missing mapping while preserving the existing blobs.
- Requested evidence: Start with a committed predecessor-format partial archive and marker-only supplement. Resume under the candidate and inspect the handoff tree for the correct part number, ID and URL. Verify that the earlier blob hashes stay intact.

**R6-F3** · P2 · evidence_gap · blocks readiness — Ignoring every predecessor receipt still satisfies the migration regression
- Location: `agent_review/test_agent_review.py:3546`; acceptance: WF04, WF08
- Trigger: The behavior suite tests whether an old failing argument scope survives a controller upgrade.
- Expected: The test distinguishes a legacy failure that actively blocks the gate from a gate missing because it has no recognized evidence.
- Actual: The revised test converts both failing A and passing B to the old-hash format. An implementation that ignores both files would also report the gate missing and would pass after the fresh A rerun. The timestamp-only test similarly has no competing passing scope at its initial assertion.
- Why it blocks / does not: The green migration regression still cannot establish that a legacy failure prevents advancement on another scope's passing evidence.
- Requested correction: Convert the failing A receipt alone, remove its current-format marker, then run B under the current format before checking the gate. Exercise the narrowed-filter case with the same distinction.
- Requested evidence: On one H, demonstrate a current B pass, a still-blocking legacy A failure, and recovery after A passes. For a policy narrowed to B, demonstrate that the excluded A failure becomes historical.

**R10-F1** · P1 · defect · blocks readiness — Headless report admission discards conflicting transcript model evidence
- Location: `agent_review/agent_review.py:953`; acceptance: WF05
- Trigger: The Claude stream and the session transcript provide different main-thread model evidence for one invocation.
- Expected: Every available main-thread model observation for the headless invocation agrees with the pinned Opus policy before report admission.
- Actual: ClaudeDeveloper.run reads the current invocation's transcript model and effort observations, then copies only the efforts into the result. develop_step validates the stream's init model and main_models. An Opus init with an empty or Opus-only stream model list therefore passes even when the same invocation's transcript records a different main-thread model.
- Why it blocks / does not: An available, contradictory model observation can be discarded before the controller attributes the checkpoint to the owner-selected developer.
- Requested correction: Carry the invocation-local transcript models into the developer provenance record and validate them alongside the stream observations before admitting the report.
- Requested evidence: Use a simulated Claude boundary with an Opus init, a successful structured report, high transcript effort and a conflicting main-thread transcript model. Verify a visible stop before reviewer dispatch. Retain a passing case with consistent observations.

**R10-F2** · P2 · defect · blocks readiness — A crash after saving a fatal attempt can lose its PR stop notice
- Location: `agent_review/agent_review.py:1692`; acceptance: WF06, WF07, WF08
- Trigger: The controller exits after saving a fatal reviewer outcome and before queuing the GitHub status comment.
- Expected: A durable fatal stop also has a durable publication intent so restart can publish its reason exactly once.
- Actual: review_attempt persists the fatal attempt and BLOCKED state together. The outgoing status notice is created later by guarded's exception handler. A process exit between those steps leaves no notice to reconcile. Ordinary continuation is refused, and an owner resume can clear the stop and start another attempt without publishing why the previous one stopped.
- Why it blocks / does not: The draft PR can permanently omit a wrong-model or quota blocker even though the controller recorded it locally.
- Requested correction: Persist the status notice or its recoverable publication intent with the fatal stop. Reconcile it before further reviewer dispatch on resume.
- Requested evidence: Restart from the state saved immediately after a fatal attempt and before the outer exception handler runs. Verify that the PR receives one blocker notice with the saved reason before any owner-authorized replacement attempt.

#### Prior finding assessments

- **R1-F6** — `fix_verified` — Rollout headers, consumed rollout records and reviewer events now reject duplicate members. The resulting provenance or completion failure reaches invocation validation.
- **R6-F1** — `fix_rejected` — Newly generated supplements preserve the reference, and new partial envelopes use the original index. The marker-only coverage check leaves already-committed predecessor supplements incomplete after activation.
- **R6-F3** — `fix_rejected` — The fixtures now remove current-format markers, but they also remove the independent current-format passing scope needed to show the legacy failure decides the result.
- **R7-F3** — `fix_verified` — Both report entry points hold the helper lock across admission and the durable transition to review. Push and verify reload authority under that same lock. The lock-contention and gate-completion regressions passed.
- **R8-F3** — `fix_rejected` — The direct reject-and-restatement case now fails final validation. A subsequent optional deferral can still resolve the retained correctness obligation because both deferral checks consult only blocks_readiness.
- **R9-F1** — `fix_verified` — Listing lag preserves acknowledged comment IDs. The candidate regressions cover repeated incomplete listings followed by acceptance with one verdict, and replacement after confirmed deletion.
- **R9-F2** — `fix_verified` — The fatal attempt and local BLOCKED state are saved together, and a recovered round checks recorded fatal attempts before dispatch. The restart regression made zero reviewer calls. R10-F2 concerns the separate PR notification.
- **R9-F3** — `fix_verified` — The client requests all commit-status pages and keeps the newest status for each context. The gh-shim regression confirms the endpoint, pagination flag and handling of a superseded failure.

#### Evidence assessment

- **Inspected:** The mission, owner addenda, repository instructions, protocol, checkpoint plan, feature diff, developer report and prior findings ledger.; Controller paths for report admission, model provenance, review validation, publication, stop/resume, gate receipts, archive creation and final readiness, together with their behavior tests.; The foreground transcript notice and the candidate-bound unit, permissions and live-smoke receipts and logs.
- **Executed verification:** Verified the detached HEAD, merge base and mission digest against the request. Independently hashed all three gate logs and matched them to the controller receipts for H.; The unit gate ran 187 tests in 350.260 seconds and reported OK with one live test skipped. The gate recorded exit code 0 and an unchanged worktree.; The permissions gate ran two Claude sessions. The production profile denied the ambient status command and allowed the enrolled helper and Git inspection. The control session ran all three commands.; The separate live smoke passed in 65.631 seconds. The real headless Opus developer pushed and verified fixture commit 83b6b7a, and the real reviewer completed a round that reached AWAITING_OWNER_REVIEW against simulated GitHub.
- **Source inspection only:** Traced the remaining failure paths against the candidate source and the predecessor archive format. The supplied logs do not record executions of those specific cases.
- **Required gaps:** A test must distinguish honoring a predecessor-format failure from ignoring all predecessor receipts when a current-format pass exists for another argument list.; Recovery coverage is needed for already-committed marker-only supplements, deferral of a retained correctness obligation, contradictory developer model observations and interruption before a fatal stop notice is queued.
- **Limitations:** The snapshot was read-only. Execution evidence comes from the controller receipts and logs. The foreground developer's whole-session transcript was withheld.; The live smoke exercised a calculator fixture. Its GitHub comments, hosted checks and handoff were simulated. The hosted-status regression also used a gh shim.

#### Summary

- **Delivered behavior:** The candidate closes the helper-admission race, retains acknowledged verdict IDs during listing lag, rejects duplicate reviewer metadata fields, prevents automatic redispatch after a recorded fatal attempt and paginates commit statuses.
- **Scope reviewed:** The intermediate controller-core checkpoint for draft PR #1, including controller behavior, schemas, prompts, model and permission configuration, behavior tests and candidate-bound gate evidence.
- **Pending later-phase work:** The setup-final checkpoint covers installation, workflow documentation, effective permissions, the Black Tentacles binding and the complete setup acceptance report.
- **Unresolved questions:** none
- **Remaining owner review:** Final acceptance of the completed setup and any later merge or release decision remain with the owner.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `high` | `high` (turns ['high']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Codex CLI `0.170.0`, thread `01a1fcae-dce1-7082-aa8d-706a1f3b182f`, duration 359.4s, response sha256 `d237415bf07c4256e713b6d1ee35314a973ac298b9e99154fd2dbd9ad33ad2a0`, request `devproc-claude-agent-review-controller-20261120192057-9024-r10-1e53c1`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "7c58a2b6d30c87ea011752bc01a28e0aa7140be4",
  "checkpoint_id": "controller-core",
  "checkpoint_type": "intermediate",
  "decision": "changes_required",
  "decision_rationale": "The required unit gate and both supplemental gates passed on H. The controller can still reach final readiness after deferring an outstanding correctness finding or overlooking a missing publication reference in an existing archive. The review also identified a developer provenance check, a crash-recovery gap in PR notification, and a legacy gate test that cannot distinguish the intended behavior from ignoring every legacy receipt.",
  "evidence_assessment": {
    "executed_verification": [
      "Verified the detached HEAD, merge base and mission digest against the request. Independently hashed all three gate logs and matched them to the controller receipts for H.",
      "The unit gate ran 187 tests in 350.260 seconds and reported OK with one live test skipped. The gate recorded exit code 0 and an unchanged worktree.",
      "The permissions gate ran two Claude sessions. The production profile denied the ambient status command and allowed the enrolled helper and Git inspection. The control session ran all three commands.",
      "The separate live smoke passed in 65.631 seconds. The real headless Opus developer pushed and verified fixture commit 83b6b7a, and the real reviewer completed a round that reached AWAITING_OWNER_REVIEW against simulated GitHub."
    ],
    "inspected": [
      "The mission, owner addenda, repository instructions, protocol, checkpoint plan, feature diff, developer report and prior findings ledger.",
      "Controller paths for report admission, model provenance, review validation, publication, stop/resume, gate receipts, archive creation and final readiness, together with their behavior tests.",
      "The foreground transcript notice and the candidate-bound unit, permissions and live-smoke receipts and logs."
    ],
    "limitations": [
      "The snapshot was read-only. Execution evidence comes from the controller receipts and logs. The foreground developer's whole-session transcript was withheld.",
      "The live smoke exercised a calculator fixture. Its GitHub comments, hosted checks and handoff were simulated. The hosted-status regression also used a gh shim."
    ],
    "required_gaps": [
      "A test must distinguish honoring a predecessor-format failure from ignoring all predecessor receipts when a current-format pass exists for another argument list.",
      "Recovery coverage is needed for already-committed marker-only supplements, deferral of a retained correctness obligation, contradictory developer model observations and interruption before a fatal stop notice is queued."
    ],
    "source_inspection_only": [
      "Traced the remaining failure paths against the candidate source and the predecessor archive format. The supplied logs do not record executions of those specific cases."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "WF05",
        "WF08"
      ],
      "actual": "A rejected nonblocking defect now retains correctness_obligation when restated as polish. On the next round, accept_report permits deferred_optional because it checks only blocks_readiness. semantic_problems likewise permits deferral_accepted and removes the ID from open_after. The ledger then records it as resolved, so final readiness accepts it.",
      "blocking_rationale": "A required correctness disposition can still be replaced with an optional deferral before handoff.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "An outstanding correctness obligation requires a verified fix or an accepted rebuttal. Optional deferral applies to genuinely optional work.",
      "id": "R8-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1903
      },
      "priority": "P1",
      "requested_correction": "Check the retained correctness obligation at both developer disposition admission and reviewer assessment validation. Preserve the deferral path for genuine optional findings.",
      "requested_evidence": "Persist a rejected nonblocking defect restated as polish in a changes-required round. Attempt to defer it in the next round and verify final readiness remains unavailable. Include a genuine optional finding whose deferral succeeds.",
      "title": "An optional deferral can still close a retained correctness obligation",
      "trigger": "A developer proposes deferring a previously rejected defect after the reviewer restated it as nonblocking polish."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF09"
      ],
      "actual": "New supplements contain the correct references, but unarchived_parts decides coverage solely by finding the marker anywhere in a committed record. A supplement written by the preceding version already contains that marker and omits the ID and URL. After activation, archive skips the part and readiness reports it covered.",
      "blocking_rationale": "A resumed enrollment can hand off an archive that still lacks the authenticated reference for a delivered review part.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "At handoff, each confirmed review part maps to its original part number, GitHub comment ID and URL, including parts archived before an upgrade.",
      "id": "R6-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2702
      },
      "priority": "P2",
      "requested_correction": "Check committed reference coverage for the delivered parts. When an older record contains the text but lacks or misnumbers its reference, append the missing mapping while preserving the existing blobs.",
      "requested_evidence": "Start with a committed predecessor-format partial archive and marker-only supplement. Resume under the candidate and inspect the handoff tree for the correct part number, ID and URL. Verify that the earlier blob hashes stay intact.",
      "title": "Previously committed supplements remain permanently missing their references",
      "trigger": "An enrollment activates the new controller after the preceding version committed a late-part supplement."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF08"
      ],
      "actual": "The revised test converts both failing A and passing B to the old-hash format. An implementation that ignores both files would also report the gate missing and would pass after the fresh A rerun. The timestamp-only test similarly has no competing passing scope at its initial assertion.",
      "blocking_rationale": "The green migration regression still cannot establish that a legacy failure prevents advancement on another scope's passing evidence.",
      "blocks_readiness": true,
      "category": "evidence_gap",
      "expected": "The test distinguishes a legacy failure that actively blocks the gate from a gate missing because it has no recognized evidence.",
      "id": "R6-F3",
      "location": {
        "file": "agent_review/test_agent_review.py",
        "line": 3546
      },
      "priority": "P2",
      "requested_correction": "Convert the failing A receipt alone, remove its current-format marker, then run B under the current format before checking the gate. Exercise the narrowed-filter case with the same distinction.",
      "requested_evidence": "On one H, demonstrate a current B pass, a still-blocking legacy A failure, and recovery after A passes. For a policy narrowed to B, demonstrate that the excluded A failure becomes historical.",
      "title": "Ignoring every predecessor receipt still satisfies the migration regression",
      "trigger": "The behavior suite tests whether an old failing argument scope survives a controller upgrade."
    },
    {
      "acceptance_ids": [
        "WF05"
      ],
      "actual": "ClaudeDeveloper.run reads the current invocation's transcript model and effort observations, then copies only the efforts into the result. develop_step validates the stream's init model and main_models. An Opus init with an empty or Opus-only stream model list therefore passes even when the same invocation's transcript records a different main-thread model.",
      "blocking_rationale": "An available, contradictory model observation can be discarded before the controller attributes the checkpoint to the owner-selected developer.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every available main-thread model observation for the headless invocation agrees with the pinned Opus policy before report admission.",
      "id": "R10-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 953
      },
      "priority": "P1",
      "requested_correction": "Carry the invocation-local transcript models into the developer provenance record and validate them alongside the stream observations before admitting the report.",
      "requested_evidence": "Use a simulated Claude boundary with an Opus init, a successful structured report, high transcript effort and a conflicting main-thread transcript model. Verify a visible stop before reviewer dispatch. Retain a passing case with consistent observations.",
      "title": "Headless report admission discards conflicting transcript model evidence",
      "trigger": "The Claude stream and the session transcript provide different main-thread model evidence for one invocation."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF07",
        "WF08"
      ],
      "actual": "review_attempt persists the fatal attempt and BLOCKED state together. The outgoing status notice is created later by guarded's exception handler. A process exit between those steps leaves no notice to reconcile. Ordinary continuation is refused, and an owner resume can clear the stop and start another attempt without publishing why the previous one stopped.",
      "blocking_rationale": "The draft PR can permanently omit a wrong-model or quota blocker even though the controller recorded it locally.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A durable fatal stop also has a durable publication intent so restart can publish its reason exactly once.",
      "id": "R10-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1692
      },
      "priority": "P2",
      "requested_correction": "Persist the status notice or its recoverable publication intent with the fatal stop. Reconcile it before further reviewer dispatch on resume.",
      "requested_evidence": "Restart from the state saved immediately after a fatal attempt and before the outer exception handler runs. Verify that the PR receives one blocker notice with the saved reason before any owner-authorized replacement attempt.",
      "title": "A crash after saving a fatal attempt can lose its PR stop notice",
      "trigger": "The controller exits after saving a fatal reviewer outcome and before queuing the GitHub status comment."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F6",
      "rationale": "Rollout headers, consumed rollout records and reviewer events now reject duplicate members. The resulting provenance or completion failure reaches invocation validation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R6-F1",
      "rationale": "Newly generated supplements preserve the reference, and new partial envelopes use the original index. The marker-only coverage check leaves already-committed predecessor supplements incomplete after activation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R6-F3",
      "rationale": "The fixtures now remove current-format markers, but they also remove the independent current-format passing scope needed to show the legacy failure decides the result."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R7-F3",
      "rationale": "Both report entry points hold the helper lock across admission and the durable transition to review. Push and verify reload authority under that same lock. The lock-contention and gate-completion regressions passed."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R8-F3",
      "rationale": "The direct reject-and-restatement case now fails final validation. A subsequent optional deferral can still resolve the retained correctness obligation because both deferral checks consult only blocks_readiness."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R9-F1",
      "rationale": "Listing lag preserves acknowledged comment IDs. The candidate regressions cover repeated incomplete listings followed by acceptance with one verdict, and replacement after confirmed deletion."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R9-F2",
      "rationale": "The fatal attempt and local BLOCKED state are saved together, and a recovered round checks recorded fatal attempts before dispatch. The restart regression made zero reviewer calls. R10-F2 concerns the separate PR notification."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R9-F3",
      "rationale": "The client requests all commit-status pages and keeps the newest status for each context. The gh-shim regression confirms the endpoint, pagination flag and handling of a superseded failure."
    }
  ],
  "request_id": "devproc-claude-agent-review-controller-20261120192057-9024-r10-1e53c1",
  "round": 10,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "The candidate closes the helper-admission race, retains acknowledged verdict IDs during listing lag, rejects duplicate reviewer metadata fields, prevents automatic redispatch after a recorded fatal attempt and paginates commit statuses.",
    "pending_later_phase_work": [
      "The setup-final checkpoint covers installation, workflow documentation, effective permissions, the Black Tentacles binding and the complete setup acceptance report."
    ],
    "remaining_owner_review": [
      "Final acceptance of the completed setup and any later merge or release decision remain with the owner."
    ],
    "scope_reviewed": "The intermediate controller-core checkpoint for draft PR #1, including controller behavior, schemas, prompts, model and permission configuration, behavior tests and candidate-bound gate evidence.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
