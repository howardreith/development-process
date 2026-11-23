<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r03-review part=1/1 sha256=f6c79a77904c30bb13c3aec820c3c421722f12ce692fb150aafc9c06eb068aa9 -->
### Codex GPT-6.2 Astra — review — round 3 — candidate `2cc19f7a03`

**Decision:** `changes_required` — The required unit gate passed, and nine of the twelve prior fixes are verified. An interrupted amendment can still leave a superseded handoff visible on the PR. A headless launch can also spend an invocation before Claude starts. Three prior findings remain open, and the new retry and instruction-display paths need corrections.

## Continuation for Claude

Let an owner resume finish an already-authorized public correction at the round cap while keeping development blocked. Resolve the executable before charging a headless launch, and check current foreground provenance before each fresh reviewer attempt. Preserve recovery of an intact review from the owner's shell.

Bind instruction output to the requested enrollment and size amendment parts by their serialized output. In watch, bind activity to the particular invocation or reviewer attempt and protect worktree files and enrollment claims when opening a log.

Exercise the failure paths in the findings with the existing Git and controller fixtures. Provide a scoped delivery observation for an escape-heavy UTF-8 amendment and run the required unit gate through verify on the pushed correction. Use this enrollment's pinned controller, model policy, permissions and budgets.

#### Findings

**R3-F1** · P1 · defect · blocks readiness — Recovery at the round cap can leave a superseded handoff visible
- Location: `agent_review/agent_review.py:4167`; acceptance: Part A.4, Part B.2
- Trigger: The controller exits after saving a foreground amendment at the cap and before posting its handoff correction.
- Expected: Recovery publishes the queued correction, blocked notice and PR status update while development stays blocked at the existing limit.
- Actual: The amendment transaction saves BLOCKED and queues the corrections. On restart, ordinary resume reaches the exhausted-budget refusal at line 4167 before it can settle those publications. The crash test recovers only by passing --max-rounds 2.
- Why it blocks / does not: The PR can continue to present a handoff that private state has already retired. Correcting the public record should not require authorization for another review round.
- Requested correction: Allow ordinary recovery to finish the amendment's authenticated pending publications and PR update at the cap. Keep the blocked state, counters and launch restrictions in force.
- Requested evidence: Interrupt after amending a handed-off enrollment on its last round. Resume with the original limit and verify the public correction and PR body, idempotent replay, unchanged counters, and closed helper and report admission.

**R3-F2** · P2 · defect · blocks readiness — A missing Claude executable consumes a headless invocation
- Location: `agent_review/agent_review.py:3876`; acceptance: Part A, existing headless operation, Part A, review limits and accounting
- Trigger: A supported headless project names its developer executable through PATH and the launching shell cannot resolve it.
- Expected: A known executable lookup failure is reported before the headless invocation is charged or recorded as outstanding.
- Actual: The new lazy executable property lets develop_step pass session_exists, increment developer.invocations and save an unreturned launch. ClaudeDeveloper.run then resolves the executable while building argv and raises UsageError. No child started, and a retry can spend another invocation.
- Why it blocks / does not: A configuration or PATH failure can exhaust the developer budget and leave a launch record that also prevents an owner amendment.
- Requested correction: Keep transcript observation independent of executable lookup. Prepare the executable on the headless dispatch path before saving the invocation charge and launch intent.
- Requested evidence: Run the headless command path with an unavailable executable name. Inspect persisted state after two refused attempts and verify the invocation count and previous launch record. Retain the foreground status and recovery coverage.

