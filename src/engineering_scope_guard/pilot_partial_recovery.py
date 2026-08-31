"""Read-only qualification of one preserved successor partial attempt.

This module has no subject, evaluator, ledger-writer, or process-launching
dependency. It can describe a recovery candidate, but it cannot resolve one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError, _usage_from_trace
from .pilot_contract import read_ledger, read_object, validate_contract
from .pilot_runner import sha256_file
from .pilot_successor import (
    next_successor_legal_action,
    predecessor_file_identity,
    read_authorization,
    validate_successor_authorization,
)

SCHEMA_NAME = "engineering-scope-guard.pilot-partial-recovery-qualification"
SCHEMA_VERSION = 1
DECISION = "STOP PILOT"


def assess_recovery_evidence(
    field_checks: dict[str, bool], *, valid_finalization_transition: bool
) -> dict[str, Any]:
    """Classify a durable partial bundle without performing a transition."""

    missing = [name for name, present in field_checks.items() if not present]
    recoverable = not missing
    return {
        "recoverable": recoverable,
        "legal": recoverable and valid_finalization_transition,
        "missing_or_ambiguous": missing,
    }


def _artifact(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ExperimentConfigurationError("partial artifact is outside the repository") from error
    return {
        "path": str(relative),
        "exists": resolved.is_file(),
        "sha256": sha256_file(resolved) if resolved.is_file() else None,
        "bytes": resolved.stat().st_size if resolved.is_file() else None,
    }


def _read_json_if_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"preserved JSON artifact is malformed: {path.name}") from error
    return value if isinstance(value, dict) else None


def _subject_summary(trace: Path, required_fields: list[str]) -> dict[str, Any]:
    terminal_types: list[str] = []
    session_ids: list[str] = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if isinstance(event_type, str):
            terminal_types.append(event_type)
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            session_ids.append(event["thread_id"])
    usage_record = _usage_from_trace(trace)
    provider_usage = usage_record["components"]
    provider_complete = all(
        isinstance(provider_usage.get(field), int)
        and not isinstance(provider_usage.get(field), bool)
        and provider_usage[field] >= 0
        for field in required_fields
    )
    usage = dict(provider_usage) if provider_complete else {}
    if provider_complete:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return {
        "terminal_event": terminal_types[-1] if terminal_types else None,
        "completed_turns": terminal_types.count("turn.completed"),
        "session_identity_sha256": (
            hashlib.sha256(session_ids[-1].encode()).hexdigest() if session_ids else None
        ),
        "usage": usage,
        "usage_complete": provider_complete,
        "usage_provenance": {
            "provider_reported": required_fields,
            "derived": {"total_tokens": "input_tokens + output_tokens"},
        },
    }


def _prediction_summary(prediction_path: Path, patch_path: Path, task_id: str) -> dict[str, Any]:
    prediction = _read_json_if_object(prediction_path)
    patch_sha256 = sha256_file(patch_path) if patch_path.is_file() else None
    mapped_patch = None if prediction is None else prediction.get(task_id, {}).get("model_patch")
    mapped_sha256 = (
        hashlib.sha256(mapped_patch.encode()).hexdigest()
        if isinstance(mapped_patch, str)
        else None
    )
    return {
        "task_identity_bound": prediction is not None and set(prediction) == {task_id},
        "patch_sha256": patch_sha256,
        "prediction_patch_sha256": mapped_sha256,
        "prediction_matches_preserved_patch": patch_sha256 == mapped_sha256,
        "patch_bytes": patch_path.stat().st_size if patch_path.is_file() else None,
    }


def _evaluator_summary(output: Path, task_id: str) -> dict[str, Any]:
    results_path = output / "results.json"
    report_path = output / task_id / "report.json"
    results = _read_json_if_object(results_path)
    report = _read_json_if_object(report_path)
    submitted_ids = results.get("submitted_ids") if results else None
    result_bound = isinstance(submitted_ids, list) and submitted_ids == [task_id]
    report_resolved = report.get("resolved") if report else None
    return {
        "official_results_present": results is not None,
        "per_instance_report_present": report is not None,
        "uniquely_bound_to_attempt_task": result_bound,
        "structured_result_complete": (
            results is not None
            and report is not None
            and result_bound
            and isinstance(report_resolved, bool)
        ),
        "observed_result_class": (
            "empty_patch"
            if results and results.get("empty_patch_ids") == [task_id]
            else "other"
        ),
        "resolved": report_resolved if isinstance(report_resolved, bool) else None,
        "process_exit_status": {
            "status": "unavailable",
            "reason": "the completed process exit status was held only in memory",
        },
        "invocation_identity": {
            "expected_from_frozen_contract": True,
            "observed_durable_command_record": False,
        },
    }


def build_partial_recovery_preview(
    root: Path,
    contract_path: Path,
    authorization_path: Path,
    integrity_path: Path,
    predecessor_path: Path,
    successor_ledger_path: Path,
    *,
    contract_source_root: Path | None = None,
) -> dict[str, Any]:
    """Inspect preserved evidence and return a sanitized, non-mutating preview."""

    root = root.resolve()
    contract = read_object(contract_path)
    validate_contract(contract, (contract_source_root or root).resolve())
    authorization = read_authorization(authorization_path)
    integrity = read_object(integrity_path)
    predecessor_events = read_ledger(predecessor_path)
    validate_successor_authorization(contract, predecessor_events, integrity, authorization)
    successor_before = successor_ledger_path.read_bytes()
    events = read_ledger(successor_ledger_path)
    action = next_successor_legal_action(contract, authorization, events)
    if action.get("action") != "resolve_partial":
        raise ExperimentConfigurationError("successor is not at the preserved resolve_partial state")
    request = action["request"]
    roots = {name: Path(value) for name, value in request["isolation_roots"].items()}
    raw = roots["raw"]
    derived = roots["derived"]
    trace = raw / "codex-round-0.jsonl"
    patch = derived / "prediction.patch"
    prediction = derived / "prediction.json"
    evaluator_output = raw / "evaluator-round-0"
    artifacts = {
        "subject_trace": _artifact(root, trace),
        "pre_subject_baseline": _artifact(root, derived / "pre-subject.index"),
        "post_subject_index": _artifact(root, derived / "subject.index"),
        "prediction_patch": _artifact(root, patch),
        "prediction_json": _artifact(root, prediction),
        "evaluator_stdout": _artifact(root, evaluator_output / "command.stdout"),
        "evaluator_stderr": _artifact(root, evaluator_output / "command.stderr"),
        "evaluator_results": _artifact(root, evaluator_output / "results.json"),
        "evaluator_report": _artifact(
            root, evaluator_output / request["actual_task_id"] / "report.json"
        ),
    }
    subject = _subject_summary(
        trace, contract["usage"]["required_provider_reported_fields"]
    )
    prediction_summary = _prediction_summary(
        prediction, patch, request["actual_task_id"]
    )
    evaluator = _evaluator_summary(evaluator_output, request["actual_task_id"])
    field_checks = {
        "subject_identity_configuration": True,
        "arm_task_cell_attempt_identity": True,
        "subject_terminal_state": subject["terminal_event"] == "turn.completed",
        "complete_authorized_usage": subject["usage_complete"],
        "generated_patch_identity": prediction_summary[
            "prediction_matches_preserved_patch"
        ],
        "authoritative_pre_subject_baseline": artifacts[
            "pre_subject_baseline"
        ]["exists"],
        "official_evaluator_invocation_identity": evaluator[
            "invocation_identity"
        ]["observed_durable_command_record"],
        "structured_evaluator_result": evaluator["structured_result_complete"],
        "receipt_started_at": False,
        "receipt_ended_at": False,
        "failure_termination_metadata": False,
        "contract_digest": request.get("contract_sha256") == contract["contract_sha256"],
        "successor_authorization_digest": events[0].get("payload", {}).get(
            "authorization_sha256"
        )
        == authorization["authorization_sha256"],
        "ledger_lineage_inputs": True,
    }
    recovery_assessment = assess_recovery_evidence(
        field_checks, valid_finalization_transition=False
    )
    missing = recovery_assessment["missing_or_ambiguous"]
    attempt = request["trajectory_attempt"]
    maximum_attempts = contract["trajectory_infrastructure_rerun_budget"][
        "maximum_attempts_per_cell"
    ]
    rerun_legal = attempt < maximum_attempts
    if successor_ledger_path.read_bytes() != successor_before:
        raise ExperimentConfigurationError("successor ledger changed during recovery preview")
    predecessor_identity = predecessor_file_identity(predecessor_path)
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "status": "fail_closed",
        "decision": DECISION,
        "root_cause": {
            "ended_at_observed_runtime_type": "str",
            "core_previous_expectation": "zero-argument callable",
            "boundary": "LiveBackend.prepare result to core receipt construction",
            "additional_usage_boundary": "provider reports components while total_tokens is derived",
        },
        "identity": {
            "contract_sha256": contract["contract_sha256"],
            "contract_file_sha256": sha256_file(contract_path),
            "authorization_sha256": authorization["authorization_sha256"],
            "authorization_file_sha256": sha256_file(authorization_path),
            "predecessor": predecessor_identity,
            "successor_ledger_file_sha256": hashlib.sha256(successor_before).hexdigest(),
            "successor_ledger_events": len(events),
            "successor_terminal_event_sha256": events[-1]["event_sha256"],
            "cell_id": request["cell_id"],
            "trajectory_attempt": attempt,
        },
        "source_artifacts": artifacts,
        "subject": subject,
        "prediction": prediction_summary,
        "evaluator": evaluator,
        "timing": {
            "attempt_started_at": request.get("attempt_started_at"),
            "receipt_started_at": {
                "status": "unavailable",
                "reason": "prepared started_at was not durably recorded",
            },
            "receipt_ended_at": {
                "status": "unavailable",
                "reason": "prepared ended_at was not durably recorded",
            },
            "filesystem_times_used_as_receipt_evidence": False,
        },
        "required_evidence": field_checks,
        "missing_or_ambiguous": missing,
        "recovery": {
            "legal": recovery_assessment["legal"],
            "recoverable": recovery_assessment["recoverable"],
            "normalized_receipt": None,
            "existing_same_attempt_valid_finalization_transition": False,
            "reason": "required authoritative evidence is missing",
        },
        "expected_state": {
            "ledger_events_to_append": [],
            "resulting_status": "resolve_partial",
            "infrastructure_reruns_consumed": authorization[
                "failure_accounting"
            ]["reruns_consumed_at_successor_start"],
            "additional_reruns_consumed": 0,
            "next_scheduled_cell": None,
            "conditional_next_cell_after_hypothetical_valid_finalization": contract[
                "schedule"
            ]["cells"][1]["cell_id"],
        },
        "rerun": {
            "legal": rerun_legal,
            "current_attempt": attempt,
            "maximum_attempts_per_cell": maximum_attempts,
            "would_be_attempt": attempt + 1,
            "reason": "same cell has exhausted its frozen attempt allowance",
        },
        "non_pilot_end_to_end_canary": {
            "run": False,
            "reason": "no separately authorized non-Pilot subject-to-receipt canary exists",
        },
        "experimental_activity": {
            "pilot_subject_invocations": 0,
            "pilot_evaluator_invocations": 0,
            "pilot_retries": 0,
            "task_replacements": 0,
            "successor_batches_created": 0,
            "successor_ledger_mutations": 0,
            "receipts_created": 0,
            "valid_completed_cells": 0,
            "policy_comparisons": 0,
        },
    }
