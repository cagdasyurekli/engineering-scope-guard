# First Public Research Package Specification

**Package ID:** `ESG-RR-001`

**Planned version:** `0.1`

**Status:** specified, not published

**Evidence cutoff:** 2026-08-29

## Package decision

Create one focused research package about C-short v0.1. Do not combine the two
interventions into one estimand or present the later final-scope review as a
replication. The package should remain valuable as a durable negative-result
record without relying on external promotion.

Working title:

> **An Exploratory Test of a Minimality Prompt in Coding Agents**

The report is not a recommendation to use or avoid minimality instructions. It
is a transparent account of one exact treatment, one frozen external-task
sample, the observed accepted-outcome/work directions, uncertainty, post-hoc
mechanism evidence, and the decision to retire the treatment.

## Exact report claim

> In an exploratory paired study using Codex CLI 0.150.1 and
> `gpt-5.6-terra` at medium reasoning, seven complete SWE-bench-Live/MultiLang
> task clusters with two repetitions per arm produced a C-short-minus-baseline
> acceptance estimate of -14.3 percentage points (exact task-bootstrap 95%
> percentile interval -50.0 to +14.3). C-short used more provider-reported input
> tokens and wall time at the paired point estimate: ratios 1.223 (1.012-1.448)
> and 1.326 (1.052-1.575), respectively. The small exploratory sample cannot
> establish a general causal effect, equivalence, non-inferiority, or preserved
> quality.

## Small draft abstract

Coding-agent guidance often treats shorter solutions and fewer tokens as
obvious improvements, but those measures matter only alongside a correct or
accepted outcome. We tested one exact minimality instruction, C-short v0.1,
against an unmodified baseline on a frozen external-task sample. The exploratory
paired acceptance estimate was adverse and the treatment did not reduce input
or wall work. One replicated task pattern was consistent with a post-hoc
literal-minimality mechanism, while another pair favored treatment and several
were null. We retired the treatment rather than tune it against viewed tasks.
The result is model-, runtime-, task-, evaluator-, and date-specific and should
not be generalized to all coding agents or all minimality guidance.

## Audience and reader prerequisites

Primary readers are software engineers, agent-tool builders, and empirical
software-engineering researchers who need to evaluate coding-agent claims.
The main text should require no knowledge of the repository's full experiment
history. A methods appendix may assume familiarity with paired designs,
percentile intervals, and deterministic test-based acceptance.

The report should explain in plain language:

- why task/repository is the independent unit rather than each run;
- why a wide interval is not proof of “no difference”;
- why cached input, fresh input, output, and reasoning output stay separate;
- why a post-hoc mechanism can guide interpretation but not prove causality;
- why treatment retirement is a project decision rather than a universal rule.

## Durable report structure

1. Report identity, version, date, evidence cutoff, author, and correction link.
2. Research question: does exact C-short v0.1 change work to accepted outcome?
3. Why accepted outcome comes before token or structural reduction.
4. Prior evidence and why C-short was a reasonable exploratory candidate.
5. Frozen methodology: arms, selection, schedule, runtime, evaluator, retry and
   missingness rules.
6. Sample scope: eight public tasks/repositories, seven complete paired task
   clusters, 28 paired cells, and 31 admissible marginal cells.
7. Outcome definitions and evidence classes.
8. Acceptance results and uncertainty before work results.
9. Input, cached/fresh input, output, reasoning, wall time, turns, search, and
   structural diagnostics.
10. Discordant/null pairs and repetition stability.
11. Post-hoc mechanism analysis, evidence against, and alternative explanations.
12. Missingness, leverage, leave-one-task-out sensitivity, and other limitations.
13. What the study does not show and the forbidden broader interpretations.
14. Project decision: retire exact C-short v0.1 unchanged.
15. What happened next: brief non-pooled note on the later retired intervention,
    thesis reassessment, and Track 1 no-material-gap decision.
16. Reproduction and independent-audit instructions.
17. Claim ledger and source/artifact manifest.
18. Conflict disclosure, corrections, version history, and citation format.

## Required result presentation

