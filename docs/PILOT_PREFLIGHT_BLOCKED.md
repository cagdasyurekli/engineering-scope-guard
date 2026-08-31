# Exploratory Pilot Strict Preflight — Blocked

**Date:** 2026-08-28

**Status:** blocked

**Frozen stop class:** `harness_failure`

**Pilot cells executed:** 0

**Policy comparisons executed:** 0

## Outcome

Strict preflight stopped the batch before cell 1. The merged readiness state is
stable and its frozen contract still audits exactly, but the repository has no
integrated live runner capable of enforcing that contract across a Pilot batch.
This is a blocked execution result, not an efficacy result.

## Stable-checkout evidence

Preflight restarted from the beginning at merged `main` commit
`c71df19b4a90d0ae408c09fa3c1518e5f0e7aef0`; it did not reuse the earlier
failed preflight as passing evidence.

- `HEAD` equaled `origin/main`, the worktree was clean, and
  `experiment/pilot_execution_contract.json` was tracked from `main`.
- The regenerated contract matched the tracked bytes. Frozen digest:
  `1ec191306215936c4f17bd0805d0a4619e0530a4d79c91c0240212b26226ead0`.
- The frozen pool, schedule, and C-short digests matched their recorded values.
- The fixed Codex subject canary passed with Codex 0.150.1,
  `gpt-5.6-terra`, medium reasoning, and isolated configuration.
- Docker 29.7.2 reported the frozen six CPUs, 16-GiB-class usable memory,
  `linux/arm64` engine, Rosetta-backed `linux/amd64` support, and all 12 frozen
  image identities.
- The evaluator, RepoLaunch, and dataset revisions matched. Repeated
  baseline/short isolation canaries were byte-identical at start and isolated
  by state root.
- Pilot state roots and the Pilot ledger were absent. No confirmatory-reserve ID
  or task body was emitted.

## Exact discrepancy

`src/engineering_scope_guard/pilot_contract.py` states that it prepares and
validates an execution plan and never launches Codex, Docker, an evaluator, or a
policy-comparison cell. `scripts/pilot_contract.py` only builds or audits the
frozen manifest. `scripts/pilot_harness_qualification.py` audits synthetic/no-op
qualification evidence.

No integrated component launches and coordinates the live Codex subject and
official evaluator while enforcing the 48-cell schedule, process-group timeout
cleanup, trajectory-local corrective resume, per-attempt receipts, frozen
failure classification, infrastructure-rerun accounting, and hash-chained
ledger. Starting a cell without that enforcement would cross the existing
integrity boundary.

The frozen taxonomy classifies this discrepancy as `harness_failure` and maps
it to `stop_batch`. Preflight therefore stopped before cell 1 and made no repair,
regeneration, or experimental-parameter change.

## Preserved boundary

This record does not modify `C-short v0.1`, Pilot task allocation, the 48-cell
schedule, replacement budgets, failure rules, isolation/cache rules, evaluator
rules, subject configuration, analysis definitions, or evidence/claims policy.
It does not run the Pilot, compare policies, create efficacy evidence, run
Freeze, or expose private task/provider material.

The machine-readable receipt is `experiment/pilot_preflight.json`.
