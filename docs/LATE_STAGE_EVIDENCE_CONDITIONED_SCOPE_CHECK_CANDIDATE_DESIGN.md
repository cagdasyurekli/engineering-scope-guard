# Late-Stage Evidence-Conditioned Scope Check — Candidate Design

**Date:** 2026-08-29

**Status:** terminal design qualification; no treatment bytes

## Decision

**CANDIDATE CONCEPT QUALIFIED — EXACT BYTES REQUIRE SEPARATE AUTHORIZATION**

Exactly one concept survives: an **Evidence-Conditioned Final Scope Review**.
It is a single bounded review after ordinary implementation and relevant
validation. It considers only additions introduced for the current task and
challenges only clearly separable engineering whose support is absent from the
requirement, repository evidence, or relevant checks. It keeps a justified
working implementation by default and creates no duty to search broadly for a
smaller or reusable alternative.

This is a conceptual specification, not text to inject into an agent. No exact
or candidate wording is supplied, implied to be frozen, or authorized for use.

## Evidence discipline

### Evidence inherited from Pilot-v3

- The frozen terminal result was previously reconciled byte for byte from the
  validated 288-event ledger. Seven complete task clusters produced a C-short
  minus baseline acceptance point estimate of -14.3 percentage points, paired
  input ratio 1.223, and paired wall-time ratio 1.326.
- One public task cluster produced the same baseline-only acceptance pattern in
  both repetitions. C-short made the same narrower change and omitted an
  adjacent missing-state case that baseline handled. This pattern is concrete
  but confined to one cluster.
- C-short used three more corrective turns. Of its aggregate paired input
  increase, 96.2% was cached input. It did not materially reduce command,
  search, file-change, or final-patch-file activity.
- C-short had more completed web searches and somewhat more local read/search
  activity, with substantial heterogeneity. Trace types do not reveal why a
  search occurred.
- One pair favored C-short and several pairs were null. These observations
  remain evidence against a universal harm explanation.

### Mechanism hypothesis

Up-front literal-minimality and reuse obligations may interfere with ordinary
correctness/integration inference and may add search/context work. Applying a
scope intervention only after plausible correctness and relevant validation
may affect late optional additions without suppressing necessary work.

This hypothesis is post-hoc. Pilot-v3 did not randomize intervention timing or
independently manipulate literal-minimality and reuse clauses, so it does not
establish causality.

### Design inferences

- Moving the intervention after relevant validation is the smallest direct way
  to avoid constraining solution discovery while still testing whether a scope
  review can remove unsupported optional engineering.
- A keep-by-default, clearly-separable threshold is necessary because cleanup
  after validation can itself introduce correctness risk.
- Limiting evidence to what normal work already produced directly addresses the
  plausible reuse/search tax without requiring a second exploration phase.
- Lines, files, dependencies, tests, tokens, and response length cannot decide
  whether work was unnecessary; support and correctness evidence must decide.

### Unsupported assumptions

- A late-stage review will actually reduce unnecessary engineering.
- Agents can reliably distinguish unsupported optional work from necessary
  inferred correctness work using a compact concept.
- The review's own work will cost less than any work it removes.
- A clearly separable unnecessary addition occurs often enough to measure.
- The concept will generalize beyond the task distribution eventually used in
  a separately authorized exploratory experiment.

Qualification means only that these assumptions are falsifiable without
recreating C-short's up-front mechanism. It is not an efficacy claim.

## Concepts considered

1. **Up-front softened minimality. Rejected.** Softer language would still
   influence discovery, scope inference, adjacent correctness, and reuse before
   correctness is established. It is C-short's mechanism with reduced force,
   not a materially distinct concept.
2. **Late structural threshold or score. Rejected.** File, line, dependency, or
   complexity thresholds would reward smaller-looking patches and require a
   rule system without establishing that the challenged work is unnecessary.
3. **Warn-only late review. Rejected.** A warning could identify optional work
   but would not test whether clearly unsupported engineering can be removed
   safely. It also risks producing commentary without changing agent work.
4. **Evidence-Conditioned Final Scope Review. Selected.** It changes timing and
   decision basis, preserves normal implementation, and permits action only on
   clearly unsupported and separable additions.

No alternative arm or wording variant is retained.

