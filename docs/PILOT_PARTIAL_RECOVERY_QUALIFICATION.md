# Pilot Partial-Receipt Recovery Qualification

**Status:** complete; recovery failed closed

## Outcome

The receipt compatibility boundary is repaired for future infrastructure use,
but preserved successor cell 1 / attempt 2 cannot be finalized as a valid Pilot
observation. Required authoritative evidence is absent, and the same cell has
already reached the frozen maximum of two attempts. No resolve or rerun was
performed.

This is another post-freeze, pre-valid-outcome infrastructure repair discovered
by the Exploratory Pilot. It does not alter the experiment or provide evidence
for or against baseline or C-short v0.1.

**Pilot v1 stopped with zero valid experimental observations.** This is an
infrastructure-integrity stop, not a policy failure.

## Final preserved Pilot-v1 state

- Cell 1 / attempt 2 is unrecoverable.
- The authoritative per-instance evaluator report is absent.
- The durable evaluator exit record is absent.
- The required receipt timestamps are absent.
- The required termination metadata is absent.
- Attempt 2 is already the frozen per-cell maximum.
- Attempt 3 is unauthorized.
- Valid completed cells remain 0.
- Policy comparisons remain 0.
- No receipt, retry, successor, or new ledger event was created.
- The successor ledger remains exactly 8 events at `resolve_partial`.
- The receipt compatibility repair is retained for future infrastructure use.
- The result provides no evidence for or against baseline or `C-short v0.1`.

## Preserved state

The qualification used the real partial attempt only as immutable input.

- successor ledger: 8 events, SHA-256
  `dac4d77481549c03fb5fc8c266964f33dcec0b32bade96a6a5c0561756b2fe15`;
- successor last event: cell 1 / attempt 2 `attempt_started`, event SHA-256
  `c03a76515a7a8702304e4e874c1a93b53f1795b4bb8104f8cd498c70608562a1`;
- predecessor ledger: 9 events, SHA-256
  `0cf33d60006cc689b4664b309a94cbe8de1914e5dc2c86306cf603c44ca6a019`;
- frozen contract file SHA-256:
  `91bca22dde1d157a3d298c25fcda90ceba8c95b56a9a5e3b48e8e21402112f41`;
- successor authorization file SHA-256:
  `e723d57d89674731abf957ea875bba586fe262398f0fa2a0664de2f343af37df`.

Before and after the real recovery preview, both ledgers had the same hashes.
The successor remained at `resolve_partial`; no event was appended.

## Exact root cause and sanitized live schema

`LiveBackend.prepare()` supplied direct timezone-aware ISO strings for
`started_at` and `ended_at`. The core consumed `started_at` as a direct value but
unconditionally called `ended_at`. The fake qualification backend had supplied
an end-time lambda, so the live direct-string representation was never tested.

The stored string was also evaluated during preparation, not at attempt
completion. Its in-memory value was lost when receipt construction raised. The
repair therefore does both of the following:

1. normalizes either an observed direct ISO string or a zero-argument accessor
   at the single receipt boundary, preserving the original string and offset;
2. makes the live adapter supply a deferred end-time accessor so future end
   times are observed after subject/evaluator work.

Null, timezone-naive, malformed, or unexpected timestamp values fail closed.
No current time is substituted and no missing timestamp is invented. The only
committed live-shape fixture is sanitized and contains no provider content.

## Adjacent adapter audit

The audit was limited to fields used by the same result-to-receipt path.

| Field group | Observed representation | Contract/receipt need | Result |
|---|---|---|---|
| start/end timing | direct ISO strings from `prepare()` | timezone-aware ISO strings; true end after work | boundary repaired; preserved receipt values unavailable |
| subject exit/timeout/session/provider failure | direct dataclass fields, with nullable exit/session where permitted | direct values with explicit nullability | compatible; unchanged |
| usage | four provider-reported components; no provider `total_tokens` | preserve four components and derive `total_tokens` | boundary repaired; real usage complete |
| evaluator accessors | direct dataclass fields | structured official result plus references/hashes | representation compatible; preserved result incomplete |
| optional/null evaluator fields | direct nullable values | null only for non-completed/error states | compatible; unchanged |
| termination | derived in core after evaluator classification | one frozen taxonomy value | derivable in live flow, but not durably retained after the crash |

