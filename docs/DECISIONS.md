# Decision Log

This file records project-level decisions that should not silently drift as implementation progresses.

## D-001 — Experiment before product

**Decision:** Do not build the full “Engineering Supervisor” before the bounded-policy/scope hypothesis is tested.

**Reason:** The central efficacy assumption is unproven; a large architecture would itself violate the project's anti-overengineering goal.

**Status:** Active

---

## D-002 — V0 is shadow-only

**Decision:** The first implementation observes and reports; it does not inject prompts, block tools, rewrite input, delete files, or call a supervising LLM.

**Reason:** Establish signal precision/relevance and integration reliability before introducing behavior-changing confounders.

**Status:** Active

---

## D-003 — Codex first, agent-agnostic core where cheap

**Decision:** Initial integration targets Codex because the motivating problems were observed there. Keep measurement logic decoupled from the adapter where this does not add material complexity.

**Reason:** Optimize the feedback loop around the real problem source; do not pay the cost of multi-agent support in V0.

**Status:** Active

---

## D-004 — No community telemetry in V0

**Decision:** All V0 data remains local.

**Reason:** Telemetry is not required to test whether the tool helps the first user, and privacy/data-design work would expand scope before efficacy is known.

**Revisit when:** Multiple independent users exist and local experiments indicate a real benefit whose heterogeneity cannot be understood from local evaluation alone.

**Status:** Active

---

## D-005 — Short semantic control is mandatory

**Decision:** A confirmatory policy experiment must compare the full policy against both baseline and a much shorter semantically similar control.

**Reason:** Prior agentic prompt experiments show that short YAGNI/minimality instructions may capture much of the observed cost effect. A long policy must justify its own instruction and maintenance cost.

**Status:** Active

---

## D-006 — Project intent is a separate experiment

**Decision:** Do not bundle project-intent injection into the first bounded-policy confirmatory experiment.

**Reason:** It is a distinct intervention and context itself can change cost/behavior. Bundling would prevent attribution.

**Status:** Active

---

## D-007 — No arbitrary global benefit/quality thresholds yet

**Decision:** Do not freeze values such as 15% minimum savings or 3/5 percentage-point quality margins before pilot/task-supply analysis and substantive justification.

**Reason:** These thresholds are product/risk decisions, not universal statistical facts. They must not be chosen after seeing confirmatory results either.

**Status:** Active

---

## D-008 — Quality guardrails outrank cost

**Decision:** A lower-cost result cannot be advertised as a success if the relevant predeclared quality/safety guardrail is breached.

**Status:** Active

---

## D-009 — No broad “overengineering detector” claim

**Decision:** V0 reports measurable structural/scope-budget signals, not objective declarations that a change is overengineered.

**Reason:** Disproportionality requires project/task judgment and is not deterministically identifiable from change size alone.

**Status:** Active

---

## D-010 — Claims are versioned and expire

**Decision:** Every empirical claim must identify agent/model versions and evaluation date and be marked stale when not revalidated on materially changed versions.

**Status:** Active


---

## D-011 — One explicit current goal

**Decision:** Development uses one active goal in `docs/CURRENT_GOAL.md` governed by `docs/GOAL_PROTOCOL.md`. Codex may not silently expand or replace it because adjacent work looks useful.

**Reason:** Goal drift is a major mechanism for overengineering and makes experimental/implementation progress hard to interpret.

**Status:** Active

---

## D-012 — Development-time model/reasoning escalation is separate from product routing

**Decision:** Codex may use different model/reasoning configurations to develop this repository according to `docs/MODEL_REASONING_POLICY.md`. This does not authorize implementing adaptive routing in V0.

**Reason:** Development should spend more compute when a failure is genuinely reasoning/capability-bound, but task failures must not trigger automatic escalation.

**Status:** Active

---

## D-013 — Public OSS quality is not production-service scope

**Decision:** Maintain a credible public-repository quality baseline (safe local defaults, tests, docs, understandable code, no accidental telemetry/secrets) without assuming production-service, enterprise, scale, HA, cloud, or compliance requirements.

**Reason:** Public distribution requires trustworthiness but does not justify speculative production infrastructure.

**Status:** Active

---

## D-014 — V0 uses Codex exec JSONL as its primary observation adapter

**Decision:** V0 ingests `codex exec --json` JSONL as its primary supported
observation interface. Command-hook JSON is a secondary adapter that always
reports degraded whole-task coverage. V0 does not read rollout transcripts and
does not depend on the experimental App Server schema.

**Reason:** Codex 0.150.1 exposes and live-emits the minimal documented exec JSONL
event family. Hooks provide useful local-tool facts but omit hosted tools, may be
bypassed by specialized paths, and lack a reliable immediate session-end
boundary. Transcript contents are explicitly unstable, while App Server remains
experimental. Separating static doctor evidence from dynamic trace health keeps
missing coverage visible without adding a wrapper, network proxy, or behavior
change.

**Evidence:** `docs/CODEX_CAPABILITIES.md`, sanitized Codex 0.150.1 fixtures, the
live minimal canary recorded on 2026-08-27, and the V0 adapter/health tests.

**Status:** Active

---

## D-015 — V0 measurement/output contracts are explicit and locally bounded

**Decision:** Snapshot schema version 2 fixes LOC as strict-UTF-8, NUL-free line
measurement with binary/symlink/special separation. Infrastructure candidates
use the versioned `candidate-infrastructure-paths-v1` set and a neutral review
label. Derived events use the named/versioned
`engineering-scope-guard.event` schema and separate trace, snapshot,
command/verification, and usage coverage. V0 remains a direct `python -m` tool
without packaging or a console entrypoint.

**Reason:** These definitions make repeated measurements interpretable without
adding semantic judgment or infrastructure. Persistent configuration remains the
smallest reliable way to bind separate commands to the same target while
revalidating outside-target state. Packaging was not part of V0 acceptance and
would add an unused build dependency and duplicate invocation path.

**Privacy boundary:** Repository-relative paths are sensitive local metadata,
not telemetry. The analyzer workflow's socket-denial test demonstrates no
in-process network API use; it does not prove operating-system confinement of
doctor's fixed local subprocesses or of separately invoked Codex capture.

**Status:** Active

---

## D-016 — Development readiness uses three isolated arms and no efficacy tasks

**Decision:** The initial development experiment may use exactly baseline, the
current short semantic control, and the current full bounded policy. Its four
prospectively authored development tasks are permanently excluded from pilot and
confirmatory evidence. Future pilot/confirmatory allocation requires a frozen
opaque catalog and deterministic partition before policy authors inspect task
text or hidden tests.

**Reason:** A fourth arm would spend scarce runs without answering the first
hierarchical questions. Separating author-visible development coverage cases
from an unseen task inventory prevents policy refinement from selecting future
winners or contaminating confirmatory evidence.

**Run boundary:** Development is capped at 24 planned runs (four tasks, three
arms, two runs) plus six infrastructure-only replacements. This is a debugging
ceiling, not a power calculation. Development results support no efficacy claim.

**Reviewer boundary:** Zero independent experienced reviewers are currently
confirmed. Until adequate blinded capacity is documented, claims are limited to
exact automated acceptance/guardrail results and deterministic diagnostics.

**Unresolved:** MCID, quality margin, final estimand, pilot/confirmatory sample
size, exact timeout/corrective/retry rules, catalog supply, reviewer protocol,
and public claim wording must be justified and frozen later. Values such as 15%,
5%, or 3 percentage points have no default authority.

**Evidence:** `docs/DEVELOPMENT_EXPERIMENT_READINESS.md`,
`scripts/development_experiment.py`, and `tests/test_experiment.py`.

**Status:** Active

---

## D-017 — Development results reject advancing the full v0.1 policy unchanged

**Decision:** Retain D v0.1 as a negative development variant and do not advance
it unchanged. Propose C-short v0.1 and the Git-backed development harness v0.2
for consideration in a separate Pilot-design goal.

**Reason:** All three arms passed all eight authored development runs, so the
full policy showed no acceptance advantage over the short control. The full
policy also had higher aggregate observed token, wall-time, exploration, and
structural diagnostics than the short control. This directly exercises the
predeclared falsification mechanism that the full policy may perform no better
than the short control.

**Claim boundary:** The tasks were authored coverage cases, the two waves used
different harness versions, provider cache isolation was not proved, run-level
billing was unavailable, and no independent reviewer was confirmed. The result
is a development-stage design pivot only—not efficacy, savings, equivalence,
non-inferiority, or preserved-quality evidence. Confirmatory arms, margins,
estimands, and public claims remain unfrozen and unchanged.

**Evidence:** `docs/evidence/development-pool-policy-experiments-2026-08-27.md`.

**Status:** Active

---

## D-018 — Pilot readiness uses a two-arm question and remains NO-GO

**Decision:** If an Exploratory Pilot becomes ready, its minimum interpretable
comparison is baseline versus C-short v0.1 as the treatment. Do not include D
v0.1 or another arm without a distinct evidence-based research question. Pilot
execution is currently NO-GO.

**Reason:** Development rejected advancing D v0.1 unchanged and left no fuller
candidate whose incremental value needs testing. C-short is therefore the
treatment, not a dose control for D. A third arm would consume task/run supply
for symmetry rather than information. The current repository has zero confirmed
eligible opaque tasks, no custodian or disjoint allocation, no task-specific
Pilot evaluators, no live subject/tool/config receipt, and no proved provider
cache or run-level billing interpretation.

**Contingent design:** Readiness requires at least 24 opaque eligible tasks across
four predeclared strata, with 12 allocated to Pilot and at least 12 retained
unseen. The proposed budget is 48 planned two-arm/two-repetition trajectories
plus eight infrastructure-only replacements. These are feasibility boundaries,
not a power calculation or authorization.

**Claim boundary:** Pilot estimates would remain exploratory. With zero confirmed
independent experienced reviewers, only exact deterministic acceptance and
guardrail outcomes may be reported; broad quality, maintainability,
proportionality, equivalence, or non-inferiority claims remain prohibited.

**Evidence:** `docs/PILOT_READINESS.md`,
`docs/evidence/exploratory-pilot-readiness-2026-08-27.md`, and
`experiment/pilot_readiness.json`.

**Status:** Active

---

## D-019 — Select SWE-bench-Live metadata frame; evaluator receipt requires redesign

**Decision:** Select `SWE-bench-Live/MultiLang` revision
`62dc0745c40f067fc366ae3eb1a26136e5928f85` as the external source for the
bounded Pilot question. Freeze eligibility version
`swe-bench-live-multilang-v1`, a 12-task/eight-language/12-repository Pilot, and
a repository-disjoint confirmatory reserve. Pilot execution remains unauthorized
and the external-input/evaluator readiness conclusion is **REDESIGN REQUIRED**.

**Reason:** The selected source provides current real-issue provenance,
per-instance images, F2P/P2P and rebuild/test metadata, eight languages, and 634
post-cutoff source-eligible tasks. It reduces policy-author task selection and
contamination risk more directly than the older fixed SWE-bench Multilingual
set. SWE-rebench V2 has much larger supply, but mixes issue- and PR-derived tasks
and includes LLM-generated problem/quality metadata; it is not clearly superior
for this issue-resolution Pilot.

The prior four mechanism strata are not used for external allocation because
they cannot be assigned from source metadata without policy authors reading and
semantically judging task bodies. Language coverage and repository identity are
observable before outcomes. This methodology change is based on source
feasibility, not observed policy effects.

**Partition boundary:** Eligibility rejects task-body fields. The fixed-seed
hash partition emits 12 Pilot IDs and only commitments/counts for 538 reserve
tasks; 84 tasks from Pilot repositories enter neither pool. Development-task
overlap is zero. Confirmatory task bodies remain unseen.

**Evaluator boundary:** The official evaluator requires Linux Docker. The
selected image is amd64 and 0.807 GB compressed, while the current arm64 host has
no container runtime. Preflight therefore stopped before task checkout, Codex,
or provider execution. This is an infrastructure-pre-subject failure, not a task,
provider, evaluator, or policy result. Do not install a runtime, run a subject,
or start Pilot without separate authorization and a passing gold receipt.

**Usage/reviewer boundary:** Codex 0.150.1 reports input, cached input, output,
and reasoning-output tokens, but not provider-billed amount/currency,
cache-write tokens, or a backend snapshot. Calculated values must be labeled as
such. Reviewer capacity remains zero; a deterministic exploratory Pilot may be
possible, but broad quality, maintainability, equivalence, architecture, or
downstream-work claims remain prohibited.

**Evidence:** `docs/EXTERNAL_INPUT_READINESS.md`,
`experiment/external_task_partition.json`,
`experiment/external_smoke_receipt.json`, and
`experiment/external_input_readiness.json`.

**Status:** Active

---

## D-020 — Local Rosetta evaluator passes one task; full Pilot budget remains unproved

**Decision:** Accept Apple Virtualization Framework plus Rosetta as functionally
compatible with the pinned official Linux/amd64 evaluator for the allocated
`BYVoid__OpenCC-1257` infrastructure smoke only. Keep Pilot execution
unauthorized and require a separate pre-Pilot methodological or execution-
environment decision before treating the complete 12-task frame as runnable.

**Reason:** The minimal amd64 canary passed four times, the unchanged official
image started as x86_64, and the exact upstream one-worker gold evaluator passed
three of three runs. A fixed two-turn Codex trajectory also completed through
the official evaluator. However, only one task has measured gold/runtime/memory
evidence; the host is at the 16 GB upstream floor, the remaining manifests are
heterogeneous and as large as 8.95 GB compressed, and upstream warns some large
C++ tasks may need 50 GB. One OpenCC receipt cannot establish the 36-gold/
48-subject budget for all frozen tasks.

**Session boundary:** Codex 0.150.1 `--ephemeral` initial sessions cannot be
resumed for the frozen corrective round. The failed first receipt is retained as
a harness failure. One infrastructure-only replacement established the smallest
workable rule: use a fresh session retained only within its trajectory when a
corrective turn is possible, and never share it across tasks, arms, or runs.
This correction was made before Pilot and changes no task, arm, model, reasoning,
timeout, evaluator, or outcome rule.

**Claim boundary:** The fixed subject remained unresolved after its official
evaluation and corrective round. That is a subject/task smoke outcome, not
evidence about baseline, C-short, efficacy, or preserved quality.

**Evidence:** `docs/EVALUATOR_RUNTIME_READINESS.md` and
`experiment/evaluator_runtime_readiness.json`.

**Status:** Active

---

## D-021 — Fixed-host qualification yields a replacement-linked 12-task pool

**Decision:** Accept a 12-task Pilot pool as operationally qualified on the
fixed 6-CPU/16-GiB Apple-Silicon Docker environment for infrastructure
scheduling only. The qualified pool consists of eight original tasks plus four
same-language, repository-disjoint replacements selected by the frozen
metadata-only hash rule. Pilot execution remains unauthorized.

**Reason:** All 12 frozen tasks received exactly three official gold
evaluations. Eight passed 3/3; Gitoxide and controller-runtime were unstable,
while codegraph and GSD Core repeatedly failed official gold tests. All four
deterministic replacements passed 3/3. Across 48 retained attempts there were
40 PASS, eight FAIL, no detected OOM/resource failure, no timeout, and no
captured architecture/emulation warning line. The fixed environment,
evaluator, RepoLaunch revision, one-worker procedure, and unchanged official
images were preserved.

**Operational boundary:** Qualification consumed 4.16 hours of summed evaluator
wall time. Final-pool medians imply 3.50 evaluator-only hours for one evaluation
of each planned trajectory or 7.00 hours if all receive a second evaluation.
This is sequential scheduling evidence, not a prediction of Codex runtime,
provider billing, cache behavior, human review, or policy effect. Sparse Docker
resource points are not peak telemetry. The completion snapshot reported 180.6
GB of local Docker images with shared layers and does not establish free-space
headroom.

**Reserve consequence:** The four replacement repositories join the effective
Pilot pool, so 39 tasks from those repositories are removed from the opaque
confirmatory reserve. The effective reserve is 499 tasks across 207 repositories
with ranked-ID commitment
`609b0dfba0a27dbd535f3db67375d84a454c7ad98b7fdd03cf501fdd16958930`.
No reserve IDs or task bodies were emitted; the original partition and
eligibility definitions remain unchanged.

