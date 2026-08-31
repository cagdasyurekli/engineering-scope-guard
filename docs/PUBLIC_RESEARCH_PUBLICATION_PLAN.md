# Public Research Publication Plan

**Decision date:** 2026-08-30

**Evidence cutoff:** 2026-08-29

**Scope:** publication planning only; no external publication or channel is
authorized

## Decision summary

The first public artifact should be one focused, versioned research report on
the C-short v0.1 exploratory program. Its working title is:

> **An Exploratory Test of a Minimality Prompt in Coding Agents**

The report should lead with accepted outcome, then work, uncertainty, mechanism
limits, and retirement. It may describe the later Evidence-Conditioned Final
Scope Review and Track 1 only in a short, explicitly non-pooled “what happened
next” section.

The first release should be GitHub-only: one canonical report, a claim ledger,
tracked body-safe evidence, exact treatment bytes, analysis code, correction
history, and a tagged/released immutable snapshot if later authorized. No
secondary publication or distribution surface is needed to make this first
result understandable or durable.

This selection is not a product launch and does not claim that minimality
prompts generally harm agents. It preserves the current binding decision:

> **NO NEW LIVE EXPERIMENT JUSTIFIED — MAINTAIN/PUBLISH EXISTING EVIDENCE**

## Publication purpose

The report should teach critical coding-agent literacy through one bounded
case:

- a shorter trajectory is not automatically a better trajectory;
- tokens, files, and LOC are not benefits without a correct or accepted outcome;
- a plausible instruction can fail on external tasks;
- adverse and null evidence can justify retirement rather than prompt tuning;
- exploratory results remain model, runtime, task, evaluator, and date scoped;
- a project decision is not an empirical effect.

The editorial commitments remain:

> We optimize for being correct and useful, not for being interesting.

> A boring null result is better than an exciting false claim.

## Publication-readiness audit

### C-short v0.1

**Publishable empirical claim.** In one exploratory paired study using Codex
CLI 0.150.1, `gpt-5.6-terra` at medium reasoning, and seven complete public
SWE-bench-Live/MultiLang task clusters with two repetitions per arm, C-short
minus baseline acceptance was -14.3 percentage points, with an exact
task-bootstrap 95% percentile interval from -50.0 to +14.3 points. C-short's
paired input-token ratio was 1.223 (1.012-1.448), and its wall-time ratio was
1.326 (1.052-1.575).

**Required context.** The frozen 32-cell schedule ended with 31 admissible cells
and one missing cell after two coherent infrastructure-invalid attempts. The
paired estimand uses 28 cells from seven complete task clusters. The incomplete
slot remains in marginal summaries and is not imputed. Acceptance came before
work in the analysis and must do so in the report.

**Mechanism status.** One task cluster showed a replicated baseline-only
acceptance pattern consistent with post-hoc literal-minimality interference.
Higher completed web search and cached input support a secondary search-tax
hypothesis. Neither mechanism was prospectively isolated or causally
established. One pair favored C-short, several were null, and those observations
must remain visible.

**Uncertainty and limitations.** Seven independent task clusters are too few
for a population effect, language subgroup, equivalence, non-inferiority,
quality-preservation, maintainability, downstream-work, or general agent claim.
The task-bootstrap interval includes both meaningful harm and a smaller
advantage. Provider billing was unavailable and must not be inferred.

**Project decision.** Retiring exact C-short v0.1 is a project decision based on
the adverse quality direction, lack of work reduction, mechanism evidence, and
frozen governance. It is not a claim that all minimality guidance is harmful.

**Reproducibility.** Exact treatment bytes, pool, schedule, contract, terminal
result, body-safe cell-level diagnostic, deterministic analysis code, tests,
and the report are tracked. The owner-local hash-chained ledger can be
cryptographically bound but not published because it contains controlled
execution references. A reader can independently recompute the core paired
quantities from the public body-safe diagnostic; full receipt-to-diagnostic
regeneration remains owner-verifiable only.

### Evidence-Conditioned Final Scope Review v0.1

