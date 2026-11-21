<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r04-review part=1/2 sha256=9aa816164363a9db9914586cb286c8e1cbfb7a22e1e2aa5593436a388658737e -->
_Part 1 of 2._

### Codex GPT-6.2 Astra — review — round 4 — candidate `1b295b6e70`

**Decision:** `changes_required` — The candidate-bound unit gate passed. The controller can still advance an intermediate checkpoint after its gate evidence becomes invalid during publication, report a handoff as current against a lagging PR head, and lose substantive review records during retirement. Recovery, publication identity, and installation ownership also have concrete gaps. These affect the controller-core exit conditions.

#### Findings

**R1-F1** · P1 · defect · blocks readiness — A handoff can pass verification when its receipt entry is absent
- Location: `agent_review/agent_review.py:2685`; acceptance: WF04, WF06
- Trigger: A recorded handoff names archive A, but its publication map lacks final-status-<A>.
- Expected: The exact receipt named by the handoff must exist locally, contain its expected parts, and authenticate against the PR.
- Actual: missing_publications iterates existing entries. A missing include_receipt key contributes no failure. The regression covers a superseded entry and a deleted remote comment, both of which retain the local publication entry.
- Why it blocks / does not: status --remote and resume can confirm a handoff without its required receipt.
- Requested correction: Look up and validate the named receipt explicitly before checking the rest of the publication inventory.
- Requested evidence: Remove the named entry from a completed fixture enrollment while leaving its other records intact. Verify that status and resume detect the missing receipt.

**R1-F2** · P1 · defect · blocks readiness — Receipt ordering and the final acceptance check can admit an invalid gate
- Location: `agent_review/agent_review.py:1999`; acceptance: WF08, WF12
- Trigger: A receipt loses its timestamp, a damaged receipt remains during a rerun, or gate evidence changes while a passing verdict is being published.
- Expected: The latest applicable run controls the gate. A replacement verification can recover a damaged run under a defined rule, and the evidence remains valid when the pass is accepted.
- Actual: gate_status orders runs by the receipt body's recorded_at, defaulting to an empty string. A newer failing receipt with that field missing can sort behind an older pass. Conversely, damaged_gates makes an identity-less receipt defeat every later rerun for H. finish_round also checks gates before sending the verdict and only checks H/M after sending it.
- Why it blocks / does not: A checkpoint can advance on invalid evidence, or a corrected gate run can remain unusable. The test deletes the damaged receipt before exercising recovery.
- Requested correction: Use the controller-written filename to validate run order and receipt structure. Define a recoverable replacement for damaged evidence, and recheck gates immediately before charging or advancing a passing round. Correct any verdict already visible if that check fails.
- Requested evidence: Exercise a newer failure missing recorded_at, recovery without manually deleting evidence, and a log damaged by the simulated publication callback. Verify the round count, checkpoint, and visible verdict in each case.

**R1-F3** · P1 · defect · blocks readiness — The first versioned install still dismantles a live flat installation
- Location: `agent_review/agent_review.py:3195`; acceptance: WF07
- Trigger: The destination has a legacy MANIFEST.json and a process is still using that installation.
- Expected: A process that started on the flat installation can finish against one complete version, or migration safely refuses before changing that installation.
- Actual: Version-to-version installation preserves running versions. The initial migration calls _retire_legacy_flat_install before staging the replacement and without excluding already-running legacy writers or helpers. It unlinks their flat workflow files.
- Why it blocks / does not: A supported upgrade can remove the workflow resources of a running enrollment. An interruption can also leave the old installation unusable before the launcher exists.
- Requested correction: Stage and verify the replacement first. Coordinate the one-time flat migration with legacy processes and make the transition recoverable before retiring their files.
- Requested evidence: Hold a real legacy controller or helper open during migration, then interrupt migration before the launcher switch. Demonstrate a usable, attributable version in each case.

**R1-F6** · P1 · defect · blocks readiness — Reviewer completion is still not bound to one verified rollout
- Location: `agent_review/agent_review.py:590`; acceptance: WF05
- Trigger: A malformed stream has a terminal event before its thread identity, or the rollout lookup yields an ambiguous or mismatched file.
- Expected: One valid thread identity precedes completion, and one complete, identity-matching rollout supplies the provenance.
- Actual: parse_codex_events accepts a completion before thread.started and does not require a valid thread ID on each start. provenance uses the supplied ID as part of a glob, takes matches[0], and does not compare session_meta.id with the requested identity. Malformed rollout lines are silently skipped.
- Why it blocks / does not: A malformed event stream or ambiguous rollout lookup can supply successful completion and apparently compliant provenance without establishing that they belong to the same execution.
- Requested correction: Validate the thread identifier and completion ordering, require an unambiguous exact rollout identity, and reject malformed provenance through the bounded attempt path.
- Requested evidence: Pass a completion-before-start stream, a missing start ID, an ambiguous rollout, and a mismatched session_meta.id through the real parsers. Verify rejection without advancing a round.

**R1-F18** · P2 · defect · blocks readiness — Child-session detection still treats unrelated metadata text as delegation
- Location: `agent_review/agent_review.py:597`; acceptance: WF05
- Trigger: Another rollout mentions the review thread in a non-parent field, or a review crosses the rollout date boundary.
- Expected: Delegation is attributed using a recorded dispatch or a structured parent-thread relationship.
- Actual: The child-rollout fallback searches for the thread ID anywhere in another file's raw first line. It does not parse the parent relationship and only scans siblings in the parent's directory.
- Why it blocks / does not: An unrelated metadata reference can invalidate a legitimate review. A child recorded in another date directory can escape the fallback used to detect indirect delegation.
- Requested correction: Check the actual parent identity in session metadata and cover the rollout locations used during the review interval.
- Requested evidence: Include an unrelated session mentioning the ID outside its parent field and a genuine child in the next date directory. Verify both classifications.

