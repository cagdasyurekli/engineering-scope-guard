# Pilot-v3 Successor Execution Interface Qualification

## Boundary

This goal added and qualified only the execution interface for the already
frozen `pilot-v3.0-successor-1` lineage. It made zero provider subject calls,
zero official live evaluator calls, executed zero successor cells, performed
zero arm comparisons, and exposed no confirmatory task body.

The original Pilot-v3 contract, pool, schedule, terminal result, and nine-event
predecessor ledger remained byte-identical. The separate successor ledger
remained its original one-event genesis.

## Qualified interface

`scripts/pilot_v3_successor.py` now provides:

- `execution-preflight`, which binds the exact contract, pool, schedule,
  terminal result, predecessor hash chain, adapter repair identity, successor
  authorization, successor genesis, Codex CLI, credential bridge, dataset
  snapshot, evaluator and RepoLaunch revisions, Docker resources, evaluator
  interface, all eight image IDs, and all eight dataset-bridge task identities;
- `execution-dry-run`, which resolves all 32 launch envelopes without writing
  attempt state or invoking a provider/evaluator; and
- a successor-authorization-digest-gated `execute` entry point whose every
  action is derived from the durable successor ledger.

The interface reuses the qualified Pilot-v3 launch request, live backend,
attempt executor, official evaluator adapter, cleanup path, receipt
reconstruction, and fsynced hash-chain writer. It adds no service, queue,
background process, dependency, or generalized orchestration layer.

## Attempts, restart, and accounting

The successor reducer enforces:

- position 1 attempt 1 remains only in immutable predecessor evidence;
- position 1 can launch only as attempt 2 and can never receive attempt 3;
- positions 2-32 retain their exact frozen identities and order and begin at
  attempt 1;
- a completed successor cell is never repeated after process restart;
- an unclassified partial attempt stops as `durable_evidence_incomplete`;
- a terminal checkpoint can be reconstructed only after durable credential-
  cleanup evidence;
- operator interruption requires a contemporaneous cause with
  `outcome_reviewed: false`; and
- the four infrastructure-rerun units and two operator-interruption units remain
  separate, bounded, and subject to the shared two-attempt maximum.

Wrong live confirmation fails before the execute marker or ledger mutation.
Fault injection at the evaluator boundary verified credential removal before
the terminal batch-stop checkpoint. A complete fixture execution reconstructed
all 32 schedule positions and reached terminal completion without repetition.

## Zero-live evidence

The complete dry-run resolved position 1 at attempt 2 and positions 2-32 at
attempt 1, with unique fresh isolation roots and zero calls or cells. The real
strict preflight passed against Codex `0.150.1`, the frozen model/reasoning
envelope, the isolated `auth.json` bridge, the eight pinned Parquet hashes,
evaluator `bc09878a5d192d0804dbd647dc6e650372fcb0ac`, RepoLaunch
`c4b623d930f3728e5338664bb634021b98492cbf`, Docker `29.7.2` and its frozen
resource envelope, all eight qualified image IDs, and all eight bridge-resolved
problem-statement digests.

Machine-readable evidence:

- `experiment/pilot_v3_successor_execution_preflight.json`
- `experiment/pilot_v3_successor_execution_dry_run.json`
- `experiment/pilot_v3_successor_execution_qualification.json`

The focused 43-test successor/adapter/runner set passed before terminalization.
Repository-wide checks and GitHub CI/CodeQL are recorded by the terminal goal
and canonical handoff.

## Decision

### `PILOT-V3 SUCCESSOR EXECUTION INTERFACE QUALIFIED — LIVE EXECUTION REQUIRES SEPARATE AUTHORIZATION`

The qualification itself creates no execution authority. The user's current
standing authorization permits Phase 2 only after this goal is merged and the
merged `main` bytes pass parity and strict-preflight readback.
