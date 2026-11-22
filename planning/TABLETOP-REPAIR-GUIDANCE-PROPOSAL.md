# Proposed owner guidance: paused Tabletop repair (not applied)

Status: **proposal only.** This document was prepared with the resume-guidance change (PR #5). It has not been
captured, applied or tested against the Tabletop enrollment.

Before anyone uses it:

1. Refresh the Tabletop enrollment's status: `status --enrollment <id>`. It must be headless, `BLOCKED` or `PAUSED`
   in the `develop` phase, with nothing outstanding and budget remaining.
2. The enrollment must run a controller version that supports `--guidance`. That requires an owner-authorized
   `activate` between runs; activation can invalidate an earlier ready result.
3. Re-read its outstanding findings and adjust the text below to them.
4. If following this approach would change that feature's acceptance contract, it is not guidance. Use the
   amendment or re-enrollment procedure instead.

Guidance text is published, sanitized, in each later review request on the PR. It must stay PR-safe: no host
names, credentials, registry dumps or private paths.

---

```markdown
# Owner guidance: Tabletop repair approach

This guidance changes the repair approach only. The mission, its acceptance criteria, the current
authorized budget, models and permissions are unchanged.

1. Simplify the runner so that it fails closed. On any unexpected condition it stops and reports;
   it never continues with partial or assumed state.
2. Restore exactly the backup contents that were verified earlier, not a regenerated or newer copy.
3. Check the host immediately before the restore. Proceed only if the host is the expected one and
   is in the expected state.
4. Verify the restore by comparing each registry (key, value name, type, data) tuple exactly against
   the verified backup. Any difference is a failure, not a warning.
5. Keep the gameplay work that was already accepted. Do not rework it as part of this repair.
6. Preserve any uncommitted recovery work for inspection. Do not discard, reset or overwrite it;
   report where it is.
```
