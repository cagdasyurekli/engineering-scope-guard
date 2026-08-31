# Pilot-v2 Measurement-Boundary Triage and Closure

## Decision

**MEASUREMENT BOUNDARY QUALIFIED — FRESH PILOT DESIGN PERMITTED**

This permits only prospective design work under separate authority. It does
not authorize a fresh Pilot design, task-pool freeze, provider call, evaluator
run, or experimental execution.

## Triage result

The supported explanation is **adapter/parser defect**.

The pinned official evaluator emitted a unique task-failure disposition:

- process exit status 0;
- `resolved: false` in the per-instance report;
- the exact instance in `failure_ids`;
- zero `error_ids` and zero `incomplete_ids`.

The report contained no named failing checks. That is a legitimate official
terminal shape: the evaluator decides resolution against the full expected
check sets, while its report's `failure` arrays contain only checks explicitly
observed as failing. For position 9, the pinned dataset expected 373
fail-to-pass checks and one pass-to-pass check. The report observed the one
pass-to-pass success but none of the 373 expected fail-to-pass checks, so it
could return `resolved: false` without placing a name in either failure array.

The adapter loaded `results.json` but used only its error/incomplete counts. It
discarded the authoritative `failure_ids` disposition. The frozen runner then
conflated two different facts:

1. the official measurement was a task failure; and
2. no named check was available for the optional corrective prompt.

That conflation caused the predeclared
`malformed_incomplete_measurement` batch stop. It was the correct frozen action
and is not changed retrospectively.

## Alternatives assessed

### Valid evaluator semantic only

Partly true but not the root boundary defect. A negative result without named
feedback is valid official behavior. The stop occurred because the adapter and
trajectory boundary did not preserve the difference between official outcome
and feedback availability.

### Evaluator/benchmark incomplete measurement

Not supported for the terminal disposition. The structured output uniquely
recorded failure, not error or incomplete, and the same pinned task/evaluator
path had three successful official gold qualification runs. Preserved stdout
also records that the submitted patch did not apply cleanly after the official
test patch, which is consistent with a negative outcome. That unstructured log
is retained as supporting diagnostic evidence, not substituted for the
official structured disposition.

### Another measurement-boundary defect

No additional defect is needed to explain the observed state.

## Prospective fix

The official-result adapter now validates and preserves one unique terminal
disposition from `results.json`:

- `success`;
- `failure`;
- `error`;
- `incomplete`;
- `empty_patch`.

It separately records whether named corrective feedback is `available`,
`unavailable`, or `not_applicable`. Contradictory identities, counts, reports,
or multiple terminal memberships fail closed as malformed.

Synthetic fixtures cover every official terminal shape, including the
position-9 shape (`failure`, `resolved: false`, no named checks). A regression
also proves that the frozen Pilot runner still classifies that shape as
`malformed_incomplete_measurement`; the new fields are prospective evidence,
not a retroactive semantic change.

A fresh Pilot contract must predeclare what happens when the official
disposition is failure but corrective feedback is unavailable. The safe
default is to retain the official negative outcome and end the trajectory
without inventing feedback. That rule belongs in a fresh design and is not
frozen here.

## Benchmark/evaluator suitability

The current SWE-bench-Live / official evaluator stack remains suitable for a
future exploratory Pilot only behind the qualified adapter boundary and a
fresh predeclared trajectory contract. This assessment is based on structured
terminal semantics, consistency checks, and prior gold qualification—not on
baseline-versus-C-short outcomes.

Replacement or redesign of the benchmark is not required by the position-9
evidence. A future design must nevertheless fail closed on contradictory,
error, or incomplete terminal shapes and must never infer a pass or failure
from missing artifacts alone.

## Frozen evidence and reproduction boundary

The investigation used only preserved position-9 artifacts, the pinned
evaluator source and dataset metadata, existing gold-qualification records,
and deterministic local parser fixtures. It invoked zero subjects, zero new
Pilot cells, and zero evaluator runs. The local position-9 parser reproduction
is debugging evidence only; it is not a new experimental observation.

The machine-readable evidence record is
`experiment/pilot_v2_measurement_boundary_qualification.json`. It records the
frozen artifact digests and sanitized position-9 evidence digests without
publishing raw local evidence or task bodies.

## Permanent Pilot-v2 closure

Pilot-v2 is permanently closed:

- all predecessor and continuation ledgers, receipts, and terminal
  classifications remain unchanged;
- position 9 remains `malformed_incomplete_measurement`;
- the terminal state remains `batch_stopped`;
- 8/44 observations retain their existing admissibility labels;
- positions 10-44 remain unstarted;
- no exploratory arm-effect estimate was produced;
- no efficacy conclusion is supported;
- no successor, continuation, restart, or recovery path may be created.

Existing observations are retained only as historical and infrastructure
evidence under their current labels. Negative and adverse evidence is neither
discarded nor rewritten.
