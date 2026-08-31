# Pilot-v3 Terminal Execution Report

**Status:** batch stopped at the first cell; zero admissible observations; no
Pilot-v3 effect analysis

## Outcome

The exact frozen Pilot-v3 preflight passed before the first live cell. The
digest-bound runner then started schedule position 1, completed one subject
process, recorded the evaluator invocation boundary, removed the isolated
credential, and exited before the official evaluator process launched because
the reused live adapter requested a trajectory-contract key that Pilot-v3 does
not contain.

Durable restart derived the next action only from the hash-chained ledger and
appended the frozen `durable_evidence_incomplete` batch stop. No second attempt,
infrastructure rerun, operator restart, task replacement, or later cell was
launched. The batch has zero admissible Pilot-v3 observations and supports no
baseline-versus-C-short comparison.

## Exact durable state

| Preserved state | Count |
| --- | ---: |
| Frozen scheduled cells | 32 |
| Cells started | 1 |
| Subject processes completed | 1 |
| Evaluator invocation boundaries recorded | 1 |
| Official evaluator processes started | 0 |
| Evaluator terminal checkpoints | 0 |
| Receipts committed | 0 |
| Admissible completed cells | 0 |
| Invalid partial attempts | 1 |
| Unstarted cells | 31 |
| Infrastructure reruns consumed / frozen | 0 / 4 |
| Operator interruptions consumed / frozen | 0 / 2 |
| Post-freeze task replacements | 0 |
| Interim arm comparisons | 0 |

The ignored local ledger remains nine events with SHA-256
`e0a03c6b7ddb6f33ee4d79473dea4536383c750b1b580a23e9c9d5de7b316ea0`.
Its final `batch_stopped` event has SHA-256
`5193864cf4acf0fbdc4e08778fafa22ded459e26839823967a64f1a2c1e01997`.
Terminal reporting did not edit, reset, or relabel that ledger.

## Failure boundary

Pilot-v3 freezes the attempt timeout under
`trajectory.timeout_seconds_per_attempt`. The reused live evaluator adapter
reads `trajectory_contract["timeout_seconds_per_trajectory_attempt"]` before
calling the official evaluator process. The resulting `KeyError` occurred
after the runner had durably recorded `evaluator_invoked`, but before the
evaluator subprocess started or produced an official disposition.

This distinction matters:

- the subject process completed with exit code 0, a valid session identity,
  no timeout, and no provider-infrastructure classification;
- provider-reported usage for that invalid partial attempt was 158,476 input,
  129,280 cached input, 1,846 output, and 344 reasoning-output tokens;
- the official evaluator produced no `success`, `failure`, `error`,
  `incomplete`, or `empty_patch` disposition;
- no failing check names or corrective feedback existed, so none was inferred
  or synthesized;
- the isolated credential copy was removed before the process exited.

The state therefore cannot be converted into an evaluator failure, provider
failure, Docker/runtime failure, timeout, empty patch, or valid negative
outcome. It is exactly the frozen scheduler's incomplete-durable-evidence batch
stop.

## Retry and interruption accounting

No frozen allowance was consumed. The first cell remains at attempt 1 with no
receipt. It was not rerun as attempt 2, and no third attempt exists. All four
infrastructure-rerun units and both operator-interruption units remain unused;
their availability does not authorize continuation after this batch stop.

The second runner invocation did not launch a subject or evaluator. It only
reconstructed the next scheduler action from durable evidence and appended the
prescribed terminal event.

## Analysis and claims boundary

The frozen exploratory analysis is not performed because there are zero
admissible cells, zero completed task-level pairs, and no official evaluator
outcome. Acceptance/success and cost/work effects therefore cannot be
estimated separately or jointly. No effect size, uncertainty interval,
direction, null/adverse comparison, task-level cluster bootstrap, per-language
estimate, equivalence, non-inferiority, quality, or maintainability claim is
reported.

This is harness-compatibility and durability evidence only. It says nothing
about whether baseline or exact `C-short v0.1` is more effective or efficient.
Provider billing amount and currency were unavailable and are not inferred
from token counts.

## Preserved boundaries

- Pool, task identities, task bodies, schedule, arm assignments, repetitions,
  treatment bytes, model, reasoning, evaluator, timeouts, corrective rules,
  retry/interruption budgets, analysis rules, and confirmatory reserve were not
  changed.
- The live harness was not repaired or redesigned after the failure.
- No post-freeze replacement, successor lineage, confirmatory task exposure,
  or confirmatory execution occurred.
- Raw provider output, task material, credentials, and temporary evaluator
  artifacts remain outside repository evidence.

## Decision

### `PILOT-V3 EXECUTION STOPPED — DURABLE EVALUATOR EVIDENCE INCOMPLETE`

The next action is stabilization of this terminal evidence only. Any harness
repair, Pilot-v3 successor/continuation, confirmatory execution, or new
experimental goal requires separate authorization.
