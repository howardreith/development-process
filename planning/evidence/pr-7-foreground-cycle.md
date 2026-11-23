# PR #7 evidence: foreground development cycle, live output and owner update (2026-11-22)

Scoped, sanitized record written by the foreground developer (the owner's interactive Claude session) for the
round-1 finding R1-F12 and the evidence gaps R1-F11 and "corrected-candidate evidence". It contains only the
commands, timestamps, outputs and decisions of this task. The unrelated parts of the conversation, raw model event
streams and private state stay private. Home paths are shortened to `~`. All times are UTC.

## 1. This PR's own foreground cycle (installed controller)

| Item | Value |
|---|---|
| Enrollment | `devproc-claude-foreground-development-20261122110938-f02a`, mode `foreground`, draft PR #7 |
| Controller supervising this PR | installed package `0c4d4d6dd16d5a3130b9b415168715b4060c0cf58dfefd58484aef692a00b982` (fingerprint `591a9f25…`, from reviewed source `0a00503`), pinned for the whole run |
| Developer | this interactive Claude session `4c80174b-08e3-4c0d-8e6d-7ffb639a948a`; transcript records `claude-opus-5-5`, effort `high`, permission mode `auto` on every main-thread turn |
| Round 1 candidate | `94a7d8febabe5973f5e99203ec3b11b1553b5093` (one coherent batch), `unit` gate through `verify`: 261 tests OK (1 skipped), 664.9 s |

**Invocation by the enrolled session (16:55:51):**
`python ~/…/versions/0c4d4d6d…/agent_review.py review --enrollment devproc-claude-foreground-development-20261122110938-f02a --report <report-r1.json>`,
run as a background task. Because the installed version predates this PR's live log, the session attached a
read-only watcher to the round's reviewer event file and relayed it into the conversation with a monitor. What the
owner could see before the reviewer exited (excerpt of that watcher's feed):

```text
[16:55:56Z] == ACTIVE/review | reviewer Codex (round 1) for 0m01s | branch 94a7d8febabe | rounds 0/5
[16:56:00Z] Codex: I'll trace the mission requirements through the candidate and check which validation results the recorded commands support.
[16:56:07Z] Codex ▸ $ … Get-Content -Raw -LiteralPath '.agent-review-inputs/prior-findings.json'
[16:59:25Z] Codex: The unit receipt matches the candidate, and its log records 261 tests with one skip. I found that an ordinary status response can satisfy the amendment-delivery check without showing Claude the amendment text. …
[17:01:00Z] ACTIVE/review | reviewer Codex (round 1) for 5m05s | … | last event 72s ago
[17:07:14Z] Codex: I confirmed two recovery issues in the controller. A review can be accepted and counted without its continuation reaching the foreground command output. …
[17:10:25Z] Codex: { "candidate_commit": "94a7d8f…", "decision": "changes_required", … }
[17:10:31Z] == review round 1 accepted on 94a7d8febabe: changes_required; open R1-F1 … R1-F15
```

**Accepted review:** round 1, `changes_required`, 15 blocking findings,
[review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7082633500). The reviewer's
continuation (its `decision_rationale`, unchanged):

> The required unit gate passed. The foreground workflow can nevertheless mark an unseen amendment as delivered,
> accept an old report under the new task, and omit an accepted continuation when a review stops or recovers. The
> supplied evidence also falls short of the required demonstration in the actual Claude conversation.
>
> ## Continuation for Claude
>
> Correct amendment delivery, report freshness, session verification and round-limit handling together. Return the
> authenticated result of the round that was accepted, including on stopped and recovered paths. Make interactive
> enrollment select foreground by default and give the session the push and observation instructions that apply to
> its project.
>
> Preserve complete gate receipts, runtime restoration and credential redaction while streaming progress. Exercise
> the failure paths in the findings with real temporary repositories, controller state and harmless gate processes.
> Keep this enrollment on its pinned controller, preserve its counters and use the existing model, permission,
> publication and owner-handoff boundaries.
>
> Run the required unit gate on the corrected candidate. Supply a scoped, sanitized record of one actual foreground
> correction cycle that identifies the controller code exercised, shows activity before completion, and connects the
> accepted review to the same Claude session's correction and handling of an owner update. An isolated fixture can
> exercise the candidate without activating it on this PR or another running job.

**The session's explanation to the owner (posted in the conversation right after acceptance; excerpt, with each
bullet's detail elided; the owner did not relay or approve anything):** "Round 1 accepted: `changes_required`, 15 blocking
findings … Here's the correction batch I'm implementing now: amendment delivery and freshness (F1–F3, F15) …
round cap (F4) … session verification (F5) … accepted review on every path (F6) … gate streaming (F7–F9, F13) …
setup defaults and instructions (F10, F14) … watching headless jobs (F11) … evidence (F12) … Starting with the
controller fixes."

**Corrective action by the same session:** commit `ba32530dcf16aab3d857611dd8ff01991fadb1b0` ("round-1 corrections
for foreground delivery, recovery and streaming"), full unit suite 274 tests OK (1 skipped) before commit; the
commit that adds this record follows it; the required gate then runs through `verify` on the pushed candidate.

## 2. Demonstration on the corrected candidate (real Codex, isolated fixture)

The new capabilities belong to the candidate, which is not installed or activated on this PR or any running job. An
isolated fixture exercised them in this conversation:

| Item | Value |
|---|---|
| Controller code exercised | `agent_review/agent_review.py` of commit `ba32530`, sha256 (LF) `cf72bdc1b0f105114d3787f00a4f52c2e2d92d771539c6b56aa8aee4edd3c763`, imported from the PR worktree |
| Fixture | temporary Git repository and bare origin; foreground enrollment `t-codex-feature-20261122124120-d15c`; plan `final` with required gate `unit` (`python -u -m unittest test_calc -v`) |
| Reviewer | the REAL Codex `gpt-6.2-astra`, effort `max`, read-only (3 reviews) |
| GitHub | SIMULATED in-process (no real PR touched) |
| Developer | THIS session: the fixture enrollment was enrolled by and bound to session `4c80174b…`; the enrollment check, every report check and the delivery observation read its real transcript (models `claude-opus-5-5`, efforts `high`, modes `auto`, problems `[]`) |
| Driver | a scratch script that only executed the controller command the session handed it (`gate`, `review`, `amend`, `instructions`, `status`, `finalize`); every edit, commit and report was the session's own |

**Live output seen in the conversation before each process exited** (excerpt of the candidate's own `live.log`,
relayed by a monitor):

```text
[17:41:39Z] gate unit started on 51ab791044 (live output follows; the receipt is the record): ~\…\python.exe -u -m unittest test_calc -v
[17:41:39Z] gate unit | checking integer case 0
[17:41:40Z] gate unit | checking integer case 1
[17:41:41Z] gate unit | checking integer case 2
[17:41:42Z] gate unit finished on 51ab791044: exit 0, worktree unchanged True, 3.1 s
[17:41:54Z] review round 1 attempt 1: Codex gpt-6.2-astra/max (read-only) is reviewing candidate 51ab791044; its activity follows
[17:42:00Z] Codex: I'll check the mission against the candidate diff and use the tool transcript to verify which tests ran at the submitted commit.
[17:42:06Z] Codex ▸ $ … Get-Content -LiteralPath '.agent-review-inputs/feature.diff' -Raw
[17:44:07Z] review round 1 attempt 1 ended: valid result, decision changes_required
```

**Cycle:**

1. The session committed a deliberately incomplete first pass (`51ab791`: `add` with an integer test only) to
   exercise the correction loop, ran the gate and submitted `review --report`.
2. The command returned on stdout, under `review`: round 1, `changes_required`, `accepted_in_this_command: true`,
   candidate `51ab791…`, the review reference, and the continuation unchanged: "The unit gate passed, but its only
   assertion used two positive integers. The mission explicitly requires a negative-number test. … Continuation for
   Claude: Keep the positive integer assertion and add a unittest case with a negative operand … Exclude
   `feature.txt` from the PR diff …", findings R1-F1 (P2), R1-F2 (P3), R1-F3 (optional), and `next` naming the
   built-in push route.
3. The session explained the batch in the conversation (add a negative test; drop the unrelated `feature.txt`;
   defer the optional delay because it makes streamed output observable) and committed `9f06919`. Dispositions:
   R1-F1 and R1-F2 `fixed` (9f06919), R1-F3 `deferred_optional`. Round 2: `ready_for_owner_review`.
4. **Owner update.** A clearly labeled demonstration amendment (written by the session, not an instruction from the
   owner) was saved outside the worktree and applied by the enrolled session with `resume --amend-mission` at
   ACTIVE finalize: exit 0, revision 1, sha256 `1ca7629d…`, the round-2 ready result moved to `superseded_ready` with
   a public "ready verdict is not current" correction, phase `develop`, rounds unchanged at 2.
5. Resubmitting the round-2 report before the amended task reached the session: refused ("has not been verifiably
   displayed in this session …"). The session then displayed `status --instructions` (full text, then the delivery
   marker); `status` reported `shown_in_foreground_session_at: 2026-11-22T17:46:00.555Z` from the real transcript.
   Resubmitting the old report again: refused ("this report does not say it was prepared under owner amendments
   revision 1 …").
6. The session implemented `subtract` (`102f98b`), ran the gate (3 tests) and submitted a report citing
   "prepared under owner amendments revision 1 sha256 1ca7629d…". Codex read `owner-amendments.md` and returned
   `ready_for_owner_review`: "The candidate satisfies the original addition requirement and the subtraction
   requirement from OWNER AMENDMENT 1." Round 3 is bound to amendment revision 1; `finalize` posted the handoff
   (source `102f98b`, archive `1498e74`).

Simulated PR history of the fixture, in order: review request/review round 1, dispositions round 1, request/review
round 2, "correction — round 2 ready verdict is not current", request/review round 3 (its request carries the
public amendment rendering), "awaiting owner review".

## 3. Already-running headless jobs during the transition (R1-F11)

`list` showed one enrollment active when the owner asked for visibility: PR #6's headless run
`devproc-claude-continuation-handoff-20261122025808-720e` (pinned package `7e8bb030…`). No other enrollment was
registered. It was observed read-only from its existing developer stream and reviewer event files with the watcher
that became this PR's `watch` command (excerpt; note the interval with no new agent event while the gate ran):

```text
[15:15:16Z] == ACTIVE/develop | developer Claude (invocation 5) for 12m04s | branch 0a005034524a (last reviewed 8f8f83ee61ee: changes_required) | rounds 3/5 | dev invocations 5/30 | open R3-F1 | gate unit running on 0a005034524a for 6m52s | last event 0s ago
[15:16:16Z] ACTIVE/develop | developer Claude (invocation 5) for 13m04s | … | gate unit running on 0a005034524a for 7m52s | last event 60s ago
[15:17:17Z] ACTIVE/develop | developer Claude (invocation 5) for 14m05s | … | gate unit running on 0a005034524a for 8m53s | last event 120s ago
[15:18:17Z] ACTIVE/develop | developer Claude (invocation 5) for 15m05s | … | gate unit running on 0a005034524a for 9m53s | last event 181s ago
[15:18:41Z] == gate unit finished on 0a005034524a: exit 0, worktree unchanged=True
[15:19:08Z] == ACTIVE/review | reviewer Codex (round 4) | branch 0a005034524a | rounds 3/5
[15:23:37Z] == review round 4 accepted on 0a005034524a: ready_for_owner_review; open R4-F1
[15:23:53Z] == AWAITING_OWNER_REVIEW/done | … | reason: source 0a005034524a…, archive c868c95e582e…
```

The same observation now comes from `python agent_review.py watch --enrollment <id> [--once] [--log FILE]` of this
candidate, which was also run read-only against that (completed) enrollment's preserved files. Enrollments stayed on
their pinned versions; no second writer was started.

## 4. Round 2 of this PR, and the long-amendment delivery route (R2-F5)

**Round 2 (installed controller, same enrollment and session).** The enrolled session submitted `f04f135`
(`unit` through `verify`: 274 tests OK, 1 skipped, 713.5 s) with `review --report`; the read-only `watch` command of
the candidate relayed the reviewer's messages into the conversation while it ran, for example
`[18:04:29Z] Codex: … The amendment checks now reject a digest-only display and an unchanged old report. I found a
recovery path that can still label an earlier round as newly accepted …` and `[18:11:16Z] Codex: I found that watch
sanitizes an event for immediate display, then reuses the original text in its status line …`. Accepted at 18:16:39:
`changes_required`, 10 of the 15 round-1 findings verified, 5 reopened and 7 new
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7083478693)). The session
explained the round-2 batch to the owner in the conversation and committed it as
`97e37843a2db50d1dba252fee654ce2481b38a57` (full suite 283 tests OK, 1 skipped, before commit).

**Long amendment, in the actual interface.** Controller code exercised: `agent_review/agent_review.py` of `97e3784`,
sha256 (LF) `8fc3a4abbac9f7456bb30ad48b79b2ee17edcaba92bd4c37d49902eef1050dac`; fixture enrollment
`t-codex-feature-20261122135146-5b60`, bound to and verified against this session's real transcript; the REAL Codex
`gpt-6.2-astra`/max reviewer; GitHub simulated; developer steps by the session itself.

1. The session applied a clearly labeled demonstration amendment of 35,494 characters (a `subtract` requirement plus
   a 1,300-row reference table; written by the session, not an instruction from the owner) with
   `resume --amend-mission` at ACTIVE develop: exit 0, revision 1, sha256 `28004f1d…`, captured document 36,028
   bytes. The printed `effective_task` held no `text` but `parts: 5` and the five
   `status --enrollment … --instructions --part K` commands (the whole output was 3,910 bytes).
2. The session displayed parts 1–4 in the conversation (each output about 8.9 KB: the text slice, then
   `agent-review effective task part K/5 delivered: …`), implemented `subtract` with four reference rows
   (`ac6fd1c`, gate passed) and submitted a report citing `prepared under owner amendments revision 1 sha256
   28004f1d…`: **refused**, "has not been verifiably displayed in this session" (part 5 missing).
3. The session displayed part 5; `status` then reported `shown_in_foreground_session_at: 2026-11-22T18:52:57.271Z`
   from the real transcript, and the same report was accepted.
4. Codex reviewed against the full document: "The subtraction test checks four distinct reference rows, satisfying
   the minimum of three in OWNER AMENDMENT 1." `ready_for_owner_review`; round 1 bound to amendment revision 1;
   `finalize` posted the handoff (source `ac6fd1c`, archive `73f8a14`).

## 5. Round 3 of this PR, and an escape-heavy UTF-8 amendment (R2-F5)

**Round 3.** The enrolled session submitted `2cc19f7` (`unit` through `verify`: 283 tests OK, 1 skipped, 1098.7 s).
The first reviewer attempt was rejected by the controller's existing provenance validation (Codex's own rollout
record was malformed; attempts are not rounds) and the controller retried automatically. The accepted attempt
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7084606273)) verified 9 of the
12 pending fixes and raised R3-F1..R3-F5. The session explained the batch in the conversation and committed it as
`b81d2feb1745666ade60d2c6c8be273cc0c3cf17` (full suite 290 tests OK, 1 skipped, before commit).

