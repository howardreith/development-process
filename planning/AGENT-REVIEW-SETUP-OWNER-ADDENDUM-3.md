# Agent review setup — owner addendum 3 (2026-11-21): first-release scope

This addendum changes the release scope. It takes precedence over the setup
brief and earlier addenda where they conflict. Owner instruction (summarized
faithfully; key sentences quoted):

> We need to bring this workflow to a usable first release. The current setup
> is spending too much time on recovery, archival synchronization, and
> compatibility machinery. [...] Make the smallest changes needed to complete
> the supported workflow below.

## Required outcome

- Reusable across the configured `C:\Dev` repositories, excluding NIMA.
- Claude Opus/high is the primary developer; Codex `gpt-6.2-astra`/high is the
  independent reviewer. They exchange substantive findings and responses
  through the GitHub PR, continue normal development without the owner relaying
  messages, and leave the final result for the owner's review. No automatic
  merge or release.

## Supported first-version conditions

- One controller, one active developer per worktree, and a sequential
  development → validation → review cycle.
- The developer finishes a checkpoint before validation and review begin.
  Required validation and the review apply to the actual candidate commit;
  later material changes invalidate the relevant evidence.
- The controller version and project configuration stay fixed during a run.
  Durable progress is preserved and restarting from a completed checkpoint is
  supported.
- For ambiguous crashes, uncertain publication, incompatible state, or
  configuration changes, a clear safe pause is acceptable: preserve all work and
  explain recovery. Seamless automatic recovery from every interruption is
  outside this release.
- Not expanded in this release: concurrent foreground orchestration, upgrades
  during active runs, migration of experimental predecessor state formats.
  Unsupported operations must be refused clearly rather than proceed unsafely.

## History

- Keep all existing code commits and PR discussion. The PR is the live
  conversation record; a one-way transcript export preserves it in Git
  separately from the reviewed feature commit. Continuous reconciliation of
  every superseded comment fragment and archive supplement is not a condition
  of source-code correctness. The existing archive path is retained and changed
  only where it blocks the supported workflow.

## Review classification for this release

Findings are classified as:

1. **Material defects in the supported workflow** — e.g. wrong candidate or
   model acceptance, ignored failed validation, conflicting writers, lost work,
   permission violations, false readiness with unresolved correctness findings.
   These remain blockers and are never reclassified as polish.
2. **Problems confined to explicitly disabled or deferred capabilities** — no
   capabilities are added to satisfy them; the capability and limitation are
   recorded in the documentation (an unsupported operation that is not refused
   clearly is a material defect).
3. **Optional improvements.**

## Procedure and stopping rule

- Work on this controller uses a fixed review procedure (the installed
  controller is not re-installed or re-activated for each correction) and
  isolated candidate testing (gates run the candidate's own code).
- Completion attempt: one focused review, one batched correction pass, one
  targeted recheck. If a material blocker remains, stop with its concrete cause
  and the smallest next decision; do not extend into another hardening cycle.
- Demonstrate one small, real unattended task in an authorized repository with
  the actual models and a real GitHub draft PR: development, candidate
  validation, review publication, continuation and final owner handoff (a
  correction cycle only if the reviewer finds a genuine defect).