**Evidence:** `docs/PILOT_HOST_QUALIFICATION.md` and
`experiment/pilot_host_qualification.json`.

**Status:** Active; supersedes D-020 only on full-pool host qualification. D-020
remains historical evidence for the earlier single-task runtime gate and its
trajectory-local session rule.

---

## D-022 — Joint Pilot readiness requires a bounded harness/contract redesign

**Decision:** Do not authorize the Exploratory Pilot yet. Preserve baseline
versus `C-short v0.1`, the qualified replacement-linked 12-task pool, the fixed
subject/host/evaluator configuration, and all narrow claim boundaries. Require
one bounded Pilot Harness and Reserve Contract Qualification goal before another
execution-readiness decision.

**Satisfied inputs:** The source contains 634 eligible tasks; the original
partition is deterministic; the effective reserve retains 499 tasks across 207
repositories; all 12 final Pilot tasks passed three of three official gold
evaluations; one non-comparative two-turn fixed-subject trajectory proved
trajectory-local resume and official evaluator feedback; provider token
components are observable; fixed-host scheduling is operationally feasible.

**Blocking evidence:** The repository has no integrated Pilot runner/live batch
canary that enforces the frozen allowlisted environment, tool/feature receipt,
trajectory-local correction, process-group timeout cleanup, and complete
failure/missingness ledger. The historical order formula is not durably bound to
the v1 external seed and final replacement-linked pool. Host qualification also
consumed four task-slot substitutions from an allowance of eight, while Pilot
design records eight trajectory-level infrastructure reruns; their distinct
units and authority are not prospectively reconciled.

**Compatible limitations:** Zero experienced reviewers does not block exact
deterministic feasibility questions but prohibits broad maintainability,
quality, equivalence, non-inferiority, and downstream-work claims. Cache-write
tokens, provider billing, cache namespace separation, and exact backend snapshot
remain unavailable, so billed-cost claims are prohibited. MCID, quality margin,
confirmatory estimand, and confirmatory sample size remain unresolved until
Freeze and are not selected from Pilot/runtime evidence.

**Smallest next goal:** Implement and qualify only the deterministic Pilot batch
harness and prospectively freeze the v1 schedule plus non-overlapping
replacement-budget units using dry-run and non-comparative canaries. Stop before
the first baseline-versus-C-short task cell. This is preferable to changing the
policy, qualified task pool, Docker allocation, official images, or hardware.

**Evidence:** `docs/PILOT_EXECUTION_READINESS_DECISION.md` and
`experiment/pilot_execution_readiness.json`.

**Status:** Active; Pilot remains unauthorized.

---

## D-023 — Pilot execution contract closes the three bounded readiness blockers

**Decision:** Qualify the exact proposed Exploratory Pilot execution manifest and
record **GO TO EXPLORATORY PILOT**, while leaving the Pilot goal inactive and
executing zero Pilot cells. The completed D-022 decision remains the historical
reason this bounded qualification was required.

**Contract:** `pilot-v1.0` binds Codex 0.150.1, `gpt-5.6-terra` at medium,
workspace-write automatic review, repository-only tools, empty MCP/plugin/hook
sets, the pinned source/evaluator/platform, two turns, one corrective round,
900-second turn and 1,800-second trajectory-attempt timeouts, isolation roots,
usage fields, and a predeclared failure taxonomy. Preflight and receipt mismatch
is a visible failure; the harness does not normalize drift.

**Pool and order:** The 12 original task slots resolve to eight originals and
four already-authorized host replacements. The body-free canonical pool digest
is `611693dc971177e76b5d7b45eb58f8dffd7c4821bf12b0dc6c540b6d580973fa`.
The 48-cell, per-task arm-interleaved schedule is derived from that digest, the
two surviving arms, two repetitions, `pilot-v1.0`, and the recorded v1 seed;
its digest is
`ab92971b4309ecb6a7ccdd18c97358a2db4ba3342261c6831f8d6b0ace04aa2e`.
Changing a slot requires a new pool identity, contract, and schedule.

**Distinct budgets:** `task_slot_replacement_budget` is pre-treatment and records
8 allowed, 4 consumed, 4 remaining before finalization. The separate
`trajectory_infrastructure_rerun_budget` records 8 available same-cell reruns,
at most one per task × arm × repetition cell. Only provider/API and local
Docker/runtime infrastructure failures can consume it. Agent failure, evaluator
failure, timeout, poor performance, or any result cannot.

**Integrity and claims:** Hash-chained JSONL events retain every failed and later
attempt. Contract/isolation and malformed-measurement failures stop the batch.
Provider-side cache isolation, cache-write tokens, backend snapshot, and billed
amount/currency remain unavailable rather than guaranteed. Reviewer capacity,
MCID, quality margin, surviving arms, C-short bytes, and all broad claim
prohibitions remain unchanged.

**Evidence:** `docs/PILOT_HARNESS_QUALIFICATION.md`,
`experiment/pilot_execution_contract.json`, and
`experiment/pilot_harness_qualification.json`.

**Status:** Active; exact Pilot goal proposed for human review, not activated.

---

## D-024 — Strict Pilot preflight stops before cell 1 on harness failure

**Decision:** Preserve the activated Execute Exploratory Pilot goal as blocked
and execute zero Pilot cells. The strict preflight restarted from the merged
readiness state and stopped at the frozen `harness_failure` integrity boundary.

**Passing evidence:** `HEAD` and `origin/main` matched the merged readiness
commit; the worktree was clean; the tracked contract regenerated byte-for-byte;
its contract, pool, schedule, and C-short commitments matched. The fixed Codex
subject, Docker/architecture/resources/images, evaluator/source revisions,
repeated isolation canary, empty Pilot state roots and ledger, and zero reserve
exposure checks passed.

**Blocking evidence:** The qualified implementation prepares and validates the
execution plan, receipts, budgets, and ledger semantics but explicitly does not
launch Codex, Docker, the evaluator, or a policy-comparison cell. Its command
surfaces build/audit the contract and audit synthetic/no-op qualification only.
There is no integrated live batch runner enforcing the frozen schedule,
process-group timeouts, same-session corrective round, official evaluator,
attempt receipts, and hash-chained ledger. D-023 therefore remains valid as
contract-semantics qualification and GO readiness evidence, but it is not proof
that a live runner exists.

**Integrity and claim boundary:** `harness_failure` is a frozen batch-stop class.
No repair, regeneration, or experimental-parameter change was made. Zero Pilot
cells and zero policy comparisons executed. This blocked result, its commit,
PR, and merge are not efficacy evidence.

**Evidence:** `docs/PILOT_PREFLIGHT_BLOCKED.md` and
`experiment/pilot_preflight.json`.

**Status:** Active; Execute Exploratory Pilot remains blocked pending separately
authorized and qualified live-runner work or an explicit resolution of the
discrepancy.

---

## D-025 — Pilot runner derives resume state only from the frozen ledger

**Decision:** Implement one sequential `preflight`/`dry-run`/`execute` runner
around the frozen `pilot-v1.0` contract and existing contract, receipt, usage,
rerun, and hash-chain machinery. The runner may execute only with an explicit
contract-digest confirmation token. This qualification does not invoke that
command or authorize Pilot execution.

**State model:** The hash-chained Pilot ledger is the sole durable authority.
Its prefix records the frozen contract, four historical task-slot replacements,
and schedule identity. Each live attempt records `attempt_started` before any
subject work and `attempt_finished` only after receipt validation. A completed
experimental outcome advances exactly one schedule cell. A predefined
provider/API or local Docker/runtime failure may authorize the same cell's
second attempt only within the distinct trajectory-rerun budget. A batch-stop
class or exhausted rerun allowance stops the ledger. Duplicate, out-of-order,
wrong-task/arm/subject, reused-root, corrupt-chain, or post-stop events fail
closed.

**Crash boundary:** A start without a finish is an explicit partial attempt.
Restart never treats it as unstarted, completed, or experimentally valid and
never reruns it automatically. Resumption requires an explicit frozen
infrastructure/batch-stop classification; experimental failure is never
inferred from partial state. The runner uses a process lock and durable ledger
sync but does not add a second workflow database or repair records.

**Subject/evaluator boundary:** The official qualified task image supplies a
fresh `/testbed` checkout. Codex runs with the frozen model/reasoning/approval
configuration, ignored user config/rules, an allowlisted environment, and a
trajectory-local non-ephemeral session retained only for the single corrective
round. The repository Git diff is preserved and wrapped only in the official
`{instance_id: {model_patch: ...}}` prediction format. The pinned official
SWE-bench-Live evaluator remains authoritative; the runner consumes its
`report.json` and `results.json` rather than reproducing grading logic.

**Budget and claim boundary:** Post-freeze task-slot replacement authority
remains zero and is never replenished by trajectory reruns. Missing provider
usage remains unavailable and makes an otherwise experimental receipt
malformed; cache-write tokens, billed currency/amount, and backend snapshot are
not invented. Runner qualification is orchestration evidence only, not policy,
task-success, cost, or quality evidence.

**Evidence:** `src/engineering_scope_guard/pilot_runner.py`,
`scripts/pilot_runner.py`, `scripts/pilot_dataset_bridge.py`,
`tests/test_pilot_runner.py`, `experiment/pilot_runner_preflight.json`,
`experiment/pilot_runner_dry_run.json`, and
`docs/PILOT_RUNNER_QUALIFICATION.md`.

**Status:** Active; runner-qualified implementation prepared for review, with
zero Pilot cells and zero policy comparisons executed.

---

## D-026 — Real Pilot stops at cell 1 on authentication and start-state integrity defects

**Decision:** Preserve the terminal frozen ledger and conclude **REDESIGN
REQUIRED**. Do not patch or resume this batch, do not use the failed attempt as
arm evidence, and do not start Freeze.

**Passing entry gates:** Local `main` equaled `origin/main` at merged runner
commit `a6b837cf2fbff51762ee5e0985f8c1acecd112c7`. The tracked frozen contract
audited at canonical digest
`1ec191306215936c4f17bd0805d0a4619e0530a4d79c91c0240212b26226ead0`.
Strict live preflight passed the subject interface, pinned dataset/evaluator/
RepoLaunch revisions, Docker resources, 12 image identities, and zero-state
checks.

**Terminal evidence:** Cell `slot-04-baseline-rep-1` launched once. Its fresh
Codex home had no authentication state, while both allowlisted API-key variables
were unset. Codex 0.150.1 emitted repeated message-only HTTP 401 errors, no
successful turn, and no usage. The runner's structured-code-only provider
failure detector did not recognize that schema; the attempt therefore became
`malformed_incomplete_measurement`, followed by the frozen terminal
`batch_stopped` event. The evaluator never ran.

**Independent isolation evidence:** The copied official task repository was at
the frozen base commit but already had one modified tracked file and 76
untracked build/test artifacts. No subject command item occurred, so the state
was dirty before subject work. A matching `HEAD` alone is insufficient evidence
of the frozen clean task state.

**Counts and claims:** One cell launched; zero valid cells, experimental
outcomes, evaluator invocations, policy comparisons, reruns, or post-freeze
replacements occurred; 47 cells remained unstarted. Usage is unavailable and
no arm effect, cost distribution, task outcome, policy efficacy, or quality
claim can be estimated.

**Next boundary:** Any future execution requires a separately authorized and
qualified runner/contract version that establishes an isolated authentication
handoff, validates the actual Codex provider-error schema, and proves a clean
repository start. It must decide prospectively how the terminal attempted cell
and already-inspected Pilot task are handled; the current ledger is not repaired
or reset.

**Evidence:** `docs/EXPLORATORY_PILOT_REPORT.md`,
`experiment/exploratory_pilot_result.json`, and the ignored local
`.local/pilot-runner` ledger/attempt state.

**Status:** Active; this terminal execution result supersedes D-025 only on live
runner adequacy. The frozen contract and prior qualification remain historical
evidence, not efficacy evidence.

---

## D-027 — Preserve task-image state and attribute only baseline-relative subject changes

**Decision:** Repair the execution boundary without changing frozen
experimental bytes. Provision only the observed file-backed `auth.json` into
fresh restrictive Codex homes, recognize the observed message-only HTTP 401 in
bounded provider event contexts, and capture each official task image's exact
pre-subject Git tree. Derive the evaluator model patch relative to that tree;
do not reset or clean the authoritative image.

**Rationale:** The pinned evaluator applies the submitted patch into the same
task-image state. Removing pre-existing tracked, untracked, or ignored build
state would change evaluation semantics, while diffing from HEAD falsely
attributes image residue to the subject. An alternate-index tree preserves the
authoritative environment and yields a deterministic subject-only patch.

**Qualification:** Two fresh non-Pilot authenticated canaries passed and
removed their credential copies. All 12 frozen images matched their base
revisions and produced empty no-subject patches. Fresh slot 4 exactly reproduced
the failed cell-1 repository state. The contract and ledger were byte-identical
before and after; no Pilot or evaluator invocation occurred.

**Resume boundary:** The existing ledger remains terminal at `batch_stopped`.
The repaired classification would prospectively make the observed provider
failure a one-unit same-cell infrastructure rerun, but it does not authorize
relabeling or extending the preserved batch. Therefore the outcome is
**REDESIGN REQUIRED**.

**Evidence:** `docs/PILOT_EXECUTION_INTEGRITY_REPAIR.md`,
`experiment/pilot_execution_integrity_qualification.json`,
`src/engineering_scope_guard/pilot_integrity.py`, and
`tests/test_pilot_integrity.py`.

**Status:** Active as the execution-integrity boundary for any future Pilot
design; it does not authorize Pilot execution.

---

## D-028 — A terminal zero-outcome Pilot continues only through a bound successor

**Decision:** Qualify one immutable successor-batch lineage as an explicit
post-freeze, pre-outcome infrastructure protocol amendment. Do not reopen,
append to, truncate, reset, or relabel the terminal predecessor. Do not execute
the successor during qualification.

**Scientific boundary:** The predecessor contains one launched invalid attempt,
zero successful subject turns, zero valid completed cells, zero evaluator runs,
and zero policy comparisons. The recorded `malformed_incomplete_measurement`
classification remains unchanged. The integrity repair independently established
that the underlying pre-subject failure was an HTTP 401 provider-authentication
failure, already covered by the frozen `provider_api_infrastructure_failure`
same-cell rerun class. No outcome-conditioned selection occurred.

**Lineage and accounting:** The separate authorization binds the unchanged
contract, schedule, pool, policies, subject/evaluator configurations,
predecessor ID/final hash/taxonomy/counts, successor ID, original cell 1, and
restart reason. Successor cell 1 is attempt 2 and consumes one existing rerun
unit; seven remain. Cells 2-48 are first attempts. No budget is reset or added.
The fresh successor-ledger genesis binds the authorization, contract,
predecessor terminal hash, and successor ID without copying observations.

**Qualification:** Strict live-input preflight and an exact 48-cell dry-run
passed. The dry-run made zero subject/evaluator calls and wrote zero experimental
observations. The predecessor nine-event ledger and frozen contract remained
byte-identical. Authentication/provider/baseline/evaluator/corrective/timeout
integrity evidence was reused because no provider-facing runner bytes changed.

**Evidence:** `docs/PILOT_SUCCESSOR_BATCH_AUTHORIZATION.md`,
`experiment/pilot_successor_batch_authorization.json`, and
`experiment/pilot_successor_batch_qualification.json`.

**Status:** **SUCCESSOR-BATCH QUALIFIED — GO TO EXECUTE SUCCESSOR PILOT** in a
separate explicitly authorized goal; no successor execution occurred here.

---

## D-029 — Successor execution stops at an unresolved receipt boundary

**Decision:** Preserve the successor ledger and attempt evidence exactly as
written and conclude **REDESIGN REQUIRED**. Do not patch the runner, synthesize
or append a receipt, retry cell 1, create another successor, resolve the partial
attempt, or treat its subject/evaluator artifacts as a valid experimental
observation.