**Publishable bounded claim.** A materially different late-stage treatment
reached a terminal partial exploratory schedule: 24/32 cells were admissible,
eight cells were missing, and five task/repository clusters were complete.
Treatment-minus-baseline paired acceptance was +0.1 with an exact task-bootstrap
95% percentile interval from 0.0 to 0.3. Five prospectively frozen retirement
gates fired: no accepted-outcome mechanism, increased search, increased cached
context, increased wall/work, and structural-proxy-only apparent reductions.

**What cannot be claimed.** The partial schedule does not establish
superiority, equivalence, non-inferiority, universal quality preservation,
maintainability, downstream work, billing, or savings. It did not demonstrate
that optional work was safely removed in jointly accepted outcomes. Its higher
acceptance point estimate does not negate the independent mechanism/work gates.

**First-package role.** This is follow-up context, not a second co-primary
study. Pooling it with C-short would combine different treatments, runtimes,
task identities, missingness, and mechanisms. A later separate report may be
considered only if the owner-local ledger boundary and opaque task commitments
can be explained without implying independent full reproduction.

### Track 1 — Shadow Observability Gap Audit

**Evidence.** V0 reliably produces privacy-bounded structural deltas and
coverage-health diagnostics with low small-fixture machine overhead and zero
target mutation in the tested fixture.

**Negative product result.** No material incremental workflow fact survived
comparison with Git, manifests, tests/CI, native Codex events, and existing
observability tools. V0 does not reliably observe repeated reads/searches,
correction or state recovery, tool-selection quality, or accepted outcomes.

**Limit.** No Codex 0.151.0 live canary was authorized; the audit separates
documented/installed capability, earlier 0.150.1 live evidence, fixture-only
coverage, and unknown live behavior. “Retain research-only” is a product
decision, not proof that observability gaps never exist.

### Project thesis reassessment

Public communication must label four different statement types:

| Type | Example |
| --- | --- |
| Evidence | C-short's paired acceptance estimate and work ratios in the tested sample |
| Research interpretation | Work per correct or accepted outcome is more useful than raw token minimization |
| Project decision | Retire both treatments; retain the repository as evidence-first research |
| Future hypothesis | Context continuity or instruction placement might matter under a different, separately justified study |

No project strategy decision may be presented as an empirical result. No future
hypothesis is a recommendation or an authorization to run another study.

## First-artifact options

The assessment is qualitative; numeric scoring would add false precision.

| Option | Scientific usefulness and evidence | Reproducibility and privacy | Reader/maintenance burden | Adversarial disposition |
| --- | --- | --- | --- | --- |
| 1. C-short report | One clear question; complete paired population; adverse and null cases; bounded post-hoc mechanism | Strongest public-safe package; public task IDs and body-safe cell metrics; raw ledger remains controlled | Lowest prerequisite and maintenance burden | **Selected** if title and abstract remain explicitly exploratory |
| 2. Two-intervention report | Shows refinement and falsification, but risks turning two exploratory programs into a causal progression | Second study is partial, task commitments are opaque, and raw ledger is controlled | Higher explanation burden; easy to over-narrativize | Reject as first artifact; later synthesis only |
| 3. Program synthesis | Accurately represents the whole project and its no-build decisions | Mixes empirical, literature, and strategic evidence classes | Broadest scope and highest folklore risk | Reject as first artifact; useful only after canonical component reports exist |
| 4. Evidence review first | Broad educational value and visible contradictions | Sources are linkable, but fast-moving evidence requires repeated revalidation | Highest ongoing maintenance and least distinctive | Reject as first artifact |
| 5. Do not publish yet | Avoids overclaim risk | Leaves an auditable negative result difficult to discover | Lowest immediate work but loses durable educational value | Reject because Option 1 survives with explicit bounds |

Option 1 remains useful without external promotion: it preserves an adverse
result, demonstrates outcome-before-efficiency analysis, and gives another
researcher enough public-safe cell-level evidence to audit the core conclusion.

## Adversarial publication review

1. **Too exploratory?** It is too exploratory for a general efficacy claim,
   but not for a labeled exploratory report whose conclusion is retirement.
2. **Sample too small?** It is too small for population inference. The report
   must state `N=7` complete independent clusters and show the broad interval.
