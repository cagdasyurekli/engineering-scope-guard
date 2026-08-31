# Runtime-Locked Reasoning-Effort Terminal Report

## Runtime lock

- Codex: `codex-cli 0.151.0`
- Binary SHA-256: `98491713ffb196061003ee148636e743997cc31d76144ba7c53462269896891d`
- Model: `gpt-5.6-sol`; the frozen observable catalog exposed native `low`
  and `medium` effort.
- Binary/catalog sentinels: passed before each contentless process launch; no
  observable binary or catalog drift occurred.
- Stability soak: failed. Both allowed launches exited locally with code 2
  before JSONL, provider, or tool events because the command combined mutually
  exclusive `--approve-for-me` and `--sandbox` options.
- The reusable public command helper removes the redundant explicit sandbox
  option and has a regression test. It was not launched after the terminal
  gate; this is a prospective mechanical correction, not experimental evidence.
- Provider-side model changes not exposed by the runtime cannot be frozen or
  detected.

## Azure

- The campaign deadline now uses persisted completed monotonic segments plus
  the current process-local monotonic segment. Azure timestamps and retry
  counters are diagnostic only.
- Eleven fake-clock scenarios passed: normal completion, changed start time,
  requeue, unchanged retry counter, restart, persisted resume, post-restart
  timeout, multiple jobs, interrupted worker, wall-clock disagreement, and
  receipt tamper/identity drift.
- One synthetic task completed without retry on one `Standard_A1_v2` worker.
  It recorded 11.712765 task-runtime seconds (0.003254 VM-hours). Its
  task-runtime cost estimate was $0.000133; a conservative cumulative upper
  bound including the prior Azure work is $0.35. Neither is a billing claim,
  and directly billed/credit value was unavailable.
- Prospective qualification jobs: 0; evaluation jobs: 0; synthetic validation
  jobs: 1; observed failures/requeues: 0.
- Fresh terminal readback at 2026-08-31T21:12:25Z: jobs `[]`, pools `[]`, and
  zero active compute.

## Task population

- Prior pool reuse decision: eligible prospectively; its sealed outcome-blind
  provenance and zero-subject accounting were revalidated.
- Qualified independent clusters: 16 from 20 examined candidates.
- Frozen primary tasks: 0.
- Frozen alternates: 0.

## Experiment

- Started: no.
- Subject attempts: 0 of an absolute 48 cap.
- Evaluator invocation starts: 0.
- Admissible cells: 0.
- Missing cells: 0; no schedule or contract existed.

## Acceptance

- LOW: not observed.
- MEDIUM: not observed.
- Paired contrast: not applicable.
- Uncertainty: not estimable because no subject outcome exists.

## Work

No subject work metrics exist. The two local command failures are
infrastructure diagnostics and are excluded from treatment comparisons.

## Falsification

The strongest contradictory result is that a runtime receipt and passing
binary/catalog sentinel did not establish launchability: the frozen command
surface itself was invalid. The soak correctly prevented contract freeze and
all subject exposure.

## Scientific disposition

**EXPERIMENT NOT STARTED / RUNTIME-STABILITY GATE FAILED.** LOW versus MEDIUM
remains scientifically unanswered. The failure is neither runtime drift nor
efficacy evidence.

## ESG-RR-002

Not justified. No ESG-RR-002 report, tag, or Release is created. The public PR
contains only the reusable campaign-clock/runtime-gate implementation and this
minimum terminal disposition.

## Repository

- Canonical: `https://github.com/cagdasyurekli/engineering-scope-guard`
- Baseline root: `f62ecf13a534195f783c91f3299bbbe2b91c1833`
- Final `main`, CI, CodeQL, privacy, Gitleaks, PR, and squash-merge identities
  are completed and read back during Git stabilization.
- Raw receipts, stderr, runtime binaries, task identities, and private working
  evidence remain excluded from Git.

## Exactly one next authorization boundary

> Authorize a separate successor program before any third stability launch,
> retry, or new LOW-versus-MEDIUM experiment.

Do not start another experiment or begin external distribution.

Terminal result SHA-256: `242c40cf59daff665305e1ba0a503e79b295e3f746a4887c661858748b61b5ac`
