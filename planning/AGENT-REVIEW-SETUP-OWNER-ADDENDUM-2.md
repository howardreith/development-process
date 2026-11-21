# Agent review setup — owner addendum 2 (2026-11-20)

Owner instruction after the controller-core review stopped on the no-progress
rule (round 4, PR #194 in the tabletop repository):

> Continue and proceed until everything is fixed and this is a reliable system
> we can depend on for long-form development of complex features. You have
> authorization to modify the settings.json with those necessary permissions.
> Yes, we should make a dedicated repo for this tool's source, not keep it in
> the tabletop repo. I have created the development-process repo for this
> purpose which is in Dev\development-process. Don't worry about onboarding
> nima for now. Onboard everything else. I have added development-process to
> the list of repos to which ChatGPT codex has access.

Implementation response:

- The controller source moved from the tabletop repository
  (`tools/agent_review/` at `a7a008e`) to this repository (`agent_review/`).
  Its earlier review history stays archived on tabletop PR #194
  (`docs/agent-reviews/pr-194/`); the review continues on this repository's
  own draft PR.
- The user-level Claude allowances for the controller's `status`, `review`,
  `finalize`, `archive`, `stop` and `push` subcommands were added to
  `~/.claude-personal/settings.json` (owner-authorized).
- Every primary Git repository under `C:\Dev` except nima has a project config
  in `agent_review/projects/`, each validated with `check-project`.
- The review continues until the reviewer passes the final checkpoint; owner
  resume after a no-progress stop restarts that rule's counters.
