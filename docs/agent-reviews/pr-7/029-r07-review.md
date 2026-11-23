<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r07-review part=1/1 sha256=e4434725469291acd400c3b7473ca0ecce59c445aebf0614dea69bfad33b3c04 -->
### Codex GPT-6.2 Astra — review — round 7 — candidate `f393ca6b96`

**Decision:** `changes_required` — The required unit gate passed. Round-limit admission and local restoration of the budget blocker are fixed. Two publication paths can still leave the wrong status last on the PR, and `watch` can report an older developer action after a replacement review request is recorded.

## Continuation for Claude

Report this result for PR #7 and candidate `f393ca6` to the owner. The supplied record identifies round 7 as the last authorized round. Further work requires a separate owner decision.

If authorized, correct the ordering of cap-related status notices and the selection of historical reviewer activity. Replay notices in their recorded sequence and account for which notice actually reached GitHub last before reusing a restoration notice. When a replacement round has no attempt, look back to the most recent recorded reviewer attempt. Keep live activity attributed to the current attempt.

Use the existing temporary Git and simulated GitHub fixtures for the three cases below. Check the actual order of PR comments after two recoveries, the watch output, helper admission and spent counters. Preserve authenticated publication, the atomic BLOCKED transition and the pinned enrollment. Run the required unit gate on the corrected candidate.

#### Findings

**R5-F3** · P2 · defect · blocks readiness — A replacement request hides the latest retained reviewer action
- Location: `agent_review/agent_review.py:6022`; acceptance: Part A, Existing running jobs, Part A.3, Part B.5
- Trigger: After failed headless reviewer attempts, an owner resumes at the same H with a changed merge base. The controller saves a replacement round and pauses while publishing its request, before opening an attempt.
- Expected: The watcher reports that no agent is running and identifies the preceding reviewer's recorded action as the latest observable activity.
- Actual: `watch` reads both attempt lists from `rounds[-1]` only. The replacement request has empty lists, while the preceding round holds the retained attempts. The time comparison therefore selects the older developer invocation and labels its action as latest.
- Why it blocks / does not: At a recovery stop, the owner receives an incorrect account of which agent acted most recently.
- Requested correction: When the current request has no attempts, include the most recent preceding round with recorded attempts in the historical comparison. Preserve the round and attempt numbers when reading its event file.
- Requested evidence: Extend the headless retry fixture by advancing the fixture target to an ancestor of H that changes the merge base. Fail publication of the replacement request and attach `watch --once`. Verify that the status shows the retained reviewer's note as historical and the replacement attempt has yet to start.

**R7-F1** · P2 · defect · blocks readiness — Recovery can leave PAUSED as the latest PR status after restoring BLOCKED locally
- Location: `agent_review/agent_review.py:4326`; acceptance: Part A.4, Part B.2, Protocol §§7, 10
- Trigger: The outage that prevents the restored BLOCKED notice from posting also prevents the following PAUSED notice from posting. Both are pending when GitHub recovers.
- Expected: After delivery settles, local state and the latest PR status both identify the applied amendment and exhausted budget. Repeated recovery preserves that result.
- Actual: On recovery, `settle_publications()` can send `status-8-blocked` followed by `status-9-paused`. The `reuse` check sees that the BLOCKED notice was pending at displacement and clears `restore_needed`. Local state returns to BLOCKED, but PAUSED is the last public notice and a second resume leaves it there.
- Why it blocks / does not: The PR directs the owner to resolve a publication outage after delivery has recovered. The decision actually needed is a budget extension.
- Requested correction: Base notice reuse on confirmed public order. If a later PAUSED notice is already visible, queue one durable BLOCKED correction. Preserve reconciliation of uncertain POSTs and reuse the existing notice when it can still serve as the final status.
- Requested evidence: In the failed-restored-notice fixture, reject all eight POST attempts across the BLOCKED and PAUSED notices, then recover twice at the original limit. Check the last public heading and reason, unique markers, empty pending queue, closed admission and stable launch and round counts.

