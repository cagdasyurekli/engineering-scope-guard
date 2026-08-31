# Engineering Scope Guard

> **Working title.** This repository starts as an experiment, not a claim that a product is already justified.

Engineering Scope Guard now investigates a broader but still falsifiable
question:

> Can people get better accepted outcomes from coding agents with less
> unnecessary agent work, fewer preventable repetitions and corrections, and
> better-calibrated use of context, tools, models, verification, and agent
> capabilities?

The project is deliberately **not** a generic token optimizer, a second coding agent, or a synchronous AI supervisor. The first goal is to measure the hypothesis honestly and cheaply. If the hypothesis fails, the project should say so and stop or narrow its scope.

## Current status

**Research program reframed; V0 Shadow Scope Analyzer retained; no new
capability experiment is authorized.**

D v0.1 remains rejected. C-short v0.1 and the materially different
Evidence-Conditioned Final Scope Review v0.1 are both retired unchanged. The
first had an adverse quality signal without work reduction. The second avoided
the frozen adverse-acceptance gate but established no accepted-outcome
unnecessary-work mechanism and increased search, cached context, and wall/work;
five prospectively frozen retirement gates fired. No third prompt treatment or
confirmatory scope-policy experiment is recommended.

The current evidence supports an evidence-first research repository plus the
existing local shadow measurement capability—not a validated auditor or active
optimizer. See the
[`project thesis reassessment`](docs/PROJECT_THESIS_REASSESSMENT.md),
[`coding-agent evidence review`](docs/CODING_AGENT_EVIDENCE_REVIEW.md), and
[`research roadmap`](docs/RESEARCH_ROADMAP.md).

No public claim of token, cost, quality, or productivity improvement is currently supported.

## Research reports

- [`ESG-RR-001 v0.6 — An Exploratory Test of a Minimality Prompt in Coding Agents`](docs/reports/ESG-RR-001.md)
  reports a seven-cluster exploratory study using Codex CLI 0.150.1 and
  `gpt-5.6-terra` at medium reasoning, evaluated on 2026-08-29. See its
  [claim ledger](docs/PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json),
  [public reproduction audit](scripts/esg_rr_001_audit.py), and
  [corrections history](docs/CLAIMS_CHANGELOG.md). Version 0.6 republishes the
  unchanged scientific record under a clean canonical repository identity
  following repository-history privacy sanitation. Scientific evidence,
  claims, analysis, results, and conclusions are unchanged.

Engineering Scope Guard remains an evidence-driven research project, not a
validated optimizer.

## Core principles

1. **Outcome before token count.** Fewer tokens, files, dependencies, or lines of code are not inherently better.
2. **No unnecessary engineering.** The target is proportional engineering, not code golf.
3. **Deterministic first.** Use repository facts, tests, manifests, diffs, AST/static tooling, and hook events before adding another LLM call.
4. **Silence is a feature.** Avoid chatty, synchronous interventions that interrupt normal agent flow.
5. **Evidence before claims.** Exploratory results are not product claims. Confirmatory claims require held-out evaluation and uncertainty reporting.
6. **Null results are valid results.** If a one-sentence instruction performs as well as a larger policy, publish the sentence and retire the larger policy.
7. **Claims expire.** Prompt-level behavior is model- and harness-specific. Results must include model version, agent version, date, and task distribution.
8. **No telemetry in V0.** Start with local measurement only. Optional privacy-preserving telemetry is a later decision, not a prerequisite.

## What V0 is

The first implementation target is a **Shadow Scope Analyzer** for Codex:

- observe a task without changing Codex behavior;
- record deterministic change signals such as files, LOC, manifest dependencies, test changes, and instruction-file growth;
- identify *candidate scope-budget events* without calling them objectively “overengineering”;
- make no automatic edits or deletions;
- keep analyzer-derived data local and make no telemetry calls;
- produce a local report for manual review.

V0 exists to answer: **are the signals precise and relevant enough to justify an intervention experiment?**

## Run the V0 analyzer

V0 requires Python 3.11 or newer and has no runtime dependencies outside the
standard library. Run it from a checkout without installing it:

```bash
PYTHONPATH=src python3 -m engineering_scope_guard doctor
```

`doctor` performs local command-surface inspection only. It does not authenticate
or contact an OpenAI provider. A normal observation workflow keeps analyzer state
outside the target repository:

