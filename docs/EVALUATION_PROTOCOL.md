# Evaluation Protocol v0.1

**Status:** Pilot-v3 is terminal historical exploratory evidence. The
Evidence-Conditioned Final Scope Review v0.1 exploratory methodology is frozen
prospectively without a selected pool or execution authority. Confirmatory
numerical margins, estimand, and sample size remain intentionally **not frozen**.

## 1. Research questions

### RQ1 — Main effect

Does C-short v0.1 change agent cost/work to a standardized accepted outcome
compared with default Codex, on the tested task distribution?

### RQ2 — Quality risk

What task-success or deterministic guardrail degradation can the experiment rule
out? If it cannot rule out a meaningful degradation, it must say so rather than
claim “quality preserved.”

### Retired development question — Longer-policy increment

Development found no acceptance advantage for D v0.1 over C-short v0.1 and did
not justify advancing the longer variant. No current Pilot question compares a
full policy with a short semantic control. A future longer policy would require
a new version and a separately justified incremental-value question.

### Deferred RQ4 — Project calibration

Only after RQ1/RQ2: does project-specific engineering intent improve decisions beyond the bounded policy alone?

### Deferred RQ5 — Downstream work

Only after a per-task effect exists: does the policy reduce total work across cumulative task chains, rather than merely shifting cost to later tasks?

## 2. Current arm logic

### A — Baseline

Exact default agent/harness behavior with no added project policy.

### B — C-short treatment

The exact C-short v0.1 text in `CANDIDATE_POLICY.md`.

Development rejected advancing D v0.1 unchanged. For a future Exploratory Pilot,
C-short is the treatment rather than a semantic/dose control for a surviving
full policy. The minimum interpretable Pilot therefore has two arms: baseline
and C-short v0.1.

Do not add D v0.1, a generic instruction, or another arm for symmetry. A third
arm requires a new candidate and a distinct predeclared research question.

### Confirmatory boundary

The future confirmatory arm design is not frozen. Pilot feasibility and variance
evidence may inform whether baseline versus C-short remains a useful question,
but may not be used to restore D v0.1 or optimize policy wording against Pilot
tasks. Exact confirmatory arms must be frozen before confirmatory task bodies or
results are inspected.

## 3. Task pools

Keep three disjoint pools.

### Development pool

- Policy and harness may be changed freely.
- Traces may be inspected.
- Results are never published as evidence of efficacy.

### Pilot/exploratory pool

Purpose:

- estimate between-task and within-task variance;
- estimate baseline acceptance and arm discordance;
- detect ceiling/floor problems;
- debug harness isolation and timeout behavior;
- test reviewer blinding feasibility;
- estimate task-supply constraints.

Pilot effect estimates must not be promoted into confirmatory claims. If pilot results are used to rewrite the policy, the pilot is contaminated for efficacy estimation.

The historical external-source frame selected 12 Pilot-v1 tasks from
`SWE-bench-Live/MultiLang` and retains a repository-disjoint reserve. At source
revision `62dc0745c40f067fc366ae3eb1a26136e5928f85`, 634 distinct tasks pass the
metadata/evaluator-feasibility frame, 12 enter the original Pilot allocation, 84
tasks from those repositories enter neither pool, and 538 enter the original
reserve. Fixed-host qualification later retained eight original tasks and four
deterministic replacements; the effective reserve is 499 tasks across 207
repositories. All final tasks passed 3/3 gold evaluation. The Pilot-specific
contract is now qualified in `experiment/pilot_execution_contract.json`; this
does not itself activate or execute the proposed Pilot goal.

Pilot-v1 and Pilot-v2 are historical/infrastructure evidence only. Pilot-v2 is
permanently closed at 8/44 admissible observations; those observations are not
used for Pilot-v3 task selection, variance, effect-size, sample-size, policy
optimization, or arm-effect estimation.

Pilot-v3 uses a fresh deterministic draw from the post-Pilot-v1 effective
opaque reserve. It selects one repository-distinct task per available language
using only the predeclared metadata projection and a frozen SHA-256 rank. The
result is 8 tasks, 8 repositories, two arms, and two repetitions per task-arm
(32 cells). All eight Pilot-v3 repositories are prospectively excluded from the
confirmatory reserve, leaving 462 tasks across 199 repositories under a new
opaque commitment. No remaining reserve IDs or bodies are emitted. Pilot-v3
has zero post-freeze task-replacement authority.

### Confirmatory pool

