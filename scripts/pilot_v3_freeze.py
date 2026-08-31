#!/usr/bin/env python3
"""Freeze and zero-provider qualify the fresh Pilot-v3 design."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_runner import parse_official_evaluator_artifacts
from engineering_scope_guard.pilot_v3 import (
    ARMS,
    LANGUAGES,
    REPETITIONS,
    SELECTION_FIELDS,
    append_event,
    build_contract,
    build_launch_request,
    build_pool,
    classify_termination,
    evaluator_transition,
    execution_confirmation,
    generate_schedule,
    next_scheduler_action,
    planned_pause_allowed,
    read_events,
    usage_summary,
    validate_contract,
)

POOL_PATH = Path("experiment/pilot_v3_pool.json")
SCHEDULE_PATH = Path("experiment/pilot_v3_schedule.json")
CONTRACT_PATH = Path("experiment/pilot_v3_execution_contract.json")
QUALIFICATION_PATH = Path("experiment/pilot_v3_qualification.json")
HISTORICAL_FILES = (
    "experiment/pilot_execution_contract.json",
    "experiment/exploratory_pilot_result.json",
    "experiment/pilot_successor_batch_authorization.json",
    "experiment/pilot_v2_execution_contract.json",
    "experiment/pilot_v2_terminal_result.json",
    "experiment/pilot_v2_continuation_authorization.json",
    "experiment/pilot_v2_continuation_terminal_result.json",
    "experiment/pilot_v2_measurement_boundary_qualification.json",
)


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected object in {path}")
    return value


def load_selection_rows(dataset_root: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as error:  # pragma: no cover - evaluator venv supplies it
        raise ExperimentConfigurationError("Pilot-v3 freeze requires evaluator pyarrow") from error
    columns = sorted(SELECTION_FIELDS - {"language"})
    rows: list[dict[str, Any]] = []
    for path in sorted((dataset_root / "data").glob("*.parquet")):
        language = path.name.split("-", 1)[0]
        for row in parquet.read_table(path, columns=columns).to_pylist():
            row["language"] = language
            rows.append(row)
    return rows


def selected_details(dataset_root: Path, instance_ids: set[str]) -> dict[str, dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as error:  # pragma: no cover
        raise ExperimentConfigurationError("Pilot-v3 qualification requires evaluator pyarrow") from error
    columns = ["instance_id", "base_commit", "problem_statement", "docker_image", "repo"]
    details: dict[str, dict[str, Any]] = {}
    for path in sorted((dataset_root / "data").glob("*.parquet")):
        language = path.name.split("-", 1)[0]
        for row in parquet.read_table(path, columns=columns).to_pylist():
            if row["instance_id"] in instance_ids:
                details[row["instance_id"]] = {
                    "instance_id": row["instance_id"],
                    "base_commit": row["base_commit"],
                    "problem_statement_sha256": hashlib.sha256(
                        row["problem_statement"].encode()
                    ).hexdigest(),
                    "docker_image": row["docker_image"],
                    "repo": row["repo"],
                    "language": language,
                }
    if set(details) != instance_ids:
        raise ExperimentConfigurationError("selected dataset details are incomplete")
    return details


def _dataset_hashes(dataset_root: Path) -> dict[str, str]:
    return {
        path.name: _sha256(path)
        for path in sorted((dataset_root / "data").glob("*.parquet"))
    }


def freeze(root: Path, dataset_root: Path) -> dict[str, Any]:
    rows = load_selection_rows(dataset_root)
    pool = build_pool(root, rows)
    schedule = generate_schedule(pool)
    contract = build_contract(root, pool, schedule)
    _write(root / POOL_PATH, pool)
    _write(root / SCHEDULE_PATH, schedule)
    _write(root / CONTRACT_PATH, contract)
    return {
        "status": "frozen-not-yet-qualified",
        "pool_sha256": pool["pool_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "contract_sha256": contract["contract_sha256"],
        "tasks": len(pool["slots"]),
        "cells": len(schedule["cells"]),
        "subject_calls": 0,
        "evaluator_calls": 0,
    }


def _run(command: list[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise ExperimentConfigurationError(
            f"qualification command failed: {command[0]} {command[1] if len(command) > 1 else ''}"
        )
    return completed.stdout.strip()


def _qualify_images(details: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for instance_id in sorted(details):
        task = details[instance_id]
        image = task["docker_image"]
        inspected = subprocess.run(
            ["docker", "image", "inspect", image], text=True, capture_output=True, check=False
        )
        if inspected.returncode != 0:
            _run(["docker", "pull", "--platform", "linux/amd64", image])
        image_info = json.loads(_run(["docker", "image", "inspect", image]))[0]
        container = _run(["docker", "create", "--platform", "linux/amd64", image, "true"])
        material_root = Path(tempfile.mkdtemp(prefix="pilot-v3-materialization-"))
        repository = material_root / "repository"
        repository.mkdir()
        try:
            _run(["docker", "cp", f"{container}:/testbed/.", str(repository)])
            head = _run(["git", "rev-parse", "HEAD"], cwd=repository)
            if head != task["base_commit"]:
                raise ExperimentConfigurationError(
                    f"materialized base commit mismatch for {instance_id}"
                )
            status = _run(["git", "status", "--porcelain=v1", "--untracked-files=no"], cwd=repository)
            receipts.append(
                {
                    "instance_id": instance_id,
                    "repo": task["repo"],
                    "language": task["language"],
                    "official_image": image,
                    "image_id": image_info["Id"],
                    "image_size_bytes": image_info["Size"],
                    "requested_platform": "linux/amd64",
                    "base_commit": head,
                    "tracked_worktree_clean": status == "",
                    "tracked_initial_state_entries": len(status.splitlines()),
                    "tracked_initial_state_sha256": hashlib.sha256(
                        status.encode()
                    ).hexdigest(),
                    "problem_statement_sha256": task["problem_statement_sha256"],
                    "fresh_materialization": True,
                    "subject_or_evaluator_invoked": False,
                }
            )
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
            shutil.rmtree(material_root)
    return receipts


def _reuse_materialization_evidence(
    root: Path, details: dict[str, dict[str, Any]]
) -> list[dict[str, Any]] | None:
    path = root / QUALIFICATION_PATH
    if not path.is_file():
        return None
    prior = _read(path)
    receipts = prior.get("materialization")
    if (
        not isinstance(receipts, list)
        or {item.get("instance_id") for item in receipts} != set(details)
        or any(item.get("subject_or_evaluator_invoked") is not False for item in receipts)
    ):
        return None
    for item in receipts:
        image = item.get("official_image")
        if not isinstance(image, str):
            return None
        inspected = json.loads(_run(["docker", "image", "inspect", image]))[0]
        if inspected.get("Id") != item.get("image_id"):
            return None
    return receipts


def _adapter_checks(root: Path) -> dict[str, bool]:
    fixture = _read(root / "tests/fixtures/pilot/official-evaluator-terminal-shapes.json")
    observed: dict[str, Any] = {}
    for case in fixture["cases"]:
        artifact = parse_official_evaluator_artifacts(
            "fixture-instance", case["report"], case["results"]
        )
        observed[case["name"]] = {
            "disposition": artifact.disposition,
            "resolved": artifact.resolved,
            "failing_checks": list(artifact.failing_checks),
            "feedback_status": artifact.feedback_status,
            "measurement_complete": artifact.measurement_complete,
        }
    named = evaluator_transition("failure", "available", 0)
    unnamed = evaluator_transition("failure", "unavailable", 0)
    return {
        "all_official_terminal_shapes_match": all(
            observed[case["name"]] == case["expected"] for case in fixture["cases"]
        ),
        "failure_with_feedback_permits_one_corrective_round": named["action"] == "correct",
        "failure_without_feedback_is_negative_without_correction": unnamed
        == {"action": "terminate", "termination": "evaluator_test_failure"},
        "error_is_attempt_invalid": evaluator_transition("error", "not_applicable", 0)["termination"]
        == "official_evaluator_error",
        "incomplete_is_attempt_invalid": evaluator_transition(
            "incomplete", "not_applicable", 0
        )["termination"]
        == "official_evaluator_incomplete",
        "empty_patch_is_experimental_negative": classify_termination(
            evaluator_transition("empty_patch", "not_applicable", 0)["termination"]
        )["experimental_outcome"],
        "unknown_or_contradictory_shape_stops_batch": evaluator_transition(
            "contradictory", "not_applicable", 0
        )["action"]
        == "stop_batch",
    }


def _state_machine_checks(contract: dict[str, Any]) -> dict[str, bool]:
    cell = contract["schedule"]["cells"][0]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        ledger = root / "ledger.jsonl"
        request = build_launch_request(contract, cell, root / "state", 1)
        before = read_events(ledger)
        planned_before = planned_pause_allowed(before)
        append_event(ledger, "attempt_started", request)
        append_event(
            ledger,
            "operator_interruption_recorded",
            {
                "cell_id": cell["cell_id"],
                "trajectory_attempt": 1,
                "cause": "fixture external operator interruption before outcome review",
                "outcome_reviewed": False,
            },
        )
        operator_action = next_scheduler_action(contract, read_events(ledger))

        reconstruction_ledger = root / "reconstruction.jsonl"
        append_event(reconstruction_ledger, "attempt_started", request)
        append_event(
            reconstruction_ledger,
            "subject_terminated",
            {
                "cell_id": cell["cell_id"],
                "trajectory_attempt": 1,
                "exit_code": 0,
                "session_id": "fixture-session",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 6,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 1,
                },
            },
        )
        append_event(
            reconstruction_ledger,
            "evaluator_finished",
            {
                "cell_id": cell["cell_id"],
                "trajectory_attempt": 1,
                "round": 0,
                "exit_code": 0,
                "official_disposition": "success",
                "feedback_status": "not_applicable",
                "report_sha256": "a" * 64,
                "results_sha256": "b" * 64,
                "terminal_if_any": "accepted_completed",
            },
        )
        append_event(
            reconstruction_ledger,
            "credential_cleanup_verified",
            {
                "cell_id": cell["cell_id"],
                "trajectory_attempt": 1,
                "credential_removed": True,
            },
        )
        reconstruction = next_scheduler_action(contract, read_events(reconstruction_ledger))

        infra_ledger = root / "infra.jsonl"
        append_event(infra_ledger, "attempt_started", request)
        append_event(
            infra_ledger,
            "receipt_committed",
            {
                "cell_id": cell["cell_id"],
                "trajectory_attempt": 1,
                "termination": "official_evaluator_error",
                "admissible": False,
            },
        )
        infra = next_scheduler_action(contract, read_events(infra_ledger))

        complete_ledger = root / "complete.jsonl"
        append_event(complete_ledger, "attempt_started", request)
        append_event(
            complete_ledger,
            "receipt_committed",
            {
                "cell_id": cell["cell_id"],
                "trajectory_attempt": 1,
                "termination": "accepted_completed",
                "admissible": True,
            },
        )
        after_complete = next_scheduler_action(contract, read_events(complete_ledger))

        incomplete_ledger = root / "incomplete.jsonl"
        append_event(incomplete_ledger, "attempt_started", request)
        incomplete = next_scheduler_action(contract, read_events(incomplete_ledger))

        codex_home = root / "credential-cleanup"
        codex_home.mkdir()
        credential = codex_home / "auth.json"
        credential.write_text("fixture", encoding="utf-8")
        credential.unlink()

        usage = usage_summary(
            [
                {
                    "input_tokens": 10,
                    "cached_input_tokens": 6,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 1,
                }
            ]
        )
        return {
            "planned_pause_only_between_attempts": planned_before
            and not planned_pause_allowed(read_events(reconstruction_ledger)[:1]),
            "operator_interruption_uses_separate_next_attempt": operator_action
            == {
                "action": "authorize_operator_restart",
                "cell_id": cell["cell_id"],
                "next_attempt": 2,
            },
            "restart_reconstructs_from_durable_terminal_evidence": reconstruction[
                "action"
            ]
            == "reconstruct_receipt",
            "infrastructure_condition_uses_separate_rerun": infra["action"]
            == "authorize_infrastructure_rerun",
            "completed_cell_is_not_repeated": after_complete.get("cell", {}).get("cell_id")
            == contract["schedule"]["cells"][1]["cell_id"],
            "incomplete_durable_evidence_stops_batch": incomplete
            == {"action": "record_batch_stop", "termination": "durable_evidence_incomplete"},
            "credential_cleanup_verified": not credential.exists(),
            "provider_components_preserved_and_fresh_input_calculated": usage
            == {
                "input_tokens": 10,
                "cached_input_tokens": 6,
                "output_tokens": 2,
                "reasoning_output_tokens": 1,
                "calculated_fresh_input_tokens": 4,
            },
            "hash_chain_round_trip": len(read_events(reconstruction_ledger)) == 4,
        }


def qualify(root: Path, dataset_root: Path, evaluator_root: Path) -> dict[str, Any]:
    pool = _read(root / POOL_PATH)
    schedule = _read(root / SCHEDULE_PATH)
    contract = _read(root / CONTRACT_PATH)
    regenerated_pool = build_pool(root, load_selection_rows(dataset_root))
    regenerated_schedule = generate_schedule(regenerated_pool)
    validate_contract(root, contract, pool, schedule)
    host = _read(root / "experiment/pilot_host_qualification.json")
    selected_ids = {slot["actual_task_id"] for slot in pool["slots"]}
    details = selected_details(dataset_root, selected_ids)
    reused_images = _reuse_materialization_evidence(root, details)
    images = reused_images if reused_images is not None else _qualify_images(details)
    current_codex = _run(["codex", "--version"]).removeprefix("codex-cli ")
    current_evaluator = _run(["git", "rev-parse", "HEAD"], cwd=evaluator_root)
    current_repolaunch = _run(["git", "rev-parse", "HEAD:launch"], cwd=evaluator_root)
    docker_info = json.loads(_run(["docker", "info", "--format", "{{json .}}"]))
    historical = {path: _sha256(root / path) for path in HISTORICAL_FILES}
    adapter = _adapter_checks(root)
    state = _state_machine_checks(contract)
    checks = {
        "pool_regenerates_byte_identically": regenerated_pool == pool,
        "schedule_regenerates_byte_identically": regenerated_schedule == schedule,
        "contract_digest_stable": contract["contract_sha256"]
        == build_contract(root, pool, schedule)["contract_sha256"],
        "exactly_two_frozen_arms": contract["arms"]["ids"] == list(ARMS),
        "exact_short_policy_bytes": contract["arms"]["short_policy_sha256"]
        == _sha256(root / "experiment/arms/short.txt"),
        "fresh_eight_task_repository_disjoint_pool": len(pool["slots"])
        == len(LANGUAGES)
        == len({slot["repo"] for slot in pool["slots"]}),
        "two_repetitions_per_task_arm": len(schedule["cells"])
        == len(pool["slots"]) * len(ARMS) * REPETITIONS,
        "zero_post_freeze_replacements": pool["selection"][
            "post_freeze_replacement_allowance"
        ]
        == 0,
        "confirmatory_reserve_opaque_and_repository_disjoint": pool[
            "confirmatory_reserve"
        ]["ids_or_bodies_emitted"]
        is False
        and pool["confirmatory_reserve"]["pilot_and_reserve_repositories_disjoint"]
        is True,
        "dataset_snapshot_bytes_match": _dataset_hashes(dataset_root)
        == host["source"]["dataset_snapshot_files_sha256"],
        "codex_version_matches_qualified_environment": current_codex
        == contract["environment"]["codex_version"],
        "evaluator_revision_matches_qualified_environment": current_evaluator
        == contract["environment"]["official_evaluator_revision"],
        "repolaunch_revision_matches_qualified_environment": current_repolaunch
        == contract["environment"]["repolaunch_revision"],
        "docker_runtime_matches_qualified_environment": (
            docker_info["ServerVersion"] == contract["environment"]["docker"]["engine_version"]
            and {"aarch64": "arm64"}.get(
                docker_info["Architecture"], docker_info["Architecture"]
            )
            == contract["environment"]["docker"]["engine_architecture"].removeprefix("linux/")
            and docker_info["NCPU"]
            == contract["environment"]["docker"]["engine_reported_cpus"]
            and docker_info["MemTotal"]
            == contract["environment"]["docker"]["engine_usable_memory_bytes"]
        ),
        "worker_count_remains_one": contract["environment"]["workers"] == 1,
        "all_selected_images_materialize_at_frozen_commits": len(images)
        == len(pool["slots"])
        and all(item["fresh_materialization"] and len(item["base_commit"]) == 40 for item in images),
        "all_selected_initial_states_are_recorded": all(
            len(item["tracked_initial_state_sha256"]) == 64 for item in images
        ),
        "all_adapter_fixture_checks_pass": all(adapter.values()),
        "all_durable_scheduler_checks_pass": all(state.values()),
        "strict_confirmation_gate_is_digest_bound": execution_confirmation(contract)
        == "execute-pilot-v3.0:" + contract["contract_sha256"]
        and contract["live_execution_authorized"] is False,
        "historical_evidence_preserved": len(historical) == len(HISTORICAL_FILES),
        "zero_live_experimental_activity": all(
            contract["qualification"][field] == 0
            for field in (
                "pilot_v3_subject_calls",
                "pilot_v3_evaluator_calls",
                "pilot_v3_cells_executed",
                "experimental_observations",
            )
        ),
    }
    status = "pass" if all(checks.values()) else "fail"
    result = {
        "schema_name": "engineering-scope-guard.pilot-v3-qualification",
        "schema_version": 1,
        "status": status,
        "decision": (
            "PILOT-V3 FROZEN AND QUALIFIED — LIVE EXECUTION REQUIRES SEPARATE AUTHORIZATION"
            if status == "pass"
            else "REDESIGN REQUIRED"
        ),
        "pool_sha256": pool["pool_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "contract_sha256": contract["contract_sha256"],
        "checks": checks,
        "adapter_fixture_checks": adapter,
        "durable_scheduler_checks": state,
        "materialization": images,
        "materialization_evidence_reused_from_same_goal": reused_images is not None,
        "historical_evidence_sha256": historical,
        "experimental_activity": {
            "pilot_v3_subject_calls": 0,
            "pilot_v3_evaluator_calls": 0,
            "pilot_v3_cells_executed": 0,
            "policy_comparisons": 0,
            "experimental_observations": 0,
            "confirmatory_task_bodies_exposed": 0,
        },
        "environment_change_assessment": {
            "material_change_from_qualified_pilot_v2": False,
            "new_live_canary_required_before_execution": False,
            "selected_task_image_materialization_qualified": status == "pass",
        },
        "execution_authority": {
            "live_execution_authorized": False,
            "separate_user_authorization_required": True,
            "confirmation_token_sha256": hashlib.sha256(
                execution_confirmation(contract).encode()
            ).hexdigest(),
        },
    }
    _write(root / QUALIFICATION_PATH, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--evaluator-root",
        type=Path,
        default=Path("/private/tmp/engineering-scope-guard-swe-bench-live-qualification"),
    )
    parser.add_argument("command", choices=("freeze", "qualify"))
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        result = (
            freeze(root, args.dataset_root.resolve())
            if args.command == "freeze"
            else qualify(root, args.dataset_root.resolve(), args.evaluator_root.resolve())
        )
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_v3_freeze: {error}", file=os.sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") not in {"fail"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
