# Shadow Observability Gap Audit

**Track:** 1 — Shadow Observability Gap Audit

**Audit date:** 2026-08-29

**Current installed Codex:** `codex-cli 0.151.0`
**Execution boundary:** static/local inspection and existing sanitized fixtures
only; zero provider-authenticated coding requests, live canaries, evaluators, or
SWE-bench cells

## Research question and result

The audit asked whether the existing V0 Shadow Scope Analyzer exposes an
important, reproducible, decision-relevant coding-agent workflow fact that
native agent capabilities or existing tools do not already expose adequately,
while remaining local, low-overhead, and non-semantic.

It does not. V0 reliably produces privacy-bounded normalization of repository
structure and explicit observer-health diagnostics. Those are useful research
artifacts, but the underlying structural facts are already available through
Git, manifest inspection, and ordinary file tools. Current native agent and
OpenTelemetry surfaces expose richer command, tool, usage, compaction, turn,
and continuation events. Conversely, V0 does not expose the important proposed
facts—same-file rereads, repeated searches, identical-result repetition,
correction/state-recovery work, accepted outcomes, or tool-selection quality—
without missing data or semantic inference.

This is a negative Track 1 result, not evidence that observability research is
unimportant. It means the existing V0 does not earn Track 2 validity testing.

## Epistemic boundary

- **Direct fact:** present in supplied repository bytes or a supported event
  field, such as an entry hash, command exit code, or turn terminal event.
- **Derived deterministic fact:** computed from direct facts without judging
  intent, such as a file delta, identical command hash, or missing-field count.
- **Semantic or causal inference:** a claim such as unnecessary search,
  confusion, forgetting, bad tool choice, overengineering, or causation. V0
  does not establish these.

Repeated activity is therefore repetition only. A terminal turn is protocol
termination only. Fewer files or tokens are not a better outcome. Missing
evidence is not zero activity.

## Phase A — Current V0 capability inventory

This inventory was checked against
`src/engineering_scope_guard/{cli,doctor,repository,trace,report}.py` and the 44
focused tests in `tests/test_{cli,doctor,repository,trace}.py`. Code presence
without a current test/contract is not treated as reliable capability.

### CLI and local state

| Surface | Exact input/output | Fact type and coverage | False negatives or ambiguity | Privacy and target effect |
| --- | --- | --- | --- | --- |
| `doctor [--json]` | Runs only `codex --version`, `codex exec --help`, and `codex features list`; returns schema 1 capability health | Direct installed-command inspection. Current result: version `0.151.0`, `--json` present, hooks `stable` and enabled | Does not prove any event is emitted, provider/auth health, hook trust, or tool-path coverage | No target writes; no provider request. Diagnostics omit command stdout beyond bounded parsed fields |
| `init --repo --state-dir` | Writes local `config.json` schema 1 with resolved repository/state roots and default instruction paths | Direct configuration binding; state must resolve outside the target | One-time setup is not installation. Defaults include only root `AGENTS.md` and `AGENTS.override.md` | Writes only the external state directory; retains absolute local roots in local config |
| `snapshot --label before|after` | Writes snapshot schema 2 with entry path/kind/bytes/SHA-256 and optional line hashes; dependency records; warnings | Direct entry metadata plus normalized manifest facts. Stable-read mismatch fails closed | Excludes named cache/dependency directories; cannot attribute a delta to Codex; unsupported manifests are absent; special entries are unread | Reads target bytes transiently, never follows symlinks, writes only external state. Relative paths and hashes remain sensitive local metadata |
| `analyze --trace` | Validates both snapshots, parses one supplied JSONL trace, runs current static doctor, writes `events.jsonl` and `report.md` | Derived snapshot/trace facts and health | A supplied trace may be partial; analysis cannot prove capture completeness or task acceptance | Reads raw trace transiently; derived output omits model/agent text and raw command/output content; target remains read-only |

The workflow has no build backend, installer metadata, console entry point,
daemon, account, service, or telemetry path. It runs as
`PYTHONPATH=src python3 -m engineering_scope_guard`.

### Repository and structural observations

