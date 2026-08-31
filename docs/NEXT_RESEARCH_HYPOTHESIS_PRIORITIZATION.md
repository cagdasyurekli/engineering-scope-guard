# Next Coding-Agent Research Hypothesis Prioritization

**Evidence cutoff:** 2026-08-29

**Goal type:** research selection and experimental feasibility only

## Decision summary

The project should not authorize another live experiment now. Three candidate
families remain scientifically interesting:

1. compaction, state loss, and durable checkpoints;
2. persistent repository instructions and path-scoped context;
3. reasoning effort and test-time compute.

None passes all of the novelty, construct-isolation, public-task, evaluation,
cost/power, and model/runtime-half-life gates. Compaction has the clearest
independent causal gap but the weakest clean induction and instrumentation.
Instruction placement has credible contradictory evidence and executable
outcomes, but the literature is now crowded and rapidly changing. Reasoning
effort is controllable and measurable, but current vendor guidance and
test-time-compute studies already establish that benefits are task-dependent;
a useful new result would require substantially more task variation and
repetition than this repository can justify.

The higher-value next step is to maintain and synthesize the evidence already
earned. That conclusion is not an efficacy claim and does not authorize an
experiment, design freeze, provider call, Track 2, feature, or publication.

## Selection method

The review used the repository evidence hierarchy and treated source authority,
peer-review status, tested population, model/runtime, evaluator, and expiration
separately. Primary sources were rechecked at the evidence cutoff. Community
reports were used only to identify pain and possible mechanisms, never to infer
prevalence or causality.

Each candidate had to survive twelve gates: user importance, scientific
uncertainty, falsifiability, outcome quality, observability, experimental
isolation, reproducibility, cost, half-life, novelty, risk, and value of a null
result. `High`, `medium`, and `low` are candidate-specific judgments, not
measurements. For cost, half-life, and risk, `high` means favorable: affordable,
durable, or low-risk. Candidate K is evaluated as the positive choice to stop.

## Fresh evidence status

### Independent and academic evidence

