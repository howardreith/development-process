# Agent review setup — acceptance report

Mission: `planning/CLAUDE-GITHUB-REVIEW-SETUP.md` (owner brief), behavioral
specification `docs/GITHUB-AGENT-REVIEW-PROTOCOL.md`, owner addenda 1–3 in
`planning/`. Addendum 3 sets the first-release scope used below. Setup PRs:
tabletop #194 (pilot rounds 1–4, then integration only) and
howardreith/development-process #1 (the controller, rounds 1–12). Live task:
howardreith/development-process #2. All are drafts with no requested reviewers.

This report states what was demonstrated with **real models**, what with
**labeled fixture simulations**, and what remains open.

## Environment established (2026-11-20)

| Item | Observed |
|---|---|
| Repository | `C:\Dev\KingmakerGunslingerLab\repo\KingmakerGunslinger`, origin `howardreith/KingmakerGunslingerAndOtherTabletopRules`, default branch `master`, no branch protection or rulesets, no hosted CI |
| Worktree | `C:\Dev\KingmakerGunslingerLab\worktrees\agent-review-workflow` (other 40 worktrees untouched) |
| Claude Code | 2.1.329, claude.ai subscription login (`apiKeySource: none`), config `~/.claude-personal` via the account shim |
| Codex CLI | 0.170.0, ChatGPT login (Pro plan) |
| gh | 2.99.0, login `howardreith`, scopes `gist, read:org, repo, workflow`, ADMIN on the repository — reused, unchanged |
| Push | Existing guarded wrapper `codex-policy/Push-KingmakerGunslinger.ps1` — reused, unchanged |
| Python | 3.14.7 (standard library only; no new dependencies) |

## Model configuration and provenance (WF01)

| Role | Requested | Observed (CLI/API metadata, not model statements) |
|---|---|---|
| Developer | `claude -p --model opus --effort high` (+ `--session-id`/`--resume`) | init event and API `message.model` = `claude-opus-5-5`; session transcript effort = `high` |
| Developer (foreground pilot) | this interactive session | transcript: every main-thread turn `claude-opus-5-5`, effort `high` |
| Reviewer | `codex exec -m gpt-6.2-astra -c model_reasoning_effort="high" --sandbox read-only` | rollout thread settings and every turn: `gpt-6.2-astra` / `high`, sandbox `read-only`, approval `never`, network `restricted` |

Limitations: the Claude init event does not report effort (the transcript
does); Codex does not expose a separate serving-backend model identity;
Claude's cost figure is a list-price estimate on subscription auth and Codex
reports tokens only, so no combined cost is claimed.

## Results

Evidence classes: **real** means real Claude Opus/high and Codex
gpt-6.2-astra/high exchanges published on a real GitHub draft PR. **live-smoke**
means real models on a fixture repository with GitHub simulated (the
`live-smoke` gate). **fixture** means behavior tests with real Git, state, locks
and archives, where only the model and GitHub boundaries are labeled
simulations.

| Row | Result | Evidence |
|---|---|---|
| WF01 | Pass (real) | Every developer invocation and review round records requested and observed provenance from CLI and API metadata, not from model statements. Live task: all 5 developer invocations were `claude-opus-5-5` with transcript effort `high`, and all 5 Astra rounds were `gpt-6.2-astra`/`high`, read-only, approval `never`, network `restricted`. Mismatches block (wrong-model tests, shared `developer_model_problem`). |
| WF02 | Pass (real) | development-process PR #1 received 12 review requests and 12 independent Astra results, each for its fixed candidate (H/B/M in every request). Live PR #2 received 5. |
| WF03 | Pass (real) | Real finding cycles. On PR #1, findings were fixed, rebutted (three rebuttals accepted under addendum 3) and rechecked; controller-core passed in round 12. On live PR #2, the unattended headless developer received 6 genuine findings, posted dispositions with corrective commits, and the reviewer verified all six by round 4. No defect was introduced deliberately. |
| WF04 | Pass (fixture) | Stale or moved H, B or M, archive-only successors and a changed review contract all invalidate reuse (StaleCandidateTests, request-contract tests, live-branch-head readiness). |
| WF05 | Pass (fixture) | Wrong model, malformed or truncated output, a failed process, missing fields, duplicate JSON members and conflicting provenance cannot produce readiness (InvalidReviewTests, provenance tests). |
| WF06 | Pass (fixture) | Lost responses and lagging listings are reconciled without duplicate comments. An ambiguous POST pauses for the owner (`--resend-undelivered`) instead of being re-posted blindly. |
| WF07 | Pass (fixture, real) | Stop and resume preserve the session, budgets, publications and lock (StopResumeLockTests). On live PR #2, two operator resumes continued the same Claude session. |
| WF08 | Pass (real, fixture) | The no-progress stop fired visibly on PR #1 and on live PR #2. Exhausted budgets, unresolved correctness findings and missing or failed required gates block with a visible status. |
| WF09 | Pass (fixture, real) | Transcript-only archive commits preserve readiness only under the inventory and hash check. Live PR #2 archived its records as transcript-only commits after the reviewed candidate. |
| WF10 | Pass (fixture) | Wrong repository, PR, actor or marker is refused before dispatch. Comment text is never executed. Helpers require enrollment authority under a lock. Headless permissions are isolated (the `permissions` gate shows real launches denying a user-level allowance). |
| WF11 | Pass (real) | Live PR #2 ended AWAITING_OWNER_REVIEW: a draft with no requested reviewers, a handoff receipt naming reviewed source `bc4b300` and transcript-only archive `b89fa6c`, and a PR status section. The effective permissions and the exact launch, resume and stop commands are in `agent_review/README.md`. |
| WF12 | Pass (real, fixture) | On PR #1, controller-core (intermediate) passed and advanced to setup-final without owner input. Fixture: HeadlessCycleTests. |