**Passing entry gates:** Fetched `main` exactly matched merged successor
authorization commit `104f82ce2e35ed04e1e0f8acecf648e045d2bb52`.
Original contract, successor authorization, predecessor lineage, pinned inputs,
Docker resources, Codex 0.150.1, credential isolation, and the exact 48-cell
successor dry-run passed strict live preflight. The predecessor ledger remained
byte-identical.

**Execution evidence:** Original schedule cell 1,
`slot-04-baseline-rep-1`, started correctly as successor attempt 2. This was
the first successor attempt to complete both a real subject turn and an official
evaluator process. Receipt construction then raised `TypeError: 'str' object is
not callable`: the production live backend stored `ended_at` as a string,
while the core receipt boundary called it as a callable. Credential cleanup
completed.

**Durable state and accounting:** The separate successor ledger contains eight
events and ends at `attempt_started`; the state machine reports
`resolve_partial`. The state is recoverable but undecided, not reset and not
terminally rewritten. Attempt 2 remains visible, no later retry was consumed,
no additional successor was created, and no policy comparison or valid
completed cell exists.

**Qualification boundary:** The prior runner qualification established
deterministic state-machine behavior with a fake backend, but did not validate
the exact live runtime type of `ended_at` across the production adapter/core
boundary. This infrastructure/measurement-boundary failure is not evidence for
or against baseline or C-short v0.1.

**Frozen-byte boundary:** The frozen contract, successor authorization,
treatments, schedule, subject/evaluator configurations, and runner bytes used by
the attempt remain unchanged. Any compatibility repair or partial-attempt
resolution requires a separate pre-outcome authorization and must not be folded
into this evidence-only change.

**Evidence:** `docs/EXPLORATORY_PILOT_REPORT.md`,
`experiment/exploratory_pilot_result.json`, and the ignored local
`.local/pilot-successor-runner` ledger/attempt state.

**Status:** Active as the authoritative successor execution boundary; zero
valid cells and zero policy comparisons exist.

---

## D-030 — Repair the receipt boundary but stop the unrecoverable Pilot

**Decision:** Normalize direct and deferred timestamps at one receipt boundary,
defer the live end timestamp until work completes, and derive only the
contract-declared total-token field. Do not resolve the preserved partial
attempt. End **STOP PILOT** because mandatory durable evidence is missing and a
third same-cell attempt is outside the frozen allowance.

**Root cause:** The production adapter returned direct strings for both timing
fields while the core called `ended_at` as a zero-argument accessor. The prior
fixture covered only a callable. The same boundary also expected provider
`total_tokens`, although the frozen contract defines it as derived from the four
provider components.

**Compatibility boundary:** Direct timezone-aware ISO strings and zero-argument
accessors are normalized centrally. The original timestamp string and offset
are preserved. Null, naive, malformed, or unknown forms fail closed. The live
adapter now defers end-time observation. Provider usage components are preserved
and `total_tokens` alone is derived as input plus output.

**Recovery evidence:** The preserved subject turn, configuration, identities,
four usage components, baseline, prediction mapping, zero-byte patch, contract,
authorization, and ledger lineage are complete. The per-instance evaluator
report, durable evaluator command/exit status, prepared receipt timestamps, and
final in-memory termination metadata are absent. The preserved `results.json`
is uniquely task-bound and reports an empty patch, but is not a complete frozen
evaluator receipt.

**State/accounting:** The successor remains at eight-event `resolve_partial`.
No existing successor transition finalizes a valid receipt from artifacts. Cell
1 is attempt 2, already the frozen per-cell maximum, so attempt 3 is not legal;
the seven remaining batch-level units do not override that limit. The recovery
preview appends no event and consumes no rerun.

**Scientific boundary:** This is another post-freeze, pre-valid-outcome
infrastructure repair exposed by the Exploratory Pilot. It changes no treatment,
task, evaluator, schedule, timeout, corrective, budget, analysis, or claims
semantic and supplies no policy comparison.

**Infrastructure lesson:** A subject/evaluator execution must durably persist
the authoritative evidence required for receipt reconstruction before receipt
finalization becomes a single point of failure. Applying that lesson to a future
experiment is out of scope here; this decision does not design Pilot v2.

**Evidence:** `docs/PILOT_PARTIAL_RECOVERY_QUALIFICATION.md`,
`experiment/pilot_partial_recovery_qualification.json`, sanitized fixtures, and
the ignored immutable successor attempt artifacts.

**Status:** **STOP PILOT**. No resolve, rerun, continuation, or new successor is
authorized by this decision.

---

## D-031 — Pilot-v2 requalification stops at the one-shot pre-subject boundary

**Decision:** Preserve the failed one-shot `BYVoid__OpenCC-1096` canary attempt
and end **REDESIGN REQUIRED**. Do not patch and rerun the canary in this goal,
derive the Pilot-v2 pool, freeze a Pilot-v2 execution contract, or execute a
Pilot-v2 subject.

**Deterministic qualification:** The minimum atomic checkpoint layer passed all
seven required fault boundaries and reconstructs a valid receipt from durable
evaluator evidence after downstream receipt failures. It reuses the qualified
credential, provider, baseline, patch, timestamp, usage, corrective-session,
worker=1, and official-evaluator boundaries. All 133 repository tests, focused
tests, warning-clean compilation, and whitespace checks passed.

**Live evidence:** The authorized `run-canary` command was invoked once for the
exact metadata-selected non-Pilot task. It returned nonzero when its local
dataset-bridge subprocess failed after preflight but before canary state
creation. Therefore it made zero credential copies, provider subject calls,
official evaluator calls, Pilot-v2 calls, or policy comparisons. The exact
read-only bridge lookup later succeeded, so the original child cause remains
unavailable; no live retry was used to resolve that ambiguity.

**Materiality:** The one-shot path failed before emitting durable canary state
or a sanitized failure receipt. A complete terminal canary is an explicit gate,
and deterministic evidence cannot substitute for it. Repair-and-rerun is
forbidden by the active goal, so pool derivation and contract freeze are not
authorized.

**Historical and claims boundary:** Pilot v1 remains byte-identical historical
infrastructure evidence with zero valid cells and zero comparisons. Neither the
failed canary nor its deterministic qualification is evidence for or against
baseline or `C-short v0.1`.

**Evidence:** `docs/PILOT_V2_REQUALIFICATION.md` and
`experiment/pilot_v2_canary_qualification.json`.

**Status:** **REDESIGN REQUIRED**; zero Pilot-v2 task/evaluator calls and no v2
pool, schedule, or execution contract were frozen.

---

## D-032 — Preserve the evaluator virtual-environment interpreter path

**Decision:** Classify the `BYVoid__OpenCC-1096` discrepancy as a deterministic
implementation defect and qualify one canonical dataset resolver without a
live canary. Preserve `.venv/bin/python` symlinks when making the interpreter
path absolute; do not use `Path.resolve()` for this process boundary.

**Evidence:** The failed wrapper dereferenced the evaluator interpreter to the
base Python, where `sys.prefix == sys.base_prefix` and `pyarrow` was unavailable.
The later read-only lookup used the virtual-environment symlink, where the same
Python version had `pyarrow 25.0.1`. The bounded matrix reproduced the legacy
failure, passed fresh and repeated canonical resolution with one identical
metadata digest, and used only the pinned local parquet bytes.

**Repair:** `scripts.pilot_runner.canonical_evaluator_python` preserves the
symlink, and both the established runner and qualification route through
`scripts.pilot_runner.resolve_dataset_task`. Regression tests bind this path
behavior. No retry, cache system, service, downloader, mirror, or orchestration
layer was added.

**Experimental boundary:** The qualification made zero Codex, credential,
evaluator, live-canary, Pilot-ledger/receipt, Pilot-v2-freeze, or policy calls.
It does not revive Pilot v1 or authorize execution in this goal.

**Evidence artifacts:** `docs/DATASET_BRIDGE_DETERMINISM_TRIAGE.md` and
`experiment/dataset_bridge_qualification.json`.

**Status:** **DATASET BRIDGE QUALIFIED — GO TO ONE FINAL LIVE CANARY**. A final
live canary still requires a separate active goal and explicit authorization.

---

## D-033 — One compact GitHub-first terminal handoff

**Decision:** Maintain exactly one canonical current handoff at
`experiment/agent_handoff.json`, backed by a portable schema and a deterministic
standard-library validator. It is a coordination index, not an evidence store,
authorization source, service, or autonomous roadmap mechanism.

**State boundary:** Record the latest terminal repository goal separately from
the still-operative experimental or operational decision. A documentation or
protocol goal therefore does not erase the Dataset Bridge qualification or
silently authorize its final canary.

**Authority and privacy:** Use a closed action/authorization vocabulary, fail
closed on conflicts with authoritative artifacts, and require explicit user
authority for provider, credential, benchmark-egress, Pilot, treatment,
held-out-data, retry-budget, or evidence-reset actions. Store no credentials,
raw provider traces, private task bodies, local paths/state, or Graphify output.

**Git semantics:** Use `pending_pr` until stable PR metadata exists, then derive
CI/CodeQL state from that PR. A null `git.head_sha` with
`omitted_to_avoid_self_reference` is deliberate: Git supplies the containing
and merge commits, so the handoff does not create commits merely to name their
own SHA. At most one follow-up commit may record stable PR number/URL metadata.

**Evidence:** `docs/AGENT_HANDOFF_PROTOCOL.md`,
`experiment/agent_handoff.schema.json`, `tests/test_agent_handoff.py`, and 146
passing repository tests.

**Status:** **AGENT HANDOFF PROTOCOL BOOTSTRAPPED — READY FOR GIT
STABILIZATION**. The final live canary remains unauthorized and unexecuted.

---

## D-034 — Final live non-Pilot canary qualifies the complete infrastructure path

**Decision:** Accept the exactly-once `BYVoid__OpenCC-1096` canary as qualified
infrastructure evidence. It completed one fixed baseline Codex trajectory and
one official evaluator round with `accepted_completed`, evaluator resolution,
complete provider usage components, durable `ledger_committed` state, and a
terminal `complete` ledger action.

**Authority and integrity:** The user explicitly authorized one execution,
credential use, provider usage, official evaluation, and sanitized evidence.
The command ran once with no substitute, retry, corrective round, repair, or
infrastructure-rerun budget use. The fixed evaluator virtual-environment path
and canonical resolver were used.

**Privacy and claims boundary:** The isolated credential was removed. The
repository receipt contains no credential, raw prompt, raw provider content,
or temporary workspace. This is infrastructure qualification only: Pilot-v2
subject/evaluator calls remain zero, policy comparisons remain zero, and no
Pilot-v2 or confirmatory task was exposed.

**Next action:** The sanitized evidence may be stabilized through Git under the
current explicit authorization. After merge, any next experimental goal,
including Pilot-v2 pool derivation, contract freeze, or execution, requires a
separate authority decision.

**Evidence:** `docs/FINAL_LIVE_CANARY_QUALIFICATION.md` and
`experiment/pilot_v2_canary_qualification.json`.

**Status:** **FINAL LIVE CANARY QUALIFIED — NEXT GOAL REQUIRES SEPARATE
AUTHORIZATION**.

---

## D-035 — Pilot v2 excludes the exposed v1 task and preserves the opaque reserve

**Decision:** Prepare `pilot-v2.0` from the 11 unexposed tasks in the already
host-qualified Pilot-v1 pool. Exclude `xroche__httrack-408` because it reached a
Pilot-v1 subject and evaluator before its receipt failed. Do not replace it from
the confirmatory reserve, run a new evaluator qualification, or execute a
Pilot-v2 cell in this goal.

**Methodology:** The exclusion is based on prospective exposure integrity, not
the task's unavailable outcome or an arm effect. The 11-task pool therefore has
seven represented languages and a 44-cell schedule: two arms by two repetitions
per task. The post-Pilot-v1 confirmatory reserve remains opaque and unchanged at
499 tasks across 207 repositories with ranked-ID commitment
`609b0dfba0a27dbd535f3db67375d84a454c7ad98b7fdd03cf501fdd16958930`.

**Contract:** Preserve baseline, `C-short v0.1`, Codex/model/reasoning,
subject/evaluator configuration, isolation, corrective-round and timeout rules,
failure taxonomy, complete usage requirements, and the eight-unit same-cell
infrastructure-rerun allowance. Set post-freeze task-slot replacement authority
to zero. Bind the shared runner to the v2 contract, v2 state root, and a
contract-digest confirmation token.

**Authority and Git boundary:** Preparation used only deterministic regeneration,
mutation rejection, synthetic/dry-run checks, and sanitized prior metadata.
Pilot-v2 subject/evaluator calls, executed cells, comparisons, and confirmatory
task-body exposures are all zero. The exact live preflight requires tracked
`HEAD` bytes, while branch/commit/push/PR/merge work is separately authorized;
therefore this goal stops at Git stabilization before execution authorization.

**Evidence:** `docs/PILOT_V2_FREEZE_READINESS.md`,
`experiment/pilot_v2_execution_contract.json`, and
`experiment/pilot_v2_freeze_qualification.json`.

**Status:** **PILOT-V2 FREEZE PREPARED — GIT STABILIZATION AND EXECUTION
AUTHORIZATION REQUIRED**.

---

## D-036 — External operator interruption stops Pilot-v2 without a fabricated rerun

**Decision:** Preserve the `pilot-v2.0` execution exactly at the externally
interrupted state: six admissible completed cells followed by cell 7
`attempt_started`. Do not append a synthetic receipt or terminal event, do not
classify the user interruption as provider or Docker/runtime infrastructure,
do not rerun cell 7, and do not execute cells 8-44.

**Observed cause:** The user requested an operational pause because they needed
to leave and intended to continue later. The user supplied contemporaneous
context that this was unrelated to baseline/C-short performance, evaluator
outcomes, token usage, task difficulty, or any interim comparison. That context
records cause but does not create rerun or continuation authority.

**Frozen-contract implication:** The state machine reports `resolve_partial`,
but its resumable classes cover only provider or local Docker/runtime
infrastructure failures. Operator interruption is not a frozen resumable class.
Calling it infrastructure would fabricate rerun entitlement; adding a new class
or successor here would be a post-outcome protocol change. The current goal
therefore stops with the unresolved partial ledger preserved unchanged.

**Evidence and claims boundary:** The 15-event ledger remains SHA-256
`a998efd2c7e1783607c3494b3a38baca174e3760066f34125288f685012344b5`;
its last event is cell 7 `attempt_started`, SHA-256
`d344cc5f725d4c7985e3208dadd10a6110ff38f3f599f4b7ad5155af4a51c83c`.
No interim arm-effect, token, cost, difficulty, or policy comparison was
performed. This is evidence of protocol incompleteness, not policy efficacy.

**Next action:** Request separate authorization for a bounded methodology
decision on whether an operator-interruption successor or continuation can be
scientifically admissible while preserving the original ledger, exposure,
schedule, and accounting. Do not create or execute that continuation in this
goal.

**Evidence:** `docs/PILOT_V2_TERMINAL_REPORT.md` and
`experiment/pilot_v2_terminal_result.json`.

**Status:** **PILOT-V2 EXECUTION STOPPED — EXTERNAL INTERRUPTION REQUIRES A
SEPARATE PROTOCOL-COMPLETENESS DECISION**.

---

## D-037 — Qualify one separate operator-interruption continuation lineage

**Decision:** Qualify one immutable `pilot-v2.0` continuation lineage beginning
at original schedule position 7. Cells 1-6 remain valid predecessor observations
and must not be copied or rerun. Cell 7 attempt 1 remains incomplete in the
original ledger; the continuation restarts the identical cell in fresh isolation
as attempt 2. Cells 8-44 keep their exact original identities, ordering, and
attempt-1 starts. Execution requires a separate authorization.

**Scientific basis:** The external operational interruption was documented
contemporaneously as unrelated to arm performance, evaluator outcome, usage,
task difficulty, or an interim comparison, and no interim arm-effect analysis
occurred. A separate ledger makes the post-interruption exploratory amendment
explicit while keeping the frozen contract and original ledger immutable. This
does not make the omitted transition prospective or establish a confirmatory
precedent.

**Accounting:** Record the cell 7 restart as one distinct
`operator_interruption_restart` unit, consumed with zero remaining. It is not an
infrastructure failure and consumes none of the existing eight infrastructure-
rerun units. No existing retry/rerun budget is increased or reset. The two-total-
attempt cap still applies, so cell 7 has no third attempt under any category;
cells 8-44 retain the original infrastructure rules.

