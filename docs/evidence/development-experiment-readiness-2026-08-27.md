# Development Experiment Readiness Evidence

**Date:** 2026-08-27

**Decision:** **GO to run only the declared four-task development-pool
experiment after its task packets and per-wave run rules are registered.**

This is a readiness decision. No development, pilot, or confirmatory task was
run, no future confirmatory task was inspected or selected, and no policy
efficacy or quality-preservation claim is supported.

## Declared design boundary

- Future pilot/confirmatory supply requires an opaque catalog, frozen eligibility
  rules and inventory hash, deterministic partition, and a custodian/access
  boundary before task text or hidden tests are exposed to policy authors.
- Development uses four prospectively authored synthetic/fixture-backed coverage
  tasks that are permanently ineligible for pilot or confirmatory evidence.
- The only initial arms are baseline, short semantic control, and full bounded
  policy.
- The ceiling is 24 planned agent sessions plus six infrastructure-only
  replacements, for 30 total. This is not a power calculation.
- Confirmed independent experienced-reviewer capacity is zero. Claims are
  limited to exact automated outcomes and deterministic facts.
- MCID, non-inferiority/equivalence margin, final estimand, confirmatory sample
  size, and the remaining freeze-register decisions are unresolved.

## Arm bytes

| Arm | Evidence | SHA-256 |
| --- | --- | --- |
| baseline | no intervention asset | unavailable by design |
| short | `experiment/arms/short.txt` | `c526058fa715dd605307938ddcdb7834668d70ee629dbb2fedc50284376527f6` |
| full | `experiment/arms/full.txt` | `9af28b62c1938cc597797c55c5fd52a053dfeb001543206f0c1f12dd9bcad128` |

`test_arm_policy_assets_match_current_candidate_document` passed, tying both
assets to the quoted current text in `docs/CANDIDATE_POLICY.md`.

## Isolation canary

Two fresh state roots were prepared from `tests/fixtures/demo_before`:

- `/private/tmp/esg-readiness-final-a.YMzUJo`
- `/private/tmp/esg-readiness-final-b.sJx923`

Each canary reported:

- exactly `baseline`, `short`, and `full`;
- byte-identical repository-start fingerprint
  `060034dc47222c5d2c53af915a0d89a4e0720fd68b9106d57265a90000c8426f`;
- distinct per-cell Codex state and raw/derived output roots;
- correct local child-process receipts for working directory, `CODEX_HOME`, arm,
  and intervention hash;
- no cross-arm intervention contamination;
- unchanged source repository bytes;
- status `pass` and exit `0`.

The two `canary.json` files were byte-identical (`cmp -s` exit `0`) with SHA-256
`3930545c663ae0c1daec79d86899393e50072a060044e34c26b1a62eac36e67c`.

This is a local process-envelope canary. It does not invoke Codex, prove provider
cache isolation, or establish that an unexecuted agent process honored a policy.
An equivalent exact-version/config receipt remains mandatory before each future
development batch.

## Run-record evidence

The focused fixtures demonstrate deterministic capture of:

- task/run/arm identity;
- started, completed, failed, and balanced-turn state;
- input, cached-input, output, and reasoning-output tokens when available;
- exact-decimal billed components when supplied, and explicit unavailable
  billing when absent;
- integer wall time, timeout state, and process exit;
- named verification kind/exit/pass state;
- unchanged privacy-bounded V0 derived events for structural and approved
  diagnostics.

Repeated capture from the same inputs produced byte-identical JSON. A timed-out
fixture remained a timeout with no process exit, empty verification did not
become a pass, and missing billing did not become zero cost.

## Commands and outcomes

| Command | Exit | Outcome |
| --- | ---: | --- |
| `PYTHONPATH=src python3 -m unittest tests.test_experiment -v` | 0 | 7 focused tests passed |
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | 0 | 51 tests passed |
| `PYTHONPATH=src python3 -W error -m compileall -q -f src tests scripts` | 0 | warning-clean compilation passed |
| `git diff --check` | 0 | no whitespace errors |
| two `development_experiment.py canary` invocations | 0, 0 | both passed |
| `cmp -s` over the two canary reports | 0 | byte-identical output |

## Gate disposition

| Readiness gate | Disposition | Limitation |
| --- | --- | --- |
| Predeclared frame without confirmatory exposure | GO | catalog supply/custodian still required before pilot/confirmatory work |
| Four-task development strategy | GO | task packets must be registered before first run and never reused as efficacy evidence |
| Exactly three arms | GO | any wording change creates a new recorded development version |
| Byte-identical starts and isolated state/output | GO | proved at local harness/process-envelope boundary, not provider cache layer |
| Deterministic run capture | GO | billed components remain unavailable unless the provider supplies a run record |
| Tasks/runs budget | GO | 30-session ceiling is debugging capacity, not statistical adequacy |
| Reviewer capacity | GO with narrowed claims | zero independent experienced reviewers confirmed; no broad quality claim |
| Confirmatory methodological freeze | NO-GO today | unresolved items are registered and must be frozen later |

## Bounded conclusion

**GO to run development-pool experiments only.** Before the first run, register
the four non-efficacy task packets and freeze equal per-wave timeout, max-turn,
permissions, failure, and replacement rules. Stay within 30 agent sessions.

**NO-GO for pilot or confirmatory evaluation.** The opaque catalog/custodian,
task supply, reviewer protocol/capacity, MCID or explicit no-MCID decision,
quality margin or explicit no-non-inferiority decision, analysis design, and
other freeze-register entries remain unresolved.

The readiness decision says the development experiment can be operated
interpretabily at the tested local boundary. It does not say that either policy
works, saves cost/tokens, or preserves quality.
