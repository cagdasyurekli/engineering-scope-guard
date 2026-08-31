# Development-Pool Policy Experiments v0.1

**Status:** complete exploratory development work

## Interpretation boundary

This phase may debug the policy and harness. Its four authored tasks are not a
sample of product use and are permanently excluded from Pilot and confirmatory
evidence. Results may reveal failure mechanisms or justify a Pilot candidate;
they cannot establish efficacy, savings, equivalence, non-inferiority, or
preserved quality.

## Registered task mechanisms

The machine-readable registry is `experiment/development_tasks/registry.json`.
Each packet has a source repository, a task statement shown to the agent, and an
external acceptance evaluator not shown during the run.

| ID | Intended mechanism | Falsification concern |
| --- | --- | --- |
| `dev-reuse-01` | find and use an existing local helper | reuse-search tax or parallel implementation |
| `dev-irreducible-01` | add a necessary shared abstraction | suppressed necessary architecture |
| `dev-guard-01` | extend behavior while retaining traversal validation | weakened safety protection or under-testing |
| `dev-shared-01` | repair a shared root cause behind one visible symptom | symptom-only patch or premature stop |

Registry hashes must be generated and frozen before the first run. Any packet
change after that point creates a new logged development version; it never
becomes eligible for Pilot or confirmatory use.

## Exactly three arms

- `baseline`: task statement only; no additional policy bytes.
- `short`: exact bytes from `experiment/arms/short.txt`, then the task statement.
- `full`: exact bytes from `experiment/arms/full.txt`, then the task statement.

No fourth arm is permitted. Policy revisions may occur only between waves. Each
variant's full bytes, hash, tasks/runs, result, and change rationale must remain
in the version log; negative variants and failed runs are never deleted.

## Frozen wave 1 rules

- Tasks: `dev-reuse-01`, `dev-irreducible-01`.
- Runs: `r1` and `r2` for every task/arm, 12 planned sessions total.
- Agent: Codex CLI `0.150.1`, `gpt-5.6-terra`, reasoning `medium`.
- Invocation: `codex exec --json --ephemeral --ignore-user-config --ignore-rules
  --approve-for-me` in a fresh task/arm/run cell. In Codex 0.150.1 this selects
  automatic approval review with the workspace-write sandbox.
- Permissions: repository workspace-write only; no MCP, plugin, or project rule
  loading; task execution itself requires no network.
- Timeout: 900 seconds per agent session; one agent turn; no corrective round.
- Order: deterministic interleave `baseline`, `short`, `full` for `r1`, then
  `full`, `short`, `baseline` for `r2`, alternating task order by run.
- Agent result: nonzero exit, timeout, failed/absent automated acceptance, or a
  safety guard breach remains an arm result.
- Replacement: only a demonstrable provider, permission, or harness failure
  independent of the arm may consume the six-session reserve. The original run
  remains in the ledger and links to its replacement.
- Billing: provider billing is `unavailable` unless an exact run-level provider
  record is supplied. Token counts are never converted to billed cost.

Wave 2 rules must be frozen before its first run. They must remain equal across
arms. A policy change between waves requires a new version entry and means the
versions are described separately, not pooled as one intervention.

## Wave 1 exploratory checkpoint

All 12 planned sessions completed one turn and passed both existing and external
acceptance tests. There were no timeouts, execution failures, dependencies, or
billing records. Available usage components and exact diagnostics are retained
in the local wave summary; billing remains unavailable rather than zero.

Mechanically observed failed-verification loops were uneven (baseline 2, short
1, full 0), but the fixture cells lacked Git metadata and several agents ran Git
verification commands. That is a harness defect, not evidence for an arm.
Wave 1 also showed no acceptance advantage for the full policy over the short
control. The full policy used more output and reasoning tokens than the short
control in aggregate, while the short control had the smallest structural delta;
these authored-task diagnostics do not establish a general ranking.

No policy wording changes for Wave 2. The guard and shared-cause tasks exercise
clauses not meaningfully stressed in Wave 1, and Wave 1 exposed no wording defect
that justified contaminating the initial variant comparison. Retaining v0.1
also directly tests the falsification concern that the full policy adds no value
beyond the short control.

## Frozen wave 2 rules

- Tasks: `dev-guard-01`, `dev-shared-01`.
- Runs, model, reasoning, timeout, permissions, order, failure classification,
  replacement rule, and billing treatment remain equal to Wave 1.
- Each fresh repository cell is initialized as a local Git repository with one
  fixture-start commit before the agent runs. This restores the ordinary diff
  surface agents attempted to use in Wave 1; `.git` remains excluded from V0
  structural measurements.
- Policy version remains `v0.1`; Wave 1 and Wave 2 are described separately
  because the harness version changed.

## Mechanically recorded outcomes

- token components present in `turn.completed`; exact billing components when
  supplied, otherwise explicit unavailable;
- turns, wall time, timeouts, process failures, and external acceptance results;
- command/test failures followed by edits (failed-verification loops);
- repeated edits to the same path after verification (post-hoc rework);
- reliably observable read/search command counts and referenced repository paths,
  with incomplete coverage stated rather than imputed;
- acceptance and task-specific guard signals from the external evaluator;
- V0 LOC, file, dependency, test/instruction, and infrastructure deltas as
  diagnostics only.

## Policy version log

| Version | Arms | First eligible wave | Status | Rationale |
| --- | --- | --- | --- | --- |
| `v0.1` | baseline / C-short v0.1 / D v0.1 | wave 1 | registered | readiness-approved initial comparison; no result viewed |

No other policy bytes were tried. D v0.1 is retained as a negative development
variant; it is not silently replaced or deleted.

## Harness attempt log

| Attempt | Agent sessions | Disposition | Evidence and change |
| --- | ---: | --- | --- |
| `wave1-preflight-01` | 0 | retained infrastructure failure | All 12 planned invocations were rejected before `thread.started` because Codex 0.150.1 forbids combining `--approve-for-me` with explicit `--sandbox`; removed only the redundant explicit sandbox flag before any arm result existed. |
| `wave1-harness-v0.1` | 12 | completed; retained | All planned sessions completed and accepted; missing Git metadata made agent-invoked Git checks fail and confounded loop diagnostics. |
| `wave2-harness-v0.2` | 0 before start | registered | Initialize an identical local Git fixture in every cell; no policy bytes changed. |

## Final exploratory disposition

Wave 2 completed all 12 planned sessions. Across both waves every arm had eight
completed turns and eight automated acceptances, with no timeout, execution
failure, dependency change, or replacement. Billing remained unavailable.

The full policy had no acceptance advantage over the short control. Relative to
the short control it recorded 36,488 more input tokens, 36,352 more cached-input
tokens, 2,260 more output tokens, 514 more reasoning-output tokens, 43,879 more
wall-time milliseconds, five more read/search commands, three more modified-file
instances, and 71 more added LOC across the authored runs. Structural figures
are diagnostics only. Shared authentication and unproved provider-cache
isolation limit token/cost interpretation.

**Decision:** NO-GO for D v0.1 unchanged. Propose C-short v0.1 plus the Git-backed
v0.2 harness for a separate Pilot-design goal. This does not claim that C-short
is effective, equivalent, non-inferior, or quality-preserving. Pilot was not
started.
