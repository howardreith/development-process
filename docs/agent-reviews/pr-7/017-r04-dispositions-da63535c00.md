<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r04-dispositions-da63535c00 part=1/1 sha256=da63535c00410e11e77090d914f906a8dd58f9e15ced9591d160503a745036a7 -->
### Claude Opus — finding dispositions — round 4

Candidate after corrections: `167b8db88fafb2a6a283d88ca0dbc7eb220a38b4`

- **R2-F4** — `fixed` — commits: `5158b1f393`
  The `--log` option is removed: `watch` opens no file for writing at all, so no destination (linked-worktree common or per-worktree Git metadata, ownership markers, host claims, aliases) can be written by the observer, whether or not Git-directory lookup succeeds. Console observation is unchanged; the README shows redirecting the console feed to a file of the owner's choosing. agent_review/test_agent_review.py ForegroundRoundFourTests.test_watch_has_no_file_output_and_leaves_every_record_untouched: the parser rejects --log; a console watch leaves every file in the enrollment state, the worktree, its Git dir and the host registry byte-identical (nothing created or removed); identity mismatch still shows nothing of the other job.
- **R4-F1** — `fixed` — commits: `5158b1f393`
  At an exhausted budget, Controller.resume settles queued publications first; when the enrollment is foreground with an applied amendment and its saved status is not the budget blocker (for example PAUSED from a resolved PR-body outage), it restores BLOCKED with budget_block_reason(), records the transition and publishes the BLOCKED status once; outstanding failures still raise from settle_publications. agent_review/test_agent_review.py ForegroundRoundFourTests.test_a_resolved_publication_outage_at_the_cap_restores_the_budget_blocker: the queued PR-body edit fails once after amending a handed-off final round (PAUSED while it lasts); recovery with the original limit, then a replay, leave BLOCKED with the budget reason, the PR body updated, one reopened notice, one not-current correction, exactly one restored BLOCKED notice, unchanged counters and closed helpers and admission.
- **R4-F2** — `fixed` — commits: `5158b1f393`
  require_foreground_launcher keeps the full transcript-read diagnostic in local state notes and puts only the failure type (and errno) in the policy stop, which is published; an observed model, effort or permission mismatch remains a persisted BLOCKED stop. agent_review/test_agent_review.py ForegroundRoundFourTests.test_a_transcript_failure_at_reviewer_admission_publishes_no_private_filename: the transcript becomes unreadable (distinctive filename outside the home folder) before an automatic retry; the command stops BLOCKED, one reviewer call, no round charged, no PR comment or stop reason contains the filename, the reason names PermissionError and the local notes contain the filename.
- **R4-F3** — `fixed` — commits: `5158b1f393`
  watch reads the whole file at attachment, replays only its tail and keeps the latest displayable action (labeled `before this watch started`, since its own time is unknown); it records the time of the latest complete event record separately and measures silence from it (or from the attempt start when nothing has arrived). agent_review/test_agent_review.py ForegroundRoundFourTests.test_watch_measures_silence_from_the_latest_event_and_finds_the_latest_action: an aged attempt with a visible command followed by 20 filtered records shows that command and a genuine 1h stall; a fresh non-displayable record clears the stall while keeping the command; 30 quiet minutes later the stall is reported. A mutation measuring silence from the last displayed row makes it fail.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/0c4d4d6dd16d5a3130b9b415168715b4060c0cf58dfefd58484aef692a00b982/agent_review.py verify --enrollment devproc-claude-foreground-development-20261122110938-f02a --gate unit | yes | pass | 698.1s | Required gate on the pushed candidate 167b8db (controller-run full unit suite); receipt in evidence/. Live-model smoke skipped. |
| python -m unittest discover -s agent_review -p test_*.py (before committing 5158b1f) | no | pass | see receipt | Full suite on the committed content. |
| mutation checks on R4-F1..R4-F3 | no | pass | about 1 min | Each targeted test failed under its mutation; code restored. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
