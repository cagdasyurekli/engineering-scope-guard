# Codex 0.150.1 V0 capability-coverage synthesis

**Evaluation date:** 2026-08-27

**Installed runtime:** `codex-cli 0.150.1`

**Evidence class:** development capability evidence, not efficacy evidence

**Goal scope:** the active capability gate in `docs/CURRENT_GOAL.md`

## Bounded recommendation

**GO to propose, but not start, the next bounded experiment.** On Codex 0.150.1,
V0's repository snapshots and primary `codex exec --json` adapter measure the
minimum structural and trace signals required by the active goal. The conclusion
is conditional on preserving the verified boundary: snapshots are the authority
for repository deltas, exec JSONL is the primary trace adapter, and command hooks
remain secondary and explicitly degraded.

This record does not show that the signals are actionable in normal work, that a
policy changes agent behavior, or that any intervention is beneficial. Those are
questions for a separately proposed experiment under
[`EVALUATION_PROTOCOL.md`](../EVALUATION_PROTOCOL.md). No experiment definition,
candidate policy, outcome, guardrail, exclusion, timeout rule, analysis method,
or public claim is changed here.

## Evidence boundary

The installed-runtime evidence consists of two controlled disposable-repository
canaries and their sanitized fixtures:

- [`codex-0.150.1-exec-command-file-change-canary.md`](codex-0.150.1-exec-command-file-change-canary.md)
  records one successful command and one added-file change item emitted by
  `codex exec --json`;
- [`codex-0.150.1-hook-emission-canary-2026-08-27.md`](codex-0.150.1-hook-emission-canary-2026-08-27.md)
  records six hook families around one local `Bash` path.

The committed fixtures remove provider prompts and responses, source contents,
raw command text and output, real identifiers, absolute paths, token counts,
credentials, and private values. Synthetic identifiers, redaction markers,
field names/types, lifecycle values, and the synthetic relative path
`canary.txt` preserve only the shape needed by the parser. Raw captures,
authentication material, recorder code, temporary state, and disposable target
repositories were not committed.

The wider structural and malformed-input evidence is offline. It uses only
`tests/fixtures/`, source-defined measurement contracts, and the local test
suite. Unobserved live shapes are described as **no direct trace**, never as
unsupported or as proof the activity did not occur.

## Commands and observed outcomes

The canary reports preserve the exact command structure, with only the random
temporary suffix and sensitive prompt bytes redacted. The exec canary ran:

```bash
CODEX_HOME="$CANARY_ROOT/codex-home" codex exec --json \
  --ephemeral --ignore-user-config --ignore-rules --approve-for-me \
  -m gpt-5.6-sol -c 'model_reasoning_effort="medium"' \
  -C "$CANARY_ROOT/repo" "$CANARY_PROMPT" \
  > "$CANARY_ROOT/capture/stdout.jsonl" \
  2> "$CANARY_ROOT/capture/stderr.txt"
```

After an initial locally rejected `--approve-for-me -s workspace-write`
combination (exit `2`, no provider call) and one sandboxed provider-connectivity
failure that was stopped without a capability inference, the corrected,
network-authorized run exited `0`. Its analyzer `init`, two `snapshot` commands,
and `analyze` command all exited `0`; the exact analyzer commands are recorded
in the linked exec-canary report.

The hook canary ran:

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

Its first sandboxed attempt did not reach a tool because provider name
resolution failed; this is environment evidence only. The identical approved
network run exited `0`. The exact configuration-validation command and hook
configuration are recorded in the linked hook-canary report.

Independent synthesis checks from the repository root were:

| Command | Exit | Result |
| --- | ---: | --- |
| `codex --version` | 0 | `codex-cli 0.150.1`; stderr also warned that PATH aliases could not be created in the restricted environment. |
| `PYTHONPATH=src python3 -m engineering_scope_guard doctor` | 0 | Static capability `healthy`; exec JSONL available; hooks stable/enabled. Doctor made only its fixed local inspections. |
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | 0 | 44 tests passed. |
| `PYTHONPATH=src python3 -W error -m compileall -q -f src tests` | 0 | Compilation passed with warnings treated as errors. |
| Standard fixture demo from `docs/CODEX_CAPABILITIES.md`, followed by a second identical `analyze` and `cmp -s` of `events.jsonl` and `report.md` | 0 | Both byte comparisons passed. SHA-256: events `01aca3b8abfeec49248258cf18210d9feebb380cdbefca4dad51ff21a62decf3`; report `8e0074234c30e6eb24696638f87d6c54916297363efd2782cf3d12dc86932e1b`. |
| The same demo snapshots analyzed twice with `tests/fixtures/traces/codex-0.150.1-live-exec-command-file-change-sanitized.jsonl`, then compared with `cmp -s` | 0 | Both byte comparisons passed. SHA-256: events `f29feb6c18d405f19c01ae8394bae1187f6bd1de246e6b0a9bfb68815ce856cc`; report `5ac728e65cd53e263eac21612dc529dbcccb80c2f3f30c0a167b5ac3105aa2e5`. |
| Two deterministic `parse_trace` serializations for each new sanitized fixture | 0 | Both pairs were equal. Exec: healthy, 9 recognized, 1 command, 1 file-change item, healthy usage. Hooks: degraded, 6 recognized, 1 command, 0 file-change items, usage unavailable. |
| Forward and reverse `compare_snapshots` over the existing demo fixtures, repeated in-process | 0 | Repeated JSON was equal. Forward: 2 added, 3 modified, +15/-2 LOC, 2 dependencies added, 1 test added, 1 instruction change, 1 infrastructure candidate. Reverse: 2 deleted, 3 modified, +2/-15 LOC, 2 dependencies removed, 1 test deleted, 1 instruction change. |

The full compound demo and repeat commands intentionally used disposable
`/private/tmp/esg-synthesis-demo.*` state. They did not modify a target
repository under observation or make a provider call.

## Capability coverage

