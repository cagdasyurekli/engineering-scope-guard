# Exploratory Pilot Readiness v0.1

**Status:** complete readiness design; Pilot not authorized

> **Historical disposition:** The 2026-08-27 zero-supply/evaluator NO-GO below
> remains the evidence available at that decision. Later source, runtime, and
> host-qualification goals superseded those specific gate facts. The current
> joint decision is in `docs/PILOT_EXECUTION_READINESS_DECISION.md`; Pilot still
> remains unauthorized.

## Decision this document supports

Can a bounded Exploratory Pilot produce interpretable feasibility and
task-clustered variance information without contaminating future confirmatory
evidence?

The Pilot would not prove that a policy works. It would test whether the study
can be operated and measured well enough to justify a later freeze decision.

## What the Pilot would learn

### Feasibility

- whether an opaque, eligible task supply can be obtained without hand-picking;
- whether paired cells start independently and retain complete run evidence;
- whether deterministic acceptance and safety checks are informative rather
  than almost always passing or failing;
- how often agent, timeout, provider, harness, isolation, and measurement
  failures occur under frozen rules;
- whether a single standardized corrective round can be operated identically.

### Variance and measurement

- between-task variation in acceptance, token/cost components, and mechanisms;
- within-task seed-to-seed variation;
- acceptance discordance and task-by-arm heterogeneity;
- timeout, high-tail, cache, billing, and missingness behavior;
- whether task-level resampling could support a later confirmatory design.

### Exploratory policy effect

The Pilot may describe the task-level distribution of differences between
default Codex and C-short v0.1. Every such estimate remains exploratory. It may
not be used to claim savings, preserved quality, improved code, fewer retries,
or product efficacy, and it may not determine a convenient confirmatory MCID or
quality margin.

## Minimum interpretable arms

| Arm | Definition | Scientific role |
| --- | --- | --- |
| `baseline` | Default Codex task execution with no injected policy bytes | Counterfactual for adding the surviving bounded instruction |
| `short` | Exact C-short v0.1 bytes in `experiment/arms/short.txt` | Treatment under evaluation |

C-short is no longer a dose control for a surviving fuller policy; it is the
treatment. D v0.1 remains a negative development variant. Development found no
acceptance advantage for D v0.1 over C-short and higher aggregate diagnostics,
so no current research question justifies spending Pilot runs on it. A third arm
would be reconsidered only after a new policy candidate and a distinct,
predeclared question exist; symmetry is not a reason.

This two-arm decision does not freeze the future confirmatory arm design.

## Sampling frame and task custody

### Eligible sources

The initial frame is deliberately narrow: small, locally runnable Python task
snapshots from redistributable public repositories or independently authored
fixture repositories held by a custodian. Each entry must have:

- a stable opaque ID and immutable source-snapshot hash;
- a task statement, independently executable hidden requirement checks, and a
  pre-task repository state;
- local execution with no credentials, network, external services, or package
  installation during the agent run;
- a supported Python 3.11+ environment using only already-present project tools;
- deterministic existing regression commands and any applicable lint/type/build
  commands;
- a recorded license/authorization basis for local use and evidence retention;
- an independently assigned stratum before allocation;
- no known use in policy wording, development tasks, harness fixtures, or prior
  Scope Guard results.

### Exclusions

Exclude and retain the reason for any entry that:

- appeared in the four development packets or policy/harness construction;
- lacks a reproducible pre-task snapshot or external acceptance checks;
- requires network, secrets, proprietary access, or unresolved human judgment;
- has nondeterministic or consistently failing setup/regression checks;
- can pass without implementing the stated requirement;
- requires weakening tests, lint, type, build, or evaluator configuration;
- cannot finish within the frozen resource envelope in a pre-policy setup check;
- overlaps another task's repository state or depends on another sampled task.

Exclusions occur before task allocation and never use observed arm performance.

### Strata

Retain four mechanism strata because they answer different failure and quality
questions already identified before Pilot:

1. over-build-prone;
2. irreducible implementation;
3. seeded guard retention;
4. seeded shared-root-cause repair.

The custodian assigns strata from task materials. The policy author receives
only opaque IDs and aggregate counts until Pilot allocation is frozen.

