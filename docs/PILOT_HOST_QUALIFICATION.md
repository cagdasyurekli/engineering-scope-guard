# Pilot Host Qualification

**Status:** complete
**Execution window:** 2026-08-27 to 2026-08-28
**Scope:** infrastructure/evaluator qualification only

## Outcome

The fixed Apple-Silicon Docker environment supports a valid 12-task pool after
four replacements selected by the already-frozen metadata-only rule. Eight of
the 12 original tasks were host-valid. Four original tasks were retained as
invalid or unstable, and all four linked same-language replacements passed the
strict three-of-three criterion. No Codex subject, policy arm, Pilot, Freeze, or
confirmatory run was executed or authorized.

## Frozen procedure

- Docker Desktop: 6 CPUs, 16,384 MiB configured memory, 2,048 MiB swap; engine
  reported 6 CPUs and 16,746,352,640 usable bytes.
- Host path: Apple Virtualization Framework with the existing Rosetta-backed
  `linux/amd64` configuration; requested evaluator platform `linux/amd64`.
- Dataset: `SWE-bench-Live/MultiLang` at
  `62dc0745c40f067fc366ae3eb1a26136e5928f85`.
- Evaluator: `microsoft/SWE-bench-Live` at
  `bc09878a5d192d0804dbd647dc6e650372fcb0ac`, with RepoLaunch at
  `c4b623d930f3728e5338664bb634021b98492cbf`.
- One evaluator worker; unchanged official images; official gold patches; three
  retained evaluations for every task considered.
- Frozen validity rule: only 3/3 PASS is host-valid. Mixed outcomes are unstable
  and invalid on this host. Repeated official-gold or evaluator failures remain
  invalid and are classified separately.

## Task results

The ledger contains 48 evaluations across 16 tasks. Forty evaluations passed
and eight failed. There were no timeouts, detected OOM/resource failures, or
captured architecture/emulation warning lines.

| Task | Role/link | Outcomes | Median wall time | Result |
| --- | --- | --- | ---: | --- |
| `BYVoid__OpenCC-1257` | frozen | P/P/P | 59.845 s | host-valid |
| `GitoxideLabs__gitoxide-2476` | frozen | F/P/P | 402.140 s | unstable/invalid |
| `MudBlazor__MudBlazor-12974` | frozen | P/P/P | 227.836 s | host-valid |
| `colbymchenry__codegraph-951` | frozen | F/F/F | 102.708 s | invalid, official gold test |
| `dragonflydb__dragonfly-7493` | frozen | P/P/P | 981.163 s | host-valid |
| `floci-io__floci-1908` | frozen | P/P/P | 836.658 s | host-valid |
| `gui-cs__Terminal.Gui-4860` | frozen | P/P/P | 198.253 s | host-valid |
| `iOfficeAI__AionUi-1818` | frozen | P/P/P | 100.142 s | host-valid |
| `kubernetes-sigs__controller-runtime-3494` | frozen | P/F/P | 216.098 s | unstable/invalid |
| `mc1arke__sonarqube-community-branch-plugin-1221` | frozen | P/P/P | 60.098 s | host-valid |
| `open-gsd__gsd-core-1799` | frozen | F/F/F | 573.499 s | invalid, official gold test |
| `rust-lang__rust-analyzer-22827` | frozen | P/P/P | 249.474 s | host-valid |
| `lakehq__sail-2284` | replaces Gitoxide | P/P/P | 228.127 s | host-valid |
| `xroche__httrack-408` | replaces codegraph | P/P/P | 113.801 s | host-valid |
| `caddyserver__caddy-7567` | replaces controller-runtime | P/P/P | 71.440 s | host-valid |
| `thlorenz__doctoc-329` | replaces GSD Core | P/P/P | 23.066 s | host-valid |

The one Gitoxide failure was an evaluator runtime/image retrieval failure even
though the image manifest had been available; the following two attempts
passed. Codegraph failed one PASS_TO_PASS test in every repetition despite all
24 FAIL_TO_PASS tests passing. Controller-runtime failed one PASS_TO_PASS test
only in repetition two. GSD Core repeatedly left nine required FAIL_TO_PASS
statuses unresolved. These observations are evaluator/host qualification
evidence, not task-difficulty or policy evidence.

## Deterministic replacements

Four of the eight authorized infrastructure replacements were consumed. Each
replacement was the next hash-ranked eligible task in the same language stratum
under seed `engineering-scope-guard-pilot-v1-2026-08-27`, excluded Pilot
repositories, and used only frozen metadata fields. No task body or policy
performance entered selection. The original tasks and every failed attempt
remain in the ledger.

The final pool therefore contains the eight host-valid originals plus Sail,
HTTrack, Caddy, and doctoc. It retains 12 distinct repositories and the original
language-stratum counts.