**Future confirmatory boundary:** Before confirmatory execution, freeze planned
between-cell pauses, a numeric operator-interruption allowance separate from
infrastructure, contemporaneous cause recording before outcome review, immutable
retention/no relabeling, next-attempt numbering with fresh isolation, the two-
attempt per-cell cap, stop-on-exhaustion behavior, and a ban on interim-effect
review before restart. No confirmatory allowance value, task body, or execution
is frozen here.

**Evidence:** `docs/PILOT_V2_CONTINUATION_QUALIFICATION.md`,
`experiment/pilot_v2_continuation_authorization.json`, and
`experiment/pilot_v2_continuation_qualification.json`.

**Status:** **CONTINUATION QUALIFIED — EXECUTION REQUIRES SEPARATE
AUTHORIZATION**.

---

## D-038 — Bind the frozen continuation to the qualified runner through durable state

**Decision:** Add one continuation-specific entry point that validates the
frozen authorization and lineage, then reuses the qualified Pilot runner's
launch envelopes, receipt taxonomy, executor, credential cleanup, evaluator
adapter, and fsynced ledger writer. Do not add another scheduler, backend,
service, generalized orchestrator, or successor lineage.

**State and accounting:** Derive every action from the separate hash-chained
continuation ledger. Exclude positions 1-6 from the executable view; start the
unchanged position-7 cell only as attempt 2; start positions 8-44 only as
attempt 1 unless their original infrastructure rule later applies. The consumed
operator restart contributes zero infrastructure-rerun units but also exhausts
cell 7's two-total-attempt cap, so no attempt 3 is legal. The existing
eight-unit infrastructure allowance remains separate, unchanged, and at zero
consumed at genesis.

**Isolation and durability:** Reuse fresh per-attempt repository, Codex home,
session, credential copy, raw/derived output, and evaluator-output paths. Keep
the pinned evaluator source checkout immutable. Fsync each attempt start,
receipt, rerun authorization, and stop before deriving the next action or
returning final aggregation. Fail closed on stale trajectory credentials or
any authorization, contract, predecessor, genesis, schedule, task, attempt, or
accounting drift.

**Authority boundary:** Deterministic preflight, complete dry-run, and fault
injection are authorized and produced zero provider/evaluator calls and zero
Pilot cells. The live command requires a separate continuation-digest
confirmation, but that mechanism does not itself grant user authority. This
goal and its stabilization workflow do not authorize live continuation.

**Evidence:**
`docs/PILOT_V2_CONTINUATION_EXECUTION_INTERFACE_QUALIFICATION.md`,
`experiment/pilot_v2_continuation_execution_preflight.json`,
`experiment/pilot_v2_continuation_execution_dry_run.json`, and
`experiment/pilot_v2_continuation_execution_qualification.json`.

**Status:** **CONTINUATION EXECUTION INTERFACE QUALIFIED — LIVE EXECUTION
REQUIRES SEPARATE AUTHORIZATION**.

---

## D-039 — Stop Pilot-v2 continuation on the frozen malformed-measurement class

**Decision:** Accept the continuation ledger's terminal `batch_stopped` event
without repair, rerun, relabeling, or successor creation. Position 9 attempt 1
returned an official unresolved evaluator result with no failing checks, which
the frozen runner deterministically classifies as
`malformed_incomplete_measurement`.

**Analysis boundary:** Two continuation cells are admissible and one is invalid;
together with the predecessor there are 8/44 admissible cells. The incomplete
schedule and mandatory batch stop make frozen exploratory arm-effect analysis
inadmissible. Do not compare arms or make confirmatory, general-efficacy, or
billed-cost claims.

**Evidence:** `docs/PILOT_V2_CONTINUATION_TERMINAL_REPORT.md` and
`experiment/pilot_v2_continuation_terminal_result.json`.

**Status:** **PILOT-V2 CONTINUATION STOPPED — MALFORMED INCOMPLETE
MEASUREMENT; EXPLORATORY ANALYSIS INADMISSIBLE**.

---

## D-040 — Qualify the prospective evaluator boundary and permanently close Pilot-v2

**Decision:** Classify the position-9 root cause as an adapter/parser defect.
The official evaluator emitted one coherent failure disposition (`resolved:
false`, the instance in `failure_ids`, and zero error/incomplete entries), but
the adapter discarded that aggregate disposition and the frozen runner treated
unavailable named corrective feedback as incomplete measurement.

**Prospective boundary:** Validate one unique official disposition—`success`,
`failure`, `error`, `incomplete`, or `empty_patch`—and preserve it separately
from `feedback_status`. Contradictory identities, counts, memberships, or
reports fail closed. A future contract must predeclare what happens when a
valid official failure has no named corrective feedback; it may not invent
feedback or infer another outcome.

**Benchmark decision:** Retain the current SWE-bench-Live / official evaluator
stack as eligible for a separately authorized fresh exploratory design. The
basis is the defined structured semantics, the prospectively qualified adapter
boundary, and three prior successful official gold qualification runs for the
affected task—not any arm outcome. No new task pool or schedule is designed or
frozen here.

**Immutability and closure:** Position 9 remains
`malformed_incomplete_measurement`; `batch_stopped`, 8/44 admissible
observations, positions 10-44 unstarted, zero arm-effect analysis, and zero
efficacy conclusions remain unchanged. Pilot-v2 is permanently closed. No
successor, continuation, restart, recovery, or further execution is permitted.

**Evidence:**
`docs/PILOT_V2_MEASUREMENT_BOUNDARY_TRIAGE_AND_CLOSURE.md`,
`experiment/pilot_v2_measurement_boundary_qualification.json`, the prospective
official-result parser and synthetic terminal-shape fixtures.

**Status:** **MEASUREMENT BOUNDARY QUALIFIED — FRESH PILOT DESIGN PERMITTED**.

---

## D-041 — Freeze a fresh eight-task Pilot-v3 with prospective durability and pause rules

**Decision:** Freeze one fresh exploratory `pilot-v3.0` contract comparing only
baseline with byte-exact `C-short v0.1`. Select one task per available language
from the post-Pilot-v1 effective opaque reserve using a new SHA-256 rank over
the existing metadata-only eligibility projection. Require distinct
repositories and exclude every Pilot-v1/Pilot-v2, successor/continuation, and
prior live-canary task and repository. Do not use historical arm outcomes,
Pilot-v2's eight admissible observations, task bodies, expected policy benefit,
or desired significance.

**Size and reserve:** Freeze 8 tasks, 8 repositories, two arms, and two paired
repetitions per task-arm (32 cells). This preserves within-task instability and
task-level clustering while remaining exploratory; it is not a power
calculation. Excluding the eight new Pilot repositories removes 37 tasks from
the pre-v3 effective reserve, leaving 462 tasks across 199 repositories under a
new opaque commitment. Emit no remaining reserve IDs or bodies. Post-freeze
task-replacement authority is zero.

**Evaluator and corrective boundary:** Preserve exactly one official terminal
disposition—`success`, `failure`, `error`, `incomplete`, or `empty_patch`—and
keep it separate from feedback availability. An initial failure with named
feedback receives only those names and may use the single corrective round. A
failure without named feedback remains an admissible negative outcome and ends
without correction. `empty_patch` is an experimental negative outcome;
coherent error/incomplete dispositions are attempt-invalid infrastructure;
contradictory or structurally inconsistent measurement stops the batch.

**Attempts, pause, and durability:** Freeze four batch-level infrastructure
reruns, two separately counted operator-interruption restarts, and a two-total-
attempt maximum per cell. Planned pauses occur only between cells and consume
no allowance. Mid-attempt interruption requires contemporaneous cause before
outcome review, immutable retention, fresh isolation, the next attempt number,
and no relabeling or interim-effect-dependent decision. Exhaustion stops and
preserves. Before scheduler transition, fsync the hash-chained attempt start,
subject/evaluator terminal evidence, structured disposition/feedback,
timestamps, usage, isolation, receipt, and admissibility. Restart derives only
from durable evidence and never repeats a completed cell.

**Environment and analysis:** Retain Codex `0.150.1`, `gpt-5.6-terra`, medium
reasoning, the qualified permission/tool surface, `linux/amd64` on the 6-CPU/
16-GiB Docker allocation, evaluator `bc09878a5d192d0804dbd647dc6e650372fcb0ac`,
dataset `62dc0745c40f067fc366ae3eb1a26136e5928f85`, RepoLaunch
`c4b623d930f3728e5338664bb634021b98492cbf`, worker 1, 900-second turn and
1800-second attempt limits, and one corrective round. Pair at task level,
cluster repetitions, resample tasks, separate acceptance from work/cost,
retain null/adverse outcomes, and make no per-language, equivalence,
non-inferiority, broad quality, maintainability, or provider-billing claim.

**Authority:** Pool/contract/schedule freeze, selected-image materialization,
deterministic fixtures/fault injection, tests, documentation, and Git
stabilization are authorized. Provider subject execution, an official
Pilot-v3 evaluator observation, every live cell, and confirmatory execution are
not authorized. The digest confirmation gate is necessary for a future live
entry point but never creates authority.

**Evidence:** `docs/PILOT_V3_FREEZE_AND_QUALIFICATION.md`,
`experiment/pilot_v3_pool.json`, `experiment/pilot_v3_schedule.json`,
`experiment/pilot_v3_execution_contract.json`, and
`experiment/pilot_v3_qualification.json`.

**Status:** **PILOT-V3 FROZEN AND QUALIFIED — LIVE EXECUTION REQUIRES
SEPARATE AUTHORIZATION**.

---

## D-042 — Preserve Pilot-v3's first-cell durable-evidence batch stop

**Decision:** Preserve the authorized Pilot-v3 execution exactly at the frozen
`durable_evidence_incomplete` batch stop. Do not repair the live adapter, rerun
the first cell, consume a retry or operator-interruption unit, execute later
cells, or create a successor/continuation in this goal.

**Observed boundary:** The exact preflight passed. Schedule position 1 completed
one subject process and durably recorded the evaluator-invocation boundary.
Before the official evaluator subprocess launched, the reused adapter read
`timeout_seconds_per_trajectory_attempt`; the frozen Pilot-v3 contract instead
contains `timeout_seconds_per_attempt`. The resulting `KeyError` left no
official disposition, evaluator-finished checkpoint, or receipt. Credential
cleanup completed.

**Durable transition:** The restarted runner derived its next action only from
the hash-chained ledger and appended `batch_stopped` with termination
`durable_evidence_incomplete`. The final ledger contains nine events, SHA-256
`e0a03c6b7ddb6f33ee4d79473dea4536383c750b1b580a23e9c9d5de7b316ea0`.
There is one invalid partial attempt, zero admissible cells, zero reruns, zero
operator interruptions, and 31 unstarted cells. All four infrastructure-rerun
units and both operator-interruption units remain unused but do not authorize
continuation after the batch stop.

**Claims boundary:** Zero admissible cells and zero task-level pairs permit no
frozen Pilot-v3 effect, acceptance, cost/work, uncertainty, per-language,
equivalence, non-inferiority, quality, or maintainability analysis. The subject
usage is preserved only as invalid-attempt operational evidence; billed amount
and currency remain unavailable and are not inferred.

**Evidence:** `docs/PILOT_V3_TERMINAL_REPORT.md` and
`experiment/pilot_v3_terminal_result.json`.

**Status:** **PILOT-V3 EXECUTION STOPPED — DURABLE EVALUATOR EVIDENCE
INCOMPLETE**.

---

## D-043 — Repair the Pilot-v3 timeout boundary and freeze one successor lineage

**Decision:** Repair only the shared evaluator adapter's contract-version-
specific attempt-timeout lookup. Pilot-v3 accepts only
`timeout_seconds_per_attempt`; Pilot-v1/v2 retain their authoritative legacy
field. Missing, mixed, unsupported, invalid, or version-incompatible timeout
shapes fail closed before evaluator subprocess launch.

**Scientific basis:** The predecessor defect was deterministic and
outcome-independent, occurred before any official evaluator process or
disposition, left zero admissible observations, and preceded any interim arm
comparison. One successor lineage is therefore admissible without changing the
original randomization or analysis: preserve position 1 attempt 1 as invalid
partial exposure, restart only as position 1 attempt 2 in fresh isolation,
forbid attempt 3, and retain positions 2–32 as exact attempt-1 cells.

**Accounting and durability:** The successor has a separate genesis ledger
bound to the exact contract, pool, schedule, predecessor ledger and terminal
event, repair identity, and starting position. Completed successor cells cannot
repeat after restart. The original four infrastructure-rerun and two operator-
interruption allowances remain unchanged at zero consumed; successor creation
does not consume, increase, or reset either budget and adds no attempt capacity.

**Evidence:** `docs/PILOT_V3_ADAPTER_SUCCESSOR_QUALIFICATION.md`,
`experiment/pilot_v3_successor_authorization.json`, and
`experiment/pilot_v3_adapter_successor_qualification.json`. Qualification used
only deterministic fixtures/fault injection and executed zero provider subjects,
zero live official evaluators, and zero Pilot cells. Original Pilot-v3 contract,
pool, schedule, terminal-result, and ledger digests remained byte-identical.

**Authority:** The frozen authorization and separate ledger do not authorize
live successor execution. A separately authorized and qualified live interface
is required before position 1 attempt 2 can launch.

**Status:** **ADAPTER REPAIR AND SUCCESSOR QUALIFIED — LIVE EXECUTION REQUIRES
SEPARATE AUTHORIZATION**.

---

## D-044 — Qualify the Pilot-v3 successor execution interface without live calls

**Decision:** Add one successor-specific durable reducer and entry point over
the existing Pilot-v3 runner. Position 1 starts only at attempt 2; position 1
attempt 3 is impossible; positions 2-32 retain their exact order and begin at
attempt 1. Every transition derives from the separate successor hash chain,
and completed cells cannot repeat after restart.

**Preflight and accounting:** Bind the exact predecessor and successor lineage,
current tracked contract, frozen dataset/evaluator/Docker/Codex environment,
qualified task/image identities, and isolated credential bridge before a live
launch. Preserve four infrastructure-rerun units and two separately accounted
operator-interruption units under the shared two-attempt maximum. Unclassified
partial state stops; operator interruption requires a recorded outcome-
independent cause; terminal receipt reconstruction requires durable cleanup.

**Evidence:**
`docs/PILOT_V3_SUCCESSOR_EXECUTION_INTERFACE_QUALIFICATION.md` and the three
`experiment/pilot_v3_successor_execution_*` receipts. Deterministic dry-run,
fault injection, and fixtures used zero provider subjects, zero official live
evaluators, and zero successor cells. Original frozen artifacts and both
lineage ledgers remained unchanged.

**Authority:** The interface confirmation digest is necessary but never grants
user authority. The current user's standing authorization permits live Phase 2
only after GitHub stabilization, green required checks, merged-main parity, and
a fresh strict preflight. Confirmatory execution remains forbidden.

**Status:** **PILOT-V3 SUCCESSOR EXECUTION INTERFACE QUALIFIED — LIVE EXECUTION
REQUIRES SEPARATE AUTHORIZATION**.

---

## D-045 — Terminalize Pilot-v3 at its frozen attempt boundary

**Decision:** Preserve the Pilot-v3 successor as terminal after position 32's
two complete, coherent `local_docker_runtime_infrastructure_failure` receipts
exhausted that cell's two-attempt maximum. Do not launch attempt 3, relabel the
attempts, replace the task, create Pilot-v4, or expose confirmatory material.

**Execution evidence:** The separate successor ledger contains 288 events, 33
attempt starts, 33 committed receipts, one infrastructure-rerun authorization,
and one `attempt_limit_exhausted` batch stop. Positions 1-31 produced admissible
experimental outcomes; position 32 remains missing. All credential-cleanup and
hash-chain boundaries are complete. This is a valid frozen runtime stop rather
than an outcome-independent harness-integrity defect, so the standing repair
and fallback criteria do not apply.

