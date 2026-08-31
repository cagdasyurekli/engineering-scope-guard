# Open Questions Before Confirmatory Work

These are intentionally unresolved. Do not let Codex silently turn them into architecture decisions.

## Before V0 implementation

### 1. Implementation language

Choose the smallest practical runtime for local Codex hook/trace ingestion and deterministic repository measurement.

Decision criteria:

- easy local install;
- reliable JSON/process/file handling;
- minimal dependency footprint;
- easy fixture-based tests;
- cross-platform needs that are real for V0, not hypothetical.

Do not choose a language for future scale or marketplace packaging.

### 2. Exact Codex integration surface

Verify against the installed/current Codex version:

- supported hook events;
- interactive vs headless/`exec` behavior;
- transcript availability;
- event gaps/failure metadata;
- plugin packaging constraints.

V0 must report unsupported coverage rather than pretend it observed events it did not receive.

### 3. Task boundary

Codex does not necessarily expose a single perfect “task completed” event in every mode/version. Define the V0 observation boundary from supported evidence, and label it honestly (session/turn/run boundary as appropriate).

## Before pilot

### 4. Task supply

Resolved at the source level in `EXTERNAL_INPUT_READINESS.md`. Four author-
visible development tasks remain permanently ineligible. The pinned
SWE-bench-Live/MultiLang frame has 634 source-eligible tasks, allocates 12 Pilot
tasks, excludes 84 tasks from Pilot repositories, and commits 538 reserve tasks
across 211 disjoint repositories without emitting their IDs or bodies. Fixed-host
qualification later produced a valid 12-task pool using four deterministic
replacements. Excluding those replacement repositories leaves an effective
opaque reserve of 499 tasks across 207 repositories. No confirmatory task body
has been selected or inspected.

### 5. Human reviewer access

Confirmed capacity is currently zero independent experienced reviewers because
no roster, commitment, or calibration evidence exists. Quality claims are
therefore limited to exact deterministic/hidden-test guardrails. One or at least
two reviewers may be recorded later only with real availability evidence.

### 6. Run budget

Development is capped at four tasks, 24 planned three-arm/repeated runs, and six
infrastructure-only replacements (30 agent sessions total). Confirmatory
execution remains unauthorized. The qualified proposed Pilot budget is 12
distinct tasks, two arms, two repetitions, 48 planned trajectories, and eight
trajectory-level infrastructure reruns (56 ceiling). It is a feasibility budget, not
a power calculation. The container/evaluator and 36-gold fixed-host
qualification gate passed through 48 retained attempts. The Pilot contract now
binds the final-pool identity and schedule and mechanically separates the
four-of-eight consumed pre-treatment task-slot budget from the zero-of-eight
trajectory-rerun budget. The exact Pilot goal remains proposed and inactive;
billing/cache limitations remain reportable constraints rather than invented
values.

### 7. Meaningful effect threshold

Before confirmatory execution, decide what efficiency improvement would justify:

- a one-sentence instruction;
- a longer policy;
- eventually a hook/plugin dependency.

These thresholds may differ because intervention cost/maintenance burden differs.

Still unresolved. No value is selected during readiness or from development
results.

### 8. Quality risk bound

Do not choose 3 pp, 5 pp, or another non-inferiority margin because it makes the sample size convenient. Decide what degradation would be substantively unacceptable for the chosen task stratum, or decline to make a non-inferiority claim.

Still unresolved. With zero confirmed independent reviewers, no non-inferiority
or broad preserved-quality claim is
permitted. Deterministic F2P/P2P evidence would support only the narrower task-
specific claim boundary documented in `EXTERNAL_INPUT_READINESS.md`.

## Before project-intent experiment

### 9. Smallest useful intent schema

Candidates to test rather than assume:

- untrusted input / exposure;
- persistence type;
- throwaway vs maintained horizon;
- explicit scale/performance requirement only when the task makes it relevant.

Avoid broad “complexity tolerance” or generic scale fields unless an experiment shows they change useful decisions.

### 10. Intent delivery mechanism

Compare only after the base policy has evidence:

- no context injection / profile used only to gate rules;
- tiny static context;
- task-relevant selected context.

Do not build RAG/context selection before this question needs to be tested.

## Before telemetry

Telemetry is not authorized in V0. Revisit only if:

- multiple independent users exist;
- local evidence shows benefit;
- there is a concrete unanswered heterogeneity question;
- the minimum derived event schema is defined;
- raw prompts/code/paths remain local;
- users can run the tool fully with telemetry off.
