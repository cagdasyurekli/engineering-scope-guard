# Pilot-v2 Continuation Terminal Report

## Outcome

The exact qualified strict preflight passed before the first live continuation
cell. The frozen runner resumed position 7 as attempt 2, completed positions 7
and 8 with admissible `evaluator_test_failure` receipts, then stopped the batch
at position 9 attempt 1 with `malformed_incomplete_measurement`.

The position-9 official evaluator returned unresolved with no failing checks.
The frozen runner therefore applied its predeclared malformed-measurement class
and durably wrote `batch_stopped`. No manual classification, repair, rerun, or
later-cell launch occurred.

## Preserved lineage and accounting

- Predecessor positions 1-6 and their ledger remain byte-identical.
- Position 7 attempt 1 remains immutable and incomplete in the predecessor
  ledger; attempt 2 is the only continuation attempt and no attempt 3 exists.
- Position 8 ran once as its original attempt-1 identity.
- Position 9 ran once as its original attempt-1 identity and triggered the
  frozen batch stop.
- Positions 10-44 remain unstarted.
- Zero infrastructure rerun units were consumed; the separate allowance remains
  0/8 consumed.
- The contract, authorization, schedule, arms, model/reasoning, evaluator,
  timeouts, corrective protocol, and analysis rules were not changed.

## Observations and usage

The continuation has three finished attempts: two admissible evaluator-test
failures and one inadmissible malformed measurement. Together with the six
predecessor observations, 8 of 44 frozen schedule cells are admissible.

Provider-reported usage across the three finished continuation attempts is
2,008,106 input tokens, including 1,791,232 cached input tokens; calculated
fresh input is 216,874 tokens. Output is 16,971 tokens, reasoning output is
3,650 tokens, and total usage is 2,025,077 tokens. Provider billed amount and
currency are unavailable, so no billed-cost claim is made.

## Analysis admissibility

No exploratory arm-effect analysis is admissible from this terminal state. The
frozen schedule is incomplete, a mandatory batch-stop failure occurred, and
only eight cells are admissible overall. No baseline-versus-C-short comparison,
interim effect inspection, confirmatory inference, general efficacy claim, or
task-body exposure was performed.

## Decision

**PILOT-V2 CONTINUATION STOPPED — MALFORMED INCOMPLETE MEASUREMENT;
EXPLORATORY ANALYSIS INADMISSIBLE.**