**Escape-heavy amendment, in the actual interface.** Controller code exercised: `agent_review/agent_review.py` of
`b81d2fe`, sha256 (LF) `eefca244304f7b1c73659c3045c8d4c3baa94952064d074f6d576336d042c267`; fixture enrollment
`t-codex-feature-20261122150639-e44d`, bound to and verified against this session's real transcript; REAL Codex
`gpt-6.2-astra`/max; GitHub simulated; developer steps by the session.

1. A labeled demonstration amendment (written by the session, not an instruction from the owner): a `subtract`
   requirement plus 240 lines of localized notes with emoji, kana/kanji and U+2212: **7,436 source characters, but
   21,361 characters once JSON-escaped**, the form the displays print. Under the round-2 rule (8,000 source
   characters per part) it would have been a single ~21 KB display; under the serialized rule it became **3 parts**.
   Printed sizes: resume output 3,734 bytes; part displays 9,614 / 9,614 / 4,513 bytes.
2. Parts 1 and 2 displayed in the conversation; `subtract` implemented (`a679e4d`, gate passed); a report citing
   `prepared under owner amendments revision 1 sha256 d4cf8a03…` was **refused** (part 3 missing).
3. Part 3 displayed; `status` reported `shown_in_foreground_session_at: 2026-11-22T20:07:41.489Z` from the real
   transcript; the same report was admitted.
