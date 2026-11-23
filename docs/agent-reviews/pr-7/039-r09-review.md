<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r09-review part=1/1 sha256=2cf4b282010a16055f81ea9ca6e199841dcc47a69eff7fa1b21b2d0d01e74376 -->
### Codex GPT-6.2 Astra — review — round 9 — candidate `ca06b995dd`

**Decision:** `changes_required` — All three round-eight fixes are verified, and the required unit gate passed. Three defects remain. Status recovery uses inconsistent publication-integrity checks. A continuing watch can replay old activity as fresh, and its status line can identify a candidate as reviewed even when no reviewer launched.

## Continuation for Claude

Keep the correction within status-notice reuse and watch output. After checking comment order against acknowledged IDs, apply the controller's existing marker, uniqueness and normalized-body checks to the selected notice. When watch falls back to a round that had already ended at attachment, label its existing events as historical. Describe a saved review request according to whether a review actually ran or was accepted.

Extend the existing delayed-notice and failed-launch fixtures, including one watch that stays attached across the failure. Preserve the enrolled controller, admission rules, budgets and owner handoff. Run the required unit gate on the corrected candidate.

#### Findings

**R9-F1** · P2 · defect · blocks readiness — Status-notice reuse disagrees with publication reconciliation
- Location: `agent_review/agent_review.py:2789`; acceptance: Part A.4, Part B.2, Protocol §7
- Trigger: A delayed BLOCKED notice posts last. Its public body is returned with CRLF line endings, or the complete listing contains a later expected-actor comment with a different ID that repeats its marker and changes the reason.
- Expected: Reuse the latest authenticated notice when its normalized body is intact. A competing copy of its marker must trigger a correction or an explicit integrity stop.
- Actual: The raw marker-plus-LF check rejects CRLF before body normalization runs, so recovery posts another BLOCKED notice. In the competing-copy case, the listing loop discards the unrecorded ID and can clear restore_needed despite the visible conflict. The existing publication_problems check handles both distinctions.
- Why it blocks / does not: Recovery can issue a redundant public correction or declare the public blocker restored while two comments bearing its marker give conflicting reasons.
- Requested correction: Use the established publication-integrity comparison on the same listing after checking chronology. Preserve the recorded ID, expected actor, complete marker and outbox digest checks.
- Requested evidence: Extend the delayed BLOCKED fixture with a CRLF-only body and a second expected-actor copy carrying the same marker and a different reason. Verify reuse in the first case, correction or an integrity stop in the second, and stable results on another resume.

**R9-F2** · P2 · defect · blocks readiness — A continuing watch can replay a finished round as live activity
- Location: `agent_review/agent_review.py:6014`; acceptance: Part A, Existing running jobs, Part A.3, Part B.5
- Trigger: Watch attaches after a replacement attempt is saved as open and before its stream setup fails. A previous round already has completed reviewer events.
- Expected: Show the earlier round's bounded historical tail and the current blocker. Preserve the age distinction between pre-existing output and events that arrive during the watch.
- Actual: The first poll selects the open replacement round. After the failure, selection falls back to the earlier round for the first time. follow() classifies history solely by whether this is poll zero, so it emits the earlier file's rows without the historical label and timestamps its last action as just observed.
- Why it blocks / does not: The owner can see a burst of apparent reviewer progress during a failed launch even though every displayed action predates the watch.
- Requested correction: Recognize streams belonging to attempts already finished when watch attached, including streams first selected on a later poll. Keep observation-time attribution for genuinely new events.
- Requested evidence: Keep one watcher running while an open replacement attempt closes with launched=false. Leave the previous round's event file untouched. Verify that its action is labeled earlier, the status reports it as predating attachment, and the launch blocker remains visible.

