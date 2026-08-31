# Development-Pool Policy Experiments Evidence

**Date:** 2026-08-27

**Decision:** **NO-GO to advance the full D v0.1 policy unchanged. Propose
C-short v0.1 and harness v0.2 for a separate Pilot-design goal.**

This is exploratory development evidence from four authored coverage cases. It
does not establish efficacy, savings, equivalence, non-inferiority, maintained
quality, or a public product claim. No Pilot or confirmatory task was inspected,
selected, or run.

## Frozen inputs and isolation

- Exactly three arms ran: baseline with no intervention, C-short v0.1
  (`c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6`),
  and D v0.1
  (`9af28b62c1938cc597797c55c5fd52a053dfeb001543206f0c1f12dd9bcad128`).
- The four-task registry hash was
  `d3764082b6fbac4f3ade5487163a879077d64b90fe4ccf19e7a934b3f34ccc1f`.
  Registry audits passed before both waves. Every task source and evaluator
  matched its pre-run registered fingerprint.
- Each wave passed a pre-batch isolation canary with equal source bytes across
  arms, distinct Codex/raw/derived roots, exact intervention hashes, and no
  source mutation or cross-arm intervention leakage.
- Codex CLI 0.150.1 used `gpt-5.6-terra` at `medium` reasoning, a 900-second
  timeout, one turn, no corrective round, and deterministic arm interleaving.
- Wave 1 used harness v0.1. After agents attempted Git checks in cells without
  Git metadata, Wave 2 froze harness v0.2 with an identical local fixture-start
  commit in every cell. Results from the two harness versions are retained by
  wave and are not treated as one confirmatory intervention estimate.

## Complete run accounting

- 24 of 24 planned agent sessions completed: four tasks × three arms × two runs.
- No timeout, process failure, or infrastructure replacement occurred.
- A separate preflight attempt produced 12 CLI argument rejections before any
  `thread.started`; those zero-session failures are retained in the harness log.
- Every provider session emitted one completed turn with available input,
  cached-input, output, and reasoning-output token components.
- Exact run-level provider billing was unavailable for all sessions. No cost was
  inferred from tokens or prices.

## Combined descriptive diagnostics

| Diagnostic | Baseline | Short | Full |
| --- | ---: | ---: | ---: |
| Sessions / accepted | 8 / 8 | 8 / 8 | 8 / 8 |
| Input tokens | 863,394 | 837,252 | 873,740 |
| Cached-input tokens | 729,856 | 701,696 | 738,048 |
| Output tokens | 12,141 | 10,558 | 12,818 |
| Reasoning-output tokens | 2,010 | 2,027 | 2,541 |
| Wall time (ms) | 354,047 | 322,450 | 366,329 |
| Verification commands | 19 | 20 | 19 |
| Failed verification commands | 13 | 11 | 12 |
| Failed-verification loops | 3 | 1 | 1 |
| Post-verification rework paths | 2 | 0 | 1 |
| Read/search commands | 51 | 50 | 55 |
| Modified-file instances | 16 | 13 | 16 |
| LOC added / deleted | 229 / 9 | 136 / 5 | 207 / 8 |
| Dependencies added / removed | 0 / 0 | 0 / 0 | 0 / 0 |

LOC, file, dependency, and exploration figures are diagnostics, not quality
outcomes. Command/read coverage is limited to completed Codex exec command and
file-change events. Several failed commands were recoverable environment or
discovery attempts (`python` absent, empty default unittest discovery, or a
search with no matches); only a nonzero verification followed by an edit counts
as a failed-verification loop.

## Falsification mechanisms

1. **Reasoning/deliberation overhead:** relative to short, full recorded 36,488
   more input, 36,352 more cached-input, 2,260 more output, and 514 more
   reasoning-output tokens, plus 43,879 more wall-time milliseconds. Shared auth
   and unproved provider-cache isolation prevent a billed-cost or causal claim.
2. **Excessive reuse search:** full recorded 55 read/search commands versus 50
   for short. This is a small authored-case diagnostic, but it does not support
   an exploration reduction from the longer wording.
3. **Symptom patching:** all six shared-cause cells modified `src/names.py`, not
   either individual caller, and passed both CLI and API external acceptance.
4. **Under-testing or premature stop:** every cell passed existing and external
   acceptance. All arms ran comparable verification-command counts. No accepted
   premature stop was mechanically observed.
5. **Suppressed necessary implementation:** all six irreducible-task cells
   implemented the required multi-channel behavior and passed failure-isolation
   acceptance. No required behavior was suppressed in this case.
6. **Safety/test protection violation:** all six guard cells routed every input
   through the existing `safe_path` validation before reads and passed traversal
   and absolute-path acceptance. No dependency, infrastructure artifact, or
   evaluator change was observed.
7. **Full no better than short:** both accepted 8/8. Full had higher aggregate
   observed token components, wall time, read/search count, modified files, and
   LOC than short. This directly triggers the predeclared reason not to preserve
   the longer artifact merely because it is more detailed.

## Variant and failure retention

Only policy version v0.1 was tried; no wording was changed after results. Both
policy assets remain in the repository. The invalid preflight invocation,
Wave 1 Git-metadata defect, corrected harness v0.2, all negative comparisons,
and every agent run remain logged in `docs/DEVELOPMENT_POOL_EXPERIMENTS.md`.

The deterministic final combined local summary had SHA-256
`3a3e3845ab5cd6454fe65aded7c2a0b44d47095a832eb76330337df8254e743f`.
The durable sanitized aggregate JSON beside this report had SHA-256
`61c371ffcb315a696443312983c71cdb52bd66f09a61af7a07f6e09016492038`.
The local summary can be regenerated with
`scripts/run_development_pool.py summarize-experiment` from retained wave roots.

## Bounded recommendation

Do not take D v0.1 unchanged into Pilot. C-short v0.1 is the smallest candidate
that remains worth testing, and harness v0.2 supplies the corrected Git-backed
cell boundary. This is a proposal for a later Pilot-design decision, not Pilot
authorization and not evidence that C-short works.

The later goal must independently resolve task supply/custody, Pilot design,
reviewer protocol/capacity, timeout/corrective rules, cache handling, and the
eventual confirmatory freeze. Confirmatory MCIDs, quality margins, estimands,
sample size, arms, and public claim wording were not selected or revised here.