### Opaque partition

Before the policy author sees any Pilot body, an independent custodian or an
equivalent inaccessible store must freeze eligibility rules, metadata, opaque
IDs, inventory hash, exclusions, and this public seed:

`engineering-scope-guard-pilot-v0.1-2026-08-27`

Within each stratum, rank IDs by SHA-256 over the UTF-8 seed, one NUL byte, and
the opaque ID. Allocate the first three eligible IDs to Pilot and retain at least
the next three unseen for confirmatory planning. Additional IDs remain unseen.
Replacement uses the next ranked eligible ID from the same stratum and retains
the excluded/replaced record. Confirmatory task bodies remain outside the policy
author's accessible state.

This requires a minimum opaque inventory of 24 distinct tasks: 12 Pilot and 12
still-unseen tasks. The latter is a disjointness reserve, not a confirmatory
sample-size decision; confirmatory analysis may require more.

### Current supply

Current confirmed eligible supply is **0 distinct tasks**. The repository has no
opaque catalog, frozen inventory hash, custodian, or inaccessible confirmatory
store. The four visible development tasks are permanently ineligible. Repeated
seeds do not increase distinct-task supply.

## Contingent run budget

If all readiness gates later pass, the smallest proposed budget is:

| Resource | Count |
| --- | ---: |
| Distinct Pilot tasks | 12 |
| Arms | 2 |
| Repetitions per task/arm | 2 |
| Planned task trajectories | 48 |
| Infrastructure-only replacement reserve | 8 |
| Absolute trajectory ceiling | 56 |
| Maximum turns per planned trajectory | 2 |
| Maximum planned agent turns | 96 |

Three distinct tasks per stratum prevent any stratum from being a single-task
anecdote while keeping the Pilot bounded. This is a feasibility/variance budget,
not a power calculation; stratum effects and high quantiles will remain crude.
The eight-run reserve can replace four complete task-by-seed two-arm blocks or
two complete four-run tasks. It cannot replace agent failure, policy-induced
timeout, failed acceptance, expensive output, or inconvenient missingness.

No monetary budget is estimated because exact run-level billing is currently
unavailable. Run count and distinct-task supply remain binding.

## Isolation and contamination protocol

### Cell start

For each task, arm, and seed:

1. unpack the registered source snapshot into a fresh directory and verify its
   content hash before any agent process;
2. initialize the same local Git baseline and confirm byte-identical snapshots
   across arms;
3. create a unique `CODEX_HOME`, repository, raw-output, derived-output, and
   temporary directory outside every other cell;
4. populate `CODEX_HOME` with only the required authentication reference; do not
   load user configuration or rules;
5. use an allowlisted environment and record executable/tool versions rather
   than copying an uncontrolled user shell environment;
6. record exact policy bytes, prompt hash, task/evaluator hashes, subject command,
   feature receipt, and cell-root receipt before execution.

No MCP server, plugin, skill, goal, memory, or hook configuration is loaded into
an experimental cell. The V0 analyzer observes from outside the repository.

### Order and drift

Use the frozen seed to randomize task order and arm order, but keep both arms for
one task/seed adjacent in time. Rank task-and-repetition blocks by SHA-256 over
the partition seed, a NUL byte, opaque task ID, a NUL byte, and repetition ID.
Within that order, alternate baseline-first and short-first; select the first
block's starting arm from the low bit of SHA-256 over the seed, a NUL byte, and
`arm-order`. Record wall-clock start/end, Codex version, model identifier,
reasoning, command/config hashes, and feature receipt per cell. Stop the batch on
version/model/config drift. Runs from different configurations are separate
experimental versions and are not pooled.

### Prompt and provider cache

Use separate provider cache namespaces per cell if the provider exposes a
supported mechanism. Do not add prompt nonces merely to defeat caching because
that changes the intervention. Always record cached and uncached token components
and exact provider billing when supplied.

The current environment does not prove cache-namespace separation and supplied
no run-level billing in development. If that remains true, behavioral and token
measurements may still be retained, but billed-cost comparison is unavailable;
cache-price differences cannot be described as reduced agent work.

### Contamination

A run is contaminated if any of these occur:

- repository start hash or evaluator hash differs from the registry;
- policy bytes/hash are wrong or baseline receives intervention bytes;
- Codex/model/reasoning/permission/tool/config receipt differs from the frozen
  subject manifest;
- cell state, output, temporary, or session paths overlap another cell;
- unexpected MCP, plugin, hook, user-config, rule, skill, memory, or goal state is
  loaded;
- cross-cell files, thread/session identifiers, corrective feedback, or task
  material appear in the wrong cell;
- the source snapshot is modified before the agent starts;
- a canary or receipt is absent, malformed, or fails.

Retain the contaminated observation but exclude it from policy estimates. Invalidate
and rerun the complete task-by-seed matched two-arm block only after the cause is
fixed, consuming the infrastructure reserve. A systemic or unknown contamination
invalidates every run since the last passing batch canary. Cache-price ambiguity
alone marks billed cost unavailable rather than silently invalidating behavioral
outcomes; evidence of prompt/state leakage is contamination.

## Fixed subject configuration

The proposed Pilot subject configuration is:

- Codex CLI `0.150.1`, reverified immediately before the batch;
- model `gpt-5.6-terra`, reasoning `medium`, identical in every arm;
- automatic approval review with the workspace-write sandbox and no additional
  writable directory;
- no task-required network, MCP, plugins, hooks, user config, or user rules;
- only repository shell/exec and repository file-edit/apply-patch tools; no web,
  browser, connector, computer-use, image, or multi-agent tools;
- exactly the frozen built-in tool/feature receipt available to both arms;
- at most two turns: initial attempt plus one corrective round;
- 900 seconds per turn and 1,800 seconds per trajectory;
- on initial hidden-check failure, return only the predeclared failing check
  names once, identically across arms; retain the first failure and stop after
  the second evaluation.

Cell sessions must persist only within one trajectory when the corrective turn
is needed; no state is resumed across tasks, arms, or seeds. The development-time
model/reasoning escalation policy never applies inside an experimental run. A
failed cell is not rerun with a stronger model or higher reasoning.

The exact provider model-version identifier is unavailable, and the current
harness does not yet enforce the allowlisted environment, required tool
allowlist, frozen tool receipt, or corrective round. These are failed readiness
gates, not values to infer.

## Failure, rerun, and missingness rules

| Class | Definition | Treatment |
| --- | --- | --- |
| Agent/task failure | Provider reached; agent exits/fails, violates a guard, or remains unaccepted | Retain as arm outcome; no free rerun |
| Timeout | Frozen per-turn or trajectory limit reached | Retain as arm outcome, including observed cost; no free rerun |
| Harness failure | Runner/evaluator defect demonstrably independent of treatment | Retain, invalidate matched block, fix transparently, and use reserve |
| Provider/API failure | Authentication/service/transport failure unrelated to treatment | Retain, invalidate matched block, and use reserve under the same rule |
| Isolation failure | Any contamination condition above | Retain, invalidate matched block or affected batch, fix, and use reserve |
| Malformed/missing measurement | Required record absent or invalid | Retain missingness explicitly; do not impute zero or drop the run |

Provider failure after meaningful agent work is not automatically infrastructure
failure. Classification uses the frozen event boundary and must be made without
looking at whether the arm result is favorable.

Retain every planned attempt, invalidated run, replacement link, exclusion,
failure, and procedural deviation in the session ledger. If C-short wording is
changed after Pilot outcomes are inspected, assign a new exploratory policy
version, keep the earlier version's evidence, and never combine their effect
estimates. Such a change does not start or repair confirmatory evidence.

## Quality evaluation and reviewer boundary

Confirmed independent experienced-reviewer capacity is **zero**: there is no
roster, commitment, calibration, or completed blinded-review evidence. An LLM
judge is not a substitute.

Each eligible task must instead provide high-information deterministic evidence:

- hidden requirement checks stored outside the agent repository;
- existing unrelated regression tests;
- existing lint/type/build commands where the repository already uses them;
- before/after detection of evaluator, test, lint, type, and build configuration;
- exact guard-retention checks in the seeded-guard stratum;
- exact cross-call-site checks in the shared-root-cause stratum.