- Held out until policy/harness/outcomes/analysis are frozen.
- Individual task statements should remain unseen where practical.
- Run once per frozen experimental version.
- Any policy revision after viewing results creates a new experiment version and requires a new held-out pool.

## 4. Task strata

The four mechanism categories used for authored development coverage are not
valid metadata strata for the external Pilot. Classifying public issues as
“over-build-prone”, “irreducible”, “seeded guard”, or “shared cause” would require
policy authors to inspect task bodies and make semantic judgments before
allocation, reintroducing the selection bias the external source is meant to
reduce.

The external Pilot instead uses observable source metadata: all eight available
languages are represented, 12 Pilot tasks come from 12 distinct repositories,
and all other tasks from those repositories are excluded from the confirmatory
reserve. Language-specific results are exploratory diagnostics only; the
12-task Pilot cannot support per-language effect claims.

Mechanism-focused strata may be reconsidered for confirmatory sampling only if
an external, policy-independent annotation already exists and is frozen before
task bodies or outcomes are inspected.

## 5. Environment control

Every arm/task/seed cell must start from a byte-identical repository state and equivalent agent state.

Freeze and record:

- agent product and exact version;
- model and exact available version identifier;
- reasoning/effort configuration;
- sampling configuration actually supported by the agent;
- tool allowlist/permissions;
- MCP/plugins/global config;
- repository commit/snapshot;
- task text;
- timeout/max-turn policy;
- evaluator version;
- date/time of run.

Do **not** invent a universal `temperature=0` requirement. Use the actual stable configuration exposed by the target agent and freeze it. Repetition is still required because deterministic behavior is not guaranteed.

### Isolation audit

Before every batch, run a canary that verifies which policy is active and that treatment hooks/plugins have not contaminated baseline cells.

Use fresh temporary agent state/container/worktree as needed. Do not assume isolation merely because the repository was reset.

### Prompt caching

Billed cost can be affected by cache behavior independently of behavioral efficiency.

- use fresh per-cell Codex state, ephemeral sessions, and separate outputs;
- counterbalance arm order within task/repetition and retain timestamps;
- record provider-reported input, cached input, output, and reasoning-output
  components separately;
- calculate fresh input only as `input - cached input` and label it calculated;
- report billed cost only when a provider billing record supplies amount and
  currency; an API-list-price estimate is not provider billing;
- invalidate billed-cost claims when cache-write tokens or charged cost remain
  unavailable and cache behavior could change the comparison;
- never describe cache-price changes alone as “less agent work.”

## 6. Outcome hierarchy

### Primary efficiency outcome

The final primary summary statistic will be frozen **after pilot distribution inspection but before confirmatory data are seen**.

Candidate economic primary:

- total billed cost from task start through the standardized corrective protocol to acceptance/failure.

Report regardless of primary choice:

- arithmetic mean cost (expected spend);
- median cost (typical task);
- high quantiles where sample size supports them;
- paired arm differences/ratios with uncertainty.

Do not select whichever statistic looks best after confirmatory results.

### Primary/guardrail effectiveness outcome

Binary accepted outcome under the frozen acceptance procedure.

Do not claim equivalence/non-inferiority unless a substantively justified margin was declared before confirmatory execution and the design has enough information to support the claim.

If not, report the interval directly, using language such as:

> We cannot rule out a decrease as large as X percentage points.

### Quality guardrails

Candidates, depending on task stratum:

- hidden-test pass;
- existing unrelated regression-suite pass;
- seeded security/data-loss/accessibility guard retained;
- shared/root-cause behavior fixed across seeded affected paths;
- no edits that weaken evaluator/test/lint/type configuration.

A quality guardrail breach cannot be compensated for by lower cost.

### Secondary outcomes

- agent turns;
- tool calls;
- wall-clock time;
- files read/searched;
- failed-verification loop count;
- post-hoc rework count;
- corrective rounds to acceptance.

### Diagnostics only

Do not present these as inherently good/bad:

- LOC added/deleted;
- files added/deleted;
- dependencies added/removed;
- duplication delta;
- complexity delta;
- test count.

## 7. Accepted outcome procedure

Preferred layered gates:

1. **Mechanical:** patch applies/builds/parses.
2. **Hidden task tests:** written independently of the policy where practical.
3. **Existing regression checks:** unchanged repository tests relevant to unrelated breakage.
4. **Repository static checks:** existing lint/type rules; detect attempts to change evaluator configuration.
5. **Blinded human review:** only if adequate external reviewer capacity exists.

