# Pilot-v3 Adapter Repair and Successor Qualification

**Decision:** `ADAPTER REPAIR AND SUCCESSOR QUALIFIED — LIVE EXECUTION
REQUIRES SEPARATE AUTHORIZATION`

## Outcome

The Pilot-v3 live evaluator boundary now selects the attempt timeout by frozen
contract version. `pilot-v3.0` accepts only
`trajectory.timeout_seconds_per_attempt`; the retained Pilot-v1/v2 boundary
accepts only its authoritative
`timeout_seconds_per_trajectory_attempt`. Missing, mixed, unknown, boolean,
non-positive, or version-incompatible timeout shapes fail closed before the
subprocess call.

A deterministic mock reached the exact official-evaluator `_run` boundary with
timeout `1800`, passing the point that previously raised `KeyError`. It launched
no subprocess, subject, provider request, Docker evaluation, or Pilot cell.

## Root cause and repair boundary

The frozen Pilot-v3 contract and launch request consistently used
`timeout_seconds_per_attempt`. The reused shared `LiveBackend.evaluate()` still
indexed the Pilot-v1/v2 field name immediately before `_run()`. This was the
earliest proven failure and no evaluator process began.

The repair adds one small version-aware resolver at that shared adapter
boundary. It does not change a frozen timeout value, contract, schedule,
treatment, evaluator command, result parser, checkpoint sequence, or failure
taxonomy. An adjacent request-field audit found no second concrete Pilot-v3
schema-name mismatch on the subject or evaluator launch path.

## Preserved predecessor

The original Pilot-v3 evidence remains exactly:

| Evidence | Preserved value |
| --- | --- |
| Contract file SHA-256 | `5847552b71edddc7504fd7147dfcaff6fa859e120cb1bf8476a9c4ca227ef660` |
| Pool file SHA-256 | `9b4409c7ee2e88ea037a18d939a8e4652787dcc8a3f3e979a8a9ad62e574b01b` |
| Schedule file SHA-256 | `7068e11295530704e27fc772cc02869a11bd501c4dedafffe74a9ea2176c4671` |
| Terminal-result file SHA-256 | `3b28a276474e131e1edb7bd7fc9277c277127ab7e9c1119793bc2fd2a5fee855` |
| Predecessor ledger SHA-256 | `e0a03c6b7ddb6f33ee4d79473dea4536383c750b1b580a23e9c9d5de7b316ea0` |
| Predecessor ledger events | 9 |
| Position 1 attempt 1 | invalid partial; subject completed; no official evaluator disposition |
| Admissible observations / interim comparisons | 0 / 0 |
| Unstarted positions | 2–32 |

Pre/post qualification digests are identical in
`experiment/pilot_v3_adapter_successor_qualification.json`. The original ledger
was not edited, reset, truncated, relabeled, or reopened.

## Zero-live qualification

Deterministic fixtures and fault injection establish all required boundaries:

1. the frozen contract validates and regenerates byte-equivalently;
2. its canonical `1800`-second attempt timeout reaches the mocked evaluator
   subprocess boundary;
3. legacy-only Pilot-v3, missing, mixed, wrong-type, non-positive, unknown, and
   unsupported-version timeout shapes fail closed;
4. evaluator invocation passes the former `KeyError` point;
5. the already-qualified official disposition and feedback semantics remain
   unchanged;
6. `evaluator_invoked` precedes the fragile process call and
   `evaluator_finished` precedes receipt aggregation;
7. evaluator-boundary exceptions still execute credential cleanup in `finally`
   and durably record its result;
8. no receipt can be reconstructed without terminal durable evaluator evidence;
9. successor progress and partial resolution derive only from its validated
   hash-chained ledger; completed cells are not repeated after restart;
10. the original contract, pool, schedule, terminal result, and ledger bytes are
    unchanged.

## Scientific successor decision

One minimal successor lineage is scientifically admissible. The predecessor
failure was a deterministic schema incompatibility before evaluator launch, not
an observed task outcome. Position 1 was exposed to the subject, so its attempt
1 remains immutable and visible; the successor does not erase or rename it.
There are zero admissible observations and no interim arm comparison that could
have influenced the restart decision.

The authorization therefore binds the exact original contract, pool, schedule,
terminal result, predecessor ledger and terminal event, repaired adapter bytes,
and starting identity. The separate successor ledger has one genesis event:

| Successor property | Frozen value |
| --- | --- |
| Authorization SHA-256 | `a0e82151c38e4643fd5e8e74541409a65d919fcdbc555b75c42442c0801c4c69` |
| Ledger SHA-256 | `41303a6a5c86ae39784238d4d8b29440823d8b9ed80707d42e20b261453285c7` |
| Genesis event SHA-256 | `891d3e96ae697ac4f1b3275381c1e98954e5ac4ea0bb921f2e79f01a9345d391` |
| Starting position / attempt | 1 / 2, fresh isolation |
| Position 1 attempt 3 | forbidden |
| Positions 2–32 | exact frozen identities/order; begin at attempt 1 |
| Infrastructure allowance | 4 total, 0 consumed, 4 remaining |
| Operator allowance | 2 total, 0 consumed, 2 remaining |

Creating this lineage does not consume, increase, or reset either frozen
allowance. The exceptional successor authorization supplies no third attempt
and is not itself relabeled as an infrastructure or operator allowance.

## Authority and claims boundary

This is compatibility, durability, and scientific-lineage qualification only.
It provides no Pilot-v3 outcome, baseline-versus-C-short comparison, acceptance,
cost/work, quality, maintainability, equivalence, non-inferiority, per-language,
or provider-billing evidence.

The authorization and ledger do not authorize execution. A future live attempt
would require a separate explicit user authorization and a separately qualified
live successor interface. This goal stops after GitHub-first stabilization.
