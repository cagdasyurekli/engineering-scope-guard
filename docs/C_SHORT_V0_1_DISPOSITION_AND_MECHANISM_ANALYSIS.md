# C-short v0.1 Disposition and Mechanism Analysis

**Date:** 2026-08-29

**Status:** terminal post-hoc exploratory analysis

## Primary disposition

**MECHANISM IDENTIFIED — ONE NEW CANDIDATE DESIGN PERMITTED**

Byte-exact `C-short v0.1` is retired unchanged. The result does not support
confirmatory execution. One later, materially distinct candidate-design goal is
rationally permissible because a replicated task-level failure exposes a
concrete intervention target: an up-front literal-minimality instruction can
suppress acceptance-relevant adjacent handling when a natural-language task is
narrower than the behavior enforced by its evaluator. This is a supported
post-hoc mechanism hypothesis, not an established causal effect.

This disposition permits design only after fresh explicit authorization. It
does not permit candidate bytes, implementation, freeze, provider/evaluator
use, task exposure, Pilot-v4, or any execution.

## Evidence classes

- **Directly observed:** frozen receipts, outcomes, evaluator dispositions,
  provider-reported usage, timestamps, trace item types, patch structure, and
  the exact treatment text.
- **Deterministically derived:** paired denominators and effects, calculated
  fresh input, exact bootstrap, task/repetition tables, trace-item counts,
  work decompositions, and leave-one-task-out summaries.
- **Post-hoc mechanism hypothesis:** an interpretation tied to several concrete
  observations but not prospectively randomized or independently manipulated.
- **Unsupported speculation:** an explanation not distinguishable from task or
  trajectory noise with the available evidence.

No post-hoc hypothesis below is presented as a causal explanation.

## 1. Frozen-result reconciliation

Mechanism interpretation proceeded only after the existing analysis regenerated
`experiment/pilot_v3_successor_terminal_result.json` byte for byte from the
validated private successor ledger. The regenerated SHA-256 is
`20c8354adc0a80bd90bbf3e2eeed21d2d3e3eb3d42eeddc3091ae1e50501c14f`.

The following checks agree with the published terminal result:

- 32 frozen cells, 33 starts, 33 complete receipts, and 288 hash-chained events;
- 31 admissible experimental cells and two coherent infrastructure-invalid
  attempts at position 32, followed by the frozen `attempt_limit_exhausted`
  stop; no position-32 attempt 3;
- 10 accepted and 21 evaluator-test-failure outcomes; no experimental failure
  was excluded or relabeled;
- seven complete task clusters (28 paired cells) and one incomplete slot; the
  incomplete slot's three admissible cells remain in marginal summaries but are
  not imputed into paired estimands;
- baseline 6/15 and C-short 4/16 marginal acceptance; complete-cluster task
  means 42.9% and 28.6%; paired C-short-minus-baseline -14.3 percentage points;
- exact nonparametric task bootstrap over all `7^7 = 823,543` ordered resamples,
  using nearest-rank 2.5th and 97.5th percentiles, reproducing -50.0 to +14.3
  percentage points;
- receipt assignment, repetition, position, and arm match the frozen schedule;
- every round-level usage sum matches its receipt, and calculated fresh input is
  exactly input minus cached input;
- paired input-token ratio 1.223 (95% interval 1.012–1.448) and wall-time ratio
  1.326 (1.052–1.575), with cached and fresh input kept separate.

The unequal marginal denominators are descriptive. The broad paired interval
does not establish equivalence, non-inferiority, or absence of harm. Provider
billing remains unknown because no amount and currency exist.

## 2. Complete-cluster diagnostic table

Task identities below were already public in the frozen Pilot-v3 pool. `B/S`
means baseline/C-short across the two repetitions. Ratios are C-short divided by
baseline after summing both repetitions. Full cell-level body-safe observations
are in `experiment/pilot_v3_c_short_mechanism_diagnostic.json`.

| Public task | Repetition outcomes | Accepted B/S | Turns B/S | Input ratio | Fresh-input ratio | Wall ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `timescale__timescaledb-9955` | both failed; both failed | 0/0 | 4/4 | 1.529 | 1.379 | 1.081 |
| `Azure__azure-sdk-for-net-58482` | C-short only; both accepted | 1/2 | 2/2 | 0.982 | 0.883 | 0.914 |
| `influxdata__telegraf-18686` | baseline only; both failed | 1/0 | 3/4 | 1.584 | 1.021 | 1.398 |
| `checkstyle__checkstyle-19487` | both failed; both failed | 0/0 | 3/4 | 1.119 | 1.179 | 1.372 |
| `GladysAssistant__Gladys-2504` | baseline only; baseline only | 2/0 | 2/4 | 1.090 | 1.056 | 1.827 |
| `gleam-lang__gleam-5982` | both failed; both failed | 0/0 | 4/3 | 0.853 | 0.752 | 0.912 |
| `ether__etherpad-7445` | both accepted; both accepted | 2/2 | 2/2 | 1.648 | 1.580 | 1.164 |

