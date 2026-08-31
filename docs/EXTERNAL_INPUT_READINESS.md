# External Input and Evaluator Gate Readiness

**Status:** complete

**As of:** 2026-08-27

## Boundary

This record resolves only the external task-source, evaluator, partition,
fixed-subject receipt, usage/cache, reviewer-claim, and budget gates left by the
completed Exploratory Pilot readiness **NO-GO**. It does not run a Pilot cell,
compare baseline with C-short v0.1, change either policy, or interpret a task
outcome as efficacy evidence.

## Source review

Primary evidence was checked against the official source pages, repositories,
dataset metadata APIs, and papers current on 2026-08-27.

| Candidate | Provenance and evaluator | Freshness/diversity | License/resource/harness limits | Disposition |
| --- | --- | --- | --- | --- |
| SWE-bench-Live/MultiLang | Real GitHub issues, base commits, F2P/P2P lists, rebuild/test commands, and per-instance Docker images; official evaluator at `microsoft/SWE-bench-Live` | Current dataset revision has 1,077 tasks across C, C++, C#, Go, Java, JavaScript, Rust, and TypeScript; 634 tasks are newer than the fixed subject knowledge cutoff and pass the metadata frame | Dataset/evaluator MIT; underlying repositories retain their licenses. Official evaluator needs Linux Docker; documented baseline is 4 CPUs/16 GB per instance and some C++ tasks may need 50 GB | **Selected** for lower contamination risk, current supply, executable evaluation, and programmatic metadata-only selection |
| SWE-rebench V2 | Real issue- and PR-derived tasks, prebuilt images, generated log parsers, F2P/P2P, and an official Docker evaluator | 32,079 tasks, 20 languages, and 3,600+ repositories | Dataset CC-BY-4.0 and builder MIT; per-repository licenses vary. Some problem descriptions and quality metadata are LLM-generated, and the public dataset is also positioned for training | Strong supply alternative, but weaker issue-only provenance and a less direct fit for this bounded issue-resolution Pilot |
| SWE-bench Multilingual | 300 manually curated real issue/PR tasks with F2P/P2P and the mature SWE-bench Docker harness | Nine languages and 41/42 repositories, but tasks date from 2017–2025 and the fixed set is heavily reused | Dataset/evaluator MIT; Docker required. Broad historical reuse creates explicit contamination/generalization limits | Useful classic compatibility fallback, not selected for a freshness-sensitive Pilot |
| Other current sources screened | Multi-SWE-bench, SWE-PolyBench, SWE-Bench++, and related builders increase language/task coverage | No reviewed source was clearly superior on the combined freshness, official executable environment, metadata-only selection, and integration criteria | Adding another framework would not remove the current host's missing-container gate | Not selected |

Official references:

