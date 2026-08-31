# Evidence-Conditioned Final Scope Review v0.1 — Exploratory Design

**Date:** 2026-08-29

**Status:** prospective methodology freeze; no task selection or execution

## Research question and boundary

This design asks:

> Does the late-stage evidence-conditioned scope review preserve correctness
> while reducing unnecessary agent work among correct/accepted outcomes,
> without recreating C-short's search/context/corrective-round costs?

This is a small exploratory experiment, not confirmatory evidence. It freezes
the method before any eligible task is selected or exposed. It does not freeze
a pool, materialize a schedule, create a ledger, invoke a subject/provider or
official evaluator, or authorize execution.

Pilot-v3 supplies mechanism-generating history only: it motivates measuring
correctness suppression, search, repeated context, corrective rounds, and wall
work. No Pilot-v3 effect size, task body, patch, evaluator-specific failure, or
semantic similarity judgment was used to choose this design, its task count, or
its selection rule.

## Frozen arms and experimental unit

There are exactly two arms:

1. **Baseline:** no intervention.
2. **Treatment:** **Evidence-Conditioned Final Scope Review**, version `v0.1`,
   loaded byte-for-byte from
   `experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt`, SHA-256
   `d9ac9e18716428e9cd6d038388b01ec668ade47df8bac014658897752166b8cb`.

The treatment bytes are not reinterpreted or normalized. No third arm, dose
control, C-short revision, or alternate wording is permitted.

The primary independent unit is the task/repository cluster. The design uses
eight tasks from eight repositories, one for each language in the frozen source
frame, and two repetitions per task-arm. The 32 cells are correlated
measurements within eight independent clusters; repetitions are never counted
as independent N.

Eight clusters are enough to expose obvious replicated harm, instability,
discordance, and failure of the proposed work mechanism across the available
language coverage while bounding provider and evaluator work. Two repetitions
add within-task stability evidence, permit a literal replicated-suppression
check, and test whether the late-stage mechanism recurs. This is not a power
calculation. The task count and repetitions do not use Pilot-v3's adverse
effect, any hoped-for effect size, or inspected task content.

## Prospective task eligibility

The source is the existing pinned SWE-bench-Live MultiLang snapshot at revision
`62dc0745c40f067fc366ae3eb1a26136e5928f85`. Future exploratory selection must
start from the reconstructable post-Pilot-v3 opaque reserve commitment
`4e8137ee3a23571546f1fec4831b26fd3d0a93a4bbdf70d90088284c87a05605`.
The current goal does not reconstruct or enumerate that reserve.

An eligible row must satisfy all of the following using metadata only:

- it belongs to that frozen snapshot and opaque reserve;
- neither its task nor repository was exposed through development experiments,
  Pilot-v1, Pilot-v2, Pilot-v3, any successor/continuation, any canary, or any
  host-qualification replacement;
- its language is `c`, `cpp`, `cs`, `go`, `java`, `js`, `rust`, or `ts`;
- its pinned host/container image is feasible;
- the official evaluator and nonempty rebuild, fail-to-pass, pass-to-pass, and
  test commands are available; and
- its repository is not used by another selected task.

Legitimate selection metadata are limited to opaque instance identity,
repository identity, language, creation timestamp, container image identity,
evaluator-command availability, and fail-to-pass/pass-to-pass counts. Task
bodies, difficulty, expected success, known patch size, outcome history,
semantic similarity to a Pilot-v3 failure, and manual preference are forbidden.
Evaluator availability is an operational feasibility property, not an
evaluator outcome.

## Exploratory partition and confirmatory reserve

At a separately authorized selection goal, exactly eight repositories will be
carved from the current opaque reserve into a new exploratory-only partition.
This makes the exploratory allocation and the remaining confirmatory reserve
repository-disjoint.

After selection, every task from a selected repository must be removed from the
confirmatory reserve. The remainder must be recommitted under a new
domain-separated SHA-256 ranking. Only its task count, repository count, and
commitment digest may be published. Remaining IDs and bodies stay opaque. This
goal performs neither the carve-out nor recommitment.

