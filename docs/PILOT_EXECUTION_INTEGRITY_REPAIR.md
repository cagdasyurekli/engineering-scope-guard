# Pilot Execution Integrity Repair

**Completed:** 2026-08-28

**Scope:** runner and infrastructure qualification only

**Pilot activity:** none

## Outcome

The three observed execution-integrity defects are repaired and qualified. The
existing Pilot batch still cannot be resumed because its immutable nine-event
ledger already terminates in `batch_stopped`; the frozen state machine has no
legal transition after that event.

**REDESIGN REQUIRED**

## Authentication isolation

The host is logged in through ChatGPT using the file credential store. Codex
0.150.1 reads that cache from `auth.json` under `CODEX_HOME`, consistent with
the [OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth).
The runner now:

- validates the source file and rejects missing, unsupported, or group/world-
  accessible credentials;
- creates a fresh trajectory-local home with mode `0700`;
- copies only `auth.json` with mode `0600`—not config, history, sessions,
  databases, rules, or other normal Codex state;
- removes the copied credential in a `finally` cleanup path, including subject
  failures; and
- persists only login/storage mode, permissions, terminal status, and usage
  counts.

Two independent non-Pilot canaries used fresh isolated homes. Both reached
`turn.completed`, reported complete usage, and removed the copied credential.
No prompt, response, trace, session identifier, or credential value was
persisted in the qualification receipt.

## Provider-error boundary

An in-memory, content-free schema case captures the Codex 0.150.1 message-only
HTTP 401 event shape observed in failed cell 1; no provider trace is retained.
Classification is restricted to `error` and `turn.failed` records and
recognizes structured provider codes or bounded 401/403 authentication status
text. The same text in agent output does not classify as infrastructure, and an
unknown failure remains malformed/fail-closed.

## Repository baseline

The official evaluator applies the submitted model patch with `git apply` to
the same task-image state. Resetting or cleaning the image would therefore
change evaluator semantics. The runner instead snapshots the exact
pre-subject index into a derived alternate Git index/tree, then derives the
model patch relative to that tree. Pre-existing tracked and untracked image
state is retained for evaluation but excluded from subject attribution.

All 12 frozen slots were independently copied from their official images,
without Codex, treatment, evaluator, or ledger work:

| Slot | Tracked | Untracked | Ignored | Baseline tree | No-subject patch |
|---:|---:|---:|---:|---|---:|
| 1 | 0 | 19 | 2 | `4601c9da387f48f4316dc93c16020a8e7b05c215` | 0 bytes |
| 2 | 0 | 1 | 1 | `d422009def4565656f2f5236a1ed719f54b3ef01` | 0 bytes |
| 3 | 0 | 0 | 135 | `213ffd8cff6f80d3c663571c0d961f8350a766f5` | 0 bytes |
| 4 | 1 | 76 | 161 | `de05218e4847fc7557d897509d0c5c08c6ff5e9d` | 0 bytes |
| 5 | 1 | 80 | 126 | `768d00678ab9006a2a4edb312c5a28d77ea64f08` | 0 bytes |
| 6 | 0 | 0 | 2 | `61a75d05e53f092c6580085adca2a4676b25d83c` | 0 bytes |
| 7 | 0 | 0 | 43 | `049f0e1c1b87fb22fc571e87888ad29680f42da5` | 0 bytes |
| 8 | 0 | 1 | 21 | `3130ec4597c54b96b83a25763477530335f7a6d3` | 0 bytes |
| 9 | 0 | 2 | 0 | `ebfb89c306f5e47c70b7003d5a95c1602a8d29f3` | 0 bytes |
| 10 | 0 | 0 | 3 | `643e3cfc77805738bce9fd5d870a6c3e3c5d46bf` | 0 bytes |
| 11 | 0 | 1 | 2 | `0efd401c059b68c68cd19aab486871992f7c55c8` | 0 bytes |
| 12 | 0 | 0 | 2 | `942516876098da61c4ad863b31eab43c9ac5b8e7` | 0 bytes |

Every slot was at its frozen base revision and satisfied the baseline
invariant. This also proves that “clean checkout” was the wrong assumption:
the official images intentionally or operationally contain ignored/build
state, and slots 4 and 5 also contain tracked modifications. The historical
failed-cell-1 state exactly matched a fresh slot-4 materialization (same HEAD,
1 tracked, 76 untracked, and 161 ignored paths), locating the dirt in the
official image/materialization rather than in subject execution.

## Immutable ledger and rerun budget

The ledger remained byte-identical at
`0cf33d60006cc689b4664b309a94cbe8de1914e5dc2c86306cf603c44ca6a019`;
its terminal event remains
`f1868900f9aea206913fe594ceb53a3ffcab21fa72bf254afd3637ef2de73046`.
The stored attempt is `malformed_incomplete_measurement`, followed by
`batch_stopped`, so its legal next action is still `batch_stopped` and it is not
rerunnable. Zero rerun units were consumed. Had the original attempt been
stored prospectively as the now-correct provider infrastructure class, the
frozen rules would have authorized the same cell's attempt 2 and consumed one
trajectory-infrastructure rerun unit. That counterfactual cannot be used to
rewrite historical evidence.

## Integrity evidence

- Frozen canonical contract digest:
  `1ec191306215936c4f17bd0805d0a4619e0530a4d79c91c0240212b26226ead0`.
- Frozen contract file SHA-256 before and after:
  `91bca22dde1d157a3d298c25fcda90ceba8c95b56a9a5e3b48e8e21402112f41`.
- 2 non-Pilot auth canaries; 12 materializations; 0 Pilot executes, subjects,
  evaluators, treatments, comparisons, reruns, replacements, or ledger writes.
- 115 repository tests, warning-clean compilation, the exact frozen-contract
  audit, the historical harness audit, JSON parsing, secret-absence checks,
  and `git diff --check` passed.
- Machine-readable evidence:
  `experiment/pilot_execution_integrity_qualification.json`.

The repaired preflight now repeats the live auth and all-slot baseline
qualification and blocks execution unless both pass and the durable ledger
itself authorizes resume. The separate qualification command records a bounded
non-executing result even when the ledger correctly requires redesign.
