# Exploratory Pilot Readiness Evidence

**Date:** 2026-08-27

**Decision:** **NO-GO.** No Pilot or confirmatory task was inspected or run.

## Evidence boundary

This is methodological readiness evidence, not an experiment. It supports no
policy-effect, savings, cost, quality-preservation, or product claim.

## Arm disposition

- `baseline`: default Codex with no injected policy.
- `short`: C-short v0.1 treatment; SHA-256
  `c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6`.
- D v0.1 remains a negative development variant and has no evidence-based Pilot
  role. No third arm was added for symmetry.

## Supply and budget evidence

- Confirmed distinct eligible Pilot tasks: **0**.
- Opaque catalog, inventory hash, custodian, and inaccessible confirmatory store:
  **absent/unconfirmed**.
- Permanently ineligible visible development tasks: four.
- Minimum contingent frame: 24 opaque tasks across four strata, allocating 12
  to Pilot and retaining at least 12 unseen.
- Contingent Pilot ceiling: 12 tasks × 2 arms × 2 repetitions = 48 planned
  trajectories, plus eight infrastructure-only replacements, 56 maximum.
- Repetitions are not independent task supply. The budget is a feasibility and
  variance budget, not a power calculation or Pilot authorization.

## Local isolation evidence

The new metadata-only readiness canary used only `baseline` and `short` over the
existing non-Pilot `tests/fixtures/demo_before` source. It invoked no agent.

Two fresh runs reported:

- byte-identical repository starts;
- distinct Codex state and raw/derived output roots;
- isolated process-envelope receipts;
- exact arm-specific intervention state with no `full` cell;
- no cross-arm intervention leakage;
- unchanged source bytes;
- repository fingerprint
  `060034dc47222c5d2c53af915a0d89a4e0720fd68b9106d57265a90000c8426f`.

The two `canary.json` files were byte-identical with SHA-256
`a08e7958892044abee576e189479d1f60d1c5901307caed631cac1759ac1e527`.
This proves only the tested local filesystem/process envelope. It does not prove
provider cache isolation, actual experimental tool inventory, model identity,
or that a future agent honors the intervention.

## Current subject and quality evidence

- Local inspection reports Codex CLI `0.150.1` and exposes the flags needed for
  isolated config/rule handling and fixed model/reasoning selection.
- The proposed subject is `gpt-5.6-terra` at `medium`, equally across arms, with
  at most one corrective round. No live subject/config receipt was run.
- Development supplied token components but no exact run-level billing and did
  not prove provider cache isolation.
- Confirmed independent experienced reviewers: **0**.
- No eligible Pilot task exists with frozen hidden checks, regression/static
  commands, evaluator/config protection, guard retention, or shared-cause checks.

## Verification

At the final readiness implementation bytes:

- `PYTHONPATH=src python3 -m unittest tests.test_experiment -v`: 9 passed;
- `PYTHONPATH=src python3 -m unittest tests.test_pilot_readiness tests.test_experiment -v`:
  12 passed;
- `PYTHONPATH=src python3 scripts/pilot_readiness.py`: audit passed, reporting
  two arms, zero tasks, 48 contingent planned runs, 56 ceiling, and NO-GO;
- `PYTHONPATH=src python3 -m unittest discover -s tests -v`: all 60 tests passed;
- warning-clean compilation and `git diff --check` passed.

## Bounded conclusion

**NO-GO.** The arm question and local envelope are bounded, but task supply,
custody/partition, task-specific evaluators, live subject receipts, and economic
cache/billing interpretation are not ready. Do not run Pilot or confirmatory
cells and do not convert this readiness result into an efficacy claim.