The machine artifact retains, for each cell, termination, official evaluator
disposition, corrective-round use, input/cached/fresh/output/reasoning tokens,
wall time, trace interaction counts, patch line/file counts, and aggregate
fail-to-pass/pass-to-pass check counts. It contains no prompts, source, raw
commands/output, failing-check names, traces, local paths, or private task data.

## 3. Discordance

Across 14 complete task-repetition pairs, both arms accepted three, both failed
seven, baseline alone accepted three, and C-short alone accepted one.

The acceptance difference is concentrated but not a one-run accident:

- `GladysAssistant__Gladys-2504` accounts for two baseline-only pairs. Both
  C-short repetitions produced the same narrower behavioral change and failed
  the same one of two fail-to-pass checks; both baseline repetitions handled the
  adjacent missing-state case, passed both fail-to-pass checks, and preserved
  all 3,386 pass-to-pass checks. The comparison is summarized structurally; no
  raw task body, source, patch, or check name is published.
- `influxdata__telegraf-18686` contributes one baseline-only pair, but baseline
  itself failed the other repetition. This supports instability/noise more than
  a replicated mechanism.
- `Azure__azure-sdk-for-net-58482` contributes the only C-short-only pair; both
  arms accepted the other repetition. Negative evidence against a universal
  harm mechanism is therefore retained.

Corrective-round use is partly a consequence of discordance, not an independent
cause: baseline used six corrective rounds and C-short nine. The three extra
C-short rounds are the three baseline-only pairs, where baseline ended accepted
after round 0 while C-short entered the frozen correction and still failed.

## 4. Work amplification

Across the 28 paired cells, C-short recorded 19,713,833 input tokens versus
16,122,630 for baseline. Of the 3,591,203-token difference, 3,455,488 (96.2%)
is cached input and 135,715 (3.8%) is calculated fresh input. This is repeated
context ingestion, not a corresponding increase in fresh tokens and not a
billing claim.

The three additional corrective turns explain part, but not all, of the
difference. C-short had 23 subject turns versus 20. Per subject turn, input was
6.3% higher and cached input 6.9% higher, while calculated fresh input was 1.5%
lower, output 5.9% lower, and reasoning output 17.6% lower. The evidence does
not support a claim that C-short caused more hidden reasoning. Per-turn timing
is unavailable, so longer individual turns cannot be established.

Trace and patch structure also show no general work-reduction pattern:

- command executions: 262 C-short versus 249 baseline;
- conservative local read/search command segments: 534 versus 512;
- completed web-search items: 22 versus 9, with C-short higher on five of seven
  task clusters and tied on two;
- file-change events: 36 versus 37;
- changed files in final patches: 51 versus 52.

The web-search difference is directly observed and directionally consistent,
but the traces do not identify which treatment clause caused each search. It is
supportive of a search-tax hypothesis, not causal proof.

Outcome-class summaries preserve inconvenient cases:

- in the three both-accepted pairs, C-short averaged 154,182 more input tokens
  but 33 seconds less wall time;
- in the seven both-failed pairs, C-short averaged 366,200 more input tokens
  and 90 seconds more wall time;
- in the three baseline-only pairs, C-short used one extra turn and averaged
  920 seconds more wall time;
- in the one C-short-only pair, C-short still used 276,838 more input tokens and
  86 seconds more wall time.

These cells do not show less agent work per correct/accepted outcome.

## 5. Mechanism assessment

### Literal-minimality interference — promoted to a concrete hypothesis

**Evidence for:** the exact treatment begins with “Implement what the
requirement states” and ends by prohibiting functionality or structure the
requirement does not require. On the replicated `GladysAssistant` discordance,
both C-short trajectories handled the explicit missing state but left an
adjacent missing-state dereference unchanged; both baseline trajectories also
handled that adjacent state. The resulting patch structures and evaluator
outcomes repeated exactly by arm. This links wording, behavior, and acceptance
through multiple concrete observations.

**Evidence against/limits:** it is one task cluster; the mechanism was not
prospectively manipulated; one other cluster favored C-short; and the evaluator
may encode behavior only implicit in the short natural-language issue. The
evidence therefore does not establish a general causal effect or a population
harm rate.

**Assessment:** concrete enough to define an intervention target, but only as a
post-hoc hypothesis. A future candidate must avoid constraining ordinary
correctness/integration inference before the work is complete.

### Reuse/search tax — supportive secondary hypothesis

**Evidence for:** C-short explicitly says to reuse what already exists. It had
13 more shell-command executions, 22 more local read/search segments, and 13
more completed web searches; web searches were higher in five clusters and
never lower. Cached input also increased broadly.

**Evidence against/limits:** local read/search differences were heterogeneous;
some high-work cells had no extra web search; trace item types do not reveal
motivation; and task/trajectory variation remains large.