4. Codex: "The candidate implements the original addition requirement and the subtraction requested by OWNER
   AMENDMENT 1." `ready_for_owner_review`, bound to amendment revision 1; handoff posted by `finalize`.

## 6. Round 4 of this PR and the owner's decision

The enrolled session submitted `8c233d0` (`unit` through `verify`: 290 tests OK, 1 skipped, 908.8 s). Codex
verified 7 of the 8 pending fixes ([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7085402653))
and raised R4-F1..R4-F3; R2-F4 (watch log destinations) had then been open for three consecutive reviews, so the
controller's no-progress rule stopped the enrollment BLOCKED at 4/5 rounds. The session reported the exact state to
the owner in the conversation and asked for the smallest decision; the owner chose to resume and use the last round
(no budget change). The owner `resume` restarted the no-progress count. The session removed the watch log option
(eliminating the destination class rather than adding path rules), fixed R4-F1..R4-F3 with tests and mutation checks,
and committed the batch as `5158b1f393ec0a1aeea00a2e63f6d15e0d6f8316` (full suite 292 tests OK, 1 skipped, before commit).

## 7. Round 5, the owner's one-round extension, and the final correction batch

Round 5 on `167b8db` (`unit` through `verify`: 292 tests OK, 1 skipped) returned `changes_required`
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7085965329)); the enrollment
stopped BLOCKED at the cap (5/5). The session reported the state; the owner then authorized exactly one further round
(limit 6, no round 7), independently reproduced R5-F1 without any outage (an older amendment, 1/5 spent and a refused
`resume --max-rounds 1` published "budget exhausted (1/5)" and closed admission; a refused resume at a genuine
no-progress stop overwrote its reason), and asked for tests that fail on `167b8db` first. The earlier handoff's claim
that both recovery findings required an outage/amendment/cap coincidence was wrong and is corrected here.

