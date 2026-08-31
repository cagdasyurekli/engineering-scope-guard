"""Validate and freeze the single attempt-preserving Pilot-v3 successor lineage.

This module has no subject or evaluator executor. It binds the immutable
predecessor, the narrow adapter repair, and a separate genesis ledger so a
future execution can be authorized independently.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import canonical_bytes, digest
from .pilot_runner import canonical_attempt_timeout, sha256_file
from .pilot_v3 import (
    MAXIMUM_ATTEMPTS_PER_CELL,
    OPERATOR_INTERRUPTION_ALLOWANCE,
    INFRASTRUCTURE_RERUN_ALLOWANCE,
    append_event,
    build_launch_request,
    classify_termination,
    read_events,
    validate_contract,
)

SCHEMA = "engineering-scope-guard.pilot-v3-successor-authorization"
SCHEMA_VERSION = 1
AUTHORIZATION_VERSION = "pilot-v3-successor-v1.0"
SUCCESSOR_ID = "pilot-v3.0-successor-1"
GENESIS_EVENT = "pilot_v3_successor_genesis"
DECISION = (
    "ADAPTER REPAIR AND SUCCESSOR QUALIFIED — "
    "LIVE EXECUTION REQUIRES SEPARATE AUTHORIZATION"
)
INTERFACE_DECISION = (
    "PILOT-V3 SUCCESSOR EXECUTION INTERFACE QUALIFIED — "
    "LIVE EXECUTION REQUIRES SEPARATE AUTHORIZATION"
)
PREFLIGHT_SCHEMA = "engineering-scope-guard.pilot-v3-successor-execution-preflight"
DRY_RUN_SCHEMA = "engineering-scope-guard.pilot-v3-successor-execution-dry-run"
REPAIR_PATHS = (
    "src/engineering_scope_guard/pilot_runner.py",
    "scripts/pilot_runner.py",
)


def repair_identity(root: Path) -> dict[str, Any]:
    files = [
        {"path": path, "sha256": sha256_file(root / path)} for path in REPAIR_PATHS
    ]
    return {"files": files, "sha256": digest(files)}


def _predecessor_facts(
    root: Path,
    contract: dict[str, Any],
    pool: dict[str, Any],
    schedule: dict[str, Any],
    terminal: dict[str, Any],
    ledger_path: Path,
) -> dict[str, Any]:
    validate_contract(root, contract, pool, schedule)
    events = read_events(ledger_path)
    expected_types = [
        "contract_frozen",
        "pool_frozen",
        "schedule_frozen",
        "attempt_started",
        "isolation_verified",
        "subject_terminated",
        "evaluator_invoked",
        "credential_cleanup_verified",
        "batch_stopped",
    ]
    first = schedule["cells"][0]
    starts = [event["payload"] for event in events if event["event_type"] == "attempt_started"]
    subjects = [event for event in events if event["event_type"] == "subject_terminated"]
    invocations = [event for event in events if event["event_type"] == "evaluator_invoked"]
    evaluators = [event for event in events if event["event_type"] == "evaluator_finished"]
    receipts = [event for event in events if event["event_type"] == "receipt_committed"]
    cleanup = [event["payload"] for event in events if event["event_type"] == "credential_cleanup_verified"]
    if (
        [event["event_type"] for event in events] != expected_types
        or len(starts) != 1
        or starts[0].get("cell_id") != first["cell_id"]
        or starts[0].get("trajectory_attempt") != 1
        or len(subjects) != 1
        or len(invocations) != 1
        or evaluators
        or receipts
        or not cleanup
        or cleanup[-1].get("credential_removed") is not True
        or events[-1]["payload"].get("termination") != "durable_evidence_incomplete"
    ):
        raise ExperimentConfigurationError("Pilot-v3 predecessor ledger shape mismatch")
    if (
        terminal.get("status") != "batch_stopped_durable_evidence_incomplete"
        or terminal.get("schedule", {}).get("admissible_completed_cells") != 0
        or terminal.get("schedule", {}).get("invalid_partial_attempts") != 1
        or terminal.get("schedule", {}).get("unstarted_cells") != 31
        or terminal.get("attempt", {}).get("evaluator_processes_started") != 0
        or terminal.get("attempt", {}).get("trajectory_attempt") != 1
        or terminal.get("analysis", {}).get("arm_effect_analysis_performed") is not False
        or terminal.get("analysis", {}).get("interim_baseline_vs_short_comparisons") != 0
        or terminal.get("retry_accounting", {}).get("infrastructure_reruns_consumed") != 0
        or terminal.get("retry_accounting", {}).get("operator_interruptions_consumed") != 0
        or terminal.get("ledger", {}).get("sha256") != sha256_file(ledger_path)
        or terminal.get("ledger", {}).get("last_event_sha256") != events[-1]["event_sha256"]
    ):
        raise ExperimentConfigurationError("Pilot-v3 terminal evidence mismatch")
    return {
        "ledger_file_sha256": sha256_file(ledger_path),
        "ledger_events": len(events),
        "terminal_event_sha256": events[-1]["event_sha256"],
        "failed_position": 1,
        "failed_cell_id": first["cell_id"],
        "failed_attempt": 1,
        "subject_processes_completed": 1,
        "official_evaluator_processes_started": 0,
        "admissible_observations": 0,
        "interim_arm_comparisons": 0,
    }


def build_authorization(
    root: Path,
    contract: dict[str, Any],
    pool: dict[str, Any],
    schedule: dict[str, Any],
    terminal: dict[str, Any],
    ledger_path: Path,
    *,
    recorded_at: str,
) -> dict[str, Any]:
    facts = _predecessor_facts(root, contract, pool, schedule, terminal, ledger_path)
    if canonical_attempt_timeout(contract["contract_version"], contract["trajectory"]) != 1800:
        raise ExperimentConfigurationError("repaired Pilot-v3 timeout semantics mismatch")
    first = schedule["cells"][0]
    value: dict[str, Any] = {
        "schema_name": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "authorization_version": AUTHORIZATION_VERSION,
        "recorded_at": recorded_at,
        "status": "frozen-qualified-execution-not-authorized",
        "decision": DECISION,
        "scientific_basis": {
            "failure_class": "outcome-independent harness/schema incompatibility",
            "subject_exposure_preserved": True,
            "official_evaluator_outcome_produced": False,
            "admissible_observations_before_successor": 0,
            "interim_arm_effect_analysis_performed": False,
            "new_randomization": False,
        },
        "original": {
            "contract_path": "experiment/pilot_v3_execution_contract.json",
            "contract_canonical_sha256": contract["contract_sha256"],
            "contract_file_sha256": sha256_file(root / "experiment/pilot_v3_execution_contract.json"),
            "pool_path": "experiment/pilot_v3_pool.json",
            "pool_sha256": contract["pool"]["pool_sha256"],
            "pool_file_sha256": sha256_file(root / "experiment/pilot_v3_pool.json"),
            "schedule_path": "experiment/pilot_v3_schedule.json",
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "schedule_file_sha256": sha256_file(root / "experiment/pilot_v3_schedule.json"),
            "terminal_result_path": "experiment/pilot_v3_terminal_result.json",
            "terminal_result_file_sha256": sha256_file(root / "experiment/pilot_v3_terminal_result.json"),
            "unchanged": True,
        },
        "predecessor": {**facts, "original_ledger_immutable": True},
        "repair": repair_identity(root),
        "successor": {
            "successor_id": SUCCESSOR_ID,
            "separate_ledger_required": True,
            "starting_schedule_position": 1,
            "starting_cell": first,
            "starting_trajectory_attempt": 2,
            "position_1_attempt_1": "immutable predecessor exposure; no evaluator disposition",
            "position_1_attempt_3_permitted": False,
            "positions_2_through_32": "exact frozen identities and order; start at attempt 1",
            "completed_cells_repeat_after_restart_permitted": False,
            "fresh_isolation_required": True,
            "execution_authorized": False,
        },
        "accounting": {
            "maximum_attempts_per_cell": MAXIMUM_ATTEMPTS_PER_CELL,
            "infrastructure_rerun_allowance": INFRASTRUCTURE_RERUN_ALLOWANCE,
            "infrastructure_reruns_consumed_at_successor_start": 0,
            "infrastructure_reruns_remaining_at_successor_start": INFRASTRUCTURE_RERUN_ALLOWANCE,
            "operator_interruption_allowance": OPERATOR_INTERRUPTION_ALLOWANCE,
            "operator_interruptions_consumed_at_successor_start": 0,
            "operator_interruptions_remaining_at_successor_start": OPERATOR_INTERRUPTION_ALLOWANCE,
            "budgets_increased_or_reset": False,
            "successor_lineage_authorization_is_not_a_retry_allowance": True,
        },
        "forbidden": [
            "modify_or_reopen_predecessor_ledger",
            "relabel_position_1_attempt_1",
            "launch_position_1_attempt_3",
            "repeat_completed_successor_cells",
            "change_contract_pool_schedule_treatment_model_reasoning_evaluator_timeout_or_analysis",
            "increase_or_reset_retry_or_operator_budgets",
            "inspect_interim_arm_effects",
            "expose_confirmatory_task_bodies",
            "execute_without_separate_authorization",
        ],
    }
    value["authorization_sha256"] = digest(value)
    return value


def validate_authorization(
    root: Path,
    contract: dict[str, Any],
    pool: dict[str, Any],
    schedule: dict[str, Any],
    terminal: dict[str, Any],
    ledger_path: Path,
    authorization: dict[str, Any],
) -> None:
    expected = build_authorization(
        root,
        contract,
        pool,
        schedule,
        terminal,
        ledger_path,
        recorded_at=authorization.get("recorded_at", ""),
    )
    if canonical_bytes(authorization) != canonical_bytes(expected):
        raise ExperimentConfigurationError("Pilot-v3 successor authorization mismatch")


def genesis_payload(authorization: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorization_sha256": authorization["authorization_sha256"],
        "original_contract_sha256": authorization["original"]["contract_canonical_sha256"],
        "predecessor_ledger_sha256": authorization["predecessor"]["ledger_file_sha256"],
        "predecessor_terminal_event_sha256": authorization["predecessor"]["terminal_event_sha256"],
        "repair_identity_sha256": authorization["repair"]["sha256"],
        "successor_id": authorization["successor"]["successor_id"],
        "starting_schedule_position": 1,
        "starting_trajectory_attempt": 2,
    }


def initialize_successor_ledger(
    authorization: dict[str, Any], ledger_path: Path
) -> list[dict[str, Any]]:
    if ledger_path.exists():
        raise ExperimentConfigurationError("Pilot-v3 successor ledger already exists")
    append_event(ledger_path, GENESIS_EVENT, genesis_payload(authorization))
    return read_events(ledger_path)


def validate_successor_ledger(
    authorization: dict[str, Any], ledger_path: Path
) -> list[dict[str, Any]]:
    events = read_events(ledger_path)
    if (
        not events
        or events[0]["event_type"] != GENESIS_EVENT
        or events[0]["payload"] != genesis_payload(authorization)
    ):
        raise ExperimentConfigurationError("Pilot-v3 successor genesis mismatch")
    return events


def next_successor_action(
    contract: dict[str, Any], authorization: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Derive the next successor launch without repeating completed cells."""

    if not events or events[0]["event_type"] != GENESIS_EVENT:
        raise ExperimentConfigurationError("Pilot-v3 successor genesis is absent")
    batch_stops = [event for event in events if event["event_type"] == "batch_stopped"]
    if len(batch_stops) > 1:
        raise ExperimentConfigurationError("successor contains repeated batch stops")
    if batch_stops:
        if events[-1] != batch_stops[0]:
            raise ExperimentConfigurationError("successor ledger continues after batch stop")
        return {"action": "batch_stopped", "payload": batch_stops[0]["payload"]}
    cells = contract["schedule"]["cells"]
    receipts = [event["payload"] for event in events if event["event_type"] == "receipt_committed"]
    all_starts = [event["payload"] for event in events if event["event_type"] == "attempt_started"]
    started_attempts = {
        (item.get("cell_id"), item.get("trajectory_attempt")) for item in all_starts
    }
    if any(
        (receipt.get("cell_id"), receipt.get("trajectory_attempt")) not in started_attempts
        for receipt in receipts
    ):
        raise ExperimentConfigurationError("successor receipt lacks a matching attempt start")
    infrastructure_authorizations = [
        event for event in events if event["event_type"] == "infrastructure_rerun_authorized"
    ]
    operator_authorizations = [
        event for event in events if event["event_type"] == "operator_restart_authorized"
    ]
    if (
        len(infrastructure_authorizations)
        > authorization["accounting"]["infrastructure_reruns_remaining_at_successor_start"]
        or len(operator_authorizations)
        > authorization["accounting"]["operator_interruptions_remaining_at_successor_start"]
    ):
        raise ExperimentConfigurationError("successor allowance accounting is exceeded")
    completed_ids = [
        receipt["cell_id"]
        for receipt in receipts
        if classify_termination(receipt["termination"])["experimental_outcome"]
    ]
    if len(completed_ids) != len(set(completed_ids)):
        raise ExperimentConfigurationError("completed successor cell is repeated")
    expected_prefix = [cell["cell_id"] for cell in cells[: len(completed_ids)]]
    if completed_ids != expected_prefix:
        raise ExperimentConfigurationError("successor completions are not a schedule prefix")
    if len(completed_ids) == len(cells):
        return {"action": "complete"}
    position = len(completed_ids)
    cell = cells[position]
    allowed_started_ids = {item["cell_id"] for item in cells[: position + 1]}
    if any(item.get("cell_id") not in allowed_started_ids for item in all_starts):
        raise ExperimentConfigurationError("successor started a future schedule cell")
    starts = [
        event["payload"]
        for event in events
        if event["event_type"] == "attempt_started"
        and event["payload"].get("cell_id") == cell["cell_id"]
    ]
    first_attempt = 2 if position == 0 else 1
    expected_attempts = [first_attempt] if len(starts) == 1 else [first_attempt, 2]
    if starts and [item.get("trajectory_attempt") for item in starts] != expected_attempts:
        raise ExperimentConfigurationError("successor attempt sequence is invalid")
    for request in starts:
        roots = request.get("isolation_roots")
        if not isinstance(roots, dict) or not isinstance(roots.get("repository"), str):
            raise ExperimentConfigurationError("successor launch isolation is invalid")
        state_root = Path(roots["repository"]).parents[3]
        expected = build_launch_request(
            contract, cell, state_root, request["trajectory_attempt"]
        )
        observed = {key: value for key, value in request.items() if key != "attempt_started_at"}
        if observed != expected or not isinstance(request.get("attempt_started_at"), str):
            raise ExperimentConfigurationError("successor launch request mismatch")
    if not starts:
        return {
            "action": "launch",
            "cell": cell,
            "trajectory_attempt": first_attempt,
        }
    latest = starts[-1]
    attempt = latest.get("trajectory_attempt")
    if attempt not in {1, 2} or (position == 0 and attempt != 2):
        raise ExperimentConfigurationError("successor attempt identity is invalid")
    matching_receipts = [
        item
        for item in receipts
        if item.get("cell_id") == cell["cell_id"]
        and item.get("trajectory_attempt") == attempt
    ]
    if len(matching_receipts) > 1:
        raise ExperimentConfigurationError("successor attempt receipt is repeated")
    receipt = next(
        (
            item
            for item in reversed(receipts)
            if item.get("cell_id") == cell["cell_id"]
            and item.get("trajectory_attempt") == attempt
        ),
        None,
    )
    if receipt is None:
        interruptions = [
            event
            for event in events
            if event["event_type"] == "operator_interruption_recorded"
            and event["payload"].get("cell_id") == cell["cell_id"]
            and event["payload"].get("trajectory_attempt") == attempt
        ]
        if len(interruptions) > 1:
            raise ExperimentConfigurationError("successor interruption is repeated")
        if interruptions:
            if interruptions[0]["payload"].get("outcome_reviewed") is not False:
                raise ExperimentConfigurationError("successor interruption followed outcome review")
            authorizations = [
                event
                for event in events
                if event["event_type"] == "operator_restart_authorized"
                and event["payload"].get("cell_id") == cell["cell_id"]
                and event["payload"].get("next_attempt") == attempt + 1
            ]
            if len(authorizations) > 1:
                raise ExperimentConfigurationError("successor operator restart is repeated")
            if authorizations:
                if attempt >= MAXIMUM_ATTEMPTS_PER_CELL:
                    raise ExperimentConfigurationError("successor attempt allowance is exhausted")
                return {"action": "launch", "cell": cell, "trajectory_attempt": attempt + 1}
            consumed = sum(
                event["event_type"] == "operator_restart_authorized" for event in events
            )
            if (
                attempt >= MAXIMUM_ATTEMPTS_PER_CELL
                or consumed >= authorization["accounting"]["operator_interruptions_remaining_at_successor_start"]
            ):
                return {
                    "action": "record_batch_stop",
                    "termination": "operator_interruption_allowance_exhausted",
                }
            return {
                "action": "authorize_operator_restart",
                "cell_id": cell["cell_id"],
                "next_attempt": attempt + 1,
                "consumed": consumed + 1,
            }
        checkpoints = [
            event
            for event in events
            if event["payload"].get("cell_id") == cell["cell_id"]
            and event["payload"].get("trajectory_attempt") == attempt
        ]
        terminal_checkpoint = any(
            event["event_type"] in {"subject_terminated", "evaluator_finished"}
            and bool(event["payload"].get("terminal_if_any"))
            for event in checkpoints
        )
        cleanup = any(
            event["event_type"] == "credential_cleanup_verified"
            and event["payload"].get("credential_removed") is True
            for event in checkpoints
        )
        if terminal_checkpoint and cleanup:
            return {"action": "reconstruct_receipt", "request": latest}
        if terminal_checkpoint:
            return {"action": "cleanup_then_reconstruct", "request": latest}
        return {"action": "record_batch_stop", "termination": "durable_evidence_incomplete"}
    classification = classify_termination(receipt["termination"])
    if classification["batch_stop"]:
        return {"action": "record_batch_stop", "termination": receipt["termination"]}
    if classification["infrastructure_invalid"]:
        if attempt >= MAXIMUM_ATTEMPTS_PER_CELL:
            return {"action": "record_batch_stop", "termination": "attempt_limit_exhausted"}
        authorizations = [
            event
            for event in infrastructure_authorizations
            if event["payload"].get("cell_id") == cell["cell_id"]
            and event["payload"].get("next_attempt") == attempt + 1
        ]
        if len(authorizations) > 1:
            raise ExperimentConfigurationError("successor infrastructure rerun is repeated")
        if authorizations:
            return {
                "action": "launch",
                "cell": cell,
                "trajectory_attempt": attempt + 1,
            }
        reruns = len(infrastructure_authorizations)
        if reruns >= authorization["accounting"]["infrastructure_reruns_remaining_at_successor_start"]:
            return {"action": "record_batch_stop", "termination": "infrastructure_rerun_allowance_exhausted"}
        return {
            "action": "authorize_infrastructure_rerun",
            "cell_id": cell["cell_id"],
            "next_attempt": attempt + 1,
            "consumed": reruns + 1,
        }
    raise ExperimentConfigurationError("successor scheduler could not advance")


