<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r04-review part=1/1 sha256=236fabb76f47920724626d6d8ab8f5743208548942edcb1c08ae452730d53c4d -->
### Codex GPT-6.2 Astra — review — round 4 — candidate `8c233d0c29`

**Decision:** `changes_required` — The required unit gate passed, and seven of eight pending fixes are verified. Watch can still write into a linked worktree’s Git records and report a false stall. Two foreground failure paths can leave a stale blocker or publish a private transcript filename.

## Continuation for Claude

Protect both Git directories used by a linked worktree before opening a watch log. Track the arrival of event records separately from the last action displayed. After a capped amendment’s queued publication succeeds, restore the budget as the current blocker. Keep transcript filenames in local diagnostics when a reviewer launch is refused.

Exercise these four paths with temporary Git repositories, real controller state and the existing model and GitHub fixtures. Run the required unit gate on the corrected commit through the pinned controller. Keep the existing enrollment, model policy, review budget and owner handoff boundary.

#### Findings

**R2-F4** · P2 · defect · blocks readiness — Watch log protection is incomplete for linked worktrees
- Location: `agent_review/agent_review.py:5986`; acceptance: Part A, Existing running jobs, Part A.3
- Trigger: An operator selects a Git metadata path as the log for a linked worktree, or the observing shell cannot resolve that worktree’s Git directory.
- Expected: File output is admitted only after the controller establishes that its destination is separate from the enrolled worktree’s Git and ownership records.
- Actual: watch_log_problem protects the per-worktree Git directory only when its lookup succeeds. It suppresses lookup errors, leaving the linked worktree’s ownership marker outside the remaining protected roots. Even on success, the common Git directory holding the enrolled branch’s refs and reflogs is outside the check. The regression fixture uses an ordinary clone whose .git directory is already inside its worktree.
- Why it blocks / does not: An observer can append its feed to an ownership record or the enrolled branch’s Git metadata. Either can interfere with the job being watched.
- Requested correction: Protect the per-worktree and common Git directories. Refuse optional file output when the protected locations cannot be established. Keep console observation available.
- Requested evidence: Use a real linked worktree with separate state and Git directories. Verify refusal for a destination in shared Git metadata and for the ownership marker when Git-directory lookup fails. Check that protected files remain byte-identical and that a separate log works.

**R4-F1** · P2 · defect · blocks readiness — Successful publication recovery can leave a stale PAUSED reason at the cap
- Location: `agent_review/agent_review.py:4188`; acceptance: Part A.4, Part B.2, Part B.5
- Trigger: The amendment has consumed the last available round and GitHub temporarily fails while the controller publishes its handoff correction.
- Expected: Once publication recovers, the enrollment reports BLOCKED with the exhausted budget and applied amendment as its current reason.
- Actual: A failed queued PR-body edit reaches guarded, which saves PAUSED with the publication error. On the next ordinary resume, settle_publications completes the edit, then the exhausted-budget branch raises UsageError. The saved status and reason still describe the resolved outage.
- Why it blocks / does not: The owner can recover the public correction and still be told by status and watch that publication is the outstanding problem. The actual decision needed is whether to extend the review budget.
- Requested correction: After successful settlement, restore the capped amendment’s durable blocker and make the public status consistent. Preserve publication failures while they are outstanding and keep replay idempotent.
- Requested evidence: Fail the queued PR-body edit once after amending a handed-off final round. Recover with the original limit and inspect status, the public notices and the PR body. Repeat recovery and verify stable counters, closed admission and no duplicate correction.

**R4-F2** · P2 · defect · blocks readiness — A reviewer retry can publish the private transcript filename
- Location: `agent_review/agent_review.py:3012`; acceptance: Part A.5, Part A, private evidence, Protocol §8
- Trigger: The enrolled session’s transcript becomes unreadable when the controller checks provenance before a fresh reviewer attempt.
- Expected: The launch stays closed. Local status carries the diagnosis needed for recovery, and the PR receives the documented filesystem-error summary.
- Actual: require_foreground_launcher embeds the full filesystem exception in a Stop. guarded therefore publishes the Stop reason directly. Its filesystem-error handling, which limits the public diagnostic to the error type and errno, only applies when it receives an OSError. A transcript filename outside the home directory survives publication sanitization.
- Why it blocks / does not: A private transcript location can enter the PR discussion and its archived records during an ordinary read failure.
- Requested correction: Preserve the distinction between the local diagnostic and the publishable reason when transcript access fails at reviewer admission. Keep the persisted policy stop for an observed model, effort or permission mismatch.
- Requested evidence: Have the transcript read fail before a retry with a distinctive fixture filename. Verify the local diagnosis, the public comment’s error type and omission of the filename, and the unchanged reviewer-call and round counts.

