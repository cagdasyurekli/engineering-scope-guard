# Current-Runtime Experimental Requalification

**Evidence cutoff:** 2026-08-30

**Status:** terminal — no live experiment justified

## Decision question

Can one current-runtime, externally evaluated experiment change a practical
Engineering Scope Guard decision without weakening accepted-outcome, causal,
privacy, or attempt-accounting standards?

The governing objective remains less unnecessary agent work per correct or
accepted outcome. Acceptance is primary; tokens and wall time are not quality
proxies.

## Stable starting state

The canonical repository, numeric identity `1351269335`, and its predecessor
remain private. The completed author-metadata correction and fresh-clone checks
were revalidated without reopening remediation. GitHub-owned historical pull-
request refs and old-object access remain a visibility blocker, not a research
blocker. The v0.5 Release remains a zero-asset draft. No new privacy defect was
observed and no visibility or Release action occurred.

## Current Codex runtime

The installed client is Codex CLI `0.151.0`. The frozen candidate runtime uses
`gpt-5.6-sol`; the model catalog exposes native `low` and `medium` reasoning
controls, a 272,000-token nominal context window, and a 258,400-token effective
session window in the observed runtime. The user's active configuration used
`medium`, while the catalog's model default was `low`.

Current interfaces materially improve measurement but do not answer efficacy:

- `codex exec --json` emits lifecycle and item events and supports isolated,
  resumable sessions;
- app-server schemas expose manual compaction, compaction lifecycle items, and
  token-usage updates;
- resumed thread items are explicitly lossy for some interactions;
- the project `AGENTS.md` is model-visible, while `docs/CURRENT_GOAL.md` is not
  automatically injected;
- one isolated, content-free canary observed exactly input, cached-input,
  cache-write-input, output, and reasoning-output usage fields. It observed no
  provider-reported total. Calculated fresh input is therefore defined
  explicitly as input minus cached input minus cache-write input.

