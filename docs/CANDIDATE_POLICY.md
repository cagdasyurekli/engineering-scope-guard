# Candidate Policy v0.1

**Status:** C-short v0.1 retired after terminal Pilot-v3 mechanism/disposition
analysis; D v0.1 remains a negative development variant; no new treatment bytes
exist

**2026-08-29 program disposition:** Evidence-Conditioned Final Scope Review
v0.1, the one materially different late-stage candidate permitted below, was
also retired unchanged after five frozen gates fired. No third scope-treatment
variant is authorized or recommended. This file is historical, not current
prompt guidance; see `docs/PROJECT_THESIS_REASSESSMENT.md`.

## Hypothesis

A bounded instruction may reduce unsupported engineering work without materially worsening task outcomes. The policy may also increase deliberation, exploration, or under-engineering; those are explicit falsification mechanisms.

## Short semantic control (C-short v0.1)

> Implement what the requirement states; reuse what already exists; do not add functionality or structure it does not require.

Purpose: determine whether a short instruction captures most or all of any benefit. If the full policy does not materially outperform this control, the long policy has not justified its complexity.

## Full bounded policy (D v0.1)

> Implement what the requirement states. Do not add abstractions, dependencies, configuration, infrastructure, or functionality solely for requirements that are not stated.
>
> Before writing new code, check whether the requirement is already satisfied by existing code in this repository, an already-installed dependency or framework capability, or the standard library/platform. Use a suitable existing option instead of creating parallel functionality.
>
> Do not remove existing validation of untrusted input, data-loss protections, security controls, or accessibility behavior as a shortcut.
>
> When the required change is in a shared code path, fix the shared cause rather than patching only one affected call site.
>
> Run the repository's existing checks relevant to the changed code. Stop when the stated requirement is met and those checks pass.

## Why this wording is intentionally narrow

The policy deliberately avoids vague prompts such as:

- “think deeply”;
- “explore multiple approaches”;
- “production-ready”;
- “robust”;
- “follow all best practices”;
- “make it scalable/extensible”;
- “write the cleanest possible code.”

Prior evidence suggests that unbounded deliberation and large instruction sets can increase reasoning/cost without a reliable success benefit. The goal is to constrain unsupported work, not to ask the model to be generically “better.”

## Open wording risks to test

1. **Reuse-search tax.** “Check existing code” may cause broad search and context growth.
2. **Under-engineering.** Negative constraints may suppress a necessary abstraction or dependency.
3. **Symptom patching.** A short-diff bias could patch one call site instead of a shared cause.
4. **Premature stop.** A stop condition may skip adjacent required integration work.
5. **Instruction interference.** Added constraints may crowd out useful default harness behavior.
6. **Framework mismatch.** Existing dependencies/patterns may be deprecated or inappropriate.

## Not included in Experiment 1

Project-intent attributes such as lifetime, exposure, scale, persistence, or sensitivity are a **separate factor**. They must not be bundled into the first confirmatory policy experiment because doing so would make attribution ambiguous.

## Freeze/version rule

- Development wording may change freely on the development pool.
- A pilot wording version must be tagged.
- Before confirmatory evaluation, the exact policy bytes and short-control bytes are hashed/tagged and frozen.
- A wording change after confirmatory results creates a new policy version and requires a new held-out confirmatory pool.

## Development-pool disposition (2026-08-27)

The authored four-task development pool did not show an acceptance difference
between baseline, C-short v0.1, and D v0.1. D v0.1 also had higher aggregate
observed token, wall-time, read/search, and structural diagnostics than C-short.
These development results are not efficacy evidence and do not establish that
C-short is beneficial.

They do establish a bounded design decision: **do not advance D v0.1 unchanged**.
C-short v0.1 and the corrected development harness are proposed for a separately
authorized Pilot-design goal. Confirmatory arms remain unfrozen; a later goal
must resolve and freeze them before any confirmatory task is inspected or run.

## Pilot-readiness disposition (2026-08-27)

The minimum interpretable Pilot question is baseline versus C-short v0.1. C-short
is the treatment, not a dose control for D v0.1. No fuller-policy arm currently
has an evidence-based Pilot role, and no arm may be added for symmetry.

Pilot execution remains NO-GO because the repository has zero confirmed eligible
opaque tasks and lacks the required custodian/partition, task-specific evaluators,
live subject receipt, and cache/billing interpretation. This disposition does
not change C-short bytes, freeze confirmatory arms, or support an efficacy claim.

## Pilot execution-readiness disposition (2026-08-28)

Later source, evaluator, fixed-subject, and host-qualification goals superseded
the 2026-08-27 zero-supply/runtime facts without changing C-short bytes. The
joint execution-readiness result is **REDESIGN REQUIRED**: a Pilot-specific batch
harness must enforce the frozen environment/tool/corrective/session/failure
contract, the run order must be bound to the v1 final pool, and replacement
budget units must be reconciled prospectively. This is an execution-contract
decision, not policy evidence.

## Pilot successor-batch disposition (2026-08-28)

The first real batch terminated before any valid outcome. Its terminal ledger
and recorded failure remain immutable. A separate digest-bound successor is
qualified to restart the unchanged schedule at cell 1 while consuming one
existing infrastructure-rerun unit. This lineage amendment does not change
C-short bytes, add an arm, alter treatment semantics, or provide policy evidence.
Successor execution did not occur during qualification.

## Pilot-v3 mechanism/disposition (2026-08-29)

Pilot-v3 later completed 31/32 frozen cells and supported seven complete paired
task clusters. C-short's paired acceptance estimate was adverse, and it showed
no work-reduction signal for input tokens or wall time. A post-hoc body-safe
diagnostic identified one replicated task-level pattern consistent with the
up-front literal-minimality wording suppressing adjacent acceptance-relevant
handling; a secondary search-tax mechanism remains plausible.

**C-short v0.1 is retired unchanged.** Exactly one materially distinct
candidate-design hypothesis is permissible only under a fresh explicit goal:
a late-stage, evidence-conditioned scope check that does not constrain ordinary
correctness work or create a new reuse/search obligation. No exact wording,
implementation, freeze, provider/evaluator use, or execution is authorized.
See `docs/C_SHORT_V0_1_DISPOSITION_AND_MECHANISM_ANALYSIS.md`.