**R4-F3** · P2 · defect · blocks readiness — Watch can report a stall immediately after an event arrives
- Location: `agent_review/agent_review.py:5964`; acceptance: Part A, Existing running jobs, Part A.3, Part B.5
- Trigger: A running developer or reviewer emits records whose content is intentionally omitted from the live view.
- Expected: The watcher accurately distinguishes event arrival, the latest displayable action and elapsed time without exposing reasoning content.
- Actual: The watcher updates its activity time only for records that render a row. With no such row it measures silence from the attempt start, even when a complete record just arrived. On first attachment it also selects the last 15 raw records before rendering, so it can miss the latest command and report that no action has been observed.
- Why it blocks / does not: The live view can tell the owner that no events have arrived for the entire stall interval while the current stream is receiving records.
- Requested correction: Track the last complete event for the current invocation or attempt separately from its last rendered action. On attachment, recover the latest displayable action even when later records are filtered.
- Requested evidence: Attach to an aged attempt with a visible command followed by more than 15 filtered records. Append a fresh metadata event and check the reported action and silence interval. Then advance through a genuinely quiet interval and verify the stall notice.

#### Prior finding assessments

- **R2-F3** — `fix_verified` — Actions are keyed by developer invocation or reviewer round and attempt. The passing retry fixture distinguishes both attempts and labels a live gate PID as identity unconfirmed. R4-F3 concerns the separate calculation of event silence.
- **R2-F4** — `fix_rejected` — The hard-link and host-claim checks pass. The ownership marker remains writable through the optional log when Git-directory discovery fails for a linked worktree. The ordinary-clone fixture cannot detect that omission.
- **R2-F5** — `fix_verified` — Part selection now counts JSON-escaped width. The unit fixture checks the complete displays and missing-part refusal. The matching-code interface record reports displays of 9,614, 9,614 and 4,513 bytes, refusal before part 3 and admission after its display.
- **R3-F1** — `fix_verified` — After the specified interruption immediately following the amendment save, ordinary resume settles the public corrections at the original limit. The candidate fixture verified two replays, closed admission and unchanged counters. R4-F1 concerns the status left by an intervening publication error.
- **R3-F2** — `fix_verified` — Headless dispatch resolves the PATH-selected executable before recording launch intent or charging the invocation. The fixture exercised run and resume with a simulated lookup failure and observed zero charges and no launch record.
- **R3-F3** — `fix_verified` — Every automatic attempt now checks current foreground provenance. The passing test changed effort after the first retryable failure and observed BLOCKED, one reviewer call and zero completed rounds.
- **R3-F4** — `fix_verified` — The status dispatcher compares the requested enrollment ID before rendering either instruction form. Both CLI calls in the misdirected-claim fixture refused without exposing the other amendment or its marker.
- **R3-F5** — `fix_verified` — The watch dispatcher closes the optional log in a finally block. The candidate test verified a readable feed and observed no ResourceWarning after collection.

#### Evidence assessment

