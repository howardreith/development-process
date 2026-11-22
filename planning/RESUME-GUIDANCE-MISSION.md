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

## Owner addendum of 2026-11-22: narrow the design, keep the safety bar

The first enrollment of this branch stopped after three review rounds under the no-progress rule. Its
design had grown to about 670 controller lines: foreground support, STOP-file renaming and identity
tracking, transcript-turn detection, and guidance rechecks inside publication retries. Most open findings
were crash or race windows in that extra machinery.

The owner chose to narrow the design and re-enroll on the same PR and branch. This addendum supersedes
any broader reading of the requirements above. Simplify in new commits; never rewrite history. Remove
machinery that this design does not need.

1. **Headless only.** `--guidance` is refused, with a clear message and no state change, for
   foreground enrollments. Do not detect foreground turns or inspect transcripts.

2. **One supported state.** Accept guidance only when all of the following hold. Anything else is
   refused (exit code 4, no state change, no PR post, STOP untouched, no agent launched):
   - the enrollment is headless;
   - status is `BLOCKED` or `PAUSED`;
   - phase is `develop`;
   - there is no active review round or reviewer attempt;
   - the last developer launch has returned;
   - there are no pending or uncertain publications.

   Check these with the existing locks held, together with the existing identity, workflow, mission and
   snapshot checks.

3. **Validate before mutating.** Before anything changes:
   - read the file;
   - require nonempty, non-whitespace content that is valid UTF-8;
   - compute the sha256 of the exact bytes.

   Every validation failure is a usage refusal raised before any write. Guided resume otherwise behaves
   exactly like the existing `resume`, including its existing STOP-file handling. Add no new STOP
   semantics.

4. **Content-addressed capture.**
   - Write the bytes to `<state dir>/guidance/<sha256>.md` with the controller's existing atomic-write
     helper. Writing is idempotent: identical content yields the same file and no new revision.
   - Only after the file exists, record the revision in `state.json` in the same save as the resume
     transition. Record its sha256, its revision number, when it was captured and the original path, for
     information only.
   - An earlier revision's file is never removed or overwritten.
   - If the save fails, the unreferenced file is harmless.
   - The private state directory is in the same trust domain as `state.json`. Add no special defenses
     against links or junctions inside it beyond what the existing state writes already do.

5. **Integrity at use.**
   - Immediately before composing a developer prompt, and before a reviewer attempt record is opened,
     re-read the selected snapshot and verify its sha256.
   - If the file is missing or its digest is wrong, stop BLOCKED with a clear reason before any launch,
     and leave no unfinished attempt record.
   - If guidance revisions exist but the selection is missing or invalid (including an explicit null),
     stop BLOCKED. Never fall back silently to unguided.
   - State with no guidance key at all is an unguided legacy enrollment and behaves exactly as before.

6. **Delivery.**
   - The developer prompt (start and continuation) includes the guidance text inline, under a heading
     that names the digest and revision. The digest identifies the captured bytes. Newline handling by
     the existing prompt transport is acceptable and out of scope.
   - The reviewer receives a byte-exact copy inside the existing reserved inputs folder, next to the
     mission. The reviewer prompt names that file and its digest.
   - The round's request record and its review envelope or archive record name the digest, or `none`.

7. **Freshness.**
   - Each review round records the guidance digest that applied.
   - Capturing a new revision invalidates the current report and any ready result, using the existing
     mechanism for a moved head (for example, `develop_context` `needs_report` and clearing
     `last_report_for` and `ready_review`).
   - Readiness and finalize require the ready review's digest to equal the current selection.
   - Historical rounds keep their recorded digest.
   - Publications carry already-rendered bodies. Add no guidance checks inside publication retries.

8. **Small diff.** Aim for a change that a reviewer can verify end to end. Remove the code for
   foreground guidance, STOP identity and renaming, transcript-turn detection, symlink and junction
   defenses for the staging file, and publication-retry rechecks, unless one of those is strictly
   required by points 1–7 above.

9. **Tests.** Keep the required behaviors listed under "Required tests", with foreground replaced by
   "foreground `--guidance` is refused". Remove tests for removed machinery.

10. **Review scope for the reviewer.** The following are out of scope unless this change makes existing
    behavior worse:
    - adversarial redirection inside the private state directory;
    - crash windows in the pre-existing STOP handling;
    - foreground mode;
    - newline translation in the existing prompt transport.

    The safety bar for the supported path itself is unchanged:
    - refusals change nothing;
    - capture is durable and content-addressed;
    - the guidance is never silently omitted;
    - freshness is bound to the guidance digest;
    - ordinary resume is unchanged.