The session ran the owner's `resume --max-rounds 6` (limit 5 to 6), wrote six behavior tests, and ran them against the
`167b8db` logic with only a no-behavior watch test seam added: all six failed for the reasons in the findings (one
fixture-timing assertion was corrected and re-run so the continuing-watch test failed at the age-of-action defect).
It then implemented the correction, committed as `1c92fed57a8d763db0e358c305ee18e93be2d437` (all six pass; full suite 298 tests OK, 1 skipped, before
commit; mutations of the proposed/authorized distinction and the marker gate make their tests fail). No new real-model
demonstration was run: these changes do not touch the amendment-delivery, review-return or live-output paths that the
demonstrations in sections 2, 4 and 5 exercised.

## 8. Round 6, the owner's further extension, and the round-7 batch (sanitized command evidence)

Round 6 on `f0f6330` (`unit` through `verify`: 298 tests OK, 1 skipped) returned `changes_required`
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7086981819)); the enrollment
stopped at the cap (6/6). The owner authorized one further round (limit 7, no round 8) and corrected the handoff's
characterization: R5-F1 is an admission and persisted-authorization defect, not merely wording or display. The session
ran `resume --max-rounds 7`, mapped the resume branches and the publication-failure boundaries, wrote nine
regressions, and ran them against a clean detached checkout of the reviewed candidate:

```text
$ git rev-parse HEAD                      # clean detached checkout, only the new test file copied in
f0f6330b86587ae86b15dfdec0e1b9ede02e8d19
$ sha256sum agent_review/agent_review.py
ac7ffd4a2a9099fdb9849eb212dd6756db7d56a18767da56340cf6032de156b9
$ python -m unittest agent_review.test_agent_review.ForegroundRoundSevenTests
FAIL: test_a_crash_after_the_amendment_then_a_replay_failure_then_success (attempt=1)
AssertionError: Tuples differ: ('BLOCKED', 'review-round budget for final [150 chars]N`)') != ('PAUSED', 'operational failure during resu[38 chars]age')
FAIL: test_a_crash_after_the_amendment_then_a_replay_failure_then_success (attempt=2)
AssertionError: Tuples differ: ('BLOCKED', 'review-round budget for final [150 chars]N`)') != ('PAUSED', 'operational failure during resu[38 chars]age')
FAIL: test_a_failed_restored_notice_then_success_keeps_one_restoration_notice (attempt=1)
AssertionError: Tuples differ: ('BLOCKED', 'review-round budget for final [150 chars]N`)') != ('PAUSED', 'publication of status-8-blocked[154 chars]ume')
FAIL: test_a_failed_restored_notice_then_success_keeps_one_restoration_notice (attempt=2)
AssertionError: Tuples differ: ('BLOCKED', 'review-round budget for final [150 chars]N`)') != ('PAUSED', 'publication of status-8-blocked[154 chars]ume')
FAIL: test_an_exhausted_proposal_never_reopens_a_superseded_handoff
AssertionError: UsageError not raised
FAIL: test_an_exhausted_proposal_saves_no_due_rebinding
AssertionError: {'sta[522 chars]d\\wf-earlier-install'}, 'settings': 'develope[1457 chars]': 0} != {'sta[522 chars]d\\wf'}, 'settings': 'developer-settings-7a3bd[1441 chars]': 0}
FAIL: test_an_exhausted_proposal_with_resend_never_clears_an_uncertain_delivery
AssertionError: {'sta[2334 chars]>', 'posting_since': '2026-11-22T23:07:02Z', '[251 chars]': 0} != {'sta[2334 chars]>', 'sha256': '68fcfcc0d7b4a567a426a7f10063a5c[210 chars]': 0}
FAIL: test_an_explicit_zero_from_paused_develop_is_refused_before_anything_changes
AssertionError: UsageError not raised
FAIL: test_watch_reads_attempts_retained_by_resume
AssertionError: 'latest action: Codex: REVIEWER-NOTE-events-3 (before this watch started)' not found in 'PAUSED/review | no agent running (controller or the foreground session) | candidate be6ac7aad66e (last reviewed be6ac7aad66e:
Ran 9 tests in 35.888s
FAILED (failures=9)
```

(The two tests not listed, `test_an_initial_publication_failure_then_success_restores_the_capped_blocker` and
`test_a_crash_after_the_restoration_then_success`, passed there: they cover the R4-F1/R5-F2 behavior verified in round 6.)

Corrected results on `5650e2f1c0c2edb2a44ad80d26d9bdae24a893ca`:

```text
$ python -m unittest agent_review.test_agent_review.ForegroundRoundSevenTests
Ran 9 tests ... OK
$ python -m unittest <the nine foreground, amendment and guidance classes>
Ran 85 tests ... OK
$ python -m unittest discover -s agent_review -p "test_*.py"
Ran 307 tests ... OK (skipped=1)
mutations: no admission hook -> zero test FAILS; no shared displacement marking -> crash/replay test FAILS;
           no notice reuse -> failed-notice test FAILS; current attempts only -> retained-attempt watch test FAILS
