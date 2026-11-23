<!-- agent-review:v1 enrollment=devproc-claude-foreground-development-20261122110938-f02a key=r01-request part=1/1 sha256=f107a7b42be251fbcb2c919ca335200e5ce529d90911e944ccdfc59c40210ab3 -->
### Claude Opus — review request — round 1 — candidate `94a7d8feba`

| Field | Value |
|---|---|
| Request ID | `devproc-claude-foreground-development-20261122110938-f02a-r01-e6ff84` |
| Checkpoint | `final` (final) |
| Candidate H | `94a7d8febabe5973f5e99203ec3b11b1553b5093` |
| Target B (`main`) | `a2a14d8e4b0e080bed34683ae2dc8eb123e4524b` |
| Merge base M | `a2a14d8e4b0e080bed34683ae2dc8eb123e4524b` |
| Mission | `foreground-development-mission` sha256 `6767591f27` |
| Workflow | `591a9f2599` |
| Owner guidance | none |
| Owner amendments | none |
| Developer observed | foreground session `4c80174b-08e3-4c0d-8e6d-7ffb639a948a`: models ['claude-opus-5-5'], effort ['high'] (CLI-recorded transcript) |
| Reviewer requested | Codex `gpt-6.2-astra`, effort `max`, read-only sandbox |
| Round budget | 1 of 5 |

**Scope:** The complete mission as written.

**Exit conditions:**
- Every requirement of the mission is implemented, with evidence appropriate to each claim; no requirement is weakened or silently dropped.
- Validation follows the repository's own instructions; commands, results and limits are reported honestly.
- Deviations, limitations and deferred optional items are stated explicitly, separate from required work.

**Developer summary:**