**R3-F3** · P2 · defect · blocks readiness — Automatic reviewer retries reuse an earlier foreground provenance check
- Location: `agent_review/agent_review.py:2971`; acceptance: Part A.2, Part A.5
- Trigger: The review command runs in the background and the interactive session's recorded policy changes before a retry.
- Expected: Each fresh reviewer dispatch uses current recorded provenance. An enrolled session with a policy mismatch receives the documented blocked outcome.
- Actual: review_round checks foreground provenance once before entering the attempt loop. After a nonfatal result, line 2971 can launch the next attempt with only a stop-file check. If a later command does detect mismatched provenance at the launcher guard, it raises UsageError and can leave the enrollment ACTIVE in review.
- Why it blocks / does not: A new reviewer process can start after the enrolled session has recorded an ineligible model, effort or permission mode. The documented blocked status is also missing on retry admission.
- Requested correction: Check the enrolled session's current provenance at each fresh attempt, including automatic retries. Distinguish an outside caller's refusal from a policy mismatch in the enrolled session. Preserve publication-only recovery.
- Requested evidence: Have the first simulated reviewer attempt return a retryable failure after the foreground transcript gains an ineligible turn. Verify that a second reviewer never starts, the round is uncharged and the command reports the policy blocker.

**R3-F4** · P1 · defect · blocks readiness — Instruction display can read a different enrollment's amendment
- Location: `agent_review/agent_review.py:6487`; acceptance: Part A.4, Part B.5
- Trigger: A stale registry claim points the requested enrollment at another valid state directory.
- Expected: The requested enrollment identity is checked before its owner instructions are displayed.
- Actual: The status dispatcher loads the directory returned by find_enrollment and calls effective_task or effective_task_part without comparing the loaded enrollment ID with args.enrollment. The response can contain the other job's amendment text and delivery marker.
- Why it blocks / does not: The newly documented part-reading command can deliver another task's private instructions into the current conversation.
- Requested correction: Check the requested ID against the loaded state before rendering either full or numbered instructions. Report a mismatch without emitting the unrelated document or marker.
- Requested evidence: Point one fixture claim at a different valid enrollment. Exercise status --instructions and its --part form through the CLI and verify that neither returns the other enrollment's content.

**R2-F3** · P2 · defect · blocks readiness — Watch can still attribute old activity to the current attempt
- Location: `agent_review/agent_review.py:5893`; acceptance: Part A, Existing running jobs
- Trigger: A reviewer retries before producing a displayable event, or an interrupted gate helper's PID is reused.
- Expected: Activity, elapsed time and liveness belong to the specific invocation, attempt or gate being reported.
- Actual: All reviewer attempts share actions['reviewer']. When a new attempt has only a start event, watch can assign the prior attempt's final action and age to it. Gate liveness also relies on pid_alive alone, so an unanswered marker can appear running after its PID is reused.
- Why it blocks / does not: The owner can see apparent activity or a stall for the wrong attempt, or a gate reported as running after its helper exited.
- Requested correction: Track actions by invocation and reviewer attempt. Report when the current attempt has produced no observable action. Corroborate a pending gate's helper identity or describe its liveness as unconfirmed.
- Requested evidence: Attach during a retry with an older completed attempt and no current action, then observe its first action. Include a stale gate marker whose PID belongs to an unrelated live fixture process.

**R2-F4** · P2 · defect · blocks readiness — Watch log protection misses worktree aliases and ownership records
- Location: `agent_review/agent_review.py:5960`; acceptance: Part A, Existing running jobs, Part A.3
- Trigger: The operator selects an existing destination outside the two checked directory paths that belongs to the enrollment.
- Expected: The optional watch log is separate from the selected enrollment's worktree and controller-owned records, including aliases.
- Actual: watch_log_problem rejects paths inside the state directory and worktree, but its same-file scan covers only the state directory. An external hard link to a worktree file passes. The enrollment's host registry claim also normally lives outside both protected roots and can be selected directly.
- Why it blocks / does not: The observer can alter the enrolled worktree or corrupt the claim needed to locate and operate the enrollment.
- Requested correction: Protect worktree file aliases and the enrollment's ownership records when validating the log destination. Verify the selected state identity before using it to authorize an output path.
- Requested evidence: Use an external hard link to a fixture worktree file and the fixture's host claim as log destinations. Verify refusal and byte-identical protected files, alongside successful output to a separate log.

