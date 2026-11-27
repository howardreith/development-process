# Mission: exact comment transport (gh literal-escape rewriting)

Owner authorization: Mounted Combat owner instruction 2026-11-26f section 4 (bounded infrastructure task; at most two
independent read-only review executions). Starting material: local commit `ba6c062` on `codex/gh-transport-literal-escapes`
(preserved unchanged), carried onto this `claude/*` branch.

## Problem

`gh` 2.99.0 rewrites control-character escapes in the API responses it prints, before `--jq` and also with `@base64` or
`--allow-escape-sequences`. The six literal characters `\u0000` inside a stored comment body are printed as `\^@`, so the
controller's publication check (`publication_problems` -> part identity) reads an intact comment as altered. Observed on a
Mounted Combat review round: GitHub's stored body, the direct REST response and the paginated REST listing are identical
(21093 characters); gh's output has 21087.

## Requirements

1. `GitHub.comment` and `GitHub.comments` return the exact stored body strings, for the single lookup and the paginated
   listing, by reading the REST API directly (standard library) with the existing `gh auth token` credential.
2. Byte-exact alteration and deletion detection are kept: 404 on a single comment is the only "deleted" answer;
   authentication (401), rate limiting (403/429 with an exhausted limit or Retry-After), other HTTP statuses, a failure on
   any page, an undecodable response and network failures raise `CommandError`, never `None` or a partial listing.
3. The credential is sent only to the API origin (scheme, host, port): cross-origin pagination links and redirects are
   refused without sending it; no message or log carries it.
4. Behavior tests with a local HTTP server (simulated GitHub, clearly labeled) and a gh shim printing gh 2.99.0's
   caret-notation output: literal escapes, actual control characters, ordinary Unicode, pagination, missing versus
   authentication/rate-limit/other failures, origin scoping.
5. No caret-to-escape normalization, no loosened comparison, no edit of any existing GitHub comment, no
   acceptance-migration mechanism.

## Validation

Required gate `unit` (`python -m unittest discover -s agent_review -p "test_*.py" -v`).
