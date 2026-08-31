"""Frozen lineage for the externally interrupted Pilot-v2 batch.

This module can validate, authorize, qualify, and initialize an unstarted
continuation ledger. It intentionally has no subject or evaluator executor.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import (
    canonical_bytes,
    classify_receipt,
    digest,
    read_ledger,
    validate_preflight,
)
from .pilot_runner import (
    append_runner_event,
    build_launch_request,
    next_legal_action,
    sha256_file,
)
from .pilot_v2 import validate_contract

SCHEMA = "engineering-scope-guard.pilot-v2-operator-continuation-authorization"
SCHEMA_VERSION = 1
AUTHORIZATION_VERSION = "pilot-v2-operator-continuation-v1.0"
CONTINUATION_ID = "pilot-v2.0-operator-continuation-1"
CONTINUATION_LEDGER_NAME = "pilot-v2-continuation-ledger.jsonl"
GENESIS_EVENT = "operator_continuation_genesis"
DECISION = "CONTINUATION QUALIFIED — EXECUTION REQUIRES SEPARATE AUTHORIZATION"
INTERFACE_DECISION = (
    "CONTINUATION EXECUTION INTERFACE QUALIFIED — "
    "LIVE EXECUTION REQUIRES SEPARATE AUTHORIZATION"
)
CAUSE = "external_user_requested_operational_interruption"
CONTINUATION_PREFLIGHT_SCHEMA = (
    "engineering-scope-guard.pilot-v2-continuation-execution-preflight"
)
CONTINUATION_DRY_RUN_SCHEMA = (
    "engineering-scope-guard.pilot-v2-continuation-execution-dry-run"
)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"{path} is not a JSON object")
    return value


def _validate_source_state(
    root: Path,
    contract: dict[str, Any],
    terminal: dict[str, Any],
    ledger_path: Path,
) -> dict[str, Any]:
    """Validate the interrupted shape without comparing arm outcomes."""

    validate_contract(contract, root)
    events = read_ledger(ledger_path)
    ledger = terminal.get("ledger", {})
    schedule = terminal.get("schedule", {})
    analysis = terminal.get("analysis", {})
    interruption = terminal.get("interruption", {})
    if (
        terminal.get("status") != "externally_interrupted_unresolved_partial"
        or ledger.get("events") != 15
        or ledger.get("sha256") != sha256_file(ledger_path)
        or ledger.get("last_event_sha256") != events[-1].get("event_sha256")
        or ledger.get("last_event_type") != "attempt_started"
        or ledger.get("modified_for_terminal_reporting") is not False
        or schedule.get("admissible_completed_cells") != 6
        or schedule.get("cells_started") != 7
        or schedule.get("unstarted_cells") != 37
        or schedule.get("infrastructure_reruns_consumed") != 0
        or analysis.get("arm_effect_analysis_performed") is not False
        or analysis.get("interim_baseline_vs_short_comparisons") != 0
        or interruption.get("cause_classification") != CAUSE
        or interruption.get("provider_infrastructure_failure_observed") is not False
        or interruption.get("runtime_infrastructure_failure_observed") is not False
        or interruption.get("operator_context_authorizes_continuation") is not False
    ):
        raise ExperimentConfigurationError("terminal interruption evidence mismatch")
    action = next_legal_action(contract, events)
    if action.get("action") != "resolve_partial":
        raise ExperimentConfigurationError("original ledger is not the preserved partial state")
    runtime = events[2:]
    cells = contract["schedule"]["cells"]
    if len(runtime) != 13:
        raise ExperimentConfigurationError("original runtime event count mismatch")
    for offset in range(6):
        started = runtime[offset * 2]
        finished = runtime[offset * 2 + 1]
        cell = cells[offset]
        if (
            started.get("event_type") != "attempt_started"
            or finished.get("event_type") != "attempt_finished"
            or started.get("payload", {}).get("cell_id") != cell["cell_id"]
            or finished.get("payload", {}).get("cell_id") != cell["cell_id"]
            or started.get("payload", {}).get("trajectory_attempt") != 1
            or finished.get("payload", {}).get("trajectory_attempt") != 1
            or not classify_receipt(contract, finished["payload"])[
                "counts_as_experimental_outcome"
            ]
        ):
            raise ExperimentConfigurationError("completed-cell lineage mismatch")
    partial = runtime[-1]
    seventh = cells[6]
    if (
        partial.get("event_type") != "attempt_started"
        or partial.get("payload", {}).get("cell_id") != seventh["cell_id"]
        or partial.get("payload", {}).get("trajectory_attempt") != 1
        or interruption.get("interrupted_cell") != seventh["cell_id"]
        or interruption.get("interrupted_trajectory_attempt") != 1
        or interruption.get("evaluator_result_present") is not False
    ):
        raise ExperimentConfigurationError("interrupted cell-7 lineage mismatch")
    return {
        "ledger_file_sha256": sha256_file(ledger_path),
        "ledger_events": len(events),
        "terminal_event_sha256": events[-1]["event_sha256"],
        "completed_positions": list(range(1, 7)),
        "completed_cell_ids": [cell["cell_id"] for cell in cells[:6]],
        "interrupted_position": 7,
        "interrupted_cell_id": seventh["cell_id"],
        "unstarted_positions": list(range(8, 45)),
    }


def build_authorization(
    root: Path,
    contract_path: Path,
    terminal_path: Path,
    ledger_path: Path,
    *,
    recorded_at: str,
) -> dict[str, Any]:
    """Build the one deterministic continuation authorization."""

    contract = _read_object(contract_path)
    terminal = _read_object(terminal_path)
    facts = _validate_source_state(root, contract, terminal, ledger_path)
    cells = contract["schedule"]["cells"]
    rerun = contract["trajectory_infrastructure_rerun_budget"]
    value: dict[str, Any] = {
        "schema_name": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "authorization_version": AUTHORIZATION_VERSION,
        "recorded_at": recorded_at,
        "status": "frozen-qualified-execution-not-authorized",
        "decision": DECISION,
        "scientific_basis": {
            "interruption_cause": CAUSE,
            "cause_recorded_contemporaneously": True,
            "cause_unrelated_to_arm_or_outcome": True,
            "interim_arm_effect_analysis_performed": False,
            "post_interruption_arm_comparisons": 0,
            "exploratory_only": True,
        },
        "original_contract": {
            "path": "experiment/pilot_v2_execution_contract.json",
            "contract_version": contract["contract_version"],
            "canonical_sha256": contract["contract_sha256"],
            "file_sha256": sha256_file(contract_path),
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
            "unchanged": True,
        },
        "predecessor": {
            "terminal_result_path": "experiment/pilot_v2_terminal_result.json",
            "terminal_result_file_sha256": sha256_file(terminal_path),
            **facts,
            "original_ledger_immutable": True,
        },
        "continuation": {
            "continuation_id": CONTINUATION_ID,
            "separate_ledger_required": True,
            "starting_schedule_position": 7,
            "starting_cell": cells[6],
            "starting_trajectory_attempt": 2,
            "positions_1_through_6": "incorporate predecessor observations without copying or rerun",
            "position_7": "restart whole cell in fresh isolation; retain predecessor attempt 1 as incomplete",
            "positions_8_through_44": "retain exact original identities, order, and first-attempt number",
            "new_randomization": False,
            "execution_authorized": False,
            "execution_interface_present": False,
        },
        "accounting": {
            "category": "operator_interruption_restart",
            "infrastructure_failure_class": False,
            "existing_infrastructure_rerun_allowance": rerun["allowance"],
            "existing_infrastructure_reruns_consumed_at_continuation_start": 0,
            "existing_infrastructure_reruns_remaining_at_continuation_start": rerun[
                "allowance"
            ],
            "existing_infrastructure_budget_changed": False,
            "operator_restart_units_authorized_for_observed_interruption": 1,
            "operator_restart_units_consumed_at_continuation_start": 1,
            "operator_restart_units_remaining": 0,
            "cell_7_maximum_total_attempts": 2,
            "cell_7_additional_rerun_after_attempt_2_permitted": False,
            "cells_8_through_44_existing_rerun_rules_unchanged": True,
        },
        "future_confirmatory_predeclaration": {
            "planned_pauses": "between cells before attempt_started",
            "mid_attempt_interruption_event_must_be_declared": True,
            "cause_must_be_recorded_before_outcome_review": True,
            "operator_restart_allowance_must_be_fixed_before_execution": True,
            "operator_restart_accounting_separate_from_infrastructure": True,
            "restart_uses_next_attempt_number_and_fresh_isolation": True,
            "incomplete_attempt_is_retained_and_never_reclassified": True,
            "maximum_total_attempts_per_cell_across_all_categories": 2,
            "exhausted_allowance_disposition": "stop and preserve incomplete state",
            "interim_effect_review_before_restart_permitted": False,
        },
        "forbidden": [
            "modify_original_ledger",
            "rerun_positions_1_through_6",
            "reclassify_operator_interruption_as_infrastructure",
            "increase_existing_retry_or_rerun_budgets",
            "change_contract_schedule_treatment_model_evaluator_or_analysis",
            "inspect_interim_arm_effects",
            "expose_confirmatory_task_bodies",
            "execute_without_separate_authorization",
        ],
    }
    value["authorization_sha256"] = digest(value)
    return value


def validate_authorization(
    root: Path,
    contract_path: Path,
    terminal_path: Path,
    ledger_path: Path,
    authorization: dict[str, Any],
) -> None:
    expected = build_authorization(
        root,
        contract_path,
        terminal_path,
        ledger_path,
        recorded_at=authorization.get("recorded_at", ""),
    )
    if canonical_bytes(authorization) != canonical_bytes(expected):
        raise ExperimentConfigurationError("continuation authorization mismatch")


def genesis_payload(authorization: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorization_sha256": authorization["authorization_sha256"],
        "continuation_id": authorization["continuation"]["continuation_id"],
        "original_contract_sha256": authorization["original_contract"][
            "canonical_sha256"
        ],
        "original_ledger_file_sha256": authorization["predecessor"][
            "ledger_file_sha256"
        ],
        "predecessor_terminal_event_sha256": authorization["predecessor"][
            "terminal_event_sha256"
        ],
        "starting_schedule_position": 7,
        "starting_trajectory_attempt": 2,
        "operator_restart_units_consumed": 1,
        "execution_authorized": False,
    }


def initialize_continuation_ledger(
    authorization: dict[str, Any], ledger_path: Path
) -> dict[str, Any]:
    """Create the separate one-event lineage ledger; never append to a path."""

    if ledger_path.exists():
        raise ExperimentConfigurationError("continuation ledger already exists")
    event: dict[str, Any] = {
        "sequence": 1,
        "event_type": GENESIS_EVENT,
        "recorded_at": authorization["recorded_at"],
        "previous_event_sha256": None,
        "payload": genesis_payload(authorization),
    }
    event["event_sha256"] = digest(event)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("xb") as handle:
        handle.write(canonical_bytes(event))
        handle.flush()
        os.fsync(handle.fileno())
    return event


def read_continuation_ledger(
    authorization: dict[str, Any], ledger_path: Path
) -> list[dict[str, Any]]:
    """Read the durable chain and validate its immutable genesis."""

    try:
        events = read_ledger(ledger_path)
    except (OSError, UnicodeError) as error:
        raise ExperimentConfigurationError(f"cannot read continuation ledger: {error}") from error
    if not events:
        raise ExperimentConfigurationError("continuation ledger genesis is absent")
    expected = {
        "sequence": 1,
        "event_type": GENESIS_EVENT,
        "recorded_at": authorization["recorded_at"],
        "previous_event_sha256": None,
        "payload": genesis_payload(authorization),
    }
    expected["event_sha256"] = digest(expected)
    if events[0] != expected:
        raise ExperimentConfigurationError("continuation ledger genesis mismatch")
    return events


def validate_continuation_ledger(
    authorization: dict[str, Any], ledger_path: Path
) -> dict[str, Any]:
    """Validate and return the genesis of an unstarted continuation."""

    events = read_continuation_ledger(authorization, ledger_path)
    if len(events) != 1:
        raise ExperimentConfigurationError("continuation ledger must be unstarted genesis only")
    return events[0]


def _continuation_contract_view(contract: dict[str, Any]) -> dict[str, Any]:
    """Return the exact frozen schedule suffix used only by the state reducer."""

    view = copy.deepcopy(contract)
    view["schedule"]["cells"] = copy.deepcopy(contract["schedule"]["cells"][6:])
    return view


def _runner_runtime_events(
    contract: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Add the runner's metadata prefix in memory; never copy it into the ledger."""

    view = _continuation_contract_view(contract)
    return [
        {
            "event_type": "contract_frozen",
            "payload": {"contract_sha256": contract["contract_sha256"]},
        },
        {
            "event_type": "schedule_frozen",
            "payload": {
                "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
                "schedule_sha256": contract["schedule"]["schedule_sha256"],
                "cells": len(view["schedule"]["cells"]),
            },
        },
        *events[1:],
    ]


