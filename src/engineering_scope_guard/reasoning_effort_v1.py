"""Provider-free contract, schedule, ledger, and usage rules for effort-v1.

The module deliberately has no runner boundary.  It freezes identities and
validates durable evidence before a separate, explicitly authorized adapter
may launch a subject execution.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import canonical_bytes, digest

SCHEMA_NAME = "engineering-scope-guard.reasoning-effort-experiment"
SCHEMA_VERSION = 1
CONTRACT_VERSION = "reasoning-effort-v1.0"
SCHEDULE_SEED = "engineering-scope-guard-reasoning-effort-v1-order-2026-08-30"
ARMS = ("low", "medium")
TASK_COUNT = 8
REPETITIONS = 2
CELL_COUNT = TASK_COUNT * len(ARMS) * REPETITIONS
MAXIMUM_ATTEMPTS_PER_CELL = 2
MAXIMUM_SUBJECT_EXECUTIONS = 64
MAXIMUM_QUALIFICATION_EXECUTIONS = 4
USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
USAGE_MEASUREMENT_SCOPE = "fresh_session_cumulative_final"
EXPERIMENTAL_OUTCOMES = (
    "accepted_completed",
    "evaluator_test_failure",
    "empty_patch_failure",
    "agent_subject_failure",
    "trajectory_timeout",
)
RETRYABLE_INFRASTRUCTURE = (
    "provider_api_infrastructure_failure",
    "local_docker_runtime_infrastructure_failure",
    "official_evaluator_error",
    "official_evaluator_incomplete",
)
BATCH_STOP_CLASSES = (
    "harness_failure",
    "isolation_contract_violation",
    "malformed_inconsistent_measurement",
    "durable_evidence_incomplete",
)
DEFAULT_QUESTION = (
    "For current-runtime repository tasks, does medium rather than low native "
    "reasoning effort change official acceptance or measured subject work?"
)
DEFAULT_HYPOTHESIS = (
    "Medium reasoning effort may improve official acceptance but may increase "
    "token use, wall time, turns, and observed work relative to low effort."
)


def _rank(*parts: str) -> str:
    return hashlib.sha256("\0".join((SCHEDULE_SEED, *parts)).encode()).hexdigest()


def _sealed(value: dict[str, Any], identity_field: str) -> dict[str, Any]:
    result = dict(value)
    result[identity_field] = digest(value)
    return result


def _identity_matches(value: dict[str, Any], identity_field: str) -> bool:
    recorded = value.get(identity_field)
    body = {key: item for key, item in value.items() if key != identity_field}
    return isinstance(recorded, str) and recorded == digest(body)


def _normalize_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"task_id", "repository", "task_snapshot_sha256"}
    if len(tasks) != TASK_COUNT or any(set(task) != required for task in tasks):
        raise ExperimentConfigurationError("effort-v1 requires exactly eight identity-only tasks")
    if any(
        not isinstance(task[field], str) or not task[field]
        for task in tasks
        for field in required
    ):
        raise ExperimentConfigurationError("task identities must be non-empty strings")
    if any(
        len(task["task_snapshot_sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in task["task_snapshot_sha256"])
        for task in tasks
    ):
        raise ExperimentConfigurationError("task snapshot identities must be lowercase SHA-256")
    if len({task["task_id"] for task in tasks}) != TASK_COUNT:
        raise ExperimentConfigurationError("effort-v1 tasks must be distinct")
    if len({task["repository"] for task in tasks}) != TASK_COUNT:
        raise ExperimentConfigurationError("effort-v1 repositories must be distinct")
    ordered = sorted(tasks, key=lambda task: (_rank("pool", task["task_id"]), task["task_id"]))
    return [{"slot": slot, **task} for slot, task in enumerate(ordered, start=1)]


def generate_schedule(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Build 32 cells with an AB/BA arm order within every task."""

    slots = _normalize_tasks(tasks)
    pool_sha256 = digest(slots)
    first_arm = {
        slot["slot"]: min(ARMS, key=lambda arm: _rank(pool_sha256, str(slot["slot"]), arm))
        for slot in slots
    }
    cells: list[dict[str, Any]] = []
    for repetition in range(1, REPETITIONS + 1):
        ordered = sorted(
            slots,
            key=lambda slot: (
                _rank(pool_sha256, "repetition", str(repetition), str(slot["slot"])),
                slot["slot"],
            ),
        )
        for slot in ordered:
            arm_order = [
                first_arm[slot["slot"]],
                next(arm for arm in ARMS if arm != first_arm[slot["slot"]]),
            ]
            if repetition == 2:
                arm_order.reverse()
            for arm in arm_order:
                cells.append(
                    {
                        "position": len(cells) + 1,
                        "cell_id": f"effort-v1-slot-{slot['slot']:02d}-{arm}-rep-{repetition}",
                        "task_slot": slot["slot"],
                        "task_id": slot["task_id"],
                        "repository": slot["repository"],
                        "arm": arm,
                        "reasoning_effort": arm,
                        "repetition": repetition,
                    }
                )
    schedule = {
        "schema_name": f"{SCHEMA_NAME}.schedule",
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "algorithm": "SHA-256-ranked repetition blocks; per-task AB/BA counterbalancing",
        "seed": SCHEDULE_SEED,
        "pool_sha256": pool_sha256,
        "tasks": slots,
        "arms": list(ARMS),
        "repetitions_per_task_arm": REPETITIONS,
        "cells": cells,
        "manual_edits_permitted": False,
    }
    return _sealed(schedule, "schedule_sha256")


