# AGENTS.md

## Purpose

This repository investigates whether a **small bounded engineering policy** can reduce unnecessary coding-agent work without meaningfully degrading task outcomes.

The repository itself must not become an overengineered demonstration of the problem it studies.

## Authority order

When working in this repository, follow this order:

1. The user's explicit request in the current task.
2. This `AGENTS.md`.
3. `docs/PRODUCT_SCOPE.md`.
4. `docs/CURRENT_GOAL.md` for the active development outcome.
5. `docs/GOAL_PROTOCOL.md` for goal lifecycle rules.
6. `docs/MODEL_REASONING_POLICY.md` for development-time model/reasoning choices.
7. `docs/EVALUATION_PROTOCOL.md` for experimental work.
8. Existing repository conventions.

If these conflict materially, stop and surface the conflict rather than silently inventing a resolution.

## Non-negotiable scope constraints

Until the evidence gate in `docs/PRODUCT_SCOPE.md` is passed, do **not** add:

- a supervising LLM call per turn or per tool call;
- a network proxy;
- background/cloud telemetry;
- user accounts, authentication, billing, dashboards, databases, queues, or services;
- multi-agent or multi-IDE support;
- automatic repository-wide deletion/refactoring;
- model routing or adaptive reasoning **as an end-user product feature**; development-time model/reasoning selection is governed separately by `docs/MODEL_REASONING_POLICY.md`;
- a custom replacement for existing static-analysis tools;
- enterprise/security/compliance infrastructure beyond what this local OSS prototype actually needs.

Do not add a dependency unless the current requirement cannot reasonably be met with the standard library or code already in the repository. If a dependency is necessary, state why in the change summary.

## Engineering style

- Implement what the current requirement needs; do not design for hypothetical future requirements.
- Prefer a small coherent module over a framework or abstraction hierarchy.
- Prefer deterministic analysis over LLM judgment where the signal is mechanical.
- Do not treat fewer LOC/files/dependencies as an objective by themselves.
- Do not weaken tests, lint rules, type checking, security checks, or evaluation criteria to make a result look better.
- Do not silently alter benchmark definitions, exclusions, outcomes, statistical rules, or public claim wording after seeing results.
- Never call exploratory results confirmatory.

## Goal discipline

Work on exactly one active goal from `docs/CURRENT_GOAL.md`. Follow `docs/GOAL_PROTOCOL.md`. Do not invent adjacent goals or continue polishing after the current goal's evidence and stop conditions are satisfied.

On a goal terminal state, update the machine-readable handoff defined by
`docs/AGENT_HANDOFF_PROTOCOL.md`. It summarizes durable state for external
review and does not authorize adjacent work by itself.

A public repository should be safe, understandable, testable, and contributor-friendly, but it is not automatically a production service. Do not add production infrastructure or enterprise hardening unless the current goal explicitly requires it.

## Development-time model and reasoning

Follow `docs/MODEL_REASONING_POLICY.md`. Default ordinary implementation to a balanced model/reasoning configuration; escalate only after classifying a failure.

A failed command or test is not by itself a reason to increase reasoning or switch models. Increase reasoning when adequate evidence exists but reasoning is not converging; switch to a stronger model when there is evidence of a capability ceiling or the decision is materially high-risk. De-escalate after the hard reasoning step is resolved.

## Repository maps

When `graphify-out/graph.json` exists, check its freshness before relying on it.
After an in-scope structural change makes that index stale, run Graphify's
incremental update and verify the resulting graph. Do not create a new Graphify
index solely for compliance when the repository does not already have one.

## Experimental integrity

Changes that affect any of the following require an explicit update to the matching document and rationale in `docs/DECISIONS.md`:

- candidate policy wording;
- experimental arms;
- task inclusion/exclusion rules;
- primary outcomes or quality guardrails;
- timeout/failure handling;
- analysis method;
- public evidence/claims policy.

Once a confirmatory experiment is frozen, do not edit the frozen artifacts. A post-result change creates a new experiment version and requires a new held-out set.

## V0 implementation target

Build only the **Shadow Scope Analyzer** described in `docs/PRODUCT_SCOPE.md` unless the user explicitly expands scope.

The analyzer should:

- be local-first;
- observe Codex lifecycle/transcript/repository changes using supported interfaces;
- tolerate missing hook events and fail visibly rather than silently claiming coverage;
- record deterministic facts, not semantic conclusions;
- write local machine-readable events and a human-readable report;
- make no network calls;
- make no automatic repository modifications;
- add effectively no latency to the Codex execution path.

Examples of deterministic facts:

- added/deleted/modified file counts;
- added/deleted LOC;
- manifest dependency additions/removals;
- test-file changes;
- `AGENTS.md`/instruction-file size delta;
- introduction of obvious new infrastructure/config artifacts;
- commands/tests executed when reliably observable.

Use language such as **“scope-budget signal”**, **“structural delta”**, or **“candidate review event”**. Do not label a change “overengineered” as an objective fact.

## Codex hook caution

Codex hook behavior is evolving. Do not assume all tool paths emit symmetric events or expose the same failure metadata. Any integration must:

- verify behavior against the exact Codex version used;
- include a small integration/canary test;
- surface degraded coverage to the user;
- avoid making correctness depend on an event that is known to be inconsistently emitted.

## Testing

For implementation changes:

- add tests for deterministic parsing/measurement logic;
- use fixture transcripts/repositories rather than live network calls where possible;
- test malformed/missing hook payloads;
- test that telemetry/network activity is absent in V0;
- test that shadow mode never modifies the target repository.

## Documentation discipline

Keep this file short. Do not add procedures or research discussion here. Put detailed material under `docs/` and link to it.

If this file approaches ~200 lines, treat that as a design smell and move detail to scoped documentation.
