<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r13-dispositions-7f731e50fc part=1/1 sha256=7f731e50fc7b722e37a81a12d6593690ebab134a1ea7c87dee65819fe0f4639a -->
### Claude Opus — finding dispositions — round 13

Candidate after corrections: `69bcb4e2834bb719d52472194bf42661bb081968`

- **R13-F1** — `fixed` — commits: `69bcb4e283`
  agent_review.py enroll(): state_root = Path(expand(...)).resolve(); prior_claim_state() refuses unverifiable ownership (missing/unreadable/foreign state, relative or malformed claim) before any state folder is created; find_enrollment refuses relative claims. Tests EnrollmentOwnershipTests.test_relative_state_root_is_resolved_and_a_second_enrollment_elsewhere_is_refused and test_claim_whose_prior_state_cannot_be_established_is_not_replaced; both claims are compared byte for byte after each refusal. Both fail against 14cb454.
- **R13-F2** — `fixed` — commits: `69bcb4e283`
  planning/AGENT-REVIEW-SETUP-ACCEPTANCE.md 'Handoff readback': gh pr view 2 (open draft, no requested reviewers, head b89fa6c), handoff status comment key=final-status-b89fa6c72d naming H bc4b300 / A b89fa6c / M / B, git diff --stat bc4b300 b89fa6c = four transcript files, status --remote handoff_current true.
- **R13-F3** — `fixed` — commits: `69bcb4e283`
  Acceptance report: 5 developer invocations and a per-round candidate table (af2d176, b0df762, b66d172, c391eff, then the transcript-only successor bc4b300 with the fifth invocation's fresh report and unit run). WF01 says all 5 invocations.
- **R13-F4** — `fixed` — commits: `69bcb4e283`
  docs/AGENT-REVIEW-WORKFLOW.md added: an entry point mapping topics to agent_review/README.md sections, without duplicating instructions.
- **R13-F5** — `fixed` — commits: `69bcb4e283`
  agent_review/README.md 'Install, upgrade, disable': install adds an immutable version and does not wait for controllers; activation is explicit between runs; stop is asynchronous (wait for a non-ACTIVE status, developer_running false, lock_holder null); permanent disable waits for runtime locks, cancels until CANCELLED (cancel refuses under live developer/helper/runtime), and only then removes files.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | about 352s | Full behavior suite (194 tests; the opt-in live test skipped by design). |
| verify --gate permissions | yes | pass | a few minutes | Real headless launches: the user-level allowance is denied under --setting-sources '' and runs in the control launch. |
| verify --gate live-smoke | yes | pass | a few minutes | Real Opus developer and Astra reviewer on a fixture repository; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