def build_contract(
    tasks: list[dict[str, Any]],
    *,
    model: str,
    codex_version: str,
    runtime_identity: str,
    source_revision: str,
    evaluator_revision: str,
    qualification_subject_executions: int = 0,
    research_question: str = DEFAULT_QUESTION,
    hypothesis: str = DEFAULT_HYPOTHESIS,
    dataset_identity: str | None = None,
    evaluator_identity: str = "official task-source evaluator",
    repolaunch_revision: str = "provider-free-not-materialized",
    image_pool_identity: str | None = None,
    expected_pool_sha256: str | None = None,
) -> dict[str, Any]:
    """Freeze the experiment without granting live-execution authority."""

    identities = (
        model,
        codex_version,
        runtime_identity,
        source_revision,
        evaluator_revision,
        research_question,
        hypothesis,
        dataset_identity or source_revision,
        evaluator_identity,
        repolaunch_revision,
    )
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ExperimentConfigurationError("frozen runtime/source identities must be non-empty")
    if (
        not isinstance(qualification_subject_executions, int)
        or isinstance(qualification_subject_executions, bool)
        or not 0 <= qualification_subject_executions <= MAXIMUM_QUALIFICATION_EXECUTIONS
    ):
        raise ExperimentConfigurationError("qualification subject-execution count is invalid")
    schedule = generate_schedule(tasks)
    if expected_pool_sha256 is not None and expected_pool_sha256 != schedule["pool_sha256"]:
        raise ExperimentConfigurationError("passed pool identity does not match selected tasks")
    resolved_image_pool = image_pool_identity or digest(
        [task["task_snapshot_sha256"] for task in schedule["tasks"]]
    )
    if not isinstance(resolved_image_pool, str) or not resolved_image_pool:
        raise ExperimentConfigurationError("image-pool identity must be non-empty")
    contract = {
        "schema_name": f"{SCHEMA_NAME}.contract",
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": "frozen-provider-free-live-execution-not-authorized",
        "live_execution_authorized": False,
        "scientific_question": {
            "question": research_question,
            "directional_hypothesis": hypothesis,
            "frozen_before_outcomes": True,
        },
        "subject": {
            "model": model,
            "codex_version": codex_version,
            "runtime_identity": runtime_identity,
            "only_variable": "reasoning_effort",
            "arms": {arm: {"reasoning_effort": arm} for arm in ARMS},
            "configuration_change_within_arm_permitted": False,
            "baseline": {
                "arm": "low",
                "semantics": "native reasoning_effort=low; no other configuration difference",
            },
            "treatment": {
                "arm": "medium",
                "semantics": "native reasoning_effort=medium; no other configuration difference",
            },
        },
        "source": {
            "dataset_identity": dataset_identity or source_revision,
            "dataset_revision": source_revision,
            "pool_sha256": schedule["pool_sha256"],
            "image_pool_identity": resolved_image_pool,
            "repolaunch_revision": repolaunch_revision,
            "evaluator_identity": evaluator_identity,
            "evaluator_revision": evaluator_revision,
            "post_outcome_task_or_image_replacement_permitted": False,
        },
        "schedule": schedule,
        "trajectory": {
            "subject_invocations_per_cell": 1,
            "corrective_followup_invocations": 0,
            "prompt_framing": "exact UTF-8 problem_statement bytes plus one LF on stdin",
            "subject_timeout_seconds": 900,
            "evaluator_timeout_seconds": 1800,
        },
        "analysis_unit": {
            "unit": "task/repository",
            "task_count": TASK_COUNT,
            "repository_distinct": True,
            "repetitions_correlated_within_task": True,
        },
        "attempt_accounting": {
            "maximum_attempts_per_cell": MAXIMUM_ATTEMPTS_PER_CELL,
            "completed_cells_never_repeated": True,
            "attempt_2_requires_explicit_prior_authorization": True,
            "qualification_subject_executions": qualification_subject_executions,
            "maximum_qualification_subject_executions": MAXIMUM_QUALIFICATION_EXECUTIONS,
            "maximum_subject_executions_including_qualification": MAXIMUM_SUBJECT_EXECUTIONS,
            "capacity_may_not_be_increased": True,
            "attempt_2_only_for_retryable_infrastructure": True,
        },
        "failure_taxonomy": {
            "experimental_outcomes": list(EXPERIMENTAL_OUTCOMES),
            "retryable_infrastructure": list(RETRYABLE_INFRASTRUCTURE),
            "mandatory_batch_stop": list(BATCH_STOP_CLASSES),
            "post_outcome_reclassification_permitted": False,
        },
        "outcomes": {
            "primary": "official evaluator acceptance",
            "missingness": "report by frozen arm and reason; no imputation",
            "experimental_failures_retained_in_assigned_arm": True,
            "secondary": {
                "provider_usage": list(USAGE_FIELDS),
                "calculated_fresh_input_tokens": (
                    "input_tokens - cached_input_tokens - cache_write_input_tokens"
                ),
                "subject_wall_time_seconds": True,
                "subject_turns": True,
                "command_count": True,
                "search_count": True,
                "item_count": True,
            },
        },
        "analysis": {
            "estimand": "task-cluster mean paired difference, medium minus low",
            "repetitions_correlated_within_task": True,
            "uncertainty": {
                "method": "deterministic task-cluster bootstrap",
                "seed": "engineering-scope-guard-effort-v1-task-bootstrap-2026-08-30",
                "resamples": 10000,
            },
            "required_diagnostics": [
                "discordant acceptance pairs",
                "task heterogeneity",
                "leave-one-task-out sensitivity",
            ],
        },
        "claim_boundaries": {
            "exploratory_only": True,
            "equivalence_claim_permitted": False,
            "noninferiority_claim_permitted": False,
            "per_language_claim_permitted": False,
            "billing_claim_permitted": False,
            "causal_mechanism_claim_permitted": False,
        },
        "staging": {
            "stage_1_cell_count": 4,
            "stage_1_cell_ids": [cell["cell_id"] for cell in schedule["cells"][:4]],
            "stage_1_is_qualification_not_treatment_tuning": True,
            "continue_only_if_no_batch_stop_or_measurement_failure": True,
            "outcome_blind_infrastructure_gate": {
                "required_final_cells_per_arm": 2,
                "require_frozen_arm_command_receipt": True,
                "require_subject_return_receipt": True,
                "require_complete_provider_usage": True,
                "require_complete_subject_work_receipt": True,
                "require_no_prohibited_tool_receipt": True,
                "require_complete_official_evaluator_receipt": True,
                "require_durable_receipt_binding": True,
                "outcome_direction_used_for_decision": False,
                "failure_is_terminal": True,
            },
        },
        "stop_rules": {
            "mandatory_batch_stop_classes": list(BATCH_STOP_CLASSES),
            "stop_at_global_subject_execution_cap": True,
            "treatment_tuning_after_any_outcome_permitted": False,
            "post_outcome_replacement_permitted": False,
            "confirmatory_experiment_permitted": False,
            "second_experiment_permitted": False,
        },
        "usage": {
            "provider_reported_required_fields": list(USAGE_FIELDS),
            "measurement_scope": USAGE_MEASUREMENT_SCOPE,
            "derived_fields": {
                "calculated_fresh_input_tokens": (
                    "input_tokens - cached_input_tokens - cache_write_input_tokens"
                ),
            },
            "provider_reports_total_tokens": False,
            "reasoning_output_tokens_included_in_output_tokens": True,
            "ambiguous_intermediate_or_cumulative_aggregation_permitted": False,
        },
    }
    return _sealed(contract, "contract_sha256")