**R2-F1** · P1 · defect · blocks readiness — Retired verdicts can still disappear from the committed exchange
- Location: `agent_review/agent_review.py:2583`; acceptance: WF04, WF06, WF09
- Trigger: H moves just after the full verdict is posted, or gate evidence becomes invalid after only part of an earlier publication reached GitHub.
- Expected: Every authenticated retired review remains available in full on the PR and in the committed records, with its envelope and publication identifiers.
- Actual: retire_verdict emits a historical rendering only for a partially visible verdict or an explicitly requested unsent one. A fully visible verdict is marked superseded, and archive skips it. Gate invalidation also calls retire_verdict without the authenticated envelope, so a partially visible verdict on that path loses its remaining parts.
- Why it blocks / does not: The eventual archive can contain a correction without the substantive review and its provenance. A partial gate-invalidated review can also be incomplete on the PR.
- Requested correction: Preserve the complete authenticated review and envelope for every retirement path. Associate the archived rendering with the publication parts that actually carried it.
- Requested evidence: Complete a later handoff after both a fully posted stale verdict and a partially posted gate-invalidated verdict. Locate the last finding, request identity, and publication links in the PR and committed records.

**R2-F2** · P1 · defect · blocks readiness — Legacy finding recovery can substitute an older authenticated statement
- Location: `agent_review/agent_review.py:1539`; acceptance: WF08
- Trigger: A legacy finding was restated across rounds and only its earlier envelope remains readable and authentic.
- Expected: Recovered text comes from the authenticated round that last stated that finding.
- Actual: full_findings iterates accepted rounds in order. It can populate a legacy entry from an earlier authenticated envelope, skip the missing or altered latest envelope, and pass the subsequent presence check with outdated text.
- Why it blocks / does not: The reviewer can close a repeated finding while seeing an older trigger or correction request.
- Requested correction: Bind recovery to the ledger's last applicable finding round. Refuse dispatch when the latest required text cannot be authenticated.
- Requested evidence: Restate one finding differently in two accepted rounds. Remove its embedded ledger text and damage only the second envelope. Verify that the first round's wording cannot satisfy dispatch.

**R2-F3** · P1 · defect · blocks readiness — Installer ownership checks still allow overwriting or deleting unrelated files
- Location: `agent_review/agent_review.py:3195`; acceptance: WF07, WF10
- Trigger: A destination contains a familiar filename without an installation identity, or a legacy directory contains data outside its manifest.
- Expected: The entire destination and every file proposed for replacement or deletion are checked for ownership before the first mutation.
- Actual: install accepts top-level names from INSTALL_ENTRIES as proof of ownership and replaces an existing agent_review.py even in an unrelated directory. Legacy migration removes manifest files before checking for unknown entries and recursively deletes directories whose only remaining entry is named __pycache__.
- Why it blocks / does not: An installation attempt can overwrite unrelated code or delete unowned contents, including on a migration that ultimately refuses.
- Requested correction: Validate the existing layout and manifest paths before modifying them. Preserve unowned cache contents and refuse to replace an unrelated launcher or pointer solely because its filename matches.
- Requested evidence: Use an unrelated directory containing only agent_review.py and a legacy installation with an unowned cache sentinel and an unexpected file. Verify byte-for-byte preservation on refusal.

**R3-F1** · P2 · evidence_gap · blocks readiness — The archive-numbering regression checks expressions without archiving records
- Location: `agent_review/test_agent_review.py:2466`; acceptance: WF09
- Trigger: A long enrollment archives a three-digit round after its record sequence reaches four digits.
- Expected: A real archive commit demonstrates that round 100 retains its own provenance and that sequence allocation advances past 999.
- Actual: The production lookup now parses the full round number. The cited test checks the name regex and a separately written regex against literals. It never invokes archive or reads a committed envelope.
- Why it blocks / does not: The requested regression evidence for correct envelope attribution at the numbering boundary is absent.
- Requested correction: Exercise the production archive path with distinguishable round-10 and round-100 results and an existing record numbered 999.
- Requested evidence: Read the resulting Git blobs and compare filenames, request IDs, and response hashes with the two input envelopes.

**R3-F2** · P1 · defect · blocks readiness — Comment retries refresh the actor but can still target an ineligible PR
- Location: `agent_review/agent_review.py:1219`; acceptance: WF10
- Trigger: The enrolled PR changes while a reviewer runs or a publication retry waits.
- Expected: At the write boundary the controller checks the applicable target and actor for each GitHub mutation.
- Actual: send now refreshes the actor immediately before POST, but does not repeat pr_view there. A retargeted, closed, or converted PR can still receive the comment. Draft creation also uses the actor observation made before enrollment acquired its writer lock.
- Why it blocks / does not: A delayed or retried mutation can write outside the enrolled draft-PR conditions.
- Requested correction: Apply the open-draft and enrolled PR identity guard alongside the actor guard before comment POSTs, including retries. Refresh the actor immediately before draft creation.
- Requested evidence: Retarget or close the simulated PR after the entry check and before a retry. Separately switch the actor before draft creation. Verify zero writes to the invalid target or under the changed actor.

**R3-F3** · P1 · evidence_gap · blocks readiness — Effective isolation of headless permissions remains unobserved
- Location: `agent_review/test_agent_review.py:2483`; acceptance: WF10
- Trigger: The real CLI launches in a user or project profile with an additional allowance.
- Expected: The launched headless developer can use its enrolled helper and receives a denial for a harmless command allowed only by ambient settings.
- Actual: The gate proves the composed file excludes the ambient rule and the argv contains an empty setting-sources argument. The supplied evidence contains no launched permission decision for that ambient-only command. The reported smoke with no denials does not exercise that decision.
- Why it blocks / does not: The previous finding explicitly required evidence about effective permissions in the launched developer.
- Requested correction: Supply a focused permission observation from the actual candidate launch profile.
- Requested evidence: Record the candidate and CLI version, the harmless ambient-only allowance, the successful enrolled helper operation, and the denial for the ambient-only operation.

