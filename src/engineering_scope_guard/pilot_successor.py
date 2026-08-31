"""Immutable lineage and accounting for the single authorized Pilot successor.

This module does not execute a subject or evaluator. It validates the terminal
predecessor, builds the separate authorization, and prepares a fresh successor
ledger whose runtime state starts at the original cell 1 as attempt 2.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import (
    RERUNNABLE_INFRASTRUCTURE,
    canonical_bytes,
    classify_receipt,
    digest,
    read_ledger,
)
from .pilot_runner import (
    _validate_metadata_events,
    append_runner_event,
    build_launch_request,
    dry_run_receipt,
    next_legal_action,
    sha256_file,
)

SCHEMA = "engineering-scope-guard.pilot-successor-batch-authorization"
SCHEMA_VERSION = 1
AUTHORIZATION_VERSION = "pilot-successor-v1.0"
PREDECESSOR_BATCH_ID = "pilot-v1.0-predecessor-1"
SUCCESSOR_BATCH_ID = "pilot-v1.0-successor-1"
SUCCESSOR_LEDGER_NAME = "pilot-successor-ledger.jsonl"
SUCCESSOR_GENESIS_EVENT = "successor_batch_genesis"
UNDERLYING_FAILURE = "provider_api_infrastructure_failure"
RESTART_REASON = (
    "post-freeze pre-outcome infrastructure protocol amendment after an "
    "authentication failure prevented successful subject execution"
)


def _predecessor_facts(
    contract: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Validate and summarize the only supported terminal predecessor shape."""

    _validate_metadata_events(contract, events)
    if not events or events[-1].get("event_type") != "batch_stopped":
        raise ExperimentConfigurationError("predecessor is not terminal batch_stopped")
    if next_legal_action(contract, events)["action"] != "batch_stopped":
        raise ExperimentConfigurationError("predecessor terminal state is inconsistent")
    starts = [event["payload"] for event in events if event["event_type"] == "attempt_started"]
    finishes = [
        event["payload"] for event in events if event["event_type"] == "attempt_finished"
    ]
    if len(starts) != 1 or len(finishes) != 1:
        raise ExperimentConfigurationError("successor supports exactly one predecessor attempt")
    first = contract["schedule"]["cells"][0]
    if starts[0].get("cell_id") != first["cell_id"] or finishes[0].get("cell_id") != first["cell_id"]:
        raise ExperimentConfigurationError("predecessor attempt is not original schedule cell 1")
    classifications = [classify_receipt(contract, receipt) for receipt in finishes]
    valid_completed = sum(item["counts_as_experimental_outcome"] for item in classifications)
    evaluator_runs = sum(
        receipt.get("evaluator_result", {}).get("rounds", 0) for receipt in finishes
    )
    comparisons = valid_completed
    reruns = sum(
        event["event_type"] == "infrastructure_rerun_authorized" for event in events
    )
    if valid_completed or evaluator_runs or comparisons or reruns:
        raise ExperimentConfigurationError(
            "predecessor contains outcomes, evaluator runs, comparisons, or reruns"
        )
    terminal = events[-1]["payload"]
    recorded_failure = finishes[0].get("termination")
    if terminal.get("termination") != recorded_failure:
        raise ExperimentConfigurationError("predecessor stop taxonomy does not match attempt")
    return {
        "attempts_launched": len(starts),
        "valid_completed_cells": valid_completed,
        "evaluator_runs": evaluator_runs,
        "policy_comparisons": comparisons,
        "infrastructure_reruns_recorded": reruns,
        "recorded_attempt_termination": recorded_failure,
        "terminal_state": "batch_stopped",
        "terminal_stop_termination": terminal.get("termination"),
        "terminal_event_sha256": events[-1]["event_sha256"],
        "failed_cell_id": first["cell_id"],
    }


def _validate_integrity_qualification(
    contract: dict[str, Any], qualification: dict[str, Any], terminal_hash: str
) -> None:
    parser = qualification.get("provider_parser", {})
    ledger = qualification.get("ledger", {})
    activity = qualification.get("experimental_activity", {})
    if (
        qualification.get("contract_sha256") != contract["contract_sha256"]
        or qualification.get("repairs_qualified") is not True
        or parser.get("observed_message_only_401_classified_as_provider_infrastructure")
        is not True
        or qualification.get("materialization", {}).get("status") != "pass"
        or ledger.get("terminal_event_sha256") != terminal_hash
        or ledger.get("unchanged") is not True
        or activity.get("pilot_subject_invocations") != 0
        or activity.get("pilot_evaluator_invocations") != 0
        or activity.get("policy_comparisons") != 0
    ):
        raise ExperimentConfigurationError("execution-integrity qualification mismatch")


