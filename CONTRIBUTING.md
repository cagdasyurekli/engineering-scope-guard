# Contributing

Thank you for considering a contribution to Engineering Scope Guard.

This repository is currently evaluating the V0 Shadow Scope Analyzer. Please read
[`AGENTS.md`](AGENTS.md), [`docs/START_HERE.md`](docs/START_HERE.md), and the
active goal in [`docs/CURRENT_GOAL.md`](docs/CURRENT_GOAL.md) before proposing a
change.

## Before opening an issue

- Use the bug report form for reproducible defects in implemented behavior.
- Use the evidence concern form for problems with a research claim, protocol,
  measurement, or interpretation.
- Do not include credentials, private source code, proprietary prompts, or raw
  traces that may contain sensitive data.
- Do not include private working discussions, assistant/user transcripts,
  private memory exports, personal planning notes, or unrelated personal
  information. Record only the minimum impersonal project conclusion needed for
  evidence, reproducibility, policy, or a durable project decision.
- Do not report security vulnerabilities in a public issue. Follow the private
  vulnerability reporting instructions in [`SECURITY.md`](SECURITY.md).

Feature requests for later product phases are intentionally deferred until the
V0 evidence gate is passed.

## Pull requests

Keep each pull request tied to the single active goal and make the smallest
coherent change that satisfies it. In particular:

- preserve the V0 non-goals in `AGENTS.md` and `docs/PRODUCT_SCOPE.md`;
- prefer deterministic, local mechanisms and the standard library;
- do not add telemetry, network calls, automatic repository modifications, a
  supervising LLM, or model routing as a product feature;
- add or update tests in proportion to the behavior changed;
- report the exact checks you ran and any material limitation;
- use a privacy-safe Git author identity for public contributions;
- update `docs/DECISIONS.md` when a change alters an experimental definition or
  another durable project decision.

Changes to candidate policy wording, experimental arms, task selection,
outcomes, guardrails, timeout handling, analysis methods, or public claim rules
must include the matching protocol update and rationale required by
`AGENTS.md`. Exploratory results must never be presented as confirmatory.

## Development setup

Use Python 3.11 or newer. V0 has no third-party runtime dependencies and can be
run directly from a checkout:

```bash
PYTHONPATH=src python3 -m engineering_scope_guard --help
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Keep test repositories and analyzer state in separate temporary directories.
Documentation changes should also be checked for working relative links and
consistency with the authoritative project contract.