**R9-F3** · P2 · defect · blocks readiness — Watch labels an unlaunched candidate as last reviewed
- Location: `agent_review/agent_review.py:6134`; acceptance: Part A, Existing running jobs, Part B.5
- Trigger: A review request records H, but its first attempt fails during setup before any reviewer process starts.
- Expected: Identify the candidate as requested and show its actual review state. A last-reviewed candidate must have review evidence.
- Actual: The status line always takes 'last reviewed' from the newest round's H. In the existing first-attempt stream-failure fixture it therefore prints the candidate as last reviewed alongside zero completed rounds and a blocker stating that no reviewer launched.
- Why it blocks / does not: The owner-facing status makes a false claim about which source received independent review.
- Requested correction: Label the newest round as a request, or derive the last reviewed candidate and verdict from an accepted round. Represent the absence of a completed review explicitly.
- Requested evidence: Extend the existing zero-dispatch fixture to check the candidate and verdict text on the status line. Also check that a later unlaunched request cannot be presented as the previous accepted review.

#### Prior finding assessments

- **R8-F1** — `fix_verified` — An acknowledged PAUSED ID missing from the listing prevents reuse of the older BLOCKED notice. The passing fixture restores the public budget reason and verifies stable comment and round counts after visibility returns.
- **R8-F2** — `fix_verified` — Changing the reason on the recorded comment while retaining its ID, author and marker now produces a distinct intact correction. The edited comment is preserved, and the intact LF control is reused. R9-F1 concerns normalized-equivalent text and competing copies.
- **R8-F3** — `fix_verified` — Attempts explicitly closed with launched=false are excluded from execution selection, event-file reads and time comparison. The candidate gate covers both directory faults, older records without the flag and a genuinely open attempt. R9-F2 and R9-F3 concern how the resulting history is displayed.

#### Evidence assessment

- **Inspected:** The enrolled mission and hash, fixed request, repository instructions, protocol, full feature diff, correction diff from d73f96a, developer report and prior-findings ledger.; The publication queue, reconciliation, status restoration, reviewer-attempt records, watch loop and their behavior fixtures.; The scoped foreground-cycle record, including earlier interface observations of pre-exit output, same-session continuation, amendment delivery and stale-report refusal.
- **Executed verification:** The controller's unit receipt names the exact candidate, exit code 0 and an unchanged worktree. Its log reports 318 tests run with one skipped in 989.277 seconds. I verified the log SHA-256 against the receipt.; The candidate log records passes for all ten integrated acceptance cases, including the omitted PAUSED ID, edited and intact BLOCKED bodies, both stream-directory failures, retained older attempts and an open attempt without events.; In a read-only text comparison using an archived PR #6 BLOCKED notice, converting LF to CRLF preserved the marker line and normalized body. The candidate's literal marker-plus-LF prefix matched only the LF representation.
- **Source inspection only:** I traced the effects of the status-reuse predicate and both watch defects through the production code. The supplied gate does not exercise those specific outcomes.
- **Required gaps:** Candidate-bound unit evidence for normalized and competing status comments, a continuing watch across a pre-launch failure, and the review identity displayed for an unlaunched request.
- **Limitations:** The foreground tool transcript is withheld. The candidate-bound gate confirms the integrated tests. The standalone bundle and mutation runs are documented in developer-authored excerpts.; The correction tests use real temporary Git repositories and controller state with simulated GitHub and model boundaries. The actual-interface demonstrations used earlier identified revisions. The supplemental live-model smoke was skipped on this candidate.

#### Summary

- **Delivered behavior:** Interactive enrollment selects and verifies the foreground Claude session. The session receives accepted Astra feedback and owner amendments, and the controller exposes gate and reviewer activity while preserving receipts and review accounting.
- **Scope reviewed:** The complete final mission for PR #7, with correction-round inspection focused on capped-amendment publication recovery and the activity reported around failed reviewer launches.
- **Pending later-phase work:** none
- **Unresolved questions:** none
- **Remaining owner review:** After a current handoff, assess the foreground conversation and live progress display and decide whether to merge draft PR #7.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `max` | `max` (turns ['max']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Owner guidance bound to this review: none.

Owner amendments bound to this review: none.

