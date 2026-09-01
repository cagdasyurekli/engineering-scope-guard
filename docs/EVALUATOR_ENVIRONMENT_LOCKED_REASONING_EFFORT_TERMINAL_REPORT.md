# Evaluator-Environment-Locked Reasoning-Effort Terminal Report

## Evaluator environment

- The predecessor froze complete installed-distribution identity
  `82d6d5440801cfe448ba268f3e2e6cb64fbfcdba44d1b24ebd8a106c1379773e`
  but observed
  `38b429379d977a6ef791c9d1d48f66f711f2c333102d42e03e699f6d063c642a`
  at its first cell. Python `3.12.13`, interpreter bytes, direct evaluator
  packages, and evaluator/launch source identities matched. The material drift
  was the complete transitively resolved Python distribution set. Because the
  historical receipt retained only the aggregate hash, the individual package
  difference is not recoverable.
- The successor defines evaluator source as E1, immutable evaluator and task
  images as E2, resolved Python/system packages and toolchains as E3,
  runner/configuration identity as E4, and legitimate task-specific inputs as
  E5. Timestamps, temporary paths, host/process names, worker IDs, and Azure
  task IDs are non-semantic observations.
- Exact package lock SHA-256:
  `ef243c72a7c33af13453c51dc18fc197e35f90681b0cba81c001de083e2f228c`
- Immutable evaluator image digest:
  `sha256:2454b7c257514e74c40d8b4fa6d959f86ac0d193cd3d1d4472dad804ddaa4514`
  for `linux/amd64`.
- Effective evaluator source-tree SHA-256:
  `ffaaf7e50fc33470b17fd11e67160c973587a8299db19924ac775a2e909fdfaa`.
- Two fresh container workers independently observed the same semantic
  environment. Global environment SHA-256:
  `25eecaafadc6f41fc795bc007f715f41f7851488e4173810ecb8a174765249bf`.
- One frozen alternate gold fixture passed with one submitted and one resolved
  result, no failures/errors/incomplete results, five hashed output artifacts,
  and zero remaining task containers. This used 1 of the maximum 4 preflight
  tasks and is infrastructure evidence, not treatment evidence.

## Agent

- Codex: `codex-cli 0.151.0`
- Model: `gpt-5.6-sol`
- Runtime receipt SHA-256:
  `595f2050d34c767f20bc6ecab9696095e0e892ab6496d416ac4d4d79ed8990ba`
- LOW profile SHA-256:
  `c80a425aa2b3d1cd4c5a1a17275254dfc71786a9df5800440d2354a0024afaeb`
- MEDIUM profile SHA-256:
  `db8d0af59ad3627e43faea60a128c9ef080b271ce7fc52bf457878659b24cfa4`
- The pinned runtime, model, binary, catalog, configuration, tool surface, and
  treatment-only LOW/MEDIUM diff revalidated. No new contentless provider
  launch was needed, so 0 of the maximum 2 were used.

## Task population

- The prior outcome-blind qualification still contains 16 independent
  repository clusters: 12 primary-qualified and 4 alternates.
- No task body, outcome, patch, or exact private task identity was exposed.
- The readiness failure occurred before the authorized ten-primary/four-
  alternate subject freeze. Therefore no new primary or alternate population
  was frozen for this successor.

## Experiment

- Readiness receipt SHA-256:
  `2a0f72d3d60da8fbc6786f56d806e29ec2d265167b5e080f481c67856401b3e5`.
- Thirteen of fifteen gates passed. `sufficient_subject_quota` failed its
  prospective minimum.
  `no_azure_reserve_contention` failed because the separately owned Future
  Evaluator Reserve was still active.
- `subject_freeze_authorized` was false. No contract, schedule, population, or
  48-start ledger was frozen. Planned cells are therefore not missing outcomes;
  they never became experimental cells.
- Subject starts: 0. Evaluator starts: 0. Attempts: 0. Admissible cells: 0.
  Alternates activated: 0.

## Acceptance

LOW and MEDIUM acceptance are unavailable (`0/0` admissible cells). There is no
paired difference or cluster-level uncertainty estimate.

## Work

No subject ran, so token, wall-time, turn, tool, search, and correction metrics
are unavailable. Environment qualification and gold preflight work cannot be
used as treatment work measurements.

## Falsification

There is no preferred treatment interpretation to falsify. The strongest fact
against any LOW/MEDIUM claim is the complete absence of a frozen experiment and
admissible treatment observations. Successful infrastructure qualification
does not contradict or support a treatment effect.

## Scientific decision

**EXPERIMENT INVALID / TERMINATED.** The evaluator-environment repair passed,
but two mandatory prospective gates failed. LOW versus MEDIUM remains
unanswered. The current authorization is consumed and this program is not
resumable.

## ESG-RR-002

**Not justified.** The admissible-data, uncertainty, usefulness, and permitted-
disposition publication gates cannot pass. No ESG-RR-002 report or immutable
Release is created.

## Azure

- Experiment-owned pools: 0. Jobs: 0. Active nodes: 0. Compute cost: `$0`.
- The separate Future Evaluator Reserve was inspected only for contention. It
  was not stopped, resized, deleted, or used for task selection; no reserve
  outcome was inspected.

## Repository

- Canonical public base inspected before execution:
  `e7cb645bd56895fbd20719e5fc6b23112f6da7a1`.
- Terminal-record work uses a dedicated branch and GitHub noreply identity.
  Required Python 3.11, Python 3.14, CodeQL Python, CodeQL Actions, privacy, and
  Gitleaks state are derived from the final PR and protected `main` rather than
  embedded as stale claims.
- Raw tasks, prompts, traces, patches, evaluator logs, credentials, quota
  receipts, Azure task details, and local diagnostic paths are excluded from
  Git.

## Exactly one next authorization boundary

Any later reasoning-effort experiment requires a new explicit successor
authorization and a fresh prospective readiness decision after subject quota
and reserve availability are sufficient. Do not resume this program, consume a
quota reset, or start a second experiment under the current authority.
