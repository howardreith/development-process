# agent-review: Claude Opus develops, Codex GPT-6.2 Astra reviews

A machine-level development workflow for the GitHub repositories under
`C:\Dev`. Claude Opus (high effort) implements a mission; Codex with GPT-6.2
Astra (`gpt-6.2-astra`, high reasoning effort) independently reviews each
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
game transaction is active. Deploy, install, publish, live-mod, store-submit,
migration and production scripts are denied to the headless developer per
project. Plans: `single` (any mission), `black-tentacles`, `agent-review-setup`.

## Architecture

```text
 owner ──start/stop/resume──▶ controller (python, this host, one writer per branch)
          ┌─────────────────────┼──────────────────────────────┐
          ▼                     ▼                              ▼
  Claude Code -p          Codex exec (read-only)          gh (owner's auth)
  opus / high             gpt-6.2-astra / high            draft PR comments,
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
  -c model_reasoning_effort="high" -c windows.sandbox="elevated" --sandbox
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
python $ar status  --enrollment <id> [--remote]
python $ar stop    --enrollment <id> --reason "..."
python $ar resume  --enrollment <id> --reason "what changed" [--max-rounds N]
python $ar cancel  --enrollment <id> --reason "..."
```

Plans with intermediate checkpoints and `required_gates` go in `plans/` (or
`~/.agent-review/plans/`). Exit codes: 0 done/awaiting owner, 2 BLOCKED,
3 PAUSED, 4 refused.

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
| Round cap / no progress | BLOCKED with a visible status comment | Decide; `resume --reason … [--max-rounds N]` (restarts the no-progress counters) |
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
python $ar activate --enrollment <id>   # for each running enrollment, after reviewing the change
```

`install` refuses while any controller holds a lock. To disable: `stop` or
`cancel` running enrollments, delete or rename `C:\Dev\agent-review\`, and
remove the allowances from `~/.claude-personal/settings.json`. State in
`~/.agent-review\` and claims in `C:\ProgramData\agent-review\` can then be
deleted. No GitHub settings, tokens, Actions or webhooks exist to revoke;
Codex configuration was never edited.

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
