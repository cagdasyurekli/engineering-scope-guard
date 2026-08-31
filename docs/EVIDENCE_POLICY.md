# Evidence & Claims Policy v0.1

This project values long-term trust over large headline numbers.

## 1. Core rule

**We do not claim more than the experiment measured.**

A result is always scoped to the exact agent/model/version/date/task distribution and evaluation procedure used.

## 2. Evidence classes

### Development

Used to build/debug the intervention. Never evidence of efficacy.

### Exploratory

Useful for generating/refining hypotheses and estimating variance. Must be labeled exploratory. May not be presented as confirmatory proof.

### Confirmatory

Requires a held-out pool and a publicly or locally timestamped/frozen experimental definition before results are inspected.

## 3. Mandatory scope block for published numbers

Every headline result must include or link immediately to:

- policy version;
- agent + exact version;
- model + exact available identifier;
- evaluation date;
- languages/repositories/task distribution;
- N distinct tasks and N total runs;
- outcome definition;
- uncertainty interval.

## 4. Claims we will not make from insufficient evidence

Do not say:

- “no quality loss” from `p > 0.05`;
- “quality preserved” without a valid predeclared non-inferiority/equivalence result or an explicitly bounded quality interval supporting that statement;
- “saves X%” without an interval and scope;
- “up to X%” based on the best subgroup/task/CI boundary;
- “improves code quality” because LOC/dependencies/files/complexity fell;
- “reduces future maintenance/rework” from a one-task benchmark;
- “works for your project” from a benchmark distribution;
- “reduces tokens” when the only effect is cheaper cached-token pricing;
- a vendor's benchmark result as if it were ours;
- user acceptance/stars/testimonials as evidence of objective productivity improvement.

## 5. Preferred null/uncertain-result language

Example:

> We did not detect a reliable cost difference. The estimated effect was -3% with a 95% interval from -14% to +9%; the data are compatible with both a meaningful saving and an increase.

For quality:

> We did not detect a difference in acceptance, but the experiment cannot rule out a decrease as large as X percentage points.

If the interval is too wide to answer the question:

> This experiment was uninformative about quality.

## 6. Negative results

Null and negative confirmatory results must be published with the same prominence as positive results.

If the full policy is not materially better than the one-sentence control, the project should publish that result and simplify/retire the full policy rather than preserve it for product identity.

## 7. Subgroups

- Predeclared strata may be reported with their interaction analysis/uncertainty.
- Unplanned subgroup discoveries are hypotheses only.
- State how many subgroups were inspected.
- Never headline the best subgroup while hiding a weak aggregate result.

## 8. Popularity is not evidence

GitHub stars, downloads, marketplace installs, testimonials, and user-reported helpfulness measure adoption/experience, not objective efficacy.

User feedback remains valid for UX outcomes such as annoyance, clarity, timing, and preference.

## 9. Claim expiry

Prompt-level behavior may change with model/harness versions.

Every supported claim must have an `evaluated_on` date and supported agent/model versions. When a materially new agent/model version is used, mark prior claims as **not yet revalidated** until rerun.

Do not silently edit old evidence. Maintain a claim changelog.

## 10. Pre-registration/freeze record

Before confirmatory runs, freeze/tag/hash:

- policy bytes;
- arm definitions;
- harness configuration;
- task sampling frame;
- outcomes/guardrails;
- MCID/margins if used;
- missing/timeout rules;
- analysis code;
- stopping rule.

If these change after results are viewed, that experiment becomes exploratory.

## 11. Reproducibility and privacy

Publish as much as safely and legally possible:

- harness and analysis code;
- frozen policy text;
- run-level derived metrics;
- exclusions/failures/timeouts;
- task definitions/tests for open benchmark tasks;
- raw traces/diffs only when licenses, secrets, privacy, and repository rights permit.

Transparency does **not** require publishing private source code, secrets, proprietary prompts, or re-identifiable user telemetry.

## 12. Conflict disclosure

The project author may also author the intervention and parts of the evaluation. Public reports must disclose this and describe mitigations such as held-out tasks, independent reviewers, hidden tests, frozen protocols, and arm-isolation canaries.

## 13. Evidence changelog template

For each public claim record:

- claim text;
- policy version;
- evidence version;
- supported agent/model versions;
- evaluated date;
- current status: supported / stale / contradicted / superseded;
- reason for change;
- link to raw/derived evidence.

## 14. Source classification and contradiction registry

Maintain material external claims in `docs/EVIDENCE_REGISTRY.md` with a stable
ID, primary URL, publication and verification dates, evidence tier,
peer-review status, model/agent/task/population scope, observed outcome,
limitations, independent support and contradiction, confidence, and expiry or
revalidation trigger.

Separate independent empirical evidence, vendor research, official product
guidance, reproducible technical work, community experience, and project-local
evidence. Official guidance establishes current supported behavior; it is not
automatically efficacy evidence. Community observations generate hypotheses;
they do not estimate prevalence or causality. Contradictory evidence must remain
visible rather than being silently resolved in favor of the project.

## 15. Outcome-efficiency claims

Do not equate fewer tokens, calls, files, LOC, tools, or turns with efficiency.
Report fresh input, cached input, output, reasoning, wall time, correction work,
search, verification, and user intervention separately where available, and
interpret them only with a correct or accepted outcome and quality guardrails.
A structural reduction without an accepted-outcome unnecessary-work mechanism
is not evidence that unnecessary work fell.

Do not publish an aggregate workflow-health score unless its construction and
decision value are independently justified. `No change recommended` is a valid
and often preferred conclusion.

## 16. Editorial and correction policy

Future reports and external educational material must follow
`docs/PUBLICATION_AND_EDITORIAL_POLICY.md`. Null, negative, and adverse findings
receive equal publication treatment. Material corrections are public and
changelogged; financial, professional, commercial, sponsorship, vendor, or
platform incentives cannot change an experimental conclusion.
