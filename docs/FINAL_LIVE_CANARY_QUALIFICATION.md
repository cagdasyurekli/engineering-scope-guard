# Final Live Non-Pilot Canary Qualification

**Status:** complete; qualified infrastructure path

## Outcome

The exactly-once `BYVoid__OpenCC-1096` non-Pilot canary completed through the
qualified isolated ChatGPT/Codex credential path and the official
SWE-bench-Live Docker evaluator.

The terminal result was `accepted_completed`. The official evaluator resolved
the task in one round, the durable attempt reached `ledger_committed`, and the
ledger's next action was `complete`. No corrective round or retry was used.

This is infrastructure-qualification evidence only. It is not a Pilot-v2 cell,
policy comparison, efficacy result, cost claim, or evidence that baseline or
`C-short v0.1` is superior. Provider token components are observable in the
sanitized receipt; provider-billed amount and currency remain unavailable.

## Authority and exactly-once boundary

The current user request explicitly authorized one execution, the isolated
credential copy, one provider trajectory, the official evaluator, and
sanitized evidence creation. Before execution:

- `experiment/agent_handoff.json` passed its canonical validator;
- all five referenced evidence files existed and matched their recorded
  SHA-256 digests;
- `main` and `origin/main` matched at `521054d` and the worktree was clean;
- the exact selection and canary contract regenerated to their existing
  commitments;
- the canary state root was absent;
- Pilot-v1 contract, predecessor ledger, successor ledger, and successor
  authorization hashes matched the preserved qualification values;
- the restored qualified durability/resolver/runner path passed all 24 focused
  tests before the live command.

The live command was issued once. The same process was observed to completion;
no second command, substitute task, infrastructure rerun, or automatic repair
was used.

## Sanitized terminal evidence

The canonical receipt is
`experiment/pilot_v2_canary_qualification.json` with SHA-256
`462ba42215705030b4776639e94fda8e510ffe763d28a6a86076c8b4d882e121`.
It records:

- exact task: `BYVoid__OpenCC-1096` (`BYVoid/OpenCC`, C++);
- fixed subject: Codex `0.150.1`, `gpt-5.6-terra`, `medium` reasoning;
- canary invocations: 1;
- evaluator rounds: 1;
- evaluator resolved: true;
- termination: `accepted_completed`;
- provider usage fields complete;
- durable terminal stage: `ledger_committed`;
- recovery action: `complete`;
- Pilot-v2 subject calls: 0;
- Pilot-v2 evaluator calls: 0;
- confirmatory tasks exposed: 0;
- policy evidence: false.

The isolated credential copy was removed during runner cleanup. No `auth.json`
remains in the canary state. Raw prompt, provider trace, evaluator workspace,
and task repository remain ignored local execution evidence and are not part of
the sanitized repository artifact.

## Scope boundary and next action

No Pilot-v2 pool, schedule, or execution contract was frozen. No Pilot-v2 task
or confirmatory task was exposed or run. Baseline, `C-short v0.1`, evaluator
semantics, and retry budgets were unchanged.

The current request authorizes Git stabilization of this sanitized evidence.
After merge, the durable next action is to request separate authorization for
any next experimental goal. Any later Pilot-v2 preparation, freeze, or
execution remains a separate goal and authority decision.

## Decision

### `FINAL LIVE CANARY QUALIFIED — NEXT GOAL REQUIRES SEPARATE AUTHORIZATION`
