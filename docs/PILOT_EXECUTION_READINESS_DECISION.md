# Pilot Execution Readiness Decision

**Status:** complete
**Decision date:** 2026-08-28
**Evidence class:** decision-only; zero Pilot policy-comparison runs

## Outcome

The task source, replacement-linked 12-task pool, official evaluator, fixed
host, one live two-turn subject trajectory, session-persistence rule, and narrow
measurement/claim boundaries are now sufficient inputs for a Pilot harness.
They do not yet jointly authorize the Exploratory Pilot because the repository
cannot reproduce all frozen execution controls as a batch, and two prospective
allocation rules remain ambiguous.

No Codex subject, baseline cell, C-short cell, Pilot comparison, Freeze, or
confirmatory run was executed during this decision.

## Evidence precedence

The original `docs/PILOT_READINESS.md` and
`experiment/pilot_readiness.json` remain historical evidence for the initial
NO-GO design. Their zero-task, absent-partition, and unqualified-evaluator facts
were later superseded by D-019, D-020, D-021, and their receipts. Their arm,
measurement, failure, reviewer, claims, and MCID boundaries remain applicable
unless explicitly replaced below.

This reconciliation does not rewrite those earlier results or silently reopen
the selected source, policy wording, outcome hierarchy, task eligibility, or
host qualification.

## Gate reconciliation

| Gate | Current status | Durable evidence and boundary |
| --- | --- | --- |
| Arms | Satisfied | Exactly baseline versus `C-short v0.1`; short-policy SHA-256 `c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6`; D v0.1 remains excluded. Development results selected the question but did not establish efficacy. |
| Source and eligibility | Satisfied | SWE-bench-Live/MultiLang revision `62dc0745c40f067fc366ae3eb1a26136e5928f85`; 1,077 rows, 634 eligible tasks, 223 repositories, metadata-only selection. |
| Partition | Satisfied with an opacity limit | Original allocation: 12 Pilot tasks/12 repositories and 538 reserve tasks/211 repositories. IDs/bodies were not emitted or inspected, but a public dataset, seed, and algorithm do not provide cryptographic secrecy or independent custody. |
| Final Pilot pool | Satisfied | Eight original tasks plus Sail, HTTrack, Caddy, and doctoc; 12 tasks/12 repositories preserving the eight language quotas. All final tasks passed three of three official gold evaluations. |
| Effective reserve | Satisfied | Replacement-repository exclusion leaves 499 tasks across 207 repositories; ranked-ID commitment `609b0dfba0a27dbd535f3db67375d84a454c7ad98b7fdd03cf501fdd16958930`; no reserve IDs/bodies emitted. |
| Evaluator | Satisfied for deterministic gates | Pinned evaluator `bc09878a5d192d0804dbd647dc6e650372fcb0ac`, RepoLaunch `c4b623d930f3728e5338664bb634021b98492cbf`, unchanged official images, one worker, fixed `linux/amd64` host. This supports F2P/P2P/rebuild/test outcomes, not maintainability or architecture claims. |
| Host/resource feasibility | Satisfied within the measured envelope | Forty-eight gold attempts, 40 PASS/eight FAIL, final pool 36/36 PASS, no OOM or timeout. Evaluator-only planning burden is 3.50–7.00 hours for 48 trajectories; gold time does not predict subject time. |
| Fixed subject specification | Satisfied as a specification | Codex 0.150.1, `gpt-5.6-terra`, medium reasoning, workspace-write automatic review, maximum two turns, 900 seconds per turn and 1,800 seconds per trajectory. The local CLI still reported 0.150.1 during this decision. Exact backend snapshot remains unavailable. |
| Live fixed-subject path | Satisfied for one non-comparative condition | One complete snapshot → initial turn → official evaluator → one failing-name correction → same-session turn → evaluator → receipt trajectory exists. Its unresolved task result is not policy evidence. |
| Session persistence | Satisfied as a rule | Fresh session retained only within one trajectory for the corrective turn; never resumed across tasks, arms, or repetitions. The failed ephemeral-resume attempt remains retained. |
| Local cell-envelope isolation | Satisfied only as a local canary | Two byte-identical baseline/short directory-envelope canaries exist. They do not execute the live batch subject or prove frozen tool/environment enforcement. |
| Batch harness enforcement | **Blocker** | Current code copies the full process environment, does not enforce the required tool/feature receipt, uses the development runner's ephemeral one-turn path, kills only the parent on timeout, and has no integrated official-evaluator corrective/failure ledger for Pilot cells. |
| Run/arm order | **Blocker** | The historical schedule formula is bound to the superseded v0.1 mechanism-strata seed. No durable artifact binds it prospectively to the v1 external seed and final replacement-linked pool. |
| Token observability | Satisfied for component reporting | Input, cached-input, output, and reasoning-output tokens were observed. Fresh input may be calculated as input minus cached input and must be labeled calculated. |
| Cache and billing | Compatible limitation, not a pass | Cache-write tokens, provider-billed amount/currency, exact backend snapshot, and provider cache-namespace separation are unavailable. Token components and behavioral outcomes remain reportable; billed-cost, cost-savings, and cache-price-as-work claims are prohibited. |
| Reviewer capacity | Compatible limitation for the narrow question | Confirmed independent experienced reviewers remain zero. Deterministic acceptance/variance questions remain possible; human-quality claims do not. |
| Quality claims | Satisfied as a prohibition | No maintainability, overall quality, architecture, equivalence, non-inferiority, objective overengineering, downstream-maintenance, or efficacy claim is authorized. |
| MCID and quality margin | Deferred to Freeze | The exploratory Pilot needs neither. No 15%, 5%, three-percentage-point, or other arbitrary value is inherited. Confirmatory estimand, margin, and sample size remain unresolved. |
| Timeout/failure/missingness rules | Specified | Agent/task failure and policy timeout remain outcomes with no free rerun. Arm-independent harness/provider/isolation failures are retained, invalidate the matched block, and may consume only an authorized infrastructure reserve. Missing measurements remain explicit and are never imputed as zero or dropped. |
| Replacement-budget units | **Blocker** | Host qualification records an allowance of eight task-slot substitutions with four consumed. The Pilot design records eight trajectory-level infrastructure reruns and a 56-trajectory ceiling. These units are not interchangeable, and durable authority does not explicitly separate or debit them. |

