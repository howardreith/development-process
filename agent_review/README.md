# agent-review: Claude Opus develops, Codex GPT-6.2 Astra reviews

A machine-level development workflow for the GitHub repositories under
`C:\Dev`. Claude Opus (high effort) implements a mission; Codex with GPT-6.2
Astra (`gpt-6.2-astra`, max reasoning effort) independently reviews each
checkpoint; a small local controller runs both, verifies every result and
keeps the whole exchange on a GitHub **draft PR**. The owner is involved only
for a human decision, a precise blocker, or the final review. Nothing merges,
releases, tags or requests human reviewers.

Behavioral specification: [../docs/GITHUB-AGENT-REVIEW-PROTOCOL.md](../docs/GITHUB-AGENT-REVIEW-PROTOCOL.md).

## Layout on this machine

| Path | What it is |
|---|---|
| `C:\Dev\development-process\agent_review\` | Source (this folder): controller, schemas, prompts, permission base, project configs, plans, tests. |
| `C:\Dev\agent-review\` | Pinned installed copy with `MANIFEST.json`, installed from a reviewed checkout; never edited in place. |
| `C:\ProgramData\agent-review\` | Host-wide claims: one writer lock and one registry entry per repository branch, shared by every clone and every state home. |
| `<worktree git dir>\agent-review.lock`, `agent-review-enrollment.json` | Physical guard: the same worktree cannot be owned twice. |
| `~\.agent-review\projects\`, `plans\` | Optional user-local configs (`init-project` writes here); shipped ones live in this folder. |
| `~\.agent-review\state\<enrollment>\` | Private enrollment state (unless a project sets `state_root`): `state.json`, outbox, round inputs, envelopes, developer logs, gate receipts. Never committed. |
| `<repo>\docs\agent-reviews\pr-<N>\` | Committed, sanitized review records for each PR. |

## Onboarded repositories

Every primary repository under `C:\Dev` except nima has a project config in
[projects/](projects/), validated with `check-project` on 2026-11-20:

| Project | Repository | Target | Branches | Push | Gates |
|---|---|---|---|---|---|
| `development-process` | howardreith/development-process | main | `claude/*` | built-in | `unit` |
| `kingmaker-gunslinger` | howardreith/KingmakerGunslingerAndOtherTabletopRules | master | `codex/*` | repo wrapper | `focused` (`Invoke-KmgGate.ps1 -Filter …`) |
| `kingmaker-buff-planner` | howardreith/KingmakerBuffPlanner | main | `codex/kingmaker-buff-planner…` | repo wrapper | `focused` (`Test-Development.ps1 -Only …`) |
| `kingmaker-mounted-combat` | howardreith/KingmakerMountedCombat | main | `codex/*` | built-in | `focused` (`Test-Tiers.ps1 -Tier … -Focused …`) |
| `kingmaker-dice-roller` | howardreith/KingmakerDiceRoller | main | `claude/*` | built-in | `domain` |
| `kingmaker-last-azlanti-preserver` | howardreith/KingmakerLastAzlantiPreserver | main | `claude/*` | built-in | `qualify` |
| `kingmaker-skip-cinematic` | howardreith/KingmakerSkipCinematic | main | `claude/*` | built-in | `test` |
| `kingmaker-memory-leaks` | howardreith/KingmakerMemoryLeaksFix | main | — | — | enrollment refused: its AGENTS.md forbids pushes and PRs |
| `civ5-1836` | howardreith/Civ5_1836 | main | `claude/*` | built-in | `unit` |
| `theatre-game` | howardreith/theatre-game | main | `claude/*` | built-in | `validate` |
| `auditionintel-backend` | LeitbyteLLC/AuditionIntelBackEnd | main | `claude/*` | built-in | `unit`, `lint` |
| `auditionintel-frontend` | LeitbyteLLC/AuditionIntelFrontEnd | master | `claude/*` | built-in | `smoke` |
| `noelle-backend` | LeitbyteLLC/NoelleBackEnd | main | `claude/*` | built-in | `unit`, `lint` |
| `noelle-native-app` | LeitbyteLLC/NoelleNativeApp | main | `claude/*` | built-in | `unit`, `lint` |
| `getnoellecom` | LeitbyteLLC/getnoellecom | main | `claude/*` | built-in | `unit` |

The Kingmaker projects list all six shared runtime transaction locks, so a
developer is never terminated and a handoff never declared while any lab's
game transaction is active. `kingmaker-gunslinger` also lists its
loader-compat game-copy lock (`game-copies/loader-compat.lock`), and its
developer may run `Build-Local.ps1` and the loader-compat harness/session
scripts, which operate only on the disposable game copy (owner decision
2026-11-21, PR #195). Deploy, install, publish, live-mod, store-submit,
migration and production scripts are denied to the headless developer per
project. Plans: `single` (any mission), `black-tentacles`, `agent-review-setup`.

## Architecture

```text
 owner ──start/stop/resume──▶ controller (python, this host, one writer per branch)
          ┌─────────────────────┼──────────────────────────────┐
          ▼                     ▼                              ▼
  Claude Code -p          Codex exec (read-only)          gh (owner's auth)
  opus / high             gpt-6.2-astra / max             draft PR comments,
  developer worktree      detached snapshot of H          PR body status
  push + verify helpers   structured review JSON          (controller only)
```

- **Controller** owns enrollment, candidate identity (H reviewed commit, B
  target tip, M merge base), model launch settings and provenance checks,
  schema and semantic validation of reviews, host-wide and worktree locks,
  idempotent publication, retries, round budgets, gate receipts, archive
  commits and readiness. It is the only component that writes to GitHub.
- **Developer**: Claude Code. *Headless mode* (normal missions): the
  controller launches `claude -p --model opus --effort high --session-id <uuid>`
  and later `--resume <uuid>` (never `--continue`), with
  `--permission-mode dontAsk`, the enrollment's hash-pinned permission file,
  no MCP servers and a required structured report. *Foreground mode*: an
  interactive Claude session is the developer and submits reports with
  `review --report`; each report is bound to that session's CLI-recorded
  model and effort.
- **Reviewer**: `codex -a never exec --ignore-user-config -m gpt-6.2-astra
  -c model_reasoning_effort="max" -c windows.sandbox="elevated" --sandbox
  read-only --disable <connectors/agents/browser/...> -C <snapshot>
  --output-schema <schema> -o <result> --json -`, prompt on stdin, in a
  detached worktree of H. Its inputs (mission, diff, prior findings, report,
  gate receipts, headless tool transcript) are copied into a reserved
  `.agent-review-inputs/` folder inside that workspace.
- **Owner model policy** is pinned in code (`POLICY`); a project file cannot
  select other models.

The host must stay on, signed in and online while a run is active. Nothing
continues after it sleeps or loses access; `resume` reconciles state and
GitHub afterwards.

### Round lifecycle

1. Developer commits, pushes (repository wrapper or the controller's guarded
   `push` helper) and runs the checkpoint's required gates with
   `verify --gate <id>`; the controller runs each gate on the clean candidate
   and writes a receipt bound to H (command, exit code, output digest, whether
   the worktree stayed unchanged). Then it reports `checkpoint_ready`.
2. Controller verifies identity (worktree, origin, actor, PR number,
   same-repository head, base, draft), H = pushed head = PR head, the report's
   binding to H, required gate receipts for H, the transcript tree delta, and
   posts **Claude Opus — review request**.
3. Codex reviews the fixed snapshot.
4. Controller validates exit status, complete JSON, schema
   `agent-review.review.v1`, echoed identity, decision vs checkpoint type,
   finding/evidence consistency (no pass with blocking findings or required
   gaps; a `required_gap` must block; open blocking findings stay blocking),
   prior-finding assessments (unique, pending, compatible with the
   disposition, no deferral of blocking items, rejections restated) and
   provenance from the Codex rollout (model and effort per turn, read-only
   sandbox, approval `never`, no sub-agents). Failed attempts retry with
   backoff and never count as rounds; wrong model or effort and usage limits
   stop at once. A valid attempt is promoted atomically, its envelope bound by
   digest and workflow version.
5. Before and after publishing, the controller re-checks PR head, branch head
   and merge base; a move makes the review HISTORICAL with a visible
   correction. Otherwise **Codex GPT-6.2 Astra — review** is posted and the
   round, findings ledger, counters, next phase and any stop are saved in one
   write.
6. `changes_required` → the developer disposes every pending finding; the
   controller posts **Claude Opus — finding dispositions** (keyed by the full
   body, so replays are idempotent). `checkpoint_passed` (intermediate)
   advances automatically. `ready_for_owner_review` (final) goes to finalize.

### Records, archive and handoff

After a ready review of H the controller authenticates every outgoing body and
accepted envelope against their recorded digests, persists an archive intent
(including the record contents), writes the records to
`docs/agent-reviews/pr-<N>/`, commits them as archive commit A and pushes it.
Interrupted archives resume from the intent; a commit made just before a crash
is adopted only if it contains exactly the intended records. Readiness at A
requires every commit in H..A to be a non-merge pure addition of plain files
the controller wrote for this PR, with matching hashes; every substantive
publication sent and still intact on the PR; required gates and hosted checks
(per provider) passing on H; no runtime lock; an unchanged merge base. The
handoff is re-checked after posting the receipt and after editing the PR body;
`status --remote` re-runs the same checks (including the receipt) to tell
whether a handoff is still current, and `resume` reopens a superseded one.

## Onboarding a repository

```powershell
$ar = 'C:/Dev/agent-review/agent_review.py'
python $ar init-project --repo C:/Dev/<repo> --name <name> [--branch-prefix claude/] [--allow "npm test"] [--push-command '[...]']
# add "gates" (id -> argv, optional extra_args_pattern, timeout_minutes) and protected-path denials, then:
python $ar check-project --project <name> --repo C:/Dev/<repo>
python $ar preflight --project <name>
```

Shipped configs belong in `projects/` here (reviewed); `init-project` writes
user-local ones to `~/.agent-review/projects/`. A project with
`"enrollment_allowed": false` can be checked but never enrolled.

Required gates: a project's `required_gates` (by default every declared gate)
are required at every checkpoint of every plan, including the generic `single`
plan. A plan checkpoint can add gates but cannot drop them. Declare
supplemental gates and list only the required ones, as development-process
does (`"required_gates": ["unit"]`).

## Running a mission

```powershell
git -C C:/Dev/<repo> worktree add -b claude/<feature> <worktree> origin/<default>
# commit the mission file (or a first change) and push it
python $ar enroll  --project <name> --worktree <worktree> --plan single --mission <MISSION.md> --mode headless
python $ar run     --enrollment <id>      # develop → verify → review → correct → … → owner handoff
python $ar list                          # every enrollment on this machine (read-only)
python $ar status  --enrollment <id> [--remote]
python $ar stop    --enrollment <id> --reason "..."
python $ar resume  --enrollment <id> --reason "what changed" [--max-rounds N] [--guidance <file> | --amend-mission <file>]
python $ar cancel  --enrollment <id> --reason "..."
```

Plans with intermediate checkpoints and `required_gates` go in `plans/` (or
`~/.agent-review/plans/`). Exit codes: 0 done/awaiting owner, 2 BLOCKED,
3 PAUSED, 4 refused.

`list` prints a JSON array with one object per claim in the host registry
(`%ProgramData%\agent-review\registry`), sorted by enrollment ID: `enrollment`,
`repository`, `branch`, and from that enrollment's `state.json` `status`,
`phase`, `pr` (number or null) and `updated_at`. It is strictly read-only: no
locks, no writes and no network or GitHub calls, so it is safe while
controllers run. A claim whose state file (or the claim itself) is missing,
unreadable or malformed is still listed, with `status` `"unknown"` and an
`error` field saying why; one damaged enrollment never fails the listing.
Enrollment resolves the state root to an absolute path, so new claims record
both `dir` and `state_dir` as absolute paths and enrollments made with a
relative `--state-root` list correctly from any directory. Older claims naming only a relative directory, paths on network
storage (a UNC/device path or a mapped network drive), and any path whose
registry folder, claim file, state directory components or `state.json` is a
symbolic link, junction or other reparse point are reported the same way
without being read (links are refused conservatively, whatever their target;
paths with `..` segments are refused, and a path with a missing component is
reported missing without being opened). A registry folder that is linked,
remote or cannot be enumerated (for example, listing permission denied) makes
`list` refuse with exit 4 rather than print `[]`; an absent registry prints
`[]`. A state file whose
`enrollment_id` differs from the claim's is reported without copying any of
its fields. `pr` is a positive integer or null even if the state file holds
something else. Cancelled
enrollments release their claim and are not listed. Use `status --enrollment
<id>` for the full detail of one enrollment.

### The owner's experience and the supervisor's duties

The workflow runs as one familiar sequence: agreed task → Claude's PR and
explanation → Codex's review and continuation → Claude's corrections → repeat
→ owner notification and final review. What the controller does and what the
supervising Claude (the interactive session that launched the run) does are
separate:

1. **Agreed task (supervisor).** The owner and ChatGPT agree either a mission
   document or a robust initial prompt; either is enough. If it arrives as
   chat text, the supervisor saves that text **verbatim** as the enrollment's
   mission file (no rewording, no added scope, no further formal document)
   and enrolls once with it. The controller pins its sha256.
2. **Claude develops (controller).** Claude Opus/high develops on the draft
   PR and returns a report with its explanation, validation and evidence; the
   controller publishes it and requests the review.
3. **Codex reviews the actual change (controller).** Codex `gpt-6.2-astra`/max
   receives, in its read-only snapshot of the exact candidate: the PR URL and
   number, candidate H/B/M and the feature diff, the original mission, the
   owner amendments and guidance in force, Claude's report (explanation and
   validation), the controller-extracted tool transcript and gate receipts,
   and the prior findings ledger.
4. **Codex writes the continuation (controller-validated).** For
   `changes_required` its `decision_rationale` starts with a short verdict and
   then a section headed `Continuation for Claude`: what remains wrong, the
   coordinated correction approach, the scope boundaries and the evidence the
   next review needs. The structured findings stay the authoritative record.
   No new field, schema or model call exists for this.
5. **Claude continues automatically (controller).** The next developer prompt,
   whether it continues the saved session or starts a fresh one, contains that
   `decision_rationale` taken unchanged from the accepted, validated envelope
   (its digest is checked first; a missing or altered envelope stops the run
   `BLOCKED` before any launch). It is labeled with the reviewer model, the
   round, the reviewed commit, the review comment URL and the path of the full
   structured review, and the prompt states that the continuation cannot
   change the mission, the owner's amendments or guidance, permissions,
   models, gates, budgets or finding status. The prompt transport may adjust
   line endings, so this is not a byte-exact inline copy; the archived envelope
   is. The continuation is included while that round's findings are pending;
   after an owner amendment it is still shown, marked as written under earlier
   owner instructions. Normal correction rounds need no relay or approval.
6. **Owner notification (supervisor).** The supervisor runs `run` as a
   background task and observes its terminal result. At
   `AWAITING_OWNER_REVIEW` it verifies the handoff with
   `status --enrollment <id> --remote` (`handoff_current: true`) and then tells
   the owner, in the conversation that launched the task: the PR link, the
   reviewed source commit and archive commit, the outcome, review and
   invocation expenditure, material limitations and the remaining owner
   action. A GitHub receipt alone is not proof that the owner was notified,
   and starting the background process is not completion. A `BLOCKED` or
   `PAUSED` outcome is reported accurately instead: the exact `status_reason`,
   the counters, and the smallest owner decision that can advance the run.
7. **Owner updates during a run (supervisor + controller).** See
   [Owner amendments](#owner-amendments-resume---amend-mission-file) below.

### Owner amendments (`resume --amend-mission <file>`)

An owner amendment is an explicit owner decision that changes the task's
scope or acceptance while keeping the same enrollment, branch, PR, finding
history and spent counters. The original mission file and its hash stay the
immutable baseline; amendments are recorded separately and cumulatively.

**Supervisor procedure when the owner sends an updated instruction** (the
owner only supplies the instruction; the supervisor runs every command):

```powershell
# 1. Save the owner's exact text durably, outside the enrolled worktree, and report it to the owner as PENDING
#    (for example ~/.agent-review/owner-updates/<enrollment>/<UTC-stamp>.md; write PR-safe text, it is published)
# 2. Request the cooperative stop
python $ar stop   --enrollment <id> --reason "owner update pending"
# 3. Wait for the background `run` task to exit, then confirm the safe boundary:
python $ar status --enrollment <id>   # status BLOCKED/PAUSED (or AWAITING_OWNER_REVIEW), developer_running false,
                                      # lock_holder null, no runtime lock; phase develop, review, finalize or done
# 4. Apply it; the same command continues the same enrollment (run it as a background task again)
python $ar resume --enrollment <id> --reason "owner update of <date>" --amend-mission <saved-file>
# 5. Check: status.amendments.selected (applied) and, once the next invocation returns,
#    status.amendments.latest_developer_invocation (included in a recorded agent input)
```

If step 4 is refused (exit 4), nothing changed: the instruction stays pending
with the supervisor, who reports the exact refusal. A run that never reaches a
stopped state (for example a developer finishing a runtime restoration) is
waited for, never interrupted. A process that died without a recorded return
is not a returned invocation: use the existing recovery (`resume`) first, stop
again, then apply. There is no live injection into a running agent, and the
supervisor never claims an agent saw text that only the supervisor received.

#### Amendment rules

- **Supported boundaries (headless only).** A headless enrollment that is
  `BLOCKED` or `PAUSED` in `develop`, `review` or `finalize`, or that is
  `AWAITING_OWNER_REVIEW` on its still-open draft PR. Refused (exit 4, nothing
  changed, the instruction stays pending): an `ACTIVE` run (it holds the
  writer lock, or it has not reached a stop), a live developer process, a
  developer launch without a recorded return, a reviewer attempt still running
  or without a recorded end, a push/verify helper holding the helper lock, a
  configured runtime lock, a publication of uncertain delivery, an archive
  commit in progress, a closed or non-draft PR, a damaged guidance or
  amendments selection, the exact message that is already the latest
  amendment, or a combination with `--max-rounds`, `--resend-undelivered` or
  `--guidance`. Foreground enrollments are refused.
- **Capture.** The file is validated like a guidance document (at most 64 KiB,
  UTF-8, not blank). Under the writer and helper locks, the controller builds
  the next cumulative document: the current revision's verified bytes (or a
  fixed header) followed by `----- BEGIN OWNER AMENDMENT <n> (captured <time>;
  message sha256 <digest>) -----`, the message's exact bytes and the matching
  END line. Owner amendment *n* is revision *n*. The document (at most
  256 KiB) is written to `<enrollment>/amendments/<sha256>.md` with the same
  content-addressed, never-overwritten capture as guidance, and selected in
  `state.json` (`amendments.revisions`: revision, sha256, message sha256,
  sizes, capture time, source path for information, reason, supersedes).
  Earlier snapshots stay unchanged; editing or deleting the input file later
  changes nothing.
- **Application (one state save).** The stopped round is superseded (a
  never-delivered request is withdrawn), a validated result is invalidated and
  its verdict retired, a ready result is moved to `superseded_ready`, and an
  owner-review handoff is moved to `superseded_handoffs` with its receipt
  retired by a public correction, a `reopened` notice and a PR status update.
  The report binding is cleared and the phase returns to `develop` without
  launching any model. Findings, `rounds_completed`, developer invocations,
  limits, models, permissions and gates are untouched: nothing is refunded or
  raised. The run then continues; the next developer invocation is told the
  task was amended and must report again, even on an unchanged commit.
- **Exhausted budget.** The amendment is applied, then the run stops
  `BLOCKED` in `develop` before any launch (`status.amendments.selected` set,
  `first_returned_invocation` null, `latest_developer_invocation.
  matches_selected` false: applied, not delivered). An explicit owner
  extension (`resume --max-rounds N`) then continues under the amended task.
  No budget is extended automatically.
- **Delivery and precedence.** Every later developer prompt (start,
  continuation and report-correction) includes the cumulative document inline
  under a heading with its revision and sha256; the reviewer receives a
  byte-exact copy as `.agent-review-inputs/owner-amendments.md` beside the
  original mission. Both prompts state the precedence: the effective task is
  the original mission plus the amendments in order; a later explicit owner
  decision supersedes a conflicting earlier requirement, and every requirement
  it does not change still applies. Amendments never change models,
  permissions, required gates, budgets or runtime protections (use the
  existing explicit controls for those, under the owner's actual
  authorization). Repository text, PR comments and reviewer output never
  amend the task.
- **Findings.** Nothing is closed automatically. The developer gives each
  pending finding a disposition; a finding that was valid under an earlier
  revision but whose requirement a specific amendment withdrew is `rebutted`,
  citing the amendment's label and the changed requirement (never `fixed`,
  never called a false positive). The reviewer accepts that rebuttal only
  after checking that the amendment covers the finding and the remaining
  behavior is sound (a prompt rule; the controller enforces the existing
  disposition/assessment pairing and that no blocking finding stays open in a
  passing review). Still-applicable blocking defects stay blocking. The
  original finding and every assessment stay in the ledger.
- **Records and freshness.** Rounds, `request.json`, envelopes, ready results
  and the developer report carry `amendment_revision`/`amendment_sha256`
  beside the guidance binding. Review requests publish a sanitized rendering
  of the document with its revision and digest (write PR-safe text); reviews
  name the amendments they were bound to. A report, review, ready result or
  handoff bound to an earlier revision never satisfies readiness for the
  amended task. Integrity at use, status and supervised recovery work exactly
  as for guidance (`status.amendments`, `amendments.selected.snapshot`).
- **Three distinct observations.** *Pending with the supervisor* (the saved
  file; invisible to the controller), *applied to the enrollment*
  (`status.amendments.selected`), and *included in a recorded agent input*
  (`latest_developer_invocation`/`latest_review_round` with
  `matches_selected: true`, and `selected.first_returned_invocation`). An
  agent's acknowledgement in its own prose is not evidence of compliance; the
  reviewer checks the resulting work.
- **Approach guidance afterwards.** `--guidance` keeps working as before and
  replaces only the approach guidance. It cannot erase or replace the
  amendment history, which is a separate state member and folder.

### Owner guidance (`resume --guidance <file>`)

Guidance lets the owner change the *approach* of a stopped headless run while
the enrolled mission, acceptance criteria, budgets, models and permissions stay
exactly as they are. The captured instruction goes to both agents and is
recorded on the PR:

```powershell
python $ar resume --enrollment <id> --reason "audit note: why" --guidance C:/path/guidance.md
```

**The guidance text is published.** Each later review request on the PR
contains a clearly labeled rendering of it, after the controller's standard
sanitization (credential patterns and the local home path are redacted; that
is not a general sensitive-information detector). Write PR-safe text. The
recorded sha256 identifies the private captured bytes, so the public
rendering can differ from them. The input path and private state paths are
never published. `--reason` stays an audit note and is not an instruction to
either agent.

#### Operator playbook

| Owner situation | Correct operation |
|---|---|
| A transient blocker is resolved; mission and approach are unchanged | Ordinary `resume --reason ...`. The reason is an audit note, not agent instruction. |
| The owner supplies the agreed task as chat text | Save it verbatim as the mission file and enroll once with it; do not reword or expand it. |
| The approach should change while meeting the same acceptance criteria | In the supported idle state, `resume --reason ... --guidance FILE`; then check `status` (`guidance.selected`) and, as the run continues, the `latest_developer_invocation` and `latest_review_round` bindings. |
| The owner changes the task's scope or acceptance criteria | Save the exact instruction as pending, `stop`, wait for the stopped state, then `resume --reason ... --amend-mission FILE` (above). Same enrollment, branch, PR and counters. |
| Permissions, models, required gates, budgets or project policy must change | Use the existing explicit operation under the owner's actual authorization (`resume --max-rounds`, re-enrollment, between-run `activate`). Neither guidance nor an amendment applies these changes. |
| An instruction arrives while an agent is working | Save it as pending, `stop`, wait until `status` shows the run stopped (not `ACTIVE`, `developer_running` false, `lock_holder` null), then apply it (`--amend-mission` for a task change, `--guidance` for an approach change in `develop`). There is no live injection into a running agent. |
| The background run exits | Inspect its result. At `AWAITING_OWNER_REVIEW`, verify with `status --remote` and notify the owner here (item 6 above); otherwise report the exact stop and the next decision. |
| A budget is exhausted, or the same approach has repeatedly failed | Report the concrete blocker, the actual counters, and the specific owner decision that can advance the run (below). No automatic resume or cap increase. |

**No-progress stop versus exhausted budget.** These are different stops, but
they can coincide, so always check the counters in `status`:
`rounds_completed[<checkpoint>]` against `round_limit`, and
`developer_invocations` against the enrollment's limit (`limits.max_developer_invocations`
in its `state.json`; default 30). The stop reason names whichever cap was hit.

- A no-progress stop (`status_reason` starts with `no progress`) means the
  same blocking findings stayed open. The no-progress check runs before the
  round-cap check, so this reason can also be recorded on the last permitted
  round, with no budget left. An owner `resume` restarts the no-progress
  counting. If the approach must change, the supervising Claude reads the
  actual outstanding findings and supplies concrete guidance through
  `--guidance`; another status reason is not enough.
- An exhausted review-round budget (`review-round cap reached`, or
  no progress on the last round) needs an explicit owner decision.
  `resume --max-rounds N` raises only the review-round limit.
- An exhausted developer-invocation budget
  (`developer invocation budget exhausted`) is a separate owner decision. No
  `resume` option raises it, and `--max-rounds` does not help. Report it and
  use the existing re-enrollment procedure.
- Every ordinary `resume`, including one with `--max-rounds`, continues the
  run immediately: the developer is launched under the current guidance
  selection. Guidance is refused while a budget is exhausted and never
  accompanies a budget change. If both are needed, the owner extends the
  budget first and accepts that the run continues under the current approach.
  The supervisor then requests `stop`, waits for the stopped state and
  resumes with `--guidance`.
- If the owner has already authorized a specific continuation, the supervisor
  carries it out without asking again. A genuinely new scope or budget
  decision stays with the owner.

**Status reports by the supervising Claude** are concise and cover: the
current source commit versus the last-reviewed source commit, the actual run
`status`/`status_reason`, the checkpoint, rounds used and remaining, the
selected guidance with its delivery evidence (below), the next permitted
operation, and whether an owner decision is needed. A PR body that still says
"enrolled" does not show that a run is working; use `status`. The supervisor
does not become a second implementation writer in an enrolled worktree.

#### Rules

- **Supported state (headless only).** `--guidance` is accepted only for a
  headless enrollment that is `BLOCKED` or `PAUSED` in the `develop` phase,
  with no active review round or reviewer attempt, a returned last developer
  launch (or none yet), no live developer process, no push/verify helper
  holding the helper lock, no configured runtime lock, and no pending or
  uncertain publication, queued public operation or pending archive commit.
  Neither the round budget nor the developer invocation budget may be
  exhausted. `--max-rounds` (a budget change) and `--resend-undelivered`
  cannot be combined with it. Foreground enrollments are refused (give the
  interactive session the instruction directly). Every other state is
  refused with exit code 4, for every document, including the current one.
  The option is never silently ignored. `resume` without `--guidance` behaves
  exactly as before.
- **Validation before any change.** The file is read (at most 64 KiB + 1
  byte), must be valid UTF-8 with non-whitespace content, and is hashed
  before anything else. A workflow that fails to load, a malformed manifest
  or a malformed claim file is also a refusal. Under the writer lock the
  controller takes the helper lock and holds it until capture. It then checks,
  read-only, that the owner-selected enrollment ID, the loaded state, its
  directory and both ownership claims name the same enrollment. Next come
  the state rules above and the integrity of any existing selection. A null,
  malformed or dangling selection, or a damaged selected snapshot, is refused:
  supplying a new document is not a repair bypass. Last come the usual
  identity, workflow-fingerprint and mission checks. A refusal (exit 4)
  leaves `state.json`, the `STOP` file, every counter and the PR unchanged and
  launches nothing. Content is never validated as natural language.
- **Capture.** The bytes are written with the controller's atomic-write
  pattern to the content-addressed file `<enrollment>/guidance/<sha256>.md`.
  An existing file is verified and reused, and never overwritten. Only after
  the file exists is the revision selected in `state.json`
  (`guidance.revisions`: revision, sha256, size, capture time, original path
  for information, reason), in the same state save as the resume itself. The
  `STOP` file is handled exactly as by an ordinary resume. If the save fails,
  the unreferenced content file is harmless and nothing is selected. Editing
  or deleting the original file afterwards changes nothing.
- **Revisions.** Identical content keeps the current revision. Any other
  content becomes a new revision. A → B → A creates revisions 1, 2 and 3, and
  revision 3 reuses A's content file. Content identity and the latest owner
  decision are different things. Earlier content files are immutable.
- **Delivery.** Every later developer prompt (start, continuation and
  report-correction invocations) includes the text inline under a heading
  that names the revision and sha256. The prompt transport may adjust line
  endings; the digest identifies the captured bytes. The reviewer gets a
  byte-exact copy as `.agent-review-inputs/owner-guidance.md` next to the
  mission, and its prompt names that file, the revision and the digest. Both
  prompts say that guidance supplies the owner's approach within the
  enrolled mission. It does not change acceptance criteria, close a finding,
  change budgets, models or permissions, or authorize a scope change. The
  reviewer still judges the work against the mission.
- **Records.** Each round records `guidance_revision`/`guidance_sha256`. The
  reviewer's `request.json`, the validated envelope, the published request
  (with its frozen public rendering) and review comments, and therefore the
  archived records, name the revision and digest that applied, or `none`. The
  rendering is fixed when the request is queued. Publication retries send the
  already-rendered body and do not re-read guidance.
- **Freshness.** A developer report, round, envelope and ready result are
  bound to a revision *and* its digest. Selecting a new revision clears the
  current report and ready bindings, so the next review needs a fresh
  developer report even on an unchanged commit. A stale review, including one
  bound to revision 1 after A → B → A, does not satisfy readiness or finalize.
  Historical rounds keep their original binding.
- **Status.** `status` adds a `guidance` summary computed from existing state:
  `selected` (revision, digest, capture time, snapshot path and `integrity`),
  `latest_developer_invocation` and `latest_review_round`.
  - `latest_developer_invocation`: its guidance binding,
    `intent_recorded_at` (saved before dispatch, so intent only),
    `process_start_recorded` and `returned`.
  - `latest_review_round`: its binding, its status and its latest attempt
    (`opened_at`, `process_start_recorded`, `ended_at`, `ok`).
  - `process_start_recorded` is `true` only when the controller's
    process-start callback (or a later return) recorded it, `false` for an
    attempt closed as never launched, and `null` when there is no evidence
    either way.
  - `matches_selected` compares each binding with the selection.
  - A null, malformed or dangling selection shows `"integrity": "problem"`
    (with the recorded member, locally), never "none". `selected: null` means the
  enrollment never had guidance. These are distinct observations: "captured",
  "included in the invocation input", "launch recorded" and "returned". A
  saved file or launch intent alone does not prove delivery to a running
  process. An agent's acknowledgement in its own prose is not independent
  evidence that it followed the guidance; the reviewer checks the resulting
  work.
- **Integrity at use.** Immediately before each developer prompt is built,
  and before a review request is recorded or a reviewer attempt is opened,
  the controller re-reads the selected snapshot and verifies its digest. A
  missing or altered file, or a present but null or invalid selection, stops
  the run `BLOCKED` before any launch or invocation charge. That stop is
  persisted. It differs from an admission refusal, which changes nothing.
  Only a state without any `guidance` key is an unguided (legacy) enrollment.
  A known filesystem failure while the reviewer's inputs are being prepared
  closes that attempt as not launched and stops `BLOCKED`, leaving no
  unfinished attempt.
- **Supervised recovery.** A damaged selected snapshot is never repaired
  automatically, and `--guidance` refuses until it is fixed. Restore the
  identical captured bytes to the path that local
  `status.guidance.selected.snapshot` shows (the published stop reason names
  only the revision and digest; the sha256 must match), confirm
  `"integrity": "intact"`, then run an ordinary `resume`. The same applies to
  an earlier revision's file: resubmitting that document never recreates it,
  and `--guidance` refuses (exit 4, nothing changed) until the identical bytes
  are restored. A failure to write a new capture file is also an exit-4
  refusal with the path in the local message; nothing is selected or published. A damaged selection
  record in `state.json` needs supervised repair of the enrollment state, or a
  cancel and re-enrollment. Enrollments that never received guidance,
  including state written before this option existed, load, run and archive
  unchanged.
- **Not provided.** Foreground guidance, live injection into a running
  agent, guidance outside the idle `develop` state, automatic repair and
  acknowledgement protocols. Task changes use `--amend-mission` (above).

#### After the owner accepts this change: install and activate

The candidate in this PR is code under test. It is not installed or
activated as part of the PR. After owner acceptance, install exactly the
reviewed source commit H named in the owner handoff (`<reviewed-sha>`). Use a
fresh, clean, detached checkout of that commit, not a working copy that may
hold local edits, and not a later merge commit whose content was not
reviewed:

```powershell
$src = 'C:/Dev/agent-review-src-<reviewed-sha>'
git -C C:/Dev/development-process fetch origin
git -C C:/Dev/development-process worktree add --detach $src <reviewed-sha>
git -C $src rev-parse HEAD                                  # must print <reviewed-sha>
git -C $src status --porcelain                              # must print nothing
python $src/agent_review/agent_review.py install --dest C:/Dev/agent-review
# install prints the new package's fingerprint; record it. Existing versions stay in place for pinned enrollments.
# New enrollments made from here on use the new version (reviewer continuation, --amend-mission).
# Optional, per existing enrollment and only as an explicit owner decision between runs:
python $ar status --enrollment <id>                         # inspect: mode headless, status, phase, counters
python $ar stop   --enrollment <id> --reason "activate the amendment-capable controller"
python $ar status --enrollment <id>                         # wait: not ACTIVE, developer_running false, lock_holder null
python $ar activate --enrollment <id>                       # owner decision, between runs
python $ar status --enrollment <id>                         # confirm workflow_fingerprint_matches, then continue:
python $ar resume --enrollment <id> --reason "..."          # or, for a pending owner update, --amend-mission <file>
```

If an eligibility check fails, `--guidance` or `--amend-mission` refuses with
exit code 4 and changes nothing. Remove the temporary source worktree afterwards with
`git -C C:/Dev/development-process worktree remove $src`; the installed
version is self-contained.

Activation is a per-enrollment owner decision. It can invalidate a previous
validated or ready result, which is then reviewed again. Enrollments that are
not activated stay on their pinned versions. An example guidance document for
the paused Tabletop repair is prepared, but not applied, in
`planning/TABLETOP-REPAIR-GUIDANCE-PROPOSAL.md`. Refresh that enrollment's
status before using it.

### Prepared mission: Black Tentacles (not started)

The `black-tentacles` plan keeps the mission
(`C:\Dev\KingmakerGunslingerLab\BLACK-TENTACLES-MISSION.md`, hash-pinned at
enrollment) as the contract. It reviews automatically after Phases 0–1
(intermediate) and at the complete Phase 4 candidate (final), and both require
the `focused` gate. The exact start sequence is in the tabletop repository's
`docs/AGENT-REVIEW-WORKFLOW.md` (draft PR #194):

```powershell
$ar   = 'C:/Dev/agent-review/agent_review.py'
$repo = 'C:/Dev/KingmakerGunslingerLab/repo/KingmakerGunslinger'
$wt   = 'C:/Dev/KingmakerGunslingerLab/worktrees/black-tentacles'
git -C $repo fetch origin
git -C $repo worktree add -b codex/black-tentacles $wt origin/master
Copy-Item C:/Dev/KingmakerGunslingerLab/BLACK-TENTACLES-MISSION.md "$wt/planning/BLACK-TENTACLES-MISSION.md"
git -C $wt add planning/BLACK-TENTACLES-MISSION.md
git -C $wt commit -m "Add Black Tentacles mission contract"
Push-Location $wt; powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Dev/KingmakerGunslingerLab/codex-policy/Push-KingmakerGunslinger.ps1; Pop-Location
python $ar enroll --project kingmaker-gunslinger --worktree $wt --plan black-tentacles --mission C:/Dev/KingmakerGunslingerLab/BLACK-TENTACLES-MISSION.md --mode headless --title "[draft] Black Tentacles"
python $ar run --enrollment <id printed by enroll>
```

`stop` writes a `STOP` file; the developer finishes or restores its current
transaction, commits, pushes and returns `paused`. At the soft deadline (8 h)
the controller requests that stop itself; after the grace period (1 h) it
terminates the developer only if no configured runtime lock exists. An
interrupted launch is reconciled by finding the session's process by its
session ID, so a running child is never duplicated even if its PID was never
recorded. Long missions resume the same Claude session across invocations
(Claude Code compacts its context automatically); each invocation, gate
receipt, round and publication is recorded.

## First-release scope and limitations

The supported workflow (owner addendum 3, `planning/AGENT-REVIEW-SETUP-OWNER-ADDENDUM-3.md`):

- **One controller, one developer per worktree, sequential cycle.** The developer finishes a checkpoint
  (commit, guarded push, required gates via `verify`) before review starts; the reviewer reviews exactly that
  candidate commit H, and gate receipts are bound to H. Any later material change invalidates that evidence.
- **Fixed controller version and project config during a run.** An enrollment pins the workflow fingerprint
  and project snapshot. Progress is durable; restarting from a completed checkpoint (`resume`) is supported.
- **Safe pause, not seamless recovery.** Ambiguous crashes, uncertain GitHub delivery, incompatible state or
  configuration changes stop the enrollment (PAUSED/BLOCKED) with the work preserved and the reason in
  `status`. Recovery is an owner decision: inspect, then `resume` (with `--resend-undelivered` only after
  checking the PR) or `cancel`.
- **History.** The draft PR is the live conversation record. The controller exports its own comments to
  `docs/agent-reviews/pr-<n>/` as transcript-only commits that are separate from the reviewed feature commits.

Deferred or not supported in this release. These are refused or paused rather than attempted:

| Capability | Behavior in this release |
| --- | --- |
| Two writers (controllers or foreground sessions) on one branch | Refused by the host branch lock and worktree lock |
| Upgrading the controller or refreshing project config during an active run | Not supported during a run. `activate` is an explicit owner action; it invalidates in-progress review results and requires a fresh review |
| Migrating experimental predecessor state formats | Not supported; an incompatible state version is refused (`unsupported enrollment state version`) |
| Automatic recovery from ambiguous publication (a POST whose outcome is unknown) | Pauses; the owner checks the PR and resumes with `--resend-undelivered` |
| Replacing an ownership claim whose enrollment state is missing, unreadable, foreign or recorded as a relative path | Refused (ownership needs inspection). If that enrollment is truly gone and no developer from it is running, remove the claim file by hand. State roots are resolved to absolute paths at enrollment |
| Merge, release, tagging, requesting reviewers | Never performed |

Working on the controller itself: review it with a fixed installed version. Run that enrollment's commands
through its pinned `versions/<package>/agent_review.py` path, and test candidates through the project's gates,
which run the candidate's own code. Do not reinstall or activate the controlling version for every correction.

## Permissions

| Surface | Effective permission |
|---|---|
| GitHub | The existing `gh` login (ADMIN on every onboarded repository) is reused; no new tokens, Actions, webhooks or status writes. The token is not branch-limited, so the controller enforces repository, PR number, same-repository head, head/base, draft state, the actor at every mutation, and the author of every posted comment. |
| Push | Repository wrapper where configured (Gunslinger, Buff Planner), otherwise the guarded helper: live enrollment in development, open draft PR, enrolled branch matching the project's prefix, clean tree, every effective push URL approved, fast-forward, no credential patterns in the feature diff, never force. |
| Headless developer | `settings/developer.base.json` + project extras, composed and hash-pinned per enrollment; `--permission-mode dontAsk`. Reads anywhere; edits only inside the worktree; git inspection/add/`commit -m/-F` (no amend/no-verify); the `push` (when no wrapper) and `verify` helpers for its own enrollment; the project's validation commands. Denied: direct push, `gh`, history rewriting, network fetchers, every other controller subcommand, edits to transcripts, `.claude/`, `AGENTS.md`, `CLAUDE.md`, plus per-project deploy/publish/production paths. The prompt lists the allowed prefixes. Running tests and builds the developer writes is inherent to development; the boundary is no blanket shell, no bypass mode and no GitHub writes. |
| Foreground session | User-level allowances in `~/.claude-personal/settings.json` for the controller's `status`, `review`, `finalize`, `archive`, `stop` and `push` subcommands (owner-authorized 2026-11-20). `run`, `resume`, `enroll`, `activate`, `install`, `cancel` and `init-project` stay owner-initiated. |
| Reviewer | Read-only filesystem sandbox, restricted network, approvals `never`, user config ignored (no MCP servers, plugins, hooks), connectors/browser/computer-use/image generation disabled; any sub-agent call invalidates the review. `~/.codex/config.toml` is untouched. |

## Recovery

| Situation | Behavior | Owner action |
|---|---|---|
| Host restart / crash | OS locks released by the kernel; pending publications reconciled (single same-actor marker, identical body) and sent before advancing; interrupted developer launch reconciled by session-process lookup; interrupted archive completed from its intent | `resume --reason "host restart"` |
| GitHub outage while publishing | PAUSED with the validated result preserved; resume re-checks binding and freshness, then publishes without rerunning the review | `resume` |
| Reviewer failure / malformed output | Up to 3 attempts per round, then BLOCKED; attempt files numbered monotonically | `resume` (fresh attempt budget) |
| Wrong model/effort, usage limit | BLOCKED at once; never downgrades | Restore access, `resume` |
| Head or merge base moved | HISTORICAL review or correction comment; new report needed | Reconcile, `resume` |
| Material change after ready or handoff | Ready result invalidated; superseded handoffs detected and reopened | `resume` |
| No progress (`no progress: …`) | BLOCKED with a visible status comment | Check `rounds_completed` against `round_limit` (no progress can fall on the last round). With budget left: read the outstanding findings, then either `resume --reason … --guidance <file>` to change the approach or `resume --reason …`. Either restarts the no-progress counting. With no rounds left: handle it as the round-cap row |
| Round cap (`review-round cap reached`, or no progress on the last round) | BLOCKED with a visible status comment | Owner budget decision: `resume --reason … --max-rounds N`. This continues the run immediately; guidance cannot be added in the same command. To change the approach as well, `stop` the continued run, wait, then `resume --guidance` |
| Developer invocation budget exhausted | BLOCKED (`developer invocation budget exhausted`) | Separate owner decision. No `resume` option raises it (`--max-rounds` does not), and guidance is refused. Use the existing re-enrollment procedure |
| Owner guidance snapshot missing or altered, or selection invalid | BLOCKED before any launch; `--guidance` refuses | Restore the identical captured bytes to the snapshot path (`status` shows path and digest; integrity must read `intact`), then ordinary `resume`. A damaged selection record needs supervised state repair or re-enrollment |
| Developer `blocked` / `needs_owner_decision` | Dispositions published; BLOCKED / PAUSED | Decide, `resume --reason` |
| Operational error (git/gh/process/decoding/filesystem) | Persisted PAUSED and posted when identity is established. A filesystem error is posted by type and errno only; the local `status` reason names the path | Fix, `resume` |
| Workflow reinstalled | PAUSED until `activate`; validated or ready results from the old version are re-reviewed | Review, `activate` |
| Mission, mission snapshot, permission file or a record changed | BLOCKED | Restore or re-enroll |
| Abandon an enrollment | `cancel`: CANCELLED, claims released, history kept | — |

## Costs and limits

Both roles use existing subscriptions (Claude claude.ai login, Codex ChatGPT
Pro). Usage is recorded per role: Claude `total_cost_usd`/`modelUsage` per
invocation (a list-price estimate on subscription auth) and Codex token counts
and plan type per review. No combined cost is claimed. Defaults: 5 review
rounds per checkpoint, 3 attempts per round, 30 developer invocations, 3-round
no-progress limit, 8 h soft developer deadline + 1 h grace, 60-minute reviewer
timeout. A review of the ~3,000-line controller took 5–6 minutes and about
1M (mostly cached) input tokens.

## Install, upgrade, disable

```powershell
python C:/Dev/development-process/agent_review/agent_review.py install --dest C:/Dev/agent-review
python $ar activate --enrollment <id>   # per enrollment, between runs, after reviewing the change
```

**Install and activate.** `install` adds a new immutable version under
`C:\Dev\agent-review\versions\` and points `current.json` at it. Existing
versions are never modified or removed, so it does not wait for running
controllers: a running controller and its helpers keep the code they loaded,
and each enrollment stays pinned to its version. Under the new version an
enrollment pauses until you `activate` it. Activation is an explicit owner
decision between runs; results validated under the old version are reviewed
again.

**Pause (keep everything for later).** `stop` only writes a stop request and
returns at once. The controller pauses at its next safe boundary, and an active
developer invocation first finishes its own work and any runtime restoration.
Wait until `status` shows a status other than `ACTIVE`, `developer_running`
false and `lock_holder` null. Keep the installed version and the state, then
continue with `resume`.

**Permanent disable.** Do not delete anything right after `stop`.
1. `stop` each running enrollment and wait for the paused state above. For a
   project with `runtime_lock_paths`, also wait until those lock files are gone
   (the runtime was restored).
2. `cancel --reason …` each remaining enrollment (ACTIVE, PAUSED, BLOCKED or
   AWAITING_OWNER_REVIEW). Cancel itself refuses, leaving the enrollment PAUSED,
   while a developer, a push/verify helper or a runtime transaction is still
   live. Repeat it until it reports `CANCELLED`, which releases both ownership
   claims.
3. Only then delete or rename `C:\Dev\agent-review\`, remove the allowances
   from `~/.claude-personal/settings.json`, and delete the state in
   `~/.agent-review\` and the host files in `C:\ProgramData\agent-review\`.

No GitHub settings, tokens, Actions or webhooks exist to revoke, and the Codex
configuration was never edited. A claim whose enrollment state is missing or
unreadable blocks a new enrollment of that branch until you inspect it (see
"First-release scope and limitations").

## Tests

```powershell
python -m unittest discover -s agent_review -p "test_*.py" -v
$env:AGENT_REVIEW_LIVE = "1"; python -m unittest agent_review/test_live_smoke.py -v   # real models
```

The behavior suite uses real temporary Git repositories, OS locks, state and
archive commits, and stubs only the model and GitHub boundaries with labeled
simulated responses. The live smoke runs a real headless Claude Opus developer
(including the `verify` gate and the guarded push helper) and a real Astra
reviewer against a harmless temporary repository with simulated GitHub.
