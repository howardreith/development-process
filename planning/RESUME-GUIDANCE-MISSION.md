# Mission: owner guidance on `resume` (`resume --guidance <file>`)

## Read this first: how this document is organized and what governs

This file was consolidated on 2026-11-22 for the re-enrollment of branch `claude/resume-guidance` and draft
PR #5. It contains three parts, in order of precedence:

1. **Part A — Completion mission of 2026-11-22 (governing).** The complete owner contract for this closeout.
2. **Part B — Owner addendum of 2026-11-22 (governing, as narrowed by Part A).** The narrow supported path.
3. **Part C — Original mission of 2026-11-21 (historical background only).** Kept so earlier decisions and
   review references stay available. Where Part C describes the broader design (foreground guidance, STOP
   handling, "PAUSED or BLOCKED", exact inline bytes, the foreground variants of its required tests), Parts A
   and B replace it. Conflicting Part C text is **not** an acceptance criterion.

Appendix H lists the open findings of the previous enrollment, labelled with that enrollment so they cannot be
confused with this enrollment's round IDs.

### Previous enrollment and starting state (recorded by the supervising Claude at setup)

- Previous enrollment: `devproc-claude-resume-guidance-20261121200122-662b` (abbreviated `662b` below), same
  branch and PR, pinned controller package `34fb8529…` (fingerprint `17b66fac…`).
- It spent **3 review rounds** (round 1 on `abfbb7b`, round 2 on `d8fdf1c`, round 3 on `e071f50`, each
  `changes_required`) and was BLOCKED for no progress after round 3. The owner then resumed it unchanged; that
  resumed developer invocation (4) was found dead at 2026-11-22T05:33Z without returning a report.
- Its uncommitted worktree changes from invocation 4 were preserved, unreviewed, in the local branch
  `preserve/resume-guidance-662b-inv4-wip` (commit `38019dc`). **They are still present as uncommitted
  changes in this worktree at enrollment.** They extend STOP identity/renaming and foreground rechecks, which
  the addendum removes. Treat them as unreviewed scratch work: reconcile or discard them as part of your
  simplification batch. Do not commit them merely because they are present.
- `662b` was cancelled through the supported `cancel` command on 2026-11-22. Its best-effort CANCELLED status
  comment was not published (its guard refused because the mission file had changed after enrollment); the
  cancellation itself stands. Its state and public records are preserved.
