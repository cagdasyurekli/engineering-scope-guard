# Exploratory Pilot Report

**Date:** 2026-08-28

**Status:** successor stopped with a durable partial attempt

## Outcome

The authorized successor Pilot began from fetched `main` commit
`104f82ce2e35ed04e1e0f8acecf648e045d2bb52`. The original contract,
successor authorization, predecessor lineage, pinned inputs, Docker resources,
Codex 0.150.1 interface, minimal credential bridge, and 48-cell dry-run all
passed strict live preflight.

The successor ledger was created separately and correctly bound the original
contract digest, successor authorization digest, predecessor terminal event
hash, and successor batch identity. It then started only original schedule cell
1, `slot-04-baseline-rep-1`, as trajectory attempt 2, consuming one of the
eight frozen infrastructure-rerun units and leaving seven globally.

The subject completed one turn and the official evaluator process ran. While
the runner was constructing the attempt receipt, it raised:

```text
TypeError: 'str' object is not callable
```

The successor ledger therefore contains `attempt_started` but no
`attempt_finished` or terminal batch event. The frozen successor state machine
reports `resolve_partial`, and the merged execute path says that state requires
a new explicit authorization decision. The partial attempt was preserved and
was not rerun, relabeled, completed manually, or discarded.

This was the first successor attempt to reach both a real subject invocation and
official evaluator execution. It did not become a valid experimental cell
because receipt construction failed afterward. The state remains recoverable
but undecided at `resolve_partial`; it was neither reset nor terminally
rewritten. No experimental retry was consumed beyond the already recorded
attempt 2, and no policy comparison exists.

No valid Pilot cell completed, no policy comparison exists, and no arm effect
can be estimated. This is harness/runtime evidence, not a baseline or policy
result.

## Exact counts

| Measure | Count |
| --- | ---: |
| Frozen scheduled cells | 48 |
| Successor cells started | 1 |
| Successor attempts finished | 0 |
| Valid completed cells | 0 |
| Unstarted cells | 47 |
| Experimental outcomes | 0 |
| Policy comparisons | 0 |
| Successor subject processes | 1 |
| Successor completed subject turns | 1 |
| Successor evaluator processes | 1 |
| Corrective rounds | 0 |
| Successor infrastructure-rerun units consumed at start | 1 |
| Globally remaining infrastructure-rerun units | 7 |
| Post-freeze task-slot replacements | 0 |
| Historical pre-treatment task-slot replacements | 4 |

The immutable predecessor remains at nine ledger events, one launched invalid
attempt, zero valid cells, zero evaluator outcomes, zero comparisons, and
`batch_stopped`. Its raw ledger SHA-256 remains
`0cf33d60006cc689b4664b309a94cbe8de1914e5dc2c86306cf603c44ca6a019`;
its terminal event hash remains
`f1868900f9aea206913fe594ceb53a3ffcab21fa72bf254afd3637ef2de73046`.

## Runtime defect

The earliest proven defect is a production adapter/core contract mismatch:

- `LiveBackend.prepare()` stores `ended_at` as an already-evaluated string.
- `_execute_prepared_attempt()` calls `prepared["ended_at"]()`.
- the fake backend used by the runner tests supplies a lambda, so the production
  mismatch was not exercised by qualification.

The prior runner qualification is therefore narrowed: it did not validate the
exact live runtime type of `ended_at` across the production adapter/core
boundary.

Credential cleanup still ran in `finally`; no `auth.json` remains in the
attempt state. The predecessor did not change.

The partial evidence also exposes a separate usage-integration gap. Codex
reported the four required provider components, but not `total_tokens`; the
frozen parser did not derive the contract's required total before
`_sum_usage()`. This did not cause the Python exception, but it would prevent
the partial attempt from becoming an admissible measurement.

## Partial attempt evidence

The invalid partial attempt recorded:

- schedule cell `slot-04-baseline-rep-1`, baseline arm, attempt 2;
- one `turn.completed` event and no provider-infrastructure event;
- observed input tokens: 916,296;
- observed cached-input tokens: 841,984;
- observed reasoning-output tokens: 1,884;
- observed output tokens: 4,948;
- a zero-byte prediction patch;
- one evaluator invocation;
- evaluator aggregate output marking one submitted empty patch;
- no task report, so no official resolved outcome was available.

These token values describe only the preserved invalid partial attempt. They are
not included in any arm distribution, mean, median, tail comparison, cost
estimate, or policy effect.

Provider-billed amount/currency, cache-write tokens, backend model snapshot, and
the frozen runner's derived total-token value remain unavailable. No monetary
value was imputed.

## Exploratory analysis

With zero valid cells, evaluator success by arm, token distributions by arm,
mean/median usage, dispersion, runaway behavior, within-task variance,
between-task variance, paired differences, arm discordance, task-by-arm
heterogeneity, correctness patterns, and structural comparisons are not
estimable. Reviewer capacity remains zero, so this run cannot support
maintainability, overall quality, equivalence, absence-of-harm, or downstream
maintenance claims.

## Methodological history

The evidence sequence remains visible:

1. original readiness qualification;
2. missing-runner blocked preflight;
3. runner enablement;
4. the first real predecessor batch stopped before a valid observation because
   of execution-integrity gaps;
5. authentication, provider classification, and pre-subject baseline repair;
6. confirmation that the immutable `batch_stopped` predecessor could not
   resume;
7. the post-freeze, pre-outcome successor authorization, which was not part of
   the original preregistration;
8. this successor execution, which stopped with a preserved partial attempt
   because of the production receipt-construction defect.

The sanitized machine-readable summary is
`experiment/exploratory_pilot_result.json`. The ignored local successor state
preserves the execute marker, attempt roots, raw trace, evaluator artifacts,
repository, and eight-event hash-chained ledger. No inconvenient evidence was
deleted or overwritten.

## Limitations

This evidence is specific to this frozen task distribution, Codex/model
configuration, runner/harness, and execution date. It supports no generic
savings claim, no quality-preservation claim, and no cross-agent
generalization. The successor Pilot did not reach a terminal experimental
outcome, so confirmatory design is not interpretable from these data.

## REDESIGN REQUIRED

The bounded blocker is the qualified runner's production contract and recovery
path, not an observed policy effect. Any repair and resolution of the durable
partial attempt require a separately authorized, pre-outcome integrity decision.
Do not patch this ledger manually, rerun cell 1, create another successor, start
Freeze, inspect confirmatory task bodies, or modify C-short under this goal.