- Gloaguen et al., [*Evaluating AGENTS.md*](https://arxiv.org/abs/2602.11988),
  is an arXiv preprint also presented as an ICLR 2026 workshop paper, not an
  identified archival peer-reviewed result. Across CTXbench and SWE-bench,
  context files generally did not significantly improve success and increased
  steps or cost. The study directly raises the novelty bar for candidate A.
- Lulla et al., [*On the Impact of AGENTS.md Files on the Efficiency of AI
  Coding Agents*](https://arxiv.org/abs/2601.20404), is a JAWs/ICSE workshop
  preprint with a DOI placeholder in the available paper. It reports lower
  median runtime and output tokens with comparable completion across 10
  repositories and 124 pull requests. It remains a first-class contradiction,
  not a resolution.
- Chakrabarti et al., [*Why Does CLAUDE.md Keep
  Growing?*](https://arxiv.org/abs/2608.11095), is an observational plus
  controlled-synthetic preprint. Its large longitudinal corpus and instruction-
  following experiment strengthen the case that content and rationale matter,
  but the controlled mechanism is not a repository-level accepted-outcome
  experiment.
- Xu et al., [*The Devil Is in the Interface*](https://arxiv.org/abs/2608.11386),
  is a preprint using 11,700 repository-level trajectories across six tool
  architectures. It materially reduces the novelty of a generic tool-interface
  or tool-count study.
- Repantis et al., [*How Many Tools Should an LLM Agent
  See?*](https://arxiv.org/abs/2605.24660), is a benchmark preprint. Adaptive
  shortlisting preserved high recall with a much smaller visible catalog and
  improved downstream selection when the correct tool was retained. It leaves
  a recall-versus-ambiguity trade-off, not a blank research field.
- Suri et al., [*Structured Uncertainty guided
  Clarification*](https://aclanthology.org/2026.findings-acl.2028/), is an
  archival peer-reviewed Findings of ACL 2026 paper. It reports higher coverage
  with fewer clarification questions on ambiguous tool-use tasks. It is not a
  repository-coding outcome study, but it reduces the novelty of generic
  clarification policies.
- [Dialogue SWE-Bench](https://arxiv.org/abs/2606.13995) is a coding-focused
  preprint reporting gains from schema-guided dialogue. Simulator and LLM-judge
  components keep candidate H open while weakening a claim that clarification
  is wholly unstudied.
- [*A Jagged Frontier*](https://arxiv.org/abs/2608.18389) is a preprint showing
  that semantics-preserving task presentation and harness choice can change
  coding-agent scores and rankings. It raises the half-life and generalization
  burden for every harness-specific candidate.
- [*Scaling Test-Time Compute for Agentic
  Coding*](https://arxiv.org/abs/2604.16529) and [*Thinking Longer, Not
  Larger*](https://arxiv.org/abs/2503.23803) are preprints reporting conditional
  gains from additional test-time compute. They make a simple low-versus-high
  effort comparison insufficiently novel.
- [CooperBench](https://arxiv.org/abs/2601.13295) and
  [SlopCodeBench](https://arxiv.org/abs/2603.24755) remain preprints. The former
  documents coordination failure in collaborative coding; the latter supplies
  long-horizon iterative tasks but does not by itself validate compaction or
  checkpoint mechanisms.

### Current official product state

- OpenAI's current [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model)
  exposes multiple reasoning levels, recommends representative evaluation, and
  advises increasing reasoning only where measured quality warrants it. Its
  lean-prompt figures are vendor-internal and workload-dependent.
- OpenAI's official [compaction guidance](https://developers.openai.com/api/docs/guides/compaction)
  documents server-side compaction and an opaque compaction item intended to
  preserve key prior state. This is a native product improvement, not
  independent proof that state loss is solved.
- OpenAI's official [tool-search guidance](https://developers.openai.com/api/docs/guides/tools-tool-search)
  supports deferred tools and runtime search. This makes an always-loaded-versus-
  deferred schema comparison product-current but less novel.
- OpenAI's [multi-agent guidance](https://developers.openai.com/api/docs/guides/responses-multi-agent)
  describes a beta capability, recommends independent parallel work, and warns
  about token overhead and sequential or shared-mutable-state work. It supports
  conditionality, not a general benefit claim.
- Current Claude, Gemini, Copilot, Cursor, and OSS substitutes in
  `EVIDENCE_REGISTRY.md` and `COMPETITOR_AND_SUBSTITUTE_MAP.md` likewise expose
  native instruction scoping, context management, planning, tool selection,
  subagents, and tracing. Capability availability does not establish efficacy,
  but it shortens experiment half-life and raises the bar for building a custom
  layer.

## Candidate matrix

| Candidate | Importance | Uncertainty | Falsifiable | Outcome quality | Observable | Isolated | Reproducible | Cost | Half-life | Novelty | Risk | Null value |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. Persistent instructions/context | High | Medium | High | High | High | Medium | High | Medium | Low | Medium | High | High |
| B. Compaction/checkpoints | High | High | Medium | High | Medium | Low | Medium | Low | Low | High | High | High |
| C. Reasoning effort/TTC | High | Medium | High | High | High | High | High | Low | Low | Low | High | High |
| D. Tool exposure/ambiguity | High | Low | High | High | High | High | High | Medium | Low | Low | High | Medium |
| E. Tool-output compression | Medium | Low | High | High | High | High | High | High | Medium | Low | High | Medium |
| F. Planning | Medium | Medium | Medium | Medium | High | Low | Medium | Medium | Low | Medium | High | Medium |
| G. Subagents/coordination | Medium | Medium | High | High | Medium | Low | Medium | Low | Low | Medium | Medium | Medium |
| H. Clarification/completeness | High | Medium | High | Medium | Medium | Medium | Medium | Low | Low | Medium | Low | High |
| I. Verification/trust | High | High | Medium | Low | Medium | Low | Low | Low | Medium | High | Low | High |
| J. Build-versus-not-build | Medium | High | Low | Low | Low | Low | Low | High | High | High | High | Medium |
| K. No new experiment | High | High | High | High | High | High | High | High | High | High | High | High |

### Candidate-specific disposition

| Candidate | Credible evidence and unresolved issue | How it loses or becomes uninformative | Disposition |
| --- | --- | --- | --- |
| A | Independent studies conflict; vendor guidance supports scoped instructions; community pain concerns growth and conflicting rules. Content type and delivery scope remain unresolved. | Loses if path-scoped guidance does not improve accepted outcomes or if any gain is offset by exploration/work. Becomes uninformative if relevance, bytes, or exposure differ across arms. | Strongest clean-outcome candidate, but crowded and fast-expiring; do not design now. |
| B | Official mechanics and community reports support state-loss pain; independent causal coding evidence is thin. | Loses if native compaction preserves the prospectively defined state or checkpoint maintenance equals recovery saved. Artificially forced compaction would measure the harness rather than the reported phenomenon. | Highest scientific uncertainty, weakest clean induction; do not design now. |
| C | Vendor guidance and TTC preprints support task-conditional effects; cost/work variance is real. | Loses if higher effort does not improve accepted outcomes or if improvement is dominated by latency/cost. A small task set cannot identify a useful escalation rule. | Clean control, insufficient novelty and affordable power; do not design now. |
| D | Peer-reviewed tool-choice work, large coding-interface studies, shortlist benchmarks, and native tool search already cover the central mechanism. | Loses if correct-tool recall, not ambiguity, explains the effect. | Generic study is already adequately answered; reject. |
| E | RTK provides a reproducible intervention and diagnostic-loss is testable. | Loses if compression removes failure evidence or produces no success-adjusted saving. | Incremental research value is too low; reject. |
| F | Plans may help decomposition but can anchor or stale. | Loses if a plan changes several mechanisms or requires subjective “plan quality.” | Treatment is too vague for a clean next study; reject. |
| G | CooperBench and vendor guidance support structure-dependent coordination effects. | Loses if orchestration, model, communication, and partition quality cannot be held apart. | Current runtimes and harnesses dominate the result; reject for now. |
| H | Peer-reviewed clarification work and Dialogue SWE-Bench show benefit under ambiguity, while interruption cost remains unresolved. | Loses if benchmark ambiguity is synthetic or if simulator/judge quality determines the outcome. | Meaningful, but credible repository work likely needs human interaction or validated simulation; reject for now. |
| I | Security and judge research show confidence and verification can diverge from correctness. | Loses if “trust” is inferred from traces or unvalidated judges. | Next meaningful study requires human-subject and ethics infrastructure; reject. |
| J | No-code outcomes are plausible and strategically important, but prevalence is unknown. | Loses if task intent cannot be labeled independently or private traces are required. | Observational taxonomy lacks a validated public sample; reject automatic classification and a live study. |
| K | Multiple prior project interventions are null/adverse/retired; Track 1 found no incremental product gap; current external work narrows several open fields. | Loses only if a candidate passes every hard gate with a distinctive, affordable contribution. None does. | Prioritize evidence maintenance and separately authorized publication planning. |

## Anti-confirmation-bias review

### B. Compaction, state loss, and durable checkpoints

**Constructive pass.** This is credible user pain, has limited independent
causal evidence, and a negative result could show that native compaction or the
maintenance cost of checkpoints already dominates the proposed benefit. A
durable state object also has an interpretable mechanism: preserve objective,
completed work, rejected hypotheses, verification state, and next action.

**Adversarial pass.** Current native compaction is opaque and evolving. Forcing
a context threshold or injecting irrelevant length would create an artificial
treatment. Natural long-horizon tasks may not compact reliably, and observing
the exact pre/post state without private reasoning traces is difficult. A
checkpoint changes both retained content and agent behavior, so repeated work
cannot be attributed cleanly. The result could expire with one runtime release.
This candidate does not survive the isolation and half-life gates.

### A. Persistent repository instructions and path-scoped context

**Constructive pass.** The independent evidence conflict is real, accepted
outcomes can be execution-checked, public tasks exist, and a byte-matched
always-loaded versus path-scoped comparison could isolate delivery timing more
cleanly than earlier presence/absence studies. A null result would be useful
independent replication on a newer model and harness.

**Adversarial pass.** The field now includes a broad multi-agent/model study, a
workshop efficiency study, a large longitudinal instruction-growth study, and
current vendor scoping guidance. A new study could become a narrow harness
snapshot. Byte matching does not ensure equivalent exposure, and path-local
instructions may be relevant to only some tasks. Selecting tasks with known
local guidance could bias toward the treatment. The current incremental novelty
does not justify the cost and evidence half-life.

### C. Reasoning effort and test-time compute

**Constructive pass.** Effort is a native control, costs can be separated into
input, cached input, reasoning output, visible output, wall time, retries, and
corrections, and correctness can be execution-tested. A heterogeneous task set
could falsify “higher is always better” and identify task conditions where an
escalation is worthwhile.

**Adversarial pass.** Existing TTC studies already show conditional gains, and
official guidance already calls for workload-specific evaluation. Discovering
a reliable interaction requires many independent tasks and repetitions, not a
small low/medium/high comparison. Adaptive escalation adds a classifier and a
second mechanism. Model updates, provider pricing, caching, and reasoning
implementation rapidly expire the result. The study is clean but not novel or
durable enough at an affordable sample size.

## Feasibility sketches, not designs

These sketches name task-source families only. They do not select task
identities, inspect held-out bodies, freeze treatment bytes, define a runnable
contract, or authorize calls.

| Candidate | High-level question and arms | Possible public source and outcome | Unit, scale, instrumentation, configuration | Burden, confound, prospective kill |
| --- | --- | --- | --- |
| B. Compaction/checkpoints | Native compaction baseline versus one concise durable checkpoint before compaction; a native persisted-reasoning control only if the exact runtime exposes it consistently. | Open long-horizon iterative tasks such as SlopCodeBench or execution-verifiable SWE-bench-style tasks; primary accepted/correct outcome, guarded by no increase in unrecovered state or checkpoint maintenance work. | Independent task/repository; roughly 8–12 tasks, 2 repetitions, 2–3 arms (32–72 subject calls). Native event/usage, VCS, commands/tests, wall time, and explicit compaction boundary. One fixed current model/runtime. | Likely tens of millions of input tokens, hundreds of provider dollars, and substantial harness qualification. Strongest confound: forced compaction and opaque native state. Kill if natural compaction cannot be induced prospectively without task padding, or current native state already retains the defined facts. |
| A. Persistent/path-scoped instructions | No persistent file versus byte-matched always-loaded guidance versus the same guidance exposed path-scoped/on demand. | Public CTXbench/SWE-bench-style repository tasks with deterministic acceptance; quality guardrail is no lower accepted outcome. | Independent task/repository; roughly 12–20 tasks, 2 repetitions, 3 arms (72–120 subject calls). Native trace/usage, VCS, commands/tests, search/read counts, and wall time. One current model and harness. | Likely tens of millions of tokens and low-to-mid hundreds of provider dollars. Strongest confound: task-guidance relevance and unequal exposure. Kill if no pre-body public sampling frame supports genuinely path-local guidance or current literature already isolates the same mechanism. |
| C. Reasoning effort | Fixed low, medium, and high reasoning on the same task/configuration; adaptive escalation is not included because it introduces another mechanism. | Public execution-verifiable repository tasks; primary accepted/correct outcome with work/time/cost and variability reported separately. | Independent task/repository; roughly 12–20 tasks, 2–3 repetitions, 3 arms (72–180 subject calls). Native usage split into input/cached/reasoning/output, VCS, retries, corrections, commands/tests, and wall time. One current model. | Likely tens of millions of tokens, low-to-mid hundreds of provider dollars or more, and long wall time. Strongest confound: task-difficulty mix and model drift. Kill if the exact client cannot hold effort constant or affordable repetitions cannot distinguish task interactions from run variance. |

None of these sketches earns a separate design goal today. They are retained so
a future material evidence or runtime change can be assessed without pretending
that feasibility was never considered.

## External publication boundary

External publication and distribution channels are outside the scientific record and require separate project decisions.
## Final bounded decision

No candidate currently survives all hard gates. Revisit selection only after a
material independent replication, a stable native interface that resolves the
compaction-isolation problem, a public task source that improves task variation
without semantic judging, or a cost reduction large enough to support adequate
repetition. Until then, preserve and communicate the evidence already earned
under separate authorization.

**NO NEW LIVE EXPERIMENT JUSTIFIED — MAINTAIN/PUBLISH EXISTING EVIDENCE**
