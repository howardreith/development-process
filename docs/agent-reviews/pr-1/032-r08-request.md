<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r08-request part=1/1 sha256=6a15c6cceb4cedd11e09e008f1a8c1015972ae6431dcc19606886798557558da -->
### Claude Opus — review request — round 8 — candidate `61b50a0992`

| Field | Value |
|---|---|
| Request ID | `devproc-claude-agent-review-controller-20261120192057-9024-r08-2b792e` |
| Checkpoint | `controller-core` (intermediate) |
| Candidate H | `61b50a09921c18f801151511ff7e2d0b5a856a80` |
| Target B (`main`) | `79ab7af62729c2e329f267796780ce36fdffd07c` |
| Merge base M | `79ab7af62729c2e329f267796780ce36fdffd07c` |
| Mission | `agent-review-setup` sha256 `0ae972cfa8` |
| Workflow | `33eb5e5e00` |
| Developer observed | foreground session `8d9c01f2-9d44-41c8-a695-d47ecffee8d2`: models ['claude-opus-5-5'], effort ['high'] (CLI-recorded transcript) |
| Reviewer requested | Codex `gpt-6.2-astra`, effort `high`, read-only sandbox |
| Round budget | 8 of 9 |

**Scope:** Controller, versioned reviewer/developer schemas, prompts, model/permission configuration and behavior tests (tools/agent_review/).

**Exit conditions:**
- Controller enforces candidate identity (H/B/M), explicit model selection with requested/observed provenance, schema/request validation, single-writer lock, idempotent publication, bounded retries, round budget, stop/resume and the transcript-only archive check.
- Behavior tests with real temporary Git repositories cover protocol rows WF04-WF10 and WF12; only the model and GitHub boundaries are stubbed.
- No path lets a malformed, failed, wrong-model or stale review produce readiness.

**Developer summary:**

Round-7 corrections in 61b50a0992. The structural change is that composite state transitions are now single transactions (deferred saves, rollback on failure, no sends inside), which removes the class of half-persisted transitions behind several findings. 169 behavior tests; unit, permissions and live-smoke gates run by the controller on this candidate.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit | yes | pass | 310s | 169 behavior tests (1 live test skipped by design). |
| verify --gate permissions | no | pass | about 30s | Two real headless Claude launches; CLI-recorded decisions. |
| verify --gate live-smoke | no | pass | about 70s | Real Opus developer and Astra reviewer; GitHub simulated. |

**Prior findings to assess:** `R1-F6`, `R5-F1`, `R5-F2`, `R5-F4`, `R6-F1`, `R6-F3`, `R7-F1`, `R7-F2`, `R7-F3`, `R7-F4`, `R7-F5`

_Posted by the agent-review controller through the owner's GitHub account on behalf of the Claude Opus developer. Automated request; not a human review._
