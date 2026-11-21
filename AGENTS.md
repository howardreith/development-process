# development-process agent instructions

This repository holds the machine-level development workflow for the
repositories under `C:\Dev`: the agent-review controller (`agent_review/`),
its schemas, prompts, permission base, project configs and mission plans.
Read `agent_review/README.md` (operating guide) and
`docs/GITHUB-AGENT-REVIEW-PROTOCOL.md` (behavioral specification) first.

## Engineering rules

- Python 3 standard library only; no new dependencies without an explained,
  maintained replacement for substantial code.
- Behavior tests use real temporary Git repositories and the real controller
  state, locks and archive commits. Stub only the model (Claude/Codex) and
  GitHub boundaries, with clearly labeled simulated responses. Never test
  source text.
- Focused validation: `python -m unittest discover -s agent_review -p "test_*.py" -v`
  (the `unit` gate). The real-model smoke runs only when explicitly selected:
  `AGENT_REVIEW_LIVE=1 python -m unittest agent_review/test_live_smoke.py -v`.
- Owner model policy (`POLICY` in `agent_review.py`: Claude `opus`/high
  developer, Codex `gpt-6.2-astra`/high reviewer) changes only by an explicit
  owner decision.
- Never weaken a safeguard to make a test or a review pass; fix the cause.

## Git and handoff

- Work on `claude/*` branches; the default branch is `main`. Never force-push,
  rewrite history, merge or tag without explicit owner authorization.
- When a branch is enrolled in the workflow, the controller alone posts PR
  comments and archives `docs/agent-reviews/`; push through the controller's
  guarded `push` helper and run gates with `verify`.
- After changing behavioral files (controller, schemas, prompts, permission
  base), reinstall to `C:\Dev\agent-review` and `activate` each running
  enrollment; do this only for a reviewed version.
- Never commit credentials, local machine state (`~/.agent-review`,
  `C:\ProgramData\agent-review`) or raw model event streams.
