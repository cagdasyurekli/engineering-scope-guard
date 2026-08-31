# Codex Handoff — First Implementation Session

Use this when beginning implementation in Codex after the repository is created.

## Goal

Implement **only V0 Shadow Scope Analyzer** as defined in `docs/PRODUCT_SCOPE.md`.

Do not implement an intervention policy yet. The purpose of V0 is to learn whether deterministic scope-budget signals are reliable enough to justify behavioral intervention.

## Required first steps

1. Read `README.md`, `AGENTS.md`, `docs/CURRENT_GOAL.md`, `docs/GOAL_PROTOCOL.md`, `docs/MODEL_REASONING_POLICY.md`, `docs/PRODUCT_SCOPE.md`, `docs/EVALUATION_PROTOCOL.md`, `docs/EVIDENCE_POLICY.md`, and `docs/DECISIONS.md`.
2. Inspect the current Codex hook/plugin interfaces available in the exact installed Codex version. Do not rely on memory or old blog posts.
3. Confirm the active goal from `docs/CURRENT_GOAL.md`. Do not expand it.
4. State the initial model/reasoning configuration appropriate for the next task using `docs/MODEL_REASONING_POLICY.md`. If the runtime cannot switch configuration itself, state the recommendation rather than pretending it can.
5. Produce a very small implementation plan that explicitly lists:
   - the hook/transcript events actually available;
   - known gaps or inconsistent events;
   - the minimum local data needed;
   - the minimum code/modules needed;
   - what will deliberately not be built.
6. Prefer the standard library. Add a third-party dependency only when it removes clear, current implementation risk or substantial code.
7. Implement a canary/doctor command early so unsupported/missing hook coverage fails visibly.

## V0 functional requirements

The tool must be able to:

- initialize local configuration for a repository;
- observe a Codex task/session without modifying the target repository;
- snapshot/compare repository structural state at supported boundaries;
- record local JSONL events;
- generate a concise local report;
- identify a small number of deterministic candidate scope-budget signals;
- report adapter/coverage health;
- operate with networking/telemetry disabled by design.

## Minimum measurements

Start with measurements that are cheap and mechanically defensible:

- files changed/added/deleted;
- LOC added/deleted;
- dependency manifest changes;
- test-file changes;
- instruction-file size changes (`AGENTS.md` and other configured files);
- obvious newly created infrastructure/config artifacts;
- observable verification commands and follow-up edits only where the Codex event/transcript data supports them reliably.

Do not implement semantic “overengineering” classification in V0.

## Required tests

- repository fixture before/after diff measurement;
- dependency-manifest change detection;
- instruction-file delta detection;
- malformed/missing hook payload handling;
- coverage-health degradation reporting;
- target-repository immutability in shadow mode;
- proof that V0 performs no network telemetry calls.

## Stop conditions for the first implementation session

Stop when a local fixture/demo can:

1. observe or ingest a representative Codex event/trace;
2. produce deterministic structural metrics;
3. write a local report;
4. pass the minimal tests above.

Do not continue into policy injection, blocking, cleanup, telemetry, dashboards, multi-agent support, or full benchmarking in the same session.


## Failure and escalation rule

When a task or verification step fails, do not blindly retry with more reasoning. Classify the failure using `docs/GOAL_PROTOCOL.md`.

- Mechanical or missing-evidence failure: fix/retrieve with the current configuration.
- Reasoning failure with adequate evidence: increase reasoning one level.
- Repeated complex/capability failure: move to a stronger model and reset to a balanced effort before escalating further.
- Goal/hypothesis failure: stop and revise the approach instead of spending more compute.

If model/effort switching is not available within the current Codex runtime, stop at a clean boundary and give the exact recommended configuration for the next attempt plus a concise evidence/hypothesis handoff.