**R3-F4** · P1 · defect · blocks readiness — A truncated preserved envelope bypasses verdict retirement
- Location: `agent_review/agent_review.py:1723`; acceptance: WF05, WF06
- Trigger: The validated envelope becomes invalid JSON while its verdict publication is pending or already visible.
- Expected: Unreadable, truncated, and digest-mismatched envelopes all trigger durable verdict retirement and replacement.
- Actual: finish_round parses the envelope before comparing its recorded digest. Truncated JSON raises before retire_verdict runs. The generic command handler pauses the enrollment, and resume repeats the same parse against the same validated round.
- Why it blocks / does not: An already-visible verdict can remain uncorrected indefinitely, and the normal recovery path cannot obtain a replacement review.
- Requested correction: Authenticate the bytes before parsing and handle unreadable or malformed envelopes through the same recoverable invalidation transition. Persist retirement and round invalidation together.
- Requested evidence: Truncate an envelope after a stored but unacknowledged verdict. Restart through the command entry point and verify a visible correction, one fresh review, and a completable handoff.

**R3-F5** · P2 · defect · blocks readiness — First-time status insertion still alters existing PR description text
- Location: `agent_review/agent_review.py:2746`; acceptance: WF06
- Trigger: An enrolled PR has no status markers and its description ends in whitespace.
- Expected: Appending the first status section preserves the existing PR description exactly.
- Actual: The first insertion uses body.rstrip(), which removes owner-authored trailing spaces, tabs, and blank lines. The test uses text with no trailing whitespace.
- Why it blocks / does not: The requested preservation guarantee still fails on the first status update.
- Requested correction: Append the separator and section without stripping the original body.
- Requested evidence: Start with a marker-free description ending in Markdown whitespace and blank lines. Compare the complete original prefix after the first update, then check both sides on a subsequent replacement.

**R4-F1** · P1 · defect · blocks readiness — Final handoff can accept a stale PR view after the branch has moved
- Location: `agent_review/agent_review.py:2483`; acceptance: WF04, WF09
- Trigger: The branch advances after archive verification while GitHub's PR projection still reports A.
- Expected: Both the pushed branch and PR head still identify A during the final checks and subsequent handoff verification.
- Actual: readiness checks pr.headRefOid against A but never checks the current remote branch head. The earlier archive check can be minutes old when the final receipt and body edit finish. handoff_superseded uses the same PR-only observation.
- Why it blocks / does not: A lagging PR view can permit or reaffirm AWAITING_OWNER_REVIEW after a material push.
- Requested correction: Check the live enrolled branch head in the shared readiness check, including after publication and during remote status or resume.
- Requested evidence: Push a material commit to the fixture origin during receipt publication while the simulated PR view continues to return A. Verify that the handoff is rejected and any visible receipt is corrected.

**R4-F2** · P1 · defect · blocks readiness — Configuration-only upgrades silently reuse the old installed package
- Location: `agent_review/agent_review.py:3199`; acceptance: WF07, WF10, WF12
- Trigger: Two reviewed packages have identical controller code, schemas and prompts, but different project or plan files.
- Expected: The launcher selects a complete installed package matching the reviewed source, including the configuration used for new enrollments.
- Actual: The version-directory key excludes projects, plans, and README.md. If only a shipped gate, permission rule, or checkpoint plan changes, install reuses the existing directory after checking it against its own manifest. It never compares that directory's full file hashes with the new source.
- Why it blocks / does not: A successful install can silently leave new enrollments using superseded permissions or acceptance gates.
- Requested correction: Use a complete package digest for immutable installation directories. The behavioral fingerprint can remain separate for enrollment activation.
- Requested evidence: Install twice with only a project rule or required checkpoint gate changed. Enroll through the launcher and verify that the new configuration is selected while the previous package remains intact.

**R4-F3** · P1 · defect · blocks readiness — Two failed lookups can authenticate an excluded transcript addition
- Location: `agent_review/agent_review.py:1168`; acceptance: WF09, WF10
- Trigger: The feature adds an unrecognized transcript path that Git quotes in raw textual diff output.
- Expected: Every addition in the excluded transcript tree has an explicit inventory entry and a successfully read matching blob.
- Actual: verify_transcript_delta parses Git's quoted text paths and compares archived.get(path) directly with blob_sha256. A quoted path can fail both lookups, yielding None on both sides. For a plain addition under another PR directory, verify_transcripts does not supply a second check.
- Why it blocks / does not: An unrecognized record can be omitted from the feature diff and accepted as controller-owned.
- Requested correction: Require positive inventory membership and a successful blob read. Parse Git path records without display quoting, for example using NUL-delimited output.
- Requested evidence: Add a plain file with a Git-quoted filename in a different PR transcript directory in a temporary repository. Verify refusal before reviewer dispatch and continued acceptance of genuine controller records.

**R4-F4** · P1 · defect · blocks readiness — A lost POST response followed by a stale listing can duplicate publication
- Location: `agent_review/agent_review.py:1215`; acceptance: WF06
- Trigger: The first reconciliation read after an ambiguous POST does not yet show the stored comment.
- Expected: An uncertain send is reconciled across retries and restart without issuing a duplicate comment.
- Actual: When POST stores a comment but raises before returning, tentative remains None. If the next listing temporarily omits the stored comment, send POSTs it again. A successful second response is accepted immediately, and missing_publications later checks only the recorded comment ID.
- Why it blocks / does not: The controller can finish with duplicate requests or verdicts bearing the same marker.
- Requested correction: Persist the uncertain-send state, allow bounded time for the marker to become visible, and pause when delivery remains ambiguous. Verify marker uniqueness when confirming publication.
- Requested evidence: Have simulated GitHub store the first comment, lose its response, and omit it from the next successful listing. Restart and verify exactly one remote comment and one acknowledged publication.

**R4-F5** · P1 · defect · blocks readiness — A controller command can outlive the enrollment authority it checked
- Location: `agent_review/agent_review.py:3334`; acceptance: WF07, WF10
- Trigger: Another command cancels or replaces the enrollment between initial lookup and writer-lock acquisition.
- Expected: Every mutating command verifies its current enrollment ownership and command eligibility under the writer lock.
- Actual: Ordinary controller commands resolve the enrollment and check its status before acquiring the writer lock. guarded reloads state under that lock but does not recheck the command's status eligibility or current claims. A paused process can therefore resume its command after cancellation or replacement and act on its old enrollment.
- Why it blocks / does not: The helper fix closes this race for push and verify. The controller can still archive or reopen work using authority that has since been withdrawn.
- Requested correction: Revalidate the host and worktree claims and command-specific state after locking, including the activation path. Refuse stale commands before publication, archive writes, or child dispatch.
- Requested evidence: Hold a command after enrollment lookup, cancel or replace that enrollment, then allow the command to acquire the lock. Verify that it makes no commit, post, or launch.

