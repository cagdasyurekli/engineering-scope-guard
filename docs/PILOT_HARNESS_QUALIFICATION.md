# Pilot Harness and Reserve Contract Qualification

**Completed:** 2026-08-28
**Pilot cells executed:** 0
**Policy comparisons executed:** 0

The previous Pilot Execution Readiness Decision remains a completed
**REDESIGN REQUIRED** decision. This goal made only its three requested bounded
corrections and did not reopen the task source, host decisions, arms, policy,
reviewer capacity, claims, cost observability, MCID, or quality margin.

## Qualified contract

`experiment/pilot_execution_contract.json` is the single frozen execution
manifest. It is regenerated from durable source receipts and audited byte for
byte. Before a cell launch, the harness rejects any mismatch in the scheduled
slot/task/arm/repetition, contract/pool/schedule digest, task snapshot identity,
subject configuration, evaluator, platform, intervention bytes, or isolation
roots. It also rejects state-root reuse across attempts.

The manifest records what isolation is controlled, what is observed per
attempt, and what remains unavailable. It does not claim provider-side cache
isolation or provider-billed cost.

## Pool and schedule commitment

The replacement-resolved pool contains 12 ordered slots, eight original tasks,
and four already-authorized pre-treatment task-slot replacements. It exposes
identifiers, repositories, languages, image-derived task-snapshot commitments,
and audit links—not task bodies or future confirmatory IDs.

- Final-pool SHA-256:
  `611693dc971177e76b5d7b45eb58f8dffd7c4821bf12b0dc6c540b6d580973fa`
- Schedule SHA-256:
  `ab92971b4309ecb6a7ccdd18c97358a2db4ba3342261c6831f8d6b0ace04aa2e`
- Schedule: 48 cells, baseline and C-short adjacent within each randomized
  task/repetition pair, using the recorded v1 seed.

The same pool, arm set, repetition count, contract version, and seed regenerate
the same schedule bytes. A changed slot changes the pool commitment and requires
a new contract and schedule.

## Two non-overlapping budgets

`task_slot_replacement_budget` changes which valid task occupies a slot before
treatment: 8 allowed, 4 consumed during completed host qualification, 4
unused when the final pool was locked, after which remaining authority is zero
inside this contract. Those four events retain original
task, invalidity reason, actual task, and reserve-rank commitment.

`trajectory_infrastructure_rerun_budget` changes only which attempt represents
the same task × arm × repetition cell: 8 total and at most one rerun per cell.
Only provider/API or local Docker/runtime infrastructure failures qualify. All
attempts remain in the hash-chained ledger. Agent failure, evaluator/test
failure, trajectory timeout, poor policy performance, and undesirable results
never qualify.

## Failure, correction, and ledger

The initial round is round 0. Only an initial evaluator/test failure returns one
round of failing-check-name-only feedback in the same trajectory-local session.
Round 1 is the only corrective round. Model and reasoning cannot change.

Accepted/completed, evaluator/test failure, agent/subject failure, and
trajectory timeout count as experimental outcomes. The two predefined
infrastructure categories invalidate an attempt and may consume same-cell rerun
budget. Harness, isolation/contract, and malformed/incomplete-measurement
failures stop the batch. These rules are frozen before outcomes.

The JSONL hash chain preserves schedule and slot events, every attempt,
infrastructure rerun authorization and remaining budget, evaluator result,
usage completeness, and deviations. Receipts contain identifiers and derived
metadata only, not private raw task/prompt/source content.

## Qualification evidence

Synthetic/no-op tests prove contract drift and contamination rejection,
cross-cell state separation, deterministic pool-bound schedule regeneration,
distinct budget consumption, outcome/rerun separation, incomplete-measurement
batch stopping, and failed-attempt ledger retention. No baseline-versus-C-short
Pilot task was run.

## Exact proposed Pilot goal — inactive

> Execute exactly the 48 scheduled Exploratory Pilot cells in the frozen
> `pilot-v1.0` manifest, enforcing preflight, isolation, corrective-round,
> timeout, failure/admissibility, usage, and append-only ledger rules; permit at
> most eight predefined same-cell infrastructure reruns and one rerun per cell;
> stop the batch on integrity failures; report only permitted exploratory
> deterministic feasibility and variance evidence; preserve zero-reviewer,
> provider-cost/cache, MCID, quality-margin, and broad-claims limitations; do not
> alter the pool, schedule, arms, policy, model, reasoning, or contract.

This proposal is for human review. It is not active and was not executed.

## Completion decision

**GO TO EXPLORATORY PILOT**
