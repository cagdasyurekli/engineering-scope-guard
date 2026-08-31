#!/usr/bin/env python3
"""Create an opaque, reproducible SWE-bench-Live Pilot partition.

The input must contain only the metadata fields needed for eligibility and
evaluation feasibility. Reference patches, test patches, problem statements,
and other task-body fields are rejected rather than silently ignored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_DATASET = "SWE-bench-Live/MultiLang"
SOURCE_REVISION = "62dc0745c40f067fc366ae3eb1a26136e5928f85"
SOURCE_ROWS = 1_077
ELIGIBILITY_VERSION = "swe-bench-live-multilang-v1"
CUTOFF = datetime(2026, 2, 16, 23, 59, 59, tzinfo=timezone.utc)
SEED = "engineering-scope-guard-pilot-v1-2026-08-27"
EXPECTED_ELIGIBLE = 634
PILOT_QUOTAS = {
    "c": 1,
    "cpp": 2,
    "cs": 2,
    "go": 1,
    "java": 2,
    "js": 1,
    "rust": 2,
    "ts": 1,
}
ALLOWED_FIELDS = {
    "instance_id",
    "repo",
    "created_at",
    "docker_image",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
    "rebuild_cmds",
    "test_cmds",
    "language",
}


class PartitionError(RuntimeError):
    """Raised when source metadata cannot satisfy the frozen frame."""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _rank(instance_id: str) -> str:
    material = f"{SEED}\0{SOURCE_REVISION}\0{instance_id}".encode()
    return hashlib.sha256(material).hexdigest()


def _nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item for item in value
    )


def _created_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _exclusion_reason(record: dict[str, Any], development_ids: set[str]) -> str | None:
    if record["instance_id"] in development_ids:
        return "previously_used_development_task"
    created = _created_at(record["created_at"])
    if created is None or created <= CUTOFF:
        return "not_newer_than_subject_knowledge_cutoff"
    if not isinstance(record["docker_image"], str) or not record["docker_image"]:
        return "missing_evaluator_image"
    if not _nonempty_strings(record["FAIL_TO_PASS"]):
        return "missing_fail_to_pass"
    if not _nonempty_strings(record["PASS_TO_PASS"]):
        return "missing_pass_to_pass"
    if not _nonempty_strings(record["rebuild_cmds"]):
        return "missing_rebuild_command"
    if not _nonempty_strings(record["test_cmds"]):
        return "missing_test_command"
    return None


def _read_metadata(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or len(value) != SOURCE_ROWS:
        raise PartitionError(f"expected exactly {SOURCE_ROWS} source rows")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != ALLOWED_FIELDS:
            raise PartitionError("source must contain only the frozen metadata projection")
        instance_id = item.get("instance_id")
        if not isinstance(instance_id, str) or not instance_id or instance_id in seen:
            raise PartitionError("source instance IDs must be non-empty and unique")
        if item.get("language") not in PILOT_QUOTAS:
            raise PartitionError(f"unsupported language for {instance_id}")
        if not isinstance(item.get("repo"), str) or not item["repo"]:
            raise PartitionError(f"missing repository for {instance_id}")
        seen.add(instance_id)
        records.append(item)
    return records


def _read_development_ids(path: Path) -> set[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    tasks = value.get("tasks") if isinstance(value, dict) else None
    if not isinstance(tasks, list):
        raise PartitionError("development registry is invalid")
    identifiers = {item.get("task_id") for item in tasks if isinstance(item, dict)}
    if any(not isinstance(item, str) or not item for item in identifiers):
        raise PartitionError("development registry has an invalid task ID")
    return identifiers


def build_partition(
    metadata_path: Path, development_registry: Path
) -> dict[str, Any]:
    """Apply the frozen frame and return commitments without reserve IDs."""

    records = _read_metadata(metadata_path)
    development_ids = _read_development_ids(development_registry)
    exclusions: Counter[str] = Counter()
    eligible: list[dict[str, Any]] = []
    for record in records:
        reason = _exclusion_reason(record, development_ids)
        if reason is None:
            eligible.append(record)
        else:
            exclusions[reason] += 1
    if len(eligible) != EXPECTED_ELIGIBLE:
        raise PartitionError(
            f"frozen source expected {EXPECTED_ELIGIBLE} eligible tasks, got {len(eligible)}"
        )

    pilot: list[dict[str, Any]] = []
    pilot_repositories: set[str] = set()
    for language, quota in PILOT_QUOTAS.items():
        ranked = sorted(
            (record for record in eligible if record["language"] == language),
            key=lambda record: (_rank(record["instance_id"]), record["instance_id"]),
        )
        for record in ranked:
            if record["repo"] in pilot_repositories:
                continue
            pilot.append(record)
            pilot_repositories.add(record["repo"])
            if sum(item["language"] == language for item in pilot) == quota:
                break
        else:
            raise PartitionError(f"cannot satisfy Pilot quota for {language}")

    pilot_ids = {record["instance_id"] for record in pilot}
    reserve = [
        record for record in eligible
        if record["instance_id"] not in pilot_ids
        and record["repo"] not in pilot_repositories
    ]
    repository_holdout = len(eligible) - len(pilot) - len(reserve)
    ranked_reserve_ids = [
        record["instance_id"]
        for record in sorted(
            reserve, key=lambda record: (_rank(record["instance_id"]), record["instance_id"])
        )
    ]
    pilot_output = [
        {
            "instance_id": record["instance_id"],
            "repo": record["repo"],
            "language": record["language"],
            "created_at": record["created_at"],
            "docker_image": record["docker_image"],
            "fail_to_pass_count": len(record["FAIL_TO_PASS"]),
            "pass_to_pass_count": len(record["PASS_TO_PASS"]),
            "rebuild_cmds": record["rebuild_cmds"],
            "test_cmds": record["test_cmds"],
            "rank_commitment": _rank(record["instance_id"]),
        }
        for record in sorted(pilot, key=lambda record: record["instance_id"])
    ]
    smoke_record = min(
        pilot,
        key=lambda record: (
            len(record["FAIL_TO_PASS"]) + len(record["PASS_TO_PASS"]),
            _rank(record["instance_id"]),
        ),
    )
    eligible_ids = sorted(record["instance_id"] for record in eligible)
    allocation = {
        "pilot_ids": sorted(pilot_ids),
        "reserve_ids_ranked": ranked_reserve_ids,
        "repository_holdout_ids": sorted(
            record["instance_id"] for record in eligible
            if record["instance_id"] not in pilot_ids
            and record["repo"] in pilot_repositories
        ),
    }
    return {
        "schema_name": "engineering-scope-guard.external-task-partition",
        "schema_version": 1,
        "source": {
            "dataset": SOURCE_DATASET,
            "revision": SOURCE_REVISION,
            "row_count": SOURCE_ROWS,
            "metadata_projection_sha256": _canonical_hash(records),
        },
        "eligibility": {
            "version": ELIGIBILITY_VERSION,
            "subject_knowledge_cutoff_exclusive": CUTOFF.isoformat(),
            "required_fields": sorted(ALLOWED_FIELDS),
            "eligible_distinct_tasks": len(eligible),
            "eligible_repositories": len({record["repo"] for record in eligible}),
            "eligible_by_language": dict(sorted(Counter(
                record["language"] for record in eligible
            ).items())),
            "eligible_ids_sha256": _canonical_hash(eligible_ids),
            "exclusions_by_first_reason": dict(sorted(exclusions.items())),
            "selection_uses_task_bodies_or_outcomes": False,
        },
        "partition": {
            "algorithm": "sha256(seed NUL source_revision NUL instance_id)",
            "seed": SEED,
            "pilot_count": len(pilot_output),
            "pilot_language_quotas": PILOT_QUOTAS,
            "pilot_repository_count": len(pilot_repositories),
            "pilot_tasks": pilot_output,
            "smoke_candidate": {
                "selection_rule": "minimum F2P plus P2P count, then hash rank",
                "selection_uses_task_bodies_or_outcomes": False,
                "instance_id": smoke_record["instance_id"],
                "repo": smoke_record["repo"],
                "language": smoke_record["language"],
                "docker_image": smoke_record["docker_image"],
                "fail_to_pass_count": len(smoke_record["FAIL_TO_PASS"]),
                "pass_to_pass_count": len(smoke_record["PASS_TO_PASS"]),
            },
            "confirmatory_reserve_count": len(reserve),
            "confirmatory_reserve_repositories": len({record["repo"] for record in reserve}),
            "confirmatory_reserve_ids_sha256": _canonical_hash(ranked_reserve_ids),
            "pilot_repository_holdout_count": repository_holdout,
            "allocation_sha256": _canonical_hash(allocation),
            "reserve_ids_or_bodies_emitted": False,
            "pilot_and_reserve_task_ids_disjoint": True,
            "pilot_and_reserve_repositories_disjoint": True,
        },
        "development_exclusions": {
            "registered_ids": sorted(development_ids),
            "overlap_with_source": len(development_ids.intersection(eligible_ids)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path)
    parser.add_argument(
        "--development-registry",
        type=Path,
        default=Path("experiment/development_tasks/registry.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_partition(args.metadata, args.development_registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "pass",
        "eligible_distinct_tasks": result["eligibility"]["eligible_distinct_tasks"],
        "pilot_count": result["partition"]["pilot_count"],
        "confirmatory_reserve_count": result["partition"]["confirmatory_reserve_count"],
        "allocation_sha256": result["partition"]["allocation_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
