# Project Thesis Reassessment

**Decision date:** 2026-08-29

**Basis:** literature, official guidance, community observations, substitutes,
and the project's two terminal intervention analyses

**Scope:** research-program decision; no capability authorization

## Decision in one sentence

Continue as an evidence-first research repository with the existing local
shadow measurement capability, while requiring new evidence and separate
authorization before testing any read-only auditor or recommendation layer.
Direct scope prompting is retired as the proposed core mechanism.

The optimization concept is:

> less unnecessary agent work per correct or accepted outcome

Raw token reduction is neither the objective nor a sufficient proxy. Necessary
investigation and verification may increase tokens while improving the outcome;
a short failed trajectory may simply move work into correction and recovery.

## What survives the original thesis

The following propositions remain defensible research questions:

- users can misjudge agent productivity and correctness;
- some agent work is repeated, abandoned, poorly targeted, or caused by state
  loss, and can sometimes be observed deterministically;
- context, tools, reasoning, verification, and coordination have conditional
  benefits and costs;
- accepted-outcome work, wall time, corrections, interventions, and repeated
  search are more decision-relevant than raw structural or token reductions;
- a local shadow analyzer and the experiment/evaluation infrastructure can be
  useful even when an intervention fails.

The evidence does **not** establish that the repository can already identify
unnecessary work reliably, that users want recommendations, that a common
policy spans all users, or that a new layer beats native logs and configuration.

## Historical disposition

- D v0.1 remains rejected.
- C-short v0.1 remains retired and is not silently revised.
- Evidence-Conditioned Final Scope Review v0.1 remains retired and is not
  silently revised.
- No third scope-treatment variant is authorized or recommended.
- Both negative programs remain valuable mechanism and measurement evidence.
- No confirmatory scope-policy experiment is justified by current evidence.
- The frozen records and task identities remain historical artifacts; this
  reassessment does not rewrite them.

## Audience is a segmentation problem

“All coding-agent users” is a possible long-term population, not one treatment
group. At least these dimensions may change the appropriate assistance:

- software-engineering and domain expertise;
- coding-agent experience and ability to delegate or verify;
- task risk, reversibility, and expected software lifetime;
- learning versus outcome-only intent;
- desired autonomy and tolerance for interruptions.

These are hypotheses rather than a frozen taxonomy. Research must allow them to
collapse, split, or be replaced. Non-developers must not receive a simplified
version of professional-developer advice by default: they may need more intent
elicitation and independent verification, while also being less able to assess
unsafe or superficially plausible output.

## Strongest case for not building the project

Severity describes threat to an end-user product: **critical** can invalidate
the product shape, **high** can invalidate a major capability, and **medium**
requires a bounded design response.