def validate_contract(contract: dict[str, Any]) -> None:
    """Reject any identity drift or structurally invalid frozen schedule."""

    if not _identity_matches(contract, "contract_sha256"):
        raise ExperimentConfigurationError("reasoning-effort contract identity mismatch")
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise ExperimentConfigurationError("reasoning-effort contract version mismatch")
    if contract.get("live_execution_authorized") is not False:
        raise ExperimentConfigurationError("provider-free contract cannot authorize execution")
    schedule = contract.get("schedule")
    if not isinstance(schedule, dict) or not _identity_matches(schedule, "schedule_sha256"):
        raise ExperimentConfigurationError("reasoning-effort schedule identity mismatch")
    expected = generate_schedule(
        [
            {key: task[key] for key in ("task_id", "repository", "task_snapshot_sha256")}
            for task in schedule.get("tasks", [])
        ]
    )
    if canonical_bytes(expected) != canonical_bytes(schedule):
        raise ExperimentConfigurationError("reasoning-effort schedule is not canonical")
    try:
        source = contract["source"]
        scientific = contract["scientific_question"]
        rebuilt = build_contract(
            [
                {
                    key: task[key]
                    for key in ("task_id", "repository", "task_snapshot_sha256")
                }
                for task in schedule["tasks"]
            ],
            model=contract["subject"]["model"],
            codex_version=contract["subject"]["codex_version"],
            runtime_identity=contract["subject"]["runtime_identity"],
            source_revision=source["dataset_revision"],
            evaluator_revision=source["evaluator_revision"],
            qualification_subject_executions=contract["attempt_accounting"][
                "qualification_subject_executions"
            ],
            research_question=scientific["question"],
            hypothesis=scientific["directional_hypothesis"],
            dataset_identity=source["dataset_identity"],
            evaluator_identity=source["evaluator_identity"],
            repolaunch_revision=source["repolaunch_revision"],
            image_pool_identity=source["image_pool_identity"],
            expected_pool_sha256=source["pool_sha256"],
        )
    except (KeyError, TypeError) as error:
        raise ExperimentConfigurationError(
            "reasoning-effort scientific contract is incomplete"
        ) from error
    if canonical_bytes(rebuilt) != canonical_bytes(contract):
        raise ExperimentConfigurationError(
            "reasoning-effort scientific fields differ from the frozen design"
        )
    subject = contract.get("subject", {})
    if subject.get("only_variable") != "reasoning_effort" or subject.get("arms") != {
        arm: {"reasoning_effort": arm} for arm in ARMS
    }:
        raise ExperimentConfigurationError("reasoning-effort arm contract is invalid")
    accounting = contract.get("attempt_accounting", {})
    if accounting != {
        "maximum_attempts_per_cell": MAXIMUM_ATTEMPTS_PER_CELL,
        "completed_cells_never_repeated": True,
        "attempt_2_requires_explicit_prior_authorization": True,
        "qualification_subject_executions": accounting.get("qualification_subject_executions"),
        "maximum_qualification_subject_executions": MAXIMUM_QUALIFICATION_EXECUTIONS,
        "maximum_subject_executions_including_qualification": MAXIMUM_SUBJECT_EXECUTIONS,
        "capacity_may_not_be_increased": True,
        "attempt_2_only_for_retryable_infrastructure": True,
    }:
        raise ExperimentConfigurationError("reasoning-effort attempt accounting drifted")
    qualification = accounting.get("qualification_subject_executions")
    if (
        not isinstance(qualification, int)
        or isinstance(qualification, bool)
        or not 0 <= qualification <= MAXIMUM_QUALIFICATION_EXECUTIONS
    ):
        raise ExperimentConfigurationError("qualification subject-execution count is invalid")


