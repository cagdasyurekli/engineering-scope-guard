# Experiment Disk Safety

## Purpose

Experimental attempt repositories and Docker images can grow independently of
tracked Git state. This guard prevents the current prospective runner from
starting another attempt when the host write volume lacks a conservative
reserve or retained attempt repositories exceed a bounded allocation budget.

It is operational infrastructure, not a Shadow Scope Analyzer product feature
and not evidence about any experimental treatment.

## Frozen project limits

The runner uses code-bound, non-overridable limits:

- 64 GiB must remain free after the reserved execution headroom;
- 64 GiB is reserved for the next attempt;
- retained attempt repositories may occupy at most 64 GiB of filesystem-reported
  allocated blocks.

Therefore a new attempt requires at least 128 GiB available and no more than
64 GiB retained under sibling experiment state roots. Equality passes. An
invalid, incomplete, inaccessible, or symlink-redirected measurement fails
closed.

The allocation measurement is `st_blocks * 512`, with hard-linked inodes
counted once and symlinks never followed. On APFS, clones, compression, and
filesystem accounting mean this is neither logical file size nor a promise of
uniquely reclaimable space.

## Enforcement

`scripts/reasoning_effort_v1_runner.py` checks the filesystem containing the
configured `--state-root` during live preflight and again under the runner lock
immediately before `attempt_started`. A failure consumes no attempt, writes no
experimental outcome, provisions no credential, and starts neither Docker nor
provider/evaluator work.

Read-only status and recovery/reconcile commands remain available below the
threshold. Historical and frozen runners are unchanged; this safeguard does
not retroactively modify their contracts, ledgers, receipts, or conclusions.

## Operator commands

Inspect the current host state without starting Docker:

```bash
PYTHONPATH=src python3 scripts/experiment_disk_safety.py check
```

The command writes exact host-specific measurements to the ignored private
`.local/disk-safety-check.json`. Standard output contains only pass/fail,
failure codes, and the frozen-policy digest.

Create a private, ignored inventory for cleanup review:

```bash
PYTHONPATH=src python3 scripts/experiment_disk_safety.py plan-cleanup
```

The second command writes `.local/disk-cleanup-plan.json`. Standard output
only confirms that a private plan was written and withholds paths, counts,
sizes, and their digest. The plan has
`deletion_authorized: false`; it classifies no repository as safe to delete and
contains no deletion command. Before any explicit cleanup, an operator must
separately prove that selected attempts are terminal and their ledgers,
receipts, derived evidence, and required reproductions remain intact.

The target-set digest binds only the sorted relative path set; it is not an
inode or content identity and must never be reused as deletion approval. A
future explicitly authorized cleanup must re-inventory and revalidate every
target immediately before deletion.

Neither command starts Docker, inspects Docker Desktop's virtual-disk capacity,
or authorizes `docker system prune`, Docker image deletion, `Docker.raw`
mutation, or repository deletion. Host headroom is a stop gate, not proof of
Docker attribution.
