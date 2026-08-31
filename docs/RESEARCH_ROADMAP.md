# Research Roadmap

**Status:** ordered falsification program, not authorization

**Decision basis:** [`PROJECT_THESIS_REASSESSMENT.md`](PROJECT_THESIS_REASSESSMENT.md)

## Governing rule

Each track must earn the next. A roadmap entry is not permission to execute it.
Any new capability, provider/evaluator call, treatment, Pilot, confirmatory run,
external publication, or account action requires a separately authorized goal.
Historical task bodies, frozen treatments, ledgers, and retirement decisions
remain unchanged.

The common outcome family is work, time, turns, corrections, searches, user
interventions, and cost **per correct or accepted outcome**. Report components
separately. Do not optimize raw tokens, LOC, files, or a synthetic health score.

## Track 0 — maintain the evidence base

**Question:** Can claims remain current, contradictory, scoped, and auditable?

- Maintain [`EVIDENCE_REGISTRY.md`](EVIDENCE_REGISTRY.md), including source
  tier, review status, tested population/task/runtime, limitations,
  contradictions, confidence, and revalidation triggers.
- Recheck rapidly expiring vendor guidance after material model/runtime changes
  and at least quarterly while actively cited.
- Preserve null and adverse evidence; do not turn guidance into runtime rules.

**Prerequisite:** none. Documentation-only maintenance still requires an
explicit bounded goal when it changes the repository.

**Kill/falsification condition:** if the registry cannot be kept current enough
to support calibrated claims, stop issuing project recommendations and retain
it only as a dated literature record.

## Track 1 — shadow-observability gap audit

**Status:** complete — advance gate not passed (2026-08-29)

**Question:** Which decision-relevant facts can the existing V0 observe
reliably, locally, and with negligible burden?

- Audit supported Codex interfaces for coverage of context boundaries, repeated
  operations, tool calls, search, verification, corrections, and completion.
- Separate observed facts from inferred intent and surface missing events.
- Compare the V0 inventory with native logs and existing evaluation tools.
- Measure analyzer setup, storage, review time, and target-repository effects.

**Prerequisites:** current runtime documentation, a privacy-safe fixture set,
explicit authorization for any new canary, and no provider/evaluator execution
unless separately authorized.

**Advance only if:** at least one important, reproducible observation gap exists
that native capabilities do not already expose adequately.

**Kill condition:** required facts need invasive interception, semantic guesses,
private-content publication, target mutation, or overhead comparable to the
candidate waste. Fall back to research-only.

**Terminal result:** The existing V0 reliably normalizes structural deltas and
observer-health evidence, but Git/manifests/tests/CI and native traces already
provide the underlying useful facts. V0 does not reliably expose same-file
rereads, repeated searches/results, correction or state-recovery work, tool
selection quality, or accepted outcomes. See
[`SHADOW_OBSERVABILITY_GAP_AUDIT.md`](SHADOW_OBSERVABILITY_GAP_AUDIT.md).
Track 2 is not authorized and its prerequisite was not met.

## Track 2 — measurement validity and accepted-outcome linkage

**Question:** Do observable signals correspond to actual repeated/unnecessary
work without rewarding under-work?

- Predefine accepted-outcome and verification criteria before viewing results.
- Validate repeated-search, correction, state-recovery, and abandoned-work
  candidates against independently reviewable outcomes.
- Include necessary-investigation counterexamples and no-issue cases.
- Report false positives, false negatives, missing coverage, and observer cost.

**Prerequisites:** Track 1 advance gate, representative consented/local evidence,
and a separate experimental authorization and freeze where comparison occurs.

**Advance only if:** a small set of signals is sufficiently precise and useful
to users while outcome quality and safety remain protected.

**Kill condition:** structural/token proxies repeatedly disagree with accepted
outcomes, or useful classification requires an unvalidated LLM semantic judge.

## Track 3 — user, task, risk, and intent segmentation

**Question:** Which differences materially alter useful observations or safe
support?