- **Inspected:** The mission, repository instructions, operating guide, protocol, full feature diff and correction diff from 2cc19f7.; The developer report, all eight pending ledger entries, candidate-bound unit receipt and log, and the foreground transcript withholding notice.; The foreground behavior tests and planning/evidence/pr-7-foreground-cycle.md, including the correction cycle, pre-exit output, amendment demonstrations and PR #6 outcome.
- **Executed verification:** The controller receipt binds the required unit command to 8c233d0c2940065d2555e9d02d857a096cd5852d. It records exit 0, an unchanged worktree and 908.8 seconds. The matching log records 290 tests, OK with one skipped, including all seven ForegroundRoundThreeTests.; Read-only Git and hash checks confirmed HEAD, the merge base, the enrolled mission digest and the gate-log digest. The controller file matches the SHA-256 in section 5 of the interface record. Only that evidence document changed after b81d2fe.; Git reported distinct per-worktree and common Git directories for this detached snapshot.
- **Source inspection only:** Traced watch log admission through the Git directory lookup and append operation, and watch timing from event parsing through the stall message.; Traced a failed PR-body edit through guarded and the next capped resume, and a transcript read error through require_foreground_launcher and public status publication. These failure combinations were identified from source.
- **Required gaps:** A corrected-candidate unit receipt covering linked-worktree log protection, the budget status after publication recovery, public transcript-read diagnostics and watch timing after filtered events.
- **Limitations:** This read-only review used the supplied gate evidence. The real-interface observations come from the scoped developer record. The controller withheld the mixed foreground transcript, so the mutation-check claims could not be independently confirmed.; The unit run skipped the opt-in headless live smoke. The documented foreground demonstrations used real Codex with simulated GitHub.

#### Summary

- **Delivered behavior:** Interactive enrollment selects foreground development. The review command returns authenticated feedback, reviewer and gate output are visible during execution, and numbered amendment displays bind a fresh report to the updated task. The scoped record connects an accepted review to corrections by the same Claude session.
- **Scope reviewed:** The complete unamended foreground-development mission for PR #7, all eight pending dispositions and the affected watch, recovery, reviewer admission and instruction-display paths.
- **Pending later-phase work:** none
- **Unresolved questions:** none
- **Remaining owner review:** If the controller accepts this review, R2-F4 reaches the configured three-review no-progress threshold. The owner decides whether to resume within the existing budget.; After a corrected handoff, the owner judges the interactive experience and decides whether to merge draft PR #7.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `max` | `max` (turns ['max']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Owner guidance bound to this review: none.

Owner amendments bound to this review: none.

