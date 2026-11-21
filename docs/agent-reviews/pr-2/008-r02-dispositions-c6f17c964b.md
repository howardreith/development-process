<!-- agent-review:v1 enrollment=devproc-claude-list-command-20261121013957-b56a key=r02-dispositions-c6f17c964b part=1/1 sha256=c6f17c964bd87af04128e55a6c650d2751a2ecc8e3598d5dd2615556a158ab7a -->
### Claude Opus — finding dispositions — round 2

Candidate after corrections: `b66d17218f1de1da446b6918b0aa653840042024`

- **R1-F3** — `fixed` — commits: `b66d17218f`
  As the reviewer suggested, the claim gains an additive `state_dir` field holding the absolute path, set with os.path.abspath when the enrollment is created. `dir` and every other command's behavior are unchanged: find_enrollment, assert_claims and cancel still read `dir`/`enrollment_id`. `_list_row` prefers `state_dir`. Older claims with only a relative `dir` keep the diagnostic.

Test `test_enrollment_with_a_relative_state_root_is_listed_from_any_directory` uses the real fixture. It cancels the original enrollment, re-enrolls through `ar.enroll` with `state_root='rel-root'` from env.root, and checks that `dir` is still 'rel-root\\<id>' and `state_dir` is absolute. It plants a decoy state (AWAITING_OWNER_REVIEW, pr 99) where the relative `dir` would resolve from the work tree. From the work tree, env.root and the bare origin, `list` returns exactly the enrollment's own status (ACTIVE), phase, pr 7 and updated_at. The older-claim decoy test is kept.
- **R1-F4** — `fixed` — commits: `b66d17218f`
  New `local_read_problem` runs remote_path_reason first, then lstat on each existing component from the anchor down. lstat does not traverse symlinks or junctions, and parents are checked before children. Anything with S_ISLNK or FILE_ATTRIBUTE_REPARSE_POINT is refused. It is applied to the registry folder (raises UsageError, exit 4, before is_dir or glob), each claim file, and state_dir/state.json.

`test_links_are_refused_before_they_are_followed` (Windows) creates real junctions with _winapi.CreateJunction. A junction as the state directory and a junction as a parent component are refused with 'reparse point ... did not access it'. The same target read directly gives ACTIVE with pr 5. A junctioned AGENT_REVIEW_HOST_DIR gives exit 4 with nothing on stdout. In every case the tripwire fails the test on any read_json under the junction.

`test_symbolic_links_to_state_or_claim_files_are_refused` uses real symlinks for state.json and for a registry claim file. Both are refused with the tripwire armed, and a control read shows the target itself is readable. It ran on this host.

Link targets are local, so no share is contacted. Remaining limits: refusal is conservative (any link), there is a check-then-open race, mapped-drive detection is tested only in the negative case, and POSIX network mounts are not detected.
- **R2-F1** — `fixed` — commits: `b66d17218f`
  After a successful read, `_list_row` requires `state['enrollment_id'] == claim enrollment_id`, which must be non-null. Otherwise the row is unknown, says 'state file ... belongs to enrollment X, not to this claim's Y; its fields were not used', and phase, pr and updated_at stay null.

Test `test_claim_pointing_at_another_enrollments_state_shows_none_of_its_fields` adds a claim 'm-mismatch' and a claim with no enrollment_id, both pointing at the healthy fixture's real state dir. The healthy row keeps its exact values. Both damaged rows are unknown with null pr, phase and updated_at plus the identity diagnostic.

The long-path case now points to state with matching enrollment_id 'n-local-long' and reads PAUSED with pr 11. The R1-F2 fixtures carry matching IDs, so their pr and status assertions still test typing.

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/636e21b4604b27e3f496dd30830ab340f5274e1d9d370ba46a4a730b69219fad/agent_review.py verify --enrollment devproc-claude-list-command-20261121013957-b56a --gate unit | yes | pass | 345.0s | Controller-run unit gate on the committed, pushed candidate b66d17218f1d: exit 0, worktree_unchanged true. Log: gate-unit-b66d17218f1d-db0c5f1992b-a7601cf9c6c-20261121T072735233484Z.log. The full discover suite ran, including the 11 ListCommandTests. |
| python -m unittest agent_review/test_agent_review.py -k ListCommand -v | no | pass | 7.7s | Focused run before commit: 11 tests, all OK. The Windows-only junction and UNC tests ran, and the symlink test ran rather than skipped, so this host can create symlinks. I did not run the new tests against b0df762, because checkout/restore is outside the command allowlist. What b0df762 does with these inputs: it never writes state_dir, so a relative-root enrollment shows 'unknown'. It has no lstat walk, so a junction or symlink is followed and the tripwire records the read. It has no identity check, so m-mismatch shows ACTIVE with pr 7. |
| python -m unittest discover -s agent_review -p "test_*.py" | no | pass | 344.8s | Local full run on the final tree before commit: 202 tests OK, 1 skipped (the live smoke, which needs AGENT_REVIEW_LIVE). Existing enroll, cancel, claim and registry tests still pass with the extra state_dir claim field. |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
