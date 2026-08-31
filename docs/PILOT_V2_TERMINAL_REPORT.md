# Pilot-v2 External-Interruption Terminal Report

**Status:** execution stopped; preserved incomplete attempt; protocol-completeness
decision required separately

## Technical summary

The authorized `pilot-v2.0` execution stopped after an external,
user-requested operational interruption while schedule cell 7 was active. The
interruption was unrelated to any experimental result: the user needed to leave
and intended to continue later. It was not prompted by baseline or C-short
performance, evaluator outcomes, token usage, task difficulty, or an interim
comparison.

The frozen contract does not define operator interruption as a resumable
infrastructure class. The preserved ledger therefore remains exactly as
observed: six admissible completed cells followed by cell 7
`attempt_started`, with no fabricated `attempt_finished`, infrastructure-rerun
authorization, or `batch_stopped` event. Cell 7 was not rerun and cells 8-44
were not executed.

This is a protocol-completeness result, not a policy result. No arm-efficacy,
token, task-difficulty, or interim baseline-versus-C-short analysis was
performed.

## The durable state stops before a resumable classification

The local append-only ledger remains 15 events and SHA-256
`a998efd2c7e1783607c3494b3a38baca174e3760066f34125288f685012344b5`.
Its final event is cell 7 `attempt_started`, event SHA-256
`d344cc5f725d4c7985e3208dadd10a6110ff38f3f599f4b7ad5155af4a51c83c`.
No terminal event was appended because the user explicitly required the
observed ledger to remain unchanged.

| Preserved state | Count |
| --- | ---: |
| Frozen scheduled cells | 44 |
| Cells started | 7 |
| Admissible completed cells | 6 |
| Incomplete `attempt_started` cells | 1 |
| Unstarted cells | 37 |
| Infrastructure reruns authorized or consumed | 0 |
| Post-freeze task replacements | 0 |
| Interim arm-effect analyses or comparisons | 0 |

The six completed cells retain their original receipts, complete provider-usage
fields, evaluator evidence, termination classes, and admissibility. Across
those receipts there are four `accepted_completed` and two
`evaluator_test_failure` outcomes. These counts are reported only to preserve
terminal evidence; they were not grouped, contrasted, or interpreted by arm.

## Cell 7 remains an incomplete external interruption

Cell `v2-slot-05-baseline-rep-1` started trajectory attempt 1. Its initial
subject turn completed and the official evaluator process was active when the
user requested an operational pause. The runner was interrupted, the orphaned
evaluator process and exact Docker container were stopped, and the isolated
credential copy was removed. No evaluator result or valid receipt was created.

The frozen state machine now reports `resolve_partial`. Its available classes
cover provider infrastructure, local Docker/runtime infrastructure, or
batch-stop integrity failures. The observed cause was none of those: it was an
external operator interruption. Reclassifying it as provider or Docker
infrastructure would fabricate a same-cell rerun entitlement. Appending a
different terminal classification would alter the observed ledger, which the
current authorization forbids.

The batch is therefore operationally stopped while its immutable internal
state remains an unresolved partial attempt. This distinction is deliberate
and is not described as a normally completed or resumable batch.

## No policy analysis is admissible from this goal

The schedule stopped after six of 44 cells and before the frozen repetitions
were complete. More importantly, the user explicitly prohibited inspecting or
comparing interim arm effects. No estimate, direction, variance, acceptance
difference, token comparison, cost comparison, heterogeneity assessment, or
policy claim was produced.

The only supported conclusion is methodological: `pilot-v2.0` omitted a
prospective transition for an external operator interruption after
`attempt_started`. The run says nothing about whether baseline or C-short is
better, cheaper, safer, or more effective.

## Preserved boundaries and limitations

- The frozen contract, pool, schedule, arms, model, reasoning, evaluator,
  timeout, corrective-round, and rerun budgets were not changed.
- Valid cells 1-6 and the incomplete cell 7 evidence remain in the ignored
  local state root; the ledger was not edited, reset, or relabeled.
- No confirmatory task body was exposed and no confirmatory or Freeze work
  began.
- Provider-billed amount, currency, cache-write tokens, and backend model
  snapshot remain unavailable and were not inferred.
- The user-supplied reason for interruption is contemporaneous operational
  context, not evidence supporting a continuation or rerun.
- No chart is included because arm comparison is prohibited and the exact
  terminal audit table is the least misleading representation.

## Next decision requires separate authorization

The next bounded action is not execution. A separately authorized methodology
decision must determine whether an operator-interruption successor or
continuation can be scientifically admissible while preserving the original
ledger, exposure history, schedule identities, and rerun accounting.

That future decision must not infer authority from this report. This goal did
not create or execute a successor, add a continuation rule, rerun cell 7, or
start cells 8-44.

## Decision

### `PILOT-V2 EXECUTION STOPPED — EXTERNAL INTERRUPTION REQUIRES A SEPARATE PROTOCOL-COMPLETENESS DECISION`
