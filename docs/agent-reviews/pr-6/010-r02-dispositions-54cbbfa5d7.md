<!-- agent-review:v1 enrollment=devproc-claude-continuation-handoff-20261122025808-720e key=r02-dispositions-54cbbfa5d7 part=1/1 sha256=54cbbfa5d76a9ce621c906806a9d11c98984b7ab538ce9b5c911dba4257e30e9 -->
### Claude Opus — finding dispositions — round 2

Candidate after corrections: `8f8f83ee61ee088412cb24eb2669d2dc1df6aa1d`

- **R1-F3** — `fixed` — commits: `8f8f83ee61`
  apply_amendment now picks the correction from confirmed delivery. If the validated verdict was never delivered, the posted request gets the withdrawal correction, which names the round and commit. If no handoff reached the PR, the ready verdict gets the 'not current' correction and no reopened notice is posted. Tests: AmendmentBoundaryTests.test_a_failed_verdict_post_closes_the_posted_request and test_a_failed_first_receipt_post_corrects_the_ready_verdict_and_claims_no_handoff. Both assert the exact PR correction and that no extra reviewer launch occurs. A mutation check confirmed the first test fails without the fix.
- **R1-F5** — `fixed` — commits: `8f8f83ee61`
  The refusal-matrix subtest first refuses the unsafe file with state unchanged. In the same enrollment it then applies a PR-safe file, accepts a checkpoint-ready report and publishes the review request. The test asserts the request contains the safe text, revision 1 and the digest row/heading, and that the reviewer request is bound to amendment revision 1.
- **R2-F1** — `fixed` — commits: `8f8f83ee61`
  A partly delivered or undelivered request is now marked withdrawn; a fully delivered one stays posted. missing_publications verifies the delivered parts of a withdrawn request and flags a withdrawn part if it appears on the PR. status pending_publications, send, guidance eligibility and the archive all recognize the withdrawn state. The partial-delivery test runs through to a verified handoff. It checks the request is absent from pending_publications and the archived 'Withdrawn record' header. Editing or deleting the delivered part on simulated GitHub makes status --remote report handoff_current false and name r01-request.
- **R2-F2** — `fixed` — commits: `8f8f83ee61`
  The replay check now covers every recorded revision, not only the latest. Test test_retrying_an_older_saved_file_never_reinstates_it_over_a_later_amendment applies A, then B, then retries A's file: the retry is refused, the state bytes and agent calls are unchanged, and B stays selected. A new file with A's exact text is then accepted as revision 3. A mutation check confirmed the test fails without the fix.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/7e8bb030d54a1f439a4eebb537110bd52f9dc3ade47ef31cc62c399adab86aca/agent_review.py verify --enrollment devproc-claude-continuation-handoff-20261122025808-720e --gate unit | yes | pass | 659.4s | Required gate run by the controller on pushed candidate 8f8f83e: the full unit suite. Receipt log gate-unit-8f8f83ee61ee-db0c5f1992b-a7601cf9c6c-20261122T145201292053Z.log. The live-model tests are skipped in this gate. |
| python -m unittest (continuation, amendment, guidance and publication test classes) | no | pass | 235.3s | 52 focused tests on real Git, controller, publication and archive fixtures. Claude, Codex and GitHub are simulated. The first run had one failure and one error, both from assertions that still expected the old `superseded` request state. I updated those assertions to the new posted/withdrawn rule before this passing run. |
| Mutation checks on the validated-verdict withdrawal and the full-history replay check | no | pass | 3.6s | With each fix removed, its new test failed. Both fixes were restored afterwards. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