| Observation | Source and exact derived field/event | Type | Coverage and ambiguity |
| --- | --- | --- | --- |
| File delta | Snapshot `entries[]` → `structural_delta.files.{added,deleted,modified,counts}` | Derived | Reliable for scanned entry metadata across the two explicit boundaries. Git already supplies the underlying tracked-file fact; V0 also sees untracked/hidden regular entries outside excluded directories |
| LOC delta | `entries[].text.line_hashes` → `structural_delta.loc` under `strict-utf8-lines-v1` | Derived | Strict UTF-8, NUL-free regular files only; replacements are additions plus deletions; binary/symlink/special LOC is zero and separately counted |
| Entry kinds | `entries[].kind` → `loc.changed_entry_kinds` | Direct then derived count | Text/binary/symlink/special separation is deterministic, but not change quality |
| Dependency delta | Supported `package.json` and `pyproject.toml` tables → `dependency_delta.{added,removed,changed}` | Derived | npm sections and selected PEP 621/dependency-group shapes only. Names are normalized; specifications are hashed. No semantic “used dependency” analysis |
| Test-file delta | Changed path heuristic → `test_file_delta` | Derived | Recognizes conventional directory/name shapes. False negatives and false positives are possible for unconventional tests |
| Instruction-size delta | Configured relative paths → `instruction_delta.files[].{before_bytes,after_bytes,delta_bytes}` | Derived | Default root files only. It measures bytes changed, not persistent prompt size, discovery, precedence, load, relevance, or use |
| Infrastructure candidate | Added path → `infrastructure_delta.candidates[]` and neutral candidate event | Derived | Exact versioned basename/root-prefix/path rules only. A match is not evidence the artifact is excessive or unnecessary |
| Candidate events | Two runtime dependencies, substantial instruction growth, or a path-pattern match | Derived | Deterministic threshold crossing for manual review only; decision relevance and precision have not been validated against accepted outcomes |

Snapshots retain repository-relative paths, entry sizes, file hashes, per-line
hashes, normalized dependency names, and hashed dependency specifications. The
line hashes are needed by the current LOC algorithm but permit known-content
matching if shared. Command hashes likewise permit equality and possible
dictionary matching. These artifacts should remain local/private; this audit
documents the concern and does not authorize a storage redesign.

### Trace, hooks, commands, usage, and outcomes