**R2-F5** · P2 · evidence_gap · blocks readiness — The amendment part size does not bound the displayed JSON
- Location: `agent_review/agent_review.py:337`; acceptance: Part A.4, Part B.5
- Trigger: The selected amendment contains substantial non-ASCII text.
- Expected: Each required display fits the supported interface for the accepted UTF-8 input range, including text that expands when serialized.
- Actual: amendment_parts counts 8,000 source characters, while the CLI and transcript matcher use JSON's default ASCII escaping. A full slice of supplementary Unicode characters produces 96,000 ASCII characters before the response framing. The unit size assertion uses ASCII lines, and the interface record demonstrates outputs of about 8.9 KB.
- Why it blocks / does not: A valid amendment can supersede readiness and then require a single displayed result larger than the demonstrated interface capacity. Repeating that part offers the same oversized output.
- Requested correction: Select the single-result or multipart route and size each part against the serialized display, including framing. Keep the original document digest and complete-content check for every part.
- Requested evidence: Use a valid escape-heavy UTF-8 amendment. Record serialized output sizes and a scoped interface observation showing refusal with one part missing and successful admission after complete display.

**R3-F5** · P3 · optional_polish · non-blocking — The optional watch log is left to garbage collection
- Location: `agent_review/agent_review.py:6396`; acceptance: Part A.3
- Trigger: An in-process watch --once invocation opens a separate log and returns.
- Expected: The watch command closes its optional log when observation ends.
- Actual: The dispatcher opens the log without closing it explicitly. The candidate unit log records a ResourceWarning for the unclosed watch.log handle.
- Why it blocks / does not: The tested feed was flushed and readable. Deterministic closure is an optional cleanup for in-process callers.
- Requested correction: Scope the output handle to the watch invocation, including interruption and early return.
- Requested evidence: The existing watch-log test completes without the ResourceWarning.

#### Prior finding assessments

- **R1-F10** — `fix_verified` — The general setup, notification and amendment procedures now identify the foreground review/finalize sequence and the separate headless run/stop sequence. The guide also includes the requested PR #6 wording correction.
- **R1-F3** — `fix_verified` — An intact preserved envelope can be published by owner recovery. An invalidated envelope re-enters review_round and encounters the launcher guard. The fixture refused both outside caller cases and allowed the enrolled session to launch the replacement. R3-F3 concerns a later automatic attempt within one command.
- **R1-F4** — `fix_verified` — The amendment, retired handoff, counters and BLOCKED status are saved in one transaction before the helper lock is released. The interruption test confirmed closed helper and report admission. R3-F1 concerns replay of the public correction after that save.
- **R1-F5** — `fix_verified` — The production parser splits on physical LF, counts unreadable completed records and derives effort from real turns. The candidate gate exercised a literal Unicode separator, a malformed completed record, an incomplete tail and a synthetic-only message.
- **R1-F6** — `fix_verified` — Review and resume capture the baseline immediately after reloading under the writer lock. An unavailable baseline yields a null review. The early-stop tests preserved the counter and avoided a second acceptance line.
- **R2-F1** — `fix_verified` — Both event renderers sanitize complete text fields before shortening them, and watch caches rendered rows. The passing fixture checked the immediate feed, status summary and separate log with synthetic credential-shaped content.
- **R2-F2** — `fix_verified` — Both readers must record EOF for a complete capture. Display exceptions leave the evidence readers draining, and a capture problem prevents a passing receipt. The real subprocess fixture preserved all three output lines despite display failures.
- **R2-F3** — `fix_rejected` — Per-checkpoint counts and developer-versus-reviewer selection are corrected. The cache still combines separate attempts of the same role, and a live PID alone does not identify the gate helper.
- **R2-F4** — `fix_rejected` — Direct paths and a hard link to state.json are covered. The same-file check omits worktree files, and the host ownership claim is outside both protected roots.
- **R2-F5** — `fix_rejected` — The five-part demonstration covers missing-part refusal and successful delivery for its reference table. Source-character slicing leaves the displayed size of other supported UTF-8 inputs well above the verified range.
- **R2-F6** — `fix_verified` — Transcript reads no longer resolve the Claude executable. The candidate fixture recovered an intact verdict once and returned parseable remote handoff status with an unavailable executable name. R3-F2 covers the separate effect on headless dispatch.
- **R2-F7** — `fix_verified` — The watch dispatcher passes the selected ID and the observation loop checks it before following either private event stream. The wrong-directory fixture emitted a mismatch row with no job activity. R3-F4 concerns the instruction-display command.

