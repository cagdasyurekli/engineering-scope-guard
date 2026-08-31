# Evidence-Conditioned Final Scope Review v0.1 — Exact-Bytes Qualification

**Date:** 2026-08-29

**Status:** terminal exact-bytes qualification; no experimental execution

## Decision

**EXACT TREATMENT BYTES QUALIFIED — EXPLORATORY EXPERIMENT DESIGN REQUIRES
SEPARATE AUTHORIZATION**

Exactly one wording survived the semantic and complexity audits. It is frozen
as **Evidence-Conditioned Final Scope Review v0.1**, a member of a new
late-stage treatment family materially distinct from C-short and D.

Qualification establishes wording fidelity and identity only. It does not
establish efficacy, quality preservation, work reduction, an experimental arm,
an exploratory design, task eligibility, or execution authority.

## Frozen identity

- Authoritative bytes:
  `experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt`
- Encoding: UTF-8 without a byte-order mark.
- Newlines: LF only, with exactly one terminal LF and no other normalization.
- Byte length: 740.
- Word count under whitespace splitting: 93.
- SHA-256:
  `d9ac9e18716428e9cd6d038388b01ec668ade47df8bac014658897752166b8cb`

The artifact, not a retyped quotation in this report, is the byte authority.
Loading uses raw bytes. The deterministic test decodes and re-encodes UTF-8,
rejects carriage returns or multiple terminal newlines, compares all 740 bytes
with a frozen literal, and recomputes the digest. Whitespace must not be
normalized after this identity.

## Complexity audit

The treatment is one paragraph of four compact sentences. It exposes no
heading, checklist, score, stage framework, taxonomy, example, size target, or
reuse/minimality proof. Its behavioral structure is limited to:

1. one late activation condition;
2. one support-and-keep rule;
3. one narrow removal boundary with no broad search; and
4. one failure/no-op rule.

The wording stands on its own. It does not require the longer candidate-design
report to tell an agent what to do. The longer report remains the audit trail,
not hidden operational instructions.

## Sentence-level semantic audit

### Sentence 1 — timing

The opening makes ordinary interpretation, exploration, implementation,
debugging, and necessary correctness/integration work antecedents to the one
final review. Plausible correctness and consideration or feasible execution of
relevant checks are explicit activation conditions. It does not tell the agent
to narrow, reuse, minimize, or review while discovering the solution.

**Timing result:** pass. No sentence creates a pre-correctness scope constraint.

### Sentence 2 — support and keep-by-default

Support may come from requirements, repository evidence, relevant checks, or
necessary correctness, integration, safety, or security. Literal task wording
is therefore not the sole support source. Uncertain, entangled, and risky-to-
remove work is explicitly kept.

**Literal-minimality result:** pass. The wording does not say to implement only
what was explicitly requested, avoid all unstated work, or make the smallest
possible change.

**Correctness-inference result:** pass. Adjacent correctness, integration,
shared-cause, safety/security, and relevant-test work can be supported without
being literal requirements.

**Keep-by-default result:** pass. Uncertainty resolves toward the working
implementation.

### Sentence 3 — search and action boundary

The review may act only on task-introduced additions that are both clearly
separable and unsupported, and only while correctness confidence is preserved.
It explicitly forbids broad new searching. It neither requires reuse discovery
nor rewards lines, files, dependencies, tests, tokens, reasoning, or response
length.

**Search-tax result:** pass. No broad reuse, alternative, dependency, or
architecture search is requested or incentivized.

**Action-boundary result:** pass. Unsupported status alone is insufficient;
safe separability and preserved correctness confidence are also required.

**Proxy-avoidance result:** pass. No size or work-count proxy appears.

### Sentence 4 — failure and no-op

A relevant failure or correctness uncertainty routes the agent back to normal
debugging and validation rather than toward deletion. Finding no eligible work
is explicitly valid, so the review does not require a visible reduction.

**Failure/no-op result:** pass.

## Deterministic adversarial interpretation fixtures

The machine-readable fixtures are frozen in
`experiment/evidence_conditioned_final_scope_review_v0_1_semantic_fixtures.json`.
They are abstract semantic cases and contain no experimental task body. Tests
protect the exact nine identifiers and outcomes. These fixtures freeze the
prospective interpretation judgment; they do not claim to measure how a model
will behave.

| Fixture | Expected induced behavior |
| --- | --- |
| Narrow requirement plus adjacent correctness edge case | Complete and keep the edge-case work as necessary correctness. |
| Justified shared-root-cause fix | Fix and keep the evidenced shared cause rather than narrowing to a literal call site. |
| Speculative abstraction | Remove or simplify only when unsupported status, separability, and safety are clear. |
| Unrelated refactor | Remove or revert only when clearly separable and confidence-preserving. |
| Relevant failing test at review point | Suspend the review and continue ordinary debugging/validation. |
| Uncertain, entangled supporting work | Keep it. |
| Already-known repository mechanism | Use existing evidence; remove duplicate machinery only if clear and safe, without a broad search. |
| Reuse proof would require broad search | Do not search broadly; keep the working addition. |
| Correct implementation with nothing unnecessary | Make no change. |

No fixture induces up-front narrowing or a proof-of-minimality obligation.

## Material distinction and historical boundary

This treatment is not `C-short v0.2`, a revision of C-short v0.1, or a revision
of D v0.1.

- C-short v0.1 remains retired unchanged under D-046. Its byte-exact identity
  and historical observations remain attached only to C-short v0.1.
- D v0.1 remains rejected/excluded under D-017 and D-018. It is not restored as
  a dose control or alternate arm.
- Evidence-Conditioned Final Scope Review v0.1 belongs to a different late-
  stage family: C-short constrained discovery up front, while this treatment
  waits for plausible correctness and relevant checks, recognizes inferred
  correctness/integration support, forbids broad search, and keeps uncertainty.
- Pilot-v3 remains mechanism-generating exploratory evidence only. No Pilot-v3
  observation is relabeled as evidence for this treatment, and no known task
  body was used to tune the wording.

## Frozen prospective retirement gates

This identity incorporates D-047's already-qualified retirement logic without
new numerical margins or minimum clinically important differences. A future,
separately authorized exploratory experiment should retire this exact treatment
if it shows any of the following:

- replicated suppression or removal of necessary correctness work;
- adverse acceptance without a prospectively legitimate countervailing benefit;
- no evidence-grounded unnecessary-work reduction among accepted outcomes;
- increased corrective-round frequency;
- increased search activity;
- increased repeated or cached context ingestion;
- increased wall work;
- apparent benefit only through smaller-looking patches or other size proxies;
- pre-activation changes to ordinary discovery, correctness, integration,
  shared-cause, or validation work;
- behavior materially equivalent to C-short's up-front restriction; or
- broad proof-of-minimality search or review complexity inconsistent with one
  bounded final check.

These are retirement gates, not an exploratory design. This goal does not
define tasks, arms, schedule, sample size, randomization, outcome analysis,
evaluator semantics, or execution rules.

## Authorization and execution accounting

This goal made zero Codex/provider experimental subject calls, zero evaluator
calls, zero policy comparisons, and zero experimental observations. It did not
inspect confirmatory reserve task bodies, select or freeze a task pool, create
Pilot-v4, alter baseline or prior treatment bytes, change model/reasoning, or
begin exploratory or confirmatory design.

After the authorized GitHub stabilization, stop. Any exploratory experiment
design, task work, freeze, provider/evaluator use, or execution requires fresh
explicit authorization.