def validate_frozen_identity(
    contract: dict[str, Any],
    *,
    expected_contract_sha256: str,
    expected_schedule_sha256: str,
) -> None:
    """Bind execution to identities stored outside the candidate contract."""

    validate_contract(contract)
    if contract["contract_sha256"] != expected_contract_sha256:
        raise ExperimentConfigurationError("frozen reasoning-effort contract was replaced")
    if contract["schedule"]["schedule_sha256"] != expected_schedule_sha256:
        raise ExperimentConfigurationError("frozen reasoning-effort schedule was replaced")


def append_event(path: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append one fsync'd canonical event to a SHA-256 chained JSONL ledger."""

    events = read_events(path)
    if not isinstance(event_type, str) or not event_type or not isinstance(payload, dict):
        raise ExperimentConfigurationError("ledger event is malformed")
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
        os.fsync(handle.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return event


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError(
                f"malformed effort-v1 ledger line {number}"
            ) from error
        if not isinstance(event, dict):
            raise ExperimentConfigurationError("effort-v1 ledger event must be an object")
        recorded = event.get("event_sha256")
        body = {key: item for key, item in event.items() if key != "event_sha256"}
        if body.get("sequence") != number or body.get("previous_event_sha256") != previous:
            raise ExperimentConfigurationError("effort-v1 ledger chain mismatch")
        if not isinstance(recorded, str) or recorded != digest(body):
            raise ExperimentConfigurationError("effort-v1 ledger digest mismatch")
        events.append(event)
        previous = recorded
    return events


def _cell_ids(contract: dict[str, Any]) -> set[str]:
    return {cell["cell_id"] for cell in contract["schedule"]["cells"]}


def _valid_stage_1_audit(audit: Any, expected_status: str) -> bool:
    criteria_names = {
        "awaiting_stage_1_authorization",
        "exact_four_cell_schedule_prefix",
        "both_arms_have_two_final_cells",
        "arm_command_receipts_complete",
        "subject_returns_complete",
        "usage_receipts_complete",
        "subject_work_receipts_complete",
        "tool_policy_receipts_complete",
        "official_evaluator_receipts_complete",
        "durable_receipts_bound",
        "no_batch_stop",
    }
    if not isinstance(audit, dict) or audit.get("status") != expected_status:
        return False
    criteria = audit.get("criteria")
    if (
        not isinstance(criteria, dict)
        or set(criteria) != criteria_names
        or any(not isinstance(value, bool) for value in criteria.values())
        or audit.get("completed_cells") != 4
        or audit.get("final_cells_by_arm") != {arm: 2 for arm in ARMS}
        or audit.get("outcome_direction_inspected") is not False
        or audit.get("outcome_values_emitted") is not False
    ):
        return False
    return all(criteria.values()) if expected_status == "pass" else not all(criteria.values())


def validate_attempt_ledger(contract: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """Replay attempt state and enforce all frozen retry/capacity rules."""

    validate_contract(contract)
    qualification = contract["attempt_accounting"]["qualification_subject_executions"]
    starts: dict[str, list[int]] = {}
    completed: set[str] = set()
    authorizations: set[str] = set()
    subject_invocations: set[tuple[str, int]] = set()
    subject_returns: set[tuple[str, int]] = set()
    stage_1_boundary = False
    stage_2_authorized = False
    stage_1_failed = False
    valid_cells = _cell_ids(contract)
    subject_executions = qualification
    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ExperimentConfigurationError("attempt ledger payload is malformed")
        cell_id = payload.get("cell_id")
        if event_type == "stage_1_boundary_reached":
            if stage_1_boundary or len(completed) != contract["staging"]["stage_1_cell_count"]:
                raise ExperimentConfigurationError("stage-1 boundary is out of sequence")
            if payload.get("completed_cell_count") != contract["staging"]["stage_1_cell_count"]:
                raise ExperimentConfigurationError("stage-1 boundary count drifted")
            stage_1_boundary = True
            continue
        if event_type == "stage_2_authorized":
            audit = payload.get("audit")
            if not stage_1_boundary or stage_2_authorized or stage_1_failed:
                raise ExperimentConfigurationError("stage-2 authorization is out of sequence")
            if payload.get("stage_1_completed_cell_count") != contract["staging"][
                "stage_1_cell_count"
            ] or (
                not _valid_stage_1_audit(audit, "pass")
                or payload.get("audit_sha256") != digest(audit)
            ):
                raise ExperimentConfigurationError("stage-2 authorization count drifted")
            stage_2_authorized = True
            continue
        if event_type == "stage_1_failed":
            audit = payload.get("audit")
            if (
                not stage_1_boundary
                or stage_2_authorized
                or stage_1_failed
                or len(completed) != contract["staging"]["stage_1_cell_count"]
                or payload.get("stage_1_completed_cell_count")
                != contract["staging"]["stage_1_cell_count"]
                or payload.get("reason") != "stage_1_infrastructure_gate_failed"
                or not _valid_stage_1_audit(audit, "fail")
                or payload.get("audit_sha256") != digest(audit)
            ):
                raise ExperimentConfigurationError("stage-1 failure is out of sequence")
            stage_1_failed = True
            continue
        if event_type not in {
            "attempt_started",
            "attempt_2_authorized",
            "subject_invocation_started",
            "subject_invocation_returned",
            "cell_completed",
        }:
            continue
        if cell_id not in valid_cells:
            raise ExperimentConfigurationError("attempt ledger references an unknown cell")
        attempts = starts.setdefault(cell_id, [])
        if event_type == "subject_invocation_returned":
            attempt = payload.get("attempt")
            key = (cell_id, attempt)
            if key not in subject_invocations or key in subject_returns:
                raise ExperimentConfigurationError("subject invocation return is out of sequence")
            if (
                not isinstance(payload.get("timed_out"), bool)
                or (
                    payload.get("exit_code") is not None
                    and (
                        not isinstance(payload.get("exit_code"), int)
                        or isinstance(payload.get("exit_code"), bool)
                    )
                )
                or not all(
                    isinstance(payload.get(field), str) and payload[field]
                    for field in ("stdout_sha256", "stderr_sha256")
                )
            ):
                raise ExperimentConfigurationError("subject invocation return evidence is malformed")
            subject_returns.add(key)
        elif event_type == "subject_invocation_started":
            attempt = payload.get("attempt")
            key = (cell_id, attempt)
            if (
                attempt not in (1, 2)
                or not attempts
                or attempts[-1] != attempt
                or key in subject_invocations
                or cell_id in completed
            ):
                raise ExperimentConfigurationError("subject invocation is out of sequence")
            if not all(
                isinstance(payload.get(field), str) and payload[field]
                for field in ("prompt_sha256", "command_sha256", "codex_executable_sha256")
            ):
                raise ExperimentConfigurationError("subject invocation identity is incomplete")
            subject_invocations.add(key)
            subject_executions += 1
            if subject_executions > MAXIMUM_SUBJECT_EXECUTIONS:
                raise ExperimentConfigurationError("global subject-execution cap exceeded")
        elif event_type == "attempt_2_authorized":
            if attempts != [1] or cell_id in completed or cell_id in authorizations:
                raise ExperimentConfigurationError(
                    "attempt 2 authorization is out of sequence"
                )
            if (
                payload.get("next_attempt") != 2
                or not isinstance(payload.get("reason"), str)
                or not payload["reason"]
                or payload.get("classification") not in RETRYABLE_INFRASTRUCTURE
            ):
                raise ExperimentConfigurationError("attempt 2 authorization is not explicit")
            authorizations.add(cell_id)
        elif event_type == "attempt_started":
            attempt = payload.get("attempt")
            if cell_id in completed:
                raise ExperimentConfigurationError("completed cell cannot be repeated")
            if attempt not in (1, 2) or attempt != len(attempts) + 1:
                raise ExperimentConfigurationError("attempt number is repeated or out of sequence")
            if attempt == 2 and cell_id not in authorizations:
                raise ExperimentConfigurationError("attempt 2 lacks explicit authorization")
            attempts.append(attempt)
        else:
            attempt = payload.get("attempt")
            if not attempts or attempt != attempts[-1] or cell_id in completed:
                raise ExperimentConfigurationError("cell completion is out of sequence")
            if len(completed) >= contract["staging"]["stage_1_cell_count"] and not stage_2_authorized:
                raise ExperimentConfigurationError("cell completion crossed the stage-1 boundary")
            completed.add(cell_id)


def read_attempt_ledger(path: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Read and validate both the durable hash chain and attempt semantics."""

    events = read_events(path)
    validate_attempt_ledger(contract, events)
    return events


def authorize_attempt_2(
    path: Path,
    contract: dict[str, Any],
    cell_id: str,
    reason: str,
    classification: str = "provider_api_infrastructure_failure",
) -> dict[str, Any]:
    events = read_attempt_ledger(path, contract)
    payload = {
        "cell_id": cell_id,
        "next_attempt": 2,
        "reason": reason,
        "classification": classification,
    }
    validate_attempt_ledger(
        contract,
        [*events, {"event_type": "attempt_2_authorized", "payload": payload}],
    )
    return append_event(path, "attempt_2_authorized", payload)


def record_attempt_start(
    path: Path, contract: dict[str, Any], cell_id: str, attempt: int
) -> dict[str, Any]:
    events = read_attempt_ledger(path, contract)
    candidate = {
        "sequence": len(events) + 1,
        "event_type": "attempt_started",
        "recorded_at": "validation-placeholder",
        "previous_event_sha256": events[-1]["event_sha256"] if events else None,
        "payload": {"cell_id": cell_id, "attempt": attempt},
        "event_sha256": "validation-placeholder",
    }
    validate_attempt_ledger(contract, [*events, candidate])
    return append_event(path, "attempt_started", candidate["payload"])


def record_cell_completed(
    path: Path, contract: dict[str, Any], cell_id: str, attempt: int
) -> dict[str, Any]:
    events = read_attempt_ledger(path, contract)
    payload = {"cell_id": cell_id, "attempt": attempt}
    validate_attempt_ledger(
        contract,
        [*events, {"event_type": "cell_completed", "payload": payload}],
    )
    return append_event(path, "cell_completed", payload)


def validate_usage(usage: dict[str, Any], *, measurement_scope: str) -> dict[str, Any]:
    """Validate one final fresh-session usage snapshot without summing cumulatives."""

    if measurement_scope != USAGE_MEASUREMENT_SCOPE:
        raise ExperimentConfigurationError(
            "usage scope is ambiguous or cumulative across sessions"
        )
    if set(usage) != set(USAGE_FIELDS):
        raise ExperimentConfigurationError("current usage components are incomplete or unexpected")
    if any(
        not isinstance(usage[field], int) or isinstance(usage[field], bool) or usage[field] < 0
        for field in USAGE_FIELDS
    ):
        raise ExperimentConfigurationError("current usage components must be non-negative integers")
    if (
        usage["cached_input_tokens"] + usage["cache_write_input_tokens"]
        > usage["input_tokens"]
    ):
        raise ExperimentConfigurationError("cache input components exceed total input")
    if usage["reasoning_output_tokens"] > usage["output_tokens"]:
        raise ExperimentConfigurationError("reasoning output exceeds total output")
    provider_reported = {field: usage[field] for field in USAGE_FIELDS}
    return {
        "provider_reported": provider_reported,
        "derived": {
            "calculated_fresh_input_tokens": (
                usage["input_tokens"]
                - usage["cached_input_tokens"]
                - usage["cache_write_input_tokens"]
            ),
        },
    }
