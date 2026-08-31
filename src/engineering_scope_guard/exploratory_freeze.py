"""Deterministic exploratory allocation and schedule freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .exploratory_design import (
    ARMS,
    DESIGN_VERSION,
    LANGUAGES,
    REPETITIONS,
    SCHEDULE_SEED,
    SELECTION_SEED,
    SOURCE_REVISION,
    STARTING_RESERVE_COMMITMENT,
    TASK_COUNT,
    TREATMENT_PATH,
    TREATMENT_SHA256,
    canonical_bytes,
    generate_schedule,
    select_metadata_rows,
)
from .pilot_contract import digest, read_object
from .pilot_v3 import SELECTION_FIELDS, build_pool, eligible_rows

SCHEMA_NAME = "engineering-scope-guard.evidence-conditioned-final-scope-review-exploratory-freeze"
FREEZE_VERSION = "evidence-conditioned-final-scope-review-exploratory-freeze-v0.1"
DECISION = "EXPLORATORY TASK AND SCHEDULE FREEZE QUALIFIED — EXECUTION REQUIRES SEPARATE AUTHORIZATION"
DESIGN_PATH = Path("experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json")
ARTIFACT_PATH = Path("experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_freeze.json")
POOL_DOMAIN = "engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-exploratory-pool"
TASK_DOMAIN = "engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-task"
RESERVE_DOMAIN = "engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-confirmatory-reserve"
EXPECTED_DATASET_SHA256 = {
    "c-00000-of-00001.parquet": "30c0b8cb9e7140e05a4e539f20be0c325be597cbba4bf35e232355987ddddd0c",
    "cpp-00000-of-00001.parquet": "8448db887817b63e4c0c284ca99de1ccda15023f48e5b2234a4084466e0768ae",
    "cs-00000-of-00001.parquet": "29ffe16d0b2cd802e753262b8b0d7fe3f2bb1b489396da238146e79f37937c1f",
    "go-00000-of-00001.parquet": "76d2b5dff0f3fac8303d30fa85495539e487d25974ad7c21cd21a545cb4756e2",
    "java-00000-of-00001.parquet": "00387685808c71d21ada175335304b1c118859453afadd58ea21a00b0d568ee8",
    "js-00000-of-00001.parquet": "bc6ec49ffaf9db97840d55eba6954fae8f5fb0fb071cf49e187f36ffadd55a7a",
    "rust-00000-of-00001.parquet": "02ac78e2c51a84eb174ac393bb07b77478f1f96cf260af18835a711dd8074ebc",
    "ts-00000-of-00001.parquet": "7e23783e27230c9cfab1035690035c25523043d6af635bc78da3fd2010c32714",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _rank(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def dataset_hashes(dataset_root: Path) -> dict[str, str]:
    """Return the pinned Parquet snapshot fingerprint without reading task bodies."""

    return {
        path.name: _sha256(path)
        for path in sorted((dataset_root / "data").glob("*.parquet"))
    }


def reconstruct_post_v3_reserve(root: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstruct and verify the exact committed post-Pilot-v3 reserve."""

    partition = read_object(root / "experiment/external_task_partition.json")
    host = read_object(root / "experiment/pilot_host_qualification.json")
    tracked_v3 = read_object(root / "experiment/pilot_v3_pool.json")
    _require(partition["source"]["revision"] == SOURCE_REVISION, "source revision changed")
    eligible = eligible_rows(rows, partition["eligibility"]["subject_knowledge_cutoff_exclusive"])
    _require(
        len(eligible) == partition["eligibility"]["eligible_distinct_tasks"],
        "eligible source frame no longer matches its commitment",
    )
    _require(build_pool(root, rows) == tracked_v3, "Pilot-v3 pool or reserve derivation changed")
    original_repositories = {
        item["repo"] for item in partition["partition"]["pilot_tasks"]
    }
    original_ids = {
        item["instance_id"] for item in partition["partition"]["pilot_tasks"]
    }
    replacement_repositories = set(
        host["summary"]["effective_confirmatory_reserve"][
            "replacement_repositories_now_excluded"
        ]
    )
    pilot_v3_repositories = {item["repo"] for item in tracked_v3["slots"]}
    reserve = [
        row
        for row in eligible
        if row["instance_id"] not in original_ids
        and row["repo"] not in original_repositories
        and row["repo"] not in replacement_repositories
        and row["repo"] not in pilot_v3_repositories
    ]
    expected = tracked_v3["confirmatory_reserve"]
    _require(len(reserve) == expected["remaining_count"], "post-Pilot-v3 reserve count changed")
    _require(
        len({row["repo"] for row in reserve}) == expected["remaining_repositories"],
        "post-Pilot-v3 reserve repository count changed",
    )
    ranked_ids = [
        row["instance_id"]
        for row in sorted(
            reserve,
            key=lambda row: (
                _rank(
                    "engineering-scope-guard-confirmatory-reserve-post-pilot-v3",
                    SOURCE_REVISION,
                    row["instance_id"],
                ),
                row["instance_id"],
            ),
        )
    ]
    actual = digest(
        {
            "domain": "engineering-scope-guard-confirmatory-reserve-post-pilot-v3",
            "source_revision": SOURCE_REVISION,
            "ranked_ids": ranked_ids,
        }
    )
    _require(actual == STARTING_RESERVE_COMMITMENT, "starting opaque reserve commitment mismatch")
    return reserve


