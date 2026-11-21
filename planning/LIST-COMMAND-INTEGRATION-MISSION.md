# Mission: integrate the list command with main

## Context

The `list` command (draft PR #2, mission `planning/LIST-COMMAND-MISSION.md`)
was developed and reviewed on a branch stacked on the controller branch (PR #1).
That review ended at owner handoff for reviewed source `bc4b300` (archive
`b89fa6c`). PR #1 has since been merged into `main` (`2fbf851`) with its history
preserved, and PR #2 is retargeted to `main`. The owner's review asked for the
integration to be validated and reviewed as its own candidate, not treated as
covered by the earlier reviews.

## Scope

Integration only. No new capability.

1. Merge `main` into `claude/list-command` with a normal merge commit (no
   rebase, no force-push).
2. Resolve the README conflict by keeping both PR #1's Black Tentacles section
   and PR #2's `list` documentation.
3. Keep every PR #1 change intact, in particular:
   - the bounded wait for a lagging PR view at handoff and its regression test
     (`FirstReleaseTests.test_handoff_waits_for_a_lagging_pr_view`);
   - the R13-F1 enrollment-ownership fix and `EnrollmentOwnershipTests`.
4. Adjust `list` code, tests or documentation only where PR #1's merged
   behavior changes their premises. For example, claims now record an absolute
   `dir` because the state root is resolved at enrollment.

## Exit conditions

- The merge has parents `b89fa6c` (PR #2) and `2fbf851` (main), and the branch
  contains `main`.
- No conflict markers; both README sections present; the PR #1 changes above
  unchanged relative to `main`.
- The `list` behavior from the PR #2 review is unchanged: read-only, no locks,
  writes, subprocesses or GitHub calls, and damaged entries isolated.
- The required `unit` gate passes on the integration candidate.
- An independent review of the integration change (the merge's difference
  from each parent) finds no unresolved correctness issue.

## Out of scope

Deferred capabilities in `agent_review/README.md` ("First-release scope and
limitations"); new features; starting Black Tentacles.
