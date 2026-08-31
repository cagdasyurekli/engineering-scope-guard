# Pilot-v2 Continuation Execution Interface Qualification

## Boundary

This goal added and qualified only the execution interface for the already
frozen operator-interruption continuation. It did not invoke a Codex/provider
subject, invoke the official evaluator for a Pilot cell, execute any position
7-44 cell, inspect an interim arm effect, expose the confirmatory reserve, or
create another lineage.

The original Pilot-v2 contract remains byte-identical at SHA-256
`4c1019f74becb059f0f1c8440d3fb676ff4595904e57cd79fd69770d6543d53c`.
The predecessor ledger remains byte-identical at SHA-256
`a998efd2c7e1783607c3494b3a38baca174e3760066f34125288f685012344b5`.
The continuation ledger remains its original one-event genesis at SHA-256
`182ce981af6b8044bcd92ba7fc199d245f0dcae3ae5260dfbac5b2975922cc69`.

## Minimal interface

`scripts/pilot_v2_continuation.py` now exposes continuation-specific
`execution-preflight`, `execution-dry-run`, and confirmation-gated `execute`
commands. The entry point reuses the qualified runner's immutable launch
envelope, receipt validation, failure taxonomy, attempt executor, credential
bridge/cleanup, evaluator adapter, and durable ledger writer. It does not add a
new scheduler, backend, service, queue, or generalized orchestration layer.

Before a future launch, the interface rebuilds and validates the frozen
authorization, exact contract, terminal result, predecessor hash chain and
terminal event, continuation genesis, schedule suffix, task identities,
attempt numbering, and accounting. A mismatched dependency fails closed.
Separate live authority must be expressed by the exact continuation-bound
confirmation token; the interface rejects a missing or wrong token before any
execution marker or ledger write.

## Durable state and attempts

The continuation state reducer reads the hash-chained ledger for every action.
It has no in-memory cursor:

- positions 1-6 are absent from its executable schedule view and remain
  satisfied only through predecessor evidence;
- position 7 is the original `v2-slot-05-baseline-rep-1` at trajectory attempt
  2 and consumes no infrastructure-rerun unit;
- an infrastructure-class result at position 7 attempt 2 stops rather than
  authorizing attempt 3;
- positions 8-44 retain their exact cell/task/arm/repetition/order identities
  and begin at attempt 1;
- valid completed continuation cells are skipped when state is reconstructed
  after a process restart; and
- attempt starts, receipts, rerun authorizations, and terminal stops are
  fsynced to the ledger before the loop derives another action or returns a
  final aggregate.

The operator restart unit remains consumed with zero remaining. The original
infrastructure allowance remains eight with zero consumed at continuation
genesis. The categories are never merged or reset.

## Isolation and cleanup

Each planned attempt retains fresh repository, Codex-home, session,
trajectory-local credential copy, raw/derived output, and evaluator-output
paths. The evaluator source checkout remains the pinned immutable qualified
runtime; its writable round outputs are rooted under the fresh attempt-specific
raw directory. Fault injection at the subject boundary confirmed that the
trajectory credential is removed in `finally`, the harness-failure receipt is
durably recorded, and the batch-stop checkpoint precedes the returned result.

## Qualification evidence

The strict zero-provider preflight passed against:

- authorization, contract, terminal-result, predecessor-ledger, and genesis
  digests;
- Codex CLI 0.150.1 and its required command surface;
- the frozen Docker architecture/resources and all 11 qualified image IDs;
- pinned dataset file hashes, evaluator revision, RepoLaunch revision, and
  evaluator I/O interface; and
- restrictive file-backed credential permissions with no stale
  trajectory-local credential.

The complete dry-run resolved exactly positions 7-44: one position-7 attempt 2
and 37 attempt-1 starts. It wrote no state and recorded zero subject calls,
evaluator calls, executed cells, policy comparisons, interim analyses, or
confirmatory exposures.

Sixteen focused tests cover strict preflight, schedule and task drift,
authorization and ledger corruption, predecessor exclusion, attempt-3
rejection, exhausted operator accounting, separate infrastructure accounting,
durable restart, non-repetition, stop/failure transitions, wrong confirmation,
credential cleanup, and checkpoint ordering. The full 171-test repository
suite and warning-clean compilation pass on the final bytes.

Machine-readable evidence:

- `experiment/pilot_v2_continuation_execution_preflight.json`
- `experiment/pilot_v2_continuation_execution_dry_run.json`
- `experiment/pilot_v2_continuation_execution_qualification.json`

## Decision

### `CONTINUATION EXECUTION INTERFACE QUALIFIED — LIVE EXECUTION REQUIRES SEPARATE AUTHORIZATION`

The interface is ready for a separately authorized future live continuation.
This decision does not authorize that execution, and no live continuation may
begin after stabilization under this goal.