For the selected external source, the minimum deterministic Pilot gate is the
official F2P and P2P result plus its supplied rebuild/test commands. Additional
lint/type/build checks count only when the task image provides them; do not infer
coverage from their absence.

Human review is required before making broad maintainability/code-quality claims that automated gates do not support.

LLM-as-a-judge may be used as an exploratory screen only, not as the sole acceptance/maintainability criterion unless separately validated against human labels for this exact use.

### Blinding

Where human review is used:

- remove run/arm identifiers but do not remove substantive code/comments merely to disguise an arm;
- randomize presentation order;
- do not tell reviewers the study hypothesis;
- ask reviewers to guess arm assignment as a manipulation check;
- report agreement and disagreements.

## 8. Corrective rounds

To approximate “work until accepted outcome,” a confirmatory harness may use a standardized corrective protocol:

- initial agent attempt;
- evaluate hidden tests;
- on failure, return only predeclared limited failure information (for example failing test names) identically to every arm;
- allow at most a predeclared number of corrective rounds.

This measures **cost-to-acceptance under the standardized corrective protocol**, not universal real-world completion cost. Claims must preserve that scope.

The Pilot contract fixes one trajectory attempt containing round 0 (the initial
subject/evaluator round) plus at most round 1 (one corrective round). Only an
initial evaluator/test failure triggers round 1. Feedback contains failing check
names only, once and identically across arms. A trajectory ends at acceptance,
the second evaluator result, agent failure, trajectory timeout, an
infrastructure-invalid attempt, or a batch-stop integrity failure. Model and
reasoning effort cannot change inside a trajectory.

## 9. Retry/rework metrics

Prefer observable definitions over semantic labels.

### Failed-verification loop

Non-zero test/lint/build event followed by a source edit.

### Post-hoc rework

A file is edited, a verification event occurs, then the same file is edited again within the same task trajectory.

### Corrective rounds

Number of standardized evaluator-feedback rounds before acceptance/failure.

Discovery/search volume is a diagnostic, not automatically “waste.”

## 10. Statistical principles

- Pair arms within task.
- Treat repeated seeds/runs within a task as clustered/correlated.
- Bootstrap/resample at the **task** level, not individual run level, unless the final model explicitly accounts for hierarchy.
- Report effect sizes and uncertainty, not bare p-values.
- Report both typical and expected-cost behavior when distributions are skewed.
- Predeclare handling of timeouts, API failures, and missing runs.
- A policy-induced timeout counts against the policy in the primary intention-to-treat analysis.
- Infrastructure failures demonstrably unrelated to the arm require a predeclared rerun/exclusion rule.
- Keep confirmatory hypothesis families small; exploratory subgroup results remain exploratory unless separately confirmed.

### MCID and quality margin

No universal `15% cost` MCID or `3/5 percentage-point quality` margin is accepted by default.

Before confirmatory execution, choose margins based on:

- intervention complexity and maintenance cost;
- plausible user value;
- baseline task success;
- acceptable risk for the tested task class;
- available task supply and achievable uncertainty.

Do not widen a margin merely because the available sample cannot meet the original one.

## 11. Sample-size process

Do not set a fake precise N before the pilot.

1. Determine the minimum effect that would justify the intervention on substantive grounds.
2. Use the pilot to estimate variance, baseline acceptance, arm discordance, and task-category interaction.
3. Compute the confirmatory task/run requirement from the frozen estimand/design.
4. If the required N is infeasible, narrow the claim or report that quality non-inferiority cannot be established.

Distinct tasks matter more than simply repeating the same few tasks many times.

Historically, 12 repository-distinct Pilot tasks covering all eight available
languages, two arms, and two repetitions produce 48 planned trajectories plus
eight trajectory-level infrastructure reruns. The official source additionally
recommends three gold evaluator runs per task, creating 36 final-pool evaluator
preflights. Fixed-host qualification retained 48 attempts because four
invalid/unstable original tasks also remained in the ledger. This bounded
subject budget is intended only to expose feasibility,
variance, discordance, and heterogeneity; it is not a power calculation and does
not imply that 12 confirmatory tasks would be adequate. Container/evaluator and
runtime/storage qualification and the bounded contract qualification passed.
The 48-cell order is deterministically committed to the replacement-resolved
final-pool digest, two arms, two repetitions, contract version, and recorded
seed. The proposed Pilot goal remains inactive pending human review.