#### Prior finding assessments

- **R1-F1** — `fix_rejected` — Correction queuing survives a failed send, and a superseded named entry is detected. An entirely absent named entry still passes the inventory loop.
- **R1-F11** — `fix_verified` — Activation records receipt retirement and the status edit with the workflow transition. The unit gate exercised failed publication followed by settlement from reloaded state.
- **R1-F15** — `fix_verified` — Resume checks the completed count against the effective limit, and develop_step checks it before dispatch. The regression exercises a stop reason unrelated to the cap.
- **R1-F16** — `fix_verified` — review_round reconciles an unfinished requested or reviewing attempt before candidate capture and supersession. The moved-head regression preserves the live attempt.
- **R1-F18** — `fix_rejected` — Direct tool-name checking fixes source-comment misclassification in the main rollout. The replacement child-session fallback still uses raw text matching and a same-directory assumption.
- **R1-F19** — `fix_verified` — Under the enrollment lock, replacement imports the prior archived inventory into the host ledger. Enrollment checks its blobs before writing the new claims. The direct pre-ledger replacement fixture passed.
- **R1-F2** — `fix_rejected` — The pre-publication check and return to development improve log-damage recovery. Timestamp damage, replacement of damaged receipts, and acceptance after a long publication remain unresolved.
- **R1-F3** — `fix_rejected` — Immutable directories solve the switch between versioned packages. The supported migration from the flat layout still removes files under active legacy processes before the replacement is ready.
- **R1-F4** — `fix_verified` — Both helper entry points reload state under helper.lock, verify the host claim and active development phase, and share exclusion with cancellation.
- **R1-F6** — `fix_rejected` — Conflicting nonempty thread IDs, approval policies, and network observations are rejected. Completion ordering and identity-matched rollout selection remain unchecked.
- **R2-F1** — `fix_rejected` — The interrupted multipart stale-head fixture now publishes the full historical rendering. Fully visible retired reviews and other partial-retirement paths still lose substantive records.
- **R2-F2** — `fix_rejected` — The single-envelope damage case blocks. A repeated finding can still be recovered from an earlier envelope when its latest one fails authentication.
- **R2-F3** — `fix_rejected` — Retired siblings are no longer moved. Familiar filenames and cache-directory names still permit mutation of unowned contents, and the legacy inventory check occurs after deletion.
- **R3-F1** — `fix_rejected` — The production round and sequence parsing appears corrected. The cited regression executes no archive operation and cannot detect a wrong envelope committed beside round 100.
- **R3-F2** — `fix_rejected` — The changed-login fixture covers comment and body actor checks. Comment POSTs still lack a current target check, and draft creation retains an earlier actor observation.
- **R3-F3** — `fix_rejected` — The launch arguments and settings composition changed as proposed. The requested observation of an actual ambient-only denial is missing.
- **R3-F4** — `fix_rejected` — The fixture demonstrates recovery after a parseable envelope's digest changes. Truncation raises during parsing before the retirement path is reached.
- **R3-F5** — `fix_rejected` — An existing marked section now preserves surrounding text during replacement. Initial insertion still strips trailing owner text.

#### Evidence assessment

- **Inspected:** The fixed request, mission and owner addenda, repository instructions, operating guide, behavioral protocol, 36-file feature diff, developer report, prior-findings ledger, transcript notice, and unit receipt and log.; The controller entry points, schemas, prompts, permission base, project and checkpoint configuration, behavior suite, live-smoke fixture, and round-three correction diff.
- **Executed verification:** The controller receipt binds the unit command to 1b295b6e70413b024f43645a833dd0e449dd2b20, records exit code 0 and an unchanged worktree, and reports 232.6 seconds. The supplied log records 125 tests, with 124 passing and the opt-in live smoke skipped.; I verified the unit log SHA-256 against the receipt, the mission SHA-256 against the request, the detached HEAD against H, and the Git merge base against M.
- **Source inspection only:** The remaining failure paths below were identified by tracing candidate source and comparing it with the scenarios in the passing tests. They were not reproduced in this read-only review.
- **Required gaps:** R3-F1 lacks an archive execution that distinguishes the round-10 and round-100 envelopes and crosses record 999.; R3-F3 lacks an observation from the launched headless profile showing both an enrolled helper succeeding and a harmless ambient-only allowance being denied.
- **Limitations:** Review was read-only. The executed behavior evidence comes from the controller-run gate. Its model and GitHub boundaries are simulated.; The foreground transcript explicitly withholds the session log. The supplied inputs do not independently establish the reported separate live smoke run 12 or its effective permission behavior.

#### Summary

