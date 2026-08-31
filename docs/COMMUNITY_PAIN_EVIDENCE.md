# Community Pain Evidence

**Review date:** 2026-08-29

**Evidence class:** Tier 5 anecdotes and issue reports; hypothesis generation only

## Method and limits

The review searched recent Reddit, Hacker News, and GitHub issue reports for
context loss, compaction, stale instructions, repetition, tool overload,
unnecessary refactoring, correction loops, quota exhaustion, multi-agent
duplication, verification difficulty, and arguments against additional tooling.

This is deliberately not a post count or prevalence estimate. Search ranking,
self-selection, duplicate reports, product-community composition, model/version
drift, and unverifiable causal attributions make mechanical counting misleading.
“Approximate recurrence” below means `single`, `several related reports`, or
`cross-product cluster`, not a population frequency.

## Observed clusters

| Cluster | Platform/date/product | Approximate recurrence | Representative sources | Interpretation |
| --- | --- | --- | --- | --- |
| Compaction loses goal/progress and repeats work | GitHub, 2025–2026, Codex | Several related reports | [#35935](https://github.com/openai/codex/issues/35935), [#36712](https://github.com/openai/codex/issues/36712), [#8481](https://github.com/openai/codex/issues/8481) | Detailed, version-specific reports describe lost checkpoints, repeated reads/commands, and loops. Correlation with compaction is credible; root cause and prevalence are unproved. |
| Compaction loses decision rationale | Reddit, 2026, Claude Code | Several similar discussions | [running decision log](https://www.reddit.com/r/ClaudeAI/comments/1usuzgo/i_told_claude_code_to_keep_a_running_log_file_of/), [context management thread](https://www.reddit.com/r/ClaudeAI/comments/1rrkv0h/how_are_you_guys_managing_context_in_claude_code/) | Users report that repository state survives while reasons and rejected paths do not. File-backed checkpoints are a user workaround, not efficacy evidence. |
| Context/tool metadata refills the window | GitHub, 2026, Claude Code | Single detailed issue plus related discussion | [#84187](https://github.com/anthropics/claude-code/issues/84187), [plugin/skill duplication discussion](https://www.reddit.com/r/ClaudeAI/comments/1rij9tr/psa_your_claude_code_plugins_are_probably_loading/) | Suggests measurable repeated metadata and registry cost. The exact large-agent setup is atypical and cannot set a universal threshold. |
| Repeated investigation without evidence gain | GitHub, 2026, Codex | Several work/loop reports | [#39512](https://github.com/openai/codex/issues/39512), [cached-context regression report](https://github.com/openai/codex/issues/34971) | Users describe high time/token work without resolving the original issue. Reports mix product defects and task-level judgment; inspect trace facts before causal labels. |
| Agent follows a stale or wrong task after state loss | GitHub, 2026, Codex | Several related reports | [#11315](https://github.com/openai/codex/issues/11315), [#19910](https://github.com/openai/codex/issues/19910) | Supports measuring terminal-objective and authority continuity. Does not prove a monitor can prevent the failure. |
| Tool is exposed but ignored | Reddit, 2026, cross-agent/MCP | Repeated theme, one clear example | [installed navigation tool ignored](https://www.reddit.com/r/AI_Agents/comments/1u3nrzb/spent_two_hours_installing_a_tool_to_make_my/) | Capability and invocation are different. The user removed the extra layer and preferred native search, directly challenging “more tools help.” |
| Too many or ambiguous tools impair selection | Reddit, 2026, MCP/agent builders | Cross-community cluster | [150-tool experiment discussion](https://www.reddit.com/r/AI_Agents/comments/1s1o8gs/we_tested_6_llms_with_up_to_150_mcp_tools_openai/), [27-tool production counterexample](https://www.reddit.com/r/mcp/comments/1u2g7ad/the_guides_say_mcp_tool_selection_degrades_past/) | Reports agree ambiguity and catalog shape matter, but disagree on simple numeric limits. This argues for outcome-based local evals, not a universal tool cap. |
| Agent edits instead of stopping/asking | GitHub, 2026, Gemini CLI | Single product issue with familiar pattern | [Gemini CLI #16099](https://github.com/google-gemini/gemini-cli/issues/16099) | User reports unrelated edits while the agent searches for alternatives. Useful authority/intent hypothesis; no prevalence or cross-product causality. |
| Cleanup, correction, and review erase time gains | Reddit, 2025–2026, mixed agents | Cross-community cluster | [LocalLLaMA discussion](https://www.reddit.com/r/LocalLLaMA/comments/1mdg9z1/do_ai_coding_agents_actually_save_you_time_or/), [ExperiencedDevs discussion](https://www.reddit.com/r/ExperiencedDevs/comments/1kqnui6), [tooling-quality discussion](https://www.reddit.com/r/ExperiencedDevs/comments/1t7pz22/the_alphaquality_state_of_ai_tooling_is_hard_to/) | Mixed reports: agents help with narrow lookup, prototypes, tests, and boilerplate; complex/context-heavy work may create cleanup. Task fit is the primary hypothesis. |
| Non-developers cannot verify generated software | Reddit, 2025–2026, vibe-coding communities | Repeated concern | [non-coder confidence discussion](https://www.reddit.com/r/ChatGPTCoding/comments/1hpv3bj), [security concern discussion](https://www.reddit.com/r/AskProgrammers/comments/1rva4l8/do_you_feel_insecure_using_claude_codecoding/) | Concerns align with independent trust/security evidence, but individual claims and examples are not verified. Risk-specific education may be more justified than workflow optimization. |
| Multi-agent coordination duplicates or conflicts | Reddit, 2026, agent builders | Cross-community cluster | [single vs multi-agent field report](https://www.reddit.com/r/aiagents/comments/1thl3bo/we_tested_singleagent_vs_multiagent_on_a_real/), [middle-management discussion](https://www.reddit.com/r/AI_Agents/comments/1vb5ytp/at_what_point_does_a_multiagent_workflow_become/) | Users report benefit for independent parallel scans and overhead for shared-context/integration tasks. Consistent with vendor guidance and CooperBench, still anecdotal. |
| Knowledge/guidance becomes stale | Reddit, 2026, Cursor/Copilot | Repeated theme | [freshness discussion](https://www.reddit.com/r/AI_Agents/comments/1rtkcio/ai_coding_agents_have_a_serious_knowledge/) | Supports explicit source/version/last-verified metadata. Does not establish that another registry will remain fresher than native docs. |

## Explicit disconfirming and no-tool evidence

The review intentionally retained cases that weaken the project thesis:

- A user removed an advanced repository-navigation tool because the agent ignored
  it and native search was more reliable in practice
  ([source](https://www.reddit.com/r/AI_Agents/comments/1u3nrzb/spent_two_hours_installing_a_tool_to_make_my/)).
- A production MCP practitioner argues that ambiguity and descriptions, not a
  simple tool-count threshold, determine success and that 27 tools can be
  workable with evals and templates
  ([source](https://www.reddit.com/r/mcp/comments/1u2g7ad/the_guides_say_mcp_tool_selection_degrades_past/)).
- Experienced-developer discussion includes users who find agents useful only
  for narrow tasks and others who obtain real value from native lookup,
  autocomplete, and test generation without another optimizer
  ([source](https://www.reddit.com/r/ExperiencedDevs/comments/1kqnui6)).
- Users describe agent frameworks and no-code orchestration as overcomplicating
  simple workflows
  ([source](https://www.reddit.com/r/AI_Agents/comments/1kc9jci)).
- Current vendor products already expose rules, skills, context inspection,
  compaction, tool search, subagents, plans, hooks, and review. A separate layer
  must demonstrate incremental value over those native controls.

These observations make `No change recommended` and `Use the native capability`
mandatory possible outputs of any future research tool.

## Hypotheses worth testing

1. Durable goal/checkpoint state may reduce post-compaction repetition, but the
   checkpoint's own update and context cost must be counted.
2. Repeated identical or evidence-equivalent tool results may be a high-precision
   work signal, but retry safety and transient failures must be separated.
3. Tool-set reduction may improve selection only when it preserves correct-tool
   recall; ambiguity and descriptions may matter more than count.
4. Independent, bounded subagents may reduce wall time/context pollution, while
   dependent work increases total work and integration failures.
5. Risk- and expertise-sensitive verification support may be more useful than
   general scope advice.
6. Native tooling may already solve enough of each problem that an external
   tool's net benefit is zero or negative.

## What cannot be inferred

The review does not establish how common any problem is, which product is best,
that a reported workaround caused an improvement, that token/quota complaints
equal monetary waste, or that users want Scope Guard. It supplies vocabulary,
failure candidates, and counterexamples for later prospectively designed work.
