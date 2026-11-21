<!-- agent-review:v1 enrollment=devproc-claude-list-command-20261121013957-b56a key=r01-request part=1/1 sha256=65ef40d702643877c45c1846e6ba8830ccf08ef5017ddc12f07f4ef18118c77f -->
### Claude Opus — review request — round 1 — candidate `af2d1768c1`

| Field | Value |
|---|---|
| Request ID | `devproc-claude-list-command-20261121013957-b56a-r01-fa5bf9` |
| Checkpoint | `final` (final) |
| Candidate H | `af2d1768c1d775e84c1cb6f68452df9c4c14d707` |
| Target B (`claude/agent-review-controller`) | `2e8f58127ea0fb096d6197c030880292d8231639` |
| Merge base M | `2e8f58127ea0fb096d6197c030880292d8231639` |
| Mission | `list-command` sha256 `11e46e96cf` |
| Workflow | `6d55b038c5` |
| Developer observed | headless session `e0fa5299-068f-45a3-b1bd-cac2a4644a7e`: init `claude-opus-5-5`, API models ['claude-opus-5-5'], effort ['high'] |
| Reviewer requested | Codex `gpt-6.2-astra`, effort `high`, read-only sandbox |
| Round budget | 1 of 5 |

**Scope:** The complete mission as written.

**Exit conditions:**
- Every requirement of the mission is implemented with behavior tests; nothing weakened or dropped.
- The unit gate passes on the committed, pushed candidate.
- Deviations and limitations are stated explicitly.

**Developer summary:**

Implemented the read-only `list` subcommand (mission sha256 11e46e96…). `list_enrollments()` in agent_review/agent_review.py globs `host_dir()/registry/*.json`. It builds one object per claim with `enrollment`, `repository`, `branch` and, from that enrollment's state.json, `status`, `phase`, `pr` (the number, or null) and `updated_at`, sorted by enrollment ID. `main(["list"])` prints the array as JSON and exits 0.

Req 2: if a state file is missing, unreadable, not valid JSON or not an object, the claim is still listed with status "unknown" and an `error` naming the path and cause. This also covers a damaged claim file and a claim with no `dir` (these rows have enrollment null and sort last).

Req 3: the command takes no Lock, writes nothing, does not even mkdir the registry, starts no process (no git or gh) and opens no socket.

Req 4: there are three behavior tests in ListCommandTests on the real Env fixture (real temporary repo, real enrollment, real registry claim and state):
- An enrollment is listed with exact field values. This runs while the owning controller holds its real writer lock, and a full mtime/size snapshot of the fixture tree is unchanged afterwards.
- An empty registry prints `[]`. The real cancel releases the only claim, and a never-created host dir also gives `[]` and stays uncreated.
- A damaged state.json, a claim pointing at a missing state dir and a garbage claim file are each reported "unknown" with an error, sorted correctly, and the command exits 0.
To prove req 3, all three run under a clearly labeled tripwire that fails the test if subprocess.Popen, socket.connect or socket.create_connection is called. It answers nothing for the code, so it is not a simulated response or stub.

Req 5: README documents `list` in the Running-a-mission command block next to `status`/`stop`, plus a paragraph on output, read-only guarantees and damaged-entry behavior.

No other command's behavior changed: only a new parser entry and a new branch before `enroll` were added.

Deviations and limitations:
- `error` appears only on damaged rows.
- Rows from a damaged claim have null enrollment/repository/branch and sort after every valid ID.
- Cancelled enrollments are not listed, because cancel deletes their registry claim (existing behavior).
- Per-worktree marker files outside the registry are not scanned, since the mission scopes the command to the host registry.
- Standard library only.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/636e21b4604b27e3f496dd30830ab340f5274e1d9d370ba46a4a730b69219fad/agent_review.py verify --enrollment devproc-claude-list-command-20261121013957-b56a --gate unit | yes | pass | 338.7s | Controller-run unit gate on committed and pushed candidate af2d1768c1d7: exit 0, worktree_unchanged true, log gate-unit-af2d1768c1d7-db0c5f1992b-a7601cf9c6c-20261121T065357262403Z.log. Full discover suite (194 tests incl. the 3 new ListCommandTests). |
| python -m unittest agent_review/test_agent_review.py -k ListCommand -v | no | pass | 2.3s | Focused run of the 3 new tests before commit, on the pre-commit tree. One later test-only edit (stamping updated_at via ctl.save) is covered by the full runs below. |
| python -m unittest discover -s agent_review -p "test_*.py" | no | pass | 339.1s | Local full run on the final working tree before commit: 194 tests OK, 1 skipped (the live smoke, which needs AGENT_REVIEW_LIVE). The JSON printed to stdout comes from existing tests that print controller stops. |

**Evidence references:**
- commit af2d1768c1d775e84c1cb6f68452df9c4c14d707 (pushed via guarded push)
- gate-unit-af2d1768c1d7-db0c5f1992b-a7601cf9c6c-20261121T065357262403Z.log
- agent_review/agent_review.py: list_enrollments() after find_enrollment; `list` parser entry and dispatch in main()
- agent_review/test_agent_review.py: ListCommandTests, tree_snapshot, forbid_processes_and_network
- agent_review/README.md: Running a mission command block and `list` paragraph

_Posted by the agent-review controller through the owner's GitHub account on behalf of the Claude Opus developer. Automated request; not a human review._