**Assessment:** plausible and consistent with a search tax, but insufficient by
itself to identify the causal clause.

### Corrective-round amplification — observed mediator

Three extra C-short corrective rounds directly added repeated context and wall
time. Because they followed adverse evaluator outcomes, they are more properly
treated as a downstream mediator of failure than as proof that the prompt
independently caused deliberation.

### More reasoning or generally longer turns — unsupported

Reasoning output was lower overall and per turn under C-short. Subject-round
durations are not durably separated. Claims of deeper reasoning, longer
individual turns, or generalized repeated checking are unsupported.

### Task noise / little operational effect — remains plausible but incomplete

Several diagnostics are heterogeneous, and the acceptance point estimate is
driven by one replicated cluster. But work leave-one-task-out ratios remain
above one regardless of which cluster is omitted, and the replicated
literal-minimality failure cannot be dismissed merely as statistical
insignificance. Noise may contribute; it does not restore a savings claim.

## 6. Stability and sensitivity

C-short acceptance was stable between repetitions on all seven complete tasks;
baseline acceptance changed on two. Stability here can mean stable failure as
well as stable success and is not a quality claim.

Leave-one-task-out summaries are descriptive only:

- acceptance difference ranges from -25.0 to 0.0 percentage points; omitting
  `GladysAssistant__Gladys-2504` moves the estimate to 0.0, while omitting the
  C-short-favoring `Azure` cluster moves it to -25.0;
- input-token ratios range from 1.112 to 1.279;
- wall-time ratios range from 1.185 to 1.387.

Five of seven clusters have higher C-short input and wall time; two have lower
values for both. The adverse work direction is therefore not solely produced
by one cluster, although leverage is uneven: the `timescaledb` cluster dominates
the input difference and `GladysAssistant` dominates the wall-time difference.
With seven clusters, no per-language or elaborate subgroup inference is made.

## 7. Earlier development and Pilot history

The authored development pool gave all three arms 8/8 acceptance. Relative to
baseline, C-short used 3.0% fewer input tokens, 8.9% less wall time, one fewer
read/search command, three fewer modified-file instances, and 93 fewer added
lines. That was a reasonable development-screening reason to advance C-short
instead of the longer D v0.1 variant.

Pilot-v3 contradicts that directional development work signal and supersedes it
for disposition because it used fresh external tasks, two repetitions,
official task-specific evaluators, corrective rounds, durable receipts, and
task-clustered analysis. The authored development tasks were small coverage
fixtures, all reached a ceiling outcome, used one turn with no correction, and
were never efficacy evidence. The observations are not pooled.

Pilot-v1/v2 and their successors remain infrastructure, integrity, or incomplete
measurement history. They do not supply a comparable baseline-versus-C-short
effect and are not added to the Pilot-v3 estimate.

## 8. Candidate-design hypothesis and retirement gate

No new treatment is written or frozen here. The one design hypothesis permitted
for a later, separately authorized goal is:

- **Target mechanism:** up-front literal-minimality and reuse obligations can
  suppress acceptance-relevant adjacent correctness work and add search tax.
- **Materially distinct concept:** a single late-stage, evidence-conditioned
  scope check applied only after ordinary implementation and relevant checks,
  aimed at optional speculative structure rather than at restricting solution
  discovery, reuse, dependencies, or functionality in advance.
- **Behavior expected to change:** preserve default exploration and necessary
  adjacent integration/edge-case handling; reduce only additions unsupported by
  the requirement, repository evidence, or relevant checks after correctness is
  established; create no new search obligation.
- **Behavior that must remain unchanged:** correctness, validation, safety,
  relevant testing, shared-cause fixes, justified dependencies, evaluator,
  model/reasoning, and benchmark rules.
- **Falsifiable expected effects:** no replicated omission of adjacent
  acceptance-relevant behavior; no increase in corrective rounds, cached-context
  accumulation, or wall time; and a reduction in unnecessary structural work
  only among correct/accepted outcomes.
- **Immediate retirement evidence:** any replicated baseline-only acceptance
  caused by suppressed necessary work; no work reduction among accepted
  outcomes; higher corrective/context/wall work; or apparent benefit existing
  only as fewer lines/files while correctness worsens.

This is not `C-short v0.2`, exact wording, a frozen arm, or execution authority.

## 9. What cannot be inferred

The evidence does not establish causality, equivalence, non-inferiority,
quality preservation, per-language effects, maintainability, downstream work,
universal cost-to-acceptance, billed cost, or that every extra search/turn was
unnecessary. It cannot determine how the hypothesis will behave on a new held-
out distribution. It permits one bounded design question, not optimism.

## Authorization boundary

After this report's authorized GitHub stabilization, stop. Fresh explicit user
authorization is required for any candidate design goal. A still-later and
separate authorization would be required for exact bytes, implementation,
freeze, provider/evaluator use, task exposure, Pilot, or confirmatory work.