3. **Missingness misleading?** One cell is missing. The paired population is
   complete by construction; marginal 31-cell results and the missing slot must
   still be reported.
4. **Mechanism post-hoc?** Yes. The report may say “consistent with” and must
   show evidence against/limits; it may not say “caused by.”
5. **Folklore risk?** Material. Neutral title, claim ledger, forbidden phrases,
   scope block, and no prescriptive call-to-action are mandatory.
6. **Literature review more useful?** Not as the first artifact. The project's
   own auditable negative result is more distinctive and lower-maintenance.
7. **Interesting rather than correct?** The package is selected because its
   evidence boundary is clearer than the broader options, not because the
   adverse direction is dramatic.
8. **Enough reproducibility?** Enough to audit the core paired conclusion;
   insufficient for public replay of raw trajectories. That limitation must be
   prominent.
9. **Controlled evidence protected?** Yes if raw ledgers, traces, prompts,
   patches, task bodies, local paths, credentials, and private reserve IDs stay
   unpublished.
10. **GitHub sufficient?** Yes for the first release.
11. **Secondary archive premature?** Yes. It duplicates canonical material and
    creates maintenance before repeated publication exists.
12. **Name bias?** `Engineering Scope Guard` can imply a product, but the
    working-title warning and research-only status sufficiently bound the first
    report. Renaming now would break research continuity without evidence of a
    supported replacement.

## Publication-level claim control

The canonical structured ledger is
[`PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json`](PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json).
It separates empirical claims, post-hoc mechanisms, research interpretations,
and project decisions; binds source artifacts; records scope, uncertainty,
contradictions, forbidden interpretations, and expiry.

The following phrases are not allowed:

- “minimality prompts make coding agents worse”;
- “Scope Guard saves tokens”;
- “coding agents waste X% of their tokens”;
- “we proved overengineering can be prevented”;
- “our tool detects wasted work”;
- “no quality loss” or “quality preserved” for either intervention;
- “C-short caused extra search”;
- “the final scope review improved quality”;
- “AI agents should never use large context”;
- “native tools solve observability”;
- “the project proved no product is needed.”

## Research archive decision

### GitHub-only — selected

Use the repository as the canonical source of truth. A future authorized release
should link the report version, claim ledger, exact treatment, body-safe data,
analysis code, methods, evidence policy, and corrections history. Git history
and immutable release assets support citation and correction provenance without
duplicating evidence.

### Secondary archive — deferred

Consider only after at least two canonical reports exist or readers cannot
reasonably navigate the evidence. Its job would be discoverability and reading
comfort, never to become a second evidence authority.

### Expanded external publication surface — rejected for now

It would create content-parity and maintenance work without improving the first
claim's auditability.

## External presentation boundary

Any future external presentation requires a separate project decision and must
point to the canonical report rather than become the evidence source. It must
preserve the claim ledger, citations, correction route, reproducibility links,
and caveats. This plan does not retain a channel roadmap or operational
sequence.

## Public identity

Intentionally public author and citation metadata are maintained in `CITATION.cff`.
## Corrections and versioning workflow

- Stable report ID: `ESG-RR-001`.
- Initial report version: `0.1`; version is independent of repository release
  numbering.
- Every publication records publication date, evidence cutoff, report commit,
  claim-ledger digest, and linked artifact digests.
- Material corrections increment the report version and add correction date,
  old claim, new claim, reason, affected artifacts, and conclusion impact to
  `docs/CLAIMS_CHANGELOG.md`.
- Superseded versions remain discoverable and link forward; they are not
  silently overwritten.
- A new model/runtime marks behavioral claims `revalidation_required`; it does
  not rewrite the historical result.
- Later contradictory evidence attaches to the relevant claim ID and receives
  equal prominence.
- A replication creates a new evidence record and may update current status;
  it does not replace the historical 2026-08-29 observation.

## Authorization boundary

This plan creates no public report, release, or external distribution action.
External publication requires fresh explicit authorization.

## Terminal decision

**FIRST PUBLIC RESEARCH PACKAGE JUSTIFIED — EXTERNAL PUBLICATION REQUIRES SEPARATE AUTHORIZATION**
