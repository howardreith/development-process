# Mission: reviewer-authored continuation handoff (follow-up to PR #5)

Status: **recorded follow-up, not enrolled.** Owner decision of 2026-11-22. Enroll only after PR #5
(`resume --guidance`) is merged or the owner decides otherwise; branch from the then-current `main`. It was
deliberately not added to the running PR #5 closeout: that enrollment's mission is hash-pinned, its pinned
controller (`34fb8529`) has no channel to deliver new instructions to a running developer, and the owner ruled
out another cancel/re-enroll cycle for this clarification.

## Acceptance target: the owner's user experience

The workflow must produce this familiar sequence: agreed task → Claude's PR and explanation → Codex's review and
continuation → Claude's corrections → repeat → owner notification and final review.

1. **Agreed task as input.** Howie and ChatGPT agree either a mission document or a robust initial prompt. Either
   is accepted. If it is supplied as chat text, the supervising Claude saves that agreed prompt **verbatim** as
   the enrollment's mission file. No further formal document is required, and the supervisor does not silently
   expand its scope.
2. **Claude develops.** Claude Opus/high develops on a draft PR and supplies an explanation, validation results
   and relevant evidence. The controller may create the PR and publish on Claude's behalf through the existing
   guarded mechanisms.
3. **Codex reviews the actual change.** Codex `gpt-6.2-astra`/max receives the PR URL, the exact candidate commit
   and source snapshot, the original instructions, owner guidance, Claude's explanation, evidence, and prior
   findings, and reviews the actual changes against the agreed task.
4. **Codex writes the continuation.** When changes are required, Codex itself writes a consolidated
   **"Continuation for Claude"**: what remains wrong, the coordinated correction approach, relevant scope
   boundaries, and the evidence needed for the next review. The detailed structured findings are preserved as
   well.
5. **Claude continues automatically.** Claude receives that continuation automatically, addresses or rebuts the
   findings with evidence, updates the same PR, and returns it to Codex. Normal correction rounds do not require
   Howie to relay messages or approve each iteration.
6. **Owner notification.** At `AWAITING_OWNER_REVIEW`, the supervising Claude observes the background task's
   terminal result, verifies the handoff with `status --remote`, and notifies Howie in the conversation that
   launched the task: PR link, reviewed commit, outcome, material limitations, remaining owner action. A GitHub
   receipt alone is not proof that Howie was notified. A BLOCKED or PAUSED outcome is reported accurately
   instead.

Items 1 and 6 are supervisor operating rules (already adopted by the supervising Claude on 2026-11-22). This
mission documents them in the README operator playbook and protocol; it does not automate them.

## Implementation (smallest change)

- **Reviewer prompt** (`prompts/reviewer.md`): when the decision is `changes_required`, `decision_rationale`
  starts with a short verdict explanation followed by a section headed `Continuation for Claude` containing the
  four elements of item 4. No schema change, no new field and no extra model call. The reviewer's continuation is
  subordinate to the owner's mission, permissions, models and budgets, and the prompt says so.
- **Developer continuation prompt** (`prompts/developer-continue.md`, and `developer-start.md` for a fresh
  session): when `develop_context` is `findings`, the controller places the accepted round's `decision_rationale`
  verbatim in the prompt, under a clear label naming the reviewer, the round, the reviewed commit and the review
  comment, plus a statement that it cannot change the mission, permissions, models, budgets or finding status. The
  existing pointer to the full structured review stays. Use the accepted, validated envelope; the supervisor does
  not rewrite the text.
- **Reviewer inputs:** add the PR URL to the reviewer brief (it currently names only the PR number). Verify that
  the other item-3 inputs are already present; add none that already exist.
- **Docs:** README operator playbook and protocol section 10: items 1 and 6, and the continuation path.
- No new messaging protocol, service, dependency, queue or acknowledgement schema. Budgets, no-progress
  accounting and stable finding IDs are unchanged.

## Required behavior test

Use the existing fixtures: real temporary Git repositories, real controller state, locks, publication and
archive. Stub only the Claude, Codex and GitHub boundaries.

1. A simulated Codex review returns `changes_required` with a distinctive `Continuation for Claude` text in
   `decision_rationale`.
2. The next real controller-generated developer prompt contains that same text, labelled.
3. The review is published on the (simulated) PR and archived.
4. A subsequent ready result reaches the owner handoff (`AWAITING_OWNER_REVIEW`).

Required gate: `unit` through `verify` on the pushed candidate. Install and activation remain owner decisions
between runs.