- **Delivered behavior:** The candidate implements the review loop, candidate-bound unit receipts, structured result validation, reviewer-attempt reconciliation, numeric round limits, publication recovery, and transcript archiving. This round verifies the fixes for activation handoff updates, review-budget enforcement, live-attempt reconciliation, helper cancellation, and pre-ledger record migration.
- **Scope reviewed:** Intermediate controller-core checkpoint for draft PR #1, comparing M 79ab7af62729c2e329f267796780ce36fdffd07c with H 1b295b6e70413b024f43645a833dd0e449dd2b20.
- **Pending later-phase work:** The setup-final checkpoint covers the completed operating documentation, installation and permission handoff, Black Tentacles binding and start command, and final setup acceptance report.
- **Unresolved questions:** none
- **Remaining owner review:** After a valid final checkpoint, the owner decides whether to adopt the workflow and whether to merge or release the draft.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `high` | `high` (turns ['high']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Codex CLI `0.170.0`, thread `01a1fbd4-6328-75b1-9944-cabf099bdfc3`, duration 355.8s, response sha256 `577918e5ff6067ea9f415cc1c92a753daeb2e8f4afad4ab8bd43c4ad880348ef`, request `devproc-claude-agent-review-controller-20261120192057-9024-r04-9d6948`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "1b295b6e70413b024f43645a833dd0e449dd2b20",
  "checkpoint_id": "controller-core",
  "checkpoint_type": "intermediate",
  "decision": "changes_required",
  "decision_rationale": "The candidate-bound unit gate passed. The controller can still advance an intermediate checkpoint after its gate evidence becomes invalid during publication, report a handoff as current against a lagging PR head, and lose substantive review records during retirement. Recovery, publication identity, and installation ownership also have concrete gaps. These affect the controller-core exit conditions.",
  "evidence_assessment": {
    "executed_verification": [
      "The controller receipt binds the unit command to 1b295b6e70413b024f43645a833dd0e449dd2b20, records exit code 0 and an unchanged worktree, and reports 232.6 seconds. The supplied log records 125 tests, with 124 passing and the opt-in live smoke skipped.",
      "I verified the unit log SHA-256 against the receipt, the mission SHA-256 against the request, the detached HEAD against H, and the Git merge base against M."
    ],
    "inspected": [
      "The fixed request, mission and owner addenda, repository instructions, operating guide, behavioral protocol, 36-file feature diff, developer report, prior-findings ledger, transcript notice, and unit receipt and log.",
      "The controller entry points, schemas, prompts, permission base, project and checkpoint configuration, behavior suite, live-smoke fixture, and round-three correction diff."
    ],
    "limitations": [
      "Review was read-only. The executed behavior evidence comes from the controller-run gate. Its model and GitHub boundaries are simulated.",
      "The foreground transcript explicitly withholds the session log. The supplied inputs do not independently establish the reported separate live smoke run 12 or its effective permission behavior."
    ],
    "required_gaps": [
      "R3-F1 lacks an archive execution that distinguishes the round-10 and round-100 envelopes and crosses record 999.",
      "R3-F3 lacks an observation from the launched headless profile showing both an enrolled helper succeeding and a harmless ambient-only allowance being denied."
    ],
    "source_inspection_only": [
      "The remaining failure paths below were identified by tracing candidate source and comparing it with the scenarios in the passing tests. They were not reproduced in this read-only review."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "WF04",
        "WF06"
      ],
      "actual": "missing_publications iterates existing entries. A missing include_receipt key contributes no failure. The regression covers a superseded entry and a deleted remote comment, both of which retain the local publication entry.",
      "blocking_rationale": "status --remote and resume can confirm a handoff without its required receipt.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The exact receipt named by the handoff must exist locally, contain its expected parts, and authenticate against the PR.",
      "id": "R1-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2685
      },
      "priority": "P1",
      "requested_correction": "Look up and validate the named receipt explicitly before checking the rest of the publication inventory.",
      "requested_evidence": "Remove the named entry from a completed fixture enrollment while leaving its other records intact. Verify that status and resume detect the missing receipt.",
      "title": "A handoff can pass verification when its receipt entry is absent",
      "trigger": "A recorded handoff names archive A, but its publication map lacks final-status-<A>."
    },
    {
      "acceptance_ids": [
        "WF08",
        "WF12"
      ],
      "actual": "gate_status orders runs by the receipt body's recorded_at, defaulting to an empty string. A newer failing receipt with that field missing can sort behind an older pass. Conversely, damaged_gates makes an identity-less receipt defeat every later rerun for H. finish_round also checks gates before sending the verdict and only checks H/M after sending it.",
      "blocking_rationale": "A checkpoint can advance on invalid evidence, or a corrected gate run can remain unusable. The test deletes the damaged receipt before exercising recovery.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The latest applicable run controls the gate. A replacement verification can recover a damaged run under a defined rule, and the evidence remains valid when the pass is accepted.",
      "id": "R1-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1999
      },
      "priority": "P1",
      "requested_correction": "Use the controller-written filename to validate run order and receipt structure. Define a recoverable replacement for damaged evidence, and recheck gates immediately before charging or advancing a passing round. Correct any verdict already visible if that check fails.",
      "requested_evidence": "Exercise a newer failure missing recorded_at, recovery without manually deleting evidence, and a log damaged by the simulated publication callback. Verify the round count, checkpoint, and visible verdict in each case.",
      "title": "Receipt ordering and the final acceptance check can admit an invalid gate",
      "trigger": "A receipt loses its timestamp, a damaged receipt remains during a rerun, or gate evidence changes while a passing verdict is being published."
    },
    {
      "acceptance_ids": [
        "WF07"
      ],
      "actual": "Version-to-version installation preserves running versions. The initial migration calls _retire_legacy_flat_install before staging the replacement and without excluding already-running legacy writers or helpers. It unlinks their flat workflow files.",
      "blocking_rationale": "A supported upgrade can remove the workflow resources of a running enrollment. An interruption can also leave the old installation unusable before the launcher exists.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A process that started on the flat installation can finish against one complete version, or migration safely refuses before changing that installation.",
      "id": "R1-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3195
      },
      "priority": "P1",
      "requested_correction": "Stage and verify the replacement first. Coordinate the one-time flat migration with legacy processes and make the transition recoverable before retiring their files.",
      "requested_evidence": "Hold a real legacy controller or helper open during migration, then interrupt migration before the launcher switch. Demonstrate a usable, attributable version in each case.",
      "title": "The first versioned install still dismantles a live flat installation",
      "trigger": "The destination has a legacy MANIFEST.json and a process is still using that installation."
    },
    {
      "acceptance_ids": [
        "WF05"
      ],
      "actual": "parse_codex_events accepts a completion before thread.started and does not require a valid thread ID on each start. provenance uses the supplied ID as part of a glob, takes matches[0], and does not compare session_meta.id with the requested identity. Malformed rollout lines are silently skipped.",
      "blocking_rationale": "A malformed event stream or ambiguous rollout lookup can supply successful completion and apparently compliant provenance without establishing that they belong to the same execution.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "One valid thread identity precedes completion, and one complete, identity-matching rollout supplies the provenance.",
      "id": "R1-F6",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 590
      },
      "priority": "P1",
      "requested_correction": "Validate the thread identifier and completion ordering, require an unambiguous exact rollout identity, and reject malformed provenance through the bounded attempt path.",
      "requested_evidence": "Pass a completion-before-start stream, a missing start ID, an ambiguous rollout, and a mismatched session_meta.id through the real parsers. Verify rejection without advancing a round.",
      "title": "Reviewer completion is still not bound to one verified rollout",
      "trigger": "A malformed stream has a terminal event before its thread identity, or the rollout lookup yields an ambiguous or mismatched file."
    },
    {
      "acceptance_ids": [
        "WF05"
      ],
      "actual": "The child-rollout fallback searches for the thread ID anywhere in another file's raw first line. It does not parse the parent relationship and only scans siblings in the parent's directory.",
      "blocking_rationale": "An unrelated metadata reference can invalidate a legitimate review. A child recorded in another date directory can escape the fallback used to detect indirect delegation.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Delegation is attributed using a recorded dispatch or a structured parent-thread relationship.",
      "id": "R1-F18",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 597
      },
      "priority": "P2",
      "requested_correction": "Check the actual parent identity in session metadata and cover the rollout locations used during the review interval.",
      "requested_evidence": "Include an unrelated session mentioning the ID outside its parent field and a genuine child in the next date directory. Verify both classifications.",
      "title": "Child-session detection still treats unrelated metadata text as delegation",
      "trigger": "Another rollout mentions the review thread in a non-parent field, or a review crosses the rollout date boundary."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF09"
      ],
      "actual": "retire_verdict emits a historical rendering only for a partially visible verdict or an explicitly requested unsent one. A fully visible verdict is marked superseded, and archive skips it. Gate invalidation also calls retire_verdict without the authenticated envelope, so a partially visible verdict on that path loses its remaining parts.",
      "blocking_rationale": "The eventual archive can contain a correction without the substantive review and its provenance. A partial gate-invalidated review can also be incomplete on the PR.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every authenticated retired review remains available in full on the PR and in the committed records, with its envelope and publication identifiers.",
      "id": "R2-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2583
      },
      "priority": "P1",
      "requested_correction": "Preserve the complete authenticated review and envelope for every retirement path. Associate the archived rendering with the publication parts that actually carried it.",
      "requested_evidence": "Complete a later handoff after both a fully posted stale verdict and a partially posted gate-invalidated verdict. Locate the last finding, request identity, and publication links in the PR and committed records.",
      "title": "Retired verdicts can still disappear from the committed exchange",
      "trigger": "H moves just after the full verdict is posted, or gate evidence becomes invalid after only part of an earlier publication reached GitHub."
    },
    {
      "acceptance_ids": [
        "WF08"
      ],
      "actual": "full_findings iterates accepted rounds in order. It can populate a legacy entry from an earlier authenticated envelope, skip the missing or altered latest envelope, and pass the subsequent presence check with outdated text.",
      "blocking_rationale": "The reviewer can close a repeated finding while seeing an older trigger or correction request.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Recovered text comes from the authenticated round that last stated that finding.",
      "id": "R2-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1539
      },
      "priority": "P1",
      "requested_correction": "Bind recovery to the ledger's last applicable finding round. Refuse dispatch when the latest required text cannot be authenticated.",
      "requested_evidence": "Restate one finding differently in two accepted rounds. Remove its embedded ledger text and damage only the second envelope. Verify that the first round's wording cannot satisfy dispatch.",
      "title": "Legacy finding recovery can substitute an older authenticated statement",
      "trigger": "A legacy finding was restated across rounds and only its earlier envelope remains readable and authentic."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "install accepts top-level names from INSTALL_ENTRIES as proof of ownership and replaces an existing agent_review.py even in an unrelated directory. Legacy migration removes manifest files before checking for unknown entries and recursively deletes directories whose only remaining entry is named __pycache__.",
      "blocking_rationale": "An installation attempt can overwrite unrelated code or delete unowned contents, including on a migration that ultimately refuses.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The entire destination and every file proposed for replacement or deletion are checked for ownership before the first mutation.",
      "id": "R2-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3195
      },
      "priority": "P1",
      "requested_correction": "Validate the existing layout and manifest paths before modifying them. Preserve unowned cache contents and refuse to replace an unrelated launcher or pointer solely because its filename matches.",
      "requested_evidence": "Use an unrelated directory containing only agent_review.py and a legacy installation with an unowned cache sentinel and an unexpected file. Verify byte-for-byte preservation on refusal.",
      "title": "Installer ownership checks still allow overwriting or deleting unrelated files",
      "trigger": "A destination contains a familiar filename without an installation identity, or a legacy directory contains data outside its manifest."
    },
    {
      "acceptance_ids": [
        "WF09"
      ],
      "actual": "The production lookup now parses the full round number. The cited test checks the name regex and a separately written regex against literals. It never invokes archive or reads a committed envelope.",
      "blocking_rationale": "The requested regression evidence for correct envelope attribution at the numbering boundary is absent.",
      "blocks_readiness": true,
      "category": "evidence_gap",
      "expected": "A real archive commit demonstrates that round 100 retains its own provenance and that sequence allocation advances past 999.",
      "id": "R3-F1",
      "location": {
        "file": "agent_review/test_agent_review.py",
        "line": 2466
      },
      "priority": "P2",
      "requested_correction": "Exercise the production archive path with distinguishable round-10 and round-100 results and an existing record numbered 999.",
      "requested_evidence": "Read the resulting Git blobs and compare filenames, request IDs, and response hashes with the two input envelopes.",
      "title": "The archive-numbering regression checks expressions without archiving records",
      "trigger": "A long enrollment archives a three-digit round after its record sequence reaches four digits."
    },
    {
      "acceptance_ids": [
        "WF10"
      ],
      "actual": "send now refreshes the actor immediately before POST, but does not repeat pr_view there. A retargeted, closed, or converted PR can still receive the comment. Draft creation also uses the actor observation made before enrollment acquired its writer lock.",
      "blocking_rationale": "A delayed or retried mutation can write outside the enrolled draft-PR conditions.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "At the write boundary the controller checks the applicable target and actor for each GitHub mutation.",
      "id": "R3-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1219
      },
      "priority": "P1",
      "requested_correction": "Apply the open-draft and enrolled PR identity guard alongside the actor guard before comment POSTs, including retries. Refresh the actor immediately before draft creation.",
      "requested_evidence": "Retarget or close the simulated PR after the entry check and before a retry. Separately switch the actor before draft creation. Verify zero writes to the invalid target or under the changed actor.",
      "title": "Comment retries refresh the actor but can still target an ineligible PR",
      "trigger": "The enrolled PR changes while a reviewer runs or a publication retry waits."
    },
    {
      "acceptance_ids": [
        "WF10"
      ],
      "actual": "The gate proves the composed file excludes the ambient rule and the argv contains an empty setting-sources argument. The supplied evidence contains no launched permission decision for that ambient-only command. The reported smoke with no denials does not exercise that decision.",
      "blocking_rationale": "The previous finding explicitly required evidence about effective permissions in the launched developer.",
      "blocks_readiness": true,
      "category": "evidence_gap",
      "expected": "The launched headless developer can use its enrolled helper and receives a denial for a harmless command allowed only by ambient settings.",
      "id": "R3-F3",
      "location": {
        "file": "agent_review/test_agent_review.py",
        "line": 2483
      },
      "priority": "P1",
      "requested_correction": "Supply a focused permission observation from the actual candidate launch profile.",
      "requested_evidence": "Record the candidate and CLI version, the harmless ambient-only allowance, the successful enrolled helper operation, and the denial for the ambient-only operation.",
      "title": "Effective isolation of headless permissions remains unobserved",
      "trigger": "The real CLI launches in a user or project profile with an additional allowance."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF06"
      ],
      "actual": "finish_round parses the envelope before comparing its recorded digest. Truncated JSON raises before retire_verdict runs. The generic command handler pauses the enrollment, and resume repeats the same parse against the same validated round.",
      "blocking_rationale": "An already-visible verdict can remain uncorrected indefinitely, and the normal recovery path cannot obtain a replacement review.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Unreadable, truncated, and digest-mismatched envelopes all trigger durable verdict retirement and replacement.",
      "id": "R3-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1723
      },
      "priority": "P1",
      "requested_correction": "Authenticate the bytes before parsing and handle unreadable or malformed envelopes through the same recoverable invalidation transition. Persist retirement and round invalidation together.",
      "requested_evidence": "Truncate an envelope after a stored but unacknowledged verdict. Restart through the command entry point and verify a visible correction, one fresh review, and a completable handoff.",
      "title": "A truncated preserved envelope bypasses verdict retirement",
      "trigger": "The validated envelope becomes invalid JSON while its verdict publication is pending or already visible."
    },
    {
      "acceptance_ids": [
        "WF06"
      ],
      "actual": "The first insertion uses body.rstrip(), which removes owner-authored trailing spaces, tabs, and blank lines. The test uses text with no trailing whitespace.",
      "blocking_rationale": "The requested preservation guarantee still fails on the first status update.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Appending the first status section preserves the existing PR description exactly.",
      "id": "R3-F5",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2746
      },
      "priority": "P2",
      "requested_correction": "Append the separator and section without stripping the original body.",
      "requested_evidence": "Start with a marker-free description ending in Markdown whitespace and blank lines. Compare the complete original prefix after the first update, then check both sides on a subsequent replacement.",
      "title": "First-time status insertion still alters existing PR description text",
      "trigger": "An enrolled PR has no status markers and its description ends in whitespace."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF09"
      ],
      "actual": "readiness checks pr.headRefOid against A but never checks the current remote branch head. The earlier archive check can be minutes old when the final receipt and body edit finish. handoff_superseded uses the same PR-only observation.",
      "blocking_rationale": "A lagging PR view can permit or reaffirm AWAITING_OWNER_REVIEW after a material push.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Both the pushed branch and PR head still identify A during the final checks and subsequent handoff verification.",
      "id": "R4-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2483
      },
      "priority": "P1",
      "requested_correction": "Check the live enrolled branch head in the shared readiness check, including after publication and during remote status or resume.",
      "requested_evidence": "Push a material commit to the fixture origin during receipt publication while the simulated PR view continues to return A. Verify that the handoff is rejected and any visible receipt is corrected.",
      "title": "Final handoff can accept a stale PR view after the branch has moved",
      "trigger": "The branch advances after archive verification while GitHub's PR projection still reports A."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10",
        "WF12"
      ],
      "actual": "The version-directory key excludes projects, plans, and README.md. If only a shipped gate, permission rule, or checkpoint plan changes, install reuses the existing directory after checking it against its own manifest. It never compares that directory's full file hashes with the new source.",
      "blocking_rationale": "A successful install can silently leave new enrollments using superseded permissions or acceptance gates.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The launcher selects a complete installed package matching the reviewed source, including the configuration used for new enrollments.",
      "id": "R4-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3199
      },
      "priority": "P1",
      "requested_correction": "Use a complete package digest for immutable installation directories. The behavioral fingerprint can remain separate for enrollment activation.",
      "requested_evidence": "Install twice with only a project rule or required checkpoint gate changed. Enroll through the launcher and verify that the new configuration is selected while the previous package remains intact.",
      "title": "Configuration-only upgrades silently reuse the old installed package",
      "trigger": "Two reviewed packages have identical controller code, schemas and prompts, but different project or plan files."
    },
    {
      "acceptance_ids": [
        "WF09",
        "WF10"
      ],
      "actual": "verify_transcript_delta parses Git's quoted text paths and compares archived.get(path) directly with blob_sha256. A quoted path can fail both lookups, yielding None on both sides. For a plain addition under another PR directory, verify_transcripts does not supply a second check.",
      "blocking_rationale": "An unrecognized record can be omitted from the feature diff and accepted as controller-owned.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every addition in the excluded transcript tree has an explicit inventory entry and a successfully read matching blob.",
      "id": "R4-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1168
      },
      "priority": "P1",
      "requested_correction": "Require positive inventory membership and a successful blob read. Parse Git path records without display quoting, for example using NUL-delimited output.",
      "requested_evidence": "Add a plain file with a Git-quoted filename in a different PR transcript directory in a temporary repository. Verify refusal before reviewer dispatch and continued acceptance of genuine controller records.",
      "title": "Two failed lookups can authenticate an excluded transcript addition",
      "trigger": "The feature adds an unrecognized transcript path that Git quotes in raw textual diff output."
    },
    {
      "acceptance_ids": [
        "WF06"
      ],
      "actual": "When POST stores a comment but raises before returning, tentative remains None. If the next listing temporarily omits the stored comment, send POSTs it again. A successful second response is accepted immediately, and missing_publications later checks only the recorded comment ID.",
      "blocking_rationale": "The controller can finish with duplicate requests or verdicts bearing the same marker.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "An uncertain send is reconciled across retries and restart without issuing a duplicate comment.",
      "id": "R4-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1215
      },
      "priority": "P1",
      "requested_correction": "Persist the uncertain-send state, allow bounded time for the marker to become visible, and pause when delivery remains ambiguous. Verify marker uniqueness when confirming publication.",
      "requested_evidence": "Have simulated GitHub store the first comment, lose its response, and omit it from the next successful listing. Restart and verify exactly one remote comment and one acknowledged publication.",
      "title": "A lost POST response followed by a stale listing can duplicate publication",
      "trigger": "The first reconciliation read after an ambiguous POST does not yet show the stored comment."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF10"
      ],
      "actual": "Ordinary controller commands resolve the enrollment and check its status before acquiring the writer lock. guarded reloads state under that lock but does not recheck the command's status eligibility or current claims. A paused process can therefore resume its command after cancellation or replacement and act on its old enrollment.",
      "blocking_rationale": "The helper fix closes this race for push and verify. The controller can still archive or reopen work using authority that has since been withdrawn.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every mutating command verifies its current enrollment ownership and command eligibility under the writer lock.",
      "id": "R4-F5",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 3334
      },
      "priority": "P1",
      "requested_correction": "Revalidate the host and worktree claims and command-specific state after locking, including the activation path. Refuse stale commands before publication, archive writes, or child dispatch.",
      "requested_evidence": "Hold a command after enrollment lookup, cancel or replace that enrollment, then allow the command to acquire the lock. Verify that it makes no commit, post, or launch.",
      "title": "A controller command can outlive the enrollment authority it checked",
      "trigger": "Another command cancels or replaces the enrollment between initial lookup and writer-lock acquisition."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F1",
      "rationale": "Correction queuing survives a failed send, and a superseded named entry is detected. An entirely absent named entry still passes the inventory loop."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F11",
      "rationale": "Activation records receipt retirement and the status edit with the workflow transition. The unit gate exercised failed publication followed by settlement from reloaded state."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F15",
      "rationale": "Resume checks the completed count against the effective limit, and develop_step checks it before dispatch. The regression exercises a stop reason unrelated to the cap."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F16",
      "rationale": "review_round reconciles an unfinished requested or reviewing attempt before candidate capture and supersession. The moved-head regression preserves the live attempt."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F18",
      "rationale": "Direct tool-name checking fixes source-comment misclassification in the main rollout. The replacement child-session

