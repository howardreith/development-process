<!-- agent-review:v1 enrollment=devproc-claude-list-command-20261121013957-b56a key=r03-dispositions-d07e3a4e2d part=1/1 sha256=d07e3a4e2d8ee574eb7261e1c25e9aacc13be74bcb4c80baa8c4bc0bfcdf794e -->
### Claude Opus — finding dispositions — round 3

Candidate after corrections: `c391eff6edfc82e82b103651397e361ba17a41ab`

- **R1-F4** — `fixed` — commits: `c391eff6ed`
  agent_review.py `inspect_local_path`:
- A FileNotFoundError during the component walk now returns PATH_MISSING instead of None.
- `_list_row` reports a missing state file ('state file is missing: ...') without opening it, and a vanished claim file without reading it.
- `list_enrollments` treats a missing registry as [].
- Any '..' in Path.parts is refused before the walk, so the path that is opened is exactly the one inspected component by component.

Test `test_noncanonical_or_missing_paths_are_never_opened` (Windows) uses a real junction:
- Claim `<root>\\missing\\..\\junction` gives unknown with a "'..' segment" diagnostic. The tripwire, which compares normalized paths, fails the test on any read under the junction.
- A local `missing\\..\\other-state\\target` path is refused the same way (conservative).
- A claim with a missing component (`<root>\\nope\\x`) is reported 'state file is missing' with the tripwire forbidding reads under that path.
- The healthy enrollment keeps its exact fields.

Earlier junction, symlink, UNC and registry-link tests still pass.
- **R3-F1** — `fixed` — commits: `c391eff6ed`
  `list_enrollments` enumerates the registry with `os.scandir` inside a try block. Any OSError becomes UsageError('host registry ... cannot be enumerated: ...'), so the CLI prints the refusal on stderr and exits 4 (EXIT_USAGE) with nothing on stdout. An absent registry (PATH_MISSING) and a readable empty registry still print [], and test_empty_registry_prints_an_empty_array still passes.

Test `test_unreadable_registry_is_refused_not_reported_empty` uses the fixture's populated registry:
- On Windows it disables SeBackupPrivilege in the test process token (this host's elevated token has it enabled, which bypasses DACLs) and adds a deny-RD ACE with icacls. It then confirms the condition: os.listdir raises PermissionError and is_dir() is True.
- It asserts exit 4, empty stdout, and 'cannot be enumerated' plus 'registry' in stderr.
- Cleanup removes the ACE and restores the privilege.
- On POSIX it uses chmod 0o300 and skips when running as root.

Test `test_registry_that_is_not_a_directory_is_refused` covers another scan error: a file where the registry should be also gives exit 4 instead of [].

**Validation (developer-reported):**

| Command | Required | Result | Duration | Scope and limits |
|---|---|---|---|---|
| python C:/Dev/agent-review/versions/636e21b4604b27e3f496dd30830ab340f5274e1d9d370ba46a4a730b69219fad/agent_review.py verify --enrollment devproc-claude-list-command-20261121013957-b56a --gate unit | yes | pass | 350.7s | Controller-run unit gate on the committed, pushed candidate c391eff6edfc: exit 0, worktree_unchanged true. Log: gate-unit-c391eff6edfc-db0c5f1992b-a7601cf9c6c-20261121T074535768225Z.log. Full discover suite, including the 14 ListCommandTests. |
| python -m unittest agent_review/test_agent_review.py -k ListCommand -v | no | pass | 9.8s | Focused run before commit: 14 tests OK. The first attempt at the R3-F1 test failed because the deny ACE had no effect while SeBackupPrivilege was enabled; a temporary diagnostic run (icacls output and whoami /priv) confirmed this, and the diagnostic was removed afterwards. The new tests were not run against b66d172, because checkout/restore is outside the allowlist. Behaviour on b66d172 for these inputs: for `<root>\\missing\\..\\junction`, lstat raises FileNotFoundError, the function returns None, and read_json opens the path through the junction, which trips the normalized tripwire. For the denied registry, glob yields nothing and the command prints [] with exit 0. |
| python -m unittest discover -s agent_review -p "test_*.py" | no | pass | 346.5s | Local full run on the final tree before commit: 205 tests OK, 1 skipped (the live smoke, which needs AGENT_REVIEW_LIVE). |

_Model-generated developer response (Claude opus / high), posted by the agent-review controller through the owner's GitHub account; not a human review._
