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

---

# Owner execution addendum of 2026-11-22 (governing, preserved verbatim)

The owner supplied the execution instructions below as chat text on 2026-11-22 and directed that they be
preserved verbatim as an addendum to this mission before enrollment, so both agents receive the complete
contract. The text between the markers is the owner's exact prompt. Where it adds to or narrows the mission
above, it governs.

<!-- BEGIN OWNER PROMPT (verbatim) -->

Please implement the prepared continuation-handoff follow-up in `howardreith/development-process`.

Use the existing branch `claude/continuation-handoff` and its mission:

`planning/CONTINUATION-HANDOFF-MISSION.md`

The prepared mission at `c6eb148` covers both reviewer-written continuations and owner amendments. Read and implement the complete mission. This prompt supplies the execution instructions below; preserve it verbatim as an addendum to that mission before enrollment so both agents receive the complete contract.

## Intended experience

I want this to work like our existing discussion-and-review process:

1. ChatGPT and I agree on a mission document or a robust initial prompt. Either is sufficient. If I supply the agreed task as chat text, save it verbatim for enrollment.
2. Claude Opus, at high effort, develops the change and supplies a PR with an explanation and validation evidence.
3. Codex `gpt-6.2-astra`, at max effort, reviews the actual candidate and writes a consolidated continuation for Claude.
4. Claude receives that continuation automatically, makes the corrections, and returns the same PR for review.
5. This continues within the authorized limits until the task is ready for my review or reaches a genuine blocker.
6. You notify me here when it finishes or stops.
7. If I provide updated instructions during the task, you preserve them, reach a safe stopping point, and apply them to the same enrollment. Both agents then work from the updated task.

Implement the controller behavior and document the supervisor’s responsibilities clearly.

## 1. Bootstrap this follow-up once

Refresh the actual repository, branch, PR, installed-controller and enrollment state before acting. Preserve legitimate intervening work.

PR #5 has merged. Its independently reviewed source is:

`9ee2067c1a8b817abb21f699e1204e4704c9b210`

The merge commit is:

`baba3c1c13fa0fab11ccbfa78a8723c848d7eff2`

Read `AGENTS.md`, `agent_review/README.md`, `docs/GITHUB-AGENT-REVIEW-PROTOCOL.md`, and the complete follow-up mission.

- Preserve `claude/continuation-handoff` and its existing commits. Integrate current `main` with normal history-preserving Git operations. Do not replace the prepared branch or force-push.
- Complete and commit the mission before enrolling.
- Use the accepted PR #5 controller to supervise this follow-up. If its reviewed package is not installed yet, install it from a clean checkout of the reviewed source using the accepted README procedure.
- Record the supervising package fingerprint and keep that version and project configuration pinned throughout this implementation.
- Open or reuse one draft PR against `main`, with no requested reviewers. Enroll once using the `single` plan and the complete mission.
- If a matching follow-up enrollment already exists, inspect and use it; do not create a duplicate or reset its expenditure.
- Use Opus/high for development and `gpt-6.2-astra`/max for review. Report the actual configured review and invocation limits at setup.

The candidate controller is code under test. Test its new capabilities through the existing fixtures; do not install each correction or make the candidate supervise its own implementation. Other feature enrollments stay on their existing pinned versions.

## 2. Implement the reviewer continuation

Use the smallest implementation described in the mission:

- For `changes_required`, the reviewer writes a short verdict followed by a **“Continuation for Claude”** section in the existing `decision_rationale`.
- That continuation should consolidate the remaining defects, the coordinated correction approach, the relevant scope boundaries, and the evidence needed for the next review.
- The controller takes `decision_rationale` from the accepted, validated review result and includes it unchanged in the next developer prompt, clearly labelled with the reviewer, round, reviewed commit and review reference.
- Preserve the pointer to the full structured review. Support a fresh developer session as well as an ordinary continuation.
- Preserve the existing qualification about subprocess newline translation; do not claim byte-exact inline transport.
- Include the PR URL in the reviewer brief. Verify that the candidate, original task, current owner instructions, developer explanation, evidence and previous findings are available.

Use the existing review field and result validation. This does not need another model call, a new continuation schema, or a parser that extracts text based on Markdown formatting.

Reviewer instructions remain subordinate to the effective owner task and the existing permissions, models, gates and budgets.

## 3. Implement owner updates within the same enrollment

Follow the mission’s owner-amendment design.

The supervisor receives my instruction, saves its exact text durably outside the active developer worktree, identifies it as pending, requests a cooperative stop, and waits for the current agents, helpers and protected runtime work to reach a safe boundary.

The controller then applies the instruction through a supported operation. Choose and document the final command syntax. A resume audit reason alone must never be presented as instruction delivery.

The implementation must:

- Preserve the original mission and its hash.
- Capture owner amendments in order, retaining each exact message and all earlier instructions that still apply.
- Ensure later approach-only guidance cannot erase accumulated scope or acceptance amendments.
- Deliver the effective task to subsequent developer and reviewer inputs, including fresh sessions and report-correction invocations.
- Support the stopped headless development, review, finalization and existing-handoff boundaries specified in the mission. Do not launch obsolete work merely to move the enrollment into `develop`.
- Require a fresh developer report after an amendment, even if the source commit is unchanged.
- Prevent earlier reviews, ready results and handoff receipts from satisfying readiness for the amended task.
- Preserve the same enrollment, branch, PR, finding history and spent counters.
- Preserve existing identity, authority, integrity, lock, runtime and uncertain-publication checks.