The usage repair does not modify any provider value. It derives
`total_tokens = input_tokens + output_tokens`, as already declared by the frozen
contract, and continues to fail closed if any required provider component is
missing or malformed.

## Preserved evidence completeness

The subject trace is terminal at one `turn.completed` event and is bound to the
preserved attempt. All four required provider usage fields exist:

- input: 916,296;
- cached input: 841,984;
- output: 4,948;
- reasoning output: 1,884;
- derived total: 921,244.

The authoritative pre-subject index exists. The prediction is uniquely keyed to
the attempt task, and its mapped patch matches the preserved zero-byte patch,
SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Recovery nevertheless lacks these required authoritative fields:

- the prepared receipt `started_at` value;
- the prepared receipt `ended_at` value;
- a durable evaluator command/exit-status record;
- the per-instance official evaluator `report.json` and therefore its resolved
  boolean and hash;
- the final in-memory termination/evaluator receipt metadata.

Filesystem timestamps were not promoted into receipt evidence.

## Evaluator-completion proof

The preserved `results.json` exists, is uniquely attributable to
`xroche__httrack-408`, and classifies it as an empty patch. Its SHA-256 is
`d2fd4cbc121c65339bfe6455d39151588ce7e8a6501974629f782723935582c0`.

That is not the complete evaluator result required by the frozen adapter. The
per-instance `report.json` is absent, so there is no authoritative resolved
boolean or report hash. The process exit status existed only in memory. A
completed evaluator process therefore cannot be promoted to a complete,
contract-valid evaluator receipt.

## State and accounting semantics

The existing successor state machine recognizes only `resolve_partial` at the
current eight-event ledger. Its execute path deliberately refuses that state
pending a separate decision. No existing successor transition reconstructs and
validates a successful `attempt_finished` event from durable artifacts.

Cell 1 is already attempt 2. The successor authorization consumed rerun unit 1
of 8 at its start, and the frozen per-cell maximum is two attempts. Attempt 3 is
therefore not contract-valid even though seven batch-level units remain. A
recovery preview consumes no additional rerun because it performs no execution
or ledger transition.

## Non-mutating recovery preview

The machine-readable preview is
`experiment/pilot_partial_recovery_qualification.json`. Against the real
partial attempt it deterministically reports:

- recovery legal: false;
- normalized receipt: unavailable;
- expected ledger events: none;
- resulting state: unchanged `resolve_partial`;
- additional reruns consumed: 0;
- next scheduled cell: none while unresolved;
- conditional frozen next cell after a hypothetical valid finalization:
  `slot-04-short-rep-1`;
- further same-cell rerun: illegal attempt 3.

The preview module imports no subject, evaluator, process-runner, or ledger
writer. Tests additionally replace process creation with a hard failure and
prove the preview still completes without execution or mutation.

## Non-Pilot receipt canary

No separately authorized non-Pilot task was available to exercise a real
subject-through-receipt finalization path. None was invented. Qualification
therefore used the preserved real artifacts plus deterministic sanitized
fixtures. This leaves live end-to-end receipt construction uncanaried, although
the exact exposed boundary and adjacent shapes are regression-covered.

The infrastructure lesson is broader than the timestamp mismatch: a
subject/evaluator execution must durably persist the authoritative evidence
required for receipt reconstruction before receipt finalization becomes a
single point of failure. Future infrastructure may apply that lesson, but this
qualification does not design Pilot v2.

## Frozen invariants and activity

The original contract, successor authorization, baseline, C-short v0.1, pool,
schedule, subject/evaluator configuration, timeouts, corrective protocol,
budgets, analysis, and claims rules were not modified.

During this goal there were zero Pilot subject calls, zero Pilot evaluator
calls, zero retries, zero task replacements, zero successor creations, zero
policy comparisons, and zero real successor-ledger mutations.

## Decision

Recovery cannot preserve experimental validity because mandatory evaluator and
timing evidence is absent. A contract-valid rerun also cannot preserve validity
because attempt 2 is the per-cell maximum. The existing evidence cannot support
either authorized continuation route.

### `STOP PILOT`