Pilot-v3 deliberately uses 8 repository-distinct tasks, one per language, with
two paired repetitions per arm. The 32-cell size is for feasibility,
within-task instability, arm discordance, cost distribution, harness adequacy,
and effect-direction exploration. It is not a power calculation, does not treat
repetitions as independent tasks, and was not inflated to compensate for prior
early stops. Any future uncertainty analysis resamples at the task level.

## 12. Timeout/failure policy

The Pilot taxonomy is frozen before execution:

- accepted/completed, evaluator/test failure, agent/subject failure, and
  trajectory timeout are experimental outcomes;
- provider/API infrastructure failure and local Docker/runtime infrastructure
  failure invalidate only that attempt and may consume one same-cell rerun;
- harness failure, isolation/contract violation, and malformed/incomplete
  measurement stop the batch because integrity may be compromised;
- each task × arm × repetition cell permits at most two trajectory attempts and
  the batch permits at most eight infrastructure reruns total;
- task, arm, and repetition remain unchanged on a rerun, and every invalid
  attempt remains in the hash-chained ledger.

Task-slot replacement is a separate pre-treatment unit. Its eight-slot host
qualification allowance consumed four slots before the final pool and schedule
were frozen. Any later slot change requires a new pool identity, contract, and
schedule; it cannot consume the trajectory-rerun budget.

Confirmatory timeout, sensitivity, and missingness rules remain to be frozen
separately before confirmatory execution.

### Prospective official-evaluator result boundary

Future exploratory designs using the pinned SWE-bench-Live evaluator must
validate and preserve the aggregate official terminal disposition separately
from corrective-feedback availability. The one-instance `results.json` must
identify exactly one of `success`, `failure`, `error`, `incomplete`, or
`empty_patch`, with internally consistent counts, identifiers, and any
per-instance report. Contradictory or non-unique shapes are malformed and fail
closed.

`resolved: false` with no names in the report's failure arrays is a valid
official failure shape. It means the evaluator did not establish resolution;
it does not imply that a named check is available for a corrective prompt. A
fresh contract must predeclare terminal handling for
`official_disposition=failure` plus `feedback_status=unavailable`; it may not
invent feedback or reinterpret the result as pass, error, or incomplete.

This rule is prospective. Pilot-v2 position 9 remains frozen as
`malformed_incomplete_measurement`, and Pilot-v2 is permanently closed with no
additional execution or analysis.

### Frozen Pilot-v3 attempt and pause boundary

Pilot-v3 recognizes exactly one official disposition per invocation:
`success`, `failure`, `error`, `incomplete`, or `empty_patch`. Disposition and
corrective-feedback availability are separate. An initial `failure` with named
feedback permits the one frozen corrective round using only those names. An
initial `failure` with feedback unavailable remains a valid experimental
negative outcome and terminates without correction. `empty_patch` is an
experimental negative outcome. Coherent `error` and `incomplete` dispositions
are attempt-invalid evaluator/runtime infrastructure conditions; contradictory,
multiple, or structurally inconsistent identities are mandatory batch-stop
measurement failures.

Every Pilot-v3 cell permits at most two total attempts. Across the batch, at
most four provider/API or local Docker/runtime infrastructure reruns and at
most two separately counted external operator-interruption restarts may be
authorized. A cell can consume at most one restart of either category because
all categories share the two-attempt maximum. Exhaustion appends a durable
batch stop and preserves all evidence; capacity cannot be added after results.

Planned operator pauses occur only between cells before the next
`attempt_started` and consume no allowance. A mid-attempt operator interruption
must record its cause before outcome review, remain immutable, never be
relabeled as infrastructure, and—only when allowance remains—restart as the
next attempt in completely fresh isolation. Restart decisions cannot depend on
interim arm effects.

Before every scheduler transition, Pilot-v3 fsyncs a SHA-256 hash-chained record
covering attempt start, subject termination, evaluator invocation/exit,
official disposition, feedback availability, report identity, timestamps,
provider usage components, isolation identities, termination, receipt, and
admissibility. Restart state is reconstructed only from that durable evidence;
an in-memory cursor cannot determine completed cells.

### Post-terminal Pilot-v3 adapter-successor boundary

