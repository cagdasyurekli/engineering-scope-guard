# Canonical Closure Synchronization

## Goal

Synchronize the public repository's current handoff with the already terminal
operational state using one explicitly post-hoc, outcome-blind observation.

## Why now

PR #4 is merged, but the canonical handoff still describes its merge as the
next action. A later aggregate reserve checkpoint and a current read-only Azure
inventory observation can be recorded without reconstructing historical cause
or creating new experimental authority.

## Success criteria

1. Bind the live public `main` and merged PR #4 identity.
2. Add a public-safe receipt that separates source creation from post-hoc
   observation time and preserves every stated uncertainty.
3. Keep the evaluator experiment and Future Evaluator Reserve observation
   separate and leave all predecessor evidence unchanged.
4. Replace the completed `merge_if_green` handoff action with `none` and no new
   authorization.
5. Pass repository validation, required CI, and CodeQL; squash-merge the public
   PR and verify canonical `main`.

## In scope

- Public-safe post-hoc operational receipt and concise human-readable record.
- Goal history, decision log, and canonical handoff synchronization.
- Read-only GitHub, local aggregate receipt, and Azure inventory verification.
- Existing validation and authorized public PR/squash-merge workflow.

## Non-goals

- No experiment, subject, evaluator, successor, runner reuse, or Azure mutation.
- No reconstruction of the reserve campaign's historical terminal cause or
  cleanup time.
- No change to scientific decisions, predecessor receipts, ESG-RR-002, tags,
  Releases, product code, experiment code, or private archives.
- No task identities, bodies, outcomes, credentials, private paths, or traces.

## Evidence required

- Live GitHub `main` and PR #4 readback.
- SHA-256 commitment to the unchanged aggregate `first50-campaign.json` source.
- Timestamped, read-only aggregate Azure pools/jobs/node observation.
- Explicit `unverified` fields for unsupported historical or automation claims.
- Handoff/JSON/link/privacy/secret checks, warning-clean Python 3.11 and 3.14
  validation, full tests, required CI, and CodeQL.

## Model/reasoning plan

Use deterministic local tools and read-only provider inventories. Do not invoke
subject, evaluator, benchmark, or experimental model execution.

## Stop conditions

Stop on any source-hash mismatch, privacy exposure, non-clean isolated
worktree, validation failure, non-green required check, or need to infer an
unsupported claim. Do not start a next goal after merge.

## Status

**Complete — terminal on 2026-09-03.** The public-safe post-hoc observation is
recorded without changing predecessor evidence or asserting unverified cause.
No experiment, subject, evaluator, or successor program was started. There is
no next authorized action; any new program requires separate explicit user
authorization.