```bash
PYTHONPATH=src python3 -m engineering_scope_guard init \
  --repo /path/to/target-repository \
  --state-dir /path/outside/target/scope-guard-state

PYTHONPATH=src python3 -m engineering_scope_guard snapshot \
  --config /path/outside/target/scope-guard-state/config.json \
  --label before

# Capture supported Codex JSONL separately while Codex performs the task.
codex exec --json -C /path/to/target-repository "the task" \
  > /path/outside/target/scope-guard-state/codex-events.jsonl

PYTHONPATH=src python3 -m engineering_scope_guard snapshot \
  --config /path/outside/target/scope-guard-state/config.json \
  --label after

PYTHONPATH=src python3 -m engineering_scope_guard analyze \
  --config /path/outside/target/scope-guard-state/config.json \
  --trace /path/outside/target/scope-guard-state/codex-events.jsonl
```

The `codex exec` step is not performed by Scope Guard and may use the provider
according to the user's Codex configuration. The analyzer's `init`, `snapshot`,
and `analyze` implementations use no network APIs; the in-process socket-denial
test covers those paths. `doctor` invokes only three fixed local Codex inspection
commands. That test does not claim operating-system confinement of child
processes, and Scope Guard does not claim that a separately invoked Codex process
is offline. Raw Codex JSONL can contain sensitive content; keep it local. The
derived `events.jsonl` stores bounded summaries rather than prompts, reasoning,
source contents, command text, raw dependency specifications, or raw tool output.
Repository-relative paths remain sensitive local metadata: they are not
telemetry, but they can reveal project structure and should be protected like the
other local state files.

See [`docs/CODEX_CAPABILITIES.md`](docs/CODEX_CAPABILITIES.md) for verified
interfaces, coverage gaps, exit codes, and a fixture-driven offline demo.

Run the complete V0 tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## What V0 is not

V0 will not include:

- a second supervising LLM;
- a network proxy;
- per-tool human approval;
- automatic repository cleanup;
- stale-test deletion;
- model routing;
- adaptive reasoning control;
- community telemetry;
- cross-agent support;
- an enterprise dashboard;
- a repository-wide replacement for tools such as Knip, Vulture, linters, or static analyzers.

## Research roadmap

The ordered program starts with evidence maintenance and an observability-gap
audit, then requires accepted-outcome validity, audience/risk segmentation, and
native-substitute comparisons before any read-only auditor is considered.
Suggestion experiments are a later conditional gate. An active optimizer is
rejected under current evidence. Each track has falsification conditions and
requires separate authorization; see
[`docs/RESEARCH_ROADMAP.md`](docs/RESEARCH_ROADMAP.md).

## Historical candidate policies

The exact retired wording and disposition remain in
[`docs/CANDIDATE_POLICY.md`](docs/CANDIDATE_POLICY.md) for reproducibility.
They are not current recommendations and are not being revised.

## Evidence policy

Public communication rules live in [`docs/EVIDENCE_POLICY.md`](docs/EVIDENCE_POLICY.md). A core rule is:

> If the data cannot rule out meaningful harm, we will not say quality was preserved.

## Development with Codex

Codex should read [`AGENTS.md`](AGENTS.md) before making repository changes. The file intentionally constrains scope so this project does not become an example of the overengineering it is meant to study.

## Research basis

The source-classified registry records independent studies, vendor research,
official product guidance, reproducible technical systems, community reports,
contradictions, limitations, and expiry triggers. See
[`docs/EVIDENCE_REGISTRY.md`](docs/EVIDENCE_REGISTRY.md) and
[`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md). Community reports identify
candidate pain only; vendor guidance establishes current capabilities, not
universal efficacy.

## License

This project is licensed under the [MIT License](LICENSE).


## Development control

Development uses one explicit active goal in [`docs/CURRENT_GOAL.md`](docs/CURRENT_GOAL.md), governed by [`docs/GOAL_PROTOCOL.md`](docs/GOAL_PROTOCOL.md). Development-time model and reasoning choices are governed by [`docs/MODEL_REASONING_POLICY.md`](docs/MODEL_REASONING_POLICY.md).

Task failure does not automatically justify more compute. Mechanical or missing-evidence failures stay on the current configuration; genuine reasoning failures may increase effort one level; repeated capability-bound failures may switch to a stronger model. After the difficult reasoning step is resolved, de-escalate for mechanical implementation where practical.

This is a public OSS repository, but public distribution does not by itself imply production-service infrastructure. The repository should be safe, understandable, testable, and contributor-friendly without speculative HA, cloud, enterprise, scale, or compliance work.