Codex CLI `0.170.0`, thread `01a20634-5bdc-70f3-bfe7-bc3f3dbde0e2`, duration 699.7s, response sha256 `7c3fa9204cfcc6a4c1b46908ad589026b5710e4b46bf73af219e7ebe7779b7f1`, request `devproc-claude-foreground-development-20261122110938-f02a-r09-2ef4e5`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "ca06b995dd6043c1624e9e8280485581aa3bc4b0",
  "checkpoint_id": "final",
  "checkpoint_type": "final",
  "decision": "changes_required",
  "decision_rationale": "All three round-eight fixes are verified, and the required unit gate passed. Three defects remain. Status recovery uses inconsistent publication-integrity checks. A continuing watch can replay old activity as fresh, and its status line can identify a candidate as reviewed even when no reviewer launched.\n\n## Continuation for Claude\n\nKeep the correction within status-notice reuse and watch output. After checking comment order against acknowledged IDs, apply the controller's existing marker, uniqueness and normalized-body checks to the selected notice. When watch falls back to a round that had already ended at attachment, label its existing events as historical. Describe a saved review request according to whether a review actually ran or was accepted.\n\nExtend the existing delayed-notice and failed-launch fixtures, including one watch that stays attached across the failure. Preserve the enrolled controller, admission rules, budgets and owner handoff. Run the required unit gate on the corrected candidate.",
  "evidence_assessment": {
    "executed_verification": [
      "The controller's unit receipt names the exact candidate, exit code 0 and an unchanged worktree. Its log reports 318 tests run with one skipped in 989.277 seconds. I verified the log SHA-256 against the receipt.",
      "The candidate log records passes for all ten integrated acceptance cases, including the omitted PAUSED ID, edited and intact BLOCKED bodies, both stream-directory failures, retained older attempts and an open attempt without events.",
      "In a read-only text comparison using an archived PR #6 BLOCKED notice, converting LF to CRLF preserved the marker line and normalized body. The candidate's literal marker-plus-LF prefix matched only the LF representation."
    ],
    "inspected": [
      "The enrolled mission and hash, fixed request, repository instructions, protocol, full feature diff, correction diff from d73f96a, developer report and prior-findings ledger.",
      "The publication queue, reconciliation, status restoration, reviewer-attempt records, watch loop and their behavior fixtures.",
      "The scoped foreground-cycle record, including earlier interface observations of pre-exit output, same-session continuation, amendment delivery and stale-report refusal."
    ],
    "limitations": [
      "The foreground tool transcript is withheld. The candidate-bound gate confirms the integrated tests. The standalone bundle and mutation runs are documented in developer-authored excerpts.",
      "The correction tests use real temporary Git repositories and controller state with simulated GitHub and model boundaries. The actual-interface demonstrations used earlier identified revisions. The supplemental live-model smoke was skipped on this candidate."
    ],
    "required_gaps": [
      "Candidate-bound unit evidence for normalized and competing status comments, a continuing watch across a pre-launch failure, and the review identity displayed for an unlaunched request."
    ],
    "source_inspection_only": [
      "I traced the effects of the status-reuse predicate and both watch defects through the production code. The supplied gate does not exercise those specific outcomes."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.2",
        "Protocol \u00a77"
      ],
      "actual": "The raw marker-plus-LF check rejects CRLF before body normalization runs, so recovery posts another BLOCKED notice. In the competing-copy case, the listing loop discards the unrecorded ID and can clear restore_needed despite the visible conflict. The existing publication_problems check handles both distinctions.",
      "blocking_rationale": "Recovery can issue a redundant public correction or declare the public blocker restored while two comments bearing its marker give conflicting reasons.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Reuse the latest authenticated notice when its normalized body is intact. A competing copy of its marker must trigger a correction or an explicit integrity stop.",
      "id": "R9-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2789
      },
      "priority": "P2",
      "requested_correction": "Use the established publication-integrity comparison on the same listing after checking chronology. Preserve the recorded ID, expected actor, complete marker and outbox digest checks.",
      "requested_evidence": "Extend the delayed BLOCKED fixture with a CRLF-only body and a second expected-actor copy carrying the same marker and a different reason. Verify reuse in the first case, correction or an integrity stop in the second, and stable results on another resume.",
      "title": "Status-notice reuse disagrees with publication reconciliation",
      "trigger": "A delayed BLOCKED notice posts last. Its public body is returned with CRLF line endings, or the complete listing contains a later expected-actor comment with a different ID that repeats its marker and changes the reason."
    },
    {
      "acceptance_ids": [
        "Part A, Existing running jobs",
        "Part A.3",
        "Part B.5"
      ],
      "actual": "The first poll selects the open replacement round. After the failure, selection falls back to the earlier round for the first time. follow() classifies history solely by whether this is poll zero, so it emits the earlier file's rows without the historical label and timestamps its last action as just observed.",
      "blocking_rationale": "The owner can see a burst of apparent reviewer progress during a failed launch even though every displayed action predates the watch.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Show the earlier round's bounded historical tail and the current blocker. Preserve the age distinction between pre-existing output and events that arrive during the watch.",
      "id": "R9-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 6014
      },
      "priority": "P2",
      "requested_correction": "Recognize streams belonging to attempts already finished when watch attached, including streams first selected on a later poll. Keep observation-time attribution for genuinely new events.",
      "requested_evidence": "Keep one watcher running while an open replacement attempt closes with launched=false. Leave the previous round's event file untouched. Verify that its action is labeled earlier, the status reports it as predating attachment, and the launch blocker remains visible.",
      "title": "A continuing watch can replay a finished round as live activity",
      "trigger": "Watch attaches after a replacement attempt is saved as open and before its stream setup fails. A previous round already has completed reviewer events."
    },
    {
      "acceptance_ids": [
        "Part A, Existing running jobs",
        "Part B.5"
      ],
      "actual": "The status line always takes 'last reviewed' from the newest round's H. In the existing first-attempt stream-failure fixture it therefore prints the candidate as last reviewed alongside zero completed rounds and a blocker stating that no reviewer launched.",
      "blocking_rationale": "The owner-facing status makes a false claim about which source received independent review.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Identify the candidate as requested and show its actual review state. A last-reviewed candidate must have review evidence.",
      "id": "R9-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 6134
      },
      "priority": "P2",
      "requested_correction": "Label the newest round as a request, or derive the last reviewed candidate and verdict from an accepted round. Represent the absence of a completed review explicitly.",
      "requested_evidence": "Extend the existing zero-dispatch fixture to check the candidate and verdict text on the status line. Also check that a later unlaunched request cannot be presented as the previous accepted review.",
      "title": "Watch labels an unlaunched candidate as last reviewed",
      "trigger": "A review request records H, but its first attempt fails during setup before any reviewer process starts."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_verified",
      "finding_id": "R8-F1",
      "rationale": "An acknowledged PAUSED ID missing from the listing prevents reuse of the older BLOCKED notice. The passing fixture restores the public budget reason and verifies stable comment and round counts after visibility returns."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R8-F2",
      "rationale": "Changing the reason on the recorded comment while retaining its ID, author and marker now produces a distinct intact correction. The edited comment is preserved, and the intact LF control is reused. R9-F1 concerns normalized-equivalent text and competing copies."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R8-F3",
      "rationale": "Attempts explicitly closed with launched=false are excluded from execution selection, event-file reads and time comparison. The candidate gate covers both directory faults, older records without the flag and a genuinely open attempt. R9-F2 and R9-F3 concern how the resulting history is displayed."
    }
  ],
  "request_id": "devproc-claude-foreground-development-20261122110938-f02a-r09-2ef4e5",
  "round": 9,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "Interactive enrollment selects and verifies the foreground Claude session. The session receives accepted Astra feedback and owner amendments, and the controller exposes gate and reviewer activity while preserving receipts and review accounting.",
    "pending_later_phase_work": [],
    "remaining_owner_review": [
      "After a current handoff, assess the foreground conversation and live progress display and decide whether to merge draft PR #7."
    ],
    "scope_reviewed": "The complete final mission for PR #7, with correction-round inspection focused on capped-amendment publication recovery and the activity reported around failed reviewer launches.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