```

## 9. Round 7, the owner's extension to eight rounds, and the round-8 batch (sanitized command evidence)

Round 7 on `f393ca6` returned `changes_required`
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7087814050)): R5-F1 and R6-F1
were verified; R5-F3 was rejected (a replacement review request hid retained attempts) and R7-F1 and R7-F2 were new.
The enrollment stopped at 7/7 with a no-progress stop. The owner authorized one more round (limit 8, no round 9) and
supplied three failing acceptance cases. The session ran `resume --max-rounds 8` (seven spent rounds and the three
open findings kept; no-progress counters reset by the normal owner-resume path), read the bundle, and ran it unchanged
against the reviewed candidate before editing:

```text
$ python -I run_regressions.py --repo <worktree at f393ca6b966aaafe5a740f0b5a43475ff0e2c06a>
Python: 3.14.7
SHA-256 agent_review.py: f1acb6bc9c10b63a3c847f6633532669f0b636c3feb9931c05de25e843738efe
SHA-256 test_agent_review.py: 0cb21a19996b6429bcf3e1b619cc5c1a661dbc1953ac22d0f2e671fb1eb4415c
FAIL: test_both_deferred_status_notices_recover_to_public_and_local_blocked (recovery=1)
AssertionError: 'Workflow — blocked' not found in '### Workflow — paused — checkpoint final' : the last public status must agree with the recovered local BLOCKED state
FAIL: test_both_deferred_status_notices_recover_to_public_and_local_blocked (recovery=2)
AssertionError: 'Workflow — blocked' not found in '### Workflow — paused — checkpoint final' : the last public status must agree with the recovered local BLOCKED state
FAIL: test_reloaded_amendment_publishes_reopened_before_blocked (recovery=1)
AssertionError: Lists differ: ['### Workflow — reopened — checkpoint final', '### Workfl[28 chars]nal'] != ['### Workflow — blocked — checkpoint final', '### Workflo[28 chars]nal']
FAIL: test_reloaded_amendment_publishes_reopened_before_blocked (recovery=2)
AssertionError: Lists differ: ['### Workflow — reopened — checkpoint final', '### Workfl[28 chars]nal'] != ['### Workflow — blocked — checkpoint final', '### Workflo[28 chars]nal']
FAIL: test_replacement_request_preserves_latest_reviewer_action
AssertionError: 'latest action: Codex: RETAINED-REVIEWER-r01-events-3 (before this watch started)' not found in 'PAUSED/review | no agent running (controller or the foreground session) | candidate 6f1
Ran 3 tests in 19.003s
FAILED (failures=5)
```

The failures match the bundle's own 3.12.14 baseline. After the correction (`cf835127680aee7d3f4ebe34cd279c571524fcc2`), the same unchanged bundle:

```text
SHA-256 agent_review.py: 00d2fcc99e725ef1cb77e55bf0d12cbf1b22616af3e6ea00734e43ab20a27a9e
SHA-256 test_agent_review.py: 62fec1451599c03201542ccbf7d9983aac5ea931a4f6a3e81a00740f4de2b779
Ran 3 tests in 67.041s
OK
```

The cases are integrated into `ForegroundRoundEightTests` (bodies unchanged apart from module prefixes) together with
`test_the_dual_failure_recovery_leaves_this_public_chronology`. On a clean detached `f393ca6` checkout with only the new
test file:

```text
FAIL: test_both_deferred_status_notices_recover_to_public_and_local_blocked (recovery=1)
AssertionError: 'Workflow — blocked' not found in '### Workflow — paused — checkpoint final' : the last public status must agree with the recovered local BLOCKED state
FAIL: test_both_deferred_status_notices_recover_to_public_and_local_blocked (recovery=2)
AssertionError: 'Workflow — blocked' not found in '### Workflow — paused — checkpoint final' : the last public status must agree with the recovered local BLOCKED state
FAIL: test_reloaded_amendment_publishes_reopened_before_blocked (recovery=1)
AssertionError: Lists differ: ['### Workflow — reopened — checkpoint final', '### Workfl[28 chars]nal'] != ['### Workflow — blocked — checkpoint final', '### Workflo[28 chars]nal']
FAIL: test_reloaded_amendment_publishes_reopened_before_blocked (recovery=2)
AssertionError: Lists differ: ['### Workflow — reopened — checkpoint final', '### Workfl[28 chars]nal'] != ['### Workflow — blocked — checkpoint final', '### Workflo[28 chars]nal']
FAIL: test_replacement_request_preserves_latest_reviewer_action
AssertionError: 'latest action: Codex: RETAINED-REVIEWER-r01-events-3 (before this watch started)' not found in 'PAUSED/review | no agent running (controller or the foreground session) | candidate 12f
FAIL: test_the_dual_failure_recovery_leaves_this_public_chronology (recovery=1)
AssertionError: 'Workflow — blocked' not found in '### Workflow — paused — checkpoint final' : the last public status must agree with the recovered local BLOCKED state
FAIL: test_the_dual_failure_recovery_leaves_this_public_chronology (recovery=2)
AssertionError: 'Workflow — blocked' not found in '### Workflow — paused — checkpoint final' : the last public status must agree with the recovered local BLOCKED state
FAIL: test_the_dual_failure_recovery_leaves_this_public_chronology
AssertionError: Lists differ: ['reopened', 'blocked', 'paused', 'blocked', 'paused', 'blocked'] != ['reopened', 'blocked', 'paused', 'blocked', 'paused']
Ran 4 tests in 21.218s
FAILED (failures=8)
```

On `cf835127680aee7d3f4ebe34cd279c571524fcc2`, the actual status comments of the dual-failure case, in GitHub order (simulated GitHub):

```text
status-3-reopened  | ### Workflow — reopened — checkpoint final
status-6-blocked   | ### Workflow — blocked — checkpoint final   (amendment at the cap)
status-7-paused    | ### Workflow — paused — checkpoint final    (PR-body edit failed)
status-8-blocked   | ### Workflow — blocked — checkpoint final   (restored blocker; delivery deferred, sent on recovery)
status-9-paused    | ### Workflow — paused — checkpoint final    (its delivery failure; deferred, sent on recovery)
status-10-blocked  | ### Workflow — blocked — checkpoint final   (one correction; the second recovery adds nothing)
```

```text
$ python -m unittest ForegroundRoundEightTests ForegroundRoundSevenTests      -> Ran 13 tests ... OK
$ python -m unittest discover -s agent_review -p "test_*.py"                  -> Ran 311 tests ... OK (skipped=1)
mutations: mapping order instead of seq -> sequence test FAILS; reuse on the local record alone -> dual-failure test
           FAILS; history from the last round only -> watch-history test FAILS