def build_successor_authorization(
    contract: dict[str, Any],
    predecessor_events: list[dict[str, Any]],
    integrity_qualification: dict[str, Any],
) -> dict[str, Any]:
    """Build the deterministic post-freeze, pre-outcome authorization."""

    contract_without_digest = {
        key: value for key, value in contract.items() if key != "contract_sha256"
    }
    if contract.get("contract_sha256") != digest(contract_without_digest):
        raise ExperimentConfigurationError("original contract digest is invalid")
    facts = _predecessor_facts(contract, predecessor_events)
    _validate_integrity_qualification(
        contract, integrity_qualification, facts["terminal_event_sha256"]
    )
    if UNDERLYING_FAILURE not in RERUNNABLE_INFRASTRUCTURE or UNDERLYING_FAILURE not in set(
        contract["failure_taxonomy"]["same_cell_infrastructure_rerun"]
    ):
        raise ExperimentConfigurationError("frozen rules do not cover the infrastructure cause")
    rerun = contract["trajectory_infrastructure_rerun_budget"]
    if rerun["initial_consumed"] != 0 or rerun["allowance"] < 1:
        raise ExperimentConfigurationError("frozen infrastructure rerun allowance is unavailable")
    if rerun["maximum_attempts_per_cell"] != 2:
        raise ExperimentConfigurationError("frozen same-cell attempt allowance is incompatible")
    first = contract["schedule"]["cells"][0]
    value: dict[str, Any] = {
        "schema_name": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "authorization_version": AUTHORIZATION_VERSION,
        "amendment_class": "post-freeze pre-outcome infrastructure protocol amendment",
        "experimental_contract_unchanged": True,
        "treatment_or_analysis_semantics_changed": False,
        "original_contract": {
            "contract_version": contract["contract_version"],
            "contract_sha256": contract["contract_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "task_pool_sha256": contract["final_pool"]["final_pool_sha256"],
            "baseline_policy_sha256": digest(
                {"arm": "baseline", "intervention_sha256": None}
            ),
            "c_short_version": contract["arms"]["short_policy_version"],
            "c_short_sha256": contract["arms"]["short_policy_sha256"],
            "subject_configuration": contract["subject"],
            "subject_configuration_sha256": digest(contract["subject"]),
            "evaluator_configuration": contract["source_and_evaluator"],
            "evaluator_configuration_sha256": digest(
                contract["source_and_evaluator"]
            ),
        },
        "predecessor": {
            "batch_id": PREDECESSOR_BATCH_ID,
            **facts,
        },
        "successor": {
            "batch_id": SUCCESSOR_BATCH_ID,
            "starting_schedule_position": 1,
            "starting_cell": first,
            "exact_original_schedule": True,
            "new_randomization": False,
            "restart_reason": RESTART_REASON,
        },
        "failure_accounting": {
            "predecessor_recorded_failure_preserved": facts[
                "recorded_attempt_termination"
            ],
            "qualified_underlying_cause": UNDERLYING_FAILURE,
            "underlying_cause_evidence_sha256": digest(integrity_qualification),
            "existing_rerun_allowance": rerun["allowance"],
            "predecessor_reruns_recorded": facts["infrastructure_reruns_recorded"],
            "successor_cell_1_consumes_existing_rerun_units": 1,
            "reruns_consumed_at_successor_start": 1,
            "reruns_remaining_at_successor_start": rerun["allowance"] - 1,
            "successor_cell_1_trajectory_attempt": 2,
            "successor_cells_2_through_48_trajectory_attempt": 1,
            "new_retry_capacity_added": 0,
        },
    }
    value["authorization_sha256"] = digest(value)
    return value


def validate_successor_authorization(
    contract: dict[str, Any],
    predecessor_events: list[dict[str, Any]],
    integrity_qualification: dict[str, Any],
    authorization: dict[str, Any],
) -> None:
    expected = build_successor_authorization(
        contract, predecessor_events, integrity_qualification
    )
    if canonical_bytes(authorization) != canonical_bytes(expected):
        raise ExperimentConfigurationError("successor authorization mismatch")


def successor_genesis_payload(
    contract: dict[str, Any], authorization: dict[str, Any]
) -> dict[str, Any]:
    return {
        "authorization_sha256": authorization["authorization_sha256"],
        "original_contract_sha256": contract["contract_sha256"],
        "predecessor_terminal_event_sha256": authorization["predecessor"][
            "terminal_event_sha256"
        ],
        "successor_batch_id": authorization["successor"]["batch_id"],
    }


def initialize_successor_ledger(
    contract: dict[str, Any], authorization: dict[str, Any], ledger_path: Path
) -> list[dict[str, Any]]:
    """Create a fresh successor chain; an existing path is always an error."""

    if ledger_path.exists():
        raise ExperimentConfigurationError("successor ledger already exists unexpectedly")
    event = {
        "sequence": 1,
        "event_type": SUCCESSOR_GENESIS_EVENT,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "previous_event_sha256": None,
        "payload": successor_genesis_payload(contract, authorization),
    }
    event["event_sha256"] = digest(event)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("xb") as handle:
        handle.write(
            (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        handle.flush()
        os.fsync(handle.fileno())
    append_runner_event(
        ledger_path, "contract_frozen", {"contract_sha256": contract["contract_sha256"]}
    )
    for item in contract["final_pool"]["task_slot_replacement_budget"]["audit_events"]:
        append_runner_event(ledger_path, "task_slot_replaced", item)
    append_runner_event(
        ledger_path,
        "schedule_frozen",
        {
            "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "cells": len(contract["schedule"]["cells"]),
        },
    )
    return read_ledger(ledger_path)


def _validated_successor_runtime(
    contract: dict[str, Any], authorization: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not events or events[0].get("event_type") != SUCCESSOR_GENESIS_EVENT:
        raise ExperimentConfigurationError("successor ledger genesis is absent")
    if events[0].get("payload") != successor_genesis_payload(contract, authorization):
        raise ExperimentConfigurationError("successor ledger genesis mismatch")
    runtime = events[1:]
    _validate_metadata_events(contract, runtime)
    return runtime


def next_successor_legal_action(
    contract: dict[str, Any], authorization: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    runtime = _validated_successor_runtime(contract, authorization, events)
    first_cell_id = authorization["successor"]["starting_cell"]["cell_id"]
    return next_legal_action(
        contract,
        runtime,
        initial_trajectory_attempt=2,
        initial_reruns_consumed=1,
        initially_rerun_cells=frozenset({first_cell_id}),
    )


def validate_successor_start(
    contract: dict[str, Any],
    predecessor_path: Path,
    integrity_qualification: dict[str, Any],
    authorization: dict[str, Any],
    successor_ledger_path: Path,
) -> list[dict[str, Any]]:
    if not predecessor_path.is_file():
        raise ExperimentConfigurationError("predecessor ledger is absent")
    predecessor_events = read_ledger(predecessor_path)
    validate_successor_authorization(
        contract, predecessor_events, integrity_qualification, authorization
    )
    if successor_ledger_path.exists() or (
        successor_ledger_path.parent.exists()
        and any(successor_ledger_path.parent.iterdir())
    ):
        raise ExperimentConfigurationError("successor state already exists unexpectedly")
    return predecessor_events


def successor_dry_run_receipt(
    contract: dict[str, Any],
    root: Path,
    predecessor_path: Path,
    integrity_qualification: dict[str, Any],
    authorization: dict[str, Any],
    successor_state_root: Path,
    resolved_tasks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve the exact schedule and successor accounting without writing state."""

    ledger_path = successor_state_root / SUCCESSOR_LEDGER_NAME
    predecessor_events = validate_successor_start(
        contract,
        predecessor_path,
        integrity_qualification,
        authorization,
        ledger_path,
    )
    base = dry_run_receipt(contract, root, successor_state_root, resolved_tasks)
    cells = []
    for item in base["cells"]:
        attempt = 2 if item["position"] == 1 else 1
        cells.append(
            {
                **item,
                "trajectory_attempt": attempt,
                "attempt_kind": "infrastructure_rerun" if attempt == 2 else "first_attempt",
            }
        )
    return {
        **base,
        "schema_name": "engineering-scope-guard.pilot-successor-batch-dry-run",
        "authorization_sha256": authorization["authorization_sha256"],
        "predecessor_terminal_event_sha256": predecessor_events[-1]["event_sha256"],
        "successor_batch_id": authorization["successor"]["batch_id"],
        "successor_ledger_genesis": successor_genesis_payload(contract, authorization),
        "successor_ledger_written": False,
        "experimental_observations_written": 0,
        "infrastructure_reruns_consumed_at_start": 1,
        "infrastructure_reruns_remaining_at_start": (
            contract["trajectory_infrastructure_rerun_budget"]["allowance"] - 1
        ),
        "cells": cells,
    }


def read_authorization(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ExperimentConfigurationError("successor authorization is not an object")
    return value


def predecessor_file_identity(path: Path) -> dict[str, Any]:
    events = read_ledger(path)
    return {
        "file_sha256": sha256_file(path),
        "events": len(events),
        "terminal_event_sha256": events[-1]["event_sha256"] if events else None,
    }