def _selection_projection(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "opaque_instance_identity": row["instance_id"],
            "repository_identity": row["repo"],
            "language": row["language"],
        }
        for row in rows
    ]


def build_freeze(root: Path, rows: list[dict[str, Any]], snapshot_hashes: dict[str, str]) -> dict[str, Any]:
    """Build the exact freeze from pinned metadata only."""

    _require(snapshot_hashes == EXPECTED_DATASET_SHA256, "pinned dataset files changed")
    _require(all(set(row) == SELECTION_FIELDS for row in rows), "selection input contains non-metadata fields")
    reserve = reconstruct_post_v3_reserve(root, rows)
    selected_projection = select_metadata_rows(_selection_projection(reserve))
    selected_ids = {item["opaque_instance_identity"] for item in selected_projection}
    rows_by_id = {row["instance_id"]: row for row in reserve}
    selected_rows = [rows_by_id[item["opaque_instance_identity"]] for item in selected_projection]
    selected_repositories = {row["repo"] for row in selected_rows}
    remaining = [row for row in reserve if row["repo"] not in selected_repositories]

    selected: list[dict[str, Any]] = []
    for slot, row in enumerate(selected_rows, start=1):
        identity = row["instance_id"]
        language = row["language"]
        selected.append(
            {
                "slot": slot,
                "opaque_instance_identity": identity,
                "repository_identity": row["repo"],
                "language": language,
                "created_at": row["created_at"],
                "container_image_identity": row["docker_image"],
                "container_registry_manifest_available": False,
                "container_registry_manifest_sha256": None,
                "fail_to_pass_count": len(row["FAIL_TO_PASS"]),
                "pass_to_pass_count": len(row["PASS_TO_PASS"]),
                "rebuild_commands_available": bool(row["rebuild_cmds"]),
                "test_commands_available": bool(row["test_cmds"]),
                "selection_rank_sha256": _rank(SELECTION_SEED, SOURCE_REVISION, language, identity),
                "opaque_task_commitment": _rank(TASK_DOMAIN, SOURCE_REVISION, identity),
            }
        )
    _require({item["opaque_instance_identity"] for item in selected} == selected_ids, "selection materialization changed")

    pool_commitment = digest(
        {
            "domain": POOL_DOMAIN,
            "source_revision": SOURCE_REVISION,
            "selected": [
                {
                    "language": item["language"],
                    "opaque_task_commitment": item["opaque_task_commitment"],
                    "repository_identity": item["repository_identity"],
                }
                for item in selected
            ],
        }
    )
    ranked_remaining_ids = [
        row["instance_id"]
        for row in sorted(
            remaining,
            key=lambda row: (
                _rank(RESERVE_DOMAIN, SOURCE_REVISION, row["instance_id"]),
                row["instance_id"],
            ),
        )
    ]
    reserve_commitment = digest(
        {
            "domain": RESERVE_DOMAIN,
            "source_revision": SOURCE_REVISION,
            "ranked_ids": ranked_remaining_ids,
        }
    )
    blocks = generate_schedule(
        [item["opaque_task_commitment"] for item in selected], pool_commitment
    )
    cells: list[dict[str, Any]] = []
    materialized_blocks: list[dict[str, Any]] = []
    for block_position, block in enumerate(blocks, start=1):
        block_cells = []
        for arm in block["arms"]:
            cell = {
                "position": len(cells) + 1,
                "cell_id": f"exploratory-block-{block_position:02d}-{arm}",
                "block_position": block_position,
                "opaque_task_commitment": block["opaque_task_commitment"],
                "repetition": block["repetition"],
                "arm": arm,
            }
            cells.append(cell)
            block_cells.append(cell["cell_id"])
        materialized_blocks.append(
            {
                "position": block_position,
                **block,
                "cell_ids": block_cells,
            }
        )

    design_sha256 = _sha256(root / DESIGN_PATH)
    artifact: dict[str, Any] = {
        "schema_name": SCHEMA_NAME,
        "schema_version": 1,
        "freeze_version": FREEZE_VERSION,
        "status": "frozen-qualified-execution-not-authorized",
        "decision": DECISION,
        "authority": {
            "execution_authorized": False,
            "post_freeze_replacement_authority": False,
            "manual_or_adaptive_reordering_authorized": False,
            "experimental_subject_calls": 0,
            "experimental_evaluator_calls": 0,
            "experimental_observations": 0,
            "execution_ledger_created": False,
        },
        "source": {
            "dataset": "SWE-bench-Live/MultiLang",
            "revision": SOURCE_REVISION,
            "dataset_snapshot_files_sha256": snapshot_hashes,
        },
        "design": {
            "path": DESIGN_PATH.as_posix(),
            "version": DESIGN_VERSION,
            "sha256": design_sha256,
        },
        "treatment": {
            "path": TREATMENT_PATH.as_posix(),
            "version": "v0.1",
            "sha256": TREATMENT_SHA256,
        },
        "eligibility": {
            "metadata_fields": sorted(SELECTION_FIELDS),
            "task_bodies_or_outcomes_used": False,
            "pinned_container_and_evaluator_commands_required": True,
            "historical_exposure_excluded_by_repository": True,
            "reconstructed_reserve_count": len(reserve),
            "reconstructed_reserve_repositories": len({row["repo"] for row in reserve}),
            "starting_reserve_commitment_sha256": STARTING_RESERVE_COMMITMENT,
            "starting_reserve_commitment_verified": True,
        },
        "selection": {
            "algorithm": "SHA256(selection_seed NUL source_revision NUL language NUL opaque_instance_identity); identity-only tie-break; first unused repository",
            "selection_seed": SELECTION_SEED,
            "language_order": list(LANGUAGES),
            "selected_task_count": len(selected),
            "selected_repository_count": len(selected_repositories),
            "post_freeze_replacement_allowance": 0,
            "selected": selected,
            "exploratory_pool_commitment_domain": POOL_DOMAIN,
            "exploratory_pool_commitment_sha256": pool_commitment,
        },
        "confirmatory_reserve": {
            "commitment_algorithm": "domain-separated SHA-256 rank over remaining opaque identities, then canonical commitment",
            "commitment_domain": RESERVE_DOMAIN,
            "remaining_task_count": len(remaining),
            "remaining_repository_count": len({row["repo"] for row in remaining}),
            "commitment_sha256": reserve_commitment,
            "remaining_ids_or_bodies_emitted": False,
            "selected_repository_tasks_remaining": 0,
            "repository_disjoint_from_exploratory": True,
        },
        "schedule": {
            "algorithm": "frozen SHA-256 counterbalanced contiguous task-repetition blocks",
            "schedule_seed": SCHEDULE_SEED,
            "arms": list(ARMS),
            "repetitions_per_task_arm": REPETITIONS,
            "block_count": len(materialized_blocks),
            "cell_count": len(cells),
            "blocks": materialized_blocks,
            "cells": cells,
            "schedule_sha256": digest(cells),
        },
    }
    return artifact