def next_continuation_legal_action(
    contract: dict[str, Any],
    authorization: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive the sole future action from durable continuation evidence."""

    if not events or events[0].get("payload") != genesis_payload(authorization):
        raise ExperimentConfigurationError("continuation ledger genesis mismatch")
    view = _continuation_contract_view(contract)
    first_cell_id = authorization["continuation"]["starting_cell"]["cell_id"]
    if view["schedule"]["cells"][0]["cell_id"] != first_cell_id:
        raise ExperimentConfigurationError("continuation schedule start mismatch")
    return next_legal_action(
        view,
        _runner_runtime_events(contract, events),
        initial_trajectory_attempt=2,
        initial_reruns_consumed=0,
        initially_rerun_cells=frozenset({first_cell_id}),
    )


def strict_continuation_preflight(
    root: Path,
    contract_path: Path,
    terminal_path: Path,
    predecessor_ledger_path: Path,
    continuation_ledger_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    """Validate every lineage dependency without invoking a subject/evaluator."""

    validate_authorization(
        root, contract_path, terminal_path, predecessor_ledger_path, authorization
    )
    events = read_continuation_ledger(authorization, continuation_ledger_path)
    contract = _read_object(contract_path)
    action = next_continuation_legal_action(contract, authorization, events)
    if action.get("action") == "launch" and action["cell"]["position"] < 7:
        raise ExperimentConfigurationError("predecessor position became executable")
    state_root = continuation_ledger_path.parent
    stale_auth = sorted(state_root.glob("attempts/*/*/codex-home/auth.json"))
    if stale_auth:
        raise ExperimentConfigurationError(
            "trajectory-local authentication remains in continuation state"
        )
    return {
        "schema_name": CONTINUATION_PREFLIGHT_SCHEMA,
        "schema_version": 1,
        "status": "pass",
        "authorization_sha256": authorization["authorization_sha256"],
        "contract_file_sha256": sha256_file(contract_path),
        "predecessor_ledger_file_sha256": sha256_file(predecessor_ledger_path),
        "continuation_ledger_file_sha256": sha256_file(continuation_ledger_path),
        "continuation_events": len(events),
        "next_legal_action": action["action"],
        "next_position": action.get("cell", {}).get("position"),
        "next_trajectory_attempt": action.get("trajectory_attempt"),
        "completed_predecessor_positions": list(range(1, 7)),
        "operator_restart_units_remaining": authorization["accounting"][
            "operator_restart_units_remaining"
        ],
        "infrastructure_reruns_consumed": sum(
            event.get("event_type") == "infrastructure_rerun_authorized"
            for event in events[1:]
        ),
        "infrastructure_rerun_allowance": authorization["accounting"][
            "existing_infrastructure_rerun_allowance"
        ],
        "stale_trajectory_credentials": 0,
        "execute_marker_present": (
            state_root / "REAL_CONTINUATION_EXECUTE_INVOKED"
        ).exists(),
        "subject_invocations": 0,
        "evaluator_invocations": 0,
    }


def continuation_dry_run_receipt(
    root: Path,
    contract_path: Path,
    terminal_path: Path,
    predecessor_ledger_path: Path,
    continuation_ledger_path: Path,
    authorization: dict[str, Any],
    attempt_state_root: Path,
) -> dict[str, Any]:
    """Resolve the exact remaining launch envelopes without writing state."""

    preflight = strict_continuation_preflight(
        root,
        contract_path,
        terminal_path,
        predecessor_ledger_path,
        continuation_ledger_path,
        authorization,
    )
    events = read_continuation_ledger(authorization, continuation_ledger_path)
    if len(events) != 1:
        raise ExperimentConfigurationError("complete dry-run requires genesis-only state")
    contract = _read_object(contract_path)
    cells = []
    prior_requests: list[dict[str, Any]] = []
    for cell in contract["schedule"]["cells"][6:]:
        attempt = 2 if cell["position"] == 7 else 1
        request = build_launch_request(contract, cell, attempt_state_root, attempt)
        validate_preflight(contract, request, tuple(prior_requests))
        prior_requests.append(request)
        cells.append(
            {
                "position": cell["position"],
                "cell_id": cell["cell_id"],
                "requested_task_slot": cell["requested_task_slot"],
                "actual_task_id": cell["actual_task_id"],
                "arm": cell["arm"],
                "repetition": cell["repetition"],
                "trajectory_attempt": attempt,
                "attempt_kind": (
                    "operator_interruption_restart"
                    if cell["position"] == 7
                    else "first_attempt"
                ),
                "task_snapshot_sha256": request["task_snapshot_sha256"],
                "intervention_sha256": request["intervention_sha256"],
                "isolation_roots_relative": {
                    name: (
                        f"attempts/{cell['cell_id']}/attempt-{attempt}/{name.replace('_', '-')}"
                    )
                    for name in request["isolation_roots"]
                },
                "evaluator_output_roots_relative": [
                    f"attempts/{cell['cell_id']}/attempt-{attempt}/raw/evaluator-round-0",
                    f"attempts/{cell['cell_id']}/attempt-{attempt}/raw/evaluator-round-1",
                ],
            }
        )
    return {
        "schema_name": CONTINUATION_DRY_RUN_SCHEMA,
        "schema_version": 1,
        "status": "pass",
        "decision": INTERFACE_DECISION,
        "authorization_sha256": authorization["authorization_sha256"],
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "preflight": preflight,
        "positions_resolved": len(cells),
        "positions_1_through_6_executable": False,
        "operator_restart_units_remaining": 0,
        "infrastructure_rerun_allowance": authorization["accounting"][
            "existing_infrastructure_rerun_allowance"
        ],
        "infrastructure_reruns_consumed": 0,
        "codex_invocations": 0,
        "evaluator_invocations": 0,
        "pilot_cells_executed": 0,
        "policy_comparisons_executed": 0,
        "ledger_modified": False,
        "cells": cells,
    }


def append_continuation_event(
    ledger_path: Path, event_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Durably checkpoint one continuation transition before aggregation."""

    if event_type not in {
        "attempt_started",
        "attempt_finished",
        "infrastructure_rerun_authorized",
        "deviation",
        "batch_stopped",
    }:
        raise ExperimentConfigurationError("unsupported continuation event type")
    return append_runner_event(ledger_path, event_type, payload)


def continuation_execution_confirmation(authorization: dict[str, Any]) -> str:
    """Return the exact separately supplied live-execution confirmation."""

    return "execute-pilot-v2-continuation:" + authorization["authorization_sha256"]


def build_qualification(
    root: Path,
    contract_path: Path,
    terminal_path: Path,
    predecessor_ledger_path: Path,
    continuation_ledger_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    """Return a body-free zero-call qualification of the frozen lineage."""

    validate_authorization(
        root, contract_path, terminal_path, predecessor_ledger_path, authorization
    )
    genesis = validate_continuation_ledger(authorization, continuation_ledger_path)
    contract = _read_object(contract_path)
    cells = contract["schedule"]["cells"]
    return {
        "schema_name": "engineering-scope-guard.pilot-v2-operator-continuation-qualification",
        "schema_version": 1,
        "status": "pass",
        "decision": DECISION,
        "authorization_sha256": authorization["authorization_sha256"],
        "continuation_ledger": {
            "events": 1,
            "file_sha256": sha256_file(continuation_ledger_path),
            "genesis_event_sha256": genesis["event_sha256"],
            "unstarted": True,
        },
        "source_immutability": {
            "contract_file_sha256": sha256_file(contract_path),
            "predecessor_ledger_file_sha256": sha256_file(predecessor_ledger_path),
            "matches_authorization": True,
        },
        "schedule": {
            "completed_positions_retained": list(range(1, 7)),
            "restart": {
                "position": 7,
                "cell_id": cells[6]["cell_id"],
                "trajectory_attempt": 2,
                "accounting_category": "operator_interruption_restart",
            },
            "unstarted_positions_retained": [
                {"position": cell["position"], "cell_id": cell["cell_id"], "trajectory_attempt": 1}
                for cell in cells[7:]
            ],
        },
        "activity": {
            "subject_calls": 0,
            "evaluator_calls": 0,
            "pilot_cells_executed": 0,
            "interim_arm_effect_analyses": 0,
            "confirmatory_task_bodies_exposed": 0,
        },
        "checks": {
            "original_contract_unchanged": True,
            "original_ledger_unchanged": True,
            "completed_cells_not_repeated": True,
            "schedule_identities_unchanged": True,
            "existing_rerun_budget_unchanged": True,
            "cell_7_has_no_third_attempt": True,
            "execution_not_authorized": True,
        },
    }


def read_authorization(path: Path) -> dict[str, Any]:
    return _read_object(path)
