<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r11-dispositions-36ce9c6535 part=1/1 sha256=36ce9c6535adf90f5b0cc06d0c294eeeba13bf2cae08893811201dff9f4d1ee3 -->
### Claude Opus — finding dispositions — round 11

Candidate after corrections: `2e8f58127ea0fb096d6197c030880292d8231639`

- **R11-F1** — `fixed` — commits: `2e8f58127e`
  Controller.required_gates(cp) resolves the required set as the project's required gates (explicit required_gates, or by default every declared gate) together with the checkpoint's own. A plan can add gates but never drop them, so the generic `single` plan keeps them. The same resolved set drives missing_gates, and therefore report admission, acceptance re-checks and final readiness, as well as the developer prompt's required-gates line. load_project refuses a project that requires an undeclared gate. development-process.json declares `required_gates: ["unit"]` (permissions and live-smoke stay supplemental, as AGENTS.md states). The resolved sets for all 15 shipped projects equal their declared focused-validation gates. Test: FirstReleaseTests.test_generic_plan_keeps_the_projects_required_gates: a single-checkpoint plan without required_gates, where a failed unit run is refused at report admission and the default covers every declared gate.
- **R11-F2** — `fixed` — commits: `2e8f58127e`
  A shared developer_model_problem(cfg, out) checks the stream's init model, its main-thread models, and the models recorded in this invocation's transcript records. develop_step (report admission) and preflight both use it; preflight records observed_models_transcript and derives `ok` from the same check. Test: FirstReleaseTests.test_preflight_uses_the_same_developer_model_check, plus test_conflicting_transcript_model_is_refused for admission.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | about 340s | 191 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | about 30s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | about 70s | Real Opus developer and Astra reviewer; GitHub simulated. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