- `662b` public history on PR #5: round 1
  [request](https://github.com/howardreith/development-process/pull/5#issuecomment-7072434413) /
  [review](https://github.com/howardreith/development-process/pull/5#issuecomment-7072583182) /
  [dispositions](https://github.com/howardreith/development-process/pull/5#issuecomment-7072905347);
  round 2 [request](https://github.com/howardreith/development-process/pull/5#issuecomment-7072905888) /
  [review](https://github.com/howardreith/development-process/pull/5#issuecomment-7073043079) /
  [dispositions](https://github.com/howardreith/development-process/pull/5#issuecomment-7073338972);
  round 3 [request](https://github.com/howardreith/development-process/pull/5#issuecomment-7073339513) /
  [review](https://github.com/howardreith/development-process/pull/5#issuecomment-7073484842);
  [no-progress stop](https://github.com/howardreith/development-process/pull/5#issuecomment-7073485351).
- **Budget for this enrollment:** 2 review rounds (`--max-rounds 2`), the remainder of a five-review closeout
  total. Round 1 here is the consolidated review of the finished simplification; round 2 is the only
  correction recheck. There is no automatic extension.

---

# Part A — Completion mission of 2026-11-22 (governing)

## A.0 Goal and endpoint

Finish development-process PR #5 on `claude/resume-guidance`. Deliver a small, coherent implementation that
lets the owner change the approach of a stopped headless run, sends the captured instruction to both agents,
and leaves a readable record on GitHub. Make the supervising Claude's operating instructions clear enough that
it uses this capability correctly and does not repeatedly restart an unchanged failing loop.

Claude Opus at high effort remains the developer and `gpt-6.2-astra` at max the independent reviewer. Preserve
the existing permissions, required validation, runtime protection, and owner merge boundary.

The endpoint is this existing draft PR at `AWAITING_OWNER_REVIEW`, with the reviewed source commit, archive
commit, validation evidence, and concrete installation/activation instructions. Do not merge, install the
candidate over the production launcher, activate it for a real enrollment, or resume the three feature
projects (Tabletop, Buff Planner, Mounted Combat) as part of this mission.

## A.1 Baseline and governing scope

The reviewed snapshot before this closeout was PR head `3cecfb58d3c8e3966b2e3f17e43a5bd552ed0d88` against
main `f449b0b3cf871558d108411f3b090a1654f80a54`. The latest implementation review was `662b` round 3 against
`e071f50f6987a03a607db63bbf9ec53d90ec875f`. Head `3cecfb5` added the owner's narrowing addendum (Part B); it
did not yet implement that simplification.

The narrow supported path of Part B governs. Part A adds the limited visibility and operator-policy
requirements below. Replace conflicting descriptions of the broader design in code, docs and tests; do not
retain them as additional acceptance criteria. GitHub's mergeability flag is not a review verdict.

## A.2 Setup (performed by the supervising Claude; recorded for both agents)

The supervising Claude owns setup; the enrolled developer owns implementation. The old controller could not
acquire a new mission through `resume --reason`, and editing a hash-pinned mission does not amend an
enrollment. The supervisor therefore stopped and cancelled `662b` through the supported procedure (see the
starting-state section above), committed this consolidated contract, and enrolled the same branch and PR once,
against it, using the existing reviewed installed controller, with one final closeout checkpoint. **The
candidate controller in this branch remains code under test; it is never installed or activated as its own
supervisor during this PR.** The earlier findings do not disappear because of the new enrollment.

### Closeout budget

Two further completed substantive review rounds beyond the three recorded in `662b`: a consolidated review of
the finished simplification, then at most one correction batch and recheck. This is a five-review total for
the closeout, not a reset. Existing bounded retries for failed service calls still apply; another substantive
correction cycle must not be disguised as a technical retry. Keep the developer invocation cap. No automatic
extension, second replacement enrollment, or extra "final handoff review" outside this allowance. A more
recent explicit owner budget decision takes precedence.

## A.3 Implement the narrow guidance path

### Admission

Accept `resume --guidance FILE` only for a **headless** enrollment that is `BLOCKED` or `PAUSED` in `develop`,
with no active review round or reviewer attempt, a returned last developer launch (or no launch yet), no
active developer/helper/runtime transaction, and no pending or uncertain publication or public operation.

Use the existing locks, enrollment identity/claims, workflow/mission checks, and budget checks. Refuse
unsupported states, foreground mode, exhausted budgets, a simultaneous budget change (`--max-rounds`), or
`--resend-undelivered`. Do not inspect foreground transcripts or invent a transition out of review or finalize
to admit guidance.

Read the bounded input before mutation; require valid UTF-8 and non-whitespace content, and hash its exact
bytes. Retain the existing size limit. Known input/setup failures, including malformed manifest or claim JSON,
produce the documented exit-4 refusal. Refusal leaves persisted state, STOP, counters and PR unchanged, with no
launch. A damaged or invalid existing guidance selection detected during guided admission is also refused
unchanged; supplying a new document is not a repair bypass. Do not catch arbitrary programming exceptions and
turn them into success.

### Capture, selection and use

Use the existing atomic-write pattern to create `<enrollment>/guidance/<full-sha256>.md`, adding a small
bytes-writing helper if needed. The current JSON helper must not serialize or transform the captured document.
Verify an already-existing content file before reusing it. Store the selection and resume transition in one
state save after the snapshot exists. A failed save may leave an unreferenced content file; it must not select
it. Earlier snapshot files are immutable.

Identical current content keeps the current revision. A → B → A reuses A's content file but creates selection
revisions 1, 2 and 3. Keep the existing inexpensive (revision, digest) freshness binding. Content identity and
the latest owner decision are different things.

On `run` or ordinary `resume`, before preparing each developer prompt and before opening a reviewer attempt,
verify the selected snapshot. A missing/altered file, invalid selection, or present-but-null `guidance` member
must stop BLOCKED before launch or invocation charge. This integrity-at-use stop is distinct from the unchanged
guided-admission refusal above. Only absence of the entire `guidance` key means a legacy unguided enrollment.
The explicit `guidance: null` case currently launches without guidance and needs a direct regression test.

Handle known filesystem failures while preparing reviewer inputs as a controlled operational failure, leaving
no unfinished attempt for a reviewer that never launched. Reuse the existing attempt bookkeeping; do not
redesign crash reconciliation. Distinguish admission refusal from a later integrity failure: the latter may
legitimately persist a BLOCKED status.

Do not automatically repair or overwrite a previously selected damaged snapshot. Document the existing
supervised recovery boundary, including restoring the identical captured bytes when appropriate; do not create
another repair transaction or migration system.

### Delivery and freshness

Include the guidance text, revision and digest in both start and continuation developer prompts, including
report-correction invocations. The digest identifies the captured bytes; existing subprocess newline
translation is acceptable. Remove claims that the inline transport is byte-exact.

Give the reviewer a byte-exact copy in its existing reserved inputs folder and name that file, revision and
digest in its brief. Preserve the current invocation, report, round, envelope and ready-result bindings. A
changed selection clears the current report/ready binding and requires a fresh developer report, even if the
source commit is unchanged. An otherwise valid stale review, including revision 1 after A → B → A, cannot
satisfy final readiness. Historical rounds retain their original bindings.

Guidance supplies the owner's approach within the enrolled mission. It does not change acceptance criteria,
close a finding, increase a budget, change models or permissions, or itself authorize a scope amendment.

### Remove the excluded machinery

Remove foreground guidance support and report extensions, transcript-turn detection, new STOP
identity/renaming logic, special adversarial link/junction/staging defenses in trusted private state, automatic
snapshot repair, and guidance integrity checks inside publication retries. Use the pre-existing STOP behavior.
Existing publication retries send their already-rendered bodies.

Remove tests and documentation whose sole purpose was the deleted mechanisms. Preserve ordinary foreground
operation and ordinary unguided resume. No new dependencies, services, schemas for model acknowledgements,
message queues, or general amendment APIs.

## A.4 Make intervention and delivery visible

Use existing records and publication/archive mechanisms for these additions:

- In the normal review request, include a clearly labeled, sanitized public rendering of the selected owner
  guidance, together with its revision and full captured-source digest. Freeze the rendering when preparing
  that round's inputs/body; retries must not re-read a mutable selection. Use existing sanitization and comment
  splitting. The archived request then preserves the conversation without a new synchronization mechanism.
- Explain in CLI help and the README that the public rendering is published on the PR, so authors must supply
  PR-safe guidance text. The captured-source digest identifies the private original bytes; sanitization can
  make the public rendering differ. Do not add the original input path or private state paths as publication
  metadata, or publish credentials/raw event logs. Use the existing checks and sanitizer; do not build or
  promise a general sensitive-information detector.
- Extend `status` only with a small computed summary from existing state: selected revision/digest/integrity,
  the latest developer invocation's guidance binding and recorded launch/return status, and the latest
  reviewer round/attempt's binding and recorded state. Show a missing or malformed selection as a problem,
  never as "none".
- Retain the binding in the normal request/review/archive records. Reuse existing invocation and round
  identifiers so the supervisor can verify which work was prepared under which instruction.

Use accurate language: "captured", "included in the invocation input", "launch recorded" and "returned" are
distinct observations. A saved file or launch intent alone does not prove delivery to a running process. An
acknowledgement in model-authored prose is not independent evidence that the model followed the instruction.
The reviewer still checks the resulting work.

These are additions to existing records, not a new acknowledgement protocol, delivery daemon or dashboard. Do
not add a separate GitHub publication prerequisite to guided admission.

## A.5 Close the previous findings against the actual new design

Maintain one compact disposition table (in the developer report and its PR record) with the old finding ID
(prefixed `662b/`), whether its behavior remains supported, the changed code, and evidence. Preserve the
previous review; do not retrospectively call a real old-design defect a false positive.

| `662b` round-3 item | Required treatment |
|---|---|
| 662b/R1-F2 | Keep controlled admission/setup refusal; remove the special hostile-private-path branch of the requirement. |
| 662b/R1-F7 | Fix null/invalid selection. Qualify the inline newline claim under the owner's explicit exclusion. |
| 662b/R1-F8 | Close known reviewer input-preparation failures as unlaunched. |
| 662b/R1-F6 | Remove automatic repair of selected snapshots; prove immutable content capture and selection. |
| 662b/R2-F3 | Remove the new STOP identity/renaming mechanism and retain baseline behavior. |
| 662b/R1-F5 and 662b/R3-F1 | Remove foreground guidance; test its refusal and preserve ordinary foreground operation. |
| 662b/R2-F4 | Use existing trusted-state writes; remove the extra staging-path defense framework. |
| 662b/R2-F5 | Remove guidance checks from publication retry paths; publish frozen bodies. |
| 662b/R3-F2 (optional documentation) | Explain no-progress recovery separately from an exhausted review budget. |

**Reviewer:** explicitly assess this disposition table even though the old IDs are not in this enrollment's
pending-findings array. Discuss that historical verification in your rationale/summary, labelling the IDs
`662b/…`. Your schema assessment entries must still match only this enrollment's actual pending findings (none
in round 1). Do not manufacture historical state or a migration layer. Where a supported behavior remains
wrong, it is a new finding in this enrollment; scope reduction is not permission to leave a supported-path
defect unresolved.

## A.6 Make the operating instructions usable

Update the existing README, protocol section, CLI help/error text, and relevant developer/reviewer prompt
templates together. A short operator playbook inside the README is enough. Remove stale descriptions of
foreground guidance, STOP renaming, automatic repair, exact inline bytes, and retry-time integrity checks.

Make this distinction prominent:

| Owner situation | Correct operation |
|---|---|
| A transient blocker is resolved; mission and approach are unchanged | Ordinary `resume --reason ...`. The reason is an audit note, not agent instruction. |
| The approach should change while meeting the same acceptance criteria | In the supported idle state, `resume --reason ... --guidance FILE`; verify capture and subsequent invocation/round bindings. |
| Scope, acceptance, permissions, models or project policy must change | Record the explicit owner decision and use the existing safe amendment/re-enrollment or between-run activation procedure. Guidance does not apply these changes. |
| An instruction arrives while an agent is working | Request cooperative stop, wait for the supported boundary, then deliver it. No claim of live injection. |
| The budget is exhausted, or the same approach has repeatedly failed | Report the concrete blocker and required decision. No automatic resume or cap increase. |

After a no-progress stop, the supervising Claude must read the actual outstanding findings. If the approach must
change, provide concrete guidance through the supported channel; another status reason is insufficient. If an
owner has already authorized a specific continuation, carry it out without asking again. A genuine new scope or
budget decision remains the owner's decision.

Require concise status reports that distinguish current source from last-reviewed source and show: actual run
status/reason, checkpoint, rounds used/remaining, selected guidance and delivery evidence, next permitted
operation, and whether an owner decision is needed. Do not infer that a run is working from a PR body that
still says "enrolled". The supervisor does not become a second implementation writer in an enrolled worktree.

### Reduce avoidable review loops (prompt and operating policy; also binding on both agents now)

The pinned supervisor will not load edited candidate prompts during this PR, so these instructions apply to
both agents in this enrollment directly from this mission:

- **Reviewer, round 1:** examine the complete supported change and its important failure paths, consolidating
  all supported material findings in one review. **Correction round:** first resolve prior findings, then
  inspect changed code and directly affected consumers. New concrete regressions remain reportable; unrelated
  unchanged systems and the excluded designs (Part B point 10) are not invitations to expand the mission.
- **Developer:** correct root causes in one coherent batch. For a repeated finding, explain the failing
  production path, reproduce that exact boundary, and check affected neighbors. A test that supplies the
  answer, bypasses the real orchestration, or only tests a neighboring condition does not establish the fix.
- Keep stable IDs for the same defect. If an old defect is fixed and a different defect is found, verify the
  old one and explain the new one; do not rename the same issue to evade no-progress accounting. Optional polish
  remains optional. Do not grow generic recovery or compatibility infrastructure merely to satisfy speculative
  findings.

These are prompt and operating-policy improvements. Do not introduce automatic natural-language scope
classification, a new progress score, or automatic budget tuning.

## A.7 Validation proportional to the change

Use real temporary Git repositories, controller state, locks and archives. Stub only the external model and
GitHub boundaries. Test observable behavior through the real command path where admission/loading matters.

Keep or adapt a compact set of tests covering:

1. Eligible headless no-progress resume through developer delivery, reviewer copy, published sanitized
   guidance/binding, and archive/handoff. Prove a genuinely valid matching result can finish.
2. Persistence after restart and original-file change/deletion; A → A and A → B → A; fresh report required on
   unchanged source; stale binding refused.
3. Side-effect-free refusals for invalid input/setup, unsupported mode/status/phase, outstanding
   agent/helper/runtime/publication work, wrong enrollment identity, and exhausted budgets.
4. Integrity-at-use checks for missing, altered, null or otherwise invalid selected guidance block without
   launching or charging an agent; a missing guidance key retains legacy behavior. Guided admission against the
   same damaged existing state instead refuses unchanged.
5. A real filesystem preparation failure leaves no unfinished reviewer attempt. Exercise the copy/write failure
   itself, not just a missing source file.
6. Ordinary resume/foreground behavior, findings and budgets remain intact; no-progress resume resets only the
   existing streak accounting.
7. Existing publication retry/archive behavior still works with the frozen public guidance rendering, and
   status distinguishes selected instructions from recorded invocation progress.

Use focused reproductions while editing. After the coherent code-and-docs batch is committed and pushed, run
the required `unit` gate through the pinned controller's `verify` helper on that exact candidate (underlying
command: `python -m unittest discover -s agent_review -p "test_*.py" -v`). Avoid running a duplicate complete
suite immediately before the same required gate without a concrete reason. A new commit needs a new
candidate-bound receipt; older receipts do not cover a new candidate.

Real-model `permissions` and `live-smoke` gates remain supplemental. Run one only to resolve a specific
boundary that the behavior suite and available invocation evidence cannot establish. Do not run native game
sessions for a controller guidance change. Identify Windows-specific behavior honestly; Linux fixtures alone do
not prove it.

## A.8 Review, rollout preparation and handoff

Complete the simplification, visibility additions, docs and tests before the first closeout review. The
reviewer assesses that complete candidate and the old finding dispositions. If needed, one batched correction
and the final allowed recheck follow. New supported defects still block readiness; the cap is not pressure to
approve incomplete work.

Prepare (in the README and the developer's final report) exact post-acceptance installation and activation
instructions from the reviewed source: the source SHA, the installed package/fingerprint only when actually
produced, and the existing commands to install alongside older versions, inspect an enrollment, request/wait
for a stop, activate between runs, and resume with a guidance file. Do not invent a package ID or claim an
installation happened. Explain that activation can invalidate a previous ready result and require review again.

For the paused Tabletop repair, prepare a concise proposed guidance example from the owner's existing decision:
simplify the runner to fail closed; restore the same backup contents that were verified; check the host
immediately before restore; compare each registry key/value-name/type/data tuple exactly; retain accepted
gameplay work and the current authorized budget; preserve uncommitted recovery work for inspection. If this
would actually amend that feature's acceptance contract, the amendment procedure applies instead. Its status
must be refreshed before any later application.

Completion of Tabletop, Buff Planner or Mounted Combat is not an acceptance gate for this PR. Existing
enrollments stay on their pinned versions until their owner-authorized activation.

### Reference evidence

- PR #5: https://github.com/howardreith/development-process/pull/5
- `662b` round-3 review: https://github.com/howardreith/development-process/pull/5#issuecomment-7073484842
- `662b` no-progress stop: https://github.com/howardreith/development-process/pull/5#issuecomment-7073485351
- Repository instructions and validation policy: `AGENTS.md`.
- Owner's independent preparation check (not a gate receipt): six retained focused behavior tests passed
  against `3cecfb5`; a separate reproduction confirmed that explicit `guidance: null` launches an unguided
  developer in that implementation.

## Appendix H — open findings of the previous enrollment `662b` (state after its round 3)

Summaries only; the full structured findings and assessments are in the linked round-1..3 reviews.

| ID | Last `662b` assessment (round 3) |
|---|---|
| 662b/R1-F2 | Admission is not fully side-effect-free: linked final destinations and manifest decoding failures escape the refusal path. |
| 662b/R1-F5 | Foreground idleness detection from transcripts can overlook a later user record (ordering, or arrival during remote checks). |
| 662b/R1-F6 | Save-failure rollback was tested only without a prior selection; identical-content repair can replace a live selected file. |
| 662b/R1-F7 | A present-but-null `guidance` member silently disables delivery; the newline simulation ends before Windows stdin translation. |
| 662b/R1-F8 | Filesystem exceptions while preparing the reviewer copy still leave an unfinished reviewer attempt. |
| 662b/R2-F3 | STOP consume crash window: a newer request can be moved out of the path checked on restart. |
| 662b/R2-F4 | The temporary output file can still redirect the snapshot write before the final destination is installed. |
| 662b/R2-F5 | The publication send loop can retry after the single guidance check, including after rejection and backoff. |
| 662b/R3-F1 | Foreground report guidance member is discarded before schema validation; an explicit null passes, and JSON `true` equals revision 1 in tuple comparison. |
| 662b/R3-F2 (optional) | README recovery table merges round-cap and no-progress stops. |

---

# Part B — Owner addendum of 2026-11-22: narrow the design, keep the safety bar (governing)

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

---

# Part C — Original mission of 2026-11-21 (historical background; superseded where it conflicts with Parts A and B)

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
