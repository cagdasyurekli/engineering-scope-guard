# Pilot Runner Qualification

**Completed:** 2026-08-28

**Decision:** **RUNNER-QUALIFIED — GO TO RESUME PILOT**

**Pilot cells executed:** 0

**Policy comparisons executed:** 0

**Real Pilot `execute` invocations:** 0

## Outcome

The repository now contains the smallest local, sequential execution layer
needed to faithfully orchestrate the already-frozen `pilot-v1.0` contract. The
runner selects nothing: contract validation, the 48-cell order, task/arm/model/
reasoning identities, timeouts, one corrective round, evaluator, failure
taxonomy, and both budget units remain frozen inputs.

This qualification used strict preflight, deterministic fixture-backed
orchestration tests, and a metadata-only dry-run of all 48 real scheduled
cells. It did not launch Codex, evaluate an agent patch, create a Pilot ledger,
invoke the real `execute` command, consume a Pilot cell, or compare policies.

## Interface

From the repository root:

```bash
PYTHONPATH=src python3 scripts/pilot_runner.py preflight
PYTHONPATH=src python3 scripts/pilot_runner.py dry-run
```

`preflight` validates the exact contract bytes and commitments, tracked
contract identity, Codex 0.150.1 interface, pinned dataset/evaluator/RepoLaunch
revisions, fixed Docker allocation, and the 12 qualified local image IDs. It
makes no subject or evaluator call.

`dry-run` first performs that strict preflight, then resolves every scheduled
cell to one exact dataset row, base commit, official image, task-text digest,
arm/intervention digest, subject identity, and unique future isolation roots.
It writes only the tracked dry-run receipt; it does not create or modify Pilot
state.

`execute` is implemented for a separately authorized resume goal. It requires
the explicit token
`execute-pilot-v1.0:<frozen-contract-sha256>`, holds one local process lock, and
starts from the ledger-derived next legal action. The token is an accident
guard, not a substitute for human authorization. It was never supplied in this
goal.

## Orchestration state model

The existing JSONL hash chain is the sole durable state system. A new ledger
begins with the frozen contract identity, the four already-consumed historical
task-slot replacement events, and the frozen schedule identity. For each cell:

1. `attempt_started` durably binds the next cell and unique repository,
   `CODEX_HOME`, raw, and derived roots before subject work;
2. the official task image materializes a fresh `/testbed` repository at the
   dataset base commit;
3. Codex runs with the frozen subject configuration and an allowlisted process
   environment;
4. its binary-capable Git diff is retained and wrapped in the official
   prediction mapping;
5. the pinned official evaluator produces structured `report.json` and
   `results.json` artifacts;
6. only an initial structured evaluator failure triggers one failing-check-
   names-only correction in the same trajectory-local Codex session;
7. a complete receipt is validated before `attempt_finished` is appended;
8. only an admissible experimental outcome advances to the next schedule cell.

A crash after `attempt_started` remains an explicit partial attempt. Restart
does not silently rerun, discard, or count it. An operator must explicitly
classify it with an allowed infrastructure/batch-stop class before the frozen
transition logic can continue. Completed cells cannot be rerun. Corrupt,
duplicate, wrong-order, wrong-task/arm/subject, reused-root, or post-stop state
fails closed and is never repaired automatically.

## Evaluator boundary

The runner does not grade patches. Source inspection at the pinned evaluator
revision confirms the official prediction input is a JSON object keyed by
instance ID with a `model_patch` Git diff. The official invocation remains:

```text
<qualified-python> -m evaluation.evaluation
  --dataset <pinned-snapshot> --split <frozen-language> --platform linux
  --patch_dir <prediction.json> --output_dir <round-output>
  --workers 1 --overwrite 1 --instance_ids <frozen-instance-id>
```

The runner uses the structured per-instance report and aggregate results. A
resolved false report is task outcome data; structured evaluator/Docker
infrastructure failure remains a distinct same-cell-rerunnable class; absent or
malformed required structured artifacts stop the batch.

## Budget separation

Task-slot replacement remains a completed pre-treatment operation: allowance
8, consumed 4, and post-finalization authority 0. The runner copies those four
historical events into a new ledger prefix but exposes no path that selects or
changes a task.

Trajectory infrastructure reruns remain allowance 8, initial consumed 0, and
at most one rerun for the same cell. Agent failure, evaluator test failure,
timeout, a poor patch, or either arm's observed performance never consumes that
budget. A second infrastructure failure in one cell or exhausted global budget
stops the batch.

## Usage and privacy

Input, cached-input, output, reasoning-output, and derived total tokens are
retained separately when all required fields are exposed. Missing values remain
unavailable; they are not changed to zero. Cache-write tokens, provider-billed
amount/currency, and backend model snapshot remain unavailable and are not
required or estimated by the runner.

Tracked preflight/dry-run receipts contain Pilot identifiers and immutable
digests already within the frozen Pilot boundary, not task bodies or future
confirmatory IDs. Live task text, Codex traces, diffs, and evaluator artifacts
remain under ignored local trajectory roots.

## Qualification evidence

- Frozen contract SHA-256:
  `1ec191306215936c4f17bd0805d0a4619e0530a4d79c91c0240212b26226ead0`
- Final-pool SHA-256:
  `611693dc971177e76b5d7b45eb58f8dffd7c4821bf12b0dc6c540b6d580973fa`
- Schedule SHA-256:
  `ab92971b4309ecb6a7ccdd18c97358a2db4ba3342261c6831f8d6b0ace04aa2e`
- C-short SHA-256:
  `c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6`
- Strict runner preflight: PASS; zero subject/evaluator invocations; ledger and
  execute marker absent.
- Full dry-run: PASS; all 48 cells resolved; zero subject/evaluator
  invocations; ledger unmodified; zero cells/comparisons.
- Focused runner tests: 14 passed.
- Complete repository suite: 105 passed.
- Warning-clean compilation and `git diff --check`: passed.

Graphify 0.9.48 was used only as a fresh code-only navigation index to locate
existing contract, receipt, ledger, trace/usage, evaluator, rerun, and
replacement seams. All material conclusions were verified against the cited
source files. Graph context is not part of any Pilot prompt or subject state.

## Limitations

- Qualification proves deterministic orchestration semantics with fakes and
  verifies live immutable inputs. It deliberately does not prove a successful
  live Codex/evaluator cell, because doing so would consume Pilot data or require
  a new non-Pilot external canary not authorized by the durable contract.
- Provider-side cache isolation, provider billing, and backend model snapshot
  remain unavailable.
- The runner is prepared for review but is not committed, merged, or published
  by this goal.

## Completion decision

**RUNNER-QUALIFIED — GO TO RESUME PILOT**

This decision authorizes no execution by itself. Start no cell until the user
separately activates or resumes the Pilot goal against reviewed runner bytes.
