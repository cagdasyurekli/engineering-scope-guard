# Competitor and Substitute Map

**Review date:** 2026-08-29

**Purpose:** OSS usefulness and non-duplication analysis, not commercial moat

## Decision rule

For every proposed capability ask:

1. Does a native or existing tool already provide it?
2. Is the remaining gap measurement/evaluation rather than implementation?
3. Can Scope Guard test whether the user's chosen capability helps without
   replacing it?

Capability existence is established from official documentation. Efficacy is
not inferred from a product page.

## Native coding-agent capabilities

| Product | Current relevant capabilities | What Scope Guard should not rebuild | Possible complement, if later evidenced |
| --- | --- | --- | --- |
| OpenAI Codex / GPT-5.6 platform | Current [`exec --json`](https://learn.chatgpt.com/docs/non-interactive-mode) documents turns, command/file/MCP/web/plan items, and fresh/cached/output/reasoning usage; [hooks](https://learn.chatgpt.com/docs/hooks) expose local tool and compaction lifecycle with explicit gaps; [App Server](https://learn.chatgpt.com/docs/app-server) exposes rich turn/item/diff/tool/search/compaction/usage/goal/thread state. | Model/router/compactor/multi-agent runtime, prompt optimizer, generic trace protocol, or hosted eval platform. | Consume only supported, privacy-bounded facts after a specific native gap survives. Existing V0 adds reduction/coverage health, not a missing underlying fact. |
| Claude Code | Current [hooks](https://code.claude.com/docs/en/hooks-guide) include instruction loading, tool success/failure, file/config/cwd changes, tasks, subagents, compaction, and session boundaries; [OpenTelemetry monitoring](https://code.claude.com/docs/en/monitoring-usage) records interaction/LLM/tool/hook spans and retries. | Memory/context dashboard, compactor, skill/MCP framework, subagent/team orchestrator, hook system, telemetry schema, or generic review agent. | Cross-agent comparison only after implementing and verifying a Claude adapter under a future goal; V0 currently has none. |
| Gemini / Gemini CLI | Gemini CLI's current [OpenTelemetry surface](https://geminicli.com/docs/cli/telemetry/) can write locally and exposes agent/tool/API/token metrics and traces; detailed content capture is separately configurable. | Large-context store, caching service, generic instruction system, another CLI agent, or telemetry framework. | Product/version-specific comparison only after a separately authorized and verified adapter; V0 currently has none. |
| GitHub Copilot | Repository/path instructions and customization remain native. The public-preview [Copilot SDK event stream](https://docs.github.com/en/copilot/how-tos/copilot-sdk/use-copilot-sdk/streaming-events) exposes persisted/ephemeral session, tool, permission, subagent, skill, timestamp, and usage events. | Instruction delivery, prompt/custom-agent/skill framework, code review, GitHub orchestration, or event-log layer. | Preview surfaces are version-expiring. V0 has no Copilot adapter and may not claim this support. |
| Cursor | Current [hooks](https://cursor.com/docs/hooks) cover session, tool, shell, MCP, file read/edit, prompt, compaction, subagent, and response stages. | IDE, code index, rule/memory system, plan/subagent/review product, hooks, or integrations hub. | Import only user-owned derived metrics through a stable supported interface after separate verification; V0 has no Cursor adapter. |

## Context, retrieval, and configuration substitutes

| Substitute | Capability | Non-duplication decision |
| --- | --- | --- |
| [Augment Context Services](https://docs.augmentcode.com/context-services/overview) | Semantic search over code/docs through MCP, SDK, CLI, and connectors. | Do not build a general semantic repository index. A future study can test whether retrieval improves task outcome/work on a user's workload. |
| [Continue](https://docs.continue.dev/reference) | OSS/configurable agents with models, rules, context providers, tools, and MCP. | Do not create another general configurable agent shell. |
| Cursor Rules/Memories/Skills | Always-on, path-scoped, agent-requested, and on-demand context mechanisms. | Do not create a parallel rule format; test load scope and outcome where observable. |
| AGENTS.md / CLAUDE.md / GEMINI.md / Copilot instructions | Cross-product persistent repository guidance with differing discovery/precedence. | Keep repository guidance concise and product-correct; do not claim universal benefit. An auditor may detect duplication/staleness, but recommendation efficacy needs a test. |
| Native file/search/IDE indexes | Grep/ripgrep, language servers, code indexes, repository search. | Prefer existing deterministic navigation. Require a demonstrated failure before adding Graph/RAG infrastructure. |

## Token and work substitutes

| Substitute | Capability | Non-duplication decision |
| --- | --- | --- |
| [RTK](https://github.com/rtk-ai/rtk) | Deterministic compression of common shell output. | Do not build another command-output compressor. Evaluate diagnostic retention and accepted outcomes, not advertised percentages alone. |
| Provider prompt caching | Discounted/reused stable prefixes with product-specific pricing/retention rules. | Do not infer lower total work from cached tokens; record fresh/cached separately. |
| Native compaction/context inspection | Product-managed history reduction and context breakdown. | Do not build a universal compactor. Measure continuity failures only through supported interfaces. |
| Tool search/deferred schemas | Loads relevant tool definitions on demand. | Do not build a model-based router without a proven recall/selection gap. Deterministic catalog inventory may be enough. |

## Evaluation and observability substitutes

| Substitute | Capability | Non-duplication decision |
| --- | --- | --- |
| [Promptfoo](https://www.promptfoo.dev/docs/tracing/) | OSS eval/red-team workflows with a built-in local OTLP receiver, tool/order/timing/error assertions, and explicit Codex SDK/App Server turn support. It may store sensitive span content locally unless configured carefully. | Strong substitute for general trace/eval plumbing. Do not rebuild it; privacy-bounded derived imports would require a demonstrated question and separate goal. |
| [Braintrust](https://www.braintrust.dev/docs/instrument/trace-llm-calls) | Hosted tracing logs inputs/outputs, latency, token usage, and cost through provider/framework instrumentation. | Do not duplicate hosted team observability or send private traces by default. Account/cloud burden is a real trade-off, not evidence of a V0 fact gap. |
| [LangSmith](https://docs.langchain.com/langsmith/observability-concepts) | Runs/traces/threads with provider/framework instrumentation, tool metadata, token/cost fields, datasets, and evaluators. | Do not duplicate generic LLM application observability. Hosted/privacy/setup trade-offs remain explicit. |
| Existing tests, linters, static analyzers, CodeQL, dependency tools | Deterministic or domain-specific quality/security signals. | Never replace or weaken them with a synthetic health score or LLM judgment. Link to their evidence instead. |
| Git/VCS and CI | Diffs, history, ownership, checks, review gates. | Use as authoritative evidence; do not create a parallel state database for V0. |

## Track 1 result: no material current gap

No listed tool establishes the causal claim “this user's agent did unnecessary
work.” Existing V0 does not establish it either. Its reliable output is a local,
privacy-bounded normalization of repository structure and observer health.
Git/VCS, manifests, tests/CI, and native traces already supply the underlying
facts; Promptfoo and native/OTel systems expose richer workflow events.

Important candidate facts—same-file rereads, repeated searches, identical
results, correction/state-recovery work, tool-selection quality, and accepted
outcomes—are absent or incomplete in V0. An internal schema that can name them
does not make V0 vendor-neutral or capable. Track 1 therefore found no material
incremental observation and did not pass the Track 2 gate.

## Explicit do-not-build list

- another coding agent or IDE;
- semantic code search/indexing;
- a general memory, compaction, or RAG system;
- shell-output compression;
- MCP gateway or tool marketplace;
- automatic model/reasoning router;
- multi-agent orchestration;
- generic tracing/eval/LLM-observability SaaS;
- static analysis, security scanning, or dependency analysis replacements;
- a universal best-practice prompt library;
- a synthetic health score;
- dashboards, accounts, telemetry backends, or cloud services before a local
  evidence gap is demonstrated.

## Substitute-first output semantics

A future research output should prefer, in order:

1. `No change recommended.`
2. `Use or configure the existing native capability.`
3. `Run this reversible comparison and retain the better accepted outcome.`
4. Only after replicated evidence: `Consider a narrowly scoped new capability.`
