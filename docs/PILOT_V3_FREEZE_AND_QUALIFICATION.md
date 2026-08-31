# Pilot-v3 Freeze and Zero-Provider Qualification

## Decision

**PILOT-V3 FROZEN AND QUALIFIED — LIVE EXECUTION REQUIRES SEPARATE
AUTHORIZATION**

No Pilot-v3 subject, official experimental evaluator observation, schedule
cell, policy comparison, or confirmatory execution is authorized or performed
by this goal.

## Historical boundary

Pilot-v1 and Pilot-v2 are retained unchanged as historical/infrastructure
evidence only. Pilot-v2 remains permanently closed with its frozen
`batch_stopped` state, 8/44 admissible observations, positions 10-44 unstarted,
zero arm-effect analysis, and zero efficacy conclusion. Those observations and
task outcomes did not inform Pilot-v3 selection, effect assumptions, variance,
sample size, or treatment wording.

## Fresh pool and reserve

The frozen selection reconstructs the existing 499-task/207-repository
effective opaque reserve from the pinned dataset snapshot, then applies a new
SHA-256 rank using only the existing metadata projection. It selects one task
for each of the eight available languages, requires eight distinct
repositories, and excludes every task/repository represented in Pilot-v1,
Pilot-v2, their successor/continuation lineage, host-qualification
replacements, and the prior live canary.

The selected task IDs are public Pilot-v3 pool identities in
`experiment/pilot_v3_pool.json`. Task bodies were not read or scored for
selection. The pool is 8 tasks across 8 repositories. All eight repositories
are removed prospectively from the confirmatory reserve, removing 37 tasks and
leaving 462 tasks across 199 repositories. The artifact publishes only counts
and a domain-separated SHA-256 commitment; it emits no remaining reserve IDs or
bodies.

Post-freeze replacement allowance is zero. Any selected-task change creates a
new pool, schedule, contract identity, and experiment version.

## Arms, size, and schedule

Exactly two arms are frozen:

1. `baseline`: no intervention;
2. `short`: exact `C-short v0.1`, SHA-256
   `c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6`.

Each task receives both arms in two repetitions, producing 32 cells. The
schedule uses deterministic repetition blocks, SHA-256 task ranking, and
within-task arm counterbalancing. Repetitions are correlated measurements
within task, never independent task units. Eight tasks preserve all available
language coverage while remaining small; this is for feasibility, instability,
discordance, cost distribution, harness adequacy, and exploratory direction,
not statistical significance.

## Official evaluator and corrective rule

The prospective adapter accepts exactly one structurally consistent terminal
disposition: `success`, `failure`, `error`, `incomplete`, or `empty_patch`.
Disposition and `feedback_status` are separate.

- `failure` plus `available` feedback: provide only the recorded named checks
  and permit the single corrective round.
- `failure` plus `unavailable` feedback: retain a valid negative outcome,
  provide no invented check names, launch no correction, and terminate as
  evaluator/test failure.
- `empty_patch`: experimental negative outcome, no rerun.
- coherent `error` or `incomplete`: attempt-invalid evaluator/runtime
  infrastructure, eligible only for the frozen infrastructure rule.
- contradictory, multiple, or structurally inconsistent terminal identity:
  mandatory batch-stop measurement failure.

Synthetic fixtures cover all dispositions and the no-feedback failure shape.
The frozen Pilot-v2 position-9 classification is not rewritten.

## Attempts and operator pauses

Every cell has a hard maximum of two total attempts. The batch has four
provider/API or local Docker/runtime infrastructure-rerun units and two
separately counted operator-interruption units. A cell can consume at most one
restart of either category. Neither allowance can be increased after outcomes.

Two operator interruptions provide bounded resilience across 32 cells without
becoming experimental retry capacity. Planned pauses occur only between cells,
before the next `attempt_started`, and consume no allowance. A mid-attempt
interruption must record its external cause before outcome review; the attempt
remains immutable and visible. Any permitted restart uses the next attempt
number and completely fresh isolation. It is never relabeled as provider or
Docker failure, and no decision may depend on interim arm effects. Exhaustion
stops and preserves the batch.

Valid acceptance, evaluator failure, subject failure, timeout, and empty patch
are never rerun. Coherent provider/API, Docker/runtime, evaluator error, and
evaluator incomplete conditions may rerun only within both frozen limits.

## Isolation and durable evidence