**Exploratory analysis:** Retain all 31 admissible cells in marginal summaries.
For paired inference, use the seven tasks with both frozen repetitions complete
in both arms, average repetitions within task, and resample only those task
clusters. Do not impute the missing baseline cell. The exact task-bootstrap
implementation exhausts all 823,543 ordered seven-task resamples and reports
nearest-rank 95% percentile intervals. These implementation details are
transparent analysis-time specifications, not confirmatory preregistration.

Baseline accepted 6/15 admissible cells and C-short 4/16. Across complete task
clusters, C-short minus baseline acceptance was -14.3 percentage points (95%
interval -50.0 to +14.3). C-short's input-token ratio was 1.223 (1.012-1.448)
and wall-time ratio was 1.326 (1.052-1.575). Cached and fresh input components
remain separate. Provider-billed amount and currency were unavailable and no
monetary cost was inferred.

**Claim boundary:** This small, incomplete Pilot is exploratory-only. It does
not establish equivalence, non-inferiority, quality preservation, broad
efficiency, maintainability, downstream-work effects, or per-language effects.
Confirmatory design or execution requires fresh explicit authority.

**Evidence:** `docs/PILOT_V3_SUCCESSOR_TERMINAL_REPORT.md` and
`experiment/pilot_v3_successor_terminal_result.json`.

**Status:** **PILOT-V3 SUCCESSOR TERMINAL — EXPLORATORY EVIDENCE ONLY**.

---

## D-046 — Retire C-short v0.1 and permit one materially distinct design hypothesis

**Decision:** **MECHANISM IDENTIFIED — ONE NEW CANDIDATE DESIGN PERMITTED.**
Retire byte-exact `C-short v0.1` unchanged. Do not run it confirmatorily, revise
its bytes, or describe Pilot-v3 as equivalence, non-inferiority, preserved
quality, or savings evidence. Permit only one later, separately authorized
candidate-design goal; this decision does not create treatment bytes or permit
implementation, freeze, provider/evaluator use, task exposure, Pilot-v4, or
confirmatory work.

**Reconciliation:** The frozen terminal result regenerates byte for byte from
the validated 288-event successor ledger. Counts, admissibility, missing-slot
handling, arm/repetition assignment, receipt/round usage, calculated fresh
input, wall time, task clustering, marginal and paired denominators, and the
exact `7^7` task bootstrap all match D-045 and the published terminal artifact.
No frozen observation was rewritten, excluded, relabeled, or imputed.

**Disposition evidence:** Across seven complete clusters, C-short minus baseline
acceptance remains -14.3 percentage points with broad exploratory uncertainty;
the interval does not dismiss the adverse point estimate. C-short's paired
input and wall ratios remain 1.223 and 1.326. Leave-one-task-out input ratios
remain 1.112–1.279 and wall ratios 1.185–1.387. Of the aggregate paired input
difference, 96.2% is cached input. C-short used 23 subject turns versus 20, 262
command executions versus 249, and 22 completed web-search items versus 9; it
did not reduce final changed-file counts materially.

**Mechanism boundary:** One public Pilot-v3 task produced replicated
baseline-only acceptance. Both C-short repetitions made the same structurally
narrower change and failed the same one of two fail-to-pass checks while
preserving every pass-to-pass check; both baseline repetitions handled the
adjacent missing state and passed. Together with the exact up-front instruction
to implement only what the requirement states and avoid unrequired
functionality/structure, this supports a concrete post-hoc hypothesis of
literal-minimality interference. The higher search counts support, but do not
establish, a secondary reuse/search-tax hypothesis. One C-short-only pair,
heterogeneous task diagnostics, and concentration in one replicated cluster
remain negative evidence against a universal causal claim.

**Future design constraint:** The only permissible concept is materially
distinct: a single late-stage, evidence-conditioned scope check after ordinary
implementation and relevant verification, targeting optional speculative
structure without suppressing correctness work or creating a reuse/search
obligation. Immediate retirement evidence includes replicated omission of
necessary adjacent behavior, no work reduction among accepted outcomes, or
higher corrective/context/wall work. Exact wording remains unwritten and
unfrozen.

**Historical comparison:** Development-pool results explained why C-short
survived screening but are not pooled. Their authored ceiling tasks, one-turn
protocol, and development-only evaluators are superseded for disposition by
Pilot-v3's fresh external tasks, repetitions, corrections, durable receipts,
and task-clustered analysis. Pilot-v1/v2 remain incomparable infrastructure or
incomplete-measurement history.

**Evidence:**
`docs/C_SHORT_V0_1_DISPOSITION_AND_MECHANISM_ANALYSIS.md` and
`experiment/pilot_v3_c_short_mechanism_diagnostic.json`.

**Status:** **MECHANISM IDENTIFIED — ONE NEW CANDIDATE DESIGN PERMITTED;
C-SHORT V0.1 RETIRED; DESIGN REQUIRES FRESH AUTHORIZATION**.

---

## D-047 — Qualify one evidence-conditioned final scope-review concept

**Decision:** **CANDIDATE CONCEPT QUALIFIED — EXACT BYTES REQUIRE SEPARATE
AUTHORIZATION.** Qualify exactly one conceptual successor: an
**Evidence-Conditioned Final Scope Review** that activates once only after
ordinary implementation is plausibly correct, relevant checks have been run
and inspected where available and feasible, and no relevant failure or
correctness uncertainty remains. This decision qualifies a design concept, not
treatment text, an experimental arm, or execution.

**Evidence boundary:** Pilot-v3 supplies a reconciled adverse/ambiguous
exploratory result and a concrete post-hoc mechanism hypothesis, not causal
evidence. The replicated narrower-change failure supports investigating an
intervention that does not constrain necessary adjacent correctness work. The
higher search and repeated-context observations support avoiding a new search
obligation, but do not attribute individual searches to a clause. Contrary and
null pairs remain negative evidence against a universal mechanism claim.

**Activation and support:** The review is suspended during debugging or any
unresolved relevant failure. It uses evidence already gathered in normal work
and recognizes three support levels: direct requirement/repository/check or
safety evidence; necessary inferred correctness/integration/shared-cause work;
and unsupported optional engineering. Only the third level may be challenged.
Uncertainty resolves toward keeping the working implementation, not toward less
scope.

**Action boundary:** Review only task-introduced additions. Remove or simplify
only clearly separable speculative abstractions, unused extensibility,
unrelated refactors, optional architecture, unsupported defensive complexity,
or duplicated infrastructure with no support in the first two levels. Keep
necessary edge cases, integration fixes, relevant tests, shared-cause changes,
concrete safety/security work, justified dependencies, and risky or entangled
work. Do not act to reduce lines, files, dependencies, tests, tokens, or
response length. A review change requires relevant revalidation.

**No-search and material-distinction boundary:** The concept creates no broad
reuse search, dependency hunt, architecture review, proof of minimality, or
post-solution alternative exploration. Unlike C-short v0.1, it leaves
requirement interpretation, discovery, implementation, debugging, adjacent
correctness, integration, and validation unconstrained until the late
activation boundary. If future wording changes pre-activation behavior, the
concept is not materially distinct and must be rejected.

**Prospective retirement:** Retire on replicated suppression/removal of
necessary correctness work; worse acceptance without a prospectively
admissible countervailing benefit; no evidence-grounded unnecessary-work
reduction among accepted outcomes; increased corrective rounds,
search/repeated-context/wall work; benefits consisting only of smaller
structural/token proxies; changed ordinary discovery or necessary adjacent
work; effective equivalence to C-short's up-front restriction; or a broad or
complex review process. Do not weaken these gates after outcome inspection.

**Alternatives rejected:** A softened up-front minimality concept preserves the
suspected timing mechanism. A late structural threshold rewards proxy
minimization and requires a scoring system. A warn-only review does not test
safe removal behavior. No alternate candidate or future arm is retained.

**Non-authority:** No candidate prompt bytes were written or frozen. No
injection, implementation, provider/Codex subject, evaluator, task exposure,
new pool, Pilot-v4, confirmatory design/execution, model/reasoning change, or
additional arm is authorized. Every such step requires fresh explicit user
authorization in a later goal.

**Evidence:**
`docs/LATE_STAGE_EVIDENCE_CONDITIONED_SCOPE_CHECK_CANDIDATE_DESIGN.md`.

**Status:** **CANDIDATE CONCEPT QUALIFIED; EXACT BYTES UNWRITTEN AND NOT
AUTHORIZED**.

---

## D-048 — Qualify and freeze Evidence-Conditioned Final Scope Review v0.1

**Decision:** **EXACT TREATMENT BYTES QUALIFIED — EXPLORATORY EXPERIMENT DESIGN
REQUIRES SEPARATE AUTHORIZATION.** Freeze exactly one treatment identity,
**Evidence-Conditioned Final Scope Review v0.1**, at
`experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt`. Its 740
UTF-8 bytes use LF only with exactly one terminal LF and have SHA-256
`d9ac9e18716428e9cd6d038388b01ec668ade47df8bac014658897752166b8cb`.
No whitespace normalization is permitted after this freeze.

**Semantic qualification:** The four sentences preserve one lifecycle:
ordinary interpretation, exploration, implementation, debugging, necessary
correctness/integration work, and relevant checks precede the review; plausible
correctness and considered or feasibly run relevant checks activate it; only
task-introduced, clearly separable, unsupported additions may be removed or
simplified while correctness confidence is preserved; relevant failure or
uncertainty resumes ordinary debugging/validation. Requirements, repository
evidence, checks, necessary correctness/integration, safety, and security all
support keeping work. Uncertain, entangled, or risky-to-remove work is kept.
Broad new searching is forbidden, and finding nothing to remove is valid.

**Adversarial audit:** Nine deterministic, task-body-free fixtures protect the
prospective interpretation for adjacent correctness, shared causes, speculative
abstraction, unrelated refactoring, relevant failure, uncertain entanglement,
an already-known repository mechanism, broad-search pressure, and the valid
no-op. None induces up-front narrowing or proof of minimality. These fixtures
freeze the audit judgment; they are not experimental observations.

**Historical boundary:** C-short v0.1 remains retired unchanged under D-046.
D v0.1 remains rejected/excluded under D-017 and D-018. The new identity is not
`C-short v0.2` or a revision of either prior treatment; it belongs to a
materially different late-stage family. No Pilot-v3 observation is relabeled as
evidence for the new identity, and Pilot-v3 remains post-hoc mechanism-
generating exploratory evidence only.

**Prospective retirement:** Bind this exact identity to D-047's gates. Retire it
for replicated suppression/removal of necessary correctness work; adverse
acceptance without a prospectively legitimate countervailing benefit; no
evidence-grounded unnecessary-work reduction among accepted outcomes;
increased corrective rounds, search, repeated/cached context ingestion, or wall
work; apparent benefit only through smaller-looking patches or related proxies;
material pre-activation changes; C-short-equivalent up-front restriction; or a
broad/complex review obligation. No numerical non-inferiority margin or MCID is
created here.

**Non-authority:** This decision freezes treatment bytes and identity only. It
does not make the treatment an experimental arm or freeze a task pool, schedule,
sample size, randomization, benchmark, exploratory/confirmatory design, or
execution contract. It authorizes no provider/Codex subject call, evaluator
call, task-body exposure, Pilot-v4, experiment, model/reasoning change, baseline
change, additional arm, or historical relabeling.

**Evidence:**
`docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_QUALIFICATION.md`,
`experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt`, and
`experiment/evidence_conditioned_final_scope_review_v0_1_semantic_fixtures.json`.

**Status:** **EXACT TREATMENT BYTES QUALIFIED; EXPLORATORY EXPERIMENT DESIGN
REQUIRES FRESH EXPLICIT AUTHORIZATION**.

---

## D-049 — Freeze the task-free exploratory design for the exact late-stage treatment

**Decision:** **EXPLORATORY DESIGN QUALIFIED — TASK SELECTION AND FREEZE REQUIRE
SEPARATE AUTHORIZATION.** Freeze one exploratory methodology comparing baseline
with exact **Evidence-Conditioned Final Scope Review v0.1**. No other arm or
treatment interpretation is admitted.

**Unit and size:** The independent unit is the task/repository cluster. Use
eight repository-distinct tasks, one per language in the pinned source frame,
and two correlated repetitions per task-arm for 32 cells. The second repetition
tests within-task stability, replicated correctness suppression, and mechanism
consistency. This is a bounded exploratory choice, not a power calculation; no
Pilot-v3 effect size or task detail informed it.

**Eligibility and contamination:** A later separately authorized selection goal
may carve an exploratory-only partition from the current post-Pilot-v3 opaque
reserve. Eligibility excludes every task and repository exposed through
development, Pilot-v1/v2/v3, successors/continuations, canaries, and
host-qualification replacements. Selection uses only the frozen source
revision, operational evaluator/container metadata, language, repository, and a
domain-separated SHA-256 rank. Task bodies, expected success, difficulty, patch
size, outcome history, Pilot-v3 semantic similarity, and manual preference are
forbidden. The remaining reserve must be repository-disjoint and recommitted
without emitting IDs or bodies.

**Ordering and execution semantics:** The schedule algorithm operates only on a
future pool commitment and opaque task commitments. Each task is baseline-first
once and treatment-first once; task-repetition blocks are SHA-256 ranked and
cannot be manually or adaptively rearranged. Every cell has at most two total
attempts, with four batch-level infrastructure-retry units and two separately
counted operator-interruption units. Valid negative outcomes are never rerun.
Only named official failure feedback permits the one corrective round.
Contradictory terminal identity or durable evidence stops the batch. Every
attempt uses fresh isolation and hash-chained durable restart state.

**Analysis:** Quality precedes work. The paired acceptance estimate averages
repetitions within complete task clusters; marginal acceptance retains all
admissible intention-to-treat outcomes. Incomplete clusters are not imputed and
receive explicit marginal, missingness, and bound reporting. Task-level
uncertainty exhausts ordered cluster-bootstrap resamples and includes
leave-one-task-out sensitivity and discordance. Work is reported both
unconditionally and, separately, on matched repetitions accepted in both arms.
The latter is conditional descriptive mechanism evidence with a mandatory
selection warning, never a substitute for unconditional quality.

**Retirement and claims:** Retire on replicated necessary-correctness
suppression, an adverse paired acceptance pattern, absence of evidence-grounded
accepted-outcome work reduction, increased corrective/search/cached-context/
wall work, structural-proxy-only benefit, pre-activation effects, C-short-
equivalent narrowing, or broad proof-of-minimality search. These are
prospectively operational directional gates, not significance tests, an MCID,
or a non-inferiority margin. The strongest possible result is bounded
exploratory evidence supporting consideration of another separately authorized
stage; no equivalence, non-inferiority, universal quality, per-language,
maintainability, billing, downstream, or confirmatory claim is permitted.

**Non-authority:** No actual task, eligible/reserve ID, task body, pool, real
schedule, ledger, provider/Codex subject call, official evaluator call, Pilot,
confirmatory design, model/reasoning change, treatment change, or observation
is created or authorized.

**Evidence:**
`docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_EXPLORATORY_DESIGN.md`,
`experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json`,
`src/engineering_scope_guard/exploratory_design.py`, and
`tests/test_exploratory_design.py`.

**Status:** **EXPLORATORY DESIGN QUALIFIED; TASK SELECTION AND FREEZE REQUIRE
FRESH EXPLICIT AUTHORIZATION**.

---

## D-050 — Freeze the exploratory task partition and exact schedule

**Decision:** **EXPLORATORY TASK AND SCHEDULE FREEZE QUALIFIED — EXECUTION
REQUIRES SEPARATE AUTHORIZATION.** The exact selector frozen by D-049 produced
eight tasks from eight repositories with one task in each of `c`, `cpp`, `cs`,
`go`, `java`, `js`, `rust`, and `ts`. The selected repositories are permanently
exploratory-only under this experiment version; post-freeze replacement
authority is zero.

**Prospective derivation:** The pinned source snapshot, source revision,
treatment digest, task-free design digest, and post-Pilot-v3 opaque reserve
commitment matched their authorities. Reconstruction yielded 462 tasks across
199 repositories before selection. The selector used only authorized
operational metadata and the frozen SHA-256 rank. Task bodies, solutions,
patches, difficulty, expected success, semantic similarity, prior outcomes,
and evaluator results were not inspected or used. All eight official registry
manifests were available and digest-bound without pulling or executing images.

