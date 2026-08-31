# Changelog

## Unreleased

### Research publication

- Prepared ESG-RR-001 v0.6 as an unchanged-science republication under a clean
  canonical repository identity following repository-history privacy
  sanitation.

### Project foundation

- Defined V0 as a local, shadow-only scope analyzer.
- Added candidate bounded policy and mandatory short semantic control.
- Added evaluation protocol separating development, pilot, and held-out confirmatory evidence.
- Added evidence/claims policy with null-result, uncertainty, scope, and claim-expiry requirements.
- Deferred project-intent injection, telemetry, multi-agent support, and supervising LLM behavior until evidence gates are passed.
- Added explicit current-goal lifecycle and goal drift controls.
- Added development-time model/reasoning selection and failure-driven escalation policy.
- Clarified public OSS quality baseline vs. production-service hardening.
- Updated Codex handoff and AGENTS instructions to use the new protocols.

### V0 Shadow Scope Analyzer

- Added the standard-library `python -m engineering_scope_guard` workflow for
  capability inspection, outside-target state initialization, repository
  snapshots, and local analysis.
- Added named/versioned deterministic snapshot, LOC, candidate-infrastructure,
  event, and capability-coverage contracts.
- Added privacy-bounded trace summaries, local reports, fixture canaries, and
  tests for malformed inputs, target immutability, and in-process socket denial.
