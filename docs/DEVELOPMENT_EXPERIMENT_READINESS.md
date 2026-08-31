# Development Experiment Readiness v0.1

**Status:** readiness definition; no experiment has run

## Decision this document supports

Can the project run a small development-pool policy experiment without exposing
future confirmatory tasks, mixing interventions between arms, or turning missing
run evidence into misleading zeros?

This is not a decision about whether either policy works. Development results
are ineligible for efficacy claims.

## Task sampling frame

Future pilot and confirmatory task supply must come from an opaque task catalog
created before policy authors inspect task text, patches, or hidden tests. The
catalog protocol is predeclared here; no future confirmatory task is selected in
this readiness goal.

An eligible catalog entry must have:

- a stable opaque task ID;
- a redistributable or locally usable repository snapshot with a content hash;
- a task statement and independently executable acceptance checks;
- a local setup that does not require network access during the agent run;
- a declared language/toolchain already supported by the task repository;
- an independently assigned mechanism stratum and exclusion reason, if any;
- no known appearance in policy development, prompt design, or harness fixtures.

Before any task text is revealed to the policy author, a catalog custodian must:

1. freeze the eligibility rules, catalog hash, opaque IDs, and metadata;
2. freeze a deterministic partition algorithm and public seed;
3. assign disjoint pilot and confirmatory IDs using only the frozen opaque
   inventory, seed, and predeclared strata—not observed policy performance;
4. retain future confirmatory task text, patches, and tests outside the policy
   author's accessible development state;
5. record every exclusion and replacement against the frozen rule.

If no independent custodian or equivalent access boundary exists, confirmatory
work is **NO-GO**. Repetition of a few visible tasks does not repair task-supply
or leakage problems.

### Development pool

The initial development pool contains four prospectively authored synthetic or
fixture-backed tasks, one intended to exercise each current mechanism candidate:

1. reuse/native-option search;
2. genuinely irreducible implementation;
3. retention of a seeded validation/security/data-loss/accessibility guard;
4. repair of a shared cause rather than one visible symptom.

These are coverage cases, not a random sample. They are permanently excluded
from pilot and confirmatory pools, and their results may be inspected freely for
harness/policy debugging. Their exact packets may be authored only after this
rule is committed, and they must be registered with IDs and repository hashes
before their first agent run. This goal does not author or run them.

No task from the future opaque catalog is needed to build this development pool.

## Exactly three initial arms

| Arm | Intervention source | Interpretation |
| --- | --- | --- |
| `baseline` | no intervention file | default agent/harness behavior |
| `short` | `experiment/arms/short.txt` | current short semantically equivalent bounded-policy control |
| `full` | `experiment/arms/full.txt` | current full candidate bounded policy |

There is no generic best-practices arm, project-intent arm, model-routing arm, or
fourth control. Tests require the two files to match the current quoted text in
`docs/CANDIDATE_POLICY.md`. Baseline is represented by absence, not an empty
instruction that a runner might treat differently.

The assets are development bytes, not a claim that either intervention is good.
Any wording change creates a new development policy version and must be recorded;
it does not authorize extra arms or make earlier development runs confirmatory.

## Minimal harness boundary

`scripts/development_experiment.py` has three operations:

- `prepare` copies one source tree into exactly three cells while excluding the
  same cache/state directories V0 excludes, places interventions outside the
  repository, and creates distinct `codex-home`, `raw`, and `derived` roots;
- `canary` verifies equal V0 snapshot fingerprints, source immutability, distinct
  roots, arm-specific sentinels, exact intervention bytes, and fixed local child
  process receipts for per-cell working directory, `CODEX_HOME`, and policy hash;
- `record` normalizes evidence supplied by a separately authorized run.

`record` writes the normalized record only to its required `--output` path; it
does not duplicate billing or other record data to stdout. The preparation and
canary operations continue to emit their non-sensitive JSON receipts to stdout.

The helper does **not** invoke Codex, enforce a normal-work policy, select tasks,
run verifiers, compute effect estimates, randomize a benchmark, or contact a
network. A future runner must set each process's `CODEX_HOME`, working directory,
stdout/stderr destination, and intervention from that cell's manifest. Before
every agent batch it must also record the exact Codex/model/reasoning/config and
run an equivalent isolation receipt canary. The current synthetic canary proves
the local process-envelope boundary; it does not prove provider cache isolation
or claim that an unexecuted Codex process honored configuration.

Example non-provider canary:

```bash
PYTHONPATH=src python3 scripts/development_experiment.py canary \
  --source tests/fixtures/demo_before \
  --policies-dir experiment/arms \
  --state-dir /private/tmp/esg-readiness-canary
```

## Deterministic run capture

The run record contains:

- task, run, and arm identity;
- wall time in integer milliseconds, timeout boolean, and process exit code;
- completed and failed turns from the primary Codex exec JSONL parser;
- non-negative numeric usage components when present: input, cached input,
  output, reasoning output, and total tokens;
- optional provider billing components as exact decimal strings and currency, or
  an explicit `unavailable` status when no provider billing record exists;
