# Local Evaluator Runtime Readiness

**Status:** complete

**As of:** 2026-08-27

## Boundary

This is infrastructure and instrumentation evidence only. It does not run a
baseline-versus-C-short cell, authorize Pilot, change the frozen task partition,
or support any policy efficacy or quality-preservation claim.

The source, task, evaluator, and subject remained fixed:

- dataset `SWE-bench-Live/MultiLang` at
  `62dc0745c40f067fc366ae3eb1a26136e5928f85`;
- evaluator `microsoft/SWE-bench-Live` at
  `bc09878a5d192d0804dbd647dc6e650372fcb0ac` with RepoLaunch submodule
  `c4b623d930f3728e5338664bb634021b98492cbf`;
- allocated task `BYVoid__OpenCC-1257` and official image
  `starryzhang/sweb.eval.x86_64.byvoid_1776_opencc-1257:latest`;
- Codex CLI 0.150.1, `gpt-5.6-terra`, medium reasoning, automatic approval
  review/workspace-write, ignored user config/rules, and no policy intervention.

No confirmatory task body or reserve ID was emitted or inspected.

## Host and Docker receipt

| Measurement | Observed value |
| --- | --- |
| Host | Apple Silicon `arm64`, macOS 26.6.2 (25G83) |
| Host CPU/memory | 10 logical / 10 physical CPUs; 25,769,803,776 bytes RAM |
| Docker Desktop | 4.88.1 (237512) |
| Docker client/engine | 29.7.2 / 29.7.2, API 1.55 |
| Docker engine | LinuxKit 7.0.12, `linux/arm64` (`aarch64`) |
| VM limits | 6 CPUs, 16,384 MiB RAM, 2,048 MiB swap |
| Virtualization backend | Apple Virtualization Framework |
| amd64 mechanism | Rosetta exposed with `--rosetta`, mounted and registered through `binfmt` |

The backend and Rosetta facts come from Docker Desktop's active settings/VM
startup logs, not an assumption from installed binaries.

## amd64 canary

`docker run --rm --platform linux/amd64 alpine:3.20 uname -m` reported
`x86_64` with exit 0. The cold pull/run took 5.44 seconds. Three warm repetitions
also reported `x86_64`, exited 0, and took 0.20, 0.23, and 0.21 seconds. No
architecture warning or error was emitted.

This establishes working Rosetta-backed amd64 execution for a minimal container;
it does not establish evaluator validity by itself.

## Official image and evaluator receipt

The allocated image was pulled without rebuilding or substituting it:

- image digest: `sha256:d86060b6f3692127dfe46cc8c7a5cf930f7c1a679297535b9562c637229cc0e1`;
- config digest: `sha256:fc1669e959225dbbd54c011985098c17a624d3669891bbcdcfee834d8cd35795`;
- image declaration: `linux/amd64`;
- compressed registry layer bytes: 807,365,846;
- local Docker image size field: 807,388,055 bytes;
- explicit amd64 startup: `x86_64`, exit 0, 1.34 seconds.

The completion pull took 34.59 seconds after an earlier partial pull, so it is
not a clean cold-pull measurement.

The first evaluator invocation stopped before Docker because the pinned
RepoLaunch submodule had not been initialized. It failed in 0.03 seconds with
`ModuleNotFoundError: launch.core`. This was a mechanical checkout failure, not
an architecture, task, evaluator-result, or policy failure. Initializing the
exact pinned submodule resolved it without changing evaluator code or images.

The upstream one-worker gold command then succeeded three times:

| Run | Evaluator result | Exit | Wall time |
| --- | --- | ---: | ---: |
| 1 | 1 submitted, 1 success, 0 failure/error/incomplete | 0 | 143.38 s |
| 2 | 1 submitted, 1 success, 0 failure/error/incomplete | 0 | 91.32 s |
| 3 | 1 submitted, 1 success, 0 failure/error/incomplete | 0 | 92.98 s |

Run 1 included the first dataset materialization. During that run, an observed
container sample reached 399.35% CPU and 577.2 MiB of 15.6 GiB; a later sample
was 32.03% CPU and 12.54 MiB. These are point samples, not a measured container
peak. The host evaluator process reported a 942,868,064-byte peak footprint on
run 1 and about 122 MB on warm runs. No OOM or emulation warning occurred.