**Partition and schedule:** Repository-level removal leaves 434 opaque tasks
across 191 repositories in the confirmatory reserve, bound under a new
domain-separated commitment without publishing remaining identities or
bodies. The schedule contains exactly 16 contiguous two-arm blocks and 32
cells. Every task is baseline-first once and treatment-first once; exact block
order and cell order are commitment-bound. Manual, fallback, adaptive, or
outcome-dependent replacement and reordering are forbidden.

**Non-authority:** The freeze created no execution ledger, subject/provider
call, experimental evaluator call, or experimental observation. It does not
establish efficacy, power, execution readiness, universal lack of bias, or a
confirmatory design. Experimental execution and the next goal require fresh
explicit authorization.

**Evidence:**
`docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_EXPLORATORY_FREEZE.md`,
`experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_freeze.json`,
`src/engineering_scope_guard/exploratory_freeze.py`, and
`tests/test_exploratory_freeze.py`.

---

## D-051 — Stop the exploratory execution before cell 1 on frozen-interface absence

**Decision:** **EXPLORATORY EXECUTION NOT STARTED — STRICT FROZEN PREFLIGHT
FAILED CLOSED.** The exact treatment, pool, schedule, opaque reserve, dataset,
container manifests, evaluator/RepoLaunch revisions, and prior qualified
Docker allocation revalidated without a subject or evaluator call.

**Failure:** No experiment-specific frozen execution contract or qualified
runner/preflight binds this selected pool and schedule to exact model,
reasoning, Codex version, evaluator/runtime, timeout, late-stage delivery,
credential, receipt, and ledger semantics. Creating those semantics after task
freeze would violate the request to use only already-frozen identities. Reuse
of Pilot-v3's executable contract is invalid because it binds another pool,
schedule, and treatment. Independently, installed Codex `0.151.0` differs from
Pilot-v3's frozen `0.150.1` identity.

**Accounting and claims:** Zero ledgers, attempts, credential copies, subject
calls, evaluator calls, observations, or task-body subject exposures occurred.
No exploratory analysis or efficacy/work claim is admissible. The confirmatory
reserve remains opaque and unchanged.

**Evidence:**
`docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_EXECUTION_PREFLIGHT_FAILURE.md`
and
`experiment/evidence_conditioned_final_scope_review_v0_1_execution_preflight.json`.

**Status:** **EXPLORATORY EXECUTION NOT STARTED — STRICT FROZEN PREFLIGHT
FAILED CLOSED**.

---

## D-052 — Qualify the missing late-stage execution interface without live calls

**Decision:** **EXECUTION INTERFACE QUALIFIED — PROCEEDING UNDER EXISTING LIVE
AUTHORIZATION.** Reuse the qualified Pilot-v3 process, isolation, credential,
evaluator, checkpoint, and hash-chain components. Add only an experiment-
specific contract, adapter, and terminal analysis boundary.

**Treatment delivery:** Both arms receive the ordinary task bytes first.
Baseline receives no intervention. After a successful ordinary treatment-arm
turn has a durable session identity, append and fsync one activation checkpoint,
then resume the same session with exactly the frozen 740 treatment bytes. Do not
prepend, normalize, summarize, or otherwise expose the treatment before this
boundary. Prediction and evaluator work follow the activation turn. A subject
failure before activation remains a valid negative with no treatment exposure.

**Runtime and attempts:** Bind Codex `0.151.0`, `gpt-5.6-terra` with `medium`
reasoning, the pinned dataset/evaluator/RepoLaunch/Docker identities, and the
already-repaired Pilot-v3 `timeout_seconds_per_attempt` semantics. Preserve the
two-attempt maximum, exactly four infrastructure-retry units, exactly two
operator-interruption units, one named-feedback corrective round, valid-
negative no-rerun rule, ledger-only restart, credential cleanup, and malformed-
evidence batch stop.

**Analysis:** Freeze executable analysis before outcomes. Preserve quality-
first reporting, marginal and paired intention-to-treat quality, discordance,
unconditional work, jointly accepted paired mechanism evidence with its
conditioning caveat, task-cluster bootstrap, leave-one-task-out sensitivity,
all eleven prospective retirement gates, and bounded exploratory claims.
Evidence-backed semantic annotations are required for positive treatment-
mechanism flags; missing telemetry is not normalized to zero.

**Qualification:** The exact contract regenerated, live-boundary preflight
matched current runtime and all eight selected container manifests, the dry-run
resolved 32/32 cells in order with zero calls and unique isolation, and the
26-check deterministic/fault-injection matrix passed. No execution ledger,
credential copy, subject call, evaluator call, observation, or confirmatory
identity/body exposure occurred.

**Live gate:** Execution may begin only after this qualification is committed,
green in CI/CodeQL, squash-merged, synchronized to clean `main`, and revalidated
by a tracked-HEAD strict preflight plus exact contract-derived confirmation.

**Evidence:**
`docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_EXECUTION_INTERFACE_QUALIFICATION.md`,
`experiment/evidence_conditioned_final_scope_review_v0_1_execution_contract.json`,
`experiment/evidence_conditioned_final_scope_review_v0_1_execution_dry_run.json`,
`experiment/evidence_conditioned_final_scope_review_v0_1_runtime_preflight.json`,
and
`experiment/evidence_conditioned_final_scope_review_v0_1_execution_qualification.json`.

**Status:** **EXECUTION INTERFACE QUALIFIED; LIVE EXECUTION REQUIRES STABILIZED-
MAIN PREFLIGHT**.

---

## D-053 — Retire Evidence-Conditioned Final Scope Review v0.1 at the frozen terminal boundary

**Decision:** **CANDIDATE RETIRED — EXPLORATORY EVIDENCE ONLY.** The tracked-
HEAD strict preflight passed on synchronized clean `main` after the Phase-1
qualification squash merge. The exact authorized schedule then executed until
the frozen state machine reached `batch_stopped` at block 13 baseline.

**Integrity and missingness:** Twenty-six attempts produced 26 complete
receipts: 24 admissible outcomes and two infrastructure-invalid outcomes for
the same cell. The first invalid attempt consumed one batch infrastructure-
rerun unit; the second exhausted the two-attempt same-cell limit. No attempt 3,
replacement, reorder, repair, or restart is permitted. Eight of 32 cells are
missing, five task/repository clusters are complete, and no missing value was
imputed or treated as zero.

**Quality and work:** Marginal acceptance was 5/12 for baseline and 7/12 for
treatment. Across five complete clusters, the paired treatment-minus-baseline
acceptance point difference was +0.1 with a task-bootstrap 95% percentile
interval of 0.0 to 0.3. That descriptive quality direction does not override
the prospectively frozen mechanism and harm gates. Unconditional treatment
work increased for input tokens, cached input, output, wall time, subject
turns, commands, local read/search, and completed web searches at the point
estimate; fresh input, reasoning output, and corrective rounds decreased.

**Mechanism and retirement:** Four jointly accepted repetitions across two
task clusters showed no evidence-backed optional removal/simplification cell
and no trajectory field with mean reduction. Five frozen gates fired:
`no_accepted_outcome_mechanism`, `search_increase`,
`cached_context_increase`, `wall_or_work_increase`, and
`structural_proxy_only`. All other gates, including necessary-correctness
suppression and adverse acceptance, remained false. Under the predeclared any-
gate rule, the exact candidate is retired unchanged.

**Claims and authority:** The result is exploratory and derives from a terminal
partial schedule. It supports no confirmatory, superiority, equivalence, non-
inferiority, universal quality, per-language, maintainability, downstream-work,
billing, or monetary-savings claim. It authorizes no treatment change, another
exploratory run, or confirmatory work.

**Evidence:**
`docs/EVIDENCE_CONDITIONED_FINAL_SCOPE_REVIEW_V0_1_TERMINAL_ANALYSIS.md`,
`experiment/evidence_conditioned_final_scope_review_v0_1_terminal_result.json`,
`experiment/evidence_conditioned_final_scope_review_v0_1_terminal_analysis.json`,
and
`experiment/evidence_conditioned_final_scope_review_v0_1_mechanism_annotations.json`.

**Status:** **CANDIDATE RETIRED; EXECUTION TERMINAL; NO NEXT EXPERIMENT
AUTHORIZED**.

---

## D-054 — Reframe the project as an evidence-first research program

**Decision:** **RESEARCH PROGRAM REFRAMED — NEXT CAPABILITY EXPERIMENT REQUIRES
SEPARATE AUTHORIZATION.** Retain the research repository, evidence registry,
historical experiment/evaluation infrastructure, and existing local V0 Shadow
Scope Analyzer. Treat a local read-only workflow auditor only as a conditional
future candidate. Reject an active optimizer under current evidence.

**Rationale:** Two materially different direct scope interventions failed their
advancement criteria. C-short v0.1 had an adverse quality signal and no work-
reduction signal. Evidence-Conditioned Final Scope Review v0.1 avoided its
adverse-acceptance retirement gate but established no accepted-outcome
unnecessary-work reduction; five frozen mechanism/work gates fired. External
evidence also shows material heterogeneity and contradictions across context,
tools, models, agent coordination, expertise, risk, and task type. Native
products and existing OSS/evaluation systems already cover many candidate
capabilities.

**Boundaries:** Lower raw token use is not the objective. No third scope prompt,
confirmatory scope-policy experiment, read-only auditor implementation,
suggestion layer, automatic routing, or active optimizer is authorized. Future
research must measure work per correct/accepted outcome, disclose
contradictions and expiry, compare native/no-change substitutes, and pass the
ordered falsification gates in `docs/RESEARCH_ROADMAP.md` under a separate goal.

**Evidence:** `docs/CODING_AGENT_EVIDENCE_REVIEW.md`,
`docs/EVIDENCE_REGISTRY.md`, `docs/COMMUNITY_PAIN_EVIDENCE.md`,
`docs/COMPETITOR_AND_SUBSTITUTE_MAP.md`, and
`docs/PROJECT_THESIS_REASSESSMENT.md`.

**Status:** **RESEARCH PROGRAM REFRAMED; RESEARCH-ONLY PLUS EXISTING SHADOW
MEASUREMENT; NO NEXT CAPABILITY EXPERIMENT AUTHORIZED**.

---

## D-055 — Stop after the Shadow Observability Gap Audit

**Decision:** **NO MATERIAL OBSERVABILITY GAP — RETAIN RESEARCH-ONLY.** The
existing V0 reliably produces privacy-bounded structural deltas and explicit
observer-health diagnostics, but it does not expose an important underlying
coding-workflow fact unavailable through the simplest native or existing-tool
route.

**Evidence:** Git/VCS, manifest inspection, tests/CI, and native Codex JSONL
already expose the underlying reliable structural and verification facts. The
current Codex App Server, Claude hooks/telemetry, Gemini OpenTelemetry, Copilot
SDK events, Cursor hooks, and Promptfoo tracing expose richer workflow-event
surfaces than current V0. V0 does not reliably expose same-file rereads,
repeated search queries or result fingerprints, correction/state-recovery work,
tool-selection quality, configured-but-unused tools, or accepted/correct
outcomes. The small fixture showed low machine overhead and zero target
mutation, so burden alone is not the terminal reason.

Financial, professional, commercial, sponsorship, or platform incentives must not alter research conclusions, evidence classification, publication decisions, or corrections.

**Boundaries:** This result does not claim native observability is complete,
that workflow-health questions are unimportant, or that structural facts lack
research value. It means existing V0 does not pass Track 1's incremental-gap
gate. No Track 2 measurement-validity experiment, new live canary, provider or
evaluator execution, recommendation layer, storage redesign, or end-user
capability is authorized.

**Evidence:** `docs/SHADOW_OBSERVABILITY_GAP_AUDIT.md`,
`docs/evidence/shadow-observability-matrix-2026-08-29.json`,
`docs/CODEX_CAPABILITIES.md`, `docs/COMPETITOR_AND_SUBSTITUTE_MAP.md`, and
`docs/EVIDENCE_REGISTRY.md`.

**Status:** **TRACK 1 TERMINAL; RESEARCH-ONLY; NO NEXT EXPERIMENT OR CAPABILITY
AUTHORIZED**.

---

## D-056 — Stop after next-research-hypothesis prioritization

**Decision:** **NO NEW LIVE EXPERIMENT JUSTIFIED — MAINTAIN/PUBLISH EXISTING
EVIDENCE.** Treat stopping as the selected research action. No candidate
currently passes importance, uncertainty, falsifiability, outcome quality,
observability, isolation, reproducibility, cost/power, half-life, novelty, risk,
and null-publication-value gates together.

**Evidence:** Compaction/checkpoints has the strongest independent causal gap
but cannot presently be induced and observed cleanly without artificial context
pressure or opaque runtime state. Persistent instruction delivery has
contradictory evidence and credible execution outcomes, but the literature is
now crowded and model/harness-expiring. Reasoning effort is natively controlled
and observable, but current test-time-compute evidence and vendor guidance make
a small fixed-effort comparison insufficiently novel; a useful interaction
study would require unjustified task variation and repetition. Tool exposure,
compression, planning, subagents, clarification, verification/trust, and build-
versus-not-build each fail a harder novelty, isolation, evaluation, cost, or
human-subject gate.

**Publication timing:** The preserved C-short adverse result, final-scope-review
retirement, thesis reassessment, Track 1 no-gap result, evidence registry, and
methodology are mature enough for a separately authorized publication-planning
goal centered on one source-linked report or minimal research archive. This
decision does not create or authorize an external distribution action.

**Boundaries:** No task or treatment identities were selected or frozen. No
held-out task body was inspected. No provider/evaluator call, live canary,
execution code, feature, V0 expansion, Track 2 work, or external publication is
authorized. Revisit only after a material evidence, runtime-isolation, public-
task, or affordability change under a new explicit goal.

**Evidence:** `docs/NEXT_RESEARCH_HYPOTHESIS_PRIORITIZATION.md`,
`docs/EVIDENCE_REGISTRY.md`, `docs/CODING_AGENT_EVIDENCE_REVIEW.md`, and
`docs/RESEARCH_ROADMAP.md`.

**Status:** **TERMINAL; RESEARCH-ONLY; NO LIVE EXPERIMENT AUTHORIZED**.

---

## D-057 — Select one focused C-short report as the first public research package

**Decision:** **FIRST PUBLIC RESEARCH PACKAGE JUSTIFIED — EXTERNAL PUBLICATION
REQUIRES SEPARATE AUTHORIZATION.** Specify `ESG-RR-001`, a focused, neutral,
versioned report on the C-short v0.1 exploratory program. Use GitHub as the
first canonical archive. Do not create a release or external
publication/distribution action under this goal.

**Selection rationale:** C-short has the clearest first-artifact boundary: a
single exact treatment, public task identities, seven complete paired task
clusters, two repetitions per arm, a body-safe cell-level diagnostic,
deterministic analysis code, explicit uncertainty, retained null/contrary
cases, and a bounded retirement decision. A two-intervention report would make
the later terminal partial schedule appear co-primary despite eight missing
cells, opaque task commitments, owner-local raw evidence, and no positive
accepted-outcome mechanism. A program synthesis would mix empirical results,
research interpretation, and strategy before canonical component reports
exist. An evidence-review-first artifact would be less distinctive and more
maintenance-heavy.

**Claim boundary:** The exact publishable empirical statement is scoped to
Codex CLI 0.150.1, `gpt-5.6-terra`/medium, seven complete public
SWE-bench-Live/MultiLang task clusters, 28 paired cells, and the 2026-08-29
evaluation. C-short minus baseline acceptance was -14.3 percentage points
(exact task-bootstrap 95% percentile interval -50.0 to +14.3); paired input and
wall ratios were 1.223 (1.012-1.448) and 1.326 (1.052-1.575). This is
exploratory and does not establish causality, equivalence, non-inferiority,
quality preservation, billing, maintainability, downstream work, or a general
effect of minimality prompts.