Candidate dimensions are engineering/domain/agent expertise, task risk and
reversibility, lifecycle, learning intent, and autonomy preference. Begin with
qualitative requirements and outcome definitions; do not freeze a taxonomy
before evidence.

**Prerequisites:** Track 2 produces at least one valid observation and privacy,
consent, and high-risk exclusion rules are explicit.

**Advance only if:** a small number of replicated segments predicts materially
different needs or outcome criteria.

**Kill condition:** segments are unstable, burdensome, stereotyping, or do not
improve decisions. Retain user-specified objectives instead of inferred types.

## Track 4 — native capability and substitute comparisons

**Question:** Can configuration or an existing tool solve a validated problem?

For each candidate gap, compare no change, the relevant native feature, and an
existing OSS/service option before building. Include instruction scoping,
context/tool search, deterministic output compression, tests/VCS, and existing
trace/evaluation systems where applicable.

**Prerequisites:** a Track 2 validated gap, current capability verification,
and separately authorized reversible comparisons.

**Advance only if:** a material gap remains after the simplest native or
existing solution, including its privacy and operational tradeoffs.

**Kill condition:** existing configuration/tools perform comparably with less
burden. Document the substitute and build nothing.

## Track 5 — local read-only auditor feasibility

**Question:** Would users benefit from a decomposed observation report?

A prototype, if separately authorized, may report evidence and uncertainty for
validated observations. It must support `No change recommended`, contain no
automatic mutation, and avoid a synthetic score.

**Prerequisites:** Tracks 1–4 pass; demonstrated demand; bounded privacy model;
stable supported interfaces; predeclared usefulness and burden criteria.

**Advance only if:** users understand the report, act selectively, and obtain
better accepted outcomes or less verified rework after full overhead is counted.

**Kill condition:** advice is ignored, misunderstood, stale, redundant with
native tools, or increases work/unsafe confidence.

## Track 6 — suggestion plus optional controlled experiment

**Question:** Can a user-chosen reversible comparison resolve a specific
hypothesis better than static advice?

Use `observation → hypothesis → evidence → suggested reversible experiment →
measured result`. Freeze the intervention and accepted-outcome criteria before
execution. Keep no-change controls and contradiction disclosure.

**Prerequisites:** Track 5 usefulness, explicit experimental authorization,
privacy/cost approval, sufficient task supply, and independent quality checks.

**Kill condition:** comparisons are underpowered, cannot isolate drift, create
more burden than benefit, or reproduce this project's previous search/context/
work harms.

## Explicitly outside the roadmap

An active optimizer that automatically changes context, instructions, tools,
models, or reasoning is rejected under current evidence. It does not become
authorized by completing any track. Automatic routing, cloud telemetry,
accounts, dashboards, broad multi-agent orchestration, and a new retrieval or
evaluation platform are also excluded absent a materially new thesis decision.

## Current boundary

Track 0's dated registry and Track 1's zero-provider audit are complete. Track 1
did not find a material incremental fact and did not pass its advance gate. No
Track 2 experiment, capability change, provider/evaluator execution, or live
canary is authorized.

**NO MATERIAL OBSERVABILITY GAP — RETAIN RESEARCH-ONLY**

The subsequent research-selection goal evaluated eleven candidate families
without executing or freezing any experiment. Compaction/checkpoints,
persistent instruction delivery, and reasoning effort were the strongest
scientific candidates, but none passed novelty, isolation, task-supply,
cost/power, and model/runtime-half-life gates together. See
[`NEXT_RESEARCH_HYPOTHESIS_PRIORITIZATION.md`](NEXT_RESEARCH_HYPOTHESIS_PRIORITIZATION.md).

This does not reorder or reopen Tracks 2–6. Track 0 evidence maintenance remains
the only current roadmap activity. A public synthesis of existing evidence may
be considered only through a separately authorized publication-planning goal.

**NO NEW LIVE EXPERIMENT JUSTIFIED — MAINTAIN/PUBLISH EXISTING EVIDENCE**
