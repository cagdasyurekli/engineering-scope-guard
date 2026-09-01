#!/usr/bin/env python3
"""Freeze one outcome-blind, non-experimental Azure evaluator readiness task."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

import pyarrow.parquet as parquet

from engineering_scope_guard.evaluator_stable_qualification import validate_receipt
from engineering_scope_guard.pilot_contract import canonical_bytes, digest


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _write(path: Path, data: bytes) -> None:
    _require(".local" in path.parts, "readiness evidence must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def build(
    *, qualification: dict[str, Any], preflight: dict[str, Any],
    dataset_root: Path, output_root: Path,
) -> dict[str, Any]:
    validate_receipt(qualification)
    _require(
        preflight.get("preflight_sha256")
        == digest({key: value for key, value in preflight.items() if key != "preflight_sha256"}),
        "successor preflight drifted",
    )
    excluded = set(preflight["primary_slots"] + preflight["alternate_slots"])
    selected = {
        item["slot"]: item
        for item in [
            *qualification["selection"]["primary"],
            *qualification["selection"]["alternates"],
        ]
    }
    candidates = [
        item for item in qualification["candidates"]
        if item.get("status") == "qualified"
        and item["slot"] in selected
        and item["slot"] not in excluded
    ]
    _require(bool(candidates), "no qualified non-experimental readiness task remains")
    candidate = min(candidates, key=lambda item: item["slot"])
    _require(
        all(stage.get("outcome") == "pass" for stage in candidate.get("stages", []))
        and {stage.get("stage") for stage in candidate["stages"]}
        == {"q1_environment", "q2_repeated_validation", "q3_gold", "q4_clean_gold"},
        "readiness task lacks complete evaluator qualification",
    )
    files = sorted((dataset_root / "data").glob(f"{candidate['language']}-*.parquet"))
    _require(len(files) == 1, "readiness dataset split is ambiguous")
    rows = parquet.read_table(
        files[0],
        columns=[
            "instance_id", "repo", "base_commit", "problem_statement",
            "docker_image", "patch",
        ],
    ).to_pylist()
    matches = [row for row in rows if row["instance_id"] == candidate["instance_id"]]
    _require(len(matches) == 1, "readiness dataset row is absent or duplicated")
    row = matches[0]
    patch = row["patch"].encode("utf-8")
    _require(bool(patch), "qualified readiness task has an empty gold patch")
    resolved_image = selected[candidate["slot"]]["resolved_image"]
    task = {
        "task_id": candidate["instance_id"],
        "repository": candidate["repo"],
        "language": candidate["language"],
        "base_commit": row["base_commit"],
        "docker_image": candidate["docker_image"],
        "resolved_image": resolved_image,
        "problem_statement_sha256": hashlib.sha256(
            row["problem_statement"].encode("utf-8")
        ).hexdigest(),
        "task_snapshot_sha256": candidate["manifest_sha256"],
        "source_row_identity_sha256": digest(
            {
                "instance_id": candidate["instance_id"],
                "language": candidate["language"],
                "repo": candidate["repo"],
                "base_commit": row["base_commit"],
                "docker_image": candidate["docker_image"],
                "problem_statement_sha256": hashlib.sha256(
                    row["problem_statement"].encode("utf-8")
                ).hexdigest(),
            }
        ),
    }
    _require(
        row["repo"] == task["repository"]
        and row["docker_image"] == task["docker_image"]
        and "@sha256:" in resolved_image,
        "readiness task identity drifted from qualification",
    )
    patch_path = output_root / "gold.patch"
    request_path = output_root / "request.json"
    _write(patch_path, patch)
    request = {
        "job_id": "esgrr002-readiness-v4",
        "azure_task_id": "eval-1",
        "task": task,
        "patch_path": str(patch_path.resolve()),
        "evaluator_timeout_seconds": 5400,
    }
    _write(request_path, canonical_bytes(request))
    body = {
        "schema_name": "engineering-scope-guard.azure-evaluator-readiness-selection",
        "schema_version": 1,
        "qualification_receipt_sha256": qualification["state_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
        "candidate_slot": candidate["slot"],
        "excluded_experimental_slots": sorted(excluded),
        "selection_rule": "lowest_qualified_slot_outside_frozen_primaries_and_alternates",
        "qualification_stages": [
            {"stage": stage["stage"], "outcome": stage["outcome"]}
            for stage in candidate["stages"]
        ],
        "task_identity_sha256": digest(task),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "request_sha256": digest(request),
        "benchmark_subject_exposure": False,
        "experimental_selection_affected": False,
        "status": "ready",
    }
    selection = {**body, "readiness_selection_sha256": digest(body)}
    _write(output_root / "selection.json", canonical_bytes(selection))
    return selection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        qualification=json.loads(args.qualification.read_text()),
        preflight=json.loads(args.preflight.read_text()),
        dataset_root=args.dataset_root,
        output_root=args.output_root,
    )
    print(json.dumps({
        "status": result["status"],
        "candidate_slot": result["candidate_slot"],
        "readiness_selection_sha256": result["readiness_selection_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
