# Codex Observation Capabilities for V0

**Checked:** 2026-08-29

**Installed CLI:** `codex-cli 0.151.0`

This document separates current documentation, the current installed command
surface, historical 0.150.1 live evidence, fixture-driven adapter coverage, and
unknown 0.151.0 runtime behavior. It does not infer emission from documentation
or claim that every installed tool path emitted an event.

## Supported interfaces

The V0 primary adapter ingests the JSONL written by `codex exec --json`.
Current installed-version inspection confirmed:

- `codex --version` reports `codex-cli 0.151.0`;
- `codex exec --help` exposes `--json`;
- `codex features list` reports `hooks` as `stable` and enabled.

This is **static command-surface evidence**. The analyzer's `doctor` subcommand
repeats those three local inspections without running Codex, authenticating, or
contacting a provider.

## Historical live canaries

On 2026-08-27, the following installed-runtime canary completed with exit status
zero on Codex 0.150.1:

```bash
codex exec --json --ephemeral --skip-git-repo-check --ignore-user-config \
  -s read-only -C /private/tmp \
  "Do not use tools. Reply exactly CANARY_OK."
```

Its JSONL stdout sequence was:

1. `thread.started`;
2. `turn.started`;
3. `item.completed` with an `agent_message` containing `CANARY_OK`;
4. `turn.completed` with usage data.

The sanitized fixture
`tests/fixtures/traces/codex-0.150.1-live-minimal-sanitized.jsonl` preserves that
event family without the real thread identifier or token counts. Unrelated
rollout state-database warnings appeared on stderr and were not treated as JSONL
events.

This live canary verifies minimal 0.150.1 emission and adapter acceptance. The
separately documented 0.150.1 command/file-change and hook canaries verify only
their sanitized recorded shapes. None establishes 0.151.0 live behavior,
repeated-operation coverage, or complete tool coverage. Track 1 explicitly
prohibited a new live canary, so none was run.

OpenAI's current official non-interactive-mode documentation describes JSONL
event categories including `thread.started`, turn events, `item.*`, and `error`,
with command execution, file change, MCP tool, web search, and plan item types.
Its example usage object separates input, cached input, output, and reasoning
output:
<https://learn.chatgpt.com/docs/non-interactive-mode>.

Command-hook JSON is accepted as a secondary adapter. Official hook documentation
describes lifecycle events and local tool coverage:
<https://learn.chatgpt.com/docs/hooks>.

The current official App Server documentation and the locally generated 0.151.0
schema expose a richer native surface: turn terminal status and diffs; command
cwd/status/output/exit/duration; file changes; MCP, dynamic, collaboration, and
web-search items; `contextCompaction`; thread token-usage updates; and persisted
thread goals/continuation. The installed top-level command labels App Server
experimental, and some methods/fields require explicit experimental opt-in. V0
does not ingest App Server or generated schemas:
<https://learn.chatgpt.com/docs/app-server>.

## What V0 actually retains

V0 validates exec turn/item boundaries, records bounded command hashes,
program basenames, verification categories, command status/exit code,
file-change item counts, runtime-error/turn-terminal counts, and only the
presence or absence of a completed-turn usage object. It deliberately discards
raw command strings, tool arguments/results, prompts, model text, and token
values.

Consequently, current V0 does **not** report fresh versus cached tokens, MCP or
web-search identity/query, general tool order, same-file rereads, repeated
searches, tool output volume, compaction-linked rereads, configured-but-unused
tools, correction/state-recovery work, or accepted/correct outcomes. Duplicate
observed command hashes can be compared mechanically, but V0 has no repeated-
command event/history and no live repeated-command evidence.

## Known coverage gaps

- Hosted tools such as WebSearch do not use local tool hooks.
- Specialized local tool paths may opt out of the default hook path.
- `write_stdin` does not emit another pre-tool hook for an existing command.
- `SessionEnd` may be delayed until close, archive, deletion, or idle cleanup; it
  is not an immediate turn boundary.
- `transcript_path` is convenient but its content is not a stable interface. V0
  does not read it.
- Hook-only traces therefore always report degraded whole-task coverage.
- Unknown or malformed event shapes are surfaced as degradation rather than
  interpreted as zero activity.
- Current 0.151.0 event emission is documented and installed but unverified live
  in this goal.
- App Server, native goals, and account usage are not V0 inputs. Account usage
  also requires authenticated service access and was not queried.

## Offline fixture demo

The repository also includes representative Codex 0.150.1 command/file-change
JSONL and hook records under `tests/fixtures/traces/`. Those broader fixtures test
parser behavior without provider access and are not presented as 0.151.0 live
capture evidence.

Run a complete before/after demo from the repository root:

```bash
demo_root="$(mktemp -d)"
cp -R tests/fixtures/demo_before "$demo_root/target"

PYTHONPATH=src python3 -m engineering_scope_guard init \
  --repo "$demo_root/target" --state-dir "$demo_root/state"
PYTHONPATH=src python3 -m engineering_scope_guard snapshot \
  --config "$demo_root/state/config.json" --label before

cp -R tests/fixtures/demo_after/. "$demo_root/target"

PYTHONPATH=src python3 -m engineering_scope_guard snapshot \
  --config "$demo_root/state/config.json" --label after
PYTHONPATH=src python3 -m engineering_scope_guard analyze \
  --config "$demo_root/state/config.json" \
  --trace tests/fixtures/traces/codex-0.150.1-exec.jsonl
```

The state directory then contains:

- `snapshots/before.json` and `snapshots/after.json`;
- deterministic derived `events.jsonl`;
- a concise `report.md` for manual review.

The demo should report two added files, three modified files, two added runtime
dependencies, one new test file, one instruction-size change, and one new
candidate infrastructure/config path match. It should produce candidate review
events for the two runtime dependencies and the Dockerfile without declaring
either objectively bad.

## Health and exit semantics

| Exit | Meaning |
| ---: | --- |
| `0` | Healthy observation or successful state operation |
| `1` | Fatal configuration, filesystem, parsing, or I/O error |
| `2` | Output produced with visibly degraded coverage |
| `3` | Required observation interface unsupported or no recognized trace records |

Static `doctor` health and dynamic trace health are recorded separately in the
derived coverage event and human-readable report.

The coverage event also reports four capability-specific dimensions:

- `trace`: boundary/schema health for recognized records;
- `snapshot`: repository-read health and visible manifest/filesystem warnings;
- `command_verification`: whether bounded command/verification summaries were
  observed, degraded, or unavailable;
- `usage`: whether completed turns carried usage objects. A valid `turn.failed`
  closes a turn without being treated as malformed; usage for a failed-only trace
  is explicitly unavailable.

Unavailable optional command or usage evidence does not make otherwise valid
trace boundaries malformed. Hook-only traces remain degraded for the separate
whole-task-coverage reasons above.

## Deterministic measurement and output contracts

Repository snapshots use schema version 2. Derived JSONL records use
`schema_name = engineering-scope-guard.event` and schema version 1. The coverage
record distinguishes:

- **source:** repository bytes and supported Codex records read locally;
- **normalized:** repository-relative POSIX paths, normalized dependency names,
  and SHA-256 identifiers/fingerprints;
- **derived:** deltas, bounded summaries, coverage health, and candidate review
  events.

LOC definition `strict-utf8-lines-v1` counts lines only for regular files that
decode as strict UTF-8 and contain no NUL byte. It uses Python
`splitlines(keepends=True)` and a deterministic sequence diff; replacements count
as deletions plus additions. Binary files, symlinks, and special filesystem
entries contribute zero LOC and are counted separately by changed entry kind.
Symlink targets are recorded as metadata and are never followed.

Candidate infrastructure/config paths use the versioned
`candidate-infrastructure-paths-v1` path-pattern set. A match produces the
neutral `candidate_infrastructure_artifact` review label plus the matched pattern
identifier. It is a path-shape signal, not a judgment that the artifact is
unnecessary. Version 1 matches the basename `Dockerfile` or `Dockerfile.*`
anywhere; a small exact
basename set for compose, CI, deployment, and chart configuration anywhere;
`.tf` extensions anywhere; the root-level `.circleci/`, `terraform/`, `k8s/`,
`kubernetes/`, and `helm/` directory prefixes; and YAML files that are direct
children of the root-level `.github/workflows/` directory. Pattern identifiers
encode these basename-anywhere, root-prefix, and direct-child semantics.

Persistent `init` configuration is retained because the workflow crosses
separate commands: it binds both snapshots and analysis to one resolved target
and revalidates that the state directory remains outside that target each time.
The repository-relative paths stored in snapshots, events, and reports are
sensitive local metadata. They are not transmitted, but local access controls
and sharing decisions still matter.

V0 is intentionally run directly with `PYTHONPATH=src python3 -m
engineering_scope_guard`; it has no build backend, installer metadata, or console
entrypoint. Packaging was not required by the V0 acceptance criteria and would
add an unused build dependency and a second invocation path.

The analyzer's `init`, `snapshot`, and `analyze` paths do not use network APIs,
as covered by the Python audit-hook socket-denial test. `doctor` launches only
the three fixed local inspection commands. A Python audit hook does not confine
descendant processes at the operating-system level, and the separate `codex
exec` capture command may contact a provider under the user's Codex settings.

Derived dependency records retain normalized package names and SHA-256
fingerprints of specifications. They do not copy source/version strings, which
can contain private registry locations or embedded credentials. Snapshots also
retain per-file and per-line hashes, and command summaries retain unsalted
command hashes. These values can support equality or known-content matching and
must remain private even though they omit raw content.

## Track 1 disposition

The current capability and substitute audit is recorded in
`SHADOW_OBSERVABILITY_GAP_AUDIT.md`. V0 adds privacy-bounded normalization and
fail-visible observer health, but no important underlying workflow fact that
current native/substitute routes fail to expose adequately. Important proposed
repetition, continuity, selection, and accepted-outcome facts remain outside
V0's reliable surface.