```


## 10. Round 8, the owner's completion window (limit 10), and the round-9 batch (sanitized command evidence)

Round 8 on `d73f96a` returned `changes_required`
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7088912402)): R5-F3, R7-F1 and
R7-F2 were verified; R8-F1 (an acknowledged status missing from a lagging listing), R8-F2 (a reused notice's visible
body not checked) and R8-F3 (watch counting an attempt recorded `launched: false`) were new. The owner authorized at most
rounds 9 and 10 and supplied a ten-case acceptance bundle. The session ran `resume --max-rounds 10` (eight spent rounds,
history and finding identities kept) and ran the bundle unchanged against the reviewed candidate before editing:

```text
$ python -I run_regressions.py --repo <worktree at d73f96a277b1194b4ec162a8328c5663e01665ee>
Python: 3.14.7 (tags/v3.14.7:823f032, Aug  5 2026, 10:51:32) [MSC v.1944 64 bit (AMD64)]
SHA-256 agent_review.py: 00d2fcc99e725ef1cb77e55bf0d12cbf1b22616af3e6ea00734e43ab20a27a9e
SHA-256 test_agent_review.py: 62fec1451599c03201542ccbf7d9983aac5ea931a4f6a3e81a00740f4de2b779
test_both_deferred_status_notices_recover_to_public_and_local_blocked ... ok
test_reloaded_amendment_publishes_reopened_before_blocked ... ok
test_replacement_request_preserves_latest_reviewer_action ... ok
  test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='listing still omits acknowledged PAUSED') ... FAIL
  test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='acknowledged comment visible', recovery=1) ... FAIL
  test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='acknowledged comment visible', recovery=2) ... FAIL
  test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone (recovery=1) ... FAIL
  test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone (recovery=2) ... FAIL
test_intact_delayed_blocked_notice_can_be_reused_without_reposting ... ok
  test_event_directory_fault_does_not_crash_watch_before_or_after_replacement (stage='initial closed unlaunched attempt') ... ERROR
  test_event_directory_fault_does_not_crash_watch_before_or_after_replacement (stage='unlaunched history before empty replacement request') ... ERROR
test_newer_unlaunched_round_does_not_hide_older_executed_reviewer_attempt ... FAIL
test_open_attempt_without_events_still_has_current_reviewer_role ... ok
  test_stderr_directory_fault_does_not_replace_latest_real_action_with_none (stage='initial closed unlaunched attempt') ... FAIL
  test_stderr_directory_fault_does_not_replace_latest_real_action_with_none (stage='unlaunched history before empty replacement request') ... FAIL