### Live task (development-process PR #2)

Mission `planning/LIST-COMMAND-MISSION.md`: a read-only `list` command. It used
the plan `list-command` with the `unit` gate required, ran headless and
unattended, and was enrolled with the installed controller.

- Development: 5 Claude Opus/high invocations in one session (about 15 min
  each for the implementation work). The developer's own `push` and
  `verify --gate unit` helpers ran, and a passing unit receipt is bound to each
  of the 5 reviewed candidates:

  | Round | Candidate H | What it was | Decision |
  |---|---|---|---|
  | 1 | `af2d176` | Implementation | `changes_required` |
  | 2 | `b0df762` | Corrections (R1-F1..F4) | `changes_required` |
  | 3 | `b66d172` | Corrections (R1-F3, R1-F4, R2-F1) | `changes_required` |
  | 4 | `c391eff` | Corrections (R1-F4, R3-F1) | `ready_for_owner_review` |
  | 5 | `bc4b300` | Transcript-only successor of `c391eff` (adds only archive records); the fifth invocation submitted a fresh report and unit run for it after the activation described below | `ready_for_owner_review` |

  The implementation work therefore consists of four candidates from four
  invocations; the fifth invocation changed no source.
- Review: 5 Astra rounds published on the PR, with dispositions between them.
  6 defects were found and verified fixed: malformed registry entries,
  damaged state, relative state roots, link and network-path inspection,
  cross-enrollment state, and an unreadable registry.
- Permissions: two attempts to read controller state or AppData outside the
  profile were denied, as intended.
- Stops: after round 3 the no-progress rule stopped the run on R1-F4 (the
  reviewer rejected a fix twice). An operator resume let the pair continue
  without changing the mission, and round 4 returned `ready_for_owner_review`.
- Handoff defect found by this task: GitHub's PR view lagged the transcript
  archive push, so readiness saw the previous head and paused, on every retry.
  The pause was safe. The fix waits a bounded time for the PR view when the
  branch itself is already at the archive head (FirstReleaseTests
  `test_handoff_waits_for_a_lagging_pr_view`).
- Handoff: the fixed version was activated between runs, so the same work was
  reviewed again under it (round 5: `ready_for_owner_review`, 5 of 5 rounds
  used). Finalize then completed: AWAITING_OWNER_REVIEW, reviewed source
  `bc4b300`, archive `b89fa6c`.

**Handoff readback (2026-11-21, read from GitHub and the enrollment state).**
`gh pr view 2` reports an open draft, no requested reviewers, head
`b89fa6c72dd56de945b255d3320e19059bd30065`. The handoff status comment
(`key=final-status-b89fa6c72d`, posted 2026-11-21T08:09:52Z) names reviewed
source H `bc4b30043bc952e204fb76d0dfc423055d99c117` (round 5, Codex
`gpt-6.2-astra`/`high`), archive A `b89fa6c…`, merge base
`2e8f58127ea0…`, reviewed target tip `7358a159057a…`, the observed developer
session (init `claude-opus-5-5`, effort `high`), and no open non-blocking
items. `git diff --stat bc4b300 b89fa6c` shows only four added transcript files
under `docs/agent-reviews/pr-2/` (264 lines). `status --remote` reports
AWAITING_OWNER_REVIEW, `handoff_current: true`, no pending publications, and no
running developer.

**Integration status.** PR #2 is stacked on the PR #1 branch, which has moved
since PR #2 branched; GitHub reports it as conflicting. A three-way merge is
clean for the controller and tests and has one README conflict, where PR #1's
Black Tentacles section and PR #2's `list` documentation were added at the same
place (both are kept). The owner's sequence: land PR #1, retarget PR #2 to
`main`, merge `main` into it, resolve the README, run the required validation on
the combined candidate and review the integration change.

### Supported limitations (addendum 3)

See `agent_review/README.md`, section "First-release scope and limitations".
One controller and one developer per worktree, run sequentially. Controller
version and project config stay fixed during a run. Safe pauses with owner
recovery instead of seamless recovery. No migration of predecessor state
formats. A claim whose enrollment state cannot be read is refused instead of
replaced (round 13, R13-F1). Costs: Claude reports list-price estimates on subscription auth (for
example about $4.27 for one live-task invocation); Codex reports tokens only.