Codex CLI `0.170.0`, thread `01a204f0-301b-7f43-91bf-54c97916b8e9`, duration 595.4s, response sha256 `6324ede72ad0c96603c80d23087b39fd2bf82272f6283c7d6bed86e26ed08806`, request `devproc-claude-foreground-development-20261122110938-f02a-r04-570e59`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "8c233d0c2940065d2555e9d02d857a096cd5852d",
  "checkpoint_id": "final",
  "checkpoint_type": "final",
  "decision": "changes_required",
  "decision_rationale": "The required unit gate passed, and seven of eight pending fixes are verified. Watch can still write into a linked worktree\u2019s Git records and report a false stall. Two foreground failure paths can leave a stale blocker or publish a private transcript filename.\n\n## Continuation for Claude\n\nProtect both Git directories used by a linked worktree before opening a watch log. Track the arrival of event records separately from the last action displayed. After a capped amendment\u2019s queued publication succeeds, restore the budget as the current blocker. Keep transcript filenames in local diagnostics when a reviewer launch is refused.\n\nExercise these four paths with temporary Git repositories, real controller state and the existing model and GitHub fixtures. Run the required unit gate on the corrected commit through the pinned controller. Keep the existing enrollment, model policy, review budget and owner handoff boundary.",
  "evidence_assessment": {
    "executed_verification": [
      "The controller receipt binds the required unit command to 8c233d0c2940065d2555e9d02d857a096cd5852d. It records exit 0, an unchanged worktree and 908.8 seconds. The matching log records 290 tests, OK with one skipped, including all seven ForegroundRoundThreeTests.",
      "Read-only Git and hash checks confirmed HEAD, the merge base, the enrolled mission digest and the gate-log digest. The controller file matches the SHA-256 in section 5 of the interface record. Only that evidence document changed after b81d2fe.",
      "Git reported distinct per-worktree and common Git directories for this detached snapshot."
    ],
    "inspected": [
      "The mission, repository instructions, operating guide, protocol, full feature diff and correction diff from 2cc19f7.",
      "The developer report, all eight pending ledger entries, candidate-bound unit receipt and log, and the foreground transcript withholding notice.",
      "The foreground behavior tests and planning/evidence/pr-7-foreground-cycle.md, including the correction cycle, pre-exit output, amendment demonstrations and PR #6 outcome."
    ],
    "limitations": [
      "This read-only review used the supplied gate evidence. The real-interface observations come from the scoped developer record. The controller withheld the mixed foreground transcript, so the mutation-check claims could not be independently confirmed.",
      "The unit run skipped the opt-in headless live smoke. The documented foreground demonstrations used real Codex with simulated GitHub."
    ],
    "required_gaps": [
      "A corrected-candidate unit receipt covering linked-worktree log protection, the budget status after publication recovery, public transcript-read diagnostics and watch timing after filtered events."
    ],
    "source_inspection_only": [
      "Traced watch log admission through the Git directory lookup and append operation, and watch timing from event parsing through the stall message.",
      "Traced a failed PR-body edit through guarded and the next capped resume, and a transcript read error through require_foreground_launcher and public status publication. These failure combinations were identified from source."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "Part A, Existing running jobs",
        "Part A.3"
      ],
      "actual": "watch_log_problem protects the per-worktree Git directory only when its lookup succeeds. It suppresses lookup errors, leaving the linked worktree\u2019s ownership marker outside the remaining protected roots. Even on success, the common Git directory holding the enrolled branch\u2019s refs and reflogs is outside the check. The regression fixture uses an ordinary clone whose .git directory is already inside its worktree.",
      "blocking_rationale": "An observer can append its feed to an ownership record or the enrolled branch\u2019s Git metadata. Either can interfere with the job being watched.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "File output is admitted only after the controller establishes that its destination is separate from the enrolled worktree\u2019s Git and ownership records.",
      "id": "R2-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 5986
      },
      "priority": "P2",
      "requested_correction": "Protect the per-worktree and common Git directories. Refuse optional file output when the protected locations cannot be established. Keep console observation available.",
      "requested_evidence": "Use a real linked worktree with separate state and Git directories. Verify refusal for a destination in shared Git metadata and for the ownership marker when Git-directory lookup fails. Check that protected files remain byte-identical and that a separate log works.",
      "title": "Watch log protection is incomplete for linked worktrees",
      "trigger": "An operator selects a Git metadata path as the log for a linked worktree, or the observing shell cannot resolve that worktree\u2019s Git directory."
    },
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.2",
        "Part B.5"
      ],
      "actual": "A failed queued PR-body edit reaches guarded, which saves PAUSED with the publication error. On the next ordinary resume, settle_publications completes the edit, then the exhausted-budget branch raises UsageError. The saved status and reason still describe the resolved outage.",
      "blocking_rationale": "The owner can recover the public correction and still be told by status and watch that publication is the outstanding problem. The actual decision needed is whether to extend the review budget.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Once publication recovers, the enrollment reports BLOCKED with the exhausted budget and applied amendment as its current reason.",
      "id": "R4-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 4188
      },
      "priority": "P2",
      "requested_correction": "After successful settlement, restore the capped amendment\u2019s durable blocker and make the public status consistent. Preserve publication failures while they are outstanding and keep replay idempotent.",
      "requested_evidence": "Fail the queued PR-body edit once after amending a handed-off final round. Recover with the original limit and inspect status, the public notices and the PR body. Repeat recovery and verify stable counters, closed admission and no duplicate correction.",
      "title": "Successful publication recovery can leave a stale PAUSED reason at the cap",
      "trigger": "The amendment has consumed the last available round and GitHub temporarily fails while the controller publishes its handoff correction."
    },
    {
      "acceptance_ids": [
        "Part A.5",
        "Part A, private evidence",
        "Protocol \u00a78"
      ],
      "actual": "require_foreground_launcher embeds the full filesystem exception in a Stop. guarded therefore publishes the Stop reason directly. Its filesystem-error handling, which limits the public diagnostic to the error type and errno, only applies when it receives an OSError. A transcript filename outside the home directory survives publication sanitization.",
      "blocking_rationale": "A private transcript location can enter the PR discussion and its archived records during an ordinary read failure.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The launch stays closed. Local status carries the diagnosis needed for recovery, and the PR receives the documented filesystem-error summary.",
      "id": "R4-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3012
      },
      "priority": "P2",
      "requested_correction": "Preserve the distinction between the local diagnostic and the publishable reason when transcript access fails at reviewer admission. Keep the persisted policy stop for an observed model, effort or permission mismatch.",
      "requested_evidence": "Have the transcript read fail before a retry with a distinctive fixture filename. Verify the local diagnosis, the public comment\u2019s error type and omission of the filename, and the unchanged reviewer-call and round counts.",
      "title": "A reviewer retry can publish the private transcript filename",
      "trigger": "The enrolled session\u2019s transcript becomes unreadable when the controller checks provenance before a fresh reviewer attempt."
    },
    {
      "acceptance_ids": [
        "Part A, Existing running jobs",
        "Part A.3",
        "Part B.5"
      ],
      "actual": "The watcher updates its activity time only for records that render a row. With no such row it measures silence from the attempt start, even when a complete record just arrived. On first attachment it also selects the last 15 raw records before rendering, so it can miss the latest command and report that no action has been observed.",
      "blocking_rationale": "The live view can tell the owner that no events have arrived for the entire stall interval while the current stream is receiving records.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The watcher accurately distinguishes event arrival, the latest displayable action and elapsed time without exposing reasoning content.",
      "id": "R4-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 5964
      },
      "priority": "P2",
      "requested_correction": "Track the last complete event for the current invocation or attempt separately from its last rendered action. On attachment, recover the latest displayable action even when later records are filtered.",
      "requested_evidence": "Attach to an aged attempt with a visible command followed by more than 15 filtered records. Append a fresh metadata event and check the reported action and silence interval. Then advance through a genuinely quiet interval and verify the stall notice.",
      "title": "Watch can report a stall immediately after an event arrives",
      "trigger": "A running developer or reviewer emits records whose content is intentionally omitted from the live view."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F3",
      "rationale": "Actions are keyed by developer invocation or reviewer round and attempt. The passing retry fixture distinguishes both attempts and labels a live gate PID as identity unconfirmed. R4-F3 concerns the separate calculation of event silence."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F4",
      "rationale": "The hard-link and host-claim checks pass. The ownership marker remains writable through the optional log when Git-directory discovery fails for a linked worktree. The ordinary-clone fixture cannot detect that omission."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F5",
      "rationale": "Part selection now counts JSON-escaped width. The unit fixture checks the complete displays and missing-part refusal. The matching-code interface record reports displays of 9,614, 9,614 and 4,513 bytes, refusal before part 3 and admission after its display."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R3-F1",
      "rationale": "After the specified interruption immediately following the amendment save, ordinary resume settles the public corrections at the original limit. The candidate fixture verified two replays, closed admission and unchanged counters. R4-F1 concerns the status left by an intervening publication error."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R3-F2",
      "rationale": "Headless dispatch resolves the PATH-selected executable before recording launch intent or charging the invocation. The fixture exercised run and resume with a simulated lookup failure and observed zero charges and no launch record."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R3-F3",
      "rationale": "Every automatic attempt now checks current foreground provenance. The passing test changed effort after the first retryable failure and observed BLOCKED, one reviewer call and zero completed rounds."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R3-F4",
      "rationale": "The status dispatcher compares the requested enrollment ID before rendering either instruction form. Both CLI calls in the misdirected-claim fixture refused without exposing the other amendment or its marker."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R3-F5",
      "rationale": "The watch dispatcher closes the optional log in a finally block. The candidate test verified a readable feed and observed no ResourceWarning after collection."
    }
  ],
  "request_id": "devproc-claude-foreground-development-20261122110938-f02a-r04-570e59",
  "round": 4,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "Interactive enrollment selects foreground development. The review command returns authenticated feedback, reviewer and gate output are visible during execution, and numbered amendment displays bind a fresh report to the updated task. The scoped record connects an accepted review to corrections by the same Claude session.",
    "pending_later_phase_work": [],
    "remaining_owner_review": [
      "If the controller accepts this review, R2-F4 reaches the configured three-review no-progress threshold. The owner decides whether to resume within the existing budget.",
      "After a corrected handoff, the owner judges the interactive experience and decides whether to merge draft PR #7."
    ],
    "scope_reviewed": "The complete unamended foreground-development mission for PR #7, all eight pending dispositions and the affected watch, recovery, reviewer admission and instruction-display paths.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
