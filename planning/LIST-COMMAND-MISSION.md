# Mission: read-only `list` command for the agent-review controller

## Goal

Owners currently have to know an enrollment ID to inspect anything. Add a
read-only `list` subcommand to `agent_review/agent_review.py` that shows every
enrollment registered on this machine, so an owner can see at a glance what is
running, paused or awaiting review.

## Requirements

1. `python agent_review.py list` prints a JSON array, one object per enrollment
   claim found in the host registry (the directory `host_dir() / "registry"`),
   sorted by enrollment ID. Each object contains: `enrollment`, `repository`,
   `branch`, and, read from that enrollment's `state.json`, `status`, `phase`,
   `pr` (number or null) and `updated_at`.
2. A claim whose state file is missing or unreadable is still listed, with
   `status` set to `"unknown"` and an `error` field stating why. `list` never
   fails because one enrollment is damaged.
3. The command is strictly read-only: it takes no locks, writes nothing, and
   makes no network or GitHub calls.
4. Add behavior tests to `agent_review/test_agent_review.py` using the existing
   real-temporary-repository fixtures (no new stubs): at least one enrollment
   listed with its fields, an empty registry printing `[]`, and a damaged state
   file reported as `unknown` without failing.
5. Document the command in `agent_review/README.md` next to the other
   inspection commands.

## Constraints

- Python standard library only; follow `AGENTS.md`.
- Do not change any other command's behavior.
- The required validation is the project's `unit` gate, run through `verify`
  on the committed and pushed candidate.