**Reproducibility and privacy:** Public readers can audit the core paired result
from exact treatment bytes, pool, schedule, contract, terminal result,
body-safe cell-level diagnostic, analysis code, and tests. The owner-local
hash-chained ledger, raw prompts/traces/commands/output, patches, task bodies,
execution roots, credentials, billing metadata, and held-out reserve remain
controlled. Cryptographic bindings prove identity, not public access to hidden
content. Upstream dataset/evaluator and underlying repository license/link
treatment must be revalidated immediately before any external publication.

**Architecture and identity:** GitHub-only is sufficient for the first package.
A secondary archive is deferred until repeated reports or reader-access
evidence justifies duplication. Retain `Engineering Scope Guard` as a visibly
research-only working name and preserve the intentionally public author and
maintainer identity.

**Evidence:** `docs/PUBLIC_RESEARCH_PUBLICATION_PLAN.md`,
`docs/FIRST_PUBLIC_RESEARCH_PACKAGE_SPEC.md`,
`docs/PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json`, and
`docs/PUBLICATION_AND_EDITORIAL_POLICY.md`.

**Status:** **TERMINAL PUBLICATION-PLANNING DECISION; NO EXTERNAL PUBLICATION
AUTHORIZED**.

---

## D-058 — Publish ESG-RR-001 v0.1 as the canonical GitHub research release

**Decision:** **ESG-RR-001 PUBLISHED — DISTRIBUTION CHANNELS REQUIRE SEPARATE
AUTHORIZATION.** Publish only the focused C-short v0.1 research package through
the existing GitHub repository after every local Pre-Push gate passes, then
require hosted CI and CodeQL before merge, tag, or Release.

**Pre-Push evidence:** The full report and claim-ledger parity were complete;
all material quantities independently recomputed; clean-checkout Level 1 and
Level 2 passed; owner-only Level 3 regenerated the terminal result and body-safe
diagnostic byte-for-byte from the controlled ledger; source revisions,
license/link handling, privacy, staged Gitleaks, author/conflict/correction/
citation metadata, overclaim language, internal links, JSON, 250 tests,
warning-clean compilation, local static checks, and publication-only diff scope
all passed before the first public push.