Using the existing reserve preserves a pinned dataset/evaluator boundary and
avoids creating a semantically curated side pool. Confirmatory integrity is
preserved by repository-level removal, a new opaque commitment, and the rule
that any future confirmatory work requires a separate design and authorization.

## Metadata-only selection algorithm

The future selector must process languages in the fixed order `c`, `cpp`,
`cs`, `go`, `java`, `js`, `rust`, `ts`. Within a language, it ranks candidates
lexicographically by:

```text
SHA256(selection_seed NUL source_revision NUL language NUL opaque_instance_identity)
```

where `selection_seed` is
`engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-selection`.
It chooses the first candidate whose repository is not already selected.
Digest ties are broken by opaque instance identity. If any language cannot
supply a fresh repository-distinct task, selection fails closed; tasks are not
borrowed, manually substituted, or chosen after content inspection.

Known Pilot-v3 task details and evaluator-specific failure modes are outside
the selector input. They cannot affect eligibility, rank, sample size,
replacement, or schedule. There is no post-freeze task-replacement authority.

## Deterministic schedule algorithm

The future pool contains 16 task-repetition blocks. The scheduler uses
`engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-order`
as its fixed seed.

For each opaque task commitment, one SHA-256 orientation bit determines whether
baseline or treatment is first in repetition 1. Repetition 2 uses the reverse
order. Every task is therefore baseline-first once and treatment-first once.

All task-repetition blocks are ranked by:

```text
SHA256(schedule_seed NUL future_pool_commitment NUL opaque_task_commitment NUL repetition)
```

Ties are broken only by opaque task commitment and repetition. The two arms of
each block execute contiguously in their precomputed order. The materialized
schedule is then digest-bound. Manual rearrangement, systematic baseline-first
ordering, interim adaptation, and outcome-dependent pauses or replacements are
forbidden.

The validator tests this algorithm only with synthetic opaque identities. This
goal creates no real cell or schedule.

## Official outcomes, missingness, and intention to treat

Official disposition and corrective-feedback availability remain separate.
Every randomized cell is in the analysis population. The categories are:

| Durable terminal state | Treatment |
| --- | --- |
| Accepted outcome | Valid experimental outcome; retain in frozen arm |
| Official evaluator/test failure | Valid negative outcome; retain in frozen arm |
| Empty patch | Valid negative outcome; retain in frozen arm |
| Subject failure | Valid negative outcome; retain in frozen arm |
| Trajectory timeout | Valid negative outcome; retain in frozen arm |
| Provider/API infrastructure failure | Attempt-invalid only under frozen retry handling |
| Local Docker/runtime infrastructure failure | Attempt-invalid only under frozen retry handling |
| Coherent official evaluator `error` | Attempt-invalid only under frozen retry handling |
| Coherent official evaluator `incomplete` | Attempt-invalid only under frozen retry handling |
| Contradictory/multiple terminal identity | Mandatory batch stop |
| Malformed/contradictory durable evidence | Mandatory batch stop |

Valid negative outcomes are never rerun because they are unfavorable. No
missing outcome is relabeled, synthesized, or imputed. All admissible cells,
including failures and timeouts, remain in marginal intention-to-treat quality
summaries.

An incomplete task cluster is excluded from the primary paired estimate, but
every admissible cell remains in marginal summaries. Reporting must show
missing cells by arm and frozen reason and provide best-case/worst-case
acceptance bounds for infrastructure-missing cells. No missing work value is
silently treated as zero.

## Attempts, retries, and operator pauses

Every cell has a hard maximum of two total attempts across all categories.
Across the batch there are exactly four infrastructure-retry units and two
separate operator-interruption units. Each infrastructure-invalid cell can
restart at most once, only if both its per-cell capacity and the batch
infrastructure allowance remain. These capacities cannot be increased after
freeze or outcome review.