Every cell/attempt receives a fresh repository/worktree, Codex home,
conversation/session, credential copy, raw output root, derived evidence root,
and evaluator-writable output root. Only the pinned evaluator checkout and
dataset snapshot are reusable immutable dependencies. Isolation identities are
recorded and reuse fails closed.

The runner fsyncs a JSONL SHA-256 hash chain at every fragile boundary. Durable
evidence includes attempt start, subject termination, evaluator invocation and
exit, official disposition, feedback availability, per-instance report
identity, timestamps, provider usage fields, isolation identities, termination,
credential cleanup, receipt, and admissibility. A restart reconstructs only
from those checkpoints. Completed cells are never repeated, and an in-memory
cursor has no authority.

## Usage and analysis

Provider-reported input, cached input, output, and reasoning-output tokens stay
separate. Fresh input is calculated only as input minus cached input and labeled
calculated. Provider billing is reported only if an actual amount and currency
are available; API list prices are never substituted.

Analysis remains exploratory and paired at task level. Repetitions remain
clustered within task; uncertainty resamples tasks. Acceptance/success is
reported separately from cost/work. Null and adverse outcomes remain included.
Timeouts and experimental failures follow the frozen intention-to-treat arm;
infrastructure-invalid attempts follow only frozen rerun rules. The Pilot
supports no per-language efficacy, equivalence, non-inferiority, universal MCID,
broad quality, or maintainability claim.

## Environment

The contract retains the qualified Pilot-v2 infrastructure identity:

- Codex CLI `0.150.1`;
- model `gpt-5.6-terra`, medium reasoning;
- automatic approval review with workspace-write sandbox and repository
  shell/edit tools only;
- Docker `29.7.2`, `linux/arm64` engine running official `linux/amd64` images,
  6 CPUs, 16 GiB memory, 2 GiB swap;
- dataset revision `62dc0745c40f067fc366ae3eb1a26136e5928f85`;
- evaluator revision `bc09878a5d192d0804dbd647dc6e650372fcb0ac`;
- RepoLaunch revision `c4b623d930f3728e5338664bb634021b98492cbf`;
- worker count 1;
- 900 seconds per turn, 1800 seconds per attempt, one corrective round.

The version/resource identities match the qualified Pilot-v2 infrastructure,
so no new live subject/evaluator canary is required by an environment change.
The fresh selected images must nevertheless pass zero-provider image and
repository-materialization qualification before the terminal decision.

## Qualification and execution boundary

The qualification regenerates pool, reserve commitment, schedule, and contract;
verifies digest stability; resolves every dry-run cell; tests evaluator shapes,
pause/retry transitions, durable restart/reconstruction, non-repetition,
credential cleanup, usage arithmetic, batch stops, and the digest-bound live
confirmation gate; and verifies every selected official image by copying its
repository to a fresh temporary root at the frozen base commit.

The confirmation token is necessary but never sufficient authority. Pilot-v3
live execution requires a separate explicit user request after the stabilized
contract is reviewed. Do not execute after merge under this goal.

## Qualification result

All deterministic checks passed. The pool, schedule, and contract regenerated
to their frozen digests; the exact policy bytes, pinned dataset, Codex,
Docker/resources, evaluator, RepoLaunch, worker, and execution-gate identities
matched. All eight official images were freshly materialized at their selected
base commits with initial tracked-state digests. Seven were clean. The
authoritative `GladysAssistant__Gladys-2504` image contained one tracked
baseline entry; that state is recorded and is safe only because the runner
captures the complete pre-subject baseline and attributes the evaluator patch
to subject changes relative to it.

The initial qualification implementation incorrectly required every official
image worktree to be clean, although the frozen contract requires fresh,
fingerprinted image state. That mechanical criterion was corrected without
changing the pool, schedule, contract, task identities, or execution authority.
A second representation-only mismatch normalized Docker's `aarch64` label to
the qualified `arm64` identity. The final pass reused the same-goal fresh
materialization receipts after revalidating all cached image IDs.

All official terminal-shape, no-feedback failure, retry/operator accounting,
planned-pause, restart/reconstruction, completed-cell non-repetition,
credential-cleanup, usage, hash-chain, batch-stop, and strict confirmation-gate
fixtures passed. Qualification invoked zero Pilot-v3 subjects, zero official
experimental evaluators, zero schedule cells, zero policy comparisons, and
zero confirmatory task bodies.
