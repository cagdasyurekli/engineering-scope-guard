# Experiment Log Template

## Identity

- Experiment ID:
- Date:
- Policy version:
- Git tag/hash:
- Agent/version:
- Model/version:
- Harness version:
- Task pool: development / exploratory / confirmatory

## Question

What single question does this experiment answer?

## Predeclared comparison

- Primary comparison:
- Secondary comparison:

## Frozen inputs

- Policy bytes/hash:
- Agent config:
- Reasoning config:
- Tools/permissions:
- Task sampling rule:
- Repository snapshots:
- Timeout/max-turn rule:
- Corrective-round rule:
- Outcome definitions:
- Missing/failure rule:
- Analysis code/hash:

## Outcomes

### Efficiency

- Primary estimand:
- Mean:
- Median:
- Interval:

### Acceptance/quality

- Acceptance definition:
- Arm rates:
- Difference/interval:
- What degradation can/cannot be ruled out?

### Guardrails

- Hidden tests:
- Unrelated regressions:
- Seeded guard retention:
- Shared-cause stratum:
- Evaluator/config edits:

### Secondary/diagnostics

- Turns:
- Tool calls:
- Failed-verification loops:
- Corrective rounds:
- Files read:
- LOC:
- Files:
- Dependencies:

## Isolation/validity checks

- Canary passed?
- Cross-cell cache isolated?
- Timeouts handled per protocol?
- Reviewer blinding manipulation check:
- Missing data:
- Deviations from preregistration:

## Interpretation

### What the data support

### What the data do not support

### Alternative explanations

### Decision

- Continue
- Simplify to short policy
- Narrow scope
- Revise and return to exploratory
- Stop

## Public claim candidate

Write the exact sentence that would be allowed under `EVIDENCE_POLICY.md`.