| # | Challenge | Severity and supporting evidence | Possible mitigation and credibility | Kill condition |
| --- | --- | --- | --- | --- |
| 1 | Vendors absorb useful capabilities. | Critical. Codex, Claude Code, Gemini, Copilot, and Cursor already expose instructions, memory/context, planning, tools, subagents, hooks, and evaluation surfaces. | Measure native capability rather than duplicate it. Credible only if a cross-vendor, local measurement gap remains. | Native outputs supply the same trustworthy observations and comparison workflow with no material extra burden. |
| 2 | Models improve faster than recommendations. | Critical. Model- and harness-specific results expire; old security and long-context findings do not transfer automatically. | Version every claim and revalidate. Credible for a registry, expensive for prescriptive software. | Required revalidation exceeds sustainable research capacity or recommendations are usually stale before use. |
| 3 | Extra guidance increases context/work. | Critical. Repository-instruction evidence is contradictory; this project's interventions added search/context/work or harmed acceptance. | Default to no change and test against no-guidance controls. Credible. | Advice cannot outperform silence on accepted outcomes in representative replicated tests. |
| 4 | Monitoring creates another complexity layer. | High. Additional setup, state, reports, and interpretation can become the waste being studied. | Local, passive, bounded outputs; measure observer burden. Credible for shadow measurement only. | Setup plus interpretation costs exceed detected avoidable work or cause target-repository changes. |
| 5 | Cheap user-specific causality may be impossible. | Critical. Agent trajectories vary and accepted outcomes are heterogeneous. | Reversible within-user comparisons with explicit outcome criteria. Partly credible, not for one-off high-risk work. | Useful advice requires impractical sample sizes or cannot separate task/model drift from intervention effects. |
| 6 | Recommendations become stale. | High. Vendor controls, context, pricing, and models change rapidly. | Expiry metadata and contradiction-first presentation. Credible for research, operationally costly for a product. | More than a small minority of active recommendations are unverifiable for current versions. |
| 7 | Users/tasks need contradictory policies. | Critical. Expertise, risk, task type, and context studies show heterogeneous effects. | Narrow applicability statements and segmentation research. Credible only if a few stable segments emerge. | No stable, actionable segments replicate across tasks or versions. |
| 8 | External observability is insufficient. | Critical. Hooks/logs may omit state, intent, failures, cache semantics, or acceptance. | Report coverage gaps; use supported read-only interfaces; never infer missing semantics. Credible for limited facts. | Key accepted-outcome/rework facts cannot be observed without invasive interception or semantic guesswork. |
| 9 | Measurement overhead exceeds waste. | High. Trace ingestion, storage, and user review add latency and privacy burden. | Sample selectively and report overhead alongside benefit. Credible. | Net time/work burden is non-positive after including installation, review, and false positives. |
| 10 | Best practices become cargo cults. | High. Tool descriptions and prompt rules can alter behavior without value. | Registry entries remain scoped, contradictory, expiring hypotheses. Credible if editorial discipline holds. | Users treat registry entries as defaults despite repeated null/negative comparisons. |
| 11 | Users do not want another tool. | Critical. Community counterexamples report uninstalling ignored tools and preferring native workflows. | Test demand before capability work; permit a research-only outcome. Credible. | Target users decline installation or ignore outputs even when reports identify verified rework. |
| 12 | Native logs/evals are enough. | High. Promptfoo, Braintrust, LangSmith, vendor logs, tests, and VCS cover much observability. | Complement and translate rather than replace. Credible only for a demonstrated local gap. | A documented configuration of existing tools answers the research question as well. |
| 13 | Measurability distorts the objective. | Critical. Files, LOC, calls, and tokens are proxies; structural reductions in the final review did not establish unnecessary-work reduction. | Require accepted-outcome and quality guardrails; show components, no synthetic score. Credible. | Decisions improve proxies while accepted outcomes, safety, learning, or maintenance worsen. |
| 14 | Broad audience makes the tool incoherent. | High. Novices, experts, learners, and high-risk users need different support. | Research segments before shared recommendations. Unproven. | No coherent minimal common observation layer serves multiple segments without unsafe advice. |
| 15 | Non-developer safety/liability is material. | Critical. Earlier security research found confidence can exceed correctness; tests are incomplete oracles. | Risk-tiered disclaimers, independent verification, and no autonomous mutation. Only partly credible. | The tool's advice induces high-stakes reliance it cannot verify or bound. |

These risks are not a checklist to “solve.” Several can terminate product work
even while the repository remains useful as a research archive.

## Product-shape comparison

### A. Research-only repository — retained baseline

Experiments, registry, reports, and reproducibility artifacts remain useful
without an end-user product. This is the safest default if demand, observability,
or causal usefulness fail. It requires ongoing source maintenance but avoids
claiming prescriptive authority.

### B. Shadow measurement tool — retain, do not expand by default

The existing V0 can record bounded deterministic facts locally. Its next
question is whether its observations correspond to user-recognized rework and
accepted outcomes without excessive overhead. Existing implementation is not
evidence of efficacy.

### C. Local read-only Agent Workflow Health Auditor — conditional candidate

This shape is plausible only if B exposes a repeatable, important gap not met by
native logs or existing tools. “Health” must remain decomposed into observations
such as context continuity, repeated work, verification evidence, and tool
configuration. No aggregate health score is justified. Any future recommendation
must use:

`observation → hypothesis → evidence → reversible experiment → measured result`

and allow `No change recommended.`

### D. Suggestion plus optional controlled experiment — later gate only

This may be useful after a read-only observation is valid, users want help, and
a reversible comparison can use a predeclared accepted-outcome criterion. It
must not mutate configuration automatically. It is not currently authorized.

### E. Active optimizer — rejected

Automatic changes to instructions, context, tools, models, or reasoning combine
stale causal advice, poor observability, heterogeneous users, and material
safety risk. Current evidence provides no basis for this architecture.

## Build-versus-not-build track

The proposition “the best outcome may be configuration, reuse, deletion, a
manual action, or no code change” is defensible as a future research question,
not a product feature. Dialogue/task evidence supports investigating missing
requirements and alternatives to code, but no current evidence shows that
Scope Guard can identify the best substitute reliably. Study existing/native
capability and no-change controls before inventing an implementation.

## Project identity

The repository name and intentionally public citation identity are sufficient for the research record.
## Bounded conclusion

The broader mission is defensible as a **falsifiable research program**, not as
a validated end-user guidance product. Research-only plus existing shadow
measurement is the current shape. A read-only auditor is only a conditional
candidate; suggestions require a later gate; an active optimizer is rejected.

**RESEARCH PROGRAM REFRAMED — NEXT CAPABILITY EXPERIMENT REQUIRES SEPARATE AUTHORIZATION**