Foreground (main-conversation) development, implemented in the owner's interactive session (this enrollment's developer) as one coherent batch on top of merged main (PR #6). Mission: planning/FOREGROUND-DEVELOPMENT-MISSION.md (Part A owner task, Part B owner review, verbatim).

1. Setup instructions (A.1): README 'Running a mission' now shows `--mode foreground` as the normal interactive path (enroll, status check, review, finalize) and headless only for explicitly requested unattended work; a new 'Foreground development' section describes the cycle. The CLI default stays `headless` for script compatibility; the docs require `--mode` explicitly.

2. Review result (A.2): the foreground `review --report` path is now `review_command()`. On success it prints, under `review` on stdout, the latest accepted review: round, decision, candidate (H), review_reference (PR comment URLs), structured_review (envelope path), continuation (the reviewer's decision_rationale taken unchanged from the authenticated envelope; digest checked, a missing/altered envelope is reported as `problem`, never reconstructed), findings, pending_findings, prior_finding_assessments, the guidance/amendment revisions and `next`. `guarded()` gained an `extra` hook for this; progress never goes to stdout.

3. Live output (A.3): new `LiveLog` (enrollment `live.log`, path in `status.live_log`; echoed to stderr only on an interactive terminal), `EventTail` (follows the reviewer's `events-N.jsonl` while Codex runs; `render_codex_event` shows commands, exit codes, agent messages and turn usage, never reasoning items) and `stream_process` (gate stdout/stderr read concurrently, each line logged as it arrives). `run_gate` builds the receipt exactly as before: stdout then stderr, sanitized, same log/digest, same timeout text. Review attempts log their start/end, and the review command logs the accepted verdict plus the final review text.

4. Foreground owner amendments (A.4): `amendment_refusal` accepts a foreground enrollment ACTIVE in develop/review/finalize (FOREGROUND_AMENDMENT_STATES) in addition to the existing stopped boundaries; a running review/finalize holds the writer lock (refused), a push/verify helper holds the helper lock (refused), an unended reviewer attempt is refused, all other admission checks unchanged. The resume output carries `effective_task` (mission path/sha256 and amendments revision/sha256/precedence/full text); `status --instructions` prints the same read-only. A foreground report binds to the selected amendments only when the session's CLI-recorded transcript shows a tool result containing that sha256 at/after capture (`ClaudeDeveloper.session_shown`); otherwise the report is refused with the display command. `status.amendments.selected.shown_in_foreground_session_at` reports the observation. Foreground `resume` now settles queued publications before returning (an amendment's handoff-superseded corrections are published at once). The reviewer already received owner-amendments.md byte-exact; existing freshness rules apply unchanged.

5. Session verification (A.5): `session_provenance` also collects the recorded permission modes; `foreground_session_problems` (Opus on every main-thread turn, policy effort, permission mode recorded and not bypassPermissions) runs at foreground enrollment (refusal before anything is created; `enroll` accepts an injected developer for the simulated boundary), at every report (verify_foreground_developer, Stop BLOCKED) and in `status.foreground_session`, which also states that the headless permission profile is not applied. The reviewer's provenance line names the permission modes.

6. Docs: README (setup, foreground section, amendment boundary rule, playbook rows, permissions row) and protocol sections 9 and 10. Owner Part B item 4: the R4-F1 sentence is replaced with the owner's wording.

Tests: new ForegroundDevelopmentTests (5) over the real Git/state/lock/archive fixtures with simulated Claude, Codex and GitHub: (a) the session's review returns the continuation/reference/candidate, the correction cycle reaches a current handoff with the expected PR history; (b) reviewer activity is visible in the live log while the simulated reviewer is still running, reasoning is not shown; (c) gate output is visible before the gate finishes (the gate exits 0 only if it observed its own first line in live.log) and the receipt/log/digest are unchanged; (d) a session amendment is refused while review/helper locks are held, applied at the handoff without a model launch, delivered in the output, refused for a report before display, re-displayed by status --instructions, reaches Codex byte-exact with the original mission, a stale ready result cannot finalize, and a fresh report on unchanged source reaches a new current handoff with counters intact; (e) enrollment refuses (nothing created) on bypassPermissions, an unrecorded mode, another model or another effort, and a review from a bypass session stops BLOCKED before any reviewer launch. Fixture changes: the simulated developer gained `permission_modes`, `session_shown`/`show`, and is injected into `enroll`; one obsolete refusal case ('foreground mode' amendments refused) was replaced by a foreground state outside every boundary (ACTIVE/done), still refused.

Real-interface check (supplemental, outside the repository): a scratch driver ran this candidate in foreground mode on a fixture repository with the REAL Codex gpt-6.2-astra/max reviewer (3 reviews), simulated GitHub and this session's real transcript (opus-5-5/high/auto, problems []). Its live.log was followed in the Claude conversation with a monitor: gate lines arrived second by second while the gate ran, Codex commands/messages arrived while Codex ran; round 1 changes_required with a 'Continuation for Claude', round 2 ready; an amendment applied from the session superseded the ready result, a report before display was refused, then Codex judged the amended candidate against OWNER AMENDMENT 1 (ready) and the handoff was posted.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/0c4d4d6dd16d5a3130b9b415168715b4060c0cf58dfefd58484aef692a00b982/agent_review.py verify --enrollment devproc-claude-foreground-development-20261122110938-f02a --gate unit | yes | pass | 664.9s | Required gate on pushed candidate 94a7d8f: the full unit suite run by the pinned controller; receipt in evidence/. Live-model smoke skipped in this gate. |
| python -m unittest agent_review.test_agent_review.OwnerAmendmentTests agent_review.test_agent_review.ForegroundDevelopmentTests agent_review.test_agent_review.AmendmentBoundaryTests | no | pass | 132s | 23 focused tests on the final content before commit (real Git/state fixtures; Claude, Codex and GitHub simulated). |
| scratch demo_foreground.py (candidate controller, real Codex reviewer, simulated GitHub, this session's real transcript) | no | pass | about 6 min | Supplemental real-interface check of live output and a foreground amendment; developer steps scripted; not a repository gate. Its own summary printer read status from a second controller instance (demo-script bug); the enrollment state was AWAITING_OWNER_REVIEW. |

**Evidence references:**
- candidate 94a7d8febabe5973f5e99203ec3b11b1553b5093 (pushed through the guarded push helper)
- unit gate receipt in this enrollment's evidence/ for 94a7d8f
- agent_review/test_agent_review.py ForegroundDevelopmentTests
- Limitation: the CLI default --mode remains headless (compatibility); docs require --mode explicitly
- Limitation: Claude Code shows tool output only on completion; live output is a file (status.live_log) followed with a monitor or Get-Content -Wait
- Limitation: foreground --guidance stays headless-only (approach guidance is given to the session directly)
- Deferred optional items: none

_Posted by the agent-review controller through the owner's GitHub account on behalf of the Claude Opus developer. Automated request; not a human review._
