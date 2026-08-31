"""Deterministic Pilot-v2 pool, schedule, contract, and dry-run freeze.

This module consumes only tracked, sanitized metadata. It never launches Codex,
Docker, an evaluator, or a Pilot schedule cell.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import (
    canonical_bytes,
    digest,
    read_object,
    validate_contract as validate_v1_contract,
    validate_preflight,
)
from .pilot_runner import build_launch_request

CONTRACT_VERSION = "pilot-v2.0"
SCHEDULE_SEED = "engineering-scope-guard-pilot-order-v2-2026-08-28"
EXPOSED_V1_TASK = "xroche__httrack-408"
EXPECTED_V1_STOPPED_CELL = "slot-04-baseline-rep-1"
ARMS = ("baseline", "short")
REPETITIONS = 2


def _rank(*parts: str) -> str:
    return hashlib.sha256("\0".join((SCHEDULE_SEED, *parts)).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authoritative_inputs(root: Path) -> dict[str, dict[str, Any]]:
    return {
        "v1_contract": read_object(root / "experiment/pilot_execution_contract.json"),
        "v1_result": read_object(root / "experiment/exploratory_pilot_result.json"),
        "v1_dry_run": read_object(root / "experiment/pilot_runner_dry_run.json"),
        "host": read_object(root / "experiment/pilot_host_qualification.json"),
        "canary": read_object(root / "experiment/pilot_v2_canary_qualification.json"),
    }


def _validate_lineage(inputs: dict[str, dict[str, Any]], root: Path) -> None:
    v1 = inputs["v1_contract"]
    result = inputs["v1_result"]
    canary = inputs["canary"]
    first = v1["schedule"]["cells"][0]
    validate_v1_contract(v1, root)
    if (
        v1.get("contract_version") != "pilot-v1.0"
        or first.get("cell_id") != EXPECTED_V1_STOPPED_CELL
        or first.get("actual_task_id") != EXPOSED_V1_TASK
    ):
        raise ExperimentConfigurationError("Pilot-v1 lineage differs from the terminal evidence")
    schedule = result.get("schedule", {})
    invocations = result.get("invocations", {})
    if (
        result.get("recommendation") != "REDESIGN REQUIRED"
        or schedule.get("stopped_at_cell") != EXPECTED_V1_STOPPED_CELL
        or schedule.get("valid_completed_cells") != 0
        or schedule.get("policy_comparisons") != 0
        or invocations.get("successor_subject_processes") != 1
        or invocations.get("successor_evaluator_processes") != 1
    ):
        raise ExperimentConfigurationError("Pilot-v1 exposure accounting changed")
    if (
        canary.get("status") != "pass"
        or canary.get("decision") != "CANARY PASSED — POOL FREEZE PERMITTED"
        or canary.get("pilot_v2_subject_calls") != 0
        or canary.get("pilot_v2_evaluator_calls") != 0
        or canary.get("confirmatory_tasks_exposed") != 0
    ):
        raise ExperimentConfigurationError("final live canary does not permit pool freeze")


def build_pool(root: Path) -> dict[str, Any]:
    inputs = _authoritative_inputs(root)
    _validate_lineage(inputs, root)
    v1_slots = inputs["v1_contract"]["final_pool"]["slots"]
    kept = [slot for slot in v1_slots if slot["actual_task_id"] != EXPOSED_V1_TASK]
    if len(v1_slots) != 12 or len(kept) != 11:
        raise ExperimentConfigurationError("expected one exposed task in the 12-task Pilot-v1 pool")
    slots = [
        {
            "slot": index,
            "pilot_v1_slot": item["slot"],
            "actual_task_id": item["actual_task_id"],
            "repo": item["repo"],
            "language": item["language"],
            "task_snapshot_sha256": item["task_snapshot_sha256"],
            "host_qualification_reused": True,
        }
        for index, item in enumerate(kept, start=1)
    ]
    effective_reserve = inputs["host"]["summary"]["effective_confirmatory_reserve"]
    value: dict[str, Any] = {
        "canonicalization": "slot-order; sorted-key compact JSON; trailing LF",
        "selection_rule": (
            "carry forward host-qualified Pilot-v1 tasks except any task whose body "
            "reached a subject or evaluator; do not draw from the confirmatory reserve"
        ),
        "selection_uses_task_bodies_or_task_outcomes": False,
        "excluded_exposure": {
            "pilot_v1_cell_id": EXPECTED_V1_STOPPED_CELL,
            "task_id": EXPOSED_V1_TASK,
            "reason": "task reached a Pilot-v1 subject and evaluator before receipt failure",
        },
        "slots": slots,
        "task_slot_replacement_budget": {
            "unit": "pre-treatment Pilot-v2 task slot",
            "allowance": 0,
            "consumed": 0,
            "remaining": 0,
            "remaining_authority_after_finalization": 0,
            "audit_events": [],
            "later_change_requires_new_contract": True,
        },
        "confirmatory_reserve": {
            "count": effective_reserve["effective_confirmatory_reserve_count"],
            "repositories": effective_reserve["effective_confirmatory_reserve_repositories"],
            "ids_sha256": effective_reserve["effective_confirmatory_reserve_ids_sha256"],
            "new_tasks_withdrawn_for_pilot_v2": 0,
            "ids_or_bodies_emitted": False,
            "unchanged_from_post_pilot_v1_effective_reserve": True,
        },
    }
    value["final_pool_sha256"] = digest(value["slots"])
    return value


def generate_schedule(pool: dict[str, Any]) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for repetition in range(1, REPETITIONS + 1):
        ordered = sorted(
            pool["slots"],
            key=lambda item: _rank(CONTRACT_VERSION, pool["final_pool_sha256"], str(repetition), str(item["slot"])),
        )
        for task in ordered:
            arms = sorted(
                ARMS,
                key=lambda arm: _rank(
                    CONTRACT_VERSION,
                    pool["final_pool_sha256"],
                    str(repetition),
                    str(task["slot"]),
                    arm,
                ),
            )
            for arm in arms:
                position = len(cells) + 1
                cells.append(
                    {
                        "position": position,
                        "cell_id": f"v2-slot-{task['slot']:02d}-{arm}-rep-{repetition}",
                        "requested_task_slot": task["slot"],
                        "actual_task_id": task["actual_task_id"],
                        "arm": arm,
                        "repetition": repetition,
                    }
                )
    value: dict[str, Any] = {
        "algorithm": "sha256-ranked repetition blocks with per-slot arm interleaving",
        "seed": SCHEDULE_SEED,
        "contract_version": CONTRACT_VERSION,
        "final_pool_sha256": pool["final_pool_sha256"],
        "arms": list(ARMS),
        "repetitions_per_task_arm": REPETITIONS,
        "manual_edits_permitted": False,
        "cells": cells,
    }
    value["schedule_sha256"] = digest(cells)
    return value


def build_contract(root: Path) -> dict[str, Any]:
    inputs = _authoritative_inputs(root)
    _validate_lineage(inputs, root)
    v1 = inputs["v1_contract"]
    pool = build_pool(root)
    schedule = generate_schedule(pool)
    canary_path = root / "experiment/pilot_v2_canary_qualification.json"
    value = {
        **{key: v1[key] for key in (
            "schema_name", "schema_version", "arms", "subject", "source_and_evaluator",
            "platform", "trajectory", "failure_taxonomy",
            "trajectory_infrastructure_rerun_budget", "isolation", "usage",
            "receipt_required_fields", "ledger",
        )},
        "contract_version": CONTRACT_VERSION,
        "status": "frozen-ready-not-authorized-for-execution",
        "pilot_authorized_by_manifest": False,
        "pilot_policy_comparison_runs": 0,
        "lineage": {
            "pilot_v1_contract_sha256": v1["contract_sha256"],
            "pilot_v1_result_sha256": _sha256_file(root / "experiment/exploratory_pilot_result.json"),
            "excluded_exposed_task": EXPOSED_V1_TASK,
            "final_live_canary_file_sha256": _sha256_file(canary_path),
            "final_live_canary_contract_sha256": inputs["canary"]["contract_sha256"],
            "final_live_canary_decision": inputs["canary"]["decision"],
            "pilot_v1_evidence_immutable": True,
        },
        "final_pool": pool,
        "schedule": schedule,
        "qualification": {
            "contract_path": "experiment/pilot_v2_execution_contract.json",
            "fixtures_or_dry_run_only": True,
            "pilot_v2_subject_calls": 0,
            "pilot_v2_evaluator_calls": 0,
            "pilot_v2_schedule_cells_executed": 0,
            "policy_comparisons_executed": 0,
            "confirmatory_task_bodies_exposed": 0,
            "execution_requires_separate_explicit_authorization": True,
        },
    }
    value["contract_sha256"] = digest(value)
    return value


def validate_contract(contract: dict[str, Any], root: Path) -> None:
    if canonical_bytes(contract) != canonical_bytes(build_contract(root)):
        raise ExperimentConfigurationError("frozen Pilot-v2 contract mismatch; refusing to normalize")


def build_dry_run(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    validate_contract(contract, root)
    prior_cells = _authoritative_inputs(root)["v1_dry_run"]["cells"]
    by_snapshot = {item["task_snapshot_sha256"]: item for item in prior_cells}
    cells = []
    prior_requests: list[dict[str, Any]] = []
    for cell in contract["schedule"]["cells"]:
        slot = next(
            item for item in contract["final_pool"]["slots"]
            if item["slot"] == cell["requested_task_slot"]
        )
        metadata = by_snapshot.get(slot["task_snapshot_sha256"])
        if metadata is None:
            raise ExperimentConfigurationError(f"missing frozen task metadata: {cell['actual_task_id']}")
        request = build_launch_request(contract, cell, Path("/synthetic/pilot-v2"), 1)
        validate_preflight(contract, request, tuple(prior_requests))
        prior_requests.append(request)
        cells.append(
            {
                "position": cell["position"],
                "cell_id": cell["cell_id"],
                "actual_task_id": cell["actual_task_id"],
                "task_snapshot_sha256": slot["task_snapshot_sha256"],
                "problem_statement_sha256": metadata["problem_statement_sha256"],
                "base_commit": metadata["base_commit"],
                "docker_image": metadata["docker_image"],
                "arm": cell["arm"],
                "intervention_sha256": request["intervention_sha256"],
                "subject_sha256": metadata["subject_sha256"],
            }
        )
    return {
        "schema_name": "engineering-scope-guard.pilot-v2-dry-run",
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "cells_resolved": len(cells),
        "pilot_v2_subject_calls": 0,
        "pilot_v2_evaluator_calls": 0,
        "pilot_v2_schedule_cells_executed": 0,
        "policy_comparisons": 0,
        "ledger_written": False,
        "cells": cells,
    }


def build_qualification(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    dry_run = build_dry_run(root, contract)
    pool = contract["final_pool"]
    schedule = contract["schedule"]
    task_cells = {
        slot["slot"]: [
            cell for cell in schedule["cells"]
            if cell["requested_task_slot"] == slot["slot"]
        ]
        for slot in pool["slots"]
    }
    checks = {
        "final_canary_passed": contract["lineage"]["final_live_canary_decision"] == "CANARY PASSED — POOL FREEZE PERMITTED",
        "exactly_one_exposed_v1_task_excluded": pool["excluded_exposure"]["task_id"] == EXPOSED_V1_TASK and len(pool["slots"]) == 11,
        "no_new_confirmatory_reserve_withdrawal": pool["confirmatory_reserve"]["new_tasks_withdrawn_for_pilot_v2"] == 0,
        "confirmatory_reserve_remains_opaque": pool["confirmatory_reserve"]["ids_or_bodies_emitted"] is False,
        "schedule_has_44_cells": len(schedule["cells"]) == 44,
        "each_task_has_two_arms_and_two_repetitions": all(
            {(cell["arm"], cell["repetition"]) for cell in cells}
            == {(arm, repetition) for arm in ARMS for repetition in range(1, REPETITIONS + 1)}
            for cells in task_cells.values()
        ),
        "dry_run_resolved_every_cell": dry_run["cells_resolved"] == len(schedule["cells"]),
        "zero_pilot_v2_execution": all(
            dry_run[field] == 0
            for field in (
                "pilot_v2_subject_calls", "pilot_v2_evaluator_calls",
                "pilot_v2_schedule_cells_executed", "policy_comparisons",
            )
        ),
        "execution_not_authorized": contract["pilot_authorized_by_manifest"] is False,
    }
    status = "pass" if all(checks.values()) else "fail"
    return {
        "schema_name": "engineering-scope-guard.pilot-v2-freeze-qualification",
        "schema_version": 1,
        "status": status,
        "decision": (
            "PILOT-V2 FREEZE PREPARED — GIT STABILIZATION AND EXECUTION AUTHORIZATION REQUIRED"
            if status == "pass"
            else "PILOT-V2 FREEZE NO-GO"
        ),
        "contract_sha256": contract["contract_sha256"],
        "final_pool_sha256": pool["final_pool_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "frozen_tasks": len(pool["slots"]),
        "scheduled_cells": len(schedule["cells"]),
        "checks": checks,
        "experimental_activity": {
            "pilot_v2_subject_calls": 0,
            "pilot_v2_evaluator_calls": 0,
            "pilot_v2_schedule_cells_executed": 0,
            "policy_comparisons": 0,
            "confirmatory_task_bodies_exposed": 0,
        },
        "implementation": {
            "freeze_module_sha256": _sha256_file(root / "src/engineering_scope_guard/pilot_v2.py"),
            "freeze_cli_sha256": _sha256_file(root / "scripts/pilot_v2_freeze.py"),
            "shared_runner_core_sha256": _sha256_file(root / "src/engineering_scope_guard/pilot_runner.py"),
            "shared_live_runner_sha256": _sha256_file(root / "scripts/pilot_runner.py"),
            "execution_entrypoint": "scripts/pilot_runner.py --contract experiment/pilot_v2_execution_contract.json execute",
            "live_preflight_requires_tracked_head_contract": True,
        },
        "authoritative_input_files_sha256": {
            "experiment/pilot_execution_contract.json": _sha256_file(root / "experiment/pilot_execution_contract.json"),
            "experiment/exploratory_pilot_result.json": _sha256_file(root / "experiment/exploratory_pilot_result.json"),
            "experiment/pilot_runner_dry_run.json": _sha256_file(root / "experiment/pilot_runner_dry_run.json"),
            "experiment/pilot_host_qualification.json": _sha256_file(root / "experiment/pilot_host_qualification.json"),
            "experiment/pilot_v2_canary_qualification.json": _sha256_file(root / "experiment/pilot_v2_canary_qualification.json"),
        },
        "dry_run": dry_run,
        "next_authorization_boundary": "Git stabilization before any separately authorized Pilot-v2 execution",
    }