**R7-F2** · P2 · defect · blocks readiness — Reload can reverse the reopening and budget-stop notices
- Location: `agent_review/agent_review.py:4947`; acceptance: Part A.4, Part B.2, Protocol §§7, 10
- Trigger: A foreground handoff is amended at the cap and the controller exits after saving the amendment, with the two queued status keys spanning a change in digit count.
- Expected: Replay publishes the handoff reopening before the subsequent budget stop, leaving BLOCKED as the latest status.
- Actual: With seven transitions at handoff, the amendment queues `status-7-reopened` and then `status-10-blocked`. State serialization sorts object keys. After reload, `settle_publications()` iterates those keys and sends BLOCKED first and REOPENED last. The local blocker was never displaced, so ordinary resume queues no correction.
- Why it blocks / does not: The latest PR notice says work has reopened while the enrollment requires an owner decision before development can continue.
- Requested correction: Use the persisted numeric publication sequence to order eligible pending notices across reloads. Retain the existing eligibility and authentication checks for each send.
- Requested evidence: Reach a three-round handoff at its cap, apply an amendment and interrupt immediately after the transaction saves. Resume twice and verify the public order REOPENED then BLOCKED, the corrected PR body, one comment per marker and unchanged counters.

#### Prior finding assessments

- **R5-F1** — `fix_verified` — The locked command path validates an explicit limit before rebinding, resend, handoff reopening or stop consumption. The candidate gate covers zero from PAUSED, an exhausted proposal with resend, a moved handoff and a due permission rebinding.
- **R5-F3** — `fix_rejected` — The dirty-worktree fixture now selects retained attempt 3 correctly while that round is still last. A resume that records a replacement request before it pauses hides those same retained attempts and reproduces the incorrect latest-action report.
- **R6-F1** — `fix_verified` — The command now saves the restoration marker together with the stop that displaces the local budget blocker. The candidate gate verifies local recovery after the replayed PR-body failure and the failed restored notice. R7-F1 concerns the new notice-reuse decision when the following PAUSED publication is also pending.

#### Evidence assessment

- **Inspected:** The mission, repository instructions, operating guide, protocol, feature diff, developer report and prior-findings ledger.; The resume and review command paths, state serialization, publication queue and reconciliation, watch history selection, corresponding fixtures and candidate gate artifacts.; The scoped foreground-cycle record in planning/evidence/pr-7-foreground-cycle.md, including the earlier live reviewer and gate observations, same-session corrections and amendment demonstrations.
- **Executed verification:** The controller receipt binds the required Windows unit gate to f393ca6b966aaafe5a740f0b5a43475ff0e2c06a. It records exit 0, an unchanged worktree and 307 tests run with one live-smoke skip. The supplied log's SHA-256 matches the receipt.; The gate log records all nine ForegroundRoundSevenTests passing, including the four limit-admission cases, four capped-amendment recovery cases and the retained-attempt watch case.; Read-only Git inspection confirmed the snapshot HEAD and the correction diff from f0f6330. The mission file's SHA-256 matches the enrolled digest.
- **Source inspection only:** The three remaining failure paths were traced through the candidate source. The passing fixtures cover a pause before replacement-round creation, a failure restricted to BLOCKED posts, and a one-round handoff.
- **Required gaps:** A passing watch observation after a replacement request is saved with no reviewer attempt.; Passing public-status observations after both status POSTs are deferred and after an interrupted amendment spans transition numbers 7 and 10.
- **Limitations:** The read-only snapshot permitted source and artifact inspection. The candidate gate receipt supplies the execution evidence for this round.; The controller withheld the mixed foreground session transcript. The real-interface demonstrations and pre-fix or mutation runs are documented in scoped excerpts. The real-model demonstrations exercised the earlier commits identified there.

#### Summary

- **Delivered behavior:** Interactive enrollment selects the foreground Claude session. The controller checks its recorded provenance, returns the accepted Astra continuation, streams reviewer and gate activity, and binds amended reports to observed delivery. Invalid resume limits are refused before they alter authorization.
- **Scope reviewed:** The complete foreground-development mission, with correction-round tracing focused on budget admission, capped-amendment publication recovery and retained reviewer history.
- **Pending later-phase work:** none
- **Unresolved questions:** none
- **Remaining owner review:** Decide whether to authorize further work beyond round 7 on draft PR #7. Final workflow acceptance and merge are owner decisions.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `max` | `max` (turns ['max']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Owner guidance bound to this review: none.

Owner amendments bound to this review: none.