Planned pauses occur only between cells before the next `attempt_started`
checkpoint. They are recorded contemporaneously before outcome review and
consume no interruption allowance.

A mid-attempt operator interruption is recorded contemporaneously, cannot be
relabeled as infrastructure, and leaves the interrupted attempt immutable. A
permitted restart uses the next attempt number and entirely fresh isolation.
If the relevant allowance or the two-attempt cell maximum is exhausted, the
batch stops with the incomplete state preserved. Restart decisions cannot use
interim arm outcomes.

## Corrective round

The standardized trajectory remains round 0 plus at most one corrective round:

- official `failure` with named feedback available: supply only the named
  failing checks identically to either arm and permit round 1;
- official `failure` with feedback unavailable: valid negative outcome, no
  invented feedback and no corrective round;
- `empty_patch`: valid negative outcome and no correction;
- coherent `error` or `incomplete`: only the frozen infrastructure-invalid
  handling; and
- contradictory, multiple, or structurally inconsistent terminal identities:
  stop the batch.

The correction count is not changed for expected candidate behavior.

## Isolation and durable evidence

Every attempt starts with a fresh repository/worktree, Codex home and session,
credential copy, raw root, derived root, and evaluator-writable root. Only the
pinned evaluator and dataset dependencies may be reused read-only. No state is
inherited between cells or attempts.

The scheduler writes canonical JSONL events in a SHA-256 hash chain and fsyncs
each checkpoint. Restart derives only from the durable ledger; a completed cell
is never repeated. A receipt is constructed only after required official
evaluator disposition/feedback evidence, usage/timing and isolation identities,
termination metadata, and credential-cleanup evidence are durable. Failure
paths must remove the isolated credential copy.

No ledger, receipt, credential copy, or attempt root is created by this design
goal.

## Quality and acceptance analysis

Quality is a prerequisite, not a quantity traded against work.

The primary paired estimate averages the two binary repetitions within each
arm and complete task cluster, computes treatment minus baseline for each task,
and gives every task equal weight. Marginal summaries report accepted numerator,
admissible denominator, and rate separately by arm. Reporting also includes
matched-repetition both-accepted, both-negative, baseline-only, and
treatment-only counts, plus each task's two-repetition acceptance pattern.

Experimental failures and timeouts stay negative under intention-to-treat
semantics. Infrastructure-invalid attempts follow only the frozen retry rule;
they never become arm successes or failures by inference.

For `N` complete task clusters, uncertainty exhausts all `N^N` ordered
task-cluster bootstrap resamples. It uses equal cluster weights and nearest-rank
2.5th and 97.5th percentiles. Cells are never resampled independently. The
analysis also recomputes every paired quality and work summary after leaving
out each complete task once. These are deterministic exploratory intervals and
sensitivity summaries, not significance gates.

## Unconditional work analysis

The durable trajectory measures are:

- input tokens;
- cached input tokens;
- calculated fresh input (`input - cached input`);
- output tokens;
- reasoning-output tokens;
- wall time;
- subject turns and corrective rounds;
- command executions;
- conservative local read/search interactions; and
- completed web-search interactions.

Each measure is averaged across repetitions within arm and complete task, then
compared at task-cluster level with the same task bootstrap and leave-one-task-
out analysis. Arm-level marginal distributions over every admissible cell are
also reported. Failed and expensive runs are not dropped because they weaken a
savings story.

Provider billing remains unavailable unless the provider supplies an actual
amount and currency. Token counts or list prices are never converted into a
billing claim.

Final changed files, added/deleted lines, and dependency delta are secondary
structural diagnostics only. They are not quality, success, or proof that work
was unnecessary.

## Accepted-outcome work estimand

The treatment's proposed mechanism is evaluated first on matched repetitions
accepted in both arms. Within each task, differences for jointly accepted
matched repetitions are averaged; tasks are then summarized equally. This
keeps the comparison paired and avoids presenting different arm-specific sets
of accepted outcomes as though they were exchangeable.

