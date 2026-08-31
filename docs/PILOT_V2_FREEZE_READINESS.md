# Pilot v2 Pool, Contract, and Execution-Readiness Freeze

**Status:** preparation complete; Git stabilization and execution authorization
remain separate

## Outcome

The body-free Pilot-v2 pool, deterministic schedule, and `pilot-v2.0`
execution contract are prepared and byte-regenerable. The frozen pool contains
11 previously host-qualified tasks and the schedule contains 44 paired cells:
baseline and `C-short v0.1`, twice per task.

No Pilot-v2 subject, evaluator, schedule cell, policy comparison, or
confirmatory task-body exposure occurred. Pilot-v2 execution remains explicitly
unauthorized.

## Pool decision

Pilot v1 reached a subject and evaluator for
`xroche__httrack-408` before receipt construction failed. Carrying that task
into a new Pilot would preserve exposure contamination even though it produced
no valid observation. It is therefore excluded prospectively from Pilot v2.

The remaining 11 tasks are carried forward from the already-qualified Pilot-v1
host pool. No new task is drawn from the confirmatory reserve, so its opaque
post-Pilot-v1 commitment remains unchanged:

- 499 tasks across 207 repositories;
- ranked-ID commitment
  `609b0dfba0a27dbd535f3db67375d84a454c7ad98b7fdd03cf501fdd16958930`;
- zero reserve IDs or task bodies emitted.

This choice reduces the pool from eight to seven represented languages because
the excluded task was the only C task. That is a real scope limitation, not a
reason to expose or consume an unqualified reserve task. Pilot-v2 results, if
later authorized, remain exploratory and cannot be generalized to the omitted
C stratum.

## Frozen identities

- contract version: `pilot-v2.0`;
- contract digest:
  `ae839cb6f3d2073643e214e9c920c7e7d6911dc030d9a51fb5e9d63d15a95be6`;
- pool digest:
  `b644244a4aae2a5396e045ce5415e485fb387c0bbe84d1225369e862ea621083`;
- schedule digest:
  `74e1203fea0fce45c69084e34596e666330a4e17b5a79414f9e65163b60e2766`;
- contract file SHA-256:
  `4c1019f74becb059f0f1c8440d3fb676ff4595904e57cd79fd69770d6543d53c`.

The contract preserves the qualified Codex 0.150.1, `gpt-5.6-terra`, medium
reasoning, isolated credential/home/repository/output roots, official pinned
SWE-bench-Live evaluator with one worker, two-turn/one-corrective-round
trajectory, failure taxonomy, complete provider-token requirements, and the
eight-unit same-cell infrastructure-rerun allowance with at most two attempts
per cell. The Pilot-v2 task-slot replacement allowance is zero after freeze.

## Qualification evidence

The preparation-only qualification:

- regenerated the contract exactly from tracked authoritative metadata;
- rejected contract mutation rather than normalizing it;
- resolved all 44 cells from prior body-free immutable-input receipts;
- verified each task has both arms in both repetitions;
- proved schedule sensitivity to the pool identity;
- bound the existing shared runner to the v2 contract and a v2-specific
  confirmation token/state root;
- recorded zero ledger writes and zero live or experimental activity.

The machine-readable evidence is
`experiment/pilot_v2_freeze_qualification.json`. Its SHA-256 is
`13a162685b8ea2f33a68906f7c5a733cb1d75357affb598fe01989069598acb6`.

## Remaining boundary

The exact live preflight requires the frozen contract to be tracked at `HEAD`.
Git branch/commit/push/PR/merge work was not included in this goal's authority,
so remote CI and CodeQL cannot yet be derived and the live preflight was not
run. No substitute canary was run: the final qualified live canary is reused as
the frozen infrastructure evidence.

The next bounded action is Git stabilization of these prepared bytes. Only
after that separate authorization, green required checks, and a tracked-head
preflight may another explicit user authorization permit the execution command.

## Decision

### `PILOT-V2 FREEZE PREPARED — GIT STABILIZATION AND EXECUTION AUTHORIZATION REQUIRED`
