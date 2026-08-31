# Codex 0.150.1 exec command/file-change canary

**Run date:** 2026-08-27

**Installed CLI:** `codex-cli 0.150.1`

**Scope:** one controlled `codex exec --json` command/file-change task in an isolated disposable Git repository

**Evidence class:** development capability evidence, not efficacy evidence

## Boundary and configuration

The target repository, analyzer state, raw stdout, stderr, and a temporary
`CODEX_HOME` were created under one disposable `/private/tmp` directory. The
temporary home contained only a copied authentication file; user configuration
and user exec-policy rules were ignored, and the run was ephemeral. The target
repository contained a narrow `AGENTS.md` canary boundary and a README before
the run. No real user workspace was used.

The provider prompt, response text, source contents, raw command text, raw tool
output, identifiers, absolute paths, token counts, credentials, and private
values are excluded from repository evidence. The raw capture remained only in
the disposable directory. The repository fixture replaces content and IDs with
redaction markers, substitutes a synthetic command/program, retains the
synthetic relative path `canary.txt`, and uses an empty usage object. This is the
minimum shape needed to exercise the observed event family without preserving
the provider transcript.

## Installed-interface checks

These commands were run from the project checkout before the provider canary:

```bash
codex --version
codex exec --help
codex features list
```

They reported `codex-cli 0.150.1`, exposed `codex exec --json`, and listed
`hooks` as stable and enabled.

## Canary commands and execution classification

The shell variables below describe the actual command structure while
deliberately omitting the provider prompt bytes and randomized temporary suffix:

```bash
CANARY_ROOT=/private/tmp/<randomized-canary-directory>
CANARY_PROMPT='<redacted provider prompt>'

CODEX_HOME="$CANARY_ROOT/codex-home" codex exec --json \
  --ephemeral --ignore-user-config --ignore-rules --approve-for-me \
  -m gpt-5.6-sol -c 'model_reasoning_effort="medium"' \
  -C "$CANARY_ROOT/repo" "$CANARY_PROMPT" \
  > "$CANARY_ROOT/capture/stdout.jsonl" \
  2> "$CANARY_ROOT/capture/stderr.txt"
```

An initial invocation also supplied `-s workspace-write`. Codex rejected that
locally because `--approve-for-me` and `--sandbox` cannot be combined; it exited
2 with no JSONL stdout and made no provider call. Removing only `-s
workspace-write` preserved the requested workspace-write behavior documented by
`--approve-for-me`.

The corrected invocation first ran in the restricted command sandbox. Provider
DNS/WebSocket connection failed, HTTP fallback retries also failed, and the
attempt was manually stopped without treating the environment failure as
capability evidence. The same corrected invocation was then run once with the
required network escalation and completed with exit status 0. Stdout and stderr
remained separate throughout.

The analyzer commands were:

```bash
PYTHONPATH=src python3 -m engineering_scope_guard init \
  --repo "$CANARY_ROOT/repo" \
  --state-dir "$CANARY_ROOT/analyzer-state"
PYTHONPATH=src python3 -m engineering_scope_guard snapshot \
  --config "$CANARY_ROOT/analyzer-state/config.json" --label before
PYTHONPATH=src python3 -m engineering_scope_guard snapshot \
  --config "$CANARY_ROOT/analyzer-state/config.json" --label after
PYTHONPATH=src python3 -m engineering_scope_guard analyze \
  --config "$CANARY_ROOT/analyzer-state/config.json" \
  --trace "$CANARY_ROOT/capture/stdout.jsonl"
```

`analyze` exited 0.

## Observed runtime shape

The successful stdout contained 9 JSONL records in this order:

1. `thread.started`;
2. `turn.started`;
3. `item.completed` / `agent_message`;
4. `item.started` / `command_execution` with `in_progress` status;
5. `item.completed` / `command_execution` with `completed` status and exit code 0;
6. `item.started` / `file_change` with one `add` change;
7. `item.completed` / `file_change` with one `add` change;
8. `item.completed` / `agent_message`;
9. `turn.completed` with a usage object.

The command items exposed `id`, `type`, `command`, `aggregated_output`, `status`,
and `exit_code`. The file-change items exposed `id`, `type`, `changes`, and
`status`; each change exposed `path` and `kind`. These are field-shape
observations only. Their raw values are not retained.

No `item.updated`, `turn.failed`, or top-level `error` record occurred in this
successful canary. That bounded absence is not evidence that Codex 0.150.1
cannot emit those records. No hook-emission conclusion is made by this canary.

## Analyzer result

V0 reported:

- overall, static, dynamic trace, snapshot, command/verification, and usage
  health: `healthy`;
- adapter: `codex-exec-json`;
- 9 recognized records, no malformed lines, unknown events, unknown item types,
  missing fields, invalid fields, or runtime errors;
- one observed command with completed status and exit code 0;
- one Codex file-change item;
- one completed turn with usage present;
- repository delta: 1 added text file, 0 deleted, 0 modified, and +1/-0 LOC
  under `strict-utf8-lines-v1`;
- no dependency, test-file, instruction-size, or candidate-infrastructure delta.

The sanitized fixture is
`tests/fixtures/traces/codex-0.150.1-live-exec-command-file-change-sanitized.jsonl`.
The raw provider capture is intentionally absent from the repository.

## Offline verification

Focused and full offline tests passed:

```bash
PYTHONPATH=src python3 -m unittest tests.test_trace -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src tests
```

Result: 20 focused trace tests and all 44 offline tests passed; compilation also
succeeded. The sanitized fixture parsed as `codex-exec-json` with 9 recognized
records, one file-change item, complete usage coverage, and no unmatched item
IDs. Two consecutive `analyze` invocations against the same snapshots and
sanitized fixture both exited 0; `cmp -s` returned 0 for both `events.jsonl` and
`report.md`, establishing byte-for-byte repeated output for this input.

## Limitations

- This is one minimal successful task, not exhaustive event-schema evidence.
- Absence of an event family in this run is not proof of unsupported behavior.
- The usage object's presence is established, but token values are intentionally
  removed.
- The command was a non-verification command, so this run establishes command
  observation but not a live verification-kind classification.
- The file-change item establishes one apply-patch-style add path only; it does
  not establish live modify/delete or every tool path.
- Network escalation was needed because the default command sandbox could not
  reach the provider. That is an environment fact, not a Codex capability
  result.
- Hook emission and its whole-task gaps require the separate hook canary.
