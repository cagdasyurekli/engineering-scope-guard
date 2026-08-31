# Pilot-v2 Operator-Interruption Continuation Qualification

## Scope and evidence boundary

This goal asked only whether the externally interrupted exploratory Pilot-v2
can retain scientific credibility through a minimal successor lineage. It did
not execute, evaluate, compare, or inspect any additional Pilot cell. It did not
inspect interim baseline-versus-C-short effects or expose confirmatory task
bodies.

The assessment validated the frozen `pilot-v2.0` contract, the sanitized
terminal result, and the original 15-event hash-chained ledger. The contract
remains file-identical at SHA-256
`4c1019f74becb059f0f1c8440d3fb676ff4595904e57cd79fd69770d6543d53c`.
The original ledger remains file-identical at SHA-256
`a998efd2c7e1783607c3494b3a38baca174e3760066f34125288f685012344b5`
and ends at event SHA-256
`d344cc5f725d4c7985e3208dadd10a6110ff38f3f599f4b7ad5155af4a51c83c`.

## Why continuation is scientifically defensible

The interruption cause was recorded contemporaneously as an external
user-requested operational pause. It was unrelated to arm performance,
evaluator outcome, token usage, task difficulty, or an interim comparison, and
no interim arm-effect analysis occurred. The missingness therefore has a
documented non-outcome operational cause. This permits a narrow exploratory
lineage amendment provided the incomplete attempt remains visible and the
decision cannot select, reorder, replace, or repeat observations based on
results.

This is not ordinary frozen-contract resumption. The original contract omitted
the operator-interruption transition, so its ledger cannot be appended or
reclassified. A separate authorization and ledger make the post-interruption
amendment visible rather than pretending it was prospective.

## Frozen lineage

- Cells 1-6 remain the original valid completed observations. They are included
  in the eventual `pilot-v2.0` exploratory evidence through the predecessor
  ledger and must not be copied or rerun.
- Cell 7 attempt 1 remains the incomplete `attempt_started` observation in the
  original ledger. The continuation starts at the same cell as trajectory
  attempt 2, using a fresh repository, Codex home, session, and output roots.
- Cells 8-44 retain their exact original cell IDs, task/arm/repetition
  identities, order, and attempt-1 starts.
- There is no new randomization, task selection, arm, treatment byte, model,
  reasoning setting, evaluator, timeout, corrective rule, or analysis rule.
- The continuation authorization has no execution entry point and explicitly
  records that execution is not authorized.

The tracked authorization is
`experiment/pilot_v2_continuation_authorization.json`. The separate ignored
ledger is initialized with one `operator_continuation_genesis` event at
`.local/pilot-v2-continuation/pilot-v2-continuation-ledger.jsonl`. Its genesis
binds the authorization, frozen contract, original ledger file digest, original
terminal event, continuation ID, schedule position 7, and attempt 2. It contains
no experimental observation.

## Attempt and budget accounting

Cell 7 may restart exactly once as attempt 2. The restart is not a provider,
Docker, evaluator, or task infrastructure failure and consumes zero of the
frozen eight-unit infrastructure-rerun allowance. Instead, the lineage records
one `operator_interruption_restart` unit, consumed at continuation genesis with
zero remaining.

This does not increase or reset the existing retry/rerun budget. The frozen
infrastructure allowance remains eight, with zero consumed. The trade-off is
strict: because the contract caps a cell at two total attempts, cell 7 cannot
receive a third attempt even if attempt 2 later encounters otherwise-rerunnable
infrastructure failure. Cells 8-44 retain the original infrastructure rules.

## Confirmatory predeclaration

Confirmatory work must not copy this post-interruption amendment after seeing
data. Before any confirmatory execution, its failure/missingness contract must
declare:

- planned pauses only between cells, before `attempt_started`;
- a separately counted, numerically fixed operator-interruption allowance;
- contemporaneous cause recording before any outcome review;
- immutable retention of an interrupted attempt and no infrastructure relabel;
- next-attempt numbering and fresh isolation for any permitted restart;
- a maximum of two total attempts per cell across all categories;
- stop-and-preserve behavior when the allowance is exhausted; and
- a prohibition on interim-effect review before a restart decision.

The confirmatory allowance value, design, tasks, and execution remain unfrozen
and unauthorized in this goal.

## Qualification evidence

Seven focused tests cover deterministic authorization, original-byte identity,
schedule/lineage binding, drift rejection, non-comparative terminal evidence,
single-creation ledger genesis, zero-call qualification, exact positions 8-44,
attempt accounting, and confirmatory predeclaration. The machine-readable
qualification records zero subject calls, evaluator calls, executed cells,
interim analyses, and confirmatory exposures.

## Decision

### `CONTINUATION QUALIFIED — EXECUTION REQUIRES SEPARATE AUTHORIZATION`
