<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r08-review part=1/1 sha256=2a011ca9330abc94cc9f39b34ae6e497f32bc017097983714feb79da3f6261c4 -->
### Codex GPT-6.2 Astra — review — round 8 — candidate `61b50a0992`

**Decision:** `changes_required` — The three candidate-bound gates passed. Source inspection still identifies paths that can advance a checkpoint using an older gate pass, accept a verdict whose publication is incomplete, or discard conflicting reviewer provenance. Recovery also leaves gaps in persisted budgets and archived records. These affect the controller-core exit conditions.

#### Findings

**R7-F3** · P1 · defect · blocks readiness — A gate finishing between two directory scans can disappear from the evidence check
- Location: `agent_review/agent_review.py:2152`; acceptance: WF07, WF08, WF12
- Trigger: A required gate rerun finishes while a controller command is reading the evidence directory.
- Expected: A reader overlapping completion sees either a pending run or its completed outcome.
- Actual: gate_receipts lists completed JSON files first and pending markers second. A helper can write its failed receipt and remove its marker between those listings. Both listings then omit the newer run, and gate_status returns the older pass. The regression constructs a stationary pending file, so it cannot observe this transition.
- Why it blocks / does not: A required-evidence check can report success while the latest completed validation on H has failed.
- Requested correction: Give each run a durable identity whose pending-to-completed transition readers can observe consistently. Coordinate foreground admission and helper activity so an older pass cannot authorize advancement during that transition.
- Requested evidence: Start with a pass, overlap report admission with a real failing rerun on the same H, and verify that the pending run and its failure both prevent advancement. Verify recovery with a subsequent passing run.

**R1-F6** · P1 · defect · blocks readiness — Later settings can erase conflicting reviewer provenance
- Location: `agent_review/agent_review.py:678`; acceptance: WF05, WF10
- Trigger: A rollout contains multiple applied settings, or a typed tool-call record has an unusable name.
- Expected: Every consumed model and effort observation agrees with policy, and each recorded tool dispatch has an identifiable name.
- Actual: Each thread_settings_applied record overwrites observed_model and observed_effort. An earlier conflicting setting disappears if the last setting and recorded turn contexts match policy. Separately, a function_call with a missing or structured name is converted to text and ignored, leaving its tool identity unverifiable.
- Why it blocks / does not: An otherwise passing result can be accepted with contradictory model metadata or an unidentifiable tool call.
- Requested correction: Retain and validate all applied model and effort observations. Require a nonblank string name for tool-call records used in delegation checks.
- Requested evidence: Supply otherwise valid rollouts with conflicting applied model or effort settings and with an unnamed tool call. Verify rejection through review dispatch and an unchanged completed-round count.

**R7-F4** · P1 · defect · blocks readiness — A locally posted verdict can advance without its complete PR publication
- Location: `agent_review/agent_review.py:1919`; acceptance: WF06, WF12
- Trigger: The controller resumes between verdict publication and checkpoint acceptance.
- Expected: Before accepting a preserved verdict, the controller confirms its complete numbered inventory and authenticates each part on the PR.
- Actual: send returns immediately for a locally posted record. finish_round then checks only the IDs remaining in its parts list. An empty list passes all(), a shortened list can pass, and a comment removed from GitHub during interruption retains its local ID. An intermediate checkpoint can advance without its complete public verdict.
- Why it blocks / does not: Advancement can permanently precede delivery of the review the next phase relies on.
- Requested correction: Apply the complete inventory, marker, actor, and body checks to the specific verdict before committing acceptance. Preserve the existing atomic retirement behavior.
- Requested evidence: Resume a validated intermediate round with a posted multipart verdict after one remote part disappears. Also exercise an empty or shortened local inventory. Neither case may consume a round or advance the checkpoint.

**R5-F2** · P1 · defect · blocks readiness — Reopening can persist ACTIVE before persisting the budget extension
- Location: `agent_review/agent_review.py:2585`; acceptance: WF07, WF08
- Trigger: The owner supplies --max-rounds while reopening a superseded handoff at its previous cap.
- Expected: A reopened enrollment's status and effective round limit are saved together before publication.
- Actual: resume passes the proposed larger limit into reopen. reopen persists ACTIVE/develop using that limit, then settles public operations. The new limit itself is saved later in resume. An interruption during settlement leaves ACTIVE/develop with the exhausted old limit, and helper_authority_problems admits helpers based on status and phase.
- Why it blocks / does not: The durable enrollment can lose the owner's extension while exposing development authority inconsistent with its stored budget.
- Requested correction: Persist the owner-authorized limit in the same transaction that reopens the handoff and selects ACTIVE or BLOCKED.
- Requested evidence: Resume a superseded handoff at its old cap with a larger limit. Interrupt the first public update, reload the enrollment and check the stored limit, helper eligibility, and continuation without repeating the extension.

