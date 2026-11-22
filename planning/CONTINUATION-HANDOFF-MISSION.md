# Mission: reviewer continuation and owner-updated instructions (follow-up to PR #5)

Status: **recorded follow-up, not enrolled.** Owner decision of 2026-11-22. Enroll only after PR #5
(`resume --guidance`) is merged or the owner decides otherwise; branch from the then-current `main`. It was
deliberately not added to the running PR #5 closeout: that enrollment's mission is hash-pinned, its pinned
controller (`34fb8529`) has no channel to deliver new instructions to a running developer, and the owner ruled
out another cancel/re-enroll cycle for this clarification.

## Owner clarification: updated task instructions are supported work

The owner asked on 2026-11-22: "Seems like we ought to have a way to send updated instructions. Can we adjust the system to achieve this?"

This not-yet-enrolled mission now covers both reviewer-authored continuations and owner instruction updates. A later explicit owner decision may change the task's approach, scope or acceptance criteria while preserving the same enrollment, branch and PR. Keeping the controller version pinned does not require freezing the owner's task instructions forever. The original mission remains an immutable baseline; amendments are recorded separately. This changes the follow-up's contract, not the already-running PR #5 enrollment.

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

7. **Owner updates during a run.** Howie can give the supervising Claude updated instructions. The supervisor saves the exact instruction, requests a cooperative stop, waits for a safe boundary, applies a versioned owner amendment, and continues the same enrollment when the current authorization and budget permit. Both agents receive the updated task. No routine cancellation, replacement enrollment, manual mission-file editing, or repeated permission request is required.

Items 1 and 6 are supervisor operating rules (already adopted by the supervising Claude on 2026-11-22). Document them in the README operator playbook and protocol. For item 7, the supervisor coordinates the existing stop/background-completion/resume mechanisms; the controller implements safe amendment capture, application, delivery and freshness. Do not add an independent notification or scheduling service.

## A. Reviewer continuation (smallest change)

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

## B. Owner instruction updates

### Owner-facing behavior and delivery boundary

Receiving an update and applying it are separate events. The supervisor may receive an update at any time. It first saves the exact text durably outside the enrolled developer worktree and reports it as pending. It requests the existing cooperative stop and waits for the current developer/reviewer, helpers and runtime transactions to finish or restore. It then applies the update through a supported controller operation and continues automatically if already authorized and within budget.

Do not write into a running agent's prompt, claim it saw text that only the supervisor received, interrupt a native restoration, or treat a dead process as a successfully returned invocation. If the existing recovery machinery cannot establish a safe boundary, keep the saved instruction pending and report the exact blocker. Ordinary recovery remains the existing recovery procedure.

Use the PR #5 capture/revision machinery and the existing resume path. An explicit owner-amendment mode, for example `resume --guidance FILE --amend-mission`, is an acceptable small extension; choose and document the final syntax. That example is a proposed interface, not a claim that the current controller supports it. Preserve ordinary approach-only guidance and unguided behavior. The supervisor handles the commands; Howie should only need to supply the updated instruction.

### Effective task and authority

The effective task is the original agreed mission plus captured owner amendments in order. Later explicit owner decisions supersede conflicting earlier task requirements; requirements they do not change still apply. A reviewer continuation proposes corrections under that effective task and cannot amend it.

Later approach-only guidance must preserve all still-applicable owner amendments and cannot undo an amended scope or acceptance requirement. Reusing guidance storage must not make the latest approach document replace the effective task's amendment history.

Reuse a cumulative owner-addenda document: preserve each exact owner message in order, with a simple identifying label, and capture the complete document using the existing revision/digest mechanism. A second update must not silently discard the first update's still-applicable instructions. Keep earlier snapshots and the original mission/hash unchanged. No semantic merging engine, natural-language authorization classifier or new hash-chain protocol is required.

Use the owner/supervisor control path to apply amendments. Do not treat arbitrary repository content, PR comments or reviewer-generated text as an owner decision. Preserve the headless developer's restriction against changing its own controller state or permissions.

Task amendments may change scope and task acceptance. They do not silently change model settings, shell permissions, required project gates, budgets, runtime protections, repository identity or the target PR. Those remain the existing explicit configuration/control operations. A request that also needs one of those operations must be reported and handled through that operation under the owner's actual authorization.

### Apply at the next safe boundary, without re-enrollment

Support idle, stopped headless enrollments in `develop`, `review` and `finalize`, and an existing owner-review handoff on a still-open PR. Reuse existing identity checks, writer/helper locks, runtime checks and publication reconciliation. Do not require another developer invocation merely to move into `develop`. Refuse application while an agent/helper/runtime transaction is active, while delivery is genuinely uncertain, or when the enrollment/PR is no longer eligible. Retain the pending instruction in those cases.

After admission, capture/select the cumulative instruction revision and invalidate obsolete work using the existing state transaction and superseding mechanisms. Require a fresh developer report under the updated task, even on an unchanged source commit, and return to `develop`. Existing pending requests, accepted reviews, ready results and handoff receipts under the previous instruction revision must not satisfy current readiness. Preserve them as history, with the existing public superseding behavior when needed.