The analysis must also identify whether durable trajectory evidence supports a
specific treatment-induced removal or simplification of unsupported optional
work without broad search or lost correctness. A smaller patch alone is not
such evidence.

Arm-specific work summaries over all accepted cells may be shown separately as
descriptions of selected populations. They cannot support a causal work claim:
conditioning on acceptance can select different tasks/outcomes in each arm.
The unconditional quality result, discordance, failures, and missingness must
appear beside every accepted-outcome work summary. This conditional mechanism
analysis never replaces intention-to-treat quality.

## Operational retirement gates

These are directional, evidence-based stop rules, not significance tests,
non-inferiority margins, or MCIDs. The exact candidate is retired if any gate
fires:

1. **Necessary-correctness suppression:** the same task shows treatment-caused
   suppression/removal of necessary correctness work in both repetitions, or
   the event recurs on two task clusters.
2. **Adverse acceptance:** paired task-level treatment acceptance is below
   baseline and baseline-only discordant clusters outnumber treatment-only
   clusters. Only prospectively classified arm-independent infrastructure
   missingness may explain the pattern; work savings cannot compensate for it.
3. **No accepted-outcome mechanism:** jointly accepted matched comparisons do
   not show both a concrete evidence-supported removal/simplification of
   unsupported optional work and a reduction in at least one trajectory work
   measure.
4. **More corrective rounds:** the treatment task-cluster mean is higher and
   more complete clusters increase than decrease.
5. **More search:** the treatment task-cluster mean for local read/search or
   completed web search is higher and more complete clusters increase than
   decrease.
6. **More repeated context:** the treatment task-cluster mean for cached input
   is higher and more complete clusters increase than decrease.
7. **More wall/work:** treatment wall time or another trajectory work mean is
   higher and more complete clusters increase than decrease.
8. **Structural-proxy-only benefit:** apparent benefit exists only as fewer
   files, lines, dependencies, or another smaller-looking patch diagnostic.
9. **Pre-activation effect:** durable trajectory evidence shows changed ordinary
   discovery, correctness, or integration work before the frozen review point.
10. **C-short equivalence:** durable evidence shows up-front literal narrowing,
    reuse hunting, or other behavior materially equivalent to C-short v0.1.
11. **Broad proof search:** the final review initiates broad proof-of-minimality
    searching in both repetitions of one task or on two task clusters.

No threshold may be weakened after task or outcome inspection. Multiple gates
may fire; reporting preserves them all rather than choosing the most favorable
story.

## Required reporting and claim boundary

The final exploratory report must present, in this order:

1. execution completeness and missingness;
2. unconditional marginal and paired quality;
3. discordant pairs/clusters and repeated patterns;
4. unconditional work;
5. accepted-outcome paired mechanism evidence with its selection warning;
6. corrective/search/context and activation diagnostics;
7. leave-one-task-out and task-bootstrap uncertainty;
8. every retirement gate; and
9. the bounded disposition.

The strongest possible positive statement is that the exact candidate produced
bounded exploratory evidence sufficient to consider another separately
authorized stage. The experiment cannot establish equivalence,
non-inferiority, universal quality preservation, broad maintainability,
per-language efficacy, monetary savings without provider billing, downstream
lifecycle savings, or confirmatory proof.

## Machine authority and authorization boundary

The machine-readable methodology is
`experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json`.
The standard-library validator checks canonical bytes, treatment identity,
two-arm identity, sample/repetition counts, selection contamination controls,
counterbalancing, retry/correction ceilings, quality precedence, work measures,
retirement gates, and absence of actual task material. Synthetic schedule
fixtures test reproducibility without representing an eligible task.

Task selection, pool freeze, real schedule freeze, execution contract, ledger,
provider/Codex use, official evaluator use, and confirmatory work require fresh
explicit authorization.

## Decision

### `EXPLORATORY DESIGN QUALIFIED — TASK SELECTION AND FREEZE REQUIRE SEPARATE AUTHORIZATION`