## Conceptual specification

### 1. Activation

The review activates once, near task completion, only when all of the following
are true:

- the agent has an implementation it considers plausibly correct;
- checks relevant to the changed behavior have been run when available and
  feasible, and their results have been inspected;
- no known relevant failure, unresolved correctness question, or active debug
  hypothesis remains; and
- enough existing task/repository/check evidence exists to judge the support
  for task-introduced additions without a broad new search.

Passing every repository-wide check is not required when such checks are
unavailable, infeasible, or irrelevant. The activation evidence is the best
relevant evidence ordinarily used to finish the task, not a new universal test
gate. If correctness is uncertain, the review remains suspended and ordinary
debugging, integration work, and validation continue.

The review never activates merely because time, token, or patch-size pressure
exists. A failed check is not evidence that the solution should be narrower.

### 2. Small evidence hierarchy

The review uses three support levels, in order:

1. **Direct obligation or concrete constraint.** Explicit task requirements;
   repository instructions, architecture, interfaces, and conventions; relevant
   compiler, test, static-analysis, runtime, security, safety, and data-loss
   evidence. Work supported here is kept.
2. **Necessary correctness inference.** Adjacent behavior implied by the chosen
   implementation, integration boundaries, edge cases supported by repository
   behavior, shared root causes, and cleanup required to leave the working
   change coherent. Work supported here is also kept even when not literally
   requested.
3. **Unsupported optional engineering.** Hypothetical extensibility,
   unobserved production hardening, unrelated refactoring, stylistic preference,
   or optional structure with no support in levels 1 or 2. Only this level may
   be challenged.

Uncertainty is not level 3. If support cannot be resolved from already-known
evidence or one concrete lookup, the implementation is kept.

### 3. Narrow challenge set

Eligible challenges are task-introduced additions such as:

- speculative abstractions or architecture layers;
- unused extension points and future-proofing;
- unrelated refactors or stylistic cleanup;
- defensive complexity for an unobserved hypothetical;
- new infrastructure duplicating an existing mechanism already known to
  satisfy the current need.

The review does not challenge necessary edge-case handling, integration fixes,
relevant tests, shared-cause changes, safety/security work with concrete
justification, justified dependencies, or coherence work required by the
chosen implementation.

### 4. No-new-search semantics

The review begins from evidence already collected during normal work. It does
not require repository-wide reuse discovery, exhaustive dependency hunting,
broad architecture review, or exploration of alternatives after a valid
solution exists.

At most, an ordinary targeted lookup may answer one concrete unresolved
question about a specific addition—for example, whether the already-known
repository mechanism actually covers the required case. The lookup is not a
proof-of-minimality exercise. If answering the question would require broad
search, the addition is kept.

### 5. Action semantics

The review has a keep-by-default bias:

- keep every addition supported at hierarchy level 1 or 2;
- keep uncertain, entangled, or risky-to-remove work;
- remove or simplify only level-3 work that is clearly separable and whose
  removal does not change required behavior;
- do not modify anything solely to reduce lines, files, dependencies, tests,
  tokens, or apparent patch size;
- after any removal or simplification, rerun the relevant affected check or
  restore the working implementation if confidence is reduced.

The concept is review-and-remove/simplify only under this narrow condition. It
is neither aggressive deletion nor a general refactoring pass. Finding no
eligible work is a valid no-op.

### 6. Failure interaction

When a relevant check fails or correctness becomes uncertain, the scope review
stops. The agent returns to ordinary diagnosis and correction without pressure
to narrow the solution. The review may restart once, from the beginning, only
after the corrected implementation again meets the activation conditions.

A failure caused by a review change causes that change to be restored or
repaired as ordinary correctness work. It is evidence against the review's
classification, not evidence for a cheaper implementation.

## Material distinction from C-short v0.1

