# Coding Agent Evidence Review

**Reviewed through:** 2026-08-29

**Decision use:** project-thesis and research-roadmap reassessment

**Claim boundary:** synthesis, not a new efficacy experiment

## Executive finding

The broader mission is defensible only after removing two assumptions:

1. direct scope prompting is not presently justified as the core mechanism;
2. lower raw token use is not the objective.

The evidence supports a narrower research program around **less unnecessary
agent work per correct or accepted outcome**. It does not yet support a general
auditor that tells all users how to configure agents, and it strongly rejects an
active optimizer that automatically changes instructions, context, tools,
models, or reasoning.

Across independent studies, official guidance, project evidence, and community
reports, the recurring pattern is conditionality. Context can add necessary
knowledge or noise; stronger reasoning can help difficult tasks or create
overthinking; subagents can isolate verbose independent work or multiply
coordination cost; AI assistance can accelerate some novices/tasks while
slowing experienced maintainers in a different setting. The useful research
question is not “which best practice wins?” but “what observable condition,
for which user/task/risk scope, predicts a reversible change that improves an
accepted outcome?”

## Evidence lanes

- **Independent evidence** supplies the strongest efficacy and harm constraints.
- **Vendor research** can reveal current usage and hypotheses, but is not
  independent replication.
- **Official guidance** is authoritative for supported mechanics and current
  controls, not for universal benefit.
- **Reproducible OSS work** supplies testable mechanisms and substitutes.
- **Community reports** identify failure language and candidate observables;
  they do not estimate prevalence or prove interventions.
- **Project evidence** establishes only what happened in the two frozen
  exploratory programs and cannot be generalized to all agents or tasks.

The detailed source identities, peer-review states, limits, and expiry triggers
are in [`EVIDENCE_REGISTRY.md`](EVIDENCE_REGISTRY.md).

## 1. Context engineering

### Supported

