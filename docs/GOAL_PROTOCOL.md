# Goal Protocol

## Purpose

This protocol keeps Codex focused on one evidence-producing objective at a time and prevents opportunistic scope expansion.

The project objective is stable; the current goal is disposable and may change as evidence changes.

## Hierarchy

1. **Project objective** — why this repository exists. Defined by `README.md` and `docs/PRODUCT_SCOPE.md`.
2. **Current goal** — the single active outcome being pursued now. Defined by `docs/CURRENT_GOAL.md`.
3. **Tasks** — concrete implementation/research steps needed to satisfy the current goal.

Do not create parallel goals unless the user explicitly requests concurrent work.

## Creating a goal

A goal may be created when:

- the user explicitly requests a new outcome;
- the previous goal is complete and the next goal is already implied by the approved project scope/roadmap; or
- evidence shows the existing goal cannot answer the question it was created to answer.

Before implementation, write or update `docs/CURRENT_GOAL.md` with:

- **Goal** — one outcome, not a list of activities;
- **Why now** — what uncertainty or user need it resolves;
- **Success criteria** — observable evidence required to call it complete;
- **In scope** — work required now;
- **Non-goals** — tempting adjacent work that is explicitly deferred;
- **Evidence required** — tests, fixtures, measurements, or review needed;
- **Model/reasoning plan** — initial configuration and allowed escalation path, following `docs/MODEL_REASONING_POLICY.md`;
- **Stop conditions** — when to stop even if more improvements are possible;
- **Status** — `proposed`, `active`, `blocked`, `complete`, or `abandoned`.

## Goal quality rules

A good goal:

- can be falsified or completed with observable evidence;
- is small enough to finish without inventing a new architecture;
- separates required behavior from future improvements;
- does not encode a solution if the solution itself is still under investigation;
- does not use “production-ready”, “enterprise-ready”, “future-proof”, or similar unbounded targets unless the user explicitly requires them.

## Public-repository quality baseline

This is a public open-source repository. Public does **not** mean “production service”.

The repository should be safe and credible for others to inspect, clone, run, and contribute to. That requires:

- clear setup/use documentation;
- deterministic tests for the behavior we claim;
- safe local defaults;
- no accidental secret collection or network telemetry;
- understandable code and error messages;
- dependency hygiene and reproducible behavior where practical.

It does **not** by itself require:

- high availability;
- multi-user/auth infrastructure;
- cloud deployment;
- enterprise observability;
- compliance frameworks;
- distributed services;
- speculative scalability work;
- exhaustive hardening for deployment modes the project does not support.

Add those only when an explicit goal requires them.

## Working a goal

During implementation:

1. Work only toward the current goal's success criteria.
2. Record material design/evidence decisions in `docs/DECISIONS.md` when required by `AGENTS.md`.
3. Treat newly discovered adjacent opportunities as notes/non-goals unless they block the current goal.
4. Do not silently broaden success criteria after implementation begins.
5. Do not keep polishing after all success criteria and stop conditions are met.

## Failure handling

A failed task does not automatically justify more compute or a stronger model.

First classify the failure:

### Mechanical/environment failure

Examples: typo, missing fixture, malformed path, dependency/environment mismatch, deterministic test setup issue.

**Action:** fix with the current model/effort. Do not escalate merely because the command failed.

### Information/context failure

Examples: required file was not inspected, requirement was misunderstood, repository state was incomplete.

**Action:** retrieve the missing evidence first. Keep the same model/effort unless reasoning itself remains difficult after the missing information is supplied.

### Reasoning failure

Examples: same plausible hypothesis fails repeatedly; root cause remains unclear despite adequate evidence; constraints interact in a non-obvious way.

**Action:** increase reasoning by one level if the current model is capable. Re-evaluate before escalating again.

### Capability failure

Examples: repeated reasoning attempts fail on a genuinely complex task; task requires stronger architecture/debugging/statistical/security judgment than the current model reliably provides.

**Action:** move to a stronger model, normally resetting effort to a sensible baseline (`medium`) before increasing it further. Do not carry `xhigh/max` forward automatically.

### Hypothesis/goal failure

Examples: evidence shows the planned approach cannot satisfy the success criteria, or the goal tests the wrong question.

**Action:** do not brute-force with more reasoning. Mark the goal `blocked` or `abandoned`, explain the evidence, and revise the goal/approach.

## When escalation is justified

Escalate model and/or reasoning only when the expected value of better reasoning is material to correctness or progress.

Good escalation reasons:

- unresolved root-cause debugging after adequate evidence collection;
- security-sensitive or destructive decisions;
- architecture decisions with costly reversal;
- statistical/evaluation methodology where a subtle error would invalidate evidence;
- complex concurrency/state interactions;
- repeated failed attempts that fail for different non-mechanical reasons.

Poor escalation reasons:

- a test failed once;
- a command returned an error that explains the fix;
- the task is large but mechanical;
- more reasoning might make the answer “nicer”;
- the agent has not yet inspected obvious evidence.

## Completing a goal

Mark a goal complete only when every success criterion has evidence.

On completion:

1. Record the evidence in `docs/CURRENT_GOAL.md`.
2. Record durable decisions in `docs/DECISIONS.md` when applicable.
3. Update and validate `experiment/agent_handoff.json` according to
   `docs/AGENT_HANDOFF_PROTOCOL.md`.
4. Note unresolved follow-ups without implementing them.
5. Propose the next goal only if it is already inside approved scope; otherwise stop for user direction.
6. Do not start the next goal in the same step if it materially expands scope.

The same handoff update is required for any blocked, abandoned, or other
terminal goal state. The handoff indexes durable state; it does not replace
authoritative goal, decision, receipt, contract, ledger, report, or Git records,
and it never creates execution authority.

## Changing an active goal

Change an active goal only when:

- the user changes the requested outcome;
- new evidence invalidates a core assumption;
- an external capability/API limitation makes the goal impossible as written;
- the goal is too broad to produce interpretable evidence.

Document why. A failure to implement one task is not sufficient reason to redefine the goal.