**R6-F3** · P1 · defect · blocks readiness — Receipt migration can retain obsolete filters or discard current failures
- Location: `agent_review/agent_review.py:2178`; acceptance: WF04, WF08
- Trigger: An existing enrollment activates this controller with pre-upgrade gate receipts.
- Expected: Migration preserves the latest outcome for each still-applicable argument list and retires runs excluded by a changed definition.
- Actual: For timestamp-only filenames, attribution compares only the base command. A legacy run with a now-excluded filter is assigned the current definition, fails argument validation, and keeps the gate failed even after the allowed filter passes. For the immediately preceding hashed format, the old digest covered argv alone. The new reader treats those receipts as replaced even when the declaration was unchanged, so a failure for filter A can disappear when filter B is rerun.
- Why it blocks / does not: Upgrade can either strand a required gate on H or remove an outstanding failure from its decision.
- Requested correction: Handle both predecessor receipt formats using the pinned declaration and recorded arguments. Preserve failing scopes across an unchanged declaration and classify positively excluded arguments as historical.
- Requested evidence: On the same H, migrate an old-hash failure for A and pass B under an unchanged declaration. A must still require recovery. Separately narrow a timestamp-only A/B declaration to B, pass B, and verify that excluded A no longer blocks.

**R6-F1** · P1 · defect · blocks readiness — An existing partial archive never acquires a late-delivered part
- Location: `agent_review/agent_review.py:2640`; acceptance: WF06, WF09
- Trigger: A predecessor enrollment already archived a superseded multipart verdict while a delivery was unresolved.
- Expected: A newly confirmed delivery is represented in an append-only archive record even when an earlier controller archived a partial inventory.
- Actual: archive skips an archived key before reconciling its parts. The preceding version could already have archived one part and marked the whole key archived. When resume later identifies another delivered part, readiness's unresolved-delivery check clears, but the archive still lacks that part and its publication reference.
- Why it blocks / does not: An upgraded enrollment can reach handoff with an incomplete committed review history.
- Requested correction: Compare confirmed deliveries with the archived part inventory. Append a supplemental record for late confirmations and require coverage before handoff.
- Requested evidence: Start from a real partial archive commit and an already-archived key. Reveal the late part, resume, and demonstrate that both authenticated references exist at handoff while the original archive file remains intact.

**R8-F1** · P2 · defect · blocks readiness — The archive exemption also excludes substantive handoff corrections
- Location: `agent_review/agent_review.py:2640`; acceptance: WF06, WF09
- Trigger: An earlier final receipt is corrected before a successor handoff.
- Expected: The final storage receipt has the recursion exemption. Substantive corrections to earlier handoffs are preserved.
- Actual: The archive excludes every publication whose key starts with final-. That includes retirement and supersession corrections, which missing_publications now correctly treats as substantive. The correction can be present on GitHub and absent from every committed transcript.
- Why it blocks / does not: The committed record can omit the message explaining why an earlier public handoff ceased to be current.
- Requested correction: Narrow the archive exemption to storage receipts and include posted correction records in the successor archive.
- Requested evidence: Retire an earlier handoff, complete its successor, and inspect the committed tree for the authenticated retirement correction. Verify that the final receipt still terminates without another archive cycle.

**R8-F2** · P2 · defect · blocks readiness — Activation can reuse a published request under a changed review contract
- Location: `agent_review/agent_review.py:2527`; acceptance: WF04, WF06, WF07
- Trigger: A reviewed workflow or project change is activated after request publication and before a valid result is preserved.
- Expected: A published request remains bound to the workflow and project inputs under which it was issued.
- Actual: Activation invalidates a validated round, but leaves requested and reviewing rounds reusable. The reuse check compares H, M, and checkpoint ID. A subsequent attempt can therefore use the new prompt or instructions under the old request ID, whose already-posted body still identifies the earlier workflow.
- Why it blocks / does not: The published request and its accepted envelope can describe different review contracts.
- Requested correction: Bind workflow and project digests when creating the request. On activation, reconcile any running attempt and supersede an outstanding request whose contract changed before dispatching a new one.
- Requested evidence: Interrupt after request publication, activate a changed reviewer prompt, then resume. Verify distinct request IDs and matching contract identities for the replacement request and accepted envelope.

