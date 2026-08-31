# Codex 0.150.1 hook-emission canary

**Date:** 2026-08-27

**Installed runtime:** `codex-cli 0.150.1` on `macos-aarch64`

**Evidence class:** development capability evidence, not efficacy evidence

## Bounded conclusion

A controlled `codex exec` invocation reached one local `Bash` tool path and
emitted `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`,
and `SessionEnd` command-hook records. The process exited `0`, the local command
item exited `0`, and the target repository was not modified by Codex.

The sanitized six-record fixture is accepted by V0 as `codex-hook-json` with no
missing or invalid fields. Its overall status remains `degraded` by design:
hook-only input cannot establish whole-task coverage.

This is evidence for the one controlled local shell path only. It is not evidence
that every tool path emits hooks.

## Installed interface and configuration

`codex features list` reported `hooks` as `stable` and enabled. The installed
0.150.1 parser accepted the following command-handler structure under
`--strict-config`. `$CANARY_ROOT` below replaces the real temporary absolute path
at the sanitization boundary.

```toml
[features]
hooks = true

[hooks]
SessionStart = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
SessionEnd = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
UserPromptSubmit = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
PreToolUse = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
PermissionRequest = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
PostToolUse = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
PreCompact = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
PostCompact = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
SubagentStart = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
SubagentStop = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
Stop = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
Interrupt = [{ hooks = [{ type = "command", command = "$CANARY_ROOT/hook-recorder.py $CANARY_ROOT/raw-hooks.jsonl" }] }]
```

The temporary recorder read one JSON object from stdin and appended one JSONL
record to a file outside the target repository. The canary used
`--dangerously-bypass-hook-trust` only because the isolated configuration was
temporary and its recorder source was created for this run. This does not
recommend bypassing hook trust for normal use.

## Commands and outcomes

The real temporary root was created with:

```bash
mktemp -d /private/tmp/esg-hook-canary.XXXXXX
```

The isolated home contained only the canary configuration, recorder, temporary
state, and a permission-preserving temporary copy of the existing local Codex
authentication file. Global Codex configuration and state were not changed. The
target was a separate temporary Git repository containing one untracked
`README.md` before and after the run.

Configuration validation:

```bash
CODEX_HOME="$CANARY_ROOT" \
  codex --strict-config doctor --summary --no-color --ascii
```

The configuration loaded successfully. Doctor separately reported authentication
missing before authentication was copied into the isolated home; that expected
preparation state was not treated as a hook result.

Frozen canary invocation, with stdout and stderr separated:

```bash
CODEX_HOME="$CANARY_ROOT" \
  codex --strict-config --dangerously-bypass-hook-trust \
  -m gpt-5.6-sol -c 'model_reasoning_effort="medium"' \
  -a never -s workspace-write exec --json \
  -C "$CANARY_ROOT/target" \
  '<sanitized fixed prompt requiring exactly one harmless shell call>' \
  > "$CANARY_ROOT/stdout.jsonl" \
  2> "$CANARY_ROOT/stderr.txt"
```

The first sandboxed attempt could not resolve the provider hostname. The outer
command runner reached its 30-second bound without capturing a Codex exit status.
That run emitted only `SessionStart` and `UserPromptSubmit`, never reached a tool,
and is classified as an environment/provider-path failure rather than tool-hook
absence. The same frozen invocation was rerun with approved network access and
exited `0`.

The successful stdout contained nine records:

| Exec JSONL family | Count |
| --- | ---: |
| `thread.started` | 1 |
| `turn.started` | 1 |
| `item.started` | 1 |
| `item.completed` | 5 |
| `turn.completed` | 1 |

One completed item was `command_execution` with status `completed` and exit code
`0`. The terminal turn carried a usage object; its token counts were not retained.
Successful stderr contained one non-event diagnostic line and no provider error.

## Hook emission result

All twelve installed/configurable families were enabled for the same recorder.

| Hook family | Successful run | Interpretation |
| --- | ---: | --- |
| `SessionStart` | 1 | Observed at process/session startup. |
| `UserPromptSubmit` | 1 | Observed before sampling; prompt content removed. |
| `PreToolUse` | 1 | Observed for the local `Bash` call. |
| `PostToolUse` | 1 | Observed after the local `Bash` call. |
| `Stop` | 1 | Observed after the final assistant response. |
| `SessionEnd` | 1 | Observed when this non-interactive process closed. |
| `PermissionRequest` | 0 | The command needed no approval under this run; not exercised. |
| `PreCompact` | 0 | No compaction occurred; not exercised. |
| `PostCompact` | 0 | No compaction occurred; not exercised. |
| `SubagentStart` | 0 | No subagent was requested; not exercised. |
| `SubagentStop` | 0 | No subagent was requested; not exercised. |
| `Interrupt` | 0 | No interrupt occurred; not exercised. |

The zeroes above mean absent on this controlled path, not unsupported. Hosted
tools, specialized local paths, command continuation, approval, compaction,
subagent, and interrupt behavior remain outside this canary.

Observed minimum shapes were:

- common lifecycle context: session, working directory, hook name, and optional
  model/permission/turn fields;
- tool context: `tool_name = "Bash"`, tool-use identifier, and a `tool_input`
  object with a `command` field;
- post-tool context: the same tool context plus a string `tool_response`;
- stop context: a boolean `stop_hook_active` and string assistant-message field;
- session-end context: `reason = "other"` for this invocation.

## Sanitization boundary

Raw hook JSONL, exec JSONL, stderr, temporary authentication, transcript/state,
the target repository, and the recorder were kept only under `$CANARY_ROOT` and
were not committed. The committed fixture replaces real session, turn, and
tool-use identifiers with synthetic fixture labels; replaces absolute paths,
model identity, prompt, command, tool output, and assistant text with synthetic
or redacted values; and omits provider response content and token counts. No
credential or private value is present.

The fixture preserves only event names, field presence/types, neutral lifecycle
values needed by the parser, the local `Bash` tool category, and the observed
six-record order. V0 hashes the redacted command placeholder and does not copy it
as raw command text; its bounded command summary retains only the synthetic
placeholder's program basename.

## Adapter health and limitations

For `tests/fixtures/traces/codex-0.150.1-live-hooks-sanitized.jsonl`, V0 reports:

- adapter: `codex-hook-json`;
- status: `degraded`;
- recognized records: 6;
- missing fields: 0;
- invalid fields: 0;
- command-observation problems: 0;
- usage coverage: `unavailable`.

The degradation is expected and material. A hook-only trace cannot prove complete
task coverage; hosted tools do not use local tool hooks; specialized local paths
may bypass the default hook path; and `SessionEnd` is not a reliable immediate
turn boundary in every lifecycle. The canary establishes usable secondary-adapter
evidence for one local command, not a replacement for `codex exec --json`.

## Offline verification

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_trace.TraceTests.test_sanitized_live_hook_shape_is_accepted_as_explicitly_degraded \
  -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

The focused test passed, all 43 repository tests passed, and compilation passed.
Two consecutive `parse_trace` calls over the sanitized fixture returned equal
Python values byte-for-byte when serialized deterministically.
