# Pilot Successor-Batch Authorization

**Status:** qualified; successor execution was not invoked

## Decision

**SUCCESSOR-BATCH QUALIFIED — GO TO EXECUTE SUCCESSOR PILOT**

This decision authorizes only a later, explicit execution of successor batch
`pilot-v1.0-successor-1`. It does not execute that batch, resume the predecessor,
or provide policy, task-success, cost, or quality evidence.

## Why a successor is defensible

The terminal predecessor launched only original schedule cell 1. Authentication
failed before a successful subject turn, provider usage, evaluator invocation,
valid experimental observation, or policy comparison. The preserved ledger
contains one invalid attempt and then `batch_stopped`; all other 47 cells were
unstarted.

The original protocol omitted a transition from a terminal stopped batch. That
omission is now recorded explicitly as a **post-freeze pre-outcome infrastructure
protocol amendment**. The predecessor is not reopened or cosmetically repaired.
Future confirmatory protocols must define terminal-batch restart semantics before
execution begins.

## Immutable lineage

The tracked authorization at
`experiment/pilot_successor_batch_authorization.json` binds:

- frozen contract `1ec191306215936c4f17bd0805d0a4619e0530a4d79c91c0240212b26226ead0`;
- original schedule `ab92971b4309ecb6a7ccdd18c97358a2db4ba3342261c6831f8d6b0ace04aa2e`;
- final task pool `611693dc971177e76b5d7b45eb58f8dffd7c4821bf12b0dc6c540b6d580973fa`;
- baseline and C-short v0.1 identities;
- exact subject and official evaluator configurations;
- predecessor batch `pilot-v1.0-predecessor-1`, its terminal event hash, frozen
  recorded failure taxonomy, and zero-outcome/evaluator/comparison counts;
- successor batch `pilot-v1.0-successor-1`, original schedule position 1, and
  original cell `slot-04-baseline-rep-1`;
- the qualified underlying provider-auth infrastructure cause and carried
  trajectory-rerun accounting.

The authorization digest is
`c81664e2a245d80657fa30112383aee34bd919424a9950ce4c7ba0e9ff450889`.
The original frozen contract file remains byte-identical at SHA-256
`91bca22dde1d157a3d298c25fcda90ceba8c95b56a9a5e3b48e8e21402112f41`.

## Frozen rerun accounting

The predecessor attempt itself was attempt 1, not a rerun. Its ledger retains
the original `malformed_incomplete_measurement` classification. The later
integrity qualification established that the actual pre-subject failure was an
HTTP 401 provider-authentication failure, which falls within the already-frozen
`provider_api_infrastructure_failure` rerun class.

Accordingly, successor cell 1 is trajectory attempt 2 and consumes exactly one
of the existing eight infrastructure-rerun units. Seven remain. Cells 2-48 are
first attempts. No retry capacity was added or reset. If successor cell 1 has
another infrastructure-invalid attempt, its per-cell maximum is exhausted and
the runner stops the batch.

## Separate successor ledger

The successor path refuses to start when its state directory or ledger already
exists unexpectedly. On a separately authorized future execute, it creates a
new hash chain whose genesis binds exactly:

- successor authorization digest;
- original frozen contract digest;
- predecessor terminal event hash;
- successor batch ID.

The predecessor's observations are not copied into the successor chain. The
successor state machine receives only the digest-bound initial accounting:
schedule position 1, trajectory attempt 2, one rerun unit consumed, and cell 1
already holding its sole rerun. The predecessor ledger remains a separate,
terminal chain.

## Fail-closed runner behavior

The successor runner rejects contract, authorization, predecessor-chain,
terminal-state, count, schedule, policy, subject/evaluator identity, start-cell,
rerun-budget, duplicate-state, and successor-genesis mismatches. The live
command requires a separate confirmation token bound to the authorization
digest. Partial successor attempts do not receive an inferred classification;
they require another explicit decision.

The runner continues to use the qualified minimal credential bridge, bounded
provider-error parser, pre-subject Git baseline, baseline-relative patch,
official evaluator, same-session corrective round, process-group timeout, and
the unchanged frozen contract.

## Qualification evidence

The strict preflight rechecked the tracked contract, Codex 0.150.1 interface,
pinned dataset and evaluator/RepoLaunch revisions, Docker resources, all 12
official image identities, evaluator interface, credential mode, and empty
successor state. No authenticated canary was repeated because successor work did
not change authentication or provider-facing runner bytes; the completed
execution-integrity qualification was reused.

The deterministic successor dry-run resolved the exact 48-cell schedule:

- cell 1: infrastructure rerun, trajectory attempt 2;
- cells 2-48: first attempts, trajectory attempt 1;
- Codex/Pilot subject calls: 0;
- evaluator calls: 0;
- experimental observations written: 0;
- successor ledger writes: 0.

Before and after qualification, the terminal predecessor remained nine events,
file SHA-256
`0cf33d60006cc689b4664b309a94cbe8de1914e5dc2c86306cf603c44ca6a019`,
and final event SHA-256
`f1868900f9aea206913fe594ceb53a3ffcab21fa72bf254afd3637ef2de73046`.
The machine-readable evidence is
`experiment/pilot_successor_batch_qualification.json`.

## Evidence sequence

1. The runner qualified under preflight and dry-run.
2. First real execution exposed authentication, baseline, and provider-error
   schema gaps before any valid outcome.
3. Those gaps were repaired and qualified without changing experimental bytes.
4. Repair could not resume because `batch_stopped` is correctly terminal.
5. The successor-batch amendment was therefore designed and qualified before
   any valid policy outcome existed.

No successor `execute` command, Pilot subject, evaluator, policy comparison, or
confirmatory-task inspection occurred in this goal.
