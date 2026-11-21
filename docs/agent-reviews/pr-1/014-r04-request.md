<!-- agent-review:v1 enrollment=devproc-claude-agent-review-controller-20261120192057-9024 key=r04-request part=1/1 sha256=09c0c756e5aa847ff2a84d28baed3149ad0439524130b6aeb3b6b232c40db92d -->
### Claude Opus — review request — round 4 — candidate `1b295b6e70`

| Field | Value |
|---|---|
| Request ID | `devproc-claude-agent-review-controller-20261120192057-9024-r04-9d6948` |
| Checkpoint | `controller-core` (intermediate) |
| Candidate H | `1b295b6e70413b024f43645a833dd0e449dd2b20` |
| Target B (`main`) | `79ab7af62729c2e329f267796780ce36fdffd07c` |
| Merge base M | `79ab7af62729c2e329f267796780ce36fdffd07c` |
| Mission | `agent-review-setup` sha256 `0ae972cfa8` |
| Workflow | `1e6c5f3cd5` |
| Developer observed | foreground session `8d9c01f2-9d44-41c8-a695-d47ecffee8d2`: models ['claude-opus-5-5'], effort ['high'] (CLI-recorded transcript) |
| Reviewer requested | Codex `gpt-6.2-astra`, effort `high`, read-only sandbox |
| Round budget | 4 of 5 |

**Scope:** Controller, versioned reviewer/developer schemas, prompts, model/permission configuration and behavior tests (tools/agent_review/).

**Exit conditions:**
- Controller enforces candidate identity (H/B/M), explicit model selection with requested/observed provenance, schema/request validation, single-writer lock, idempotent publication, bounded retries, round budget, stop/resume and the transcript-only archive check.
- Behavior tests with real temporary Git repositories cover protocol rows WF04-WF10 and WF12; only the model and GitHub boundaries are stubbed.
- No path lets a malformed, failed, wrong-model or stale review produce readiness.

**Developer summary:**

Round-3 corrections in 1b295b6e70, including three structural changes to remove whole classes of findings: immutable versioned installs behind a launcher (no swaps or deletions), shared crash-safe retirement of verdicts and receipts with durable public operations, and structured delegation detection. 125 behavior tests; the installed copy was migrated to the versioned layout live. Live smoke run 12 (headless Opus, isolated settings sources, real Astra) reached AWAITING_OWNER_REVIEW with no denials. Resumed under the owner's instruction to continue until everything is fixed.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| verify --gate unit (controller-run behavior suite) | yes | pass | 233s | 125 behavior tests (1 live test skipped by design). |
| AGENT_REVIEW_LIVE=1 python -m unittest agent_review/test_live_smoke.py (run 12) | no | pass | 64s | Real models, simulated GitHub. |

**Prior findings to assess:** `R1-F1`, `R1-F11`, `R1-F15`, `R1-F16`, `R1-F18`, `R1-F19`, `R1-F2`, `R1-F3`, `R1-F4`, `R1-F6`, `R2-F1`, `R2-F2`, `R2-F3`, `R3-F1`, `R3-F2`, `R3-F3`, `R3-F4`, `R3-F5`

_Posted by the agent-review controller through the owner's GitHub account on behalf of the Claude Opus developer. Automated request; not a human review._
