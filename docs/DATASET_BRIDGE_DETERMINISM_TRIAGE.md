# Dataset Bridge Determinism Triage

**Status:** complete; resolver-only qualification passed

## Outcome

The discrepancy has a deterministic implementation explanation. The failed
one-shot wrapper converted the evaluator virtual-environment interpreter with
`Path.resolve()`. On this host, `.venv/bin/python` is a symlink; dereferencing
it selected the base Python executable, changed `sys.prefix` from the evaluator
virtual environment to the base installation, and made `pyarrow` unavailable.
The dataset bridge then exited one before reading the pinned parquet file.

The later read-only lookup invoked `.venv/bin/python` without dereferencing it.
That preserved the virtual-environment identity, loaded `pyarrow 25.0.1`, and
resolved the exact task from the local pinned parquet split.

This was not a warm-cache success, a task-ID discrepancy, or evidence of a
transient network/source failure.

## Preserved observations and call paths

The original observations remain unchanged:

- Failed one-shot command shape: `PYTHONPATH=src <evaluator-venv-python>
  scripts/pilot_v2.py run-canary`; exit 1 with the visible parent error
  `dataset bridge failed for BYVoid__OpenCC-1096`. The child stderr was not
  retained at the time.
- Later successful command shape: `<evaluator-venv-python>
  scripts/pilot_dataset_bridge.py --dataset-root <pinned-local-dataset>
  --language cpp --instance-id BYVoid__OpenCC-1096 resolve`; exit 0.

The failed path was:

1. the one-shot wrapper started under the evaluator virtual environment;
2. its argument setup called `.resolve()` on `.venv/bin/python`;
3. the wrapper passed that dereferenced base interpreter to the resolver
   function then named `scripts.pilot_runner._bridge`;
4. the child executed `scripts/pilot_dataset_bridge.py` under the base Python;
5. `_rows()` could not import `pyarrow` and returned the fixed
   `qualified evaluator Python lacks pyarrow` error;
6. the parent discarded child stderr and exposed only the generic bridge error.

The successful path invoked `scripts/pilot_dataset_bridge.py` directly through
the `.venv/bin/python` symlink, then used `_rows()` and `_resolve()` against the
same exact local `cpp` parquet split and task identifier.

## Observed comparison

| Factor | Failed one-shot resolver child | Successful read-only lookup | Relevance |
|---|---|---|---|
| Requested interpreter | evaluator `.venv/bin/python` | evaluator `.venv/bin/python` | Same before wrapper normalization |
| Effective interpreter | dereferenced base Python | virtual-environment symlink | Root cause |
| Python | 3.12.13 | 3.12.13 | Same language runtime |
| Virtual environment active | no | yes | Root cause |
| `pyarrow` | unavailable | 25.0.1 | Root cause |
| Working directory | repository root | repository root | Same |
| `PYTHONPATH` | `src` | unset | Observed difference, falsified as causal by a passing canonical run with `PYTHONPATH=src` |
| Dataset | local pinned revision `62dc0745c40f067fc366ae3eb1a26136e5928f85` | same | Same |
| Config/split | one `cpp-00000-of-00001.parquet` file | same | Same |
| Parquet SHA-256 | `8448db887817b63e4c0c284ca99de1ccda15023f48e5b2234a4084466e0768ae` | same | Same |
| Task ID handling | exact string equality, no normalization | same | Same |
| Cache/source behavior | bridge failed before parquet import/read | direct local parquet read | No warm-cache prerequisite |
| Network/Hugging Face behavior | none in bridge path | none in bridge path | Not causal |
| Lock/materialization behavior | no bridge lock or materialization path | same | Not causal |

Graphify navigation was not used beyond checking availability: no
`graphify-out/graph.json` existed, and the two exact call paths were already
bounded to the preserved command transcript and two small authoritative source
files. Building a new graph would not have reduced uncertainty and no Graphify
output was created.

## Bounded reproduction matrix

The sanitized receipt at
`experiment/dataset_bridge_qualification.json` records:

- fresh canonical resolver process: pass;
- two resolutions in one process: pass with identical metadata digest;
- fresh canonical process after prior success: pass with the same digest;
- exact legacy dereferenced-interpreter path: deterministic exit 1 with
  `missing_pyarrow`;
- exact later read-only path: pass with the same metadata digest.

All four successful resolutions produced metadata SHA-256
`0a83c09240ba5ae16c9d50c922e419146ed9202a5388b018803f226ba1d61d5d`.
No task body was persisted.

## Minimal repair

`scripts.pilot_runner.canonical_evaluator_python` now makes the interpreter
path absolute without dereferencing symlinks. The established runner uses this
helper, and the resolver-only qualification invokes the same canonical
`scripts.pilot_runner.resolve_dataset_task` function required by an eventual
canary.

Two regression tests prove that default and explicit virtual-environment
interpreter symlinks remain intact. The repair adds no retry, cache manager,
download behavior, service, or benchmark abstraction.

## Activity boundary

This goal performed local dataset/task resolution only. It made zero Codex
invocations, credential copies, official evaluator invocations, live-canary
invocations, Pilot ledger/receipt writes, Pilot-v2 freezes, or policy
comparisons.

## Decision

### `DATASET BRIDGE QUALIFIED — GO TO ONE FINAL LIVE CANARY`

This decision authorizes no live canary in the current goal. It records only
that the original discrepancy is explained, the canonical resolver is
deterministic in fresh processes under the intended evaluator environment, and
no hidden warm-cache prerequisite exists. A live canary requires a separate
active goal and explicit authorization.