Codex CLI `0.170.0`, thread `01a2059d-4600-7e12-9d1f-e86d53e24cd8`, duration 629.1s, response sha256 `9923cd845af63ace172b5e75101a858178453be6661895481db5d5e606cd07af`, request `devproc-claude-foreground-development-20261122110938-f02a-r07-1976e6`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "f393ca6b966aaafe5a740f0b5a43475ff0e2c06a",
  "checkpoint_id": "final",
  "checkpoint_type": "final",
  "decision": "changes_required",
  "decision_rationale": "The required unit gate passed. Round-limit admission and local restoration of the budget blocker are fixed. Two publication paths can still leave the wrong status last on the PR, and `watch` can report an older developer action after a replacement review request is recorded.\n\n## Continuation for Claude\n\nReport this result for PR #7 and candidate `f393ca6` to the owner. The supplied record identifies round 7 as the last authorized round. Further work requires a separate owner decision.\n\nIf authorized, correct the ordering of cap-related status notices and the selection of historical reviewer activity. Replay notices in their recorded sequence and account for which notice actually reached GitHub last before reusing a restoration notice. When a replacement round has no attempt, look back to the most recent recorded reviewer attempt. Keep live activity attributed to the current attempt.\n\nUse the existing temporary Git and simulated GitHub fixtures for the three cases below. Check the actual order of PR comments after two recoveries, the watch output, helper admission and spent counters. Preserve authenticated publication, the atomic BLOCKED transition and the pinned enrollment. Run the required unit gate on the corrected candidate.",
  "evidence_assessment": {
    "executed_verification": [
      "The controller receipt binds the required Windows unit gate to f393ca6b966aaafe5a740f0b5a43475ff0e2c06a. It records exit 0, an unchanged worktree and 307 tests run with one live-smoke skip. The supplied log's SHA-256 matches the receipt.",
      "The gate log records all nine ForegroundRoundSevenTests passing, including the four limit-admission cases, four capped-amendment recovery cases and the retained-attempt watch case.",
      "Read-only Git inspection confirmed the snapshot HEAD and the correction diff from f0f6330. The mission file's SHA-256 matches the enrolled digest."
    ],
    "inspected": [
      "The mission, repository instructions, operating guide, protocol, feature diff, developer report and prior-findings ledger.",
      "The resume and review command paths, state serialization, publication queue and reconciliation, watch history selection, corresponding fixtures and candidate gate artifacts.",
      "The scoped foreground-cycle record in planning/evidence/pr-7-foreground-cycle.md, including the earlier live reviewer and gate observations, same-session corrections and amendment demonstrations."
    ],
    "limitations": [
      "The read-only snapshot permitted source and artifact inspection. The candidate gate receipt supplies the execution evidence for this round.",
      "The controller withheld the mixed foreground session transcript. The real-interface demonstrations and pre-fix or mutation runs are documented in scoped excerpts. The real-model demonstrations exercised the earlier commits identified there."
    ],
    "required_gaps": [
      "A passing watch observation after a replacement request is saved with no reviewer attempt.",
      "Passing public-status observations after both status POSTs are deferred and after an interrupted amendment spans transition numbers 7 and 10."
    ],
    "source_inspection_only": [
      "The three remaining failure paths were traced through the candidate source. The passing fixtures cover a pause before replacement-round creation, a failure restricted to BLOCKED posts, and a one-round handoff."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "Part A, Existing running jobs",
        "Part A.3",
        "Part B.5"
      ],
      "actual": "`watch` reads both attempt lists from `rounds[-1]` only. The replacement request has empty lists, while the preceding round holds the retained attempts. The time comparison therefore selects the older developer invocation and labels its action as latest.",
      "blocking_rationale": "At a recovery stop, the owner receives an incorrect account of which agent acted most recently.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The watcher reports that no agent is running and identifies the preceding reviewer's recorded action as the latest observable activity.",
      "id": "R5-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 6022
      },
      "priority": "P2",
      "requested_correction": "When the current request has no attempts, include the most recent preceding round with recorded attempts in the historical comparison. Preserve the round and attempt numbers when reading its event file.",
      "requested_evidence": "Extend the headless retry fixture by advancing the fixture target to an ancestor of H that changes the merge base. Fail publication of the replacement request and attach `watch --once`. Verify that the status shows the retained reviewer's note as historical and the replacement attempt has yet to start.",
      "title": "A replacement request hides the latest retained reviewer action",
      "trigger": "After failed headless reviewer attempts, an owner resumes at the same H with a changed merge base. The controller saves a replacement round and pauses while publishing its request, before opening an attempt."
    },
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.2",
        "Protocol \u00a7\u00a77, 10"
      ],
      "actual": "On recovery, `settle_publications()` can send `status-8-blocked` followed by `status-9-paused`. The `reuse` check sees that the BLOCKED notice was pending at displacement and clears `restore_needed`. Local state returns to BLOCKED, but PAUSED is the last public notice and a second resume leaves it there.",
      "blocking_rationale": "The PR directs the owner to resolve a publication outage after delivery has recovered. The decision actually needed is a budget extension.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "After delivery settles, local state and the latest PR status both identify the applied amendment and exhausted budget. Repeated recovery preserves that result.",
      "id": "R7-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 4326
      },
      "priority": "P2",
      "requested_correction": "Base notice reuse on confirmed public order. If a later PAUSED notice is already visible, queue one durable BLOCKED correction. Preserve reconciliation of uncertain POSTs and reuse the existing notice when it can still serve as the final status.",
      "requested_evidence": "In the failed-restored-notice fixture, reject all eight POST attempts across the BLOCKED and PAUSED notices, then recover twice at the original limit. Check the last public heading and reason, unique markers, empty pending queue, closed admission and stable launch and round counts.",
      "title": "Recovery can leave PAUSED as the latest PR status after restoring BLOCKED locally",
      "trigger": "The outage that prevents the restored BLOCKED notice from posting also prevents the following PAUSED notice from posting. Both are pending when GitHub recovers."
    },
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.2",
        "Protocol \u00a7\u00a77, 10"
      ],
      "actual": "With seven transitions at handoff, the amendment queues `status-7-reopened` and then `status-10-blocked`. State serialization sorts object keys. After reload, `settle_publications()` iterates those keys and sends BLOCKED first and REOPENED last. The local blocker was never displaced, so ordinary resume queues no correction.",
      "blocking_rationale": "The latest PR notice says work has reopened while the enrollment requires an owner decision before development can continue.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Replay publishes the handoff reopening before the subsequent budget stop, leaving BLOCKED as the latest status.",
      "id": "R7-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 4947
      },
      "priority": "P2",
      "requested_correction": "Use the persisted numeric publication sequence to order eligible pending notices across reloads. Retain the existing eligibility and authentication checks for each send.",
      "requested_evidence": "Reach a three-round handoff at its cap, apply an amendment and interrupt immediately after the transaction saves. Resume twice and verify the public order REOPENED then BLOCKED, the corrected PR body, one comment per marker and unchanged counters.",
      "title": "Reload can reverse the reopening and budget-stop notices",
      "trigger": "A foreground handoff is amended at the cap and the controller exits after saving the amendment, with the two queued status keys spanning a change in digit count."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_verified",
      "finding_id": "R5-F1",
      "rationale": "The locked command path validates an explicit limit before rebinding, resend, handoff reopening or stop consumption. The candidate gate covers zero from PAUSED, an exhausted proposal with resend, a moved handoff and a due permission rebinding."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R5-F3",
      "rationale": "The dirty-worktree fixture now selects retained attempt 3 correctly while that round is still last. A resume that records a replacement request before it pauses hides those same retained attempts and reproduces the incorrect latest-action report."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R6-F1",
      "rationale": "The command now saves the restoration marker together with the stop that displaces the local budget blocker. The candidate gate verifies local recovery after the replayed PR-body failure and the failed restored notice. R7-F1 concerns the new notice-reuse decision when the following PAUSED publication is also pending."
    }
  ],
  "request_id": "devproc-claude-foreground-development-20261122110938-f02a-r07-1976e6",
  "round": 7,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "Interactive enrollment selects the foreground Claude session. The controller checks its recorded provenance, returns the accepted Astra continuation, streams reviewer and gate activity, and binds amended reports to observed delivery. Invalid resume limits are refused before they alter authorization.",
    "pending_later_phase_work": [],
    "remaining_owner_review": [
      "Decide whether to authorize further work beyond round 7 on draft PR #7. Final workflow acceptance and merge are owner decisions."
    ],
    "scope_reviewed": "The complete foreground-development mission, with correction-round tracing focused on budget admission, capped-amendment publication recovery and retained reviewer history.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
