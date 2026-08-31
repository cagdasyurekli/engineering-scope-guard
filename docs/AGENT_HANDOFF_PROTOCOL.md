# Agent Handoff Protocol

## Purpose

`experiment/agent_handoff.json` is the repository's one canonical current
handoff. It lets an external reviewer with GitHub access determine, without a
Codex-chat transcript:

- which goal most recently reached a terminal state;
- which durable experimental or operational decision remains current;
- which repository evidence supports that state;
- which branch and pull request carry the handoff;
- whether CI and CodeQL must be checked;
- which bounded action is next and whether the user has authorized it;
- which actions remain forbidden.

The artifact is a compact coordination index, not raw experimental evidence and
not an accumulating history database. Historical state remains in Git history,
goal history, decisions, reports, receipts, contracts, and ledgers.

## Authority and conflicts

The handoff is not a new source of experimental truth or execution authority.
The user's current request, `AGENTS.md`, `docs/CURRENT_GOAL.md`, frozen
contracts, ledgers, experiment receipts, `docs/DECISIONS.md`, and Git history
remain authoritative in their established scopes.

If the handoff conflicts with any authoritative artifact, fail closed, report
the exact conflict, and do not execute or merge based on the handoff. A handoff
can report authorization that was supplied elsewhere; it cannot create,
extend, or infer authorization.

`goal` names the latest terminal repository goal. `current_decision` separately
names the still-operative experimental or operational decision when a protocol
or documentation goal does not replace that decision. This bootstrap therefore
records `Agent Handoff Protocol Bootstrap` as the terminal goal while retaining
the Dataset Bridge qualification as the current experimental decision.

## Canonical files

- Current handoff: `experiment/agent_handoff.json`
- Schema: `experiment/agent_handoff.schema.json`
- Standard-library validator: `engineering_scope_guard.agent_handoff`
- Validation command:

  ```bash
  PYTHONPATH=src python3 scripts/agent_handoff.py
  ```

The validator is authoritative for repository checks. The JSON Schema is the
portable shape description; no third-party schema dependency is required.

## Terminal goal lifecycle

For every completed, blocked, abandoned, or otherwise terminal goal:

1. finalize the authoritative evidence and decision records;
2. update `docs/CURRENT_GOAL.md` and the appropriate history/decision records;
3. replace `experiment/agent_handoff.json` with the current compact summary;
4. validate the handoff and its evidence paths/digests;
5. perform Git stabilization only when the active user authorization covers it;
6. stop rather than automatically beginning a materially new goal.

The handoff points to authoritative artifacts; it never replaces them. There is
only one current handoff file. Do not create one JSON file per goal.

## Action vocabulary

`next_action.kind` uses only:

- `none`
- `review`
- `persist_and_merge`
- `inspect_pr`
- `merge_if_green`
- `prepare_next_goal`
- `request_authorization`
- `run_authorized_goal`

Every next action includes a reason, whether explicit user authorization is
required, whether it is safe without explicit authorization, and one
authorization state:

- `explicit_current_request`
- `standing_user_authorization`
- `not_authorized`

Never infer standing authorization from a prior successful action, merged PR,
or handoff value. The user or an external reviewer acting on the user's explicit
instruction must set it deliberately.

## Safe-action policy

The handoff may identify ordinary bounded actions as candidates for explicit or
standing preauthorization, including reviewing a diff, inspecting an existing
PR, checking CI/CodeQL, merging when the user's authorization and all frozen
constraints cover it, or preparing but not executing a next goal.

The handoff never authorizes high-consequence experimental actions. Explicit
user authority remains required for:

- real Codex/provider execution outside an already-authorized frozen goal;
- provider usage/cost, credential use, or benchmark task-data egress;
- a new task sent to a model;
- a real Pilot or confirmatory execution;
- changing experimental treatment or freezing a new contract without existing
  authority;
- exposing held-out task bodies;
- increasing retry budgets;
- resetting or relabeling experimental evidence.

An action marked safe without explicit authorization must actually be bounded
and non-consequential. The validator rejects an unsafe action falsely marked as
authorization-free and rejects `run_authorized_goal` when authorization is
`not_authorized`.

## Privacy and size

Never place any of the following in the handoff:

- credentials, auth tokens, or personal information;
- raw provider traces;
- raw private task bodies or private benchmark content;
- local absolute paths;
- Graphify output;
- temporary worktree/environment information;
- sensitive `.local` evidence.

Evidence paths must be repository-relative regular files outside `.local` and
`graphify-out`, and their SHA-256 digests must match. The canonical handoff is
limited to 5 KiB. Large explanations belong in referenced reports.

## GitHub-first completion workflow

The normal flow is:

1. reach and record a terminal goal decision;
2. update and validate the handoff;
3. branch, commit, push, and open a PR only when authorized;
4. make at most one deliberate follow-up commit to add stable branch/PR
   metadata when useful;
5. derive required CI/CodeQL state from the referenced PR;
6. merge only when authorization covers merge and all required checks are green;
7. sync `main`, validate the merged handoff, confirm a clean tree, and stop.

Before a PR exists, required remote checks use `pending_pr`. Once PR metadata is
recorded, `ci_status` and `codeql_status` may be `derive_from_pr`. This avoids recording a
check result that becomes stale as soon as a metadata commit creates a new PR
head. An external reviewer follows `git.pr_url` and checks the current PR head.

## Avoiding self-referential commit loops

The handoff never requires the SHA of the commit that contains itself.
`git.head_sha` is either:

- an existing authoritative evidence commit with semantics
  `authoritative_evidence_commit`; or
- `null` with semantics `omitted_to_avoid_self_reference`.

The containing commit and eventual squash-merge SHA are derived from Git and the
referenced PR. Do not create a commit solely to record its own SHA. A single PR
metadata update is permitted because the PR number/URL are stable and do not
change when that commit is added.

The same rule applies to `current_decision.evidence_commit`. A clean independent
repository bootstrap with exactly one root commit cannot both contain the
handoff and embed that root commit's SHA. In that case, both commit fields are
`null` with semantics `omitted_to_avoid_self_reference`; the validator binds the
portable evidence through its repository-relative paths and SHA-256 digests,
while reviewers derive the containing root identity from Git. This omission
does not permit copying an unavailable private commit into public history.

An initial repository created directly on its protected base branch has no PR
from which to derive remote checks. Such a handoff uses `derive_from_branch` for
CI and CodeQL; reviewers inspect the current base-branch commit and its required
checks. `derive_from_pr` remains reserved for handoffs with stable PR metadata.

## External-review checklist

From repository state only, a reviewer should:

1. validate `experiment/agent_handoff.json`;
2. inspect every referenced evidence path and digest;
3. confirm the terminal goal and current decision against authoritative docs;
4. open `git.pr_url`, if present, to determine merge and CI/CodeQL state;
5. inspect `next_action`, authorization, allowed actions, and forbidden actions;
6. stop and ask the user when authorization is `not_authorized` or any conflict
   exists.
