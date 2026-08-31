# An Exploratory Test of a Minimality Prompt in Coding Agents

| Field | Value |
| --- | --- |
| Report | Engineering Scope Guard Research Report `ESG-RR-001` |
| Version | `0.6` |
| Status | Exploratory historical research report |
| Publication date | 2026-08-31 |
| Evidence cutoff | 2026-08-29 |
| Author/maintainer | Çağdaş Yürekli (`cagdasyurekli`) |
| Repository | [`cagdasyurekli/engineering-scope-guard`](https://github.com/cagdasyurekli/engineering-scope-guard) |
| Corrections | [`docs/CLAIMS_CHANGELOG.md`](../CLAIMS_CHANGELOG.md) |
| Claim ledger | [`ESG-RR-001` claim scope](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json), SHA-256 `9fc57757c8fd5bac337eff30961196e5e14c5300237a296c7c5a4cf0815be847` |
| Report commit | The root commit referenced by annotated version tag `esg-rr-001-v0.6`; the corresponding GitHub Release records its full SHA and immutable state |

> **Version 0.6 republication.** This version republishes the unchanged
> scientific record under a clean canonical repository identity following
> repository-history privacy sanitation. Scientific evidence, claims,
> analysis, results, and conclusions are unchanged.

> **Version 0.5 republication.** Version 0.5 republishes the unchanged
> scientific report after correction of repository Git author metadata.
> Scientific evidence, claims, analysis, results, and conclusions are
> unchanged.

> **Version 0.4 republication.** Version 0.4 republishes the same scientific
> report under the independent repository identity. Scientific evidence,
> claims, analysis, results, and conclusions are unchanged.

> **Version 0.3 republication.** Version 0.3 republishes the same scientific
> report after repository-history privacy sanitation. Scientific evidence,
> claims, analysis, results, and conclusions are unchanged.

> **Version 0.2 correction.** Version 0.1 incorrectly described its release
> tag as immutable. The v0.1 tag was annotated, but its GitHub Release was not
> immutable. No scientific evidence, result, claim, analysis, interpretation,
> or conclusion changed. See the [corrections history](../CLAIMS_CHANGELOG.md).

Engineering Scope Guard is an evidence-driven research project, not a
validated optimizer. This report records a bounded historical observation and
the decision made from it; it does not recommend that readers adopt or avoid a
class of prompts.

## Abstract

Coding-agent guidance often treats shorter solutions and fewer tokens as
obvious improvements, but those measures matter only alongside a correct or
accepted outcome. We tested one exact minimality instruction, C-short v0.1,
against an unmodified baseline on a frozen external-task sample. In an
exploratory paired study using Codex CLI 0.150.1 and `gpt-5.6-terra` at medium
reasoning, seven complete SWE-bench-Live/MultiLang task clusters with two
repetitions per arm produced a C-short-minus-baseline acceptance estimate of
-14.3 percentage points, with an exact task-bootstrap 95% percentile interval
from -50.0 to +14.3 percentage points. C-short used more provider-reported input
tokens and wall time at the paired point estimate, with ratios 1.223
(1.012–1.448) and 1.326 (1.052–1.575), respectively. The small exploratory
sample cannot establish a general causal effect, equivalence, non-inferiority,
or preserved quality. One replicated task pattern was consistent with a
post-hoc literal-minimality hypothesis; another pair favored C-short and
several were null. The project retired the exact treatment rather than tuning
it against viewed tasks. [`ESG-RR-001-C01`–`C05`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

## Research question and interpretation order

The question was whether adding exact C-short v0.1 changed work to an accepted
outcome relative to baseline in the frozen Pilot-v3 sample. The primary outcome
was official evaluator acceptance. Provider-reported tokens, elapsed time,
turns, search, patch structure, and other work measures were secondary.

Acceptance comes first because less work is not beneficial when a trajectory
fails an acceptance-relevant requirement. Raw token, file, or line reduction
is therefore not sufficient evidence of coding-agent efficiency; work must be
interpreted per correct or accepted outcome with quality guardrails.
[`ESG-RR-001-C07`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

## Prior evidence and candidate selection

C-short was a reasonable exploratory candidate, not a proven intervention.
An authored development pool produced ceiling acceptance in all arms and a
directional work reduction for C-short. Those cases were development fixtures,
not efficacy evidence: they were authored, small, one-turn, and never pooled
with the external-task study. The external Pilot-v3 result superseded that
directional development signal for the project's treatment decision. This
history is relevant contrary evidence, not an independent replication.
[`ESG-RR-001-C01`, `C05`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

## Exact treatment

The baseline received no intervention. C-short v0.1 was the following exact
single-line UTF-8 text, including its final newline in the tracked file:

> Implement what the requirement states; reuse what already exists; do not add functionality or structure it does not require.

The byte identity is preserved at [`experiment/arms/short.txt`](../../experiment/arms/short.txt),
SHA-256 `c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6`.
No treatment change occurred after results were viewed.

## Frozen methodology

### Runtime and task source

- Subject: Codex CLI 0.150.1, `gpt-5.6-terra`, medium reasoning, one worker.
- Permissions: automatic approval review with a workspace-write sandbox; user
  configuration and rules were not loaded; no MCP, browser, or network tool was
  exposed to the subject.
- Task source: SWE-bench-Live/MultiLang revision
  `62dc0745c40f067fc366ae3eb1a26136e5928f85`.
- Evaluator: the official task-specific evaluator at revision
  `bc09878a5d192d0804dbd647dc6e650372fcb0ac`, using RepoLaunch revision
  `c4b623d930f3728e5338664bb634021b98492cbf`.
- Trajectory: at most two subject turns, with at most one corrective round;
  900 seconds per turn and 1,800 seconds per attempt.

These are descriptive frozen-method identities, not claims about current Codex
behavior.

### Source and license record

The source links and license metadata below were revalidated on 2026-08-30.
The exact [MultiLang dataset revision](https://huggingface.co/datasets/SWE-bench-Live/MultiLang/commit/62dc0745c40f067fc366ae3eb1a26136e5928f85)
was public, ungated, and labeled MIT. The exact
[official evaluator revision](https://github.com/microsoft/SWE-bench-Live/commit/bc09878a5d192d0804dbd647dc6e650372fcb0ac)
and its pinned [RepoLaunch revision](https://github.com/microsoft/RepoLaunch/commit/c4b623d930f3728e5338664bb634021b98492cbf)
each exposed an MIT license. The evaluator repository describes the MultiLang
evaluation route; this report makes no peer-review claim about the particular
frozen dataset snapshot.

The eight source repositories remained public. Their upstream license files
were: [timescaledb](https://github.com/timescale/timescaledb/blob/main/LICENSE)
(mixed Apache-compatible/Timescale terms),
[slang](https://github.com/shader-slang/slang/blob/master/LICENSE)
(Apache-2.0 with LLVM exception),
[azure-sdk-for-net](https://github.com/Azure/azure-sdk-for-net/blob/main/LICENSE.txt)
(MIT), [telegraf](https://github.com/influxdata/telegraf/blob/master/LICENSE)
(MIT), [checkstyle](https://github.com/checkstyle/checkstyle/blob/master/LICENSE)
(LGPL-2.1), [Gladys](https://github.com/GladysAssistant/Gladys/blob/master/LICENSE)
(Apache-2.0), [gleam](https://github.com/gleam-lang/gleam/blob/main/LICENCE)
(Apache-2.0), and [etherpad](https://github.com/ether/etherpad/blob/develop/LICENSE)
(Apache-2.0). The package republishes none of their source, tests, task bodies,
or patches; the identifiers and links provide provenance only. Readers must
follow each upstream repository's terms for any separate use of its content.

### Pool, allocation, and independent unit

The pool contained eight public tasks from eight repositories and eight
languages, selected one per language by a frozen SHA-256 ranking from an opaque
external reserve. Task bodies and prior outcomes were not used for selection.
Each task had baseline and C-short cells in two counterbalanced repetitions,
for 32 frozen cells.

| Slot | Public task ID | Repository | Language | Paired status |
| ---: | --- | --- | --- | --- |
| 1 | `timescale__timescaledb-9955` | `timescale/timescaledb` | C | complete |
| 2 | `shader-slang__slang-10768` | `shader-slang/slang` | C++ | incomplete |
| 3 | `Azure__azure-sdk-for-net-58482` | `Azure/azure-sdk-for-net` | C# | complete |
| 4 | `influxdata__telegraf-18686` | `influxdata/telegraf` | Go | complete |
| 5 | `checkstyle__checkstyle-19487` | `checkstyle/checkstyle` | Java | complete |
| 6 | `GladysAssistant__Gladys-2504` | `GladysAssistant/Gladys` | JavaScript | complete |
| 7 | `gleam-lang__gleam-5982` | `gleam-lang/gleam` | Rust | complete |
| 8 | `ether__etherpad-7445` | `ether/etherpad` | TypeScript | complete |

The independent analysis unit is the task/repository cluster, not an individual
run. The two repetitions within a task share code, issue, evaluator, and task
difficulty, so treating all 28 paired cells as independent would overstate the
information in the sample. The analysis averages repetitions within each task
and resamples the seven complete task clusters.

### Outcome, retry, and missingness rules

`accepted_completed` means that the official evaluator returned its frozen
success disposition. Evaluator test failures, subject failures, empty patches,
and trajectory timeouts remained assigned to their arm. Predeclared
infrastructure-invalid states could use only the frozen bounded rerun rules;
post-outcome reclassification was forbidden.

The successor schedule started 33 attempts. The first 31 schedule positions
produced admissible outcomes. Both attempts for position 32 produced coherent
local Docker infrastructure-failure receipts, after which the frozen attempt
limit stopped the batch. Attempt 3 was forbidden. The missing baseline cell for
slot 2 was not imputed. Its three admissible sibling cells remain in marginal
summaries; the primary paired analysis uses the seven clusters complete in both
arms and repetitions. [`ESG-RR-001-C01`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

### Analysis and uncertainty

For acceptance, the paired estimate is the mean of seven task-level
C-short-minus-baseline differences. For work measures it is the ratio of the
two arm task means. The 95% intervals use an exact nonparametric task bootstrap:
seven task clusters sampled with replacement, exhaustively covering all
`7^7 = 823,543` ordered resamples, with nearest-rank 2.5th and 97.5th
percentiles. This was exploratory analysis; no universal non-inferiority margin
was frozen.

## Results

### Acceptance first

| Result | Baseline | C-short | Paired estimate |
| --- | ---: | ---: | --- |
| Acceptance, complete clusters | 42.9% | 28.6% | −14.3 pp; 95% interval −50.0 to +14.3 |
| Input-token task mean | 1,151,616 | 1,408,131 | ratio 1.223; 95% interval 1.012–1.448 |
| Wall-time task mean | 739 s | 981 s | ratio 1.326; 95% interval 1.052–1.575 |

The first row is the primary result; the work rows follow it deliberately.
[`ESG-RR-001-C01`, `C02`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

Across all 31 admissible cells, marginal acceptance was 6/15 for baseline and
4/16 for C-short. These unequal-denominator rates are descriptive. Across the
14 complete matched repetition pairs:

- three were accepted in both arms;
- seven failed in both arms;
- three were accepted only in baseline;
- one was accepted only in C-short.

Baseline acceptance changed between repetitions for two of seven complete
tasks; C-short acceptance changed for none. Stability can mean stable failure
and is not a quality claim. The wide interval remains compatible with
meaningful harm and with a smaller C-short advantage. It does not demonstrate
absence of a difference. [`ESG-RR-001-C01`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

### Work and usage diagnostics

The following task-level paired summaries are descriptive diagnostics from the
same seven clusters. Ratios are C-short divided by baseline.

| Measure | Baseline mean | C-short mean | Ratio | 95% interval |
| --- | ---: | ---: | ---: | ---: |
| Input tokens | 1,151,616 | 1,408,131 | 1.223 | 1.012–1.448 |
| Cached input tokens | 1,078,546 | 1,325,367 | 1.229 | 1.018–1.459 |
| Calculated fresh input tokens | 73,070 | 82,764 | 1.133 | 0.922–1.316 |
| Output tokens | 8,228 | 8,899 | 1.082 | 0.920–1.256 |
| Reasoning output tokens | 2,922 | 2,770 | 0.948 | 0.691–1.238 |
| Wall time, seconds | 739 | 981 | 1.326 | 1.052–1.575 |

Input and wall time did not show a reduction in this sample. The calculated
fresh-input, output, and reasoning-output intervals allow effects in either
direction. Provider billing amount and currency were unavailable; no monetary
cost is inferred from token components. [`ESG-RR-001-C02`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

Across the 28 paired cells, C-short recorded 19,713,833 input tokens and
baseline 16,122,630. Of the 3,591,203-token difference, 3,455,488 (96.2%) were
cached input and 135,715 (3.8%) were calculated fresh input. Cached input is a
provider-reported component, not a monetary price or a judgment about whether
the context was necessary. [`ESG-RR-001-C03`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

C-short used 23 subject turns versus 20 for baseline. The body-safe traces
recorded 262 versus 249 command executions, 534 versus 512 conservative local
read/search command segments, and 22 versus 9 completed web-search items. File-
change events were 36 versus 37, and final patches changed 51 versus 52 files.
These are descriptive trace/patch diagnostics; they do not identify why an
action occurred or whether each action was necessary.

### Heterogeneity and sensitivity

Five of seven complete clusters had higher C-short input and wall time; two had
lower values for both. One cluster supplied two replicated baseline-only pairs,
one cluster supplied another baseline-only pair, and one supplied the only
C-short-only pair. Several pairs were null.

Leave-one-task-out estimates were:

- acceptance difference: −25.0 to 0.0 percentage points;
- input-token ratio: 1.112–1.279;
- wall-time ratio: 1.185–1.387.

Omitting the replicated-discordance cluster moved the acceptance estimate to
0.0 points; omitting the C-short-favoring cluster moved it to −25.0 points.
These summaries expose leverage and task heterogeneity. They are not subgroup
or population estimates. [`ESG-RR-001-C01`, `C02`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

## Post-hoc mechanism evidence

One task cluster showed a replicated arm-linked patch and acceptance pattern
consistent with the post-hoc hypothesis that up-front literal-minimality
guidance can suppress acceptance-relevant adjacent handling. Both baseline
repetitions handled an adjacent missing-state case and were accepted; both
C-short repetitions made the same narrower structural change and failed the
same bounded evaluator condition. No task body, source, patch, or check name is
published here. [`ESG-RR-001-C04`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

This evidence is concrete but not causal. The mechanism was identified after
outcomes were known, was not independently manipulated, and appeared as a
replicated pattern in one cluster. The evaluator may also enforce behavior
implicit rather than explicit in the short issue statement. The secondary
pattern of more completed web search and cached context is likewise compatible
with several trajectory-level explanations and cannot be attributed to one
treatment clause.

## Evidence against the adverse narrative and alternatives

The record retains observations that do not fit a simple adverse story:

- one matched repetition pair favored C-short;
- three pairs were accepted in both arms and seven failed in both arms;
- two task clusters used less input and wall time under C-short;
- reasoning-output tokens were lower at the aggregate paired point estimate;
- the acceptance interval includes a smaller C-short advantage;
- authored development evidence was directionally favorable, although it was
  not efficacy evidence.

Task noise, evaluator/task-statement mismatch, trajectory variation, corrective
rounds, caching behavior, and heterogeneous repository difficulty remain
plausible contributors. Three additional C-short corrective turns followed
adverse evaluator outcomes and amplified context and time, so they are partly
a downstream consequence rather than an independent explanation.

## Limitations and forbidden broader interpretations

This report is limited by seven independent complete clusters, one missing
frozen cell, a broad interval, task leverage, one model/runtime configuration,
and a post-hoc mechanism analysis. It does not estimate language-specific
effects, maintainability, downstream work, user productivity, prevalence,
provider billing, or current behavior under newer Codex/model versions.

The study cannot support:

- a causal or population claim about minimality guidance generally;
- equivalence, non-inferiority, or an assertion that acceptance was maintained;
- interpreting the point estimate as a known causal quality decrement;
- treating every additional token, second, search, or turn as unnecessary;
- converting cached input into money without provider billing evidence;
- treating the post-hoc cluster mechanism as prospectively established;
- pooling the later final-scope-review experiment with this one;
- presenting a project retirement or research-only decision as an empirical
  effect.

Current applicability is not revalidated after any material change to Codex,
model, evaluator, task distribution, treatment bytes, or harness. The historical
observation remains versioned rather than being silently rewritten.

## Project decision

Engineering Scope Guard retired exact C-short v0.1 unchanged and did not
advance it to confirmatory execution. That project decision considered the
adverse acceptance direction, lack of input/wall reduction, the concrete
post-hoc pattern, and frozen governance. It applies only to this byte-exact
treatment in this research program; it is not a measured universal rule.
[`ESG-RR-001-C05`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

## What happened next — non-pooled context

A later materially different, late-stage Evidence-Conditioned Final Scope
Review treatment ended as a terminal partial exploratory schedule: 24 of 32
cells were admissible, eight were missing, and five task/repository clusters
were complete. Five prospectively frozen retirement gates fired: no accepted-
outcome mechanism, increased search, increased cached context, increased wall
or work, and structural-proxy-only apparent reductions. It was retired. It is
not a replication, is not co-primary here, and is not pooled with C-short.
[`ESG-RR-001-C06`](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json)

The subsequent thesis reassessment retained an evidence-first research project
and the existing local shadow measurement capability. A Track 1 audit found no
material incremental observability fact over native/local alternatives in its
tested scope. Those are historical project decisions, not extensions of the
C-short effect estimate.

## Reproducibility and public artifact manifest

### Level 1 — identity and integrity

From a clean checkout of tag `esg-rr-001-v0.6`, run:

```bash
PYTHONPATH=src python3 scripts/esg_rr_001_audit.py --level 1
```

The standard-library audit verifies SHA-256 identity for the exact treatment,
execution contract, pool, schedule, successor authorization, terminal result,
body-safe diagnostic, and claim ledger against
[`ESG-RR-001.manifest.json`](ESG-RR-001.manifest.json). It fails on a digest,
schema, or report-identity mismatch.

### Level 2 — independent core-analysis audit

From the same clean checkout, run:

```bash
PYTHONPATH=src python3 scripts/esg_rr_001_audit.py --level 2
```

This reads only tracked public-safe artifacts. It independently reconstructs
the seven task-level arm vectors from the body-safe cell diagnostic and uses
the repository's deterministic exact-bootstrap primitives to recompute paired
acceptance, all separated work measures and intervals, discordance counts,
cached/fresh decomposition, subject-turn totals, and leave-one-task-out ranges.
It checks the output against the terminal result, diagnostic, claim population,
and frozen artifact identities. No task body, raw trace, patch, account,
credential, or owner-local ledger is required.

### Level 3 — owner-only provenance

The maintainer can verify the tracked terminal result and body-safe diagnostic
against the controlled hash-chained ledger:

```bash
PYTHONPATH=src python3 scripts/pilot_v3_analysis.py \
  | cmp - experiment/pilot_v3_successor_terminal_result.json

PYTHONPATH=src python3 scripts/pilot_v3_mechanism.py \
  --output /tmp/pilot-v3-c-short-diagnostic.json

cmp /tmp/pilot-v3-c-short-diagnostic.json \
  experiment/pilot_v3_c_short_mechanism_diagnostic.json
```

Public readers cannot perform Level 3 because the raw ledger contains
controlled execution references. Hashes establish identity; they do not grant
access to hidden content or independently validate its provenance.

### Public artifact manifest

The package includes:

- this report and the machine-readable [claim ledger](../PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json);
- the [identity manifest](ESG-RR-001.manifest.json) and
  [`scripts/esg_rr_001_audit.py`](../../scripts/esg_rr_001_audit.py);
- exact [C-short bytes](../../experiment/arms/short.txt);
- the frozen [contract](../../experiment/pilot_v3_execution_contract.json),
  [pool](../../experiment/pilot_v3_pool.json),
  [schedule](../../experiment/pilot_v3_schedule.json), and
  [successor authorization](../../experiment/pilot_v3_successor_authorization.json);
- the body-free [terminal result](../../experiment/pilot_v3_successor_terminal_result.json)
  and body-safe [mechanism diagnostic](../../experiment/pilot_v3_c_short_mechanism_diagnostic.json);
- the canonical [disposition analysis](../C_SHORT_V0_1_DISPOSITION_AND_MECHANISM_ANALYSIS.md),
  [terminal report](../PILOT_V3_SUCCESSOR_TERMINAL_REPORT.md), analysis code,
  tests, [evidence policy](../EVIDENCE_POLICY.md), and
  [editorial policy](../PUBLICATION_AND_EDITORIAL_POLICY.md).

### Controlled and non-reproducible boundaries

The owner-local ledger, raw prompts/messages/reasoning, JSONL traces, commands
and output, prediction patches, evaluator output, execution roots, credentials,
provider request/account/billing metadata, task bodies, and held-out reserve
remain controlled and are not release assets. The package does not enable
trajectory replay, historical provider-cache recreation, billing reconstruction,
private receipt inspection, or recovery of withheld benchmark content.

The dataset/evaluator source and underlying repositories retain their own
license terms. This package links identities and canonical upstream sources; it
does not republish task bodies, repositories, benchmark tests, prediction
patches, or controlled evaluator material.

## Conflict disclosure and mitigations

The project author/maintainer also authored or directed the intervention and
substantial parts of the evaluation and research process. This work is not an
independent replication, and no employer, institution, academic organization,
or vendor sponsorship or endorsement is claimed.

Mitigations included frozen protocols and byte identities, external task
sampling, repository-distinct task-level analysis, deterministic official-
evaluator outcome handling, bounded retry/missingness rules, arm isolation,
preservation of negative/null/discordant evidence, exact exhaustive bootstrap
calculation, deterministic public analysis, an explicit claim ledger, and
controlled/public artifact boundaries. These mitigations reduce discretion;
they do not create investigator independence.

## Corrections and versioning

`ESG-RR-001` is the stable report ID. Version `0.1` is the original published
report; version `0.2` corrects publication-provenance terminology only; version
`0.3` republishes the same scientific report after repository-history privacy
sanitation; version `0.4` republishes it under an independent repository
identity; version `0.5` corrects repository Git author metadata; and version
`0.6` republishes the unchanged scientific record under the clean canonical
repository identity.
Material corrections increment the report version and add publication and
correction dates, old and new wording, reason, affected artifacts, and impact
on the conclusion to [`docs/CLAIMS_CHANGELOG.md`](../CLAIMS_CHANGELOG.md).
Superseded versions remain discoverable and link forward. Minor non-material
link or spelling fixes may be repaired in place without changing the research
meaning. New evidence creates a new evidence record; it does not rewrite this
historical observation.

## Citation

> Çağdaş Yürekli. *An Exploratory Test of a Minimality Prompt in Coding
> Agents.* Engineering Scope Guard Research Report ESG-RR-001, version 0.6.
> Published 2026-08-31; evidence cutoff 2026-08-29. Repository:
> `https://github.com/cagdasyurekli/engineering-scope-guard`. Report commit:
> annotated version tag `esg-rr-001-v0.6` (full commit SHA and immutable state
> recorded by the GitHub Release). Claim-ledger SHA-256:
> `9fc57757c8fd5bac337eff30961196e5e14c5300237a296c7c5a4cf0815be847`.
