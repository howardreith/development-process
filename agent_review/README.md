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
python $ar resume  --enrollment <id> --reason "what changed" [--max-rounds N] [--guidance <file>]
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

### Owner guidance (`resume --guidance <file>`)

An owner decision about *how* the work should proceed (for example a changed
repair approach after a no-progress stop) reaches both agents of the same
enrollment without touching the hash-pinned mission, the project
configuration, the developer session, budgets or findings:

```powershell
python $ar resume --enrollment <id> --reason "change the repair approach" --guidance C:/path/guidance.md
```

- **Supported state.** An idle `BLOCKED` or `PAUSED` enrollment in the
  `develop` phase. Idle means no running developer (including an interrupted
  launch whose session process is still alive), no reviewer attempt without an
  end record, no push/verify helper holding the helper lock and no configured
  runtime lock. The round budget (under any `--max-rounds` passed in the same
  call) and the developer invocation budget must not be exhausted; guidance
  never raises a budget. In any other status or phase (`ACTIVE`,
  `AWAITING_OWNER_REVIEW`, `review`, `finalize`, …) `--guidance` is refused
  with exit code 4; it is never ignored. `resume` without `--guidance` behaves
  exactly as before.
- **Validation before any change.** The file is read, decoded as UTF-8 and
  hashed before the writer lock is taken; a missing or non-regular file,
  invalid UTF-8, an empty or whitespace-only document, or one over 64 KiB is
  refused. Status, phase, idleness and budgets are checked under the writer
  lock, after the host/worktree claims, before anything is written. A refusal
  (exit 4) leaves `state.json`, the `STOP` file and every counter untouched
  and launches nothing. (The command's usual identity, workflow-fingerprint
  and mission guard still runs before capture; if it finds an impediment the
  enrollment stops as for any `resume`, and nothing is captured.) Content is
  never validated as natural language.
- **Capture.** The exact bytes are copied to
  `<enrollment>/guidance/r<NNN>-<sha256 prefix>.md` and recorded in
  `state.json` (`guidance.revisions`: revision, sha256, size, source path,
  reason, time) in the same transaction as the resume. Editing or deleting the
  original file afterwards changes nothing.
- **Delivery.** Every later developer prompt (start or continuation, including
  correction re-invocations) contains the captured text, its revision and
  sha256 and the path of the in-state copy; the first invocation after a new
  revision is told that a fresh report is required. The reviewer gets a copy
  as `.agent-review-inputs/owner-guidance.md` inside its snapshot, and its
  prompt names that copy and the digest. Both prompts state that the guidance
  supplements the repair approach under the mission and does not alter models,
  permissions, budgets, acceptance criteria or finding status. In foreground
  mode the controller launches no developer: `resume` prints the in-state path
  and digest, and `status` shows them (`guidance`). The guidance text is never
  published to GitHub; only its digest is.
- **Records.** Each round records `guidance_revision`/`guidance_sha256`; the
  reviewer's `request.json`, the validated envelope, the published request and
  review comments and therefore the archived records name the digest that
  applied, or `none`.
- **Persistence and revisions.** The current revision applies to every later
  invocation, review round, controller restart and ordinary `resume`. A later
  `--guidance` with different content adds a revision and keeps every earlier
  snapshot and digest; identical content to the current revision adds none.
- **Freshness.** A developer report is bound to the guidance current when it
  was accepted. After a new revision the next review needs a fresh report,
  even on an unchanged commit. An outstanding request is not reused, and a
  validated, ready or handed-off result bound to different guidance (or to
  none) is not accepted and does not satisfy readiness. Earlier rounds keep
  their original binding.
- **Failure modes.** Before every developer launch, review request and
  reviewer launch the controller verifies the snapshot against its digest. A
  missing or altered snapshot stops the enrollment `BLOCKED` with that reason,
  before any launch or charge; an ordinary `resume` refuses to continue past
  it (the `STOP` file and counters stay). Re-supplying the identical document
  with `resume --guidance` restores the snapshot; different content is refused
  until the current revision is restored, so its record is never lost.
  Enrollments that never received guidance, including state written before
  this option existed, load, run and archive unchanged.

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
| Round cap / no progress | BLOCKED with a visible status comment | Decide; `resume --reason … [--max-rounds N]` (restarts the no-progress counters), adding `--guidance <file>` to change the repair approach |
| Owner guidance snapshot missing or altered | BLOCKED before any launch | Re-supply the identical document with `resume --guidance` |
| Developer `blocked` / `needs_owner_decision` | Dispositions published; BLOCKED / PAUSED | Decide, `resume --reason` |
| Operational error (git/gh/process/decoding) | Persisted PAUSED and posted when identity is established | Fix, `resume` |
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