This task's official gold evaluation is reproducible on this machine.

## Fixed-subject receipt

The first receipt attempt completed one subject turn and an official evaluation,
but the task was unresolved. Its permitted corrective resume then failed before
a provider turn with `no rollout found`: CLI `--ephemeral` prevents the same
thread from being resumed. The original attempt, its unresolved result, and its
usage remain retained as an invalid complete-trajectory attempt. This is an
outcome-independent harness/session-persistence defect.

One predeclared infrastructure-only replacement was consumed. It used the same
task, prompt hash, repository HEAD, Codex version, model, reasoning, permissions,
and timeout. The sole mechanical change was retaining the fresh session only
within that trajectory so a corrective turn could resume it. No session was
shared across a task, arm, or run.

The replacement completed the entire path:

`task snapshot -> Codex initial turn -> patch -> official evaluator -> one
failing-check-name corrective turn -> patch -> official evaluator -> receipt`.

| Measurement | Observed value |
| --- | --- |
| Repository HEAD | `dc5aaf19d85aaa0cfea59942cdf9366851bc2cf2` |
| Prompt | 447 bytes; SHA-256 `28bd01f4addff9eab1cb90fb8524309f4375f03adf99bdef2fe22047361ed091` |
| Initial subject | exit 0, no timeout, 163.997 s |
| Initial evaluator | official exit 0, `resolved=false`, 88.27 s |
| Corrective feedback | one failing check name only |
| Corrective subject | same thread/config, exit 0, no timeout, 55.657 s |
| Final evaluator | official exit 0, `resolved=false`, 87.99 s |
| Final patch | 4 tracked files, +17/-0 LOC, 1,831 bytes; SHA-256 `004380474fc8b281d1ae03a0a6763614b8ccd18aa8816e4bac9455cfb5125ed8` |

The unresolved task outcome is retained and is not evidence about C-short or
any policy. The infrastructure receipt is complete even though the subject did
not solve the task.

Provider-reported usage for the two-turn replacement trajectory:

- input tokens: 1,144,995;
- cached input tokens: 1,076,480;
- calculated fresh input tokens: 68,515;
- reasoning output tokens: 4,720;
- output tokens: 9,855.

Cache-write tokens, provider-billed amount/currency, and exact backend model
snapshot remain unavailable. No local cost estimate was calculated; provider
spend therefore remains unavailable rather than being mislabeled as billed cost.

## Existing Pilot operational budget

All 12 frozen Pilot image names are currently locatable. Their registry
manifests total 35,603,008,328 compressed layer bytes before cross-image layer
deduplication. Individual images range from 807,365,846 to 8,948,806,277
compressed bytes. The host had 766 GiB free, and Docker reported 3.131 GB of
current image use, so raw host disk capacity is not the immediate blocker.

The measured complete two-turn replacement trajectory took 395.914 seconds
including two evaluator passes. Three OpenCC gold runs took 327.68 seconds in
total. Those figures demonstrate practical runtime for this one task, not for
the heterogeneous 12-task frame.

Only 1 of 12 allocated tasks has an actual gold/runtime/memory receipt. The host
has exactly the documented 16 GB baseline, while upstream warns that some large
C++ repositories may require 50 GB. The frozen frame also includes a second C++
task and multi-gigabyte Rust images; manifest bytes do not establish unpacked
size, peak RAM, gold validity, or wall time. Extrapolating OpenCC's result to 36
gold preflights and 48 subject trajectories would therefore be methodologically
unsupported.

The current 12-task Pilot budget is not yet operationally feasible on this Mac
as a whole. Do not silently exclude or replace resource-incompatible tasks. A
later bounded decision must either validate the remaining frozen tasks on an
adequate environment or authorize a pre-outcome sampling/execution-environment
redesign. A native x86_64 Linux host is the smallest alternative if the frozen
tasks exceed this Mac's memory or Rosetta performance envelope.

## Bounded conclusion

**REDESIGN REQUIRED:** Runtime works partially, but architecture, resource, or
performance constraints require a pre-Pilot methodological or execution-
environment change.
