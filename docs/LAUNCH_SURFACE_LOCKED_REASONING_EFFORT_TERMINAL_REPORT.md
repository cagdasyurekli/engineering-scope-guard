# Launch-Surface-Locked Reasoning-Effort Terminal Report

## Launch surface

- Predecessor conflict: the frozen command combined Codex `exec`
  `--approve-for-me` with an explicit `--sandbox`; Codex 0.151.0 rejects those
  mutually exclusive controls before provider contact.
- Successor fix: structured argv profiles use native `--approve-for-me`
  workspace-write behavior without the redundant sandbox flag. Execution uses
  argv arrays rather than a shell command.
- Diagnostic budget: 3 of 4 permitted contentless launches were used. The
  first LOW launch stopped before provider contact because the pinned runtime
  companion was absent. That pre-freeze bundle defect was repaired once. The
  next LOW launch and the MEDIUM launch both reached the provider and exited
  successfully.
- LOW profile SHA-256:
  `c80a425aa2b3d1cd4c5a1a17275254dfc71786a9df5800440d2354a0024afaeb`
- MEDIUM profile SHA-256:
  `db8d0af59ad3627e43faea60a128c9ef080b271ce7fc52bf457878659b24cfa4`
- Normalized treatment diff SHA-256:
  `28b2439e7c999731b27cf079f5f8f5cc00b9116371a417ca7f81e413f29d9e5d`
- Deterministic validation confirmed that native reasoning effort was the only
  substantive LOW/MEDIUM profile difference.

## Runtime

- Codex: `codex-cli 0.151.0`
- Binary SHA-256:
  `98491713ffb196061003ee148636e743997cc31d76144ba7c53462269896891d`
- Model: `gpt-5.6-sol`
- Runtime receipt SHA-256:
  `595f2050d34c767f20bc6ecab9696095e0e892ab6496d416ac4d4d79ed8990ba`
- The binary, model catalog, config, tool surface, dataset files, evaluator
  revision, RepoLaunch revision, and evaluator source trees remained stable.
- The first cell's pre-subject source revalidation found one material drift:
  the Azure-readiness virtual environment's complete installed-package-set
  SHA-256 differed from the evaluator-stable qualification environment's frozen
  package-set SHA-256. Python `3.12.13` and the evaluator module identities
  themselves matched. The mismatch was detected before subject launch.

## Tasks

- Qualified outcome-blind pool: 16 independent repository clusters.
- Frozen primaries: 10.
- Frozen alternates: 4.
- Task and repository identities remain withheld from tracked artifacts.

## Experiment

- All 12 prospective readiness gates passed before freeze.
- Contract SHA-256:
  `6c07336b5745a8b71bab6ce65eea00a5158c2215be40b6d1534d754ba7d3b947`
- Balanced 40-cell schedule SHA-256:
  `7a5464dd860f9842b6cc613daf8a9608d3d49a668935aa79ba7c9919da39a529`
- Planned subject cells: 40; maximum subject starts: 48.
- Durable attempt reservations: 1; actual coding-task subject starts: 0.
- Evaluator starts: 0; admissible cells: 0; missing cells: 39; alternates
  activated: 0.
- The post-freeze package-set mismatch is a mandatory
  `runtime_or_source_identity_drift` batch stop. Repair and rerun are forbidden
  for this contract.

## Acceptance

- LOW: unavailable (`0/0` admissible cells).
- MEDIUM: unavailable (`0/0` admissible cells).
- Paired difference and cluster uncertainty: unavailable.

## Work

No subject ran, so token, wall-time, turn, tool, search, and correction metrics
are unavailable. The readiness work is infrastructure evidence and is not a
treatment comparison.

## Falsification

There is no preferred treatment interpretation to falsify. The strongest fact
against any LOW/MEDIUM claim is the complete absence of admissible treatment
observations. Leave-one-task-out sensitivity is therefore unavailable. The one
recorded anomaly is the prelaunch package-set identity mismatch.

## Scientific decision

**EXPERIMENT INVALID / TERMINATED.** The launch surface was repaired and the
contract froze, but the frozen source/runtime identity did not survive the
first pre-subject gate. LOW versus MEDIUM remains unanswered.

## ESG-RR-002

**Not justified.** Protocol integrity, admissible-data, independence,
uncertainty, evaluator-validity, usefulness, and permitted-disposition gates do
not pass. No ESG-RR-002 report or Release is created.

## Azure

- One final corrected readiness task completed end to end with deterministic
  artifacts and zero retry/requeue; three earlier readiness task surfaces
  exposed prospective worker/permission defects and were corrected before
  freeze.
- The successor pool was created at `2026-08-31T23:46:42Z`; deletion began at
  `2026-09-01T00:10:46Z`, and the zero-compute readback passed before the
  separately owned future-reserve pool was created at `2026-09-01T00:18:15Z`.
  Conservatively charging the successor through that later boundary at the
  frozen `$0.214` hourly upper bound yields at most `$0.12` USD equivalent.
  This is an estimate, not a billing claim.
- Terminal Azure Batch readback: pools `[]`, jobs `[]`, active nodes `0`.
- The separate future-reserve workstream was not deleted or resized. Its pause
  was released only after the successor zero-compute readback.

## Repository

- Canonical public base inspected before execution:
  `a62c7a74637c7ce9cfb9d7b3414de36ac56c27e9`.
- Terminal-record work uses a dedicated branch. Required Python 3.11, Python
  3.14, CodeQL Python, CodeQL Actions, privacy, and Gitleaks state are derived
  from the final PR and protected `main` rather than embedded as stale claims.
- Raw tasks, prompts, traces, patches, evaluator logs, credentials, and local
  diagnostic paths are excluded from Git.

## Exactly one next authorization boundary

Any second or replacement experiment requires a new explicit authorization.
Do not repair and rerun this contract, and do not start another experiment.
