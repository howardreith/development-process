# Mission: run the agent-review controller on any of the owner's machines

## Goal

The controller and its shipped project configs assume the machine they were
written on: `developer.executable` is `%USERPROFILE%/.local/bin/claude.exe`,
`developer.config_dir` is `%USERPROFILE%/.claude-personal` and
`reviewer.codex_home` is `~/.codex`. On the owner's second machine, Claude Code
is installed by WinGet (on PATH as `claude`), its config is `~/.claude`, and the
user-level `CODEX_HOME` points at a Codex home dedicated to another project.
Agent-review reviews must use their own dedicated Codex home there (`~/.codex`,
already signed in). Make the controller work correctly on both machines
without per-run environment workarounds.

## Requirements

1. **Reviewer Codex home is explicit.** Every Codex process the controller
   starts (review attempts, preflight, `--version`, `login status`) runs with
   `CODEX_HOME` set to the configured `reviewer.codex_home`, so the rollout the
   reviewer writes is the one the controller reads for provenance. An inherited
   `CODEX_HOME` never decides where a review runs or is verified.
2. **Machine profile.** An optional, owner-controlled file
   `<agent home>/machine.json` (default `~/.agent-review/machine.json`) may set
   only these machine facts: `developer.executable`, `developer.config_dir`,
   `reviewer.codex_home`. When present, it overrides those keys of every loaded
   project config (shipped or user-local). Unknown keys, wrong types or any
   attempt to set models, effort, permissions, gates, limits or other policy are
   refused with a clear error. Without the file, behavior is unchanged.
3. **Pinning.** The effective (profile-applied) project configuration is what
   an enrollment pins and digests, so changing the machine profile during a run
   is detected exactly like any other project-config change. Existing
   enrollments made before this change keep loading under their pinned version.
4. **`init-project` defaults.** It no longer hardcodes
   `%USERPROFILE%/.local/bin/claude.exe` or `%USERPROFILE%/.claude-personal`.
   Explicit flags win; otherwise it uses the machine profile when present,
   otherwise portable defaults (`claude` resolved on PATH and the standard
   Claude config directory). The existing nima rule is preserved.
5. **Visibility.** `preflight` and `check-project` report the effective
   executable, Claude config directory and Codex home, and whether a machine
   profile was applied.
6. **Tests.** Behavior tests in `agent_review/test_agent_review.py`, using the
   existing real-repository fixtures and stubbing only the model/GitHub
   boundaries: the reviewer's child environment carries the configured
   `CODEX_HOME` even when a different one is inherited; a valid profile
   overrides the three keys; an invalid or policy-changing profile is refused;
   a profile change after enrollment is detected; `init-project` defaults.
7. **Documentation.** A "Setting up a new machine" section in
   `agent_review/README.md`: install, the machine profile, the dedicated Codex
   home login (bash syntax for Claude Code's `!` prefix:
   `CODEX_HOME="$HOME/.codex" codex login`), `preflight`, and onboarding a new
   repository with `init-project` / `check-project`.

## Constraints

- Python standard library only; follow `AGENTS.md`. Do not change the owner
  model policy or weaken any safeguard.
- Shipped project configs keep working unchanged on the original machine.
- The required validation is the project's `unit` gate, run through `verify`
  on the committed and pushed candidate.