**R8-F3** · P1 · defect · blocks readiness — A final pass can leave an actionable correctness defect undisposed
- Location: `agent_review/agent_review.py:1873`; acceptance: WF05, WF08
- Trigger: A final reviewer result reports a defect while setting its blocking flag to false.
- Expected: A final pass requires accepted dispositions for actionable correctness findings and permits genuinely optional polish to remain open.
- Actual: The final semantic check considers only blocks_readiness when computing blocking_after. A new finding classified as defect with blocks_readiness false can accompany ready_for_owner_review. finish_round leaves it open, and readiness filters it out again. Protocol section 11 requires a supported, reviewer-accepted disposition for actionable correctness findings.
- Why it blocks / does not: A final handoff can contain a newly reported correctness defect that the developer never addressed and the reviewer never disposed.
- Requested correction: Enforce the final correctness-disposition requirement during semantic validation and final readiness checks.
- Requested evidence: Submit a final pass carrying a new open nonblocking defect and verify rejection. Retain a positive case for clearly classified optional polish.

**R8-F4** · P2 · defect · blocks readiness — Quota failures in the JSON event stream lose their fatal classification
- Location: `agent_review/agent_review.py:1770`; acceptance: WF05, WF08
- Trigger: Codex reports a usage limit through its JSON event stream with no corresponding stderr text.
- Expected: Explicit quota and model-availability failures stop the attempt loop with a precise blocker across supported CLI error channels.
- Actual: parse_codex_events records a generic failure and discards the event's error detail. validate_review searches only stderr for a usage limit or unavailable model. When the CLI reports that condition in JSON on stdout, the controller can spend the remaining attempts and report a generic terminal-event failure.
- Why it blocks / does not: A known quota or model-access blocker should stop dispatch and tell the owner what needs attention.
- Requested correction: Carry structured CLI error information into invocation validation and use it for fatal failure classification.
- Requested evidence: Supply a JSON error or turn.failed event reporting a usage limit with empty stderr. Verify one attempt, zero completed rounds, and a visible quota-specific blocker.

**R8-F5** · P2 · required_gap · blocks readiness — The documented unittest entry point cannot import the live-smoke fixture
- Location: `agent_review/test_live_smoke.py:29`; acceptance: WF01, WF05
- Trigger: An operator selects the smoke with python -m unittest agent_review/test_live_smoke.py -v from the repository root.
- Expected: The explicitly selected smoke loads from the repository root using the command in AGENTS.md.
- Actual: The repository-prescribed unittest invocation imports agent_review.test_live_smoke from the root. Its absolute import of test_agent_review assumes the nested directory is on sys.path, and import agent_review resolves the directory rather than the controller module in that layout. The passing receipt used python agent_review/test_live_smoke.py --gate, which has a different import path.
- Why it blocks / does not: The supplied entry point for explicitly selecting the behavior suite's real-model smoke cannot load the test in the documented repository layout.
- Requested correction: Make the smoke and its shared fixture importable through the prescribed module invocation and the controller gate.
- Requested evidence: From the repository root, run the documented unittest command with live execution disabled first and observe a collected, skipped test. Confirm the explicitly selected live gate still passes.

#### Prior finding assessments

- **R1-F6** — `fix_rejected` — Structured model and approval values and absent payload discriminators now produce validation problems. Applied settings can still overwrite contradictory evidence, and tool-call names remain unchecked.
- **R5-F1** — `fix_verified` — Rebinding derives the full digest from the intended composition, replaces a mismatched staged file, and verifies it before selection. The candidate unit run exercised altered staged and selected files.
- **R5-F2** — `fix_rejected` — The no-extension case now persists BLOCKED with the cleared handoff. The extension path persists ACTIVE before the larger limit that justifies it.
- **R5-F4** — `fix_verified` — Headless launch records transcript byte positions before starting the child and reads appended records for its effort. The same-second regression confirms the previous high observation is excluded.
- **R6-F1** — `fix_rejected` — New archives wait for uncertain parts. Recovery skips predecessor records whose keys are already archived, even when another part is subsequently confirmed. The new readiness assertion also permits success when the fixture has no ready review.
- **R6-F3** — `fix_rejected` — The replacement-command regression passes for timestamp-only receipts. Migration still mishandles excluded legacy arguments and the preceding argv-only definition hash.
- **R7-F1** — `fix_verified` — Activation stages permissions and saves the binding, fingerprint, project, and validated-round invalidation in one transaction. The regression checks durable state after a simulated GitHub failure and after retry.
- **R7-F2** — `fix_verified` — New definition IDs include extra_args_pattern and receipt validation rechecks the recorded arguments. The narrowed-filter test rejects A and accepts a fresh B. Predecessor-format migration is covered by R6-F3.
- **R7-F3** — `fix_rejected` — A stationary pending marker correctly blocks reuse. Independent scans of receipts and markers can miss the same run as it completes.
- **R7-F4** — `fix_rejected` — A superseded verdict now forces rereview, and retirement is saved with invalidation. The acceptance check still trusts an incomplete or stale local publication inventory.
- **R7-F5** — `fix_verified` — The rebinding regression constructs the interrupted state on disk, uses production persistence, reloads the selected digest and path, and verifies altered-file rejection. It passed in the candidate-bound unit gate.