Acceptance must appear before work. At minimum include:

| Result | Baseline | C-short | Paired estimate and uncertainty |
| --- | ---: | ---: | --- |
| Acceptance, complete clusters | 42.9% | 28.6% | -14.3 percentage points; 95% interval -50.0 to +14.3 |
| Input-token task mean | 1,151,616 | 1,408,131 | ratio 1.223; 95% interval 1.012-1.448 |
| Wall-time task mean | 739 s | 981 s | ratio 1.326; 95% interval 1.052-1.575 |

Also report:

- marginal acceptance 6/15 baseline and 4/16 C-short;
- 14 complete repetition pairs: three both accepted, seven both failed, three
  baseline-only, and one C-short-only;
- 20 baseline versus 23 C-short subject turns;
- 96.2% of the aggregate paired input difference was cached input;
- leave-one-task-out acceptance differences from -25.0 to 0.0 percentage points,
  input ratios 1.112-1.279, and wall ratios 1.185-1.387;
- provider billing amount and currency unavailable.

No chart may use a truncated axis or omit the uncertainty/quality context. A
table is sufficient for the first release; a chart is optional only if it makes
task heterogeneity clearer.

## Reproducibility levels

### Level 1 — Identity and integrity

A reader should verify exact treatment bytes and SHA-256 identities for the
contract, pool, schedule, successor authorization, terminal result, and
body-safe diagnostic using ordinary repository tools.

### Level 2 — Independent core-analysis audit

Using `experiment/pilot_v3_c_short_mechanism_diagnostic.json`, a reader should
recompute the seven-cluster paired acceptance difference, input/wall ratios,
exact task bootstrap, discordance counts, cached/fresh decomposition, and
leave-one-task-out ranges without raw prompts, traces, patches, or task bodies.
The package should give exact standard-library commands or a small public-safe
reproduction entry point before external publication. Adding that convenience
entry point is reproducibility preparation, not a new experiment.

### Level 3 — Owner-only provenance verification

The maintainer can run:

```bash
PYTHONPATH=src python3 scripts/pilot_v3_analysis.py \
  | cmp - experiment/pilot_v3_successor_terminal_result.json

PYTHONPATH=src python3 scripts/pilot_v3_mechanism.py \
  --output /tmp/pilot-v3-c-short-diagnostic.json
```

against the owner-local hash-chained ledger, then compare the regenerated
diagnostic. A public reader cannot perform this level because the raw ledger is
controlled. The report must say so prominently; cryptographic hashes establish
identity, not independent access to the hidden content.

### Not reproducible from public evidence

- replaying the original provider trajectories;
- inspecting model reasoning or full transcripts;
- independently validating raw receipt contents against private execution roots;
- reproducing historical provider-side caching, billing, or model snapshots;
- inferring missing task bodies or the held-out confirmatory reserve.

## Artifact classification

### Public-safe

| Artifact | Publication use |
| --- | --- |
| `docs/C_SHORT_V0_1_DISPOSITION_AND_MECHANISM_ANALYSIS.md` | Canonical interpretation and limitations |
| `docs/PILOT_V3_SUCCESSOR_TERMINAL_REPORT.md` | Execution completeness, missingness, paired results |
| `experiment/arms/short.txt` | Exact treatment bytes |
| `experiment/pilot_v3_execution_contract.json` | Frozen runtime, arms, rules, evaluator and analysis identity |
| `experiment/pilot_v3_pool.json` | Public task/repository identities and metadata-only selection |
| `experiment/pilot_v3_schedule.json` | Cell allocation, repetitions, and counterbalancing |
| `experiment/pilot_v3_successor_authorization.json` | Preserved lineage and attempt accounting |
| `experiment/pilot_v3_successor_terminal_result.json` | Body-free terminal and paired aggregate evidence |
| `experiment/pilot_v3_c_short_mechanism_diagnostic.json` | Body-safe cell/task metrics and sensitivity audit |
| `src/engineering_scope_guard/pilot_v3_analysis.py` and wrapper scripts | Deterministic analysis implementation |
| relevant tests | Statistical, parsing, ledger, privacy, and regeneration behavior |
| `docs/EVIDENCE_POLICY.md` and `docs/PUBLICATION_AND_EDITORIAL_POLICY.md` | Claim and correction rules |
| `docs/PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json` | Exact public claim bounds |