---

<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r04-review part=2/2 sha256=e9fbd87afdc14f5966b2d655fe584003f043a19a11ce45a138238558752f6fa0 -->
_Part 2 of 2._

 fallback still uses raw text matching and a same-directory assumption."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F19",
      "rationale": "Under the enrollment lock, replacement imports the prior archived inventory into the host ledger. Enrollment checks its blobs before writing the new claims. The direct pre-ledger replacement fixture passed."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F2",
      "rationale": "The pre-publication check and return to development improve log-damage recovery. Timestamp damage, replacement of damaged receipts, and acceptance after a long publication remain unresolved."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F3",
      "rationale": "Immutable directories solve the switch between versioned packages. The supported migration from the flat layout still removes files under active legacy processes before the replacement is ready."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R1-F4",
      "rationale": "Both helper entry points reload state under helper.lock, verify the host claim and active development phase, and share exclusion with cancellation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F6",
      "rationale": "Conflicting nonempty thread IDs, approval policies, and network observations are rejected. Completion ordering and identity-matched rollout selection remain unchecked."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F1",
      "rationale": "The interrupted multipart stale-head fixture now publishes the full historical rendering. Fully visible retired reviews and other partial-retirement paths still lose substantive records."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F2",
      "rationale": "The single-envelope damage case blocks. A repeated finding can still be recovered from an earlier envelope when its latest one fails authentication."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R2-F3",
      "rationale": "Retired siblings are no longer moved. Familiar filenames and cache-directory names still permit mutation of unowned contents, and the legacy inventory check occurs after deletion."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R3-F1",
      "rationale": "The production round and sequence parsing appears corrected. The cited regression executes no archive operation and cannot detect a wrong envelope committed beside round 100."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R3-F2",
      "rationale": "The changed-login fixture covers comment and body actor checks. Comment POSTs still lack a current target check, and draft creation retains an earlier actor observation."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R3-F3",
      "rationale": "The launch arguments and settings composition changed as proposed. The requested observation of an actual ambient-only denial is missing."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R3-F4",
      "rationale": "The fixture demonstrates recovery after a parseable envelope's digest changes. Truncation raises during parsing before the retirement path is reached."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R3-F5",
      "rationale": "An existing marked section now preserves surrounding text during replacement. Initial insertion still strips trailing owner text."
    }
  ],
  "request_id": "devproc-claude-agent-review-controller-20261120192057-9024-r04-9d6948",
  "round": 4,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "The candidate implements the review loop, candidate-bound unit receipts, structured result validation, reviewer-attempt reconciliation, numeric round limits, publication recovery, and transcript archiving. This round verifies the fixes for activation handoff updates, review-budget enforcement, live-attempt reconciliation, helper cancellation, and pre-ledger record migration.",
    "pending_later_phase_work": [
      "The setup-final checkpoint covers the completed operating documentation, installation and permission handoff, Black Tentacles binding and start command, and final setup acceptance report."
    ],
    "remaining_owner_review": [
      "After a valid final checkpoint, the owner decides whether to adopt the workflow and whether to merge or release the draft."
    ],
    "scope_reviewed": "Intermediate controller-core checkpoint for draft PR #1, comparing M 79ab7af62729c2e329f267796780ce36fdffd07c with H 1b295b6e70413b024f43645a833dd0e449dd2b20.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