#### Evidence assessment

- **Inspected:** AGENTS.md, the controller operating guide and behavioral protocol, the enrolled mission and request, the six-file feature diff, the correction since f04f135, and the affected controller and test paths.; The developer report, all twelve pending ledger entries, the foreground transcript withholding notice, the candidate-bound gate receipt and log, and planning/evidence/pr-7-foreground-cycle.md.
- **Executed verification:** The controller-run unit receipt names H, exit code 0, an unchanged worktree and 1098.7 seconds. Its log SHA-256 matches c700aa90822b4f4279c2787bd0adc756611ca72900afb1743f9c30e3c408e5ff. The log records 283 tests run, 282 passed and one opt-in live smoke skipped.; All nine ForegroundRoundTwoTests completed successfully. They include the early-stop baseline, preserved-envelope recovery, durable cap block, physical transcript delimiters, complete subprocess output despite display failure, and missing-part refusal.; Git confirms the requested HEAD and merge base. The controller source is identical at 97e3784 and H, and its SHA-256 matches the controller identified in section 4 of the interface evidence.
- **Source inspection only:** The public correction stranded behind the cap, the charge before executable lookup, the automatic retry after a provenance change, and the wrong-enrollment instruction display were identified by tracing production control flow.; The worktree hard-link case, activity inherited from another attempt, reused gate PID and Unicode output expansion follow from the source. The supplied tests exercise narrower cases.
- **Required gaps:** Demonstrate complete delivery for a valid UTF-8 amendment whose JSON representation expands substantially. The recorded five-part reference table establishes delivery for the text used in that demonstration.; Provide candidate-bound behavior evidence for publication recovery without a budget extension, headless prelaunch accounting, retry-time provenance, enrollment-bound instruction display, and the remaining watch cases.
- **Limitations:** This was a read-only review. The controller withheld the mixed foreground session transcript. The timed interface observations are a scoped developer-authored record, and GitHub was simulated in the isolated real-Codex fixture.; The packet independently confirms the required unit run. It contains no separate execution transcript for the reported mutation checks or precommit suite.

#### Summary

- **Delivered behavior:** Foreground enrollment verifies recorded session policy. The review command returns authenticated feedback on the exercised acceptance and recovery paths. The scoped fixture record connects visible gate and reviewer activity to same-session corrections and a fresh handoff under a demonstrated amendment.
- **Scope reviewed:** The final foreground-development mission at H, including the complete feature diff, the round-two corrections and their directly affected consumers. The enrolled mission has no owner amendments.
- **Pending later-phase work:** none
- **Unresolved questions:** none
- **Remaining owner review:** After a current final handoff, judge the experience in the main Claude conversation and decide whether to merge draft PR #7.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `max` | `max` (turns ['max']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Owner guidance bound to this review: none.

Owner amendments bound to this review: none.

