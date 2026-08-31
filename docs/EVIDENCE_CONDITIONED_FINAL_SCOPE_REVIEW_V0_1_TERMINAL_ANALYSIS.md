# Evidence-Conditioned Final Scope Review v0.1 Terminal Analysis

**Decision:** **CANDIDATE RETIRED — EXPLORATORY EVIDENCE ONLY**

The frozen 32-cell execution reached a legitimate `batch_stopped` boundary at
the first cell of block 13. Both permitted attempts for that cell ended in the
same local Docker runtime infrastructure failure. The state machine consumed
one of four batch infrastructure-rerun units, but the stricter two-attempt
same-cell limit bound first. No attempt 3 was created and the remaining cells
were not run.

The machine-readable authorities are:

- `experiment/evidence_conditioned_final_scope_review_v0_1_terminal_result.json`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_terminal_analysis.json`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_mechanism_annotations.json`.

## 1. Execution completeness and missingness

The ledger contains 247 hash-chained events, 26 attempts, 26 receipts, 24
admissible cells, and two infrastructure-invalid receipts for the same frozen
cell. Eight cells are missing: both arms of blocks 13 through 16. There are
five complete task/repository clusters and two incomplete observed clusters.
No missing cell was imputed, normalized to zero, replaced, reordered, or
rerun beyond the frozen attempt limit.

The raw ledger remains owner-local because it contains controlled execution
references. The public terminal receipt binds its SHA-256
`dded31ad9aefd87642fa4d7d48d16ea8de46058d3fec99b06db472473f6d4cfd`
and last event SHA-256
`8b5a2b18bcdccd771d8390b6a70b6b40e780e2f54929043445acb60cb1bae2e6`.

## 2. Unconditional marginal and paired quality

Across all admissible cells, baseline accepted 5/12 (0.4167) and treatment
accepted 7/12 (0.5833). With four missing cells per arm, the frozen worst/best
bounds are 0.3125–0.5625 for baseline and 0.4375–0.6875 for treatment.

Across the five complete task clusters, mean acceptance was 0.4 for baseline
and 0.5 for treatment, a treatment-minus-baseline difference of +0.1 with an
exact task-bootstrap 95% percentile interval of 0.0 to 0.3. This is descriptive
exploratory evidence, not superiority, equivalence, or non-inferiority.

## 3. Discordant pairs and replicated patterns

The ten complete matched repetitions contain four both-accepted, five both-
negative, zero baseline-only, and one treatment-only pair. One task cluster
contains treatment-only discordance; none contains baseline-only discordance.
This does not offset separately frozen work and mechanism retirement gates.

## 4. Unconditional work

Task-cluster treatment-minus-baseline point differences were:

| Measure | Difference | Exact task-bootstrap 95% interval |
| --- | ---: | ---: |
| Input tokens | +143,106.8 | -214,609.0 to +582,079.7 |
| Cached input tokens | +147,353.6 | -183,577.6 to +568,832.0 |
| Calculated fresh input tokens | -4,246.8 | -30,234.5 to +12,591.5 |
| Output tokens | +307.3 | -1,604.1 to +1,911.9 |
| Reasoning output tokens | -56.9 | -1,382.6 to +908.1 |
| Wall seconds | +40.8 | -42.0 to +129.2 |
| Subject turns | +0.9 | +0.7 to +1.0 |
| Corrective rounds | -0.1 | -0.3 to 0.0 |
| Command executions | +2.5 | +0.3 to +5.9 |
| Local read/search interactions | +12.6 | -3.7 to +33.8 |
| Completed web searches | +0.7 | 0.0 to +1.5 |

All marginal means and medians remain in the canonical analysis artifact. The
directional gates use the prospectively frozen cluster rules, not post-hoc
significance thresholds.

## 5. Jointly accepted paired work and mechanism

Four matched repetitions across two task clusters were accepted in both arms.
Within that selected subset, treatment increased every reported trajectory
field except completed web searches and corrective rounds, which tied. No
treatment cell had evidence-backed optional-removal or simplification evidence,
so no accepted-outcome work-reduction mechanism was established.

This subset is conditional descriptive mechanism evidence. Conditioning on
joint acceptance can select outcomes and never replaces the unconditional
quality and work results above.

## 6. Corrective, search, context, and activation diagnostics

Corrective rounds decreased by 0.1 at the task-cluster level, while local
read/search interactions increased by 12.6, completed web searches by 0.7, and
cached input tokens by 147,353.6. All 12 admissible treatment cells recorded
late-stage activation; none lacked activation and no pre-activation treatment
exposure was recorded.

The mechanism annotation file records all five semantic flags as false for
each admissible treatment cell because no positive trace/patch-level manual
evidence was established. Empty references are not evidence of absence; they
prevent unsupported positive mechanism claims.

## 7. Task-level bootstrap

The exact nonparametric bootstrap uses the five complete task/repository
clusters as the resampling unit, for 5^5 = 3,125 ordered resamples. Repetitions
are correlated measurements and are not counted as independent sample size.

## 8. Leave-one-task-out sensitivity

Across all five omissions, the acceptance difference remains nonnegative (0.0
or +0.125), subject turns remain higher (+0.875 to +1.0), and completed web
searches remain higher (+0.375 to +0.875). Input, cached-context, wall-time,
and other work directions vary under omission, demonstrating the expected
fragility of this small incomplete exploratory sample. Exact values and opaque
task commitments remain in the canonical analysis artifact.

## 9. Retirement gates

Five of eleven frozen gates fired:

- `no_accepted_outcome_mechanism`;
- `search_increase`;
- `cached_context_increase`;
- `wall_or_work_increase`;
- `structural_proxy_only`.

The necessary-correctness-suppression, adverse-acceptance, corrective-round-
increase, pre-activation-effect, C-short-equivalence, and broad-minimality-
search gates did not fire. Files changed decreased by 0.6 per complete task
cluster and lines deleted decreased by 0.6, while lines added tied; without an
accepted-outcome mechanism, those structural changes are diagnostic proxies
only. Dependency delta is unavailable and was not treated as zero.

## 10. Bounded disposition

The prospectively frozen rule retires the candidate when any retirement gate
fires. Five fired, so exact **Evidence-Conditioned Final Scope Review v0.1 is
retired unchanged**. The stopped schedule is not repaired or restarted, no
attempt 3 is allowed, and the remaining eight cells are not executed.

This is exploratory evidence from a terminal partial schedule. It supports no
confirmatory, equivalence, non-inferiority, universal quality, per-language,
maintainability, downstream-work, provider-billing, or monetary-savings claim.
It authorizes no treatment revision, another exploratory iteration, or
confirmatory work.
