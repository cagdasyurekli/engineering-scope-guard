# Research Notes v0.1

This is a compact evidence map, not a literature review. Source findings constrain the design but are not automatically transferable to this project's exact workload.

## 1. Repository context can hurt

**Source:** Gloaguen et al., *Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?*

https://arxiv.org/abs/2602.11988

**Evidence:** [Strong/Moderate for tested harnesses; generalization remains bounded]

Key implications:

- Repository context files did not generally improve task success in the tested agents/models.
- Average inference cost increased by >20%.
- Instructions caused broader repository/tool exploration, showing agents were not simply ignoring the files.

**Design consequence:** Do not assume “more project context” helps. Project-intent injection is a separate experiment and should be minimal/task-relevant if tested.

## 2. Short controls matter

**Source:** Ponytail agentic benchmark and corrected methodology

https://github.com/DietrichGebert/ponytail

**Evidence:** [Moderate]

Key implications:

- A short YAGNI/minimality-style instruction captured a large fraction of the measured cost/token effect of a much longer skill.
- Large task-level heterogeneity exists; some UI tasks saw very large reductions while irreducible backend work showed little difference.
- Historical benchmark contamination is a concrete warning that plugin/hook isolation must be verified, not assumed.

**Historical design consequence:** Development falsified advancing D v0.1
unchanged. C-short v0.1 was later tested and retired after an adverse acceptance
signal and no work-reduction signal. It is no longer a surviving treatment.

## 3. User perception is not objective efficacy

**Source:** METR, *Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity*

https://metr.org/Early_2025_AI_Experienced_OS_Devs_Study-paper.pdf

**Evidence:** [Strong for that RCT population]

Key implication:

- Experienced developers believed AI made them faster while the randomized measurement found they were slower in that setting.

**Design consequence:** 👍/👎 may measure UX preference/annoyance, but not productivity or correctness.

## 4. Generic quality prompting is not enough

**Source:** SlopCodeBench

https://arxiv.org/abs/2603.24755

**Evidence:** [Moderate; benchmark-specific]

Key implications:

- Quality-aware/plan-first prompting can alter initial code characteristics.
- It did not reliably stop quality erosion over iterative checkpoints.
- Some quality/plan prompting increased cost materially.

**Design consequence:** Do not make “clean/maintainable/best practices” the product thesis. Treat generic quality wording as exploratory/control material.

## 5. Unbounded deliberation can be expensive

**Source:** Prompt-Induced Waste

https://arxiv.org/abs/2608.01347

**Evidence:** [Moderate; recent preregistered experimental evidence]

Key implications:

- Instructions to think deeply or compare multiple approaches can multiply reasoning use without a commensurate correctness gain.
- Bounded scope/acceptance/stop instructions are more promising than generic deliberation amplification.

**Design consequence:** No mandatory long alternatives analysis or “think deeply” instruction.

## 6. LLM-as-judge is not a sufficient quality oracle

**Sources:**

- CodeJudgeBench, ACL 2026: https://aclanthology.org/2026.acl-long.888/
- EACL Findings 2026 work on judge sensitivity to superficial code changes: https://aclanthology.org/2026.findings-eacl.70/

**Evidence:** [Strong that judge reliability/surface biases are material]

**Design consequence:** LLM judge may be exploratory screening only. Published quality claims require execution-based gates and, where necessary, blinded human review.

## 7. Codex hook integration is evolving

**Primary sources:**

- Codex hook engine/source: https://github.com/openai/codex/tree/main/codex-rs/hooks
- PostToolUse failure-signal issue: https://github.com/openai/codex/issues/34289
- Task-completion event request: https://github.com/openai/codex/issues/17333
- Prompt-hook ordering/security issue: https://github.com/openai/codex/issues/35929

**Evidence:** [Strong that the API surface exists; Strong that edge cases/coverage are evolving]

**Design consequence:** V0 must contain an adapter health/canary check and surface degraded event coverage. Avoid depending on a fragile hook path for correctness.

## 8. OpenAI distribution path

**Source:** OpenAI Help, *Plugins in ChatGPT and Codex*

https://help.openai.com/en/articles/20001256-plugins-in-chatgpt-and-codex

**Evidence:** [Strong, current product documentation]

**Implication:** Plugin packaging/directory distribution can be considered after the local tool proves useful. It is not required for V0.

## 9. 2026-08-29 coding-agent evidence reassessment

The current synthesis, source status, and contradictions now live in:

- `docs/CODING_AGENT_EVIDENCE_REVIEW.md`;
- `docs/EVIDENCE_REGISTRY.md`;
- `docs/COMMUNITY_PAIN_EVIDENCE.md`;
- `docs/COMPETITOR_AND_SUBSTITUTE_MAP.md`.

The reassessment adds several constraints:

- persistent-instruction evidence is contradictory, so instruction files are
  conditional mechanisms rather than universal best practice;
- context length, tool count, reasoning effort, and agent count can help or add
  noise/coordination work depending on task and runtime;
- user expertise, task risk, learning intent, and accepted-outcome definition
  can change which assistance is beneficial;
- raw tokens, LOC, files, and tool calls are components or proxies, not the
  objective; quality-preserving work per accepted outcome is the target family;
- native capabilities and existing OSS/evaluation tools must be compared before
  a new project capability is built;
- current evidence supports research plus existing shadow measurement, not a
  validated general auditor or automatic optimizer.

Official model/tool guidance is rapidly expiring and must be reverified. The
registry—not these condensed notes—is authoritative for dates, peer-review
status, tested scope, source tier, and contradiction metadata.