| Dimension | C-short v0.1 | Qualified concept |
| --- | --- | --- |
| Timing | Present before interpretation and implementation | Activates once only after plausible correctness and relevant checks |
| Discovery constraints | Literal requirement/minimality frames solution discovery | Ordinary interpretation, exploration, implementation, and debugging remain unconstrained |
| Reuse requirement | Directs reuse up front | Creates no reuse duty; existing mechanisms matter only when already evidenced or a concrete lookup resolves one question |
| Scope inference | Unrequested functionality/structure is presumptively suspect | Necessary inferred correctness and integration work is explicitly supported |
| Adjacent correctness | Can discourage work beyond literal task wording | Keeps edge cases, integration changes, shared causes, and coherent cleanup justified by evidence |
| Search obligation | May induce search for something to reuse | Prohibits broad proof-of-minimality search and alternative hunting |
| Removal/simplification | Constrains what is built from the outset | Reviews only task-introduced additions and changes only clearly separable unsupported work |
| Testing/evaluator evidence | Applies before validation evidence exists | Validation evidence is an activation prerequisite and a justification source; failures suspend review |
| Decision proxy | Emphasizes required functionality/structure | Rejects LOC, file, dependency, test, token, and response-size proxies |
| Uncertainty | May resolve ambiguity toward less scope | Resolves uncertainty toward keeping the working implementation |

The concept would be rejected if future wording caused it to influence work
before the activation boundary. Material distinction depends on lifecycle
behavior, not softer vocabulary.

## Falsifiable behavior predictions

These predictions precede any exact treatment wording. A separately authorized
future exploratory design would have to operationalize measurement without
changing them after results.

### Quality predictions

- The candidate will not reproduce a baseline-only acceptance failure caused
  by suppression or removal of necessary adjacent correctness work.
- Acceptance will not deteriorate systematically relative to baseline.
- Review-induced changes will preserve the relevant checks that justified
  activation.

### Work predictions

Among correct/accepted outcomes, at least some candidate trajectories will
omit or remove engineering that an evidence-grounded review can identify as
unsupported and optional. That mechanism-level change must exist independently
of simple reductions in lines or files.

Relative to baseline, the candidate will not increase corrective-round
frequency, repeated/cached context ingestion, total wall time, or search
activity. The final scope review itself must not erase any structural benefit
through added review/search work.

### Mechanism prediction

Differences will concentrate in late optional additions. Ordinary repository
exploration, necessary adjacent fixes, shared-root-cause work, integration, and
relevant validation will remain substantially unchanged before the activation
boundary.

If behavior changes during discovery or necessary correctness work, the
candidate is functioning like an up-front restriction and the mechanism
prediction is false.

## Prospective immediate retirement gates

Retire the concept without wording repair or post-hoc weakening if a fresh,
separately authorized exploratory experiment shows any of the following:

- replicated suppression or removal of necessary correctness work;
- worse acceptance without a compelling, prospectively admissible
  countervailing benefit;
- no evidence-grounded reduction of unnecessary work among accepted outcomes;
- increased corrective-round frequency;
- increased search activity, repeated/cached context ingestion, or total wall
  work;
- an apparent benefit consisting only of fewer lines, files, dependencies,
  tests, tokens, or shorter responses;
- meaningful changes to ordinary discovery, adjacent correctness, integration,
  shared-cause fixes, or validation before the late activation boundary;
- behavior effectively equivalent to C-short's up-front restriction;
- broad proof-of-minimality searching or a review process too complex to remain
  a single bounded check.

These are prospective design gates, not a confirmatory design. They may be made
more operational before a future exploratory freeze, but may not be weakened
after outcome inspection.

## Explicit non-goals

- optimizing for smaller patches, fewer files/dependencies/tests, shorter
  reasoning/responses, or lower tokens per turn;
- proving that every addition is minimal, necessary, reused, or architecturally
  optimal;
- constraining requirement interpretation, implementation strategy, justified
  dependencies, safety/security work, or relevant validation;
- a scoring rubric, mandatory checklist, architecture review, second agent,
  exhaustive audit, or repository-wide cleanup;
- exact treatment wording, candidate injection, implementation, freeze,
  provider/evaluator use, task selection/exposure, Pilot-v4, or confirmatory
  design/execution;
- a claim that Pilot-v3 established the mechanism or that this concept works.

## Complexity judgment

The surviving concept has one activation boundary, one three-level evidence
hierarchy, one narrow challenge class, and one keep-by-default action rule. Its
conceptual detail is longer here because this report tests the design and
records falsification boundaries. Any future treatment that requires this
report's rule-by-rule reproduction would fail the complexity budget.

No exact treatment bytes exist in this goal.
