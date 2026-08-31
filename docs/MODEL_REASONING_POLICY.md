# Development Model and Reasoning Policy

## Purpose

This policy governs **how Codex should be used to develop this repository**. It is not a V0 feature and must not be implemented as an end-user model router.

Model availability changes over time. Before relying on an exact model slug or reasoning level, inspect the current Codex environment. If a requested configuration is unavailable, use the closest available tier and record the substitution when it materially affects an experiment or decision.

## Current OpenAI guidance baseline (2026-08-27)

OpenAI currently positions the GPT-5.6 family as:

- **GPT-5.6 Sol** — frontier model for complex professional/coding work;
- **GPT-5.6 Terra** — balance of intelligence and cost;
- **GPT-5.6 Luna** — cost-sensitive/high-volume work.

GPT-5.6 supports `none`, `low`, `medium`, `high`, `xhigh`, and `max` reasoning effort. OpenAI recommends `medium` as a balanced starting point, `low` for efficient/latency-sensitive work, and higher efforts only where evaluations or task evidence justify the extra compute. `max` is for the hardest quality-first workloads, not a default fallback.

These are development defaults, not benchmark claims. Revalidate this section when model guidance changes.

Official references checked on 2026-08-27:

- OpenAI Model Guidance: https://developers.openai.com/api/docs/guides/latest-model
- OpenAI Models: https://developers.openai.com/api/docs/models

Model names exposed by the Codex product may differ from API availability. The installed Codex environment is authoritative for what can actually be selected during development.

## Core principle

Choose **model capability** and **reasoning effort** separately.

- Model answers: *How much base capability does this task need?*
- Reasoning effort answers: *How much deliberation does this particular attempt need?*

Do not equate “larger task” with “higher reasoning”. A large mechanical migration may need little reasoning; a five-line concurrency fix may need a lot.

## Default configuration

For ordinary implementation in this repository, prefer:

- **Model:** Terra-class balanced model when available.
- **Reasoning:** `medium`.

Use this default unless the task class below gives a clear reason to move.

## Task classes

### Class 1 — Mechanical / bounded

Examples:

- formatting;
- renaming;
- straightforward fixture creation;
- mechanical documentation edits;
- repetitive schema/data transformation with an established pattern;
- simple test additions once behavior is already specified;
- deterministic parsing/plumbing with clear acceptance criteria.

Preferred starting point:

- **Model:** Luna or Terra;
- **Reasoning:** `low` (or `medium` if tool use/branching is non-trivial).

Do not use high effort simply to increase confidence on work that deterministic tests can verify.

### Class 2 — Normal engineering

Examples:

- ordinary feature implementation;
- normal bug fixing;
- moderate refactoring;
- integration work;
- repository analysis with a bounded question;
- normal adapter/hook implementation.

Preferred starting point:

- **Model:** Terra;
- **Reasoning:** `medium`.

This is the default class.

### Class 3 — High-uncertainty / high-consequence reasoning

Examples:

- root-cause debugging after multiple credible failures;
- architecture decisions that are expensive to reverse;
- security-sensitive behavior;
- complex concurrency/state problems;
- evaluation/statistical methodology that affects public evidence claims;
- ambiguous cross-cutting refactors where a local mistake can invalidate many results;
- adversarial review of experimental validity.

Preferred starting point:

- **Model:** Sol;
- **Reasoning:** `medium` or `high` depending on difficulty.

Use `xhigh` only after evidence that `high` is insufficient or when the task clearly warrants a quality-first attempt. Reserve `max` for exceptional cases where marginal quality matters materially and there is a clear verification criterion.

## Escalation ladder after failure

Escalation should be **diagnostic**, not automatic.

### Step 0 — Read the failure

Before changing configuration, determine whether the failure is mechanical, informational, reasoning-related, capability-related, or a goal/hypothesis failure as defined in `docs/GOAL_PROTOCOL.md`.

### Step 1 — Same model, same effort

Use when the failure itself provides a clear deterministic fix or missing evidence.

Examples:

- compiler/test error points to a local defect;
- a required file was not read;
- fixture/environment setup is wrong.

### Step 2 — Same model, +1 reasoning level

Use when evidence is adequate but the reasoning failed.

Typical transitions:

- `low → medium`
- `medium → high`
- `high → xhigh`

Do not jump directly to `max`.

### Step 3 — Stronger model, reset effort sensibly

Use when failure suggests a capability ceiling or repeated reasoning attempts are not converging.

Typical transitions:

- Luna → Terra (`medium`)
- Terra → Sol (`medium`)

After switching to a stronger model, do not automatically inherit `high/xhigh` from the weaker model. Give the stronger model a balanced attempt first unless the task is already clearly Class 3.

### Step 4 — Stronger model + higher effort

Use only when:

- the stronger model at a balanced effort still fails for reasoning reasons; and
- the task is important enough that the additional compute is justified; and
- there is an objective way to evaluate the next attempt.

### Step 5 — Stop escalating

If two escalations do not improve the evidence or falsify the same hypothesis repeatedly, assume the problem may be the goal, missing information, tool capability, or approach—not insufficient intelligence.

Do not create an infinite “more compute” loop.

## De-escalation

After a difficult reasoning/architecture decision is resolved, return implementation work to the lowest configuration that can safely execute and verify the known plan.

Example:

1. Sol/high resolves a subtle experimental-design issue.
2. Terra/medium implements the agreed deterministic harness.
3. Luna/low may handle mechanical fixture generation if available and independently verifiable.

This prevents one hard subproblem from forcing the entire goal to run at maximum cost.

## Research and evidence work

For work that can affect public claims—benchmark design, statistics, causal interpretation, evidence wording—prefer Sol-class capability and at least `medium` reasoning. Increase to `high` when the decision is subtle or adversarial review materially reduces false-positive risk.

Do not use a cheaper model merely because the output is “only documentation” when the document determines experimental validity.

## Implementation and test work

Once a decision is frozen and the implementation is mechanical, use Terra/medium or lower where appropriate. Let deterministic tests provide confidence rather than paying for high reasoning by default.

## No silent model-policy claims

Do not claim that this routing policy is optimal. It is a development heuristic grounded in current model guidance and project risk.

If we later measure it, treat those measurements as a separate experiment from the product's bounded-engineering policy.

## If Codex cannot switch model/effort mid-task

Do not pretend it did.

When escalation is justified but runtime switching is unavailable:

1. stop the failing attempt at a clean boundary;
2. summarize the evidence already collected and failed hypotheses concisely;
3. state the recommended next model/effort;
4. resume in a new session/attempt with that configuration.

Avoid copying the entire previous transcript when a compact evidence summary is sufficient.