ERROR: test_event_directory_fault_does_not_crash_watch_before_or_after_replacement (stage='initial closed unlaunched attempt')
PermissionError: [Errno 13] Permission denied: '<temp>\\state\\t-codex-feature-20261122203036-23b5\\rounds\\r01\\events-1.jsonl'
ERROR: test_event_directory_fault_does_not_crash_watch_before_or_after_replacement (stage='unlaunched history before empty replacement request')
PermissionError: [Errno 13] Permission denied: '<temp>\\state\\t-codex-feature-20261122203036-23b5\\rounds\\r01\\events-1.jsonl'
FAIL: test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='listing still omits acknowledged PAUSED')
AssertionError: False is not true : an acknowledged-but-unlisted status must not silently finalize reuse of an older BLOCKED notice
FAIL: test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='acknowledged comment visible', recovery=1)
AssertionError: 'Workflow — blocked' not found in "<!-- agent-review:v1 enrollment=t-codex-feature-20261122203024-bede key=status-7-paused part=1/1 sha256=bf583c1e81f804426ec6780d37402ed8cf4737a4f5696
FAIL: test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='acknowledged comment visible', recovery=2)
AssertionError: 'Workflow — blocked' not found in "<!-- agent-review:v1 enrollment=t-codex-feature-20261122203024-bede key=status-7-paused part=1/1 sha256=bf583c1e81f804426ec6780d37402ed8cf4737a4f5696
FAIL: test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone (recovery=1)
AssertionError: False is not true : the public reason was edited, but recovery was falsely marked complete
FAIL: test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone (recovery=2)
AssertionError: False is not true : the public reason was edited, but recovery was falsely marked complete
FAIL: test_newer_unlaunched_round_does_not_hide_older_executed_reviewer_attempt
AssertionError: 'latest action: Codex: ACTUAL-REVIEWER-events-3 (before this watch started)' not found in 'BLOCKED/review | no agent running (controller or the foreground session) | candidate d601b2b3
FAIL: test_stderr_directory_fault_does_not_replace_latest_real_action_with_none (stage='initial closed unlaunched attempt')
AssertionError: 'latest action: Claude: ACTUAL-DEVELOPER-BEFORE-UNLAUNCHED-REVIEWER (before this watch started)' not found in 'BLOCKED/review | no agent running (controller or the foreground session) 
FAIL: test_stderr_directory_fault_does_not_replace_latest_real_action_with_none (stage='unlaunched history before empty replacement request')
AssertionError: 'latest action: Claude: ACTUAL-DEVELOPER-BEFORE-UNLAUNCHED-REVIEWER (before this watch started)' not found in 'PAUSED/review | no agent running (controller or the foreground session) |
Ran 10 tests in 38.853s
FAILED (failures=8, errors=2)
```

This matches the bundle's baseline (5 methods pass, 8 failures, 2 errors). On Windows the directory open raises
`PermissionError` where the bundle's Linux run raised `IsADirectoryError`; in both erroring subtests the setup assertions
(attempt saved with `launched: false`, no reviewer process dispatched, obstacle present) passed first. After the
correction (`8c5f6fd39a2d85c16b6175001fe248435f1049f3`), the same unchanged bundle:

```text
SHA-256 agent_review.py: ec4f604bf3f0df41c46bd35c27787f8c2d3dbf18e511ff31155838f8b00a9e41
SHA-256 test_agent_review.py: e7760d87b5c937b43a217dd6d99d19bad7db00fd3b1b45e48c31a96b64262ee8
Ran 10 tests in 43.389s
OK
```

The new cases are integrated as `ForegroundRoundNineVisibilityTests`, `ForegroundRoundNineIntegrityTests` and
`WatchRoundNineUnlaunchedTests` (class bodies unchanged apart from module prefixes and names). On a clean detached
`d73f96a` checkout with only the new test file:

```text
ERROR: test_event_directory_fault_does_not_crash_watch_before_or_after_replacement (stage='initial closed unlaunched attempt')
PermissionError: [Errno 13] Permission denied: '<temp>\\state\\t-codex-feature-20261122205005-bc3d\\rounds\\r01\\events-1.jsonl'
ERROR: test_event_directory_fault_does_not_crash_watch_before_or_after_replacement (stage='unlaunched history before empty replacement request')
PermissionError: [Errno 13] Permission denied: '<temp>\\state\\t-codex-feature-20261122205005-bc3d\\rounds\\r01\\events-1.jsonl'
FAIL: test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='listing still omits acknowledged PAUSED')
AssertionError: False is not true : an acknowledged-but-unlisted status must not silently finalize reuse of an older BLOCKED notice
FAIL: test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='acknowledged comment visible', recovery=1)
AssertionError: 'Workflow — blocked' not found in "<!-- agent-review:v1 enrollment=t-codex-feature-20261122204944-7e60 key=status-7-paused part=1/1 sha256=0104f58df6695c79a3bd058d394fbbf2329b045f7efd8
FAIL: test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked (stage='acknowledged comment visible', recovery=2)
AssertionError: 'Workflow — blocked' not found in "<!-- agent-review:v1 enrollment=t-codex-feature-20261122204944-7e60 key=status-7-paused part=1/1 sha256=0104f58df6695c79a3bd058d394fbbf2329b045f7efd8
FAIL: test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone (recovery=1)
AssertionError: False is not true : the public reason was edited, but recovery was falsely marked complete
FAIL: test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone (recovery=2)
AssertionError: False is not true : the public reason was edited, but recovery was falsely marked complete
FAIL: test_newer_unlaunched_round_does_not_hide_older_executed_reviewer_attempt
AssertionError: 'latest action: Codex: ACTUAL-REVIEWER-events-3 (before this watch started)' not found in 'BLOCKED/review | no agent running (controller or the foreground session) | candidate 0b1cdbbc
FAIL: test_stderr_directory_fault_does_not_replace_latest_real_action_with_none (stage='initial closed unlaunched attempt')
AssertionError: 'latest action: Claude: ACTUAL-DEVELOPER-BEFORE-UNLAUNCHED-REVIEWER (before this watch started)' not found in 'BLOCKED/review | no agent running (controller or the foreground session) 
FAIL: test_stderr_directory_fault_does_not_replace_latest_real_action_with_none (stage='unlaunched history before empty replacement request')
AssertionError: 'latest action: Claude: ACTUAL-DEVELOPER-BEFORE-UNLAUNCHED-REVIEWER (before this watch started)' not found in 'PAUSED/review | no agent running (controller or the foreground session) |
Ran 7 tests in 39.067s
FAILED (failures=8, errors=2)
```

Coverage of the owner's combinations on `8c5f6fd`:

| Combination | Decision | Test |
| --- | --- | --- |
| Acknowledged publication, listing delayed | order unresolved: distinct BLOCKED correction, never reuse | `test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked` |
| Intact delayed BLOCKED that really posts last | reused, posted once | `test_intact_delayed_blocked_notice_can_be_reused_without_reposting` |
| Edited visible body, full marker and id kept | distinct correction; edited comment untouched | `test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone` |
| Repeated resume after settlement | nothing added (restore_needed cleared in the restoration transaction) | second recovery in every publication case |
| Never-launched attempt, before and after an empty replacement request | excluded; directory never opened | event-directory and stderr-directory cases |
| Earlier history whose records omit `launched` | still an execution; newer unlaunched round skipped | `test_newer_unlaunched_round_does_not_hide_older_executed_reviewer_attempt` |
| Open attempt with no events | current reviewer, "none observed yet in this attempt" | `test_open_attempt_without_events_still_has_current_reviewer_role` |

```text
$ python -m unittest <round-7, round-8 and round-9 classes>        -> Ran 20 tests ... OK
$ python -m unittest discover -s agent_review -p "test_*.py"       -> Ran 318 tests ... OK (skipped=1)
mutations: listing completeness removed -> visibility test FAILS; body comparison removed -> edited-body test FAILS;
           launched=false counted -> all four watch cases FAIL
