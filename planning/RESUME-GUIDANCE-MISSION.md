# Mission: owner guidance on `resume` (`resume --guidance <file>`)

## Goal

Today an owner decision about *how* the work should proceed cannot reach the agents of an existing
enrollment. Three paths fall short:

- `resume --reason` is stored only in `status_reason` and the transition log.
- The resumed developer's continuation prompt is built from `develop_context` and the pending
  findings only.
- The mission is hash-pinned, and editing it blocks the enrollment until a cancel and re-enroll.

Add a small, bounded owner-guidance input to `resume`. It must deliver one captured instruction
document to both the developer and the reviewer of the same enrollment, without changing the
enrollment, mission, project configuration, developer session, budgets or findings.

The motivating case is an idle `BLOCKED` enrollment (no-progress stop) in the `develop` phase that
needs a changed repair approach before it spends another review round.

## Requirements

1. **Command.** `resume --guidance <file>` is accepted by the owner-initiated `resume` command.
   - The initial supported case is an idle `BLOCKED` or `PAUSED` enrollment in the `develop` phase.
     "Idle" means no active developer, no active reviewer attempt and no other lock holder.
   - In any other phase or status, `--guidance` is explicitly refused, with a clear message and a
     refusal exit code. It is never silently ignored.
   - `resume` without `--guidance` keeps its existing behavior exactly.

2. **Durable capture.**
   - Read the supplied document as UTF-8. Refuse an empty or whitespace-only document, an invalid
     encoding and a missing file.
   - Copy the document into the enrollment's private state directory and record the sha256 of its
     exact bytes.
   - Later edits to, or deletion of, the original file must not change the captured instructions.

3. **Delivery to both roles.**
   - Every developer invocation after capture, whether a start or a continuation prompt, contains
     the captured guidance, or an explicit reference to an in-state copy the developer is told to
     read, and identifies its digest.
   - The reviewer receives a copy inside its existing input snapshot (the reserved inputs folder).
     The reviewer prompt identifies it and its digest. The reviewer must not depend on any external
     Windows path.
   - Review records (the request, envelope and archived records) identify the guidance digest that
     applied, or "none".
   - Both prompts state that the guidance supplements the repair approach under the mission. It does
     not alter models, permissions, budgets, acceptance criteria or finding status.

4. **Persistence and revisions.**
   - The selected guidance persists across later developer invocations, review rounds, controller
     restarts and ordinary resumes without `--guidance`.
   - An explicit later `--guidance` with different content creates a new revision and preserves the
     earlier snapshot and digest in state.
   - Supplying content identical to the current revision creates no new revision.

5. **Review freshness.**
   - A changed guidance revision requires a fresh developer report before the next review, even when
     the candidate commit is unchanged.
   - The guidance identity is bound to the review inputs and to every check that accepts or reuses a
     review result. A ready, accepted or finalized result bound to different guidance, or to none,
     must not satisfy readiness for the current guidance.
   - Historical reviews keep their original binding. They do not silently acquire new guidance.

6. **Ownership and integrity.**
   - Guidance is accepted only through the owner-initiated `resume`, with the enrollment's existing
     host and worktree locks, identity, workflow-fingerprint, mission and snapshot checks satisfied.
   - All validation, including reading and hashing the input and checking state and phase, happens
     before anything changes. A refused call leaves state, the stop file and the counters untouched,
     and launches no agent.
   - Capture and the state change commit together in the existing transaction mechanism.
   - Before any developer or reviewer launch, verify that the captured snapshot is present and that
     its digest matches. If it is missing or altered, stop with a clear PAUSED or BLOCKED reason. It
     is never silently omitted.

7. **Scope limits.**
   - No natural-language validation of the guidance content.
   - No general messaging system.
   - No change to model policy, permissions, budgets, acceptance criteria or finding status.
   - Reuse the existing snapshot, transaction, prompt, outbox and archive mechanisms. Enrollments
     created before this change, and enrollments without guidance, stay fully backward compatible:
     their state loads, runs and archives unchanged.

8. **Existing resume semantics are preserved and tested.** The normal owner resume:
   - restarts the no-progress streak;
   - does not reset completed rounds, developer invocations or open and pending findings;
   - does not raise any budget.

9. **Documentation.** Document the option, its supported states, its revision and freshness rules,
   and its failure modes in `agent_review/README.md`. Add a short note to
   `docs/GITHUB-AGENT-REVIEW-PROTOCOL.md` if the protocol text needs it.

## Required tests

Add behavior tests to `agent_review/test_agent_review.py`. Use the existing real temporary Git
repositories and the real controller state, locks, transactions and archive. Stub only the Claude,
Codex and GitHub boundaries, with clearly labeled simulated responses. Do not test source text.

The tests must show that:

1. An eligible BLOCKED enrollment (for example, a no-progress stop) resumed with `--guidance`
   supplies the same captured guidance and digest to the developer prompt and to the reviewer's input
   snapshot and prompt, and the review record names the digest.
2. Restarting the controller, and editing or deleting the original file, does not change what later
   developer and reviewer invocations receive.
3. Changed guidance requires a fresh developer report on an unchanged commit. A review bound to
   different guidance cannot be reused for readiness. Identical content creates no new revision, and
   a replacement preserves the earlier snapshot.
4. Invalid input (missing, empty, non-UTF-8) and a damaged or missing captured snapshot fail without
   launching agents and without partial state changes. That includes no stop-file removal, no counter
   reset and no status change for refused input.
5. Ordinary resume without guidance is unchanged, both for enrollments that never had guidance and
   for state files written before this change.
6. Each of these is refused: a held lock, an unsupported phase or status (for example `review`,
   `finalize`, `AWAITING_OWNER_REVIEW` or `ACTIVE`), an exhausted budget, and a guidance call
   targeting another enrollment's state.
7. A normal owner resume from a no-progress block restarts the streak and leaves completed rounds,
   developer invocations and open findings unchanged.

Add a live smoke check only if it resolves a concrete remaining uncertainty that the unit tests
cannot.

## Constraints

- Python 3 standard library only. Follow `AGENTS.md`.
- **This branch changes the controller itself.** Do not install, `activate`, or run the candidate
  controller against any real enrollment. The review enrollment for this branch is driven by the
  pinned installed version. Test candidates only through the gates.
- The required validation is the project's `unit` gate, run through `verify` on the committed and
  pushed candidate.
- Do not merge or tag. The PR stays a draft.
