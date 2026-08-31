# Evaluator-Stable Reasoning-Effort Terminal Report

## Evaluator qualification

- Attempted candidates: 20
- Validation failures: 1
- Gold failures: 0
- Infrastructure failures: 3
- Final qualified pool: 16 independent clusters
- Task and repository identities: withheld

## Experiment

- Started: no
- Codex: codex-cli 0.151.0
- Model: gpt-5.6-sol
- Frozen primary tasks: 0
- Attempt records: 0
- Actual contentless-canary subject invocation starts: 0
- Actual experimental-cell subject invocation starts: 0
- Actual total subject invocation starts: 0
- Missing cells: 0
- Alternates activated: 0

## Primary outcome

Not applicable. The stable qualification gate passed, but exact runtime identity drifted before population and contract freeze. No LOW-versus-MEDIUM outcome exists.

- Qualification selection: 12 primary candidates and 4 alternates; this was not a frozen experimental population.
- Integrity stop: runtime_identity_mismatch_before_contract_freeze
- Contract frozen: no
- Subject outcome exposed: no

## Work

Not applicable. No subject work was observed.

## Falsification

The decisive contradictory evidence is the mismatch between the qualified runtime identity and the runtime observed at the exact pre-contract freeze gate. Outcome sensitivity analyses are not applicable because no treatment outcome exists.

## Decision

- Scientific disposition: **EXPERIMENT INVALID / TERMINATED**
- ESG-RR-002 candidate: **not_applicable**
- Basis: no experiment completed because exact runtime identity drifted before contract freeze
- This is exploratory evidence and authorizes neither equivalence, noninferiority, billing, publication, pull request, merge, nor repository visibility claims or actions.

## Repository

- Branch, commit, test, CI, and CodeQL state are recorded in the canonical terminal handoff after local Git stabilization.
- Raw task, patch, trace, evaluator, and qualification working material is excluded from tracked artifacts.
- Publication, pull request, merge, and repository visibility remain separately blocked by authorization.

## Next boundary

Exactly one action requires user authorization:

> authorize_private_canonical_branch_push

Do not start another experiment, publish, or make the repository public.

Terminal result SHA-256: `150881d10332e17e81300669489bbd2e62547bbfcb15feb3e8c3259dda64956e`