## What does not block the narrow Pilot question

Zero reviewers, unavailable provider billing, unproved provider-side cache
namespaces, sparse resource point samples, and unresolved MCID/non-inferiority
margin do not require changing the task pool, policy, model, or host. They require
strictly narrower reporting:

- exact automated acceptance, discordance, failures, missingness, and corrective
  use;
- separately reported provider token components, time, turns, and structural
  diagnostics;
- task-clustered exploratory distributions and variance;
- no billed-cost, broad quality, equivalence, non-inferiority, downstream-work,
  or policy-efficacy claim.

## Why authorization stops here

Treating a written isolation protocol as an implemented batch harness would make
contamination and failure classification non-auditable. Reusing the development
runner would also reintroduce the already-demonstrated ephemeral-resume defect,
an uncontrolled environment, and incomplete timeout cleanup. Finally, silently
calling two different replacement units one shared or two independent budgets
would replenish or consume authority after observed infrastructure outcomes.

These are bounded, remediable execution-contract defects. They do not justify
changing C-short, the qualified tasks, Docker resources, official images,
reviewer facts, or hardware.

## Exactly one proposed next goal

**Pilot Harness and Reserve Contract Qualification — proposed, not active.**

Implement and qualify the smallest deterministic Pilot batch harness and
prospectively freeze the v1 final-pool order plus non-overlapping replacement
budget units, using dry-run and non-comparative canaries only. Prove:

- byte-identical per-arm starts and unique repository, `CODEX_HOME`, raw,
  derived, session, and temporary roots;
- an allowlisted environment and exact Codex/model/reasoning/permission/tool/
  feature receipt;
- baseline receives no policy bytes and short receives the exact frozen hash;
- trajectory-local corrective resume with exactly one failing-name feedback
  round;
- process-group timeout cleanup and the 900/1,800-second limits;
- official evaluator integration, frozen failure classification, complete
  missingness/deviation retention, and drift stops;
- an exact schedule commitment for the v1 final pool;
- explicit, prospectively non-overlapping task-slot and trajectory-rerun budget
  semantics that do not replenish after outcomes.

The goal must stop before the first baseline-versus-C-short task cell. It is
preferable to changing the Pilot design or hardware because source, tasks,
evaluator, subject specification, and fixed host are already qualified; the
remaining uncertainty is local enforcement and authority accounting.

## Evidence

- `experiment/pilot_execution_readiness.json`: machine-readable matrix,
  blockers, source-byte commitments, claim boundaries, and inactive proposal.
- `scripts/pilot_execution_readiness.py`: deterministic cross-artifact audit.
- `docs/PILOT_READINESS.md`, `docs/EXTERNAL_INPUT_READINESS.md`,
  `docs/EVALUATOR_RUNTIME_READINESS.md`, and
  `docs/PILOT_HOST_QUALIFICATION.md`: completed goal evidence.
- `experiment/external_task_partition.json`,
  `experiment/evaluator_runtime_readiness.json`, and
  `experiment/pilot_host_qualification.json`: authoritative receipts.

## Bounded conclusion

**REDESIGN REQUIRED**