| Dimension | Evidence | Disposition | Material limitation |
| --- | --- | --- | --- |
| Trace boundary/schema | Live exec fixture: `thread.started`, balanced turn start/terminal, item start/completion, 9 recognized records, no missing/invalid fields or unmatched item IDs. Malformed, unknown, missing-boundary, and unsupported-input cases pass offline tests. | **GO** | One successful live shape is not an exhaustive schema. Unknown future shapes degrade visibly and are not treated as zero activity. |
| Repository snapshots | Live exec canary measured 1 added text file and +1/-0 LOC. Forward/reverse offline snapshots and the full end-to-end test cover both directions, stable reads, binary/symlink/special separation, manifest warnings, and target-tree immutability. | **GO** | Snapshot facts describe the before/after boundary, not which Codex tool caused each change. Files changing during snapshot make the snapshot fail rather than silently continue. |
| Command/verification observation | Live exec and live hook canaries each yielded one bounded command summary. The representative exec fixture and classification tests cover test/lint/type/build/other recognition and substring false positives. | **GO** | Applies when command records are observable. The live command classified as `other`; verification-kind coverage beyond that is offline fixture evidence. Raw command text is intentionally discarded, and missing/invalid command fields degrade coverage. |
| Usage observation | Live exec emitted one `turn.completed` with a usage object; V0 reported healthy presence coverage. Offline tests distinguish completed-without-usage as degraded and failed-turn-only usage as unavailable. | **GO** | Applies to presence/coverage. Token values are intentionally removed from sanitized evidence. This does not support token totals, billed cost, or cache analysis. Hook-only usage is unavailable. |
| Codex file-change items | Live exec emitted one started/completed `file_change` item with one add change; V0 counted one completed item. | **GO** | Applies to item observation. No direct trace for live modify/delete items, every file-edit tool path, or reconciliation between item paths and final snapshots. The structural snapshot remains authoritative. |
| Hook emission | One local `Bash` path emitted `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, and process-close `SessionEnd`; the six sanitized records parse without missing/invalid fields. | **GO** | Applies only as a secondary degraded adapter. No direct trace for permission, compaction, subagent, interrupt, hosted-tool, specialized-tool, or command-continuation paths. Hook-only input cannot prove complete task coverage, and `SessionEnd` is not generally an immediate turn boundary. |

## Minimum-signal matrix

`GO` means the bounded V0 fact is measured reliably enough on the stated
interface to carry into a proposed experiment. It does not mean the signal is a
valid proxy for overengineering or predicts a useful intervention.

| Minimum signal | Evidence source | Disposition | Limitation |
| --- | --- | --- | --- |
| Added, deleted, and modified file counts | Source uses deterministic path-set differences and content/type metadata. Standard demo observed 2 added/3 modified; reversed existing snapshots observed 2 deleted/3 modified; repeat output matched. | **GO** | Snapshot-boundary fact only; excluded cache directories are intentionally outside measurement. |
| Added/deleted LOC under `strict-utf8-lines-v1` | Source fixes strict UTF-8, NUL-free files, `splitlines(keepends=True)`, and deterministic sequence diff. Demo observed +15/-2; reverse observed +2/-15; binary/symlink separation tests passed. | **GO** | Binary, symlink, and special entries contribute zero LOC; replacements count as additions plus deletions. |
| Dependency additions, removals, and specification changes | Forward/reverse demo observed 2 additions/2 removals. `test_structural_dependency_test_instruction_and_infrastructure_deltas` and `test_pyproject_standard_tables_and_name_normalization` cover hashed specification changes and supported npm/Python tables. | **GO** | Only supported `package.json` and PEP 621/dependency-group `pyproject.toml` shapes are measured; parse/type problems surface as snapshot warnings. Raw specifications are hashed. |
| Test-file changes | Forward/reverse demo observed one added and one deleted test. `is_test_file` applies the same deterministic classifier to added/deleted/modified path sets. | **GO** | Modified-test classification follows the shared path rule but has no distinct installed-runtime canary. This is path-shape evidence, not test relevance or quality. |
| Instruction-file size changes | Demo and reverse each observed one configured `AGENTS.md` byte-size change; the repository test covers thresholded growth. | **GO** | Only configured instruction paths are measured; byte growth is not inherently harmful. |
| Versioned candidate-infrastructure path matches | Demo observed `Dockerfile`; the frozen path test covers positive and negative cases for `candidate-infrastructure-paths-v1`. | **GO** | Added paths only; the match is a neutral candidate-review event, not a semantic necessity judgment. |
| Commands and verification kinds when observable | Live exec observed one completed command with exit `0`; live hook observed one local command; representative fixture classified a test command and unit tests cover supported kinds/false positives. | **GO** | Live evidence establishes `other`, not every verification kind. Hosted/specialized paths can be absent from hooks; missing command fields are visible degradation. |
| Codex file-change item observation | Live exec canary produced one completed item and V0 counted it. | **GO** | Add-only live shape; no direct trace for modify/delete or all write paths. It is not the structural-delta authority. |
| Turn terminal and usage coverage | Live exec had one balanced completed turn with a usage object; offline tests cover failed turns and missing usage. | **GO** | Presence only; token counts were removed. No direct trace for every terminal/error combination. |
| Hook emission | Six families observed around one local `Bash` call and accepted without malformed fields. | **GO** | Applies only to the observed local path. The other configured families were not exercised and therefore have no direct trace. |
| Hook-only whole-task coverage | Parser always marks hook-only input degraded; source and canary limitations identify hosted-tool, specialized-path, continuation, and session-boundary gaps. | **NO-GO** | Hooks must not replace exec JSONL or repository snapshots as the complete task evidence source. |

## Unavailable and inconsistent evidence

- There is no direct trace for live modify/delete file-change item shapes, every
  verification kind, all installed tool paths, approval hooks, compaction hooks,
  subagent hooks, interrupts, or command continuation.
- Hook emission is path-dependent. Zero records for an unexercised family do not
  establish that the family is unsupported.
- A hook-only trace cannot establish turn-terminal or usage coverage and must
  remain degraded even when its individual records are well formed.
- Sanitized usage proves only that an object was present; it cannot support token
  or cost claims.
- The canaries are scoped to Codex 0.150.1 on 2026-08-27. A materially changed
  Codex version requires revalidation.
- Provider/DNS failures from the restricted outer sandbox were execution
  blockers. They were not classified as missing Codex capabilities.

## Decision boundary

The evidence supports a proposal for the next experiment because every minimum
structural signal has deterministic local evidence, the primary exec trace has
healthy live boundary/command/file-change/usage evidence, and incomplete inputs
fail visibly. The single NO-GO is deliberate: hook-only whole-task coverage is
not reliable and must remain outside the proposed experiment's evidence
authority.

Starting an experiment, freezing its design, changing policy wording, or making
an efficacy claim requires separate goal/authority. `docs/CURRENT_GOAL.md`
remains active and is not marked complete by this synthesis task.