#### Evidence assessment

- **Inspected:** Fixed request, mission, owner addenda, repository instructions, protocol, feature diff, developer report, prior findings ledger, transcript notice, and gate receipts and logs.; Controller request, provenance, gate, publication, activation, resume, archive and readiness paths, with their schemas, prompts, permission configuration, and behavior tests.
- **Executed verification:** Verified the detached HEAD and mission SHA-256 against the request. Recomputed all three gate-log SHA-256 values and matched them to receipts naming the full candidate commit, exit code 0, and an unchanged worktree.; The unit gate ran 169 tests in 306.199 seconds, with one live smoke skipped. The log records the round-seven regression tests as passing.; The permissions gate recorded two real Claude launches. The production profile denied the ambient status command and allowed the enrolled helper and Git inspection. The control profile allowed all three commands.; The separate live-smoke gate ran one real-model fixture in 72.027 seconds. Its log records the headless Opus developer's commit, guarded push, gate receipt, accepted review, and AWAITING_OWNER_REVIEW outcome with simulated GitHub.
- **Source inspection only:** The failure sequences in the findings follow from the candidate's read order, state transitions, and validation conditions. The supplied runs do not execute those sequences.; The live-smoke receipt uses direct script invocation. The repository-root unittest module entry point was inspected separately.
- **Required gaps:** Candidate-bound regressions for gate completion concurrent with a receipt scan, receipt migration across the two older naming schemes, and acceptance after a verdict part disappears.; Recovery evidence for an interrupted round-limit extension, an already archived partial verdict, and workflow activation with a published request still awaiting a result.; Negative review cases for contradictory model settings, unresolved final correctness findings, and quota errors delivered through the JSON event stream.
- **Limitations:** The snapshot permits read-only review. Execution evidence comes from the controller-owned receipts and logs. The foreground developer's whole-session transcript was withheld.; The live smoke exercised a temporary calculator repository and simulated GitHub. The permissions probe establishes the outcomes of its three specific commands.

#### Summary

- **Delivered behavior:** The candidate implements fixed Git snapshots, explicit model launches, schema and identity validation, process locks, publication recovery, controller-run gates, and append-only archives. This revision improves permission rebinding, per-invocation effort attribution, and atomic invalidation of validated results.
- **Scope reviewed:** Intermediate controller-core checkpoint for howardreith/development-process draft PR #1, including controller behavior, schemas, prompts, model and permission configuration, and behavior-test evidence.
- **Pending later-phase work:** The setup-final checkpoint covers complete workflow documentation and installation, repository permissions and bindings, the setup acceptance report, and the exact Black Tentacles start handoff.
- **Unresolved questions:** none
- **Remaining owner review:** Final acceptance of the complete setup and the separate decision on merge or release.

#### Provenance (controller-recorded)

| | Requested | Observed |
|---|---|---|
| Model | `gpt-6.2-astra` | `gpt-6.2-astra` (turns ['gpt-6.2-astra']) |
| Reasoning effort | `high` | `high` (turns ['high']) |
| Sandbox / approvals | read-only / never | `read-only` / `never` |

Codex CLI `0.170.0`, thread `01a1fc79-65d5-7c73-bc05-9d32e5e51334`, duration 383.9s, response sha256 `6fb2bbd44f6f266eebdfddaaccee4b664d9c90d1e88ce102f473c77360cf8ef4`, request `devproc-claude-agent-review-controller-20261120192057-9024-r08-2b792e`. Observed values come from the Codex session rollout's recorded thread settings, not from the model's own statements; the serving backend's model identity is not separately exposed.

<details><summary>Complete structured review (agent-review.review.v1)</summary>