def strict_successor_preflight(
    root: Path,
    predecessor_ledger_path: Path,
    successor_ledger_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    """Validate the exact successor lineage without invoking live processes."""

    contract = json.loads((root / "experiment/pilot_v3_execution_contract.json").read_text())
    pool = json.loads((root / "experiment/pilot_v3_pool.json").read_text())
    schedule = json.loads((root / "experiment/pilot_v3_schedule.json").read_text())
    terminal = json.loads((root / "experiment/pilot_v3_terminal_result.json").read_text())
    validate_authorization(
        root,
        contract,
        pool,
        schedule,
        terminal,
        predecessor_ledger_path,
        authorization,
    )
    events = validate_successor_ledger(authorization, successor_ledger_path)
    action = next_successor_action(contract, authorization, events)
    if action.get("action") == "launch" and (
        action["cell"]["position"] == 1 and action["trajectory_attempt"] != 2
    ):
        raise ExperimentConfigurationError("successor position 1 attempt identity changed")
    state_root = successor_ledger_path.parent
    stale_auth = sorted(state_root.glob("attempts/*/*/codex-home/auth.json"))
    if stale_auth:
        raise ExperimentConfigurationError("trajectory-local authentication remains in successor state")
    return {
        "schema_name": PREFLIGHT_SCHEMA,
        "schema_version": 1,
        "status": "pass",
        "authorization_sha256": authorization["authorization_sha256"],
        "contract_file_sha256": sha256_file(root / "experiment/pilot_v3_execution_contract.json"),
        "pool_file_sha256": sha256_file(root / "experiment/pilot_v3_pool.json"),
        "schedule_file_sha256": sha256_file(root / "experiment/pilot_v3_schedule.json"),
        "terminal_result_file_sha256": sha256_file(root / "experiment/pilot_v3_terminal_result.json"),
        "predecessor_ledger_file_sha256": sha256_file(predecessor_ledger_path),
        "successor_ledger_file_sha256": sha256_file(successor_ledger_path),
        "successor_events": len(events),
        "next_legal_action": action["action"],
        "next_position": action.get("cell", {}).get("position"),
        "next_trajectory_attempt": action.get("trajectory_attempt"),
        "infrastructure_reruns_consumed": sum(
            event["event_type"] == "infrastructure_rerun_authorized" for event in events
        ),
        "infrastructure_rerun_allowance": authorization["accounting"][
            "infrastructure_rerun_allowance"
        ],
        "operator_interruptions_consumed": sum(
            event["event_type"] == "operator_restart_authorized" for event in events
        ),
        "operator_interruption_allowance": authorization["accounting"][
            "operator_interruption_allowance"
        ],
        "stale_trajectory_credentials": 0,
        "execute_marker_present": (state_root / "REAL_SUCCESSOR_EXECUTE_INVOKED").exists(),
        "subject_invocations": 0,
        "evaluator_invocations": 0,
    }


def successor_dry_run_receipt(
    root: Path,
    predecessor_ledger_path: Path,
    successor_ledger_path: Path,
    authorization: dict[str, Any],
    attempt_state_root: Path,
) -> dict[str, Any]:
    """Resolve all frozen successor launch envelopes without writing state."""

    preflight = strict_successor_preflight(
        root, predecessor_ledger_path, successor_ledger_path, authorization
    )
    events = validate_successor_ledger(authorization, successor_ledger_path)
    if len(events) != 1:
        raise ExperimentConfigurationError("complete successor dry-run requires genesis-only state")
    contract = json.loads((root / "experiment/pilot_v3_execution_contract.json").read_text())
    cells = []
    isolation_roots: list[str] = []
    for cell in contract["schedule"]["cells"]:
        attempt = 2 if cell["position"] == 1 else 1
        request = build_launch_request(contract, cell, attempt_state_root, attempt)
        isolation_roots.extend(request["isolation_roots"].values())
        cells.append(
            {
                "position": cell["position"],
                "cell_id": cell["cell_id"],
                "requested_task_slot": cell["requested_task_slot"],
                "actual_task_id": cell["actual_task_id"],
                "arm": cell["arm"],
                "repetition": cell["repetition"],
                "trajectory_attempt": attempt,
                "attempt_kind": "preserved-predecessor-successor" if cell["position"] == 1 else "first_attempt",
                "intervention_sha256": request["intervention_sha256"],
                "subject": request["subject"],
                "source_and_evaluator": request["source_and_evaluator"],
                "isolation_roots_relative": {
                    name: f"attempts/{cell['cell_id']}/attempt-{attempt}/{Path(value).name}"
                    for name, value in request["isolation_roots"].items()
                },
            }
        )
    if len(isolation_roots) != len(set(isolation_roots)):
        raise ExperimentConfigurationError("successor dry-run isolation roots collide")
    return {
        "schema_name": DRY_RUN_SCHEMA,
        "schema_version": 1,
        "status": "pass",
        "decision": INTERFACE_DECISION,
        "authorization_sha256": authorization["authorization_sha256"],
        "contract_sha256": contract["contract_sha256"],
        "pool_sha256": contract["pool"]["pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "preflight": preflight,
        "positions_resolved": len(cells),
        "position_1_attempt_1_executable": False,
        "position_1_attempt_3_permitted": False,
        "infrastructure_rerun_allowance": authorization["accounting"]["infrastructure_rerun_allowance"],
        "operator_interruption_allowance": authorization["accounting"]["operator_interruption_allowance"],
        "codex_invocations": 0,
        "evaluator_invocations": 0,
        "pilot_cells_executed": 0,
        "policy_comparisons_executed": 0,
        "ledger_modified": False,
        "cells": cells,
    }


def successor_execution_confirmation(authorization: dict[str, Any]) -> str:
    return "execute-pilot-v3-successor:" + authorization["authorization_sha256"]


def write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