With zero reviewers, the Pilot may report exact automated acceptance, guardrail,
and configuration-protection outcomes. It cannot support claims about broad code
quality, maintainability, proportionality, aesthetics, quality preservation, or
non-inferiority. One reviewer would permit only bounded qualitative case notes.
Two or more hypothesis-blind experienced reviewers with a frozen rubric,
randomized presentation, arm-guess manipulation check, and reported agreement
would permit bounded human-review findings, but would not repair weak sampling.

## Measurements and analysis

Primary feasibility measures are completion/failure class, automated acceptance,
acceptance discordance, ceiling/floor behavior, timeout, corrective-round use,
isolation/harness failure, and field-level measurement completeness. Record
provider billing and input, cached-input, output, reasoning-output, and total
tokens only when supplied.

Secondary mechanism measures are turns, tool calls, verification commands,
failed-verification loops, post-verification edits, and reliably observed
read/search activity. LOC, files, dependencies, tests, complexity, and other V0
structural deltas are diagnostics only.

Pair arms within task and seed. Report task-level distributions, arithmetic mean,
median, supported high-tail summaries, raw discordant pairs, between-task
variation, within-task/seed variation, and task-by-arm heterogeneity. Resample
distinct tasks, preserving all repetitions and arms within each task cluster.
Twelve tasks provide unstable exploratory intervals; do not present them as
confirmatory precision or treat 24 repeated observations as 24 independent tasks.
Do not select the most favorable statistic after seeing outcomes.

## MCID and quality margin

The Pilot requires neither an efficacy MCID nor a quality non-inferiority margin.
Both remain unresolved.

Before confirmatory execution, the project must make substantive judgments about
the smallest efficiency benefit worth the instruction's prompt/maintenance cost
and the largest quality degradation acceptable for each task-risk class. Pilot
variance, baseline acceptance, discordance, task supply, and attainable interval
width are statistical inputs; they do not determine what users should value or
what harm is acceptable. Freeze any MCID, margin, estimand, and analysis before
confirmatory results are seen. Never choose 15%, 5%, 3 percentage points, or any
other value merely because it produces a convenient sample size.

## Decision rule

- Recommend Pilot execution only when at least 24 eligible opaque tasks and a
  custodian/partition exist; the 12 allocated Pilot tasks have informative
  deterministic evaluators; the two-arm subject configuration and local/live
  canaries pass; cache/billing limitations are compatible with the intended
  measures; and the 48+8 run budget is authorized and feasible.
- Require redesign when a remediable harness, evaluator, cache, allocation, or
  budget defect prevents interpretation. Narrow the hypothesis rather than
  pretending broad evidence if only a defensible subset of strata or outcomes is
  available.
- Stop the experiment when adequate distinct-task supply, credible isolation, or
  meaningful quality evaluation cannot realistically be obtained, or when the
  only feasible evidence cannot answer a substantively useful question.

## Current gate disposition

| Gate | Status | Evidence |
| --- | --- | --- |
| Interpretable arms | Pass | baseline versus C-short v0.1; D v0.1 excluded |
| Adequate task supply | Fail | 0 confirmed eligible tasks; 24 minimum opaque inventory |
| Opaque partition/custody | Fail | no custodian, inventory hash, or inaccessible task store |
| Local process-envelope isolation | Pass | two byte-identical two-arm canaries |
| Live subject/tool/config receipt | Fail | not run or implemented for the proposed trajectory |
| Provider cache/billing interpretation | Fail | cache isolation unproved; billing unavailable in development |
| Task-specific quality evaluators | Fail | no eligible Pilot task packets exist |
| Reviewer capacity for broad claims | Fail | zero confirmed reviewers |
| Run budget | Contingent | 48 planned + 8 reserve; not authorized without task supply |

## Bounded conclusion

**NO-GO**

The two-arm design and local envelope are interpretable, but the project has zero
eligible opaque tasks, no custodian or disjoint partition, no task-specific Pilot
evaluators, no live subject/tool/config receipt, and no provider cache or billing
interpretability. Do not create or run Pilot cells. Reassess only after those
failed gates have new evidence; do not start Freeze or confirmatory work.