```json
{
  "candidate_commit": "61b50a09921c18f801151511ff7e2d0b5a856a80",
  "checkpoint_id": "controller-core",
  "checkpoint_type": "intermediate",
  "decision": "changes_required",
  "decision_rationale": "The three candidate-bound gates passed. Source inspection still identifies paths that can advance a checkpoint using an older gate pass, accept a verdict whose publication is incomplete, or discard conflicting reviewer provenance. Recovery also leaves gaps in persisted budgets and archived records. These affect the controller-core exit conditions.",
  "evidence_assessment": {
    "executed_verification": [
      "Verified the detached HEAD and mission SHA-256 against the request. Recomputed all three gate-log SHA-256 values and matched them to receipts naming the full candidate commit, exit code 0, and an unchanged worktree.",
      "The unit gate ran 169 tests in 306.199 seconds, with one live smoke skipped. The log records the round-seven regression tests as passing.",
      "The permissions gate recorded two real Claude launches. The production profile denied the ambient status command and allowed the enrolled helper and Git inspection. The control profile allowed all three commands.",
      "The separate live-smoke gate ran one real-model fixture in 72.027 seconds. Its log records the headless Opus developer's commit, guarded push, gate receipt, accepted review, and AWAITING_OWNER_REVIEW outcome with simulated GitHub."
    ],
    "inspected": [
      "Fixed request, mission, owner addenda, repository instructions, protocol, feature diff, developer report, prior findings ledger, transcript notice, and gate receipts and logs.",
      "Controller request, provenance, gate, publication, activation, resume, archive and readiness paths, with their schemas, prompts, permission configuration, and behavior tests."
    ],
    "limitations": [
      "The snapshot permits read-only review. Execution evidence comes from the controller-owned receipts and logs. The foreground developer's whole-session transcript was withheld.",
      "The live smoke exercised a temporary calculator repository and simulated GitHub. The permissions probe establishes the outcomes of its three specific commands."
    ],
    "required_gaps": [
      "Candidate-bound regressions for gate completion concurrent with a receipt scan, receipt migration across the two older naming schemes, and acceptance after a verdict part disappears.",
      "Recovery evidence for an interrupted round-limit extension, an already archived partial verdict, and workflow activation with a published request still awaiting a result.",
      "Negative review cases for contradictory model settings, unresolved final correctness findings, and quota errors delivered through the JSON event stream."
    ],
    "source_inspection_only": [
      "The failure sequences in the findings follow from the candidate's read order, state transitions, and validation conditions. The supplied runs do not execute those sequences.",
      "The live-smoke receipt uses direct script invocation. The repository-root unittest module entry point was inspected separately."
    ]
  },
  "findings": [
    {
      "acceptance_ids": [
        "WF07",
        "WF08",
        "WF12"
      ],
      "actual": "gate_receipts lists completed JSON files first and pending markers second. A helper can write its failed receipt and remove its marker between those listings. Both listings then omit the newer run, and gate_status returns the older pass. The regression constructs a stationary pending file, so it cannot observe this transition.",
      "blocking_rationale": "A required-evidence check can report success while the latest completed validation on H has failed.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A reader overlapping completion sees either a pending run or its completed outcome.",
      "id": "R7-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2152
      },
      "priority": "P1",
      "requested_correction": "Give each run a durable identity whose pending-to-completed transition readers can observe consistently. Coordinate foreground admission and helper activity so an older pass cannot authorize advancement during that transition.",
      "requested_evidence": "Start with a pass, overlap report admission with a real failing rerun on the same H, and verify that the pending run and its failure both prevent advancement. Verify recovery with a subsequent passing run.",
      "title": "A gate finishing between two directory scans can disappear from the evidence check",
      "trigger": "A required gate rerun finishes while a controller command is reading the evidence directory."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF10"
      ],
      "actual": "Each thread_settings_applied record overwrites observed_model and observed_effort. An earlier conflicting setting disappears if the last setting and recorded turn contexts match policy. Separately, a function_call with a missing or structured name is converted to text and ignored, leaving its tool identity unverifiable.",
      "blocking_rationale": "An otherwise passing result can be accepted with contradictory model metadata or an unidentifiable tool call.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Every consumed model and effort observation agrees with policy, and each recorded tool dispatch has an identifiable name.",
      "id": "R1-F6",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 678
      },
      "priority": "P1",
      "requested_correction": "Retain and validate all applied model and effort observations. Require a nonblank string name for tool-call records used in delegation checks.",
      "requested_evidence": "Supply otherwise valid rollouts with conflicting applied model or effort settings and with an unnamed tool call. Verify rejection through review dispatch and an unchanged completed-round count.",
      "title": "Later settings can erase conflicting reviewer provenance",
      "trigger": "A rollout contains multiple applied settings, or a typed tool-call record has an unusable name."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF12"
      ],
      "actual": "send returns immediately for a locally posted record. finish_round then checks only the IDs remaining in its parts list. An empty list passes all(), a shortened list can pass, and a comment removed from GitHub during interruption retains its local ID. An intermediate checkpoint can advance without its complete public verdict.",
      "blocking_rationale": "Advancement can permanently precede delivery of the review the next phase relies on.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Before accepting a preserved verdict, the controller confirms its complete numbered inventory and authenticates each part on the PR.",
      "id": "R7-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1919
      },
      "priority": "P1",
      "requested_correction": "Apply the complete inventory, marker, actor, and body checks to the specific verdict before committing acceptance. Preserve the existing atomic retirement behavior.",
      "requested_evidence": "Resume a validated intermediate round with a posted multipart verdict after one remote part disappears. Also exercise an empty or shortened local inventory. Neither case may consume a round or advance the checkpoint.",
      "title": "A locally posted verdict can advance without its complete PR publication",
      "trigger": "The controller resumes between verdict publication and checkpoint acceptance."
    },
    {
      "acceptance_ids": [
        "WF07",
        "WF08"
      ],
      "actual": "resume passes the proposed larger limit into reopen. reopen persists ACTIVE/develop using that limit, then settles public operations. The new limit itself is saved later in resume. An interruption during settlement leaves ACTIVE/develop with the exhausted old limit, and helper_authority_problems admits helpers based on status and phase.",
      "blocking_rationale": "The durable enrollment can lose the owner's extension while exposing development authority inconsistent with its stored budget.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A reopened enrollment's status and effective round limit are saved together before publication.",
      "id": "R5-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2585
      },
      "priority": "P1",
      "requested_correction": "Persist the owner-authorized limit in the same transaction that reopens the handoff and selects ACTIVE or BLOCKED.",
      "requested_evidence": "Resume a superseded handoff at its old cap with a larger limit. Interrupt the first public update, reload the enrollment and check the stored limit, helper eligibility, and continuation without repeating the extension.",
      "title": "Reopening can persist ACTIVE before persisting the budget extension",
      "trigger": "The owner supplies --max-rounds while reopening a superseded handoff at its previous cap."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF08"
      ],
      "actual": "For timestamp-only filenames, attribution compares only the base command. A legacy run with a now-excluded filter is assigned the current definition, fails argument validation, and keeps the gate failed even after the allowed filter passes. For the immediately preceding hashed format, the old digest covered argv alone. The new reader treats those receipts as replaced even when the declaration was unchanged, so a failure for filter A can disappear when filter B is rerun.",
      "blocking_rationale": "Upgrade can either strand a required gate on H or remove an outstanding failure from its decision.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Migration preserves the latest outcome for each still-applicable argument list and retires runs excluded by a changed definition.",
      "id": "R6-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2178
      },
      "priority": "P1",
      "requested_correction": "Handle both predecessor receipt formats using the pinned declaration and recorded arguments. Preserve failing scopes across an unchanged declaration and classify positively excluded arguments as historical.",
      "requested_evidence": "On the same H, migrate an old-hash failure for A and pass B under an unchanged declaration. A must still require recovery. Separately narrow a timestamp-only A/B declaration to B, pass B, and verify that excluded A no longer blocks.",
      "title": "Receipt migration can retain obsolete filters or discard current failures",
      "trigger": "An existing enrollment activates this controller with pre-upgrade gate receipts."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF09"
      ],
      "actual": "archive skips an archived key before reconciling its parts. The preceding version could already have archived one part and marked the whole key archived. When resume later identifies another delivered part, readiness's unresolved-delivery check clears, but the archive still lacks that part and its publication reference.",
      "blocking_rationale": "An upgraded enrollment can reach handoff with an incomplete committed review history.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A newly confirmed delivery is represented in an append-only archive record even when an earlier controller archived a partial inventory.",
      "id": "R6-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2640
      },
      "priority": "P1",
      "requested_correction": "Compare confirmed deliveries with the archived part inventory. Append a supplemental record for late confirmations and require coverage before handoff.",
      "requested_evidence": "Start from a real partial archive commit and an already-archived key. Reveal the late part, resume, and demonstrate that both authenticated references exist at handoff while the original archive file remains intact.",
      "title": "An existing partial archive never acquires a late-delivered part",
      "trigger": "A predecessor enrollment already archived a superseded multipart verdict while a delivery was unresolved."
    },
    {
      "acceptance_ids": [
        "WF06",
        "WF09"
      ],
      "actual": "The archive excludes every publication whose key starts with final-. That includes retirement and supersession corrections, which missing_publications now correctly treats as substantive. The correction can be present on GitHub and absent from every committed transcript.",
      "blocking_rationale": "The committed record can omit the message explaining why an earlier public handoff ceased to be current.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "The final storage receipt has the recursion exemption. Substantive corrections to earlier handoffs are preserved.",
      "id": "R8-F1",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2640
      },
      "priority": "P2",
      "requested_correction": "Narrow the archive exemption to storage receipts and include posted correction records in the successor archive.",
      "requested_evidence": "Retire an earlier handoff, complete its successor, and inspect the committed tree for the authenticated retirement correction. Verify that the final receipt still terminates without another archive cycle.",
      "title": "The archive exemption also excludes substantive handoff corrections",
      "trigger": "An earlier final receipt is corrected before a successor handoff."
    },
    {
      "acceptance_ids": [
        "WF04",
        "WF06",
        "WF07"
      ],
      "actual": "Activation invalidates a validated round, but leaves requested and reviewing rounds reusable. The reuse check compares H, M, and checkpoint ID. A subsequent attempt can therefore use the new prompt or instructions under the old request ID, whose already-posted body still identifies the earlier workflow.",
      "blocking_rationale": "The published request and its accepted envelope can describe different review contracts.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A published request remains bound to the workflow and project inputs under which it was issued.",
      "id": "R8-F2",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 2527
      },
      "priority": "P2",
      "requested_correction": "Bind workflow and project digests when creating the request. On activation, reconcile any running attempt and supersede an outstanding request whose contract changed before dispatching a new one.",
      "requested_evidence": "Interrupt after request publication, activate a changed reviewer prompt, then resume. Verify distinct request IDs and matching contract identities for the replacement request and accepted envelope.",
      "title": "Activation can reuse a published request under a changed review contract",
      "trigger": "A reviewed workflow or project change is activated after request publication and before a valid result is preserved."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF08"
      ],
      "actual": "The final semantic check considers only blocks_readiness when computing blocking_after. A new finding classified as defect with blocks_readiness false can accompany ready_for_owner_review. finish_round leaves it open, and readiness filters it out again. Protocol section 11 requires a supported, reviewer-accepted disposition for actionable correctness findings.",
      "blocking_rationale": "A final handoff can contain a newly reported correctness defect that the developer never addressed and the reviewer never disposed.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "A final pass requires accepted dispositions for actionable correctness findings and permits genuinely optional polish to remain open.",
      "id": "R8-F3",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1873
      },
      "priority": "P1",
      "requested_correction": "Enforce the final correctness-disposition requirement during semantic validation and final readiness checks.",
      "requested_evidence": "Submit a final pass carrying a new open nonblocking defect and verify rejection. Retain a positive case for clearly classified optional polish.",
      "title": "A final pass can leave an actionable correctness defect undisposed",
      "trigger": "A final reviewer result reports a defect while setting its blocking flag to false."
    },
    {
      "acceptance_ids": [
        "WF05",
        "WF08"
      ],
      "actual": "parse_codex_events records a generic failure and discards the event's error detail. validate_review searches only stderr for a usage limit or unavailable model. When the CLI reports that condition in JSON on stdout, the controller can spend the remaining attempts and report a generic terminal-event failure.",
      "blocking_rationale": "A known quota or model-access blocker should stop dispatch and tell the owner what needs attention.",
      "blocks_readiness": true,
      "category": "defect",
      "expected": "Explicit quota and model-availability failures stop the attempt loop with a precise blocker across supported CLI error channels.",
      "id": "R8-F4",
      "location": {
        "file": "agent_review/agent_review.py",
        "line": 1770
      },
      "priority": "P2",
      "requested_correction": "Carry structured CLI error information into invocation validation and use it for fatal failure classification.",
      "requested_evidence": "Supply a JSON error or turn.failed event reporting a usage limit with empty stderr. Verify one attempt, zero completed rounds, and a visible quota-specific blocker.",
      "title": "Quota failures in the JSON event stream lose their fatal classification",
      "trigger": "Codex reports a usage limit through its JSON event stream with no corresponding stderr text."
    },
    {
      "acceptance_ids": [
        "WF01",
        "WF05"
      ],
      "actual": "The repository-prescribed unittest invocation imports agent_review.test_live_smoke from the root. Its absolute import of test_agent_review assumes the nested directory is on sys.path, and import agent_review resolves the directory rather than the controller module in that layout. The passing receipt used python agent_review/test_live_smoke.py --gate, which has a different import path.",
      "blocking_rationale": "The supplied entry point for explicitly selecting the behavior suite's real-model smoke cannot load the test in the documented repository layout.",
      "blocks_readiness": true,
      "category": "required_gap",
      "expected": "The explicitly selected smoke loads from the repository root using the command in AGENTS.md.",
      "id": "R8-F5",
      "location": {
        "file": "agent_review/test_live_smoke.py",
        "line": 29
      },
      "priority": "P2",
      "requested_correction": "Make the smoke and its shared fixture importable through the prescribed module invocation and the controller gate.",
      "requested_evidence": "From the repository root, run the documented unittest command with live execution disabled first and observe a collected, skipped test. Confirm the explicitly selected live gate still passes.",
      "title": "The documented unittest entry point cannot import the live-smoke fixture",
      "trigger": "An operator selects the smoke with python -m unittest agent_review/test_live_smoke.py -v from the repository root."
    }
  ],
  "prior_finding_assessments": [
    {
      "assessment": "fix_rejected",
      "finding_id": "R1-F6",
      "rationale": "Structured model and approval values and absent payload discriminators now produce validation problems. Applied settings can still overwrite contradictory evidence, and tool-call names remain unchecked."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R5-F1",
      "rationale": "Rebinding derives the full digest from the intended composition, replaces a mismatched staged file, and verifies it before selection. The candidate unit run exercised altered staged and selected files."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R5-F2",
      "rationale": "The no-extension case now persists BLOCKED with the cleared handoff. The extension path persists ACTIVE before the larger limit that justifies it."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R5-F4",
      "rationale": "Headless launch records transcript byte positions before starting the child and reads appended records for its effort. The same-second regression confirms the previous high observation is excluded."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R6-F1",
      "rationale": "New archives wait for uncertain parts. Recovery skips predecessor records whose keys are already archived, even when another part is subsequently confirmed. The new readiness assertion also permits success when the fixture has no ready review."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R6-F3",
      "rationale": "The replacement-command regression passes for timestamp-only receipts. Migration still mishandles excluded legacy arguments and the preceding argv-only definition hash."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R7-F1",
      "rationale": "Activation stages permissions and saves the binding, fingerprint, project, and validated-round invalidation in one transaction. The regression checks durable state after a simulated GitHub failure and after retry."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R7-F2",
      "rationale": "New definition IDs include extra_args_pattern and receipt validation rechecks the recorded arguments. The narrowed-filter test rejects A and accepts a fresh B. Predecessor-format migration is covered by R6-F3."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R7-F3",
      "rationale": "A stationary pending marker correctly blocks reuse. Independent scans of receipts and markers can miss the same run as it completes."
    },
    {
      "assessment": "fix_rejected",
      "finding_id": "R7-F4",
      "rationale": "A superseded verdict now forces rereview, and retirement is saved with invalidation. The acceptance check still trusts an incomplete or stale local publication inventory."
    },
    {
      "assessment": "fix_verified",
      "finding_id": "R7-F5",
      "rationale": "The rebinding regression constructs the interrupted state on disk, uses production persistence, reloads the selected digest and path, and verifies altered-file rejection. It passed in the candidate-bound unit gate."
    }
  ],
  "request_id": "devproc-claude-agent-review-controller-20261120192057-9024-r08-2b792e",
  "round": 8,
  "schema_version": "agent-review.review.v1",
  "summary": {
    "delivered_behavior": "The candidate implements fixed Git snapshots, explicit model launches, schema and identity validation, process locks, publication recovery, controller-run gates, and append-only archives. This revision improves permission rebinding, per-invocation effort attribution, and atomic invalidation of validated results.",
    "pending_later_phase_work": [
      "The setup-final checkpoint covers complete workflow documentation and installation, repository permissions and bindings, the setup acceptance report, and the exact Black Tentacles start handoff."
    ],
    "remaining_owner_review": [
      "Final acceptance of the complete setup and the separate decision on merge or release."
    ],
    "scope_reviewed": "Intermediate controller-core checkpoint for howardreith/development-process draft PR #1, including controller behavior, schemas, prompts, model and permission configuration, and behavior-test evidence.",
    "unresolved_questions": []
  }
}
```
</details>

_Model-generated review by Codex using the requested model, posted by the agent-review controller through the owner's GitHub account. Not a human review or approval._
