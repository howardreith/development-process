<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r03-dispositions-5c9af28b75 part=1/1 sha256=5c9af28b75b0ed3d71dc6d7e05481308cc48c03e02e44ea0d67120d4bb824eb5 -->
### Claude Opus — finding dispositions — round 3

Candidate after corrections: `8c233d0c2940065d2555e9d02d857a096cd5852d`

- **R3-F1** — `fixed` — commits: `b81d2feb17`
  Controller.resume settles already-queued publications and public operations (the amendment's corrections and PR-body update) before refusing an exhausted budget; development stays blocked. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_an_ordinary_resume_at_the_cap_finishes_the_queued_corrections_and_stays_blocked: after an interruption right after the amendment's state save on a handed-off last round, two ordinary resumes with the original limit each refuse, the reopened notice, the not-current correction, the BLOCKED notice and the PR body appear exactly once, counters and limit are unchanged, helpers and report admission stay closed.
- **R3-F2** — `fixed` — commits: `b81d2feb17`
  develop_step resolves the developer executable (self.developer.exe) after the integrity checks and before the charge and launch intent; a failure stops BLOCKED with nothing charged. Transcript observation stays executable-free. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_a_missing_executable_never_charges_a_headless_invocation: through run and then resume, both attempts stop BLOCKED, invocations stay 0, no launch record, no developer call.
- **R3-F3** — `fixed` — commits: `b81d2feb17`
  review_round runs require_foreground_launcher before every fresh attempt in its loop (automatic retries included) as well as at entry; an outside caller is refused (UsageError) while a policy mismatch in the enrolled session is a persisted Stop BLOCKED; publication-only recovery of an intact result returns earlier. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_provenance_is_checked_again_before_an_automatic_reviewer_retry: the first simulated attempt fails retryably while the session gains an ineligible turn; the second reviewer never starts, nothing is charged, the command exits BLOCKED with the provenance reason.
- **R3-F4** — `fixed` — commits: `b81d2feb17`
  The status dispatcher refuses --instructions (full or --part) when the loaded state's enrollment_id differs from the requested ID, before rendering anything. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_instruction_display_never_reads_another_enrollments_amendment: with the claim pointed at another valid enrollment holding an amendment, both forms exit 4 and output neither its text nor a delivery marker.
- **R3-F5** — `fixed` — commits: `b81d2feb17`
  The watch dispatcher closes its log handle in a finally block. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_watch_refuses_worktree_aliases_and_ownership_records_as_its_log records no ResourceWarning after gc for a separate log.
- **R2-F3** — `fixed` — commits: `b81d2feb17`
  watch keys actions by (developer, invocation) and (reviewer, round, attempt); the status line names the attempt, shows `none observed yet in this attempt` (stall timing from the attempt's start) when the current attempt has no event, and labels a pending gate whose helper PID is alive as `identity unconfirmed`. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_watch_attributes_activity_to_the_current_attempt: during a retry with an older completed attempt, the current attempt shows none observed and no earlier text; after its first event that event is shown; a marker whose PID belongs to another live process reads identity unconfirmed.
- **R2-F4** — `fixed` — commits: `b81d2feb17`
  watch_log_problem also protects the host registry/locks folder and the worktree's git dir (ownership marker and writer lock) and refuses any existing target with other hard links; the dispatcher checks the state's identity before authorizing the path. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_watch_refuses_worktree_aliases_and_ownership_records_as_its_log: an external hard link to a worktree file, the host claim and the worktree marker are refused, all protected files stay byte-identical, and a separate log receives the feed.
- **R2-F5** — `fixed` — commits: `b81d2feb17`, `8c233d0c29`
  amendment_parts cuts by each character's JSON-escaped width (DELIVERY_PART_JSON_CHARS = 9000 printed characters), so the single-result vs multipart decision and every part are bounded by the serialized display; the digest and complete-content check per part are unchanged. agent_review/test_agent_review.py ForegroundRoundThreeTests.test_amendment_parts_are_sized_by_their_serialized_display: an escape-heavy amendment under 8,000 source characters becomes several parts; the resume output and every part display stay under 12,000 characters; one missing part refuses, all parts admit. Actual-interface observation: planning/evidence/pr-7-foreground-cycle.md section 5 (7,436 source / 21,361 printed characters, 3 parts of 9,614/9,614/4,513 bytes, refusal with part 3 missing, delivery observed from the real transcript, real Codex review against OWNER AMENDMENT 1).

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/0c4d4d6dd16d5a3130b9b415168715b4060c0cf58dfefd58484aef692a00b982/agent_review.py verify --enrollment devproc-claude-foreground-development-20261122110938-f02a --gate unit | yes | pass | 908.8s | Required gate on the pushed candidate 8c233d0 (controller-run full unit suite); receipt in evidence/. Live-model smoke skipped. |
| python -m unittest discover -s agent_review -p test_*.py (before committing b81d2fe) | no | pass | 1168s | 290 tests OK, 1 skipped (live smoke). |
| mutation checks on R3-F1..R3-F4 | no | pass | about 1 min | Each targeted test failed under its mutation; code restored. |
| escape-heavy amendment demonstration (scratch driver) on b81d2fe with the real Codex reviewer | no | pass | about 3 min | Fixture repository, simulated GitHub, this session's real transcript; evidence section 5. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