```

Executed: real temporary Git repositories, controller state and command paths. Simulated: GitHub, Claude and Codex
boundaries (in the watch cases, only the test's Codex executable at process creation). Not established: CPython 3.12
on this host, real GitHub listing-lag frequency, and live-model behavior (these changes do not touch those paths).


## 11. Round 9 and the round-10 batch (sanitized command evidence)

Round 9 on `ca06b99` returned `changes_required`
([review comment](https://github.com/howardreith/development-process/pull/7#issuecomment-7090013384)): R8-F1, R8-F2 and
R8-F3 were verified. New, within the repair scope: R9-F1 (the reuse decision used its own stricter body check, so a
CRLF-only body was rejected, and it ignored a competing copy of the marker), R9-F2 (a continuing watch replayed an
earlier round as live after a failed launch) and R9-F3 (the status line called an unlaunched request "last reviewed").
Under the owner's completion window, the session corrected these and wrote `ForegroundRoundTenTests`. On a clean
detached `ca06b99` checkout with only the new test file:

```text
FAIL: test_a_competing_copy_of_the_marker_forces_a_correction_or_an_integrity_stop (recovery=1)
AssertionError: False is not true
FAIL: test_a_competing_copy_of_the_marker_forces_a_correction_or_an_integrity_stop (recovery=2)
AssertionError: False is not true
FAIL: test_a_continuing_watch_keeps_an_earlier_round_historical_after_a_failed_launch
AssertionError: '(earlier) Codex: REVIEWER-events-3' not found in ['Codex: REVIEWER-events-1', 'Codex: REVIEWER-events-2', 'Codex: REVIEWER-events-3', 'BLOCKED/review | no agent running (controller or the foreground sess
FAIL: test_a_crlf_only_delayed_notice_is_reused (recovery=1)
AssertionError: 'status-8-blocked' != 'status-10-blocked'
FAIL: test_a_crlf_only_delayed_notice_is_reused (recovery=2)
AssertionError: 'status-8-blocked' != 'status-10-blocked'
FAIL: test_the_status_line_never_presents_an_unlaunched_request_as_reviewed (case='first request, never launched')
AssertionError: '(no accepted review yet; requested 1e477a7a9069: not reviewed: no reviewer launched)' not found in 'BLOCKED/review | no agent running (controller or the foreground session) | candidate 1e477a7a9069 (last
FAIL: test_the_status_line_never_presents_an_unlaunched_request_as_reviewed (case='an unlaunched request after an accepted review')
AssertionError: '(last reviewed 98bc875b6217: changes_required; requested e8f01be77bff: not reviewed: no reviewer launched)' not found in 'BLOCKED/review | no agent running (controller or the foreground session) | candid
Ran 4 tests in 16.278s
FAILED (failures=7)
```

On `4dfac2d543dcb00cd9e1e8bc2529879e047c0853`:

```text
$ python -m unittest agent_review.test_agent_review.ForegroundRoundTenTests   -> Ran 4 tests ... OK
$ python -I run_regressions.py --repo <worktree> (owner's round-8 bundle)      -> Ran 10 tests ... OK
$ python -m unittest discover -s agent_review -p "test_*.py"                   -> Ran 322 tests ... OK (skipped=1)
mutations: publication check skipped -> competing-copy test FAILS; history only at poll zero -> continuing-watch test
           FAILS; "last reviewed" from the newest round -> status-line test FAILS
```

The continuing-watch test runs a real watcher thread that attaches while the replacement attempt is saved open; the
real CodexReviewer stream setup then fails on a directory at its stderr path, and the test's Codex executable is never
started. Simulated: GitHub, Claude and Codex boundaries. Not established: CPython 3.12 on this host, real GitHub
listing-lag frequency, live-model behavior (not affected by these changes).
