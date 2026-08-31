# Exploratory Pilot v2 Minimal Requalification

**Status:** complete; failed closed before subject execution

## Outcome

The minimum durable-attempt implementation passed deterministic qualification,
but the single authorized live non-Pilot canary did not complete. The one-shot
`BYVoid__OpenCC-1096` command stopped at the dataset-bridge resolve boundary,
after live preflight and before canary state creation, credential copying,
subject invocation, or official evaluator invocation.

This is a new material execution-integrity defect: the path returned without a
durable canary failure record, so it cannot prove a complete terminal canary
state. The exact child error was not retained. A later read-only invocation of
the exact local dataset resolve succeeded, leaving the original cause
unavailable rather than disproving the observed failure.

The active goal forbids patching and rerunning a newly exposed live defect.
There was no second canary command, no repair, no Pilot-v2 pool derivation, and
no Pilot-v2 contract freeze.

## Pilot v1 remains historical evidence

Pilot v1 permanently remains an execution-system experiment that produced:

- zero valid experimental cells;
- zero policy comparisons;
- no evidence for or against baseline versus `C-short v0.1`.

Its predecessor ledger, successor ledger, frozen contract, and successor
authorization remained byte-identical. No attempt 3, v1 successor, receipt,
retry, relabeling, or ledger append was created.

## Deterministic durability qualification

The pre-canary candidate's minimal checkpoint layer wrapped the qualified
runner rather than rebuilding authentication, provider classification, baseline
extraction, timestamp/usage normalization, worker=1 evaluation, correction, or
evaluator logic. It atomically preserved monotonic evidence using a
same-directory temporary file, file `fsync`, replacement, and parent-directory
`fsync`.

The checkpoints retain or bind:

- attempt and subject-configuration identity;
- the authoritative pre-subject baseline;
- subject terminal state, trace reference/hash, and provider usage;
- prediction and patch references/hash;
- evaluator invocation identity;
- structured evaluator result, exit/timeout state, references, and hashes;
- start/end timing and termination;
- the normalized receipt before ledger commit.

Fault injection passed at all seven required boundaries:

1. after subject completion before patch persistence;
2. after patch persistence;
3. after evaluator launch;
4. after evaluator-result persistence;
5. immediately before receipt construction;
6. during receipt construction;
7. after receipt construction before ledger commit.

The tests reconstruct the same valid receipt from durable evaluator evidence
after downstream receipt failures. A crash after evaluator launch but before a
result remains the sole tested boundary requiring a predeclared infrastructure
rerun; it does not silently rerun or invent an evaluator result.

All 133 repository tests passed. The 22 focused v2/runner tests,
warning-clean compilation, JSON parsing, deterministic canary selection, and
`git diff --check` also passed before the one-shot command.

## One-shot canary evidence

The deterministic selector chose `BYVoid__OpenCC-1096` from Pilot-v1's
repository holdout. It is not a Pilot-v1 slot, Pilot-v2 task, or confirmatory
reserve task. Selection used only frozen metadata and exposed no task body.

The official image was pulled and identified before execution. The authorized
`run-canary` command was then invoked exactly once. It returned nonzero because
the dataset-bridge subprocess failed. The wrapper had not yet created
`.local/pilot-v2-canary`, provisioned an isolated credential copy, launched
Codex, or launched the official evaluator.

The missing durable failure receipt is itself material. Because no completed
canary exists, deterministic unit evidence cannot substitute for the required
real end-to-end proof.

## Activity and claims boundary

- one `run-canary` command invocation;
- zero complete live canaries;
- zero provider subject calls;
- zero official evaluator calls;
- zero Pilot-v2 subject/evaluator calls;
- zero policy comparisons;
- zero Pilot-v2 or confirmatory task exposures;
- zero credential copies created by the canary attempt;
- zero Pilot-v2 pool or schedule artifacts frozen.

This result is infrastructure evidence only. It is not policy, task-success,
cost, efficacy, maintainability, or quality-equivalence evidence.

The stabilization PR persists only the completed documentation, sanitized
receipts, and goal/decision records. It does not merge an executable live retry,
pool-derivation, schedule-freeze, or Pilot-v2 execution path.

The sanitized machine-readable record is
`experiment/pilot_v2_canary_qualification.json`.

## Decision

### `REDESIGN REQUIRED`

Do not repair or rerun the canary in this goal. Do not derive the Pilot-v2 pool,
freeze the Pilot-v2 execution contract, or execute a Pilot-v2 subject.