Those four replacement repositories are now part of the effective Pilot pool
and must no longer be eligible for confirmatory allocation. Their exclusion
removes 39 tasks from the historically frozen 538-task reserve, leaving an
effective opaque reserve of 499 tasks across 207 repositories. The ranked-ID
commitment is
`609b0dfba0a27dbd535f3db67375d84a454c7ad98b7fdd03cf501fdd16958930`;
no reserve IDs or bodies were emitted. This is a derived post-replacement
consequence, not a change to the frozen source partition or eligibility rule.

## Duration and resource burden

All 48 gold attempts consumed 14,962.303 seconds of summed evaluator wall time
(4.16 hours). Attempt duration ranged from 22.897 to 1,267.460 seconds, with a
204.038-second median. The 36 attempts belonging to the final pool totaled
10,628.831 seconds (2.95 hours); their task-level medians ranged from 23.066 to
981.163 seconds.

Every run retained the fixed Docker capacity, timeout/OOM state, exit,
classification, official image reference, available post-run image identity,
and evaluator outputs. Selected interactive
`docker stats` point samples observed 2.546 GiB for MudBlazor, 5.298 GiB for
Gitoxide, and 5.936 GiB for Floci against the 15.6-GiB engine limit. Dragonfly
points rose as high as 2.565 GiB before falling; a late point showed 19 GB of
block writes. These are sparse point observations, not continuous telemetry or
peak measurements. No attempt was classified as a resource failure.

The completion snapshot reported 17 local images using 180.6 GB in Docker,
171.3 GB of it reclaimable, with no retained containers or build cache. Displayed
image sizes ranged from 1.9 GB for doctoc to 41.2 GB for Sail among evaluated
task images. Docker image sizes share layers and cannot be summed as independent
disk consumption; the system total is the relevant point-in-time storage
burden. No image was rebuilt, modified, or deleted.

## Planned Pilot arithmetic

The sum of the 12 final tasks' measured median gold-evaluator times is 3,149.903
seconds (52.5 minutes) for one sequential pass across the pool. With 48 planned
subject trajectories—four per task—one official evaluation per trajectory
corresponds to about 12,599.612 seconds (3.50 hours) of evaluator-only work. If
every trajectory required a second corrective evaluation, the corresponding
upper planning case is about 25,199.224 seconds (7.00 hours).

The predeclared two-turn, 900-second-per-turn subject timeout ceiling is 24
hours across 48 trajectories. Combining—not predicting—this ceiling with the
evaluator arithmetic gives a procedural scheduling ceiling of about 27.5 hours
with one evaluation per trajectory or 31.0 hours with two. Image pulls and
other overhead remain outside that ceiling.

This arithmetic is an infrastructure scheduling estimate only. It excludes
Codex/subject runtime, image pulls, provider billing, cache behavior, human
review, and retry overhead. Gold duration does not predict subject duration, and
none of these measurements estimates a policy effect.

## Deviations and limitations

- The first OpenCC evaluation completed successfully, but the receipt wrapper
  initially looked for a relative output directory from the repository rather
  than the evaluator working directory. The original wrapper record is retained;
  the official report/results were recovered from their actual location, and
  later output paths were absolute. This changed no evaluator result.
- Gitoxide repetition one failed during evaluator runtime/image retrieval and
  therefore had no available post-run image identity. Its official tag was
  retained; repetitions two and three used the same recorded amd64 image ID and
  passed. The missing first-run identity is not treated as a successful image
  verification.
- Sparse interactive resource samples do not establish per-task peak CPU,
  memory, or I/O. The stronger negative evidence is bounded: 48 fixed-capacity
  runs had no detected OOM or timeout.
- Qualification establishes host/evaluator operability for official gold
  patches. It does not establish Codex success, policy quality, provider cost,
  evaluator determinism beyond these repetitions, or Pilot acceptance.
- The Pilot remains unauthorized. This goal stops at infrastructure evidence.
- “Operationally feasible” is bounded to sequential infrastructure scheduling:
  the full qualification completed on the fixed host, no OOM or timeout was
  detected, current images fit in the existing Docker store, and the measured
  evaluator-only planning range is 3.5–7.0 hours. It is not a claim about
  subject/provider feasibility, free disk space, or a predeclared performance
  threshold.

## Evidence

- `experiment/pilot_host_qualification.json`: deterministic public-safe receipt
  retaining run outcomes, classifications, timings, resource/image facts,
  cryptographic run receipts, replacement audit trail, distributions, storage
  summary, and bounded result. Raw evaluator reports, commands, container state,
  output locations, and host-local references are excluded.
- `.local/pilot-host-qualification/raw/`: retained evaluator logs and result
  files (local and intentionally ignored).
- `scripts/sanitize_pilot_host_qualification.py`: idempotent public projection
  and fail-closed local-reference check.
- `scripts/pilot_host_qualification.py` and
  `tests/test_pilot_host_qualification.py`: deterministic runner, classifier,
  finalizer, auditor, and focused tests.

## Bounded conclusion

**A valid 12-task Pilot pool exists on the fixed environment after applying only
pre-authorized infrastructure replacements, and resource burden is
operationally feasible.**