- Long context is not equivalent to reliable use. Peer-reviewed controlled work
  found strong position effects and diminishing value from additional retrieved
  documents in older models ([Liu et al., TACL 2024](https://aclanthology.org/2024.tacl-1.9/)).
- Current official guidance from [OpenAI](https://developers.openai.com/api/docs/guides/latest-model),
  [Anthropic](https://code.claude.com/docs/en/context-window),
  [Google](https://ai.google.dev/gemini-api/docs/long-context), and
  [GitHub](https://docs.github.com/en/copilot/concepts/prompting/response-customization)
  all exposes mechanisms for scoping, caching, compaction, or selective loading.
  This establishes capability, not comparative efficacy.
- Repository instruction evidence is contradictory. Gloaguen et al. report
  higher exploration/cost and no general success improvement, while Lulla et
  al. report lower median runtime/output tokens with comparable completion
  behavior. Both are current preprints with different designs and outcome
  semantics ([Gloaguen et al.](https://arxiv.org/abs/2602.11988),
  [Lulla et al.](https://arxiv.org/abs/2601.20404)).
- Official Claude Code documentation makes state-loss boundaries concrete:
  compaction summarizes history, some content is re-injected, and some is
  reloaded only after later file access. Community reports describe lost goals,
  repeated work, and compaction loops, but remain anecdotal.

### Not supported

- “Always add an AGENTS/CLAUDE/GEMINI file.”
- “Put the whole repository or all documentation in context.”
- “Compaction preserves everything important.”
- “Cached input is free or operationally irrelevant.”

### Research implication

Measure context composition and continuity before recommending content changes:
always-loaded instruction bytes, repeated cached/fresh input, re-read/re-search
patterns, compaction boundaries, lost completion state, and whether relevant
facts were actually available. Prefer progressive disclosure and durable
checkpoints as hypotheses, not universal defaults.

## 2. Token and agent-work efficiency

Raw token reduction is an invalid objective because:

- correct outcomes can require more work;
- cached input has different price/latency semantics from fresh input;
- a shorter failed run can create later correction work;
- a longer run may include necessary verification;
- agent token use is stochastic and can vary sharply on the same task.

Bai et al. report up to 30x same-task variation and no monotonic relationship
between higher token use and accuracy on their tested coding-agent trajectories
([preprint](https://arxiv.org/abs/2604.22750)). The METR RCT shows that user
beliefs about speed can diverge from measured time
([paper](https://metr.org/Early_2025_AI_Experienced_OS_Devs_Study-paper.pdf)).
OpenAI's current guidance explicitly says fewer calls, turns, or outputs count
as improvements only when final quality still passes existing evals
([official guidance](https://developers.openai.com/api/docs/guides/latest-model)).

The preferred measurement family is therefore:

- time to correct/accepted outcome;
- work and cost per correct/accepted outcome;
- turns, searches, tool calls, corrections, and user interventions per accepted
  outcome;
- repeated work with no evidence gain;
- abandoned work and state-recovery cost;
- fresh, cached, output, and reasoning tokens reported separately.

No single aggregate “efficiency score” is warranted.

## 3. Tools and MCP

Tool use has at least four separable questions: should a tool be used, was the
right tool selected, were its arguments/output handled correctly, and did its
use improve the accepted outcome. MetaTool finds substantial selection gaps
across tested models ([ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/bc12914d66b41b6bfc2d3a5decdb498b-Abstract-Conference.html)).
EMNLP 2025 work shows selection can be manipulated by description wording
without changing functionality
([Farahani and Johansson](https://aclanthology.org/2025.emnlp-main.1060/)).

Current OpenAI and Anthropic guidance recommends deferred/tool search for large
catalogs; Claude Code documents that tools and extensions consume context.
These are product mechanics and recommendations, not independent proof of an
optimal catalog size.

Observable, non-semantic candidates include:

- exposed versus invoked tools;
- tool-schema/context bytes;
- redundant equivalent calls and identical-result repetition;
- output size before/after deterministic filtering;
- selection errors with deterministic expected tools;
- no-tool controls;
- time and correctness before/after a reversible tool-set change.

Scope Guard should not build a new context engine, shell compressor, or generic
MCP router before showing a gap that native selection, Augment, RTK, or existing
tool-search mechanisms cannot address.

## 4. Model and reasoning configuration

Official controls exist for model choice and reasoning effort, but the evidence
does not justify crude automatic routing. OpenAI currently recommends a balanced
starting point and representative evaluation, warns that higher effort can
overthink open-ended tool work, and requires measured quality gains before
escalation. This is rapidly expiring Tier 3 guidance, not a universal law.

The preprint evidence on agent token use and prompt-induced waste is consistent
with non-monotonic returns, while other workloads show gains from additional
test-time compute. The contradiction is expected: difficulty, model family,
harness, stopping rules, and evaluator all matter.

A future study may compare fixed configurations on frozen representative tasks.
An automatic router is premature because self-estimated difficulty/cost is weak,
quality regressions may be rare but consequential, and model/runtime behavior
changes rapidly.

## 5. Planning, subagents, and multi-agent systems

Plan-first behavior is not intrinsically beneficial. Plans can externalize
state and acceptance criteria, but long generic plans add context and may lock
an agent into a bad decomposition. The relevant comparison is plan content and
task shape, not plan/no-plan as a universal toggle.

Subagents provide genuine context isolation when a bounded task produces large
output. Agent teams add parallelism and independent perspectives. The same
mechanisms impose duplicated discovery, handoff, integration, and coordination
work. Anthropic's current documentation explicitly recommends lighter options
for sequential or highly dependent work
([official docs](https://code.claude.com/docs/en/agent-teams)). CooperBench's
current preprint reports a coordination penalty on conflict-bearing coding
tasks ([paper](https://cooperbench.com/static/pdfs/main.pdf)).

The defensible hypothesis is narrow: agents may help when workstreams are
independent, bounded, and cheaply verifiable. Measure duplicate reads/searches,
overlapping edits, messages/handoffs, integration failures, total work, wall
time, and accepted outcome. Do not infer benefit from parallel activity.

## 6. Verification and trust

Tests are valuable deterministic evidence but only cover encoded behavior. A
passing suite is not proof of missing requirements, security, maintainability,
or user intent. LLM judges can add triage signal but are vulnerable to bias and
perturbation ([EMNLP 2024](https://aclanthology.org/2024.emnlp-main.474/)).

Human trust also requires calibration. Qian and Wexler observed expertise- and
task-dependent performance plus automation complacency in a 76-engineer study
([IUI 2024](https://research.google/pubs/take-it-leave-it-or-fix-it-measuring-productivity-and-trust-in-human-ai-collaboration/)).
Perry et al. found an older AI assistant could increase insecure code and
confidence in its security
([CCS 2023](https://doi.org/10.1145/3576915.3623157)). These results are
model/task bounded but make confidence-only outputs unacceptable, particularly
for non-developers and high-risk work.

Future support should distinguish:

- deterministic execution/static evidence;
- human review and domain-owner acceptance;
- model judgment, visibly labeled and calibrated;
- unknown/unverified properties.

## 7. User expertise and interaction

The proposed audience dimensions are directionally useful but not yet a frozen
taxonomy. The strongest evidence supports at least four independent axes:

- task/domain knowledge;
- software-engineering and verification ability;
- agent-operation skill;
- task stakes/lifecycle and desired learning.

Occupation labels or “novice/expert” alone collapse these dimensions. A domain
expert without programming experience may specify the domain well but be unable
to validate security or deployment behavior. An experienced engineer new to an
agent may verify code well but operate the tool inefficiently. A learner's best
workflow may intentionally trade speed for understanding.

Small ICER evidence shows Copilot accelerated students on tested brownfield
tasks while raising understanding concerns
([ICER 2025](https://icer2025.acm.org/details/icer-2025-papers/18/The-Effects-of-GitHub-Copilot-on-Computing-Students-Programming-Effectiveness-Effic)).
Anthropic vendor research reports broad occupational success with returns to
domain expertise, but it is observational and vendor-authored
([report](https://www.anthropic.com/research/claude-code-expertise)).

No automatic expertise inference or universal novice mode is justified. Any
future adaptation should be user-controlled, reversible, and tested by task/risk
scope.

## 8. Intent and requirement quality

The broader hypothesis—missing information or verification may matter more than
prompt wording—is supported enough to research, not to ship as a rule.
Dialogue SWE-Bench reports that autonomous benchmarks often assume complete
specifications, that real users frequently correct/reject outputs, and that
agents rarely ask clarifying questions; its schema-guided approach improved
tested baselines while showing coding and dialogue strength can diverge
([preprint](https://arxiv.org/abs/2606.13995)).

The project should distinguish:

- ambiguity that materially changes the outcome or authority boundary;
- repository evidence that can resolve an ambiguity without user interruption;
- optional preference that can safely use a stated assumption;
- missing acceptance evidence discovered only after implementation.

Blanket “ask more questions” guidance can itself create friction. Measure wrong-
target/overscope outcomes, avoidable user interventions, and whether a question
changed the accepted outcome.

## 9. Build versus not build

This is a defensible research track because writing code is only one possible
way to satisfy an intent. Existing repository behavior, configuration, deletion,
an installed dependency, platform capability, API/service, manual procedure, or
no change may be better. However, automatic semantic routing among those choices
would recreate the same unsupported judgment problem at a broader scope.

The first testable question is observational: in accepted real tasks, how often
did the eventual solution use existing capability or no code, and what evidence
made that choice correct? No prevalence or benefit claim exists yet.

## Project-local evidence

- D v0.1 remains rejected as a development variant.
- C-short v0.1 remains retired after an adverse acceptance signal, no work
  reduction, replicated literal-minimality-compatible failure, and search tax.
- Evidence-Conditioned Final Scope Review v0.1 remains retired after five
  prospectively frozen gates: no accepted-outcome mechanism, increased search,
  increased cached context, increased wall/work, and structural-proxy-only
  apparent reductions.
- Neither result proves that all guidance is harmful or that the broader mission
  fails. Together they do make a third direct scope-treatment variant unjustified.
- The Shadow Analyzer and experiment infrastructure remain potentially useful
  as measurement assets, independently of treatment efficacy.

## Contradictions that must remain visible

1. Instruction files may help in some configurations and harm in others.
2. AI can accelerate tested student/narrow tasks and slow experienced maintainers
   on mature projects.
3. Large context enables otherwise impossible tasks while increasing cost and
   sometimes reducing reliable use.
4. Higher reasoning/parallelism can improve difficult independent work while
   increasing work or degrading coordinated tasks.
5. Native tools cover many proposed mechanisms, but product capability does not
   establish that users configure or benefit from it.

## Limitations

- Frontier models, pricing, caching, context, tool search, and orchestration
  change faster than normal software-engineering evidence cycles.
- Several directly relevant 2026 studies are preprints, not peer-reviewed.
- Benchmark tasks, exam tasks, telemetry studies, and real repository work
  answer different questions.
- Vendor studies may have strong methods but remain non-independent.
- Community sources are selected reports, not representative samples.
- This project has only small exploratory intervention evidence and cannot
  estimate population effects or long-term maintenance.
- No cited study establishes a universal causal definition of “unnecessary
  agent work.” It must remain outcome- and evidence-conditioned.

## Bounded conclusion

Track 1 subsequently established that the existing V0 adds no material
incremental fact over the simplest native or existing-tool route. A fresh
2026-08-29 selection review therefore evaluated persistent instructions,
compaction/checkpoints, reasoning effort, tool exposure, output compression,
planning, subagents, clarification, verification/trust, build-versus-not-build,
and stopping.

New instruction-growth, tool-interface, tool-shortlisting, clarification,
test-time-compute, and harness-sensitivity evidence raises the novelty and
half-life gates for another experiment. Compaction remains the clearest
independent causal gap but cannot currently be induced and observed cleanly
without a treatment that risks measuring artificial context pressure or opaque
runtime behavior. Persistent instruction placement and reasoning effort have
cleaner execution outcomes, but a useful contribution would require more task
variation and repetitions than are presently justified.

Research remains transparent, local-first, and measurement-led. The next
justified work is evidence maintenance and, under separate authorization,
publication planning for the existing null, adverse, retirement, thesis, and
no-gap record—not a recommendation layer, optimizer, Track 2, or live study.
See [`NEXT_RESEARCH_HYPOTHESIS_PRIORITIZATION.md`](NEXT_RESEARCH_HYPOTHESIS_PRIORITIZATION.md).

**NO NEW LIVE EXPERIMENT JUSTIFIED — MAINTAIN/PUBLISH EXISTING EVIDENCE**