| Observation | Source and exact field/event | Type | Coverage and ambiguity |
| --- | --- | --- | --- |
| Exec boundary | `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `error` → record counts, sequence diagnostics, and `turn_outcomes` | Direct/derived | Balances events within one supplied trace. V0 validates but does not retain the thread ID, timestamp turns, or link sessions across traces. Protocol completion is not accepted/correct outcome |
| Exec items | `item.started|updated|completed` with known item types | Direct count/validation | Unknown item types are counted and hashed. Apart from command summaries and file-change count, V0 discards item-specific payloads |
| Command/verification | Completed `command_execution.command/status/exit_code`, or hook `PostToolUse` for `Bash` → command SHA-256, program basename, verification kind, status, exit code | Derived | Exact observed commands only. Shell parsing/wrappers, non-shell verification tools, missing fields, partial traces, and hook gaps can miss activity. Hook commands get no real exit code in V0 |
| Repeated exact command | Duplicate `trace_summary.commands[].command_sha256` values | Derived but not aggregated | Equality is mechanically possible from output, but V0 has no repetition event/history and prior live evidence contains only one command. Changed/equivalent commands are not recognized |
| File-change item | Completed exec item type `file_change` → `file_change_items` count | Direct count | Does not retain paths/diffs or establish the final repository delta. Snapshots remain authoritative for final structure |
| Usage presence | Completed `turn.completed.usage` object → `usage_coverage` counts/status | Direct/derived coverage only | V0 discards input, cached-input, output, and reasoning-output token values. It cannot report fresh versus cached usage despite current native JSONL documenting those fields |
| Hook boundary | `SessionStart`, `SessionEnd`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `UserPromptSubmit`, subagent, and stop names | Direct count/validation | Hook-only traces always degrade. Hosted tools are absent, specialized paths may opt out, `SessionEnd` is not an immediate turn boundary, and transcript content is unstable. V0 retains Bash command summaries only, not general hook tool identities/arguments |
| Failures | `turn.failed`, `error`, command status/exit code, malformed/missing/invalid input diagnostics | Direct/derived | Shows protocol/runtime evidence when supplied. It cannot reliably classify timeout versus provider, transport, sandbox, command, or task failure |
| Coverage health | `coverage_health` plus trace/snapshot/command-verification/usage dimensions | Derived | Reliably reports what the current adapter received and recognized; it does not prove absent activity did not occur elsewhere |

The derived event contract is
`schema_name = engineering-scope-guard.event`, schema version 1. Outputs retain
repository-relative paths, normalized package names, hashes, bounded command
program names, verification categories, statuses, exit codes, counts, missing
field locations, and health. They do not copy raw source, command strings,
command output, prompts, model text, tool arguments, token values, credentials,
or absolute trace paths.

## Phase B — Codex observability revalidation

### Evidence lanes

| Lane | Current evidence | What it establishes |
| --- | --- | --- |
| Current documented capability | Official [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [hooks](https://learn.chatgpt.com/docs/hooks), and [App Server](https://learn.chatgpt.com/docs/app-server) checked 2026-08-29 | `exec --json` documents turn/item/error JSONL, command/file/MCP/web/plan items, and input/cached-input/output/reasoning usage. Hooks document lifecycle/local-tool events plus incomplete hosted/specialized coverage. App Server documents streamed turn/item events, token-usage updates, context-compaction items, tool/search details, diffs, terminal status, and persisted goal/thread controls |
| Current installed command surface | `codex-cli 0.151.0`; `codex exec --help`; `codex features list`; `codex app-server generate-json-schema --help` | `--json` is installed; hooks are `stable`/enabled; App Server and local schema generation are installed but the top-level command still labels App Server experimental |
| Current local source/schema inspection | `codex app-server generate-json-schema --experimental --out <temporary-directory>` | The generated 0.151.0 bundle includes turn, item, command/file/tool, compaction, token-usage, goal, and thread types. The temporary schema was not tracked and generation is not runtime-emission evidence |
| Previously live-verified evidence | Sanitized 0.150.1 minimal, command/file-change, and hook canaries under `tests/fixtures/traces/` and `docs/evidence/` | The exact prior version emitted the recorded families. It does not prove 0.151.0 behavior or repetition coverage |
| Fixture-only coverage | Broader static fixtures and 44 current focused tests | Parser, health, privacy, malformed/missing-input, deterministic delta, and target-immutability behavior. It is not live runtime evidence |
| Unknown/unverified live behavior | No 0.151.0 canary was authorized or run | Exact 0.151.0 emission across commands, reads/searches, hosted tools, hooks, compaction, continuation, failure, and usage remains unverified live for V0 |

The prior `CODEX_CAPABILITIES.md` installed-version heading was stale. It is now
updated without rewriting or relabeling the historical 0.150.1 canaries.

## Phase C — Decision-relevant observability matrix

The complete machine-readable matrix is
[`evidence/shadow-observability-matrix-2026-08-29.json`](evidence/shadow-observability-matrix-2026-08-29.json).
It uses the requested classifications as non-exclusive labels.

### Context and state continuity

- Instruction byte changes are partial and already available through Git/file
  inspection; V0 cannot prove instructions were loaded.
- Usage-object presence is partial; V0 discards the current native fresh/cached
  values.
- Supplied compaction hooks and turn boundaries are partial and degraded; native
  Codex exposes richer compaction/thread/goal surfaces.
- Repeated context load, post-transition rereads, and goal/checkpoint continuity
  are not observable in V0.
- Missing V0 coverage is reliably reported, but it is observer health rather
  than an incremental coding-workflow fact.

### Repeated work

- Exact observed Bash/exec command equality can be recovered from command
  hashes, but V0 does not aggregate it, has no live repetition canary, and the
  native trace preserves more useful command/order data.
- Same-file reads, repeated search queries, identical result fingerprints,
  correction rounds, abandoned work, and state recovery are unobservable.
- Retry intent/cause is not established by duplicate commands.

### Verification

- Observed shell test/lint/type/build shapes and exit codes are partial facts.
  Native logs, test output, CI, and check APIs are authoritative and simpler.
- “Missing verification evidence” is a coverage statement, not proof that no
  verification occurred.
- Turn completion is evaluator-independent termination, not correctness,
  acceptance, or sufficient verification.

### Tools

- V0 does not inventory exposed tools, general tool identities/arguments,
  output volume, or unused configured tools.
- It summarizes commands and counts file-change items; richer native and OTel
  traces already expose tool identity, order, arguments, status, and duration.
- Tool-selection error needs an objective expected-tool oracle. Invocation
  frequency alone cannot supply one.

### Outcome boundary

- V0 partially observes turn failure/completion and some command failures.
- It cannot observe accepted/correct outcome, user correction/rejection, or task
  success without external evidence or semantic interpretation.
- Therefore no observable repetition proxy can yet be linked to accepted
  outcome within existing V0.

No matrix entry survives as `potential_material_gap`.

## Phase D — Native and substitute comparison

This comparison concerns fact availability and burden, not commercial quality.

| Native/substitute | Current relevant fact surface | Comparison with existing V0 |
| --- | --- | --- |
| OpenAI Codex | JSONL command/file/tool/search/plan events and token fields; hooks for local lifecycle/tool/compaction events; App Server turns, diffs, command duration/output, MCP/dynamic/collab tools, web search, compaction, usage, goal, and thread state | Native surfaces contain the richer underlying events. V0 adds privacy-bounded reduction and coverage diagnostics, not a missing fact |
| Claude Code | Current [hooks](https://code.claude.com/docs/en/hooks-guide) include tool success/failure, instruction loading, file/config/cwd changes, compaction, tasks, subagents, and session boundaries; [OpenTelemetry monitoring](https://code.claude.com/docs/en/monitoring-usage) records interaction/LLM/tool/hook spans and retry attempts | Cross-agent comparison only; V0 has no Claude adapter. These surfaces show that general hook/trace observability is not distinctive |
| Gemini CLI | Current [OpenTelemetry telemetry](https://geminicli.com/docs/cli/telemetry/) can write locally and exposes agent/tool/API/token spans/metrics; detailed prompt/tool content is separately configurable | V0 has no Gemini adapter. Gemini already supplies standardized local workflow traces, with privacy settings requiring care |
| GitHub Copilot | Public-preview [Copilot SDK events](https://docs.github.com/en/copilot/how-tos/copilot-sdk/use-copilot-sdk/streaming-events) include persisted/ephemeral lifecycle, tool arguments/results, permissions, subagents, skills, timestamps, and token/tool totals | V0 has no Copilot adapter. The event surface is richer but preview/version-expiring |
| Cursor | Current [hooks](https://cursor.com/docs/hooks) cover session/tool/shell/MCP/read/edit/prompt/compaction/response events and a transcript path | V0 has no Cursor adapter. Hook availability does not establish stable complete traces, but it removes a general event-availability claim |
| Promptfoo | Current [tracing](https://www.promptfoo.dev/docs/tracing/) provides a built-in local OTLP receiver, tool/order/timing/error assertions, and explicit Codex SDK/App Server turn support | Strong substitute for general trace/eval plumbing. It requires instrumentation/configuration and can store sensitive span content; that trade-off does not make V0's narrower facts unique |
| Braintrust | Current [tracing](https://www.braintrust.dev/docs/instrument/trace-llm-calls) logs inputs/outputs, latency, token usage, and cost through SDK/provider instrumentation | Rich hosted/team substitute, but account/cloud/privacy overhead makes it unsuitable as a default local-private replacement |
| LangSmith | Current [observability model](https://docs.langchain.com/langsmith/observability-concepts) organizes traces/runs/threads and supports tool/token metadata through instrumentation | Rich general observability substitute with hosted/privacy/setup trade-offs; no need for V0 to duplicate it |
| Git/VCS, manifests, tests, and CI | Diffs, history, file/LOC changes, dependency changes, executed checks, status, and review evidence | Simplest authoritative route for every reliable structural/verification fact V0 currently reports |

Interfaces differ, so no cross-vendor completeness claim is made. Only Codex
support implemented and tested in V0 counts as current V0 functionality.

## Phase E — Full observer burden

### Measured local fixture burden

The existing `demo_before` → `demo_after` fixture was run once on Python 3.14.6
with current Codex static inspection. Portable wall-clock timing reported:

| Operation | Wall time |
| --- | ---: |
| `init` | 0.07 s |
| before snapshot | 0.06 s |
| after snapshot | 0.08 s |
| analysis, including three local doctor commands | 0.21 s |

The external state directory used 28 KiB by filesystem allocation. Logical
file sizes were 229 bytes (`config.json`), 2,422 and 4,115 bytes (snapshots),
4,270 bytes (`events.jsonl`), and 1,510 bytes/52 lines (`report.md`). A content
fingerprint taken after the fixture mutation and before observation matched
after snapshot+analysis: target-repository mutation was zero.

These numbers establish only small-fixture machine overhead. They do not
estimate real repository scan time, raw trace capture cost, Codex/provider
latency, or human review time.

### Workflow and privacy burden

- One-time per target: choose an external state directory and run `init`.
- Per observed task: coordinate a before snapshot, separately capture a Codex
  JSONL trace, take an after snapshot, run analysis, and read the report.
- Analyzer commands do not invoke a provider. The separately chosen trace
  capture can, but none was run in this audit.
- The socket-denial end-to-end test passed; it establishes no in-process socket
  activity for the tested analyzer workflow, not OS confinement of descendants.
- State retains absolute target paths in config and relative paths, hashes,
  dependency names, and command fingerprints in derived artifacts. Raw trace
  content remains wherever the user captured it. Sharing any of these needs a
  separate privacy review.
- Human interpretation burden is unknown and requires later user research. The
  52-line fixture report is only a mechanical size measure.

### Is the observer becoming more complex than the problem?

For current reliable structural facts, yes at the workflow level: Git plus
manifest/test/CI evidence is simpler and more authoritative. V0's measured
machine cost is small, so observer burden alone is not the terminal blocker.
The problem is that the extra steps yield normalization and coverage metadata,
not an important missing workflow fact.

## Phase F — Measurement-value candidates

Three near-candidates were challenged:

1. **Privacy-bounded structural normalization.** Observable and local, but Git,
   manifests, tests, and ordinary file tooling already supply the underlying
   facts. The normalized report has not shown separate decision value.
2. **Fail-visible coverage health.** Reproducible and useful for research
   integrity, but it describes the observer's evidence quality rather than an
   agent workflow fact that warrants accepted-outcome validity testing.
3. **Exact command repetition by hash.** Deterministic for observed commands,
   but not aggregated, not live-repetition-verified, incomplete across tool
   paths, and already visible in native/OTel traces. Its usefulness still
   requires semantics and accepted-outcome linkage.

None satisfies all eight survival conditions. There is no surviving fact to
carry into Track 2.

## Evidence-registry QA

The registry was checked for section, ID prefix, tier, vendor/independence,
peer-review/publication status, source type/date, applicability, and
expiry/revalidation agreement.

The known DORA 2025 defect was verified. The current DORA page and Google Cloud
announcement identify the 2025 report as Google Cloud/DORA observational survey
research based on nearly 5,000 respondents and qualitative data; it is not an
independent peer-reviewed study. The entry moved from the independent section
and `IND-014` identity to vendor research as `VEN-010`, retaining its Tier 2,
correlational, self-report, and non-causal limits. The canonical source now
points to the [2025 DORA report page](https://dora.dev/research/2025/dora-report/)
and records the 2025-09-23 publication date. No conclusion was changed.

No other material row showed a verified section/ID/tier contradiction. The
`TEC` rows remain in the explicitly mixed technical-systems section; their
individual Tier 3/4 and vendor/OSS status remains stated rather than inferred
from the prefix.

## Privacy conclusion

V0 remains local-first and does not mutate the target repository or send
analyzer telemetry. Its bounded outputs are meaningfully safer than copying raw
traces, but they are not anonymous. Relative and absolute paths, normalized
package names, per-file/per-line hashes, and command fingerprints can reveal or
enable matching of sensitive local metadata. The current storage is adequate
for private research with explicit handling; broader sharing or a new storage
architecture is not authorized.

## Track 1 red-team answers

1. **Are we measuring something users cannot already see?** No material fact.
   V0 normalizes facts users can obtain from Git, manifests, tests/CI, or native
   traces.
2. **Is the gap important, or merely technically interesting?** The coverage
   and privacy normalization is technically useful, but no incremental
   decision-relevant workflow gap survived.
3. **Could Git/VCS/tests/native logs answer it more simply?** Yes for every
   reliable structural and verification fact currently emitted.
4. **Does V0 actually observe the fact, or only a proxy?** It observes final
   structure and some protocol events. Repetition, recovery, correction, tool
   quality, and outcome value are proxies or absent.
5. **Does the fact require semantic interpretation before it becomes useful?**
   The proposed “unnecessary work” and tool-choice questions do.
6. **Is coverage too incomplete to support later recommendations?** Yes for the
   important repeated-work, state-continuity, tool, and accepted-outcome facts.
7. **Does measurement add meaningful workflow burden?** Yes: boundary
   coordination, external trace capture, state handling, and review. Machine
   overhead was low on the fixture, but total human burden is unknown.
8. **Would model/vendor changes invalidate the observation surface too
   quickly?** They already require revalidation: installed Codex advanced from
   0.150.1 to 0.151.0 in two days, while no new live canary was authorized.
9. **Is the remaining gap large enough to justify Track 2?** No. No candidate
   passed native/substitute, coverage, privacy, burden, and outcome-linkage
   challenges.
10. **If no end-user tool is ever built, did this audit still produce useful
    research?** Yes. It prevents duplicate implementation, records exact V0
    limits, corrects evidence classification, and establishes a defensible
    research-only stop.

## Limitations

- No 0.151.0 live canary was run, so current documented/installed surfaces are
  not presented as current live emission evidence.
- Official product pages establish capability, not completeness, efficacy, or
  usability. Preview/experimental surfaces can change.
- The burden measurement uses a tiny repository fixture and cannot estimate
  large-repository time, human review, or capture integration cost.
- No user study tested whether the compact report changes decisions.
- A future native interface could expose a new fact; that would require a fresh
  audit and separate authorization, not reinterpretation of this result.

## Terminal decision

**NO MATERIAL OBSERVABILITY GAP — RETAIN RESEARCH-ONLY**