Codex CLI `0.170.0`, thread `01a204bb-6b06-75a0-b676-79ae376f3a3c`, duration 794.0s, response sha256 `55f5d24a9605d3b4903c4604ee6ccf9a45f8df1392abfd751893b6d4a2540bf1`, request `devproc-claude-foreground-development-20261122110938-f02a-r03-432c48`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "2cc19f7a035974332e2d72113ffa6c13ccb84a69",
  "checkpoint_id": "final",
  "checkpoint_type": "final",
  "decision": "changes_required",
  "decision_rationale": "The required unit gate passed, and nine of the twelve prior fixes are verified. An interrupted amendment can still leave a superseded handoff visible on the PR. A headless launch can also spend an invocation before Claude starts. Three prior findings remain open, and the new retry and instruction-display paths need corrections.\n\n## Continuation for Claude\n\nLet an owner resume finish an already-authorized public correction at the round cap while keeping development blocked. Resolve the executable before charging a headless launch, and check current foreground provenance before each fresh reviewer attempt. Preserve recovery of an intact review from the owner's shell.\n\nBind instruction output to the requested enrollment and size amendment parts by their serialized output. In watch, bind activity to the particular invocation or reviewer attempt and protect worktree files and enrollment claims when opening a log.\n\nExercise the failure paths in the findings with the existing Git and controller fixtures. Provide a scoped delivery observation for an escape-heavy UTF-8 amendment and run the required unit gate through verify on the pushed correction. Use this enrollment's pinned controller, model policy, permissions and budgets.",
  "evidence_assessment": {
    "executed_verification": [
      "The controller-run unit receipt names H, exit code 0, an unchanged worktree and 1098.7 seconds. Its log SHA-256 matches c700aa90822b4f4279c2787bd0adc756611ca72900afb1743f9c30e3c408e5ff. The log records 283 tests run, 282 passed and one opt-in live smoke skipped.",
      "All nine ForegroundRoundTwoTests completed successfully. They include the early-stop baseline, preserved-envelope recovery, durable cap block, physical transcript delimiters, complete subprocess output despite display failure, and missing-part refusal.",
      "Git confirms the requested HEAD and merge base. The controller source is identical at 97e3784 and H, and its SHA-256 matches the controller identified in section 4 of the interface evidence."
    ],
    "inspected": [
      "AGENTS.md, the controller operating guide and behavioral protocol, the enrolled mission and request, the six-file feature diff, the correction since f04f135, and the affected controller and test paths.",
      "The developer report, all twelve pending ledger entries, the foreground transcript withholding notice, the candidate-bound gate receipt and log, and planning/evidence/pr-7-foreground-cycle.md."
    ],
    "limitations": [
      "This was a read-only review. The controller withheld the mixed foreground session transcript. The timed interface observations are a scoped developer-authored record, and GitHub was simulated in the isolated real-Codex fixture.",
      "The packet independently confirms the required unit run. It contains no separate execution transcript for the reported mutation checks or precommit suite."
    ],
    "required_gaps": [
      "Demonstrate complete delivery for a valid UTF-8 amendment whose JSON representation expands substantially. The recorded five-part reference table establishes delivery for the text used in that demonstration.",
      "Provide candidate-bound behavior evidence for publication recovery without a budget extension, headless prelaunch accounting, retry-time provenance, enrollment-bound instruction display, and the remaining watch cases."
    ],
    "source_inspection_only": [
      "The public correction stranded behind the cap, the charge before executable lookup, the automatic retry after a provenance change, and the wrong-enrollment instruction display were identified by tracing production control flow.",
      "The worktree hard-link case, activity inherited from another attempt, reused gate PID and Unicode output expansion follow from the source. The supplied tests exercise narrower cases."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.2"
      ],
      "actual": "The amendment transaction saves BLOCKED and queues the corrections. On restart, ordinary resume reaches the exhausted-budget refusal at line 4167 before it can settle those publications. The crash test recovers only by passing --max-rounds 2.",
      "blocking_rationale": "The PR can continue to present a handoff that private state has already retired. Correcting the public record should not require authorization for another review round.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Recovery publishes the queued correction, blocked notice and PR status update while development stays blocked at the existing limit.",
      "id": "R3-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 4167
      },
      "priority": "P1",
      "requested_correction": "Allow ordinary recovery to finish the amendment's authenticated pending publications and PR update at the cap. Keep the blocked state, counters and launch restrictions in force.",
      "requested_evidence": "Interrupt after amending a handed-off enrollment on its last round. Resume with the original limit and verify the public correction and PR body, idempotent replay, unchanged counters, and closed helper and report admission.",
      "title": "Recovery at the round cap can leave a superseded handoff visible",
      "trigger": "The controller exits after saving a foreground amendment at the cap and before posting its handoff correction."
    },
    {
      "acceptance_ids": [
        "Part A, existing headless operation",
        "Part A, review limits and accounting"
      ],
      "actual": "The new lazy executable property lets develop_step pass session_exists, increment developer.invocations and save an unreturned launch. ClaudeDeveloper.run then resolves the executable while building argv and raises UsageError. No child started, and a retry can spend another invocation.",
      "blocking_rationale": "A configuration or PATH failure can exhaust the developer budget and leave a launch record that also prevents an owner amendment.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A known executable lookup failure is reported before the headless invocation is charged or recorded as outstanding.",
      "id": "R3-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3876
      },
      "priority": "P2",
      "requested_correction": "Keep transcript observation independent of executable lookup. Prepare the executable on the headless dispatch path before saving the invocation charge and launch intent.",
      "requested_evidence": "Run the headless command path with an unavailable executable name. Inspect persisted state after two refused attempts and verify the invocation count and previous launch record. Retain the foreground status and recovery coverage.",
      "title": "A missing Claude executable consumes a headless invocation",
      "trigger": "A supported headless project names its developer executable through PATH and the launching shell cannot resolve it."
    },
    {
      "acceptance_ids": [
        "Part A.2",
        "Part A.5"
      ],
      "actual": "review_round checks foreground provenance once before entering the attempt loop. After a nonfatal result, line 2971 can launch the next attempt with only a stop-file check. If a later command does detect mismatched provenance at the launcher guard, it raises UsageError and can leave the enrollment ACTIVE in review.",
      "blocking_rationale": "A new reviewer process can start after the enrolled session has recorded an ineligible model, effort or permission mode. The documented blocked status is also missing on retry admission.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Each fresh reviewer dispatch uses current recorded provenance. An enrolled session with a policy mismatch receives the documented blocked outcome.",
      "id": "R3-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2971
      },
      "priority": "P2",
      "requested_correction": "Check the enrolled session's current provenance at each fresh attempt, including automatic retries. Distinguish an outside caller's refusal from a policy mismatch in the enrolled session. Preserve publication-only recovery.",
      "requested_evidence": "Have the first simulated reviewer attempt return a retryable failure after the foreground transcript gains an ineligible turn. Verify that a second reviewer never starts, the round is uncharged and the command reports the policy blocker.",
      "title": "Automatic reviewer retries reuse an earlier foreground provenance check",
      "trigger": "The review command runs in the background and the interactive session's recorded policy changes before a retry."
    },
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.5"
      ],
      "actual": "The status dispatcher loads the directory returned by find_enrollment and calls effective_task or effective_task_part without comparing the loaded enrollment ID with args.enrollment. The response can contain the other job's amendment text and delivery marker.",
      "blocking_rationale": "The newly documented part-reading command can deliver another task's private instructions into the current conversation.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The requested enrollment identity is checked before its owner instructions are displayed.",
      "id": "R3-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 6487
      },
      "priority": "P1",
      "requested_correction": "Check the requested ID against the loaded state before rendering either full or numbered instructions. Report a mismatch without emitting the unrelated document or marker.",
      "requested_evidence": "Point one fixture claim at a different valid enrollment. Exercise status --instructions and its --part form through the CLI and verify that neither returns the other enrollment's content.",
      "title": "Instruction display can read a different enrollment's amendment",
      "trigger": "A stale registry claim points the requested enrollment at another valid state directory."
    },
    {
      "acceptance_ids": [
        "Part A, Existing running jobs"
      ],
      "actual": "All reviewer attempts share actions['reviewer']. When a new attempt has only a start event, watch can assign the prior attempt's final action and age to it. Gate liveness also relies on pid_alive alone, so an unanswered marker can appear running after its PID is reused.",
      "blocking_rationale": "The owner can see apparent activity or a stall for the wrong attempt, or a gate reported as running after its helper exited.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Activity, elapsed time and liveness belong to the specific invocation, attempt or gate being reported.",
      "id": "R2-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 5893
      },
      "priority": "P2",
      "requested_correction": "Track actions by invocation and reviewer attempt. Report when the current attempt has produced no observable action. Corroborate a pending gate's helper identity or describe its liveness as unconfirmed.",
      "requested_evidence": "Attach during a retry with an older completed attempt and no current action, then observe its first action. Include a stale gate marker whose PID belongs to an unrelated live fixture process.",
      "title": "Watch can still attribute old activity to the current attempt",
      "trigger": "A reviewer retries before producing a displayable event, or an interrupted gate helper's PID is reused."
    },
    {
      "acceptance_ids": [
        "Part A, Existing running jobs",
        "Part A.3"
      ],
      "actual": "watch_log_problem rejects paths inside the state directory and worktree, but its same-file scan covers only the state directory. An external hard link to a worktree file passes. The enrollment's host registry claim also normally lives outside both protected roots and can be selected directly.",
      "blocking_rationale": "The observer can alter the enrolled worktree or corrupt the claim needed to locate and operate the enrollment.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The optional watch log is separate from the selected enrollment's worktree and controller-owned records, including aliases.",
      "id": "R2-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 5960
      },
      "priority": "P2",
      "requested_correction": "Protect worktree file aliases and the enrollment's ownership records when validating the log destination. Verify the selected state identity before using it to authorize an output path.",
      "requested_evidence": "Use an external hard link to a fixture worktree file and the fixture's host claim as log destinations. Verify refusal and byte-identical protected files, alongside successful output to a separate log.",
      "title": "Watch log protection misses worktree aliases and ownership records",
      "trigger": "The operator selects an existing destination outside the two checked directory paths that belongs to the enrollment."
    },
    {
      "acceptance_ids": [
        "Part A.4",
        "Part B.5"
      ],
      "actual": "amendment_parts counts 8,000 source characters, while the CLI and transcript matcher use JSON's default ASCII escaping. A full slice of supplementary Unicode characters produces 96,000 ASCII characters before the response framing. The unit size assertion uses ASCII lines, and the interface record demonstrates outputs of about 8.9 KB.",
      "blocking_rationale": "A valid amendment can supersede readiness and then require a single displayed result larger than the demonstrated interface capacity. Repeating that part offers the same oversized output.",
      "blocks_readiness": true,
      "category": "evidence_gap",
      "expected": "Each required display fits the supported interface for the accepted UTF-8 input range, including text that expands when serialized.",
      "id": "R2-F5",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 337
      },
      "priority": "P2",
      "requested_correction": "Select the single-result or multipart route and size each part against the serialized display, including framing. Keep the original document digest and complete-content check for every part.",
      "requested_evidence": "Use a valid escape-heavy UTF-8 amendment. Record serialized output sizes and a scoped interface observation showing refusal with one part missing and successful admission after complete display.",
      "title": "The amendment part size does not bound the displayed JSON",
      "trigger": "The selected amendment contains substantial non-ASCII text."
    },
    {
      "acceptance_ids": [
        "Part A.3"
      ],
      "actual": "The dispatcher opens the log without closing it explicitly. The candidate unit log records a ResourceWarning for the unclosed watch.log handle.",
      "blocking_rationale": "The tested feed was flushed and readable. Deterministic closure is an optional cleanup for in-process callers.",
      "blocks_readiness": false,
      "category": "optional_polish",
      "expected": "The watch command closes its optional log when observation ends.",
      "id": "R3-F5",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 6396
      },
      "priority": "P3",
      "requested_correction": "Scope the output handle to the watch invocation, including interruption and early return.",
      "requested_evidence": "The existing watch-log test completes without the ResourceWarning.",
      "title": "The optional watch log is left to garbage collection",
      "trigger": "An in-process watch --once invocation opens a separate log and returns."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F10",
      "rationale": "The general setup, notification and amendment procedures now identify the foreground review/finalize sequence and the separate headless run/stop sequence. The guide also includes the requested PR #6 wording correction."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F3",
      "rationale": "An intact preserved envelope can be published by owner recovery. An invalidated envelope re-enters review_round and encounters the launcher guard. The fixture refused both outside caller cases and allowed the enrolled session to launch the replacement. R3-F3 concerns a later automatic attempt within one command."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F4",
      "rationale": "The amendment, retired handoff, counters and BLOCKED status are saved in one transaction before the helper lock is released. The interruption test confirmed closed helper and report admission. R3-F1 concerns replay of the public correction after that save."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F5",
      "rationale": "The production parser splits on physical LF, counts unreadable completed records and derives effort from real turns. The candidate gate exercised a literal Unicode separator, a malformed completed record, an incomplete tail and a synthetic-only message."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F6",
      "rationale": "Review and resume capture the baseline immediately after reloading under the writer lock. An unavailable baseline yields a null review. The early-stop tests preserved the counter and avoided a second acceptance line."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F1",
      "rationale": "Both event renderers sanitize complete text fields before shortening them, and watch caches rendered rows. The passing fixture checked the immediate feed, status summary and separate log with synthetic credential-shaped content."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F2",
      "rationale": "Both readers must record EOF for a complete capture. Display exceptions leave the evidence readers draining, and a capture problem prevents a passing receipt. The real subprocess fixture preserved all three output lines despite display failures."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F3",
      "rationale": "Per-checkpoint counts and developer-versus-reviewer selection are corrected. The cache still combines separate attempts of the same role, and a live PID alone does not identify the gate helper."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F4",
      "rationale": "Direct paths and a hard link to state.json are covered. The same-file check omits worktree files, and the host ownership claim is outside both protected roots."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F5",
      "rationale": "The five-part demonstration covers missing-part refusal and successful delivery for its reference table. Source-character slicing leaves the displayed size of other supported UTF-8 inputs well above the verified range."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F6",
      "rationale": "Transcript reads no longer resolve the Claude executable. The candidate fixture recovered an intact verdict once and returned parseable remote handoff status with an unavailable executable name. R3-F2 covers the separate effect on headless dispatch."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R2-F7",
      "rationale": "The watch dispatcher passes the selected ID and the observation loop checks it before following either private event stream. The wrong-directory fixture emitted a mismatch row with no job activity. R3-F4 concerns the instruction-display command."
    }
  ],
  "request_id": "devproc-claude-foreground-development-20261122110938-f02a-r03-432c48",
  "round": 3,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "Foreground enrollment verifies recorded session policy. The review command returns authenticated feedback on the exercised acceptance and recovery paths. The scoped fixture record connects visible gate and reviewer activity to same-session corrections and a fresh handoff under a demonstrated amendment.",
    "pending_later_phase_work": [],
    "remaining_owner_review": [
      "After a current final handoff, judge the experience in the main Claude conversation and decide whether to merge draft PR #7."
    ],
    "scope_reviewed": "The final foreground-development mission at H, including the complete feature diff, the round-two corrections and their directly affected consumers. The enrolled mission has no owner amendments.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