The original Pilot-v3 batch remains terminal and immutable. A separately
authorized, zero-live qualification established that its first-cell stop was an
outcome-independent adapter/schema incompatibility before the official
evaluator process launched. With zero admissible observations and no interim
arm comparison, one successor lineage may retain the exact original schedule
without new randomization: position 1 attempt 1 remains immutable exposure,
position 1 restarts only as attempt 2 in fresh isolation, and positions 2–32
retain their frozen identities and begin at attempt 1. No position 1 attempt 3
is permitted.

The successor uses a separate hash-chained ledger bound to the original
contract, pool, schedule, predecessor ledger and terminal event, and exact
adapter-repair identity. Completed successor cells cannot repeat after restart.
The four infrastructure and two operator allowances remain at their original
totals and zero consumed counts; creating the lineage neither consumes nor
resets either category and supplies no additional attempt capacity. Live
successor execution remains outside this protocol amendment's authority.

The externally interrupted Pilot-v2 exploratory run uses one separately frozen
continuation lineage. Its first six completed cells remain observations of the
same `pilot-v2.0` schedule and are not copied or rerun. Cell 7's incomplete
attempt 1 remains in the immutable original ledger; a continuation may restart
the whole cell in fresh isolation as attempt 2. That restart is recorded under
the distinct `operator_interruption_restart` category, consumes none of the
eight infrastructure-rerun units, and exhausts the one exceptional operator
restart unit. Cell 7 can never receive a third attempt. Cells 8-44 retain their
original identities, order, attempt-1 starts, and existing infrastructure rules.
This post-interruption amendment is exploratory only and is not a precedent for
an unplanned confirmatory amendment.

Before confirmatory execution, operator pause semantics must be frozen with the
other missingness rules. Planned pauses occur between cells before
`attempt_started`. A mid-attempt pause must retain the incomplete attempt, record
the cause before any outcome review, and may restart the identical cell only if
a separately counted operator-interruption allowance was fixed prospectively.
The restart uses the next attempt number and fresh isolation; all attempt
categories together permit at most two attempts per cell. Operator interruption
must never be relabeled as provider or Docker infrastructure, and exhausted
allowance stops the run in its preserved incomplete state. No restart decision
may depend on interim arm effects.

Never drop expensive/failed runs from cost calculations simply because their token/cost record is incomplete without reporting the missingness mechanism.

## 13. Benchmark leakage and gaming

- Select confirmatory tasks before policy freeze through a predeclared sampling mechanism where possible.
- Do not hand-pick tasks where development runs showed large wins.
- Keep hidden tests hidden from policy authors where practical.
- Detect edits to tests/lint/type/evaluator configuration.
- Record every experimental policy variant tried before confirmatory freeze.
- If confirmatory data are inspected and the policy changes, the old confirmatory run becomes exploratory.

## 14. Downstream-work hypothesis

A one-ticket benchmark cannot support a claim that the policy reduces future maintenance or later agent work.

Only if per-task evidence is promising, run a **task-chain sub-study**:

- several sequential tickets applied cumulatively to the same repository copy;
- compare total cost/work across the entire chain;
- evaluate final correctness and regression state.

This sub-study is required before claiming reduced downstream work, maintenance burden, or lifecycle cost.

## 15. Publication checklist

Before publishing a positive result verify:

- confirmatory pool was held out;
- policy/harness/analysis were frozen first;
- arm contamination canary passed;
- exclusions/timeouts followed frozen rules;
- quality guardrails were reported beside cost;
- uncertainty intervals are present;
- model/agent/date/task scope is attached to every headline number;
- subgroup results are not promoted over aggregate results without a predeclared interaction analysis;
- claim language complies with `EVIDENCE_POLICY.md`.

## 16. Evidence-Conditioned Final Scope Review v0.1 exploratory design

The exact treatment qualified under D-048 has one separately frozen
exploratory methodology. Its full human-readable and machine-readable
authorities are:

- `docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_EXPLORATORY_DESIGN.md`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json`.

This candidate uses baseline and exact treatment only, eight independent
repository/task clusters spanning the eight languages in the pinned source
frame, and two correlated repetitions per task-arm. The size is for bounded
harm, instability, discordance, and mechanism detection, not confirmatory
power. Pilot-v3 effect sizes and task details are not sizing or selection
inputs.

Selection is deferred. A separately authorized goal may carve eight
repository-distinct tasks from the current post-Pilot-v3 opaque reserve using
only the frozen metadata projection and SHA-256 rank, then recommit the
repository-disjoint remainder without exposing IDs or bodies. Actual task
selection, pool/schedule freeze, ledger creation, provider/evaluator use, and
execution are not authorized by this methodology.

Quality remains primary under intention-to-treat semantics. Work is reported
unconditionally and, separately, on jointly accepted matched repetitions as
conditional descriptive mechanism evidence. The accepted-outcome analysis
cannot hide failures or replace unconditional quality. Task-cluster bootstrap,
leave-one-task-out, incomplete-cluster handling, discordance, trajectory work,
and retirement gates are frozen in the machine specification. Retirement gates
are directional evidence rules rather than significance tests or numerical
non-inferiority margins.

This design does not amend Pilot-v3 history and does not freeze any
confirmatory arm, estimand, margin, sample size, pool, or execution plan.

## 17. Evidence-Conditioned Final Scope Review v0.1 exploratory allocation freeze

The separately authorized selection goal materialized the task/repository
partition and schedule already specified by section 16. Its authorities are:

- `docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_EXPLORATORY_FREEZE.md`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_freeze.json`.

The protected machine artifact binds the exact eight-task/eight-repository
exploratory allocation, the repository-disjoint 434-task/191-repository opaque
confirmatory remainder, and the exact counterbalanced 16-block/32-cell
schedule. Remaining reserve identities and all task bodies remain unpublished.

This partition and schedule are immutable under the current authority. No
replacement, reorder, ledger, provider/subject execution, experimental
evaluator execution, observation, confirmatory design, or efficacy inference
is authorized by the freeze.

## 18. Evidence-Conditioned Final Scope Review v0.1 execution preflight

The separately authorized live execution stopped before cell 1 because strict
preflight found no experiment-specific frozen execution contract or qualified
runner/preflight. The design and allocation do not bind an exact executable
model/runtime/evaluator/late-stage-delivery/receipt/ledger interface, and those
semantics cannot be invented after task freeze. The installed Codex version
also differs from the only prior frozen runtime identity.

The terminal receipt is
`experiment/evidence_conditioned_final_scope_review_v0_1_execution_preflight.json`.
It records zero ledger events, attempts, subject calls, evaluator calls, and
observations. This is a fail-closed readiness result, not experimental evidence.

## 19. Evidence-Conditioned Final Scope Review v0.1 execution interface

Fresh explicit authority qualified the previously missing experiment-specific
interface without changing the frozen treatment, design, pool, schedule,
reserve, retry, correction, analysis, or retirement rules. Both arms receive
the ordinary task first with no treatment exposure. Baseline receives no
intervention. Treatment receives the exact frozen bytes once through a same-
session resume after the ordinary turn has terminated successfully and before
prediction/evaluator construction. The activation checkpoint and phase-specific
traces make the boundary auditable.

The contract binds Codex `0.151.0`, `gpt-5.6-terra`/`medium`, the pinned
dataset/evaluator/RepoLaunch/Docker identities, the canonical Pilot-v3 attempt
timeout schema, fresh isolation, cleanup, ledger, receipt, analysis, and all
frozen budgets. Its 32-cell dry-run and 26-check fault-injection qualification
made zero subject calls, evaluator calls, observations, or ledgers.

Live execution remains gated on committed and squash-merged qualification,
green CI/CodeQL, synchronized clean `main`, a fresh tracked-HEAD strict
preflight, and the exact contract-derived confirmation. Qualification is
execution readiness only and provides no policy evidence.

## 20. Evidence-Conditioned Final Scope Review v0.1 terminal disposition

Those live gates passed and the exact authorized schedule ran to a legitimate
frozen `batch_stopped` boundary. The state machine preserved 24 admissible
cells and stopped after both permitted attempts for block 13 baseline were
infrastructure-invalid. Eight cells remain missing, no attempt 3 is permitted,
and no missing outcome is imputed.

The terminal analysis follows section 16's frozen order and rules. Its
authorities are:

- `docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_TERMINAL_ANALYSIS.md`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_terminal_result.json`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_terminal_analysis.json`;
- `experiment/evidence_conditioned_final_scope_review_v0_1_mechanism_annotations.json`.

Five prospective retirement gates fired: no accepted-outcome mechanism,
increased search, increased cached context, increased wall/work, and structural-
proxy-only benefit. Under the frozen any-gate rule, exact Evidence-Conditioned
Final Scope Review v0.1 is retired unchanged. The terminal partial schedule is
exploratory only and authorizes no repair, restart, treatment revision, further
exploratory iteration, or confirmatory work.