def validate_freeze(value: Any, root: Path, rows: list[dict[str, Any]], snapshot_hashes: dict[str, str]) -> dict[str, Any]:
    """Regenerate the freeze and reject any manual or outcome-driven drift."""

    _require(isinstance(value, dict), "freeze must be an object")
    expected = build_freeze(root, rows, snapshot_hashes)
    receipts = value.get("selection", {}).get("selected", [])
    _require(isinstance(receipts, list) and len(receipts) == TASK_COUNT, "container eligibility receipts are incomplete")
    for expected_item, receipt in zip(expected["selection"]["selected"], receipts, strict=True):
        _require(receipt.get("container_registry_manifest_available") is True, "selected container manifest is unavailable")
        manifest_sha256 = receipt.get("container_registry_manifest_sha256")
        _require(
            isinstance(manifest_sha256, str)
            and len(manifest_sha256) == 64
            and set(manifest_sha256) <= set("0123456789abcdef"),
            "selected container manifest receipt is invalid",
        )
        expected_item["container_registry_manifest_available"] = True
        expected_item["container_registry_manifest_sha256"] = manifest_sha256
    _require(value == expected, "freeze differs from deterministic derivation")
    selection = value["selection"]
    selected = selection["selected"]
    _require(len(selected) == TASK_COUNT, "task count is not exactly eight")
    _require(len({item["repository_identity"] for item in selected}) == TASK_COUNT, "repository count is not exactly eight")
    _require(tuple(item["language"] for item in selected) == LANGUAGES, "language coverage changed")
    schedule = value["schedule"]
    _require(schedule["cell_count"] == 32 and len(schedule["cells"]) == 32, "cell count changed")
    _require(schedule["block_count"] == 16 and len(schedule["blocks"]) == 16, "block count changed")
    for task in selected:
        task_blocks = [block for block in schedule["blocks"] if block["opaque_task_commitment"] == task["opaque_task_commitment"]]
        _require(len(task_blocks) == 2, "task repetition block count changed")
        _require({tuple(block["arms"]) for block in task_blocks} == {ARMS, tuple(reversed(ARMS))}, "task is not counterbalanced")
    _require(value["authority"]["execution_authorized"] is False, "execution became authorized")
    _require(value["authority"]["experimental_observations"] == 0, "experimental observations appeared")
    return value


def load_freeze(path: Path, root: Path, rows: list[dict[str, Any]], snapshot_hashes: dict[str, str]) -> dict[str, Any]:
    """Load a canonical freeze artifact and validate it by regeneration."""

    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError("exploratory freeze is unreadable") from error
    _require(raw == canonical_bytes(value), "exploratory freeze JSON is not canonical")
    return validate_freeze(value, root, rows, snapshot_hashes)
