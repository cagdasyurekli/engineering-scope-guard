# Product Scope v0.1

> **2026-08-29 status:** V0 remains an implemented local shadow measurement
> capability. The former bounded-policy V1 path did not pass the evidence gate:
> D v0.1 was rejected, and both C-short v0.1 and Evidence-Conditioned Final
> Scope Review v0.1 were retired. No new intervention is authorized. The
> current research-only-plus-shadow direction and future falsification gates
> are recorded in `PROJECT_THESIS_REASSESSMENT.md` and `RESEARCH_ROADMAP.md`.

**Status:** V0 implemented — evidence collection

## Problem statement

Coding agents can produce engineering work that is disproportionate to the user's actual requirement or project context. Observable symptoms may include unnecessary abstractions, dependencies, infrastructure, repository growth, stale instruction context, repeated verification loops, or excessive exploration.

This project does **not** assume those symptoms can be reliably classified as “overengineering” from a single heuristic. The initial task is to determine whether useful, high-precision signals exist.

## V0: Shadow Scope Analyzer

### Goal

Measure structural changes caused by Codex without changing Codex behavior.

### Inputs

- exact Codex version and mode;
- repository state before/after a task or observable turn boundary;
- supported Codex hook/transcript data where available;
- local project configuration for the analyzer itself.

### Outputs

1. Local machine-readable event log.
2. Local human-readable shadow report.
3. Coverage/health information explaining which signals were and were not observed.

### Candidate measurements

These are facts, not value judgments:

- files added/deleted/modified;
- LOC added/deleted;
- runtime/dev dependency changes by manifest;
- test-file additions/deletions/modifications;
- instruction/context-file size changes;
- creation of obvious infrastructure/configuration artifacts;
- verification commands, failures, and follow-up edits when the hook/transcript exposes them reliably;
- repeated read/search patterns where observable without semantic inference.

### Candidate scope-budget events

V0 may flag an event for **manual review** when a deterministic threshold/rule is crossed, but it must not describe the event as objectively bad. Examples:

- a small task produces a large structural delta;
- a task adds multiple runtime dependencies;
- an instruction file grows substantially;
- a temporary-looking artifact introduced during the task remains at the end;
- an edited manifest adds a dependency that is not referenced in the resulting tree (only where reliable language tooling supports this).

The first rules should be few and auditable. Precision matters more than coverage.

## V0 non-goals

- No prompt or policy injection.
- No blocking or rewriting tool calls.
- No automatic cleanup.
- No second LLM.
- No user-expertise inference.
- No project-intent profile.
- No community telemetry.
- No cross-agent support.
- No “AI vs software” semantic router.
- No stale-test classifier.
- No full repository-maintenance system.

## Evidence gate to V1

V1 interventions are justified only if V0/shadow review reveals repeatable, actionable signals and a controlled policy experiment demonstrates a meaningful benefit worth the intervention's cost/risk.

There is deliberately no fixed universal threshold such as “90% precision” in this document. Thresholds depend on intervention severity and will be predeclared for the specific experiment rather than chosen after seeing the outcome.

## Historical V1 candidate (not authorized; evidence gate not passed)

This section preserves the original candidate path. Current evidence does not
justify advancing it. A future materially different capability would require a
new thesis decision and separate authorization rather than silently reopening
this path.

The historical V1 candidate would have tested:

- bounded policy injection;
- a one-sentence semantic control;
- task-boundary review events;
- local randomized holdouts for eligible interventions.

Any such functionality must be evaluated under `EVALUATION_PROTOCOL.md` before being described as beneficial.