- [SWE-bench-Live repository](https://github.com/microsoft/SWE-bench-Live)
- [SWE-bench-Live evaluator instructions](https://github.com/microsoft/SWE-bench-Live/blob/main/evaluation/README.md)
- [SWE-bench-Live dataset](https://huggingface.co/datasets/SWE-bench-Live/MultiLang)
- [SWE-rebench V2 repository](https://github.com/SWE-rebench/SWE-rebench-V2)
- [SWE-rebench V2 paper](https://arxiv.org/abs/2602.23866)
- [SWE-rebench V2 dataset](https://huggingface.co/datasets/nebius/SWE-rebench-V2)
- [SWE-bench Multilingual](https://www.swebench.com/multilingual.html)
- [SWE-bench evaluator repository](https://github.com/SWE-bench/SWE-bench)

## Frozen eligibility frame

The selected source is `SWE-bench-Live/MultiLang` revision
`62dc0745c40f067fc366ae3eb1a26136e5928f85`. Eligibility version
`swe-bench-live-multilang-v1` uses only the following metadata:

- unique instance ID, repository, language, and issue/PR creation timestamp;
- official Docker image identity;
- at least one F2P test and at least one P2P test;
- at least one rebuild command and one test command;
- creation strictly after `2026-02-16T23:59:59Z`, the documented GPT-5.6
  knowledge-cutoff date used for the fixed subject;
- no overlap with the four permanently development-only task IDs.

No difficulty label, solution shape, task text, reference patch, test patch,
agent result, or policy outcome participates in eligibility. No ceiling/floor
filter is imposed: the source provides no independently validated metadata that
would justify one before evaluator preflight. The partition script rejects task-
body fields rather than ignoring them.

Exact source-frame results:

- 1,077 source rows and 1,077 unique IDs;
- 634 eligible distinct tasks across 223 repositories;
- 421 excluded because they were not newer than the cutoff;
- 22 additional post-cutoff tasks excluded for missing P2P evidence;
- zero overlap with `dev-guard-01`, `dev-irreducible-01`, `dev-reuse-01`, or
  `dev-shared-01`.

The 634 count is source eligibility. Current host-runnable supply is zero until
an official evaluator can pass on a compatible container runtime.

## Opaque deterministic partition

`scripts/external_task_partition.py` ranks IDs with
`SHA-256(seed NUL source_revision NUL instance_id)`. The fixed seed is
`engineering-scope-guard-pilot-v1-2026-08-27`.

The Pilot has 12 tasks from 12 repositories and covers every source language:
C 1, C++ 2, C# 2, Go 1, Java 2, JavaScript 1, Rust 2, and TypeScript 1. These
quotas were fixed from language coverage and eligible supply, not task outcomes.
Repository uniqueness reduces clustering in the small Pilot.

All other eligible tasks from the 12 Pilot repositories are held out of both
pools. This leaves:

- 12 Pilot tasks;
- 84 same-repository holdouts;
- 538 confirmatory-reserve tasks across 211 repositories.

Reserve IDs and bodies are not emitted. The allocation commitment is
`1de066a17c4810b042b59edb8ea717775cf5a04c5dba0150c87613535d05c71b`;
the ranked reserve-ID commitment is
`71c0879b77374370873613daf8856a5c7b507977d911576d00d495f4af70e08a`.
The machine record is `experiment/external_task_partition.json`.

## Evaluator and fixed-subject receipt

The smoke candidate was selected after partitioning by the lowest metadata-only
F2P+P2P count, then hash rank: `BYVoid__OpenCC-1257` (one F2P and 123 P2P
tests). Its body and reference patch were not fetched.

The intended official evaluator is pinned to
`microsoft/SWE-bench-Live@bc09878a5d192d0804dbd647dc6e650372fcb0ac`.
The public image is Linux/amd64 with 807,365,846 compressed layer bytes. The
host is macOS arm64 and has no Docker or compatible container runtime installed.
The official evaluator preflight therefore failed before task checkout, Codex,
or evaluator execution.

No Codex subject or provider request was started because it could not reach an
evaluator. This is an `infrastructure-pre-subject-failure`, not a provider,
task, policy, or evaluator result. The persisted receipt is
`experiment/external_smoke_receipt.json`.

The fixed but unexecuted subject configuration remains Codex 0.150.1,
`gpt-5.6-terra`, medium reasoning, workspace-write automatic review,
repository-only tools, ignored user config/rules, no MCP/plugins/hooks, two
turns, 900 seconds per turn, and one standardized corrective round. The exact
provider backend snapshot remains unavailable from the CLI interface.

## Evaluator coverage and limits

When runnable, the selected source supplies:

- issue-specific F2P checks;
- P2P regression checks;
- repository-specific rebuild and test commands;
- an evaluator exit/result and per-test log parser;
- protection against accepting a patch that only passes the new target checks.

It does not generally supply independently maintained lint/type checks, human
maintainability judgment, architectural correctness, or proof against every
unrelated regression. The official instructions also warn that validity can
drift across machines and recommend three gold-patch evaluations per task before
using the locally valid subset.

## Usage, cache, and billing evidence

Codex 0.150.1 `exec --json` has actually emitted these provider-reported fields
in completed development receipts:

- `input_tokens`;
- `cached_input_tokens`;
- `output_tokens`;
- `reasoning_output_tokens`.

It has not emitted provider-billed amount/currency, `cache_write_tokens`, or an
exact backend model snapshot. OpenAI's Responses schema has separate input,
cached input, cache-write, output, reasoning-output, and total-token fields, and
current GPT-5.6 guidance says cache writes are billed differently. The Codex
CLI projection is therefore insufficient to reconstruct provider billing
exactly. See [Responses usage schema](https://developers.openai.com/api/reference/cli/resources/responses/methods/create),
[GPT-5.6 guidance](https://developers.openai.com/api/docs/guides/latest-model),
and [current model pricing](https://developers.openai.com/api/docs/models/compare).

Permitted calculated values are `fresh_input_tokens = input_tokens -
cached_input_tokens` and a clearly labeled API-list-price estimate. Neither is
provider-billed cost. The minimum interpretable Pilot efficiency record must
report fresh input, cached input, output, and reasoning output separately by run
and paired task, together with turns, time, and acceptance.

Later cache handling must use fresh per-cell `CODEX_HOME`, ephemeral sessions,
separate outputs, counterbalanced arm order, and timestamps. Provider-side cache
sharing cannot be proven absent through local state. If cache writes and actual
billing remain unavailable, billed-cost claims stay prohibited; reported cached
and fresh components are analyzed separately rather than collapsed into invented
precision.

## Reviewer capacity and claim boundary

Independent experienced-reviewer capacity remains zero. That does not by itself
prevent a narrowly exploratory Pilot whose question is limited to executable
F2P/P2P/build outcomes, classified failures, provider-reported usage components,
structural diagnostics, and variance feasibility.

With zero reviewers, the following remain prohibited:

- broad maintainability or code-quality improvement/preservation;
- architectural appropriateness or human acceptability;
- objective “overengineering” classification;
- equivalence, non-inferiority, or general quality preservation;
- downstream maintenance, lifecycle, or future-work savings.

An LLM judge is not a substitute for those missing judgments. Reviewer
recruitment is not a prerequisite for the bounded deterministic Pilot question,
but it is a prerequisite for later claims that require human judgment.

## Contingent Pilot budget

Supply supports retaining the previous 12-task design:

- 12 distinct Pilot tasks;
- two arms: baseline and C-short v0.1;
- two repetitions per task/arm;
- 48 planned subject runs;
- eight infrastructure-only replacements, for a 56-invocation ceiling;
- 36 gold evaluator preflights (three per task) before subject execution.

This is still a feasibility/variance budget, not a power calculation. Run
sequentially with one evaluator worker until measured evidence justifies
concurrency. The official resource floor is 4 CPUs/16 GB RAM per instance; each
selected image and its unpacked size must be preflighted because some C++ tasks
may require 50 GB RAM. Only the smoke image has been measured (0.807 GB
compressed), so total storage and runtime remain unavailable.

Current GPT-5.6 Terra API list rates could support a calculated estimate once
representative task usage exists. Prior tiny synthetic fixtures are not a
credible forecast for these repositories, and Codex provider billing is not
exposed. Estimated spend therefore remains unavailable rather than falsely
precise.

## Verification

At the final bytes:

- all 64 repository unit tests passed;
- warning-clean compilation of `src`, `scripts`, and `tests` passed;
- the prior bounded NO-GO readiness audit still passed;
- the external-input readiness audit passed all 10 consistency checks;
- partition regeneration was byte-identical;
- `git diff --check` passed.

## Gate result

The external source, source-level supply, deterministic partition, and bounded
zero-reviewer claims pass. The official evaluator, fixed-subject end-to-end
receipt, container isolation adapter, representative resource/storage budget,
and complete usage/cache interpretation do not.

## Bounded conclusion

**REDESIGN REQUIRED**

The gates appear solvable, but the current host/harness cannot run the selected
official evaluator. The smallest next design step is a separately authorized
compatible container runtime plus a one-task gold preflight and the already
frozen single-condition receipt. Do not run baseline versus C-short, change the
policy, inspect reserve bodies, or start the Pilot.
