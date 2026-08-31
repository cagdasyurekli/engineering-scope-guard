# Pilot-v3 Successor Terminal Report

**Date:** 2026-08-29

**Status:** terminal partial schedule; exploratory analysis supported

## Outcome

The authorized Pilot-v3 successor executed the exact frozen lineage through
schedule position 32. It started 33 attempts: position 1 only as attempt 2,
positions 2-31 once each, and position 32 twice under the single frozen
infrastructure rerun. The first 31 positions produced admissible experimental
outcomes. Both position-32 attempts produced complete, coherent
`local_docker_runtime_infrastructure_failure` receipts, so the reducer appended
the mandatory `attempt_limit_exhausted` batch stop. Position 32 remains missing;
attempt 3 is forbidden.

This is a valid frozen stop, not a harness-integrity defect. The receipts,
credential cleanup, hash chain, and retry accounting are complete. A Pilot-v4
repair or fallback is therefore neither necessary nor authorized by the
standing repair criteria.

## Execution accounting

| Measure | Count |
| --- | ---: |
| Frozen cells | 32 |
| Attempts started | 33 |
| Admissible cells | 31 |
| Accepted outcomes | 10 |
| Evaluator/test failures | 21 |
| Infrastructure-invalid attempts | 2 |
| Missing cells | 1 |
| Complete two-repetition task clusters | 7 |
| Infrastructure reruns consumed / allowed | 1 / 4 |
| Operator interruptions consumed / allowed | 0 / 2 |
| Successor ledger events | 288 |

The successor ledger SHA-256 is
`1b4156c8b3e6c20dbc590bd1e892df5e874c0b7207788dd75d09e97cdbbe1225`;
its terminal event is
`73e1530ed99235ca2e7af5787c8850d24261cbecf22de433022bec84c97f7f90`.
The predecessor ledger and every frozen contract, pool, schedule, terminal, and
successor-authorization artifact remain unchanged.

## Analysis population and method

Infrastructure-invalid attempts are excluded under the frozen taxonomy.
Experimental failures remain assigned to their arms. Because the two
repetitions are correlated within task, the paired analysis uses the seven
tasks with both repetitions complete in both arms (28 cells). The incomplete
slot 2 is excluded from paired estimands; its three admissible cells remain in
the 31-cell marginal summaries. There was no imputation.

Uncertainty uses an exact nonparametric task bootstrap: seven complete task
clusters are sampled with replacement, exhaustively covering all
`7^7 = 823,543` ordered resamples. Intervals are nearest-rank 2.5th and 97.5th
percentiles. Task-level resampling was frozen prospectively; the exact
exhaustive implementation, 95% interval level, nearest-rank rule, and complete-
cluster handling are transparent analysis-time specifications rather than
separately preregistered confirmatory choices.

## Acceptance

Across all admissible cells, baseline accepted 6/15 (40.0%) and C-short
accepted 4/16 (25.0%). These unequal-denominator marginal rates are descriptive,
not the primary paired estimate.

Across the seven complete task clusters, mean acceptance was 42.9% for baseline
and 28.6% for C-short. The paired C-short-minus-baseline difference was
**-14.3 percentage points**, with a task-bootstrap 95% percentile interval of
**-50.0 to +14.3 points**. The interval is broad: this Pilot cannot rule out
meaningful harm or a smaller advantage, and it does not establish equivalence,
non-inferiority, or preserved quality.

Among the 14 complete task-repetition pairs, both arms accepted 3, both failed
7, baseline alone accepted 3, and C-short alone accepted 1. Baseline acceptance
changed between repetitions for 2/7 complete tasks; C-short acceptance changed
for 0/7.

## Work evidence

The primary paired work summaries average the two repetitions inside each task,
then compare the seven task clusters.

| Measure | Baseline task mean | C-short task mean | C-short / baseline | 95% ratio interval |
| --- | ---: | ---: | ---: | ---: |
| Input tokens | 1,151,616 | 1,408,131 | 1.223 | 1.012-1.448 |
| Cached input tokens | 1,078,546 | 1,325,367 | 1.229 | 1.018-1.459 |
| Calculated fresh input tokens | 73,070 | 82,764 | 1.133 | 0.922-1.316 |
| Output tokens | 8,228 | 8,899 | 1.082 | 0.920-1.256 |
| Reasoning output tokens | 2,922 | 2,770 | 0.948 | 0.691-1.238 |
| Wall time, seconds | 739.3 | 980.5 | 1.326 | 1.052-1.575 |

In this small task set, C-short used more provider-reported input tokens and
more wall time. Much of the input difference was cached input, so it must not
be described as an equivalent increase in fresh model work or billed cost.
Fresh-input, output, and reasoning-output intervals remain compatible with
effects in either direction.

Provider-billed amount, currency, and cache-write pricing evidence are
unavailable. No monetary cost was inferred. The evidence supports no broad
savings, quality, maintenance, downstream-work, or per-language claim.

## Durable conclusion

Pilot-v3 is terminal and exploratory-only. It produced usable but incomplete
evidence: seven complete paired task clusters, one partially observed task, a
directionally adverse acceptance estimate with wide uncertainty, and no work-
reduction signal in input tokens or wall time. The correct next action is to
stop before confirmatory execution. Any confirmatory design, task exposure,
margin, estimand, sample size, or execution requires fresh explicit authority.

The body-free machine-readable result is
`experiment/pilot_v3_successor_terminal_result.json`. Raw task material,
provider traces, evaluator artifacts, and the successor ledger remain ignored
local evidence and are not published.