Keep the same enrollment, branch, PR, finding history, completed-round expenditure and invocation counts. Applying an update must not refund spent reviews or increase a cap. An exhausted budget still prevents further model work unless an existing explicit owner authorization allows its extension; the saved update is not lost or misrepresented as delivered.

The controller may stay pinned while its task-instruction revision changes. Apply this feature to a real enrollment only after the supporting controller version has been reviewed, installed and deliberately activated at a safe between-run boundary. Do not hot-reload implementation code.

### Both roles receive the same effective instructions

Provide the original mission and current captured owner-addenda document to every subsequent developer invocation, including a new session and report-correction invocation, and every reviewer. Clearly identify revision, digest and owner authority. Reuse the existing `(revision, digest)` bindings for reports, rounds, accepted envelopes and readiness; preserve the integrity-at-use checks and historical bindings from PR #5.

Make the precedence explicit in both prompts. A reviewer must evaluate the amended task, rather than continuing to enforce a requirement the owner has explicitly withdrawn. Unrelated requirements and still-applicable defects remain binding.

Reuse the existing public rendering, request, review, archive and status records. Distinguish pending with the supervisor, applied to the enrollment, and included in a recorded agent input. A captured file, a launch intent or a model's self-reported acknowledgement alone does not establish compliance. Keep PR-safe input and existing sanitization rules; no new redaction framework.

### Preserve findings while reassessing applicability

Do not automatically close findings when capturing an amendment. The developer gives a disposition for each pending finding, and Codex verifies it under the effective task.

Prefer the existing `rebutted` / `rebuttal_accepted` mechanism for a finding that was valid under an earlier revision but no longer applies because of a specific owner amendment. Clarify that meaning in the prompts: cite the amendment and explain which requirement changed. Preserve the original finding and assessments. Do not describe an unfixed issue as fixed or a valid historical finding as a false positive. The reviewer must verify that the amendment covers that finding and that the remaining supported behavior is sound. Still-applicable blocking defects cannot become optional just because an amendment exists. No new findings ledger is required.

## Required behavior tests

Use the existing fixtures: real temporary Git repositories, real controller state, locks, publication and
archive. Stub only the Claude, Codex and GitHub boundaries.

1. A simulated Codex review returns `changes_required` with a distinctive `Continuation for Claude` text in
   `decision_rationale`.
2. The next real controller-generated developer prompt contains that same text, labelled.
3. The review is published on the (simulated) PR and archived.
4. A subsequent ready result reaches the owner handoff (`AWAITING_OWNER_REVIEW`).

Add focused behavior coverage for owner updates using the same real-controller/Git fixtures:

1. Applying during an active invocation is refused without launching a second agent or changing the selected instructions. At the existing safe stopping boundary, application succeeds in the same enrollment. Document the supervisor's actual pending-file/stop/wait steps rather than claiming a simulated controller test proves chat delivery.
2. A task-scope amendment reaches both role inputs, retains the original mission, requires a fresh report on unchanged source, and prevents an earlier valid review/ready result from satisfying the amended task. Cover the stopped review/finalize and existing-handoff boundaries through the shared application path, with no obsolete model launch needed.
3. Two successive amendments retain earlier still-applicable instructions; amendment followed by ordinary approach guidance also retains the amended task. Restart and deletion/change of the original input file do not lose the captured task. Damaged selected instructions block before launch as under PR #5.
4. An owner-withdrawn requirement is resolved only through an explicit developer disposition and reviewer assessment citing that amendment; an unrelated defect remains blocking. Old findings, completed-round/invocation counters, models, permissions and required project gates remain intact.

Keep these focused on observable behavior. Do not resurrect PR #5's removed foreground, hostile-private-path, STOP-renaming or generic crash-recovery work. No new dependencies, daemon, message bus or general queue is required. The controller's existing single-writer and cooperative-stop model remains.

Required gate: `unit` through `verify` on the pushed candidate. Use focused tests during development and the required candidate gate after the coherent batch. Supplemental live-model gates need a concrete unanswered question. Keep the configured review allowance; no automatic extensions.

## Implementation sequence and handoff

Complete PR #5 under its existing contract and allowance. This branch is not yet enrolled, so its expanded mission can be recorded now without affecting that run. After PR #5 merges, integrate current main into this same follow-up branch with normal history-preserving Git operations, then enroll once against this complete mission. Preserve the existing continuation work; do not split this into another speculative infrastructure campaign.

The pinned reviewed controller supervises the follow-up. The candidate's new owner-amendment behavior is tested through fixtures; the developer does not need to amend its own live enrollment or activate an unreviewed candidate to implement it.

Finish at owner review with the PR link, reviewed source, archive commit, gate evidence, a short operational example of receiving and applying an update, and exact post-acceptance install/activation instructions. State which parts are controller-tested and which are the supervisor's operating duties. Install and activation remain owner decisions between runs. No merge, release, or activation of existing feature enrollments is part of this implementation handoff.