The canary used no tools, exposed no benchmark outcome, and counts as one of
the sprint's maximum 64 provider/subject executions. Relevant official
interfaces are documented in OpenAI's [non-interactive Codex
guide](https://developers.openai.com/codex/noninteractive), [App Server
guide](https://developers.openai.com/codex/app-server), [configuration
reference](https://developers.openai.com/codex/config-reference), and [model
guidance](https://developers.openai.com/api/docs/guides/latest-model).

## Candidate hard gates

| Candidate | Material current change | Terminal gate result |
| --- | --- | --- |
| Compaction / checkpoints | Manual boundary and usage events now exist. | Rejected. Natural exposure is not reproducible on the bounded task set; forced padding adds a junk-context construct; retained state and resumed tool history remain incomplete; a checkpoint changes state and behavior together. Causal isolation and instrumentation still fail. |
| Persistent repository instructions | Executable tasks and exact file bytes are available. | Rejected. No outcome-independent frame held content, relevance, bytes, and exposure constant while changing only delivery scope. Current independent studies further reduce incremental value. |
| Native reasoning effort | `low` and `medium` are exact native controls and current usage components are observable. | Conditionally selected. Same model, runtime, task, prompt, sandbox, tools, evaluator, timeout, and one-invocation trajectory; only effort differs. Requires current-evaluator gold qualification and strict tracked-input preflight before cell 1. |

Current evidence already reports task-dependent test-time-compute effects, so
the selected study is a narrow current-runtime operational replication rather
than a novelty claim. It asks whether the active `medium` setting earns its
work relative to the catalog default `low` on this executable heterogeneous
sample. It does not test an adaptive router. Related evidence includes
[*Scaling Test-Time Compute for Agentic Coding*](https://arxiv.org/abs/2604.16529),
[*Scaling Test-Time Compute for LLM Agents*](https://arxiv.org/abs/2506.12928),
and [*Evaluating AGENTS.md*](https://arxiv.org/abs/2602.11988).

No reviewed verification, tool, planning, clarification, durable-memory,
retry, or coordination candidate improved on reasoning effort's combination of
one-factor isolation, executable outcome, external tasks, and bounded quota.

The provider exposes a stable model slug and catalog controls, not a served
backend revision. Any result is therefore limited to the same current
`gpt-5.6-sol` slug/runtime over this bounded run. The counterbalanced schedule
reduces ordering risk but cannot prove that an unobservable backend stayed
byte-identical.

## Public task-source qualification

SWE-bench-Live/MultiLang remains the lowest-risk primary source for this sprint.
Its public dataset is still revision
`62dc0745c40f067fc366ae3eb1a26136e5928f85`: 1,077 tasks, 431 repositories,
and eight language splits under MIT metadata/tooling terms. The current
evaluator advanced from `bc09878...` to
`7c5ee6c11595bb0290832eb9e5b7aa81ead1cfc0`; the only changed file adjusts
pytest `XFAIL` interpretation, so historical gold checks do not certify the
current evaluator. The embedded RepoLaunch remains
`c4b623d930f3728e5338664bb634021b98492cbf`; standalone RepoLaunch main is not
substituted into the frozen infrastructure.

The source has objective execution, broad repository/language coverage, and
existing local integration. Contamination remains nonzero: prompts, patches,
tests, and some trajectories are public, and no verified current-model
knowledge cutoff is available. Subject web/browser access is therefore disabled
and no contamination-resistance claim is permitted. Causal arm comparison is
still possible because both arms use the same frozen model and task.

The strongest alternative was [SWE-bench
Science](https://github.com/OpenMOSS/SWE-bench-Science), which offers stronger
verifier separation and release boundaries across 119 tasks and 98 scientific
repositories. Its Pier/Harbor runtime is not qualified on this host and would
introduce another harness variable. SWE-bench Multilingual, Claw-SWE-Bench,
and SWE-rebench V2 were rejected for this sprint because they are older or more
exposed, less repository-diverse, add an adapter boundary, or impose much
greater evaluator/image qualification burden.

## Outcome-independent reserve

Before any benchmark subject outcome, a metadata-only SHA-256 selection excluded
all historically exposed tasks and repositories. The eligible fresh frame held
462 tasks from 199 repositories. It selected 48 repository-distinct tasks,
six per language; all 48 final selections had available official container
manifests after one manifest-unavailable JavaScript candidate was replaced by
the next frozen same-language hash rank. The selected-ID commitment is
`e08c9820f804e81d03b0e9144b853d85c6959b5202c29740c10ecbb00ecfdd51`.

An additional opaque overflow held 289 tasks across 151 repositories, committed
as `2f269a4737e3c249b463bbd41722363a977c4669da6f87297e7c85b621f7e4be`.
Task bodies, reference patches, reserve identities, and raw qualification
records remain ignored local evidence. Selection did not use expected success,
prior model output, task familiarity, or a desired direction.

The current evaluator was qualified with two official-gold repetitions on one
frozen manifest-qualified task per language. Six languages completed two of two
successes. In the next language, the initial candidate and first deterministic
replacement failed the official gold test on repetition 1; the second and final
permitted replacement ended in evaluator runtime failure on repetition 1. The
frozen two-replacement allowance was exhausted, so the eighth language was not
run. This stopped qualification before contract freeze or cell 1. No task body,
model outcome, acceptance comparison, or treatment contrast was used.

## Conditionally selected experiment

The unexecuted Reasoning Effort v1 design would have frozen:

- eight repository-distinct tasks, one per language;
- `low` baseline versus `medium` treatment;
- two repetitions per task and arm, 32 frozen cells;
- per-task AB/BA counterbalancing and deterministic schedule order;
- one fresh `codex exec` subject invocation and one official evaluation per
  cell, with no corrective resume;
- four first-schedule cells as Stage 1 infrastructure qualification;
- maximum two attempts per cell, attempt 2 only after an explicitly classified
  frozen infrastructure failure, and a global 64-execution ceiling including
  the prior canary;
- acceptance first; task/repository as the independent unit; deterministic
  task-cluster bootstrap uncertainty; discordant pairs, heterogeneity,
  missingness, and leave-one-task-out leverage;
- separate provider usage, calculated fresh input, subject wall time, evaluator
  wall time, subject turns, commands, searches, and item counts;
- no imputation, treatment tuning, post-outcome task replacement, third
  attempt, equivalence/non-inferiority, per-language efficacy, billing,
  mechanism, confirmatory, or second-experiment claim.

The live study does not begin unless the tracked contract, pool, authorization,
runtime, model catalog, dataset bytes, evaluator, RepoLaunch, Docker platform,
container images, usage schema, credentials, and empty ledger all pass a strict
zero-call preflight.

## Pre-outcome integrity audit

Two independent provider-free reviews challenged the prospective harness before
cell 1. The resulting controls bind the complete repository-owned execution and
analysis code closure, Codex executable bytes and hashed local path, evaluator
Python/package identity, exact prompt framing, selection audit, and local image
identities. They also distinguish harness attempts from conservative invocation
starts and confirmed returns, stop after four completed Stage 1 cells until a
provider-free authorization event, validate raw/derived receipt hashes on every
restart, and fail closed rather than repeat ambiguous interrupted work.

The final review found no remaining material pre-cell-1 harness blocker. A
subsequent outcome-blind Stage 1 audit was added so continuation after four
completed prefix cells would require complete frozen-command, subject-return,
provider-usage, subject-work, prohibited-tool, official-evaluator, and durable
receipt evidence. Failure would be terminal and hash-bound. Forty-eight focused
provider/evaluator-free tests pass. This work did not expose a task body or
experimental outcome and did not authorize bypassing the gold or strict-
preflight gates.

## Terminal disposition

`NO LIVE EXPERIMENT JUSTIFIED`. The gold gate ended after 15 evaluator attempts:
12 official-gold successes across six fully qualified languages, two official-
gold test failures, and one evaluator runtime failure after two deterministic
replacements. Experimental subject starts, returns, frozen-cell attempts, and
acceptance observations are all zero. One isolated content-free runtime canary
was the only new model invocation.

This is a design/infrastructure block, not a result about low versus medium
reasoning effort. It does not establish causal effect, preserved quality,
equivalence, non-inferiority, billing savings, unnecessary-work reduction, or a
per-language effect. The public-safe terminal record is
`experiment/current_runtime_requalification_terminal.json`; raw receipts,
reserve identities, and task details remain ignored local evidence.