The dataset/evaluator records an MIT license basis, while underlying source
repositories retain their own licenses. The package should link identifiers and
source provenance rather than republish task bodies, source, tests, or patches.
Recheck upstream license/terms and canonical links immediately before external
publication.

### Public-safe after deterministic sanitization

| Artifact class | Required transformation |
| --- | --- |
| Reproduction command output | Retain only hashes, counts, pass/fail state, and bounded diagnostics; remove local absolute paths |
| CI/CodeQL evidence | Link stable public checks or release commit; do not copy tokens, runner paths, or private logs |
| Optional figures/tables | Generate only from the tracked body-safe diagnostic; include claim IDs and evidence cutoff |
| Source/task links | Link public repository/task identity after license and URL revalidation; copy no task body |

### Private/controlled

| Artifact class | Reason |
| --- | --- |
| `.local/pilot-v3-successor/pilot-v3-successor-ledger.jsonl` | Controlled execution references and raw receipt provenance |
| raw Codex JSONL, prompts, messages, commands/output, and traces | May contain task content, reasoning, source, local paths, or credentials |
| raw prediction patches/diffs and evaluator output | Task/repository licensing, controlled benchmark content, and source disclosure risk |
| temporary repositories, Codex homes, credentials, and execution roots | Secrets and local identity |
| remaining confirmatory task/repository IDs or bodies | Held-out control and contamination boundary |
| provider account, billing, cache, or request metadata beyond tracked aggregates | Privacy and unsupported monetary inference |

### Outside the research package

External publication and distribution channels are outside the scientific record and require separate project decisions.
## Claim ledger requirements

The machine-readable ledger must be shipped beside the report and treated as
the canonical public claim scope. Each empirical number in the abstract,
summary, table, figure, or explainer must cite a claim ID. The initial ledger
contains:

- the paired acceptance claim;
- the paired work claim;
- the cached-input decomposition;
- the post-hoc literal-minimality mechanism;
- the C-short retirement decision;
- the later final-scope-review context;
- the research interpretation that outcome precedes raw efficiency proxies.

If a new public claim cannot be represented with source, class, scope, unit,
repetitions, outcome, estimate, uncertainty, mechanism status, contradictions,
limits, forbidden interpretations, expiry, and canonical artifact, it is not
ready for publication.

## Corrections, expiry, and citation

Suggested citation identity:

> cagdasyurekli. *An Exploratory Test of a Minimality Prompt in Coding Agents.*
> Engineering Scope Guard Research Report ESG-RR-001, version 0.1, evidence
> cutoff 2026-08-29.

Confirm the author's preferred display name before external publication. Every
release should record the report commit and claim-ledger digest. Corrections
follow `docs/PUBLICATION_AND_EDITORIAL_POLICY.md` and
`docs/CLAIMS_CHANGELOG.md`. A new Codex/model/runtime does not invalidate the
historical observation; it marks current applicability as not revalidated.

## Pre-publication gate

External publication is allowed only under fresh explicit authorization after:

1. the full report exists and matches the approved claim ledger;
2. Level 1 and Level 2 public-reader instructions run from a clean checkout;
3. the owner-only Level 3 regeneration matches the tracked artifacts;
4. source URLs, peer-review/evidence classes, dataset/evaluator license, and
   underlying repository-link treatment are revalidated;
5. internal links, JSON, tests, privacy, bounded changed-file secret scanning,
   CI, and CodeQL pass;
6. author identity, conflict disclosure, correction route, and citation text
   are explicit;
7. the title, abstract, summary, tables, figures, and any call-to-action stay
   within the claim ledger;
8. no raw/controlled artifact enters Git history or release assets.

## Authorization boundary

This specification is not the public report and does not authorize a release,
tag, external publication/distribution action, another experiment, or a change
to any frozen evidence.