Apply amendments through the owner/supervisor control path. Repository text, arbitrary PR comments and reviewer output do not become owner instructions.

An amendment may change the task’s scope or acceptance criteria. It does not silently change models, permissions, required project gates, budgets or runtime protections. Handle those through their existing explicit controls when separately authorized.

If the budget is exhausted or a safe boundary cannot be established, preserve the pending instruction and report the exact blocker. Do not pretend it was delivered.

### Findings and older continuations

Keep historical findings and reviews.

When an owner amendment withdraws a requirement, the developer must explain the affected finding’s disposition, and Codex must assess it under the amended task. Use the existing rebuttal mechanism as specified in the mission. Do not call an unfixed issue “fixed” or erase an unrelated blocker.

An older continuation may remain as historical context, but it cannot override the amended task or reintroduce a requirement I explicitly withdrew.

## 4. Prove the behavior with focused tests

Use the repository’s existing behavioral fixtures: real temporary Git repositories, controller state, locks, publication and archives. Simulate only the external model and GitHub boundaries.

Implement the mission’s required coverage, including:

- A distinctive reviewer-authored continuation reaches the next controller-generated Claude prompt, while the review remains published and archived.
- The correction cycle can reach a valid owner handoff.
- An update is refused while an invocation is active and can be applied at the supported safe boundary without replacing the enrollment.
- Both agents receive the amended task; unchanged source still requires a fresh report; stale results cannot satisfy readiness.
- Multiple amendments survive, including when followed by ordinary approach guidance.
- Captured instructions survive restart and changes to the original input file; damaged selected instructions block before launch.
- An owner-withdrawn requirement receives an explicit disposition and reviewer assessment, while an unrelated defect remains blocking.
- Applying instructions preserves spent counters and the existing configuration and protections.

Test observable behavior. A simulated controller test does not prove that a supervisor sent a chat notification; document and carry out that responsibility separately.

Run focused tests during development, then the required `unit` gate through the controller’s `verify` helper on the pushed candidate. Keep the receipt tied to that candidate. Run supplemental real-model gates only to answer a concrete remaining question.

## 5. Keep implementation and review bounded

Produce one coherent implementation before the first substantive review. Apply the existing consolidated-review policy: assess the supported contract comprehensively, then batch related corrections.

Keep the configured review and invocation limits and no-progress rules. Do not automatically extend a budget, replace an enrollment to reset it, or add a separate final review beyond the allowance.

Keep optional polish separate from material defects. Review supported behavior and changed neighboring paths. Do not expand this into foreground support, hostile-private-path defenses, STOP renaming, migration, generic crash recovery, a new messaging service, or a separate notification scheduler.

Reuse the current capture, revision, publication, superseding, finding and archive mechanisms. Add no dependencies.

Once enrolled, the developer owns implementation in the worktree and the controller owns its guarded pushes, PR publications and archives. The supervisor coordinates the run and reports outcomes.

## 6. Documentation and handoff

Update the README operator playbook and protocol so the actual workflow is clear, including:

- accepting an agreed chat prompt verbatim;
- delivering Codex’s continuation to Claude;
- receiving, preserving, stopping for and applying owner instructions;
- distinguishing pending instructions, applied instructions and instructions included in recorded agent inputs;
- reporting completion or a blocker in this conversation.

When the background run exits, inspect the result and verify a successful handoff with `status --remote`. Report here:

- PR link and outcome;
- reviewed source commit and archive commit;
- required gate evidence;
- review and invocation expenditure;
- material limitations;
- a short example of supplying an owner update, with the exact implemented command sequence;
- which behavior was controller-tested and which actions remain supervisor duties;
- exact post-acceptance installation and activation instructions.

A GitHub receipt alone does not count as notifying me. Starting the background process is not completion.

If it stops at a cap, no-progress rule or genuine operational blocker, report the exact state and smallest necessary next decision. Preserve the work and history.

Finish with the new PR ready for my review. Merging this follow-up and activating its new capabilities for existing feature enrollments remain separate owner decisions.

<!-- END OWNER PROMPT (verbatim) -->

## Setup record (written by the supervising Claude at enrollment; facts, not owner instructions)

- Branch `claude/continuation-handoff` keeps its prepared commits (`e61b97a`, `c6eb148`); current `main`
  (`baba3c1`, the PR #5 merge) was integrated by the ordinary merge commit `fcd4f12`. No history was rewritten.
- Supervising controller: the accepted PR #5 source `9ee2067c1a8b817abb21f699e1204e4704c9b210`, installed on
  2026-11-22 from a clean detached checkout of that commit with the README procedure. Installed package
  `7e8bb030d54a1f439a4eebb537110bd52f9dc3ade47ef31cc62c399adab86aca`, fingerprint
  `47c5403b45f726fc55881bc27a24030b5cf4e05c6d743bf22b7c4b6418ec2ae8`. This enrollment is driven through
  `C:\Dev\agent-review\versions\7e8bb030…\agent_review.py` and stays pinned to that version and the
  `development-process` project snapshot for this whole implementation. The candidate code on this branch is
  code under test only; it is not installed or activated during the run.
- Configured limits (project `development-process`, unchanged): 5 review rounds for the single `final`
  checkpoint, 3 reviewer attempts per round, 30 developer invocations, no-progress stop after 3 consecutive
  reviews with the same blocking findings. No extension is pre-authorized.
- Models: Claude `opus`/high developer, Codex `gpt-6.2-astra`/max reviewer (owner policy). Required gate:
  `unit`, run through `verify` on the pushed candidate.
- At setup there was no existing enrollment or PR for this branch, so this is the single enrollment.