- named verification kind, exit code, and derived pass/fail result;
- the existing privacy-bounded V0 event records, unchanged.

The recorder does not infer billed cost from tokens or prices. It does not treat
missing components as zero. Raw traces may contain sensitive prompts, code,
commands, and output and must remain local under the matching cell's raw root.

## Development run budget

The development ceiling is **four tasks and 30 agent sessions**:

- planned cells: `4 tasks × 3 arms × 2 independent runs = 24` agent sessions;
- infrastructure-only replacement reserve: at most `6` additional sessions;
- synthetic preparation/isolation canaries do not invoke an agent and therefore
  are not agent sessions.

Use two waves of two previously unused development tasks (12 planned sessions
per wave). Wording or harness changes may occur between waves; each version must
be recorded and interpreted separately. A task/arm result may be replaced only
for a predeclared provider, permission, or harness failure that is demonstrably
independent of the arm. Preserve the original record and link the replacement.
Agent failure, policy-induced timeout, failed verification, or expensive output
is a result, not infrastructure justification for a free rerun.

The ceiling is sized to exercise all four intended mechanisms twice under all
three arms and leave one complete six-session task cell of infrastructure
reserve. It is a debugging budget, not a power calculation and cannot support
an efficacy or quality-preservation claim. A new budget requires a new goal or
explicit user authorization; it must not expand automatically after results.

Each development wave must freeze its own equal-across-arm timeout, max-turn,
tool/permission, failure, and replacement rules before its first run. Exact
values remain unresolved because this readiness goal runs no agent task and has
no empirical basis to choose them.

## Independent reviewer capacity and claim boundary

As of 2026-08-27, the repository contains no reviewer roster, commitment, blind
review protocol assignment, or completed calibration evidence. The confirmed
capacity is therefore **zero independent experienced reviewers**. This means
"none confirmed," not proof that no suitable person exists.

With zero confirmed reviewers:

- development runs may debug task acceptance and deterministic guardrails;
- reports may state exact test/static-check outcomes and V0 structural facts;
- reports may not claim maintainability, code quality, proportionality,
  equivalence, non-inferiority, or preserved quality beyond those exact gates.

One reviewer could provide a bounded qualitative case review but not independent
agreement or a reliable broad quality claim. At least two experienced,
hypothesis-blind reviewers with frozen rubrics, randomized presentation,
arm-guess checks, and reported agreement/disagreement would permit bounded
human-review findings. It would still not repair weak sampling, low task supply,
or an unjustified statistical margin.

## Confirmatory freeze register

The following remain unresolved and must be frozen before future confirmatory
task text or results are inspected:

- catalog custodian/access boundary, eligibility rules, inventory hash, opaque
  task IDs, strata, partition algorithm/seed, exclusions, and replacement rule;
- exact task statements, repository snapshots, hidden tests, and evaluator
  configuration protections;
- exact policy/control bytes and hashes, arm labels, delivery mechanism, and
  manipulation/isolation canary;
- Codex product/version, model/version, reasoning, sampling controls actually
  available, global config, plugins/MCP, permissions, and cache-isolation plan;
- task timeout, max turns, corrective rounds, agent versus infrastructure
  failure definitions, intention-to-treat rule, reruns, missingness, and
  sensitivity analyses;
- acceptance procedure, quality guardrails, reviewer eligibility/blinding/rubric,
  and treatment of reviewer disagreement;
- primary economic estimand/statistic, secondary outcomes, clustering/unit of
  analysis, interval/bootstrap method, hypothesis order, multiplicity handling,
  and analysis code/hash;
- a substantively justified MCID for each intervention whose maintenance burden
  differs, or an explicit decision to report intervals without an MCID claim;
- a substantively justified quality non-inferiority/equivalence margin and
  feasible design, or an explicit decision not to make that claim;
- pilot-based variance, baseline acceptance, arm discordance, task supply,
  confirmatory tasks/runs, public claim wording, disclosure, and freeze record.

The numbers `15%`, `5%`, and `3 percentage points` are not decisions. They remain
unresolved examples unless justified from user value, intervention cost, task
risk, baseline success, and feasible uncertainty without reference to observed
confirmatory effects.

## Readiness gates

Development experiments are **GO** only if:

- exact three-arm assets reconcile with the candidate document;
- the synthetic isolation canary passes twice with byte-identical reports;
- focused and full tests plus warning-clean compilation pass;
- run capture distinguishes available, unavailable, failed, and timed-out state;
- the four-task packets are registered before their first agent run;
- each wave freezes equal rules and stays within the 30-session ceiling.

This GO would authorize only the four-task development pool. Pilot and
confirmatory work remain separate NO-GO decisions until their own unresolved
gates are satisfied.

## Current evidence and decision

The dated evidence record is
`docs/evidence/development-experiment-readiness-2026-08-27.md`.

**GO to run development-pool experiments only**, after the four permanently
non-efficacy task packets and equal per-wave rules are registered. **NO-GO for
pilot or confirmatory evaluation** until the listed task-supply, reviewer, margin,
analysis, and freeze requirements are satisfied.

No experiment ran in reaching this decision. It supports readiness, not policy
efficacy.
