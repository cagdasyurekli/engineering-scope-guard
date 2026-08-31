"""Frozen, Pilot-specific execution-contract and ledger machinery.

This module prepares and validates an execution plan. It never launches Codex,
an evaluator, Docker, or a policy-comparison cell.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError, USAGE_COMPONENTS

SCHEMA = "engineering-scope-guard.pilot-execution-contract"
CONTRACT_VERSION = "pilot-v1.0"
SCHEDULE_SEED = "engineering-scope-guard-pilot-order-v1-2026-08-28"
ARMS = ("baseline", "short")
REPETITIONS = 2
TASK_SLOT_REPLACEMENT_ALLOWANCE = 8
TRAJECTORY_INFRASTRUCTURE_RERUN_ALLOWANCE = 8
MAX_TRAJECTORY_ATTEMPTS_PER_CELL = 2

EXPERIMENTAL_OUTCOMES = {
    "accepted_completed",
    "evaluator_test_failure",
    "agent_subject_failure",
    "trajectory_timeout",
}
RERUNNABLE_INFRASTRUCTURE = {
    "provider_api_infrastructure_failure",
    "local_docker_runtime_infrastructure_failure",
}
BATCH_STOP_FAILURES = {
    "harness_failure",
    "isolation_contract_violation",
    "malformed_incomplete_measurement",
}
ALL_TERMINATIONS = (
    EXPERIMENTAL_OUTCOMES | RERUNNABLE_INFRASTRUCTURE | BATCH_STOP_FAILURES
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected a JSON object in {path}")
    return value


def _rank(seed: str, *parts: str) -> str:
    return hashlib.sha256("\0".join((seed, *parts)).encode()).hexdigest()


def resolve_final_pool(host: dict[str, Any], partition: dict[str, Any]) -> dict[str, Any]:
    """Resolve original slots through completed, pre-treatment qualification."""

    if host.get("status") != "complete" or host.get("policy_arm_runs") != 0:
        raise ExperimentConfigurationError("host qualification is not complete and pre-treatment")
    originals = partition["partition"]["pilot_tasks"]
    tasks = {item["instance_id"]: item for item in host["tasks"]}
    replacements = {
        item["replaces"]: item for item in host["tasks"] if item.get("replaces")
    }
    slots = []
    for number, original in enumerate(originals, start=1):
        original_id = original["instance_id"]
        selected = replacements.get(original_id, tasks[original_id])
        if selected.get("host_validity") != "host-valid":
            raise ExperimentConfigurationError(f"Pilot slot {number} is not host-valid")
        task_identity = {
            "dataset_revision": host["source"]["dataset_revision"],
            "instance_id": selected["instance_id"],
            "official_image": selected["official_image"],
        }
        slots.append(
            {
                "slot": number,
                "original_task_id": original_id,
                "actual_task_id": selected["instance_id"],
                "repo": selected.get("replacement_repo", selected.get("repo", original["repo"])),
                "language": selected.get("language", original["language"]),
                "task_snapshot_sha256": digest(task_identity),
            }
        )
    if len(slots) != 12 or len({item["actual_task_id"] for item in slots}) != 12:
        raise ExperimentConfigurationError("final Pilot pool must contain 12 distinct tasks")
    audit = host["replacement_rule"]["audit_trail"]
    value = {
        "canonicalization": "slot-order; sorted-key compact JSON; trailing LF",
        "slots": slots,
        "task_slot_replacement_budget": {
            "unit": "pre-treatment Pilot task slot",
            "allowance": TASK_SLOT_REPLACEMENT_ALLOWANCE,
            "consumed": host["replacement_rule"]["consumed"],
            "remaining": TASK_SLOT_REPLACEMENT_ALLOWANCE - host["replacement_rule"]["consumed"],
            "remaining_authority_after_finalization": 0,
            "audit_events": [
                {
                    "event": "task_slot_replaced",
                    "original_task_id": item["invalid_task"],
                    "actual_task_id": item["replacement_task"],
                    "reason": item["invalid_host_validity"],
                    "reserve_rank_commitment": item["rank_commitment"],
                }
                for item in audit
            ],
            "finalized_before_schedule": True,
            "later_change_requires_new_contract": True,
        },
    }
    value["final_pool_sha256"] = digest(value["slots"])
    return value


def generate_schedule(pool_sha256: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
    cells = []
    position = 0
    for repetition in range(1, REPETITIONS + 1):
        ordered = sorted(
            slots,
            key=lambda item: _rank(
                SCHEDULE_SEED, CONTRACT_VERSION, pool_sha256, str(repetition), str(item["slot"])
            ),
        )
        for task in ordered:
            arm_order = sorted(
                ARMS,
                key=lambda arm: _rank(
                    SCHEDULE_SEED,
                    CONTRACT_VERSION,
                    pool_sha256,
                    str(repetition),
                    str(task["slot"]),
                    arm,
                ),
            )
            for arm in arm_order:
                position += 1
                cells.append(
                    {
                        "position": position,
                        "cell_id": f"slot-{task['slot']:02d}-{arm}-rep-{repetition}",
                        "requested_task_slot": task["slot"],
                        "actual_task_id": task["actual_task_id"],
                        "arm": arm,
                        "repetition": repetition,
                    }
                )
    value = {
        "algorithm": "sha256-ranked repetition blocks with per-slot arm interleaving",
        "seed": SCHEDULE_SEED,
        "contract_version": CONTRACT_VERSION,
        "final_pool_sha256": pool_sha256,
        "arms": list(ARMS),
        "repetitions_per_task_arm": REPETITIONS,
        "manual_edits_permitted": False,
        "cells": cells,
    }
    value["schedule_sha256"] = digest(value["cells"])
    return value


def build_contract(root: Path) -> dict[str, Any]:
    host = read_object(root / "experiment/pilot_host_qualification.json")
    partition = read_object(root / "experiment/external_task_partition.json")
    runtime = read_object(root / "experiment/evaluator_runtime_readiness.json")
    prior = read_object(root / "experiment/pilot_readiness.json")
    pool = resolve_final_pool(host, partition)
    schedule = generate_schedule(pool["final_pool_sha256"], pool["slots"])
    short_path = root / "experiment/arms/short.txt"
    short_hash = hashlib.sha256(short_path.read_bytes()).hexdigest()
    subject = prior["subject_configuration"]
    value: dict[str, Any] = {
        "schema_name": SCHEMA,
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "status": "frozen-qualified-not-executed",
        "pilot_authorized_by_manifest": False,
        "pilot_policy_comparison_runs": 0,
        "final_pool": pool,
        "arms": {
            "ids": list(ARMS),
            "baseline_intervention": None,
            "short_policy_version": "C-short v0.1",
            "short_policy_sha256": short_hash,
        },
        "subject": {
            "codex_version": runtime["fixed_subject"]["codex_version"],
            "model": runtime["fixed_subject"]["model"],
            "reasoning_effort": runtime["fixed_subject"]["reasoning_effort"],
            "permissions": subject["permissions"],
            "required_agent_tools": subject["required_agent_tools"],
            "network_or_browser_tools": [],
            "mcp_servers": [],
            "plugins": [],
            "hooks": [],
            "user_config_loaded": False,
            "user_rules_loaded": False,
            "configuration_change_during_trajectory_permitted": False,
        },
        "source_and_evaluator": {
            "dataset": host["source"]["dataset"],
            "dataset_revision": host["source"]["dataset_revision"],
            "evaluator_identity": "SWE-bench-Live/MultiLang official evaluator",
            "evaluator_revision": host["source"]["evaluator_revision"],
            "repolaunch_revision": host["source"]["repolaunch_revision"],
            "workers": host["procedure"]["workers"],
        },
        "platform": host["fixed_environment"],
        "trajectory": {
            "maximum_turns": 2,
            "timeout_seconds_per_turn": 900,
            "timeout_seconds_per_trajectory_attempt": 1800,
            "initial_round": 0,
            "maximum_corrective_rounds": 1,
            "corrective_round": 1,
            "corrective_trigger": "initial evaluator_test_failure only",
            "corrective_feedback": "failing check names only, once, identically across arms",
            "session_rule": "fresh per cell; retain only within one trajectory attempt",
            "end_conditions": [
                "accepted_completed",
                "second evaluator result",
                "agent_subject_failure",
                "trajectory_timeout",
                "infrastructure-invalid attempt",
                "batch-stop failure",
            ],
        },
        "failure_taxonomy": {
            "experimental_outcomes": sorted(EXPERIMENTAL_OUTCOMES),
            "same_cell_infrastructure_rerun": sorted(RERUNNABLE_INFRASTRUCTURE),
            "stop_batch": sorted(BATCH_STOP_FAILURES),
            "post_outcome_reclassification_permitted": False,
        },
        "trajectory_infrastructure_rerun_budget": {
            "unit": "invalid execution attempt for the same task x arm x repetition cell",
            "allowance": TRAJECTORY_INFRASTRUCTURE_RERUN_ALLOWANCE,
            "initial_consumed": 0,
            "maximum_attempts_per_cell": MAX_TRAJECTORY_ATTEMPTS_PER_CELL,
            "task_or_arm_change_permitted": False,
            "failed_attempt_retained": True,
        },
        "isolation": {
            "controlled": [
                "fresh repository copy per cell and attempt",
                "distinct conversation/session and Codex home per cell and attempt",
                "distinct raw/derived experiment output per cell and attempt",
                "baseline has no intervention; short receives only frozen policy bytes",
                "no state root may be reused by another cell or attempt",
            ],
            "observed_per_attempt": [
                "repository start fingerprint",
                "Codex home identity digest",
                "raw and derived output identity digests",
                "intervention digest or null",
                "available provider cached-input token count",
            ],
            "unavailable": [
                "provider-side cache isolation guarantee",
                "cache-write tokens",
                "backend model snapshot",
                "provider-billed amount and currency",
            ],
            "provider_unknowns_are_limitations": True,
        },
        "usage": {
            "required_provider_reported_fields": list(USAGE_COMPONENTS[:-1]),
            "required_derived_field": "total_tokens",
            "unavailable_fields": [
                "cache_write_tokens",
                "provider_billed_amount",
                "currency",
                "backend_model_snapshot",
            ],
            "calculated_cost_must_be_labeled_not_provider_reported": True,
        },
        "receipt_required_fields": [
            "cell_id", "contract_sha256", "final_pool_sha256", "schedule_sha256",
            "requested_task_slot", "actual_task_id", "task_snapshot_sha256", "arm", "repetition",
            "trajectory_attempt", "subject", "started_at", "ended_at",
            "termination", "evaluator_result", "usage", "usage_complete",
            "isolation_roots", "intervention_sha256", "source_and_evaluator",
            "platform", "trajectory_contract", "isolation_contract", "usage_contract",
            "admissible_under_contract", "deviations",
        ],
        "ledger": {
            "format": "JSONL hash chain",
            "append_only_in_meaning": True,
            "event_types": [
                "contract_frozen", "task_slot_replaced", "schedule_frozen",
                "attempt_started", "attempt_finished", "infrastructure_rerun_authorized",
                "deviation", "batch_stopped",
            ],
            "raw_task_prompt_or_source_content_permitted": False,
        },
        "schedule": schedule,
        "qualification": {
            "fixtures_or_no_op_only": True,
            "pilot_cells_executed": 0,
            "policy_comparisons_executed": 0,
        },
    }
    value["contract_sha256"] = digest(value)
    return value


def validate_contract(contract: dict[str, Any], root: Path) -> None:
    expected = build_contract(root)
    if canonical_bytes(contract) != canonical_bytes(expected):
        raise ExperimentConfigurationError("frozen Pilot contract mismatch; refusing to normalize")


def validate_preflight(
    contract: dict[str, Any],
    request: dict[str, Any],
    prior_receipts: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """Reject any launch envelope that differs from its scheduled cell."""

    cells = {cell["cell_id"]: cell for cell in contract["schedule"]["cells"]}
    cell = cells.get(request.get("cell_id"))
    if cell is None:
        raise ExperimentConfigurationError("cell is absent from the frozen schedule")
    required = {
        "requested_task_slot": cell["requested_task_slot"],
        "actual_task_id": cell["actual_task_id"],
        "arm": cell["arm"],
        "repetition": cell["repetition"],
        "subject": contract["subject"],
        "contract_sha256": contract["contract_sha256"],
        "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "source_and_evaluator": contract["source_and_evaluator"],
        "platform": contract["platform"],
        "trajectory_contract": contract["trajectory"],
        "isolation_contract": contract["isolation"],
        "usage_contract": contract["usage"],
    }
    slot = next(
        item for item in contract["final_pool"]["slots"]
        if item["slot"] == cell["requested_task_slot"]
    )
    required["task_snapshot_sha256"] = slot["task_snapshot_sha256"]
    mismatches = [name for name, expected in required.items() if request.get(name) != expected]
    roots = request.get("isolation_roots", {})
    root_values = list(roots.values()) if isinstance(roots, dict) else []
    if len(root_values) != 4 or len(root_values) != len(set(root_values)):
        mismatches.append("isolation_roots")
    previously_used = {
        value
        for receipt in prior_receipts
        for value in receipt.get("isolation_roots", {}).values()
    }
    if previously_used.intersection(root_values):
        mismatches.append("reused_isolation_root")
    expected_intervention = (
        None if cell["arm"] == "baseline" else contract["arms"]["short_policy_sha256"]
    )
    if request.get("intervention_sha256") != expected_intervention:
        mismatches.append("intervention_sha256")
    if mismatches:
        raise ExperimentConfigurationError(
            "preflight contract mismatch: " + ", ".join(sorted(set(mismatches)))
        )
    return cell


def classify_receipt(contract: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in contract["receipt_required_fields"] if field not in receipt]
    if missing:
        raise ExperimentConfigurationError("receipt missing fields: " + ", ".join(missing))
    validate_preflight(contract, receipt)
    termination = receipt["termination"]
    if termination not in ALL_TERMINATIONS:
        raise ExperimentConfigurationError(f"unknown termination classification: {termination}")
    usage = receipt["usage"]
    usage_complete = all(
        isinstance(usage.get(name), int) and usage[name] >= 0
        for name in contract["usage"]["required_provider_reported_fields"]
    ) and isinstance(usage.get("total_tokens"), int)
    if receipt["usage_complete"] is not usage_complete:
        raise ExperimentConfigurationError("usage completeness flag contradicts receipt")
    if termination in EXPERIMENTAL_OUTCOMES and not usage_complete:
        raise ExperimentConfigurationError(
            "experimental outcome with incomplete usage must be classified malformed"
        )
    if receipt["trajectory_attempt"] not in (1, 2):
        raise ExperimentConfigurationError("trajectory attempt is outside the frozen allowance")
    if not isinstance(receipt["evaluator_result"], dict) or not isinstance(receipt["deviations"], list):
        raise ExperimentConfigurationError("receipt evaluator result or deviations are malformed")
    try:
        started = datetime.fromisoformat(receipt["started_at"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(receipt["ended_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ExperimentConfigurationError("receipt timestamps are malformed") from error
    if started.tzinfo is None or ended.tzinfo is None or ended < started:
        raise ExperimentConfigurationError("receipt timestamps are unordered or timezone-naive")
    resolved = receipt["evaluator_result"].get("resolved")
    if termination == "accepted_completed" and resolved is not True:
        raise ExperimentConfigurationError("accepted outcome lacks a passing evaluator result")
    if termination == "evaluator_test_failure" and resolved is not False:
        raise ExperimentConfigurationError("evaluator failure lacks a failing evaluator result")
    expected_admissible = termination in EXPERIMENTAL_OUTCOMES and usage_complete
    if receipt["admissible_under_contract"] is not expected_admissible:
        raise ExperimentConfigurationError("attempt admissibility contradicts frozen taxonomy")
    return {
        "counts_as_experimental_outcome": termination in EXPERIMENTAL_OUTCOMES,
        "same_cell_rerun_permitted": termination in RERUNNABLE_INFRASTRUCTURE,
        "stop_batch": termination in BATCH_STOP_FAILURES,
        "usage_complete": usage_complete,
        "admissible": expected_admissible,
    }


def infrastructure_rerun_state(
    contract: dict[str, Any], ledger_events: list[dict[str, Any]], receipt: dict[str, Any]
) -> dict[str, int]:
    classification = classify_receipt(contract, receipt)
    if not classification["same_cell_rerun_permitted"]:
        raise ExperimentConfigurationError("termination cannot consume infrastructure rerun budget")
    consumed = sum(
        event.get("event_type") == "infrastructure_rerun_authorized" for event in ledger_events
    )
    if consumed >= contract["trajectory_infrastructure_rerun_budget"]["allowance"]:
        raise ExperimentConfigurationError("trajectory infrastructure rerun budget exhausted")
    attempt = receipt["trajectory_attempt"]
    if attempt >= contract["trajectory_infrastructure_rerun_budget"]["maximum_attempts_per_cell"]:
        raise ExperimentConfigurationError("same cell has exhausted its attempt allowance")
    if any(
        event.get("event_type") == "infrastructure_rerun_authorized"
        and event.get("payload", {}).get("cell_id") == receipt["cell_id"]
        for event in ledger_events
    ):
        raise ExperimentConfigurationError("same cell already consumed its infrastructure rerun")
    allowance = contract["trajectory_infrastructure_rerun_budget"]["allowance"]
    return {
        "consumed": consumed + 1,
        "remaining": allowance - consumed - 1,
        "next_attempt": attempt + 1,
    }


def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    previous = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError(f"malformed ledger line {number}") from error
        recorded_hash = event.pop("event_sha256", None)
        if event.get("sequence") != number or event.get("previous_event_sha256") != previous:
            raise ExperimentConfigurationError(f"ledger chain mismatch at line {number}")
        calculated = digest(event)
        if recorded_hash != calculated:
            raise ExperimentConfigurationError(f"ledger digest mismatch at line {number}")
        event["event_sha256"] = recorded_hash
        events.append(event)
        previous = recorded_hash
    return events


def append_ledger_event(path: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    events = read_ledger(path)
    if event_type not in {
        "contract_frozen", "task_slot_replaced", "schedule_frozen", "attempt_started",
        "attempt_finished", "infrastructure_rerun_authorized", "deviation", "batch_stopped",
    }:
        raise ExperimentConfigurationError(f"unknown ledger event type: {event_type}")
    event = {
        "sequence": len(events) + 1,
        "event_type": event_type,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "previous_event_sha256": events[-1]["event_sha256"] if events else None,
        "payload": payload,
    }
    event["event_sha256"] = digest(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
    return event