**Publication evidence:** PR
[#38](https://github.com/cagdasyurekli/engineering-scope-guard/pull/38)
passed Python 3.11/3.14 CI and both CodeQL analyses and squash-merged as
`53c1de0e537332e06f1b3c9a53ab6b110815a54b`. Annotated tag
`esg-rr-001-v0.1` resolves to that commit. The canonical GitHub Release is
[`esg-rr-001-v0.1`](https://github.com/cagdasyurekli/engineering-scope-guard/releases/tag/esg-rr-001-v0.1),
published 2026-08-30 with no controlled assets. The claim-ledger SHA-256 is
`9fc57757c8fd5bac337eff30961196e5e14c5300237a296c7c5a4cf0815be847`;
the correction status is initial version with no corrections.

**Boundary:** The report is exploratory and does not reopen C-short, the later
final-scope-review treatment, the research roadmap, V0 product scope, or any
provider/evaluator execution. No external distribution action is authorized.

**Status:** **TERMINAL; ESG-RR-001 V0.1 PUBLISHED; DISTRIBUTION AND NEW RESEARCH
NOT AUTHORIZED**.

---

## D-059 — Correct ESG-RR-001 provenance and publish immutable v0.2

**Decision:** **ESG-RR-001 v0.2 CORRECTION PUBLISHED AND IMMUTABILITY VERIFIED
— DISTRIBUTION REQUIRES SEPARATE AUTHORIZATION.** Correct the false v0.1
release-provenance terminology visibly, preserve the historical v0.1 tag and
Release, and publish corrected report version 0.2 only after repository
immutable releases are enabled and verified.

**Correction evidence:** V0.1 is annotated tag object
`53c9824a773c5be5db4f7d8269cd7fba94c06665`, targeting report commit
`53c1de0e537332e06f1b3c9a53ab6b110815a54b`; its GitHub Release reported
`immutable: false`. The claim ledger contains no incorrect immutability
statement and remained byte-identical with SHA-256
`9fc57757c8fd5bac337eff30961196e5e14c5300237a296c7c5a4cf0815be847`.
Treatment, evidence, result tables, seven claim IDs, analysis, interpretation,
and conclusion remained unchanged. Scientific impact: none. Conclusion impact:
none.

**Verification and publication:** Level 1/2 and owner-only Level 3 passed;
250 tests, warning-clean compilation, JSON/schema/link checks, privacy, staged
Gitleaks, and bounded diff passed. PR
[#40](https://github.com/cagdasyurekli/engineering-scope-guard/pull/40)
passed Python 3.11/3.14 and both CodeQL analyses and squash-merged as
`b60c0458cdde2369dc1658293c974f25805e04e0`. Repository immutable releases
were enabled and read back as `enabled: true`. Annotated tag object
`8878da6e12fe7d6fdddb397bfdde0433ee1a905a` targets the correction commit.
GitHub Release
[`esg-rr-001-v0.2`](https://github.com/cagdasyurekli/engineering-scope-guard/releases/tag/esg-rr-001-v0.2)
reported `immutable: true`; `gh release verify` attestation verification and
tag-target parity passed. V0.1 remains historical and mutable.

**Boundary:** Do not reopen research selection, C-short, the later treatment,
V0 product work, or any provider/evaluator execution. No external distribution
action is authorized.

**Status:** **TERMINAL; V0.2 CORRECTION PUBLISHED AND IMMUTABILITY VERIFIED;
DISTRIBUTION AND NEW RESEARCH NOT AUTHORIZED**.

---

## D-060 — Keep GitHub as the canonical research record

External publication and distribution channels are outside the scientific record and require separate project decisions.
## D-061 — Maintain a public/private repository boundary

Repository history and the current tree must contain reproducible evidence and sanitized project decisions only. Scientific evidence and conclusions are unchanged.

---

## D-062 — Privacy-sanitize repository history and republish ESG-RR-001 v0.3

**Decision:** Repository history was privacy-sanitized. Scientific research
evidence and conclusions were unchanged. ESG-RR-001 v0.3 republishes the same
scientific report under a new release identity.

**Boundary:** No new experiment, provider/evaluator call, scientific result
change, or external distribution work is authorized by this decision.

---

## D-063 — Reconstruct the canonical repository under an independent identity

**Decision:** Build the canonical repository from a freshly verified,
privacy-sanitized snapshot with minimal new Git history. Keep the sanitized
predecessor repository private under a neutral name and do not copy its pull
request history into the canonical repository.

**Reason:** An independent repository identity removes inherited GitHub-owned
pull-request references from the canonical public namespace while preserving
the complete scientific and reproducibility record in the clean snapshot.

**Boundary:** ESG-RR-001 evidence, treatment identity, numerical results,
analysis, claims, and conclusions remain unchanged. This decision authorizes
no new experiment or distribution work.

---

## D-064 — Use ESG-RR-001 v0.4 for the independent repository release

**Decision:** Publish the unchanged ESG-RR-001 result as version 0.4 under tag
`esg-rr-001-v0.4` in the independent repository.

**Reason:** The predecessor already used the v0.3 publication identity. A new
version gives the independent repository an unambiguous release identity while
retaining the complete scientific and correction record.

**Boundary:** This is a publication/provenance update only. The claim ledger,
treatment, evidence, numerical results, analysis, claims, and conclusions do
not change.

---

## D-065 — Correct canonical Git author metadata and keep reopening fail-closed

**Decision:** Replace personal/non-noreply author and committer metadata in the
owner-controlled canonical history with the verified GitHub noreply identity,
retire the v0.4 Release and tag, and republish the unchanged report as
ESG-RR-001 v0.5.

**Reason:** Git identity metadata is public repository data even when file
contents are clean. The correction must remove that metadata without changing
the scientific trees or preserving affected commit identities.

**Public-visibility gate:** Keep the canonical repository private when a
GitHub-owned pull-request ref or ordinary old-object endpoint retains affected
ancestry. Do not contact GitHub Support or recreate the repository under this
goal.

**Boundary:** This is a Git-history privacy and publication-provenance
correction only. Treatment bytes, claim ledger, terminal result, task
population, missingness, numerical results, mechanism interpretation,
analysis, claims, and conclusions remain unchanged. No experiment or
provider/evaluator call is permitted.

---

## D-066 — Requalify one current-runtime exploratory experiment

**Decision:** Reopen candidate selection under the current Codex runtime and
current public task infrastructure. Compaction/checkpoints, persistent
repository instructions, reasoning effort, and any stronger primary-source
candidate must pass the same prospectively stated hard gates before execution.

**Execution boundary:** At most one new exploratory experiment may run. Freeze
all treatment, runtime, task, allocation, evaluator, retry, missingness,
analysis, and stop rules before meaningful outcome exposure. The absolute limit
is 64 new subject attempts, with no third attempt for a frozen cell. If no
candidate passes, spend the goal only on outcome-independent qualification or
harness work and record `NO LIVE EXPERIMENT JUSTIFIED`.

**Scientific boundary:** Accepted/correct outcome is primary. Work and token
metrics are secondary and cannot establish preserved quality, billing savings,
or unnecessary-work percentages. Use task or repository cluster as the
independent unit and retain null, adverse, heterogeneous, and contradictory
evidence.

**Privacy/publication boundary:** Keep the canonical and predecessor
repositories private. Raw traces, task bodies, reserve identities, temporary
receipts, and private selection notes remain ignored local evidence. Do not
publish a Release, change visibility, contact Support, recreate a repository,
or distribute results externally.

**Status:** **TERMINAL — NO LIVE EXPERIMENT JUSTIFIED.** The prospective gold
gate stopped before contract freeze or cell 1; see D-067.

---

## D-067 — Current-runtime requalification stops at the gold gate

**Decision:** Record `NO LIVE EXPERIMENT JUSTIFIED`. Do not freeze or execute
Reasoning Effort v1, do not substitute another language or task-selection rule,
and do not start a second candidate experiment.

**Evidence:** The one-worker current evaluator completed 15 pre-subject gold
attempts. Six languages produced the required two-of-two official-gold
successes (12 successes total). In the next language, the initial candidate
and first deterministic replacement each produced an official-gold test
failure on repetition 1; the second and final permitted replacement produced
an evaluator runtime failure on repetition 1. The prospectively frozen maximum
of two replacements was therefore exhausted. The eighth language was not run.
No experimental subject cell, task outcome, acceptance comparison, or treatment
contrast was exposed. One earlier content-free runtime canary remains the only
new model invocation in this sprint.

**Interpretation:** This is an infrastructure/design block, not evidence for or
against low versus medium reasoning effort. It establishes no causal effect,
quality preservation, equivalence, non-inferiority, billing saving,
unnecessary-work percentage, or per-language result.

**Harness increment:** Before the stop, the prospective runner gained an
outcome-blind Stage 1 continuation gate. At exactly four completed prefix
cells, continuation would have required two final cells per arm, frozen command
receipts, returned subject invocations, complete provider usage and subject-work
receipts, zero prohibited-tool evidence, complete official-evaluator receipts,
durable receipt binding, and no batch stop. A failure would have emitted a
hash-bound terminal `stage_1_failed` event. This provider/evaluator-free harness
work removes a future integrity ambiguity but does not authorize execution.

**Evidence:** `experiment/current_runtime_requalification_terminal.json`,
`docs/CURRENT_RUNTIME_REQUALIFICATION.md`.

**Status:** **TERMINAL.** A confirmatory run, a second exploratory experiment,
or a redesigned task/evaluator population requires separate authorization.

---

## D-068 — Fail closed on experimental disk pressure without automatic cleanup

**Decision:** Add a standard-library, host-filesystem disk gate to the
unfrozen Reasoning Effort v1 prospective runner. Before execution it requires
128 GiB available (a 64 GiB minimum reserve plus 64 GiB next-attempt headroom)
and at most 64 GiB of retained attempt-repository allocated blocks. Equality
passes. The runner rechecks under its lock before `attempt_started`; an
ambiguous or failed measurement stops without consuming an attempt or creating
an experimental outcome.

The symmetric 64 GiB reserve, next-attempt headroom, and retained-data ceiling
are conservative project safeguards chosen from the incident's observed order
of magnitude before any future execution. They are operational stop limits,
not universal storage recommendations or experimental outcome thresholds.

**Measurement boundary:** Scan only exact sibling
`<run>/attempts/<cell>/<attempt>/repository` directories on the configured
state-root filesystem. Use no-follow `lstat`, deduplicate hardlinks by device
and inode, and report `st_blocks * 512`. This is filesystem-reported allocation,
not logical size, uniquely reclaimable APFS space, Docker virtual-disk
capacity, or causal attribution to Docker.

**Cleanup boundary:** The companion analysis is pure and the CLI is
non-destructive: it writes only a controlled ignored plan artifact. Its
detailed target inventory, counts, sizes, and digest remain private local
evidence; stdout only confirms the write. Every entry is unclassified and the
plan explicitly denies deletion authorization. Its path-set digest is not an
inode or content identity and cannot be reused as approval. No automatic
repository deletion, Docker prune, Docker image deletion, background monitor,
or historical-artifact rewrite is permitted.

**Scope:** Historical and frozen runners remain byte-unchanged. The current
prospective runner was never frozen or executed under D-067, so binding this
safeguard into its execution-code identity does not alter experimental
evidence. No provider, evaluator, benchmark, or live experiment execution is
authorized by this decision.

---

## D-069 — Separate evaluator qualification from post-freeze replacement

**Decision:** Prospectively qualify a stable external task/evaluator population
before freezing or exposing any Reasoning Effort experimental cell. A candidate
that fails objective pre-outcome infrastructure or evaluator checks is
`not_qualified`; it is not an experimental replacement and consumes no subject
attempt. The historical D-067 terminal state remains unchanged and is not
reinterpreted as a result about `low` versus `medium` reasoning effort.

**Source and ordering:** Reuse the outcome-blind 48-task, repository-distinct
reserve at dataset revision
`62dc0745c40f067fc366ae3eb1a26136e5928f85`, evaluator revision
`7c5ee6c11595bb0290832eb9e5b7aa81ead1cfc0`, and embedded RepoLaunch revision
`c4b623d930f3728e5338664bb634021b98492cbf`. Recompute every stored rank from
the prior seed and dataset revision, then traverse the six frozen ranks in
language round-robin order. Do not inspect task bodies, topic, perceived
difficulty, expected Codex success, or desired treatment direction.

**Qualification:** For each candidate, require: (Q1) immutable registry/local
image identity and environment availability; (Q2) the pinned upstream
`evaluation.validation` path, including its three post-patch runs and stability
filter; (Q3) official gold-patch acceptance; and (Q4) a second separate official
gold invocation using upstream fresh-runtime semantics. Target 16 qualified
repository clusters so 12 primaries and four alternates can be frozen. Ten
independent clusters is the hard minimum. Exhaust the deterministic reserve if
needed; if fewer than ten qualify, start no subject cells.

**Integrity controls:** Raw tasks, patches, logs, container identities, and
receipts remain below ignored `.local/` with restrictive permissions. Every
stage revalidates clean pinned evaluator/RepoLaunch trees, dataset bytes,
evaluator interpreter/package identity, and the complete repository-owned
qualification code closure. Candidate ordering and mutable state are sealed;
all completed-stage artifacts are rehashed before reuse; one exclusive lock
guards state; image tags and pulled images must resolve to the same immutable
manifest; and interrupted stages reconcile without rerun. Because the pinned
upstream evaluator provides no ownership label, a newly observed matching
container blocks reconciliation and is never deleted automatically.

**Preliminary-lineage disposition:** The first implementation completed one
candidate and began a second candidate before independent review found missing
source/artifact revalidation and path/integrity controls. It was stopped with
zero subject invocations. Its private receipt and raw evidence remain preserved
as `qualification-v1-preliminary-invalid`; no candidate is grandfathered into
v2 and no preliminary count is scientific evidence.

**Experiment boundary:** Qualification itself permits zero Codex subject
invocations. If v2 reaches the minimum, the existing fixed eight-task/32-cell/
64-execution Reasoning Effort v1 machinery must be redesigned and provider-free
qualified for the selected 10–12 primary clusters, 40–48 cells, at most 56
subject invocation starts, prequalified alternates, dynamic cluster analysis,
and the newly authorized replacement/Stage 1 rules before contract freeze or
cell 1. Do not reuse the old D-066 authorization artifact as execution authority.

**Privacy/publication boundary:** Keep the repository private. Do not publish a
Release, change visibility, contact GitHub Support, recreate a repository,
expose private task identities, or begin distribution.

**Terminal disposition:** Qualifier v2 passed its continuation gate after 20
candidates, with 16 independent qualified clusters, one flaky-validation
failure, three infrastructure timeouts, and zero subject starts. The exact
pre-contract freeze subsequently observed a model-catalog identity different
from the qualification runtime. The qualified catalog bytes were unavailable,
so the prospective exact-identity requirement could not be satisfied without a
post-hoc runtime substitution or protocol change.

The experiment therefore terminalized at the authorized scientific-integrity
stop condition as `EXPERIMENT INVALID / TERMINATED`. No final experimental
population, schedule, contract, canary, subject cell, evaluator invocation,
analysis, or LOW-versus-MEDIUM outcome exists. The qualification result remains
valid infrastructure evidence but is not experimental evidence. The private
write-once integrity-stop receipt and the public-safe terminal package preserve
this distinction. No retry, second experiment, publication, push, pull request,
merge, release, or repository visibility change is authorized.

**Status:** terminal; exactly one next boundary remains:
`authorize_private_canonical_branch_push`.

---

## D-070 — Make the terminal handoff portable to one clean root commit

**Decision:** The clean independent canonical repository begins with exactly
one root commit and carries no object from the private archival histories. Its
terminal handoff therefore sets both commit fields to `null` with explicit
`omitted_to_avoid_self_reference` semantics. The containing root identity is
derived from Git; repository-relative evidence paths and SHA-256 digests bind
the public-safe terminal evidence bytes.

**Reason:** A commit cannot contain its own SHA, and retaining the prior private
evidence commit would copy historical objects into the new repository. Neither
creating a second metadata commit nor weakening evidence verification is
required. The authoritative form retains its strict 40-hex commit shape and
private archival verification already resolved it against the exact evidence;
the single-root public form verifies the exact current evidence bytes.

**Remote-check boundary:** The initial repository is created directly on
`main`, without a bootstrap pull request. CI and CodeQL therefore use
`derive_from_branch`; their live status must be read from the current protected
base-branch commit. This state does not claim that either check has passed.

**Scientific boundary:** This is a provenance/publication portability change.
It does not alter D-069, qualification counts, terminal classification,
experimental outcomes, task selection, treatment, or the zero subject/evaluator
invocation accounting. No new live research is authorized.

---

## D-071 — Publish the unchanged ESG-RR-001 record as version 0.6

**Decision:** Use report version `0.6` and annotated tag
`esg-rr-001-v0.6` for the clean-canonical-identity republication. Versions and
tag names `0.1` through `0.5` remain retired and are not recreated in the new
repository. The corresponding GitHub Release may be created only after the new
repository passes its private clean-root gates, public CI and CodeQL, active
ruleset, anonymous privacy verification, and final release audit; the Release
must then report immutable state.

**Reason:** The previous private work already reached version `0.5`, so `0.6`
is the next monotonically increasing identity. The republication note is
limited to the clean canonical repository identity and repository-history
privacy sanitation.

**Scientific boundary:** The claim ledger, treatment, contracts, terminal
result, body-safe diagnostic, numerical analysis, claims, and conclusions are
unchanged. ESG-RR-002 is not created because D-069 terminalized before contract
freeze with zero subject and evaluator invocations.

---

## D-072 — Publish a derived public-safe Pilot host receipt

**Decision:** Replace the public snapshot's raw Pilot host qualification receipt
with a deterministic projection at the same path. Retain task/repository
identity, replacement lineage, run repetition, outcome, classification,
timing/resource fields, official image identity, SHA-256 run receipts, aggregate
distributions, reserve commitments, and the bounded conclusion. Remove raw
evaluator reports/results, invocation commands, container states, raw output
locations, and host-local references. Record the projection boundary in the
receipt and verify it idempotently.

Refresh only the two tracked content-address pointers that name this receipt
and the documentation hash of the affected preparation-only qualification.
The private archival histories preserve the predecessor bytes; they are not
copied into the clean canonical repository.

**Reason:** The raw receipt contained host-local and raw evaluator material that
is unnecessary for public Level 1/2 reproduction and violates the clean-root
privacy boundary. The public projection remains sufficient for the existing
deterministic host audit and historical pool/contract reconstruction.

**Scientific boundary:** All 48 recorded run outcomes and classifications, 12
host-valid tasks, replacement accounting, frozen identities, resource facts,
terminal decisions, and all ESG-RR-001 scientific identities remain unchanged.
This is privacy sanitation of non-outcome raw material, not a reinterpretation
or scientific correction.

---

## D-073 — Prospectively lock runtime and campaign time for one new reasoning-effort experiment

**Decision:** Authorize one new exploratory LOW-versus-MEDIUM experiment only
after all readiness gates in `docs/CURRENT_GOAL.md` pass. The preferred design
is ten independent task/repository clusters, two arms, and two repetitions (40
cells), with four prequalified alternates and an absolute 48-subject-attempt
ceiling. Sample size, schedule, treatment, retry rules, outcome, analysis,
missingness, falsification, and stop rules must be frozen before cell 1.

**Prior-pool reuse:** The D-069 16-cluster qualification may be reused because
no subject model attempted any candidate and selection was prospectively
outcome-blind, but only after the sealed private receipt, all completed-stage
artifact hashes, evaluator/task-source revisions, repository independence, and
zero-subject accounting are revalidated. Reuse is infrastructure evidence, not
an experimental result.

**Runtime boundary:** Every subject cell must use one experiment-local,
read-only Codex executable bundle and one frozen observable model catalog. A
machine-readable receipt binds the executable/package digest, version, model,
native efforts, explicit config/tool surface, relevant environment, and
sandbox. A sentinel runs before each cell. Any observable drift stops before
launch as `RUNTIME IDENTITY DRIFT — EXPERIMENT INTERRUPTED`; provider-side
changes not exposed by the product remain an explicit limitation.

**Campaign-clock boundary:** Azure task timestamps and retry counters remain
diagnostic only. The hard campaign duration is derived exclusively from
persisted completed monotonic-segment elapsed time plus the current process's
`time.monotonic_ns()` segment. Restart creates a new segment and resumes from
the last durable elapsed checkpoint; it never compares process-local monotonic
origins or resets time after requeue.

**Claims and publication:** Acceptance is primary. Repetitions are not
independent tasks. Work is interpreted relative to accepted outcomes and must
retain failures. ESG-RR-002 is optional and requires adequate admissible data,
valid evaluation, protocol integrity, useful uncertainty, and a meaningful
contribution. GitHub-native publication is authorized only for such a package;
all external/social distribution remains unauthorized.

**Status:** Active prospective decision. No subject attempt has started.

---

## D-074 — Terminate the runtime-locked experiment before freeze

**Decision:** Abandon this authorized program at its pre-contract runtime-
stability gate. The maximum two contentless process launches were consumed;
both exited locally with code 2 before JSONL, provider, or tool events because
the frozen invocation combined mutually exclusive `--approve-for-me` and
`--sandbox` options. Do not reclassify either launch as model-performance
evidence, do not run a third launch, and do not start a subject or evaluator.

**Reason:** The option conflict is mechanically understood, but the prospective
protocol imposed an absolute two-launch soak maximum. Repairing the invocation
and launching again would exceed that frozen allowance. The readiness gate is
therefore unsatisfied even though the binary and catalog sentinels themselves
remained stable.

**Scientific boundary:** LOW versus MEDIUM remains unanswered. There are zero
frozen cells, zero subject starts, zero evaluator starts, and no acceptance or
work contrast. ESG-RR-002 is not justified and no research Release is created.

**Infrastructure boundary:** Preserve the campaign-clock correction and its
deterministic tests. The synthetic Azure validation is infrastructure evidence
only. Its task-runtime cost is an estimate, not a billing claim, and terminal
state requires a fresh zero-compute readback. Correct the reusable public
command helper by removing the redundant explicit sandbox option and cover the
conflict with a regression test, but do not execute the repaired command under
this program.

**Authorization boundary:** The current authorization permits public-safe
terminal persistence and merge, but not any third stability launch, retry,
successor experiment, or external distribution. Any such work requires a new
explicit program authorization.

---

## D-075 — Authorize a launch-surface-locked successor without changing the question

**Decision:** Treat the user-authorized Launch-Surface-Locked Reasoning-Effort
Experiment as a separate prospective program. Reuse the D-069 qualified,
outcome-blind population only after its sealed provenance is revalidated. Keep
the D-073 research question, primary external acceptance outcome, two native
LOW/MEDIUM arms, two repetitions, cluster-level interpretation, balanced
schedule, retry classifications, analysis ordering, and claims restrictions.
Select the first ten eligible independent clusters as primaries and the next
four as alternates. Freeze 40 mandatory cells and an absolute maximum of 48 new
coding-task subject attempts.

**Launch-surface repair:** Replace the predecessor's opaque command assembly
with self-hashed structured argv profiles. The exact D-074 conflict was the
combination of mutually exclusive `--approve-for-me` and `--sandbox`. The
successor uses the pinned CLI's native `--approve-for-me` workspace-write mode
without a redundant explicit sandbox flag. LOW and MEDIUM profiles must have a
deterministic treatment-only diff. A material profile repair after successor
freeze terminates the experiment rather than changing the running contract.

**Prospective diagnostics and runtime:** Permit no more than four contentless
provider launches before freeze, with at most two launches per arm and no
repeat after that arm passes. These launches establish provider reachability
and stable termination only; they are not coding-task attempts or efficacy
evidence. Pin one experiment-local Codex bundle, its required companion,
observable model catalog, config/tool surface, and launch profiles. Revalidate
the complete runtime and arm-specific profile immediately before every subject
release and persist the sentinel receipt. Observable drift stops before launch.

**Evaluator and readiness boundary:** Cell 1 remains unauthorized until both
contentless arms pass, the 16-cluster provenance is intact, the evaluator
source and worker identities are pinned, the corrected independent campaign
clock passes, one Azure task create/execute/receipt/cleanup path is
deterministically operational, no separate Batch workload is active, the
current Codex quota snapshot has adequate operational headroom, canonical
repository health is revalidated, and no scientific-integrity defect remains.
Azure evaluator receipts must retain task, evaluator, worker/image, elapsed,
exit, timeout/retry, infrastructure, and zero-compute evidence. A separate
future-reserve workstream's task outcomes never affect selection.

**Quota interpretation:** The Codex API exposes percentage headroom rather
than a guaranteed count of coding-task starts. Prospectively require at least
75% observable weekly headroom, no reached-limit state, and no spend-control
block immediately before freeze. Record this as an operational readiness gate,
not a guarantee that every variable-duration cell will fit.

**Status:** Terminal successor. Three contentless launches were used:
one LOW launch exposed a missing pinned companion before provider contact, the
bundle was repaired once before freeze, and one LOW plus one MEDIUM launch then
passed with stable runtime/profile receipts. This is infrastructure evidence
only. All readiness gates later passed and the contract froze, but the first
cell's pre-subject revalidation stopped before subject or evaluator launch as
recorded in D-076.

---

## D-076 — Terminate the launch-surface-locked successor on pre-subject package-set drift

**Decision:** Preserve the frozen 40-cell successor contract and its single
zero-subject attempt receipt, stop the remaining schedule, and classify the
program as `EXPERIMENT INVALID / TERMINATED`. Do not repair the evaluator
environment, rerun cell 1, activate an alternate, or start another experiment.

**Reason:** The 12-gate manifest passed and contract freeze completed. During
the first cell's stronger pre-subject source revalidation, the executable,
Python `3.12.13`, evaluator modules, evaluator revision, RepoLaunch revision,
dataset hashes, and repository source trees matched the qualified identity, but
the complete evaluator Python package-set SHA-256 differed. The separate
Azure-readiness virtual environment was therefore not byte-for-byte equivalent
to the frozen evaluator-stable qualification environment. This is a material
post-freeze source/runtime identity defect and a mandatory batch stop, not a
retryable infrastructure condition.

**Scientific boundary:** The ledger contains one durable attempt reservation
and one terminal prelaunch receipt, but zero coding-task subject starts, zero
evaluator starts, zero admissible cells, 39 missing cells, and no LOW/MEDIUM
outcome. The qualified population remains historical infrastructure evidence;
it does not supply treatment evidence. ESG-RR-002 is not justified, and no
ESG-RR-002 Release is permitted.

**Infrastructure boundary:** Azure readiness demonstrated one successful
provider-free evaluator task after prospective worker corrections. At terminal,
the successor's jobs and pool were deleted and account readbacks returned pools
`[]`, jobs `[]`, and zero active nodes. Cost remains an upper-bound estimate,
not a billing claim. The separately authorized future-reserve workstream was
paused during successor use and released only after the zero-compute readback.

**Authorization boundary:** The current request authorizes the public-safe
terminal-record branch, PR, required checks, and squash merge. It does not
authorize repairing and rerunning this contract, a second experiment,
confirmatory execution, ESG-RR-002 publication, a Release, or social/external
distribution. Any new experiment is the exactly one next authorization
boundary.
# 2026-09-01: Prospectively lock evaluator environments before any new reasoning-effort freeze

**Decision:** Treat the user-authorized evaluator-environment-locked program as
a new lineage. Preserve the launch-surface-locked contract and terminal result
unchanged. Before any successor subject freeze, represent evaluator identity as
five explicit layers: evaluator source (E1), immutable execution image (E2),
resolved package/toolchain state (E3), runner/config identity (E4), and only the
task-specific inputs that legitimately vary by task (E5). Hash a canonical
semantic projection that excludes timestamps, temporary paths, process/host
names, and Azure task IDs.

**Rationale:** The predecessor compared a qualification receipt against a
newly resolved virtual environment. Python `3.12.13`, the interpreter bytes,
the evaluator/launch module bytes, and the pinned direct packages matched, but
the complete installed-distribution hash changed from
`82d6d5440801cfe448ba268f3e2e6cb64fbfcdba44d1b24ebd8a106c1379773e`
to `38b429379d977a6ef791c9d1d48f66f711f2c333102d42e03e699f6d063c642a`.
The old receipt retained only the aggregate hash rather than the normalized
distribution manifest, so the real environment could not be reconstructed or
diffed from public evidence. An explicit manifest plus immutable task-image
mapping is the smallest repair that makes equality scientifically meaningful.

**Protocol consequence:** Pre-freeze infrastructure defects may be repaired
within the bounded preflight budget. After freeze, any material E1-E5 identity
change is a mandatory stop; the environment must not be rebuilt or repaired
inside the same contract. LOW and MEDIUM for each task/repetition must bind to
the identical evaluator semantic identity. Existing outcome-blind task
qualification may be reused only after provenance and zero-subject accounting
are revalidated. The separate Azure Future Evaluator Reserve campaign remains
out of scope and must not be modified or used for task selection.

# 2026-09-01: Terminate the environment-locked successor before subject freeze

**Decision:** Select `EXPERIMENT INVALID / TERMINATED` and stop this successor
before freezing a subject contract. Thirteen of fifteen prospective readiness
gates passed, including the canonical evaluator-environment identity, two
fresh-worker reproductions, one bounded alternate gold preflight, runtime and
launch parity, and scientific-integrity checks. The subject-quota gate and the
no-reserve-contention gate failed.

**Scientific consequence:** The program has zero subject starts, zero evaluator
starts, zero admissible cells, and no LOW/MEDIUM outcome. Infrastructure
readiness is not treatment evidence. ESG-RR-002 is not scientifically
justified, and no report or Release may be created.

**Operational consequence:** No experiment-owned Azure pool, job, or active
node was created. The separate Future Evaluator Reserve was inspected only for
contention and was not stopped, resized, deleted, or used for task selection.
The failed quota gate must not be bypassed with a reset or extra provider use.

**Authorization boundary:** The authorized public-safe terminal branch, PR,
required checks, and squash merge may proceed. Any later experiment is a new
successor and requires a new explicit authorization after its own prospective
gates; this program is not resumable.
