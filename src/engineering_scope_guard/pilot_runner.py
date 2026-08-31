"""Sequential executor for the frozen Pilot contract.

The core is deliberately backend-agnostic so fixture tests can exercise every
state transition without launching Codex, Docker, or the official evaluator.
The live process boundary is implemented by ``scripts/pilot_runner.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .experiment import ExperimentConfigurationError
from .pilot_contract import (
    BATCH_STOP_FAILURES,
    EXPERIMENTAL_OUTCOMES,
    RERUNNABLE_INFRASTRUCTURE,
    append_ledger_event,
    classify_receipt,
    infrastructure_rerun_state,
    read_ledger,
    validate_contract,
    validate_preflight,
)

RUNNER_SCHEMA = "engineering-scope-guard.pilot-runner"
PREFLIGHT_SCHEMA = "engineering-scope-guard.pilot-runner-preflight"
DRY_RUN_SCHEMA = "engineering-scope-guard.pilot-runner-dry-run"


def canonical_attempt_timeout(
    contract_version: str, trajectory_contract: dict[str, Any]
) -> int:
    """Return the sole contract-version-specific evaluator timeout."""

    canonical_key = {
        "pilot-v1.0": "timeout_seconds_per_trajectory_attempt",
        "pilot-v2.0": "timeout_seconds_per_trajectory_attempt",
        "pilot-v3.0": "timeout_seconds_per_attempt",
    }.get(contract_version)
    if canonical_key is None:
        raise ExperimentConfigurationError("unsupported trajectory timeout schema")
    if not isinstance(trajectory_contract, dict):
        raise ExperimentConfigurationError("trajectory contract is not an object")
    timeout_keys = {
        key
        for key in trajectory_contract
        if isinstance(key, str) and key.startswith("timeout_seconds_per_")
    }
    if timeout_keys != {"timeout_seconds_per_turn", canonical_key}:
        raise ExperimentConfigurationError(
            "trajectory timeout fields are missing, ambiguous, or unsupported"
        )
    value = trajectory_contract[canonical_key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ExperimentConfigurationError("trajectory attempt timeout is invalid")
    return value


@dataclass(frozen=True)
class SubjectResult:
    """One Codex turn result returned by a subject backend."""

    exit_code: int | None
    timed_out: bool
    session_id: str | None
    usage: dict[str, int]
    trace_reference: str
    provider_infrastructure_failure: bool = False


@dataclass(frozen=True)
class EvaluatorResult:
    """One official-evaluator result returned by an evaluator backend."""

    exit_code: int | None
    timed_out: bool
    resolved: bool | None
    failing_checks: tuple[str, ...]
    report_reference: str
    results_reference: str
    report_sha256: str | None
    results_sha256: str | None
    infrastructure_failure: bool = False
    malformed: bool = False
    official_disposition: str | None = None
    feedback_status: str | None = None


@dataclass(frozen=True)
class OfficialEvaluatorArtifacts:
    """Validated terminal meaning of one official evaluator invocation."""

    disposition: str
    resolved: bool | None
    failing_checks: tuple[str, ...]
    feedback_status: str
    measurement_complete: bool


class RunnerBackend(Protocol):
    """Narrow process boundary required by the frozen trajectory."""

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        """Materialize task state and return metadata plus receipt timestamps.

        Timestamp values may be direct ISO strings or zero-argument accessors.
        An end-time accessor is evaluated only after subject/evaluator work.
        """

    def cleanup(self, prepared: dict[str, Any]) -> None:
        """Remove trajectory-local credential material."""

    def run_subject(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...] | None,
        session_id: str | None,
    ) -> SubjectResult:
        """Run or resume the fixed Codex subject."""

    def create_prediction(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]:
        """Preserve the Git diff and create official prediction JSON."""

    def evaluate(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prediction: dict[str, Any],
        round_number: int,
    ) -> EvaluatorResult:
        """Invoke the official evaluator and return structured output only."""


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def parse_official_evaluator_artifacts(
    instance_id: str,
    report: dict[str, Any],
    results: dict[str, Any],
) -> OfficialEvaluatorArtifacts:
    """Validate and preserve one pinned evaluator terminal disposition.

    The official evaluator can report a valid task failure without naming a
    failing check: expected checks that are absent from parsed output make
    ``resolved`` false but do not appear in either report failure list. Keep
    that negative disposition distinct from whether corrective feedback is
    available.
    """

    categories = (
        ("success", "success_ids"),
        ("failure", "failure_ids"),
        ("error", "error_ids"),
        ("incomplete", "incomplete_ids"),
        ("empty_patch", "empty_patch_ids"),
    )
    submitted_ids = results.get("submitted_ids")
    if results.get("submitted") != 1 or submitted_ids != [instance_id]:
        raise ExperimentConfigurationError(
            "official evaluator submitted identity is malformed"
        )

    memberships: list[str] = []
    for count_name, ids_name in categories:
        identifiers = results.get(ids_name)
        count = results.get(count_name)
        if (
            not isinstance(identifiers, list)
            or any(not isinstance(item, str) for item in identifiers)
            or len(set(identifiers)) != len(identifiers)
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count != len(identifiers)
        ):
            raise ExperimentConfigurationError(
                f"official evaluator {count_name} accounting is malformed"
            )
        if instance_id in identifiers:
            memberships.append(count_name)
    if len(memberships) != 1:
        raise ExperimentConfigurationError(
            "official evaluator terminal disposition is not unique"
        )

    disposition = memberships[0]
    expected_resolved = {"success": True, "failure": False}.get(disposition)
    failing_checks: list[str] = []
    if expected_resolved is not None:
        if (
            report.get("instance_id") != instance_id
            or report.get("resolved") is not expected_resolved
        ):
            raise ExperimentConfigurationError(
                "official evaluator report disagrees with terminal disposition"
            )
        for section in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            group = report.get(section)
            if not isinstance(group, dict):
                raise ExperimentConfigurationError(
                    "official evaluator report section is malformed"
                )
            for field in ("success", "failure"):
                checks = group.get(field)
                if (
                    not isinstance(checks, list)
                    or any(not isinstance(item, str) for item in checks)
                    or len(set(checks)) != len(checks)
                ):
                    raise ExperimentConfigurationError(
                        "official evaluator check accounting is malformed"
                    )
            failing_checks.extend(group["failure"])
    elif report:
        resolved = report.get("resolved")
        if resolved is not None:
            raise ExperimentConfigurationError(
                "non-result evaluator disposition has a resolved report"
            )

    unique_failures = tuple(dict.fromkeys(failing_checks))
    feedback_status = (
        "available"
        if disposition == "failure" and unique_failures
        else "unavailable"
        if disposition == "failure"
        else "not_applicable"
    )
    return OfficialEvaluatorArtifacts(
        disposition=disposition,
        resolved=expected_resolved,
        failing_checks=unique_failures,
        feedback_status=feedback_status,
        measurement_complete=disposition in {"success", "failure", "empty_patch"},
    )


def append_runner_event(
    path: Path, event_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Append through the frozen ledger writer, then durably sync runner state."""

    event = append_ledger_event(path, event_type, payload)
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    return event


def execution_confirmation(contract: dict[str, Any]) -> str:
    """Return the exact token required for a consequential live execute call."""

    return f"execute-{contract['contract_version']}:" + contract["contract_sha256"]


def official_evaluator_command(
    evaluator_python: Path,
    dataset_root: Path,
    split: str,
    prediction_path: Path,
    output_path: Path,
    workers: int,
    instance_id: str,
) -> list[str]:
    """Return the pinned official SWE-bench-Live prediction invocation."""

    return [
        str(evaluator_python),
        "-m",
        "evaluation.evaluation",
        "--dataset",
        str(dataset_root),
        "--split",
        split,
        "--platform",
        "linux",
        "--patch_dir",
        str(prediction_path),
        "--output_dir",
        str(output_path),
        "--workers",
        str(workers),
        "--overwrite",
        "1",
        "--instance_ids",
        instance_id,
    ]


def build_launch_request(
    contract: dict[str, Any],
    cell: dict[str, Any],
    state_root: Path,
    trajectory_attempt: int,
) -> dict[str, Any]:
    """Bind one attempt to every frozen launch identity."""

    slot = next(
        item
        for item in contract["final_pool"]["slots"]
        if item["slot"] == cell["requested_task_slot"]
    )
    attempt_root = state_root / "attempts" / cell["cell_id"] / f"attempt-{trajectory_attempt}"
    request = {
        **{
            key: cell[key]
            for key in (
                "cell_id",
                "requested_task_slot",
                "actual_task_id",
                "arm",
                "repetition",
            )
        },
        "trajectory_attempt": trajectory_attempt,
        "subject": contract["subject"],
        "contract_sha256": contract["contract_sha256"],
        "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "task_snapshot_sha256": slot["task_snapshot_sha256"],
        "source_and_evaluator": contract["source_and_evaluator"],
        "platform": contract["platform"],
        "trajectory_contract": contract["trajectory"],
        "isolation_contract": contract["isolation"],
        "usage_contract": contract["usage"],
        "isolation_roots": {
            "repository": str(attempt_root / "repository"),
            "codex_home": str(attempt_root / "codex-home"),
            "raw": str(attempt_root / "raw"),
            "derived": str(attempt_root / "derived"),
        },
        "intervention_sha256": (
            None
            if cell["arm"] == "baseline"
            else contract["arms"]["short_policy_sha256"]
        ),
    }
    return request


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ExperimentConfigurationError("ledger event payload is malformed")
    return payload


def _validate_metadata_events(contract: dict[str, Any], events: list[dict[str, Any]]) -> int:
    expected = [
        ("contract_frozen", {"contract_sha256": contract["contract_sha256"]}),
        *(
            ("task_slot_replaced", event)
            for event in contract["final_pool"]["task_slot_replacement_budget"]["audit_events"]
        ),
        (
            "schedule_frozen",
            {
                "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
                "schedule_sha256": contract["schedule"]["schedule_sha256"],
                "cells": len(contract["schedule"]["cells"]),
            },
        ),
    ]
    if len(events) < len(expected):
        raise ExperimentConfigurationError("ledger metadata prefix is incomplete")
    for event, (event_type, payload) in zip(events[: len(expected)], expected, strict=True):
        if event.get("event_type") != event_type or _payload(event) != payload:
            raise ExperimentConfigurationError("ledger metadata differs from frozen contract")
    return len(expected)


def initialize_ledger(contract: dict[str, Any], ledger_path: Path) -> list[dict[str, Any]]:
    """Create the immutable ledger prefix, or validate an existing prefix."""

    events = read_ledger(ledger_path)
    if events:
        _validate_metadata_events(contract, events)
        return events
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


def next_legal_action(
    contract: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    initial_trajectory_attempt: int = 1,
    initial_reruns_consumed: int = 0,
    initially_rerun_cells: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Derive the only legal next action from the verified hash chain."""

    index = _validate_metadata_events(contract, events)
    runtime = events[index:]
    cells = contract["schedule"]["cells"]
    initial_context = (
        initial_trajectory_attempt,
        initial_reruns_consumed,
        initially_rerun_cells,
    )
    allowed_initial_contexts = {
        (1, 0, frozenset()),
        (2, 1, frozenset({cells[0]["cell_id"]})),
        # A separately accounted operator interruption can consume the first
        # cell's second and final attempt without consuming infrastructure
        # rerun budget. The continuation layer validates that frozen lineage
        # before selecting this context.
        (2, 0, frozenset({cells[0]["cell_id"]})),
    }
    if initial_context not in allowed_initial_contexts:
        raise ExperimentConfigurationError("unsupported initial ledger accounting")
    position = 0
    attempt = initial_trajectory_attempt
    started: dict[str, Any] | None = None
    last_finished: dict[str, Any] | None = None
    used_roots: set[str] = set()

    for event_index, event in enumerate(runtime, start=index):
        event_type = event.get("event_type")
        payload = _payload(event)
        if event_type == "batch_stopped":
            if event is not runtime[-1]:
                raise ExperimentConfigurationError("events exist after batch stop")
            return {"action": "batch_stopped", "payload": payload}
        if position >= len(cells):
            raise ExperimentConfigurationError("ledger contains events after final cell")
        cell = cells[position]
        if event_type == "attempt_started":
            if started is not None or last_finished is not None:
                raise ExperimentConfigurationError("attempt start is out of order")
            if payload.get("cell_id") != cell["cell_id"] or payload.get("trajectory_attempt") != attempt:
                raise ExperimentConfigurationError("attempt start does not match next frozen cell")
            roots = payload.get("isolation_roots", {})
            root_values = set(roots.values()) if isinstance(roots, dict) else set()
            if used_roots.intersection(root_values):
                raise ExperimentConfigurationError("attempt start reuses a prior isolation root")
            validate_preflight(contract, payload)
            used_roots.update(root_values)
            started = payload
        elif event_type == "attempt_finished":
            if started is None or last_finished is not None:
                raise ExperimentConfigurationError("attempt finish has no unique matching start")
            if payload.get("cell_id") != cell["cell_id"] or payload.get("trajectory_attempt") != attempt:
                raise ExperimentConfigurationError("attempt finish identity mismatch")
            classification = classify_receipt(contract, payload)
            started = None
            last_finished = payload
            if classification["counts_as_experimental_outcome"]:
                position += 1
                attempt = 1
                last_finished = None
            elif classification["stop_batch"]:
                # A batch_stopped event must durably follow before any next launch.
                continue
            elif not classification["same_cell_rerun_permitted"]:
                raise ExperimentConfigurationError("attempt termination has no frozen transition")
        elif event_type == "infrastructure_rerun_authorized":
            if last_finished is None:
                raise ExperimentConfigurationError("infrastructure rerun authorization is out of order")
            expected = _infrastructure_rerun_state_with_initial(
                contract, events[:event_index], last_finished,
                initial_reruns_consumed, initially_rerun_cells,
            )
            if payload != {"cell_id": cell["cell_id"], **expected}:
                raise ExperimentConfigurationError("infrastructure rerun authorization mismatch")
            attempt = expected["next_attempt"]
            last_finished = None
        elif event_type in {"deviation"}:
            continue
        else:
            raise ExperimentConfigurationError(f"unexpected runtime ledger event: {event_type}")

    if started is not None:
        return {"action": "resolve_partial", "request": started}
    if last_finished is not None:
        classification = classify_receipt(contract, last_finished)
        if classification["stop_batch"]:
            return {"action": "record_batch_stop", "receipt": last_finished}
        if classification["same_cell_rerun_permitted"]:
            budget = contract["trajectory_infrastructure_rerun_budget"]
            consumed = initial_reruns_consumed + sum(
                event.get("event_type") == "infrastructure_rerun_authorized"
                for event in events
            )
            already_rerun = last_finished["cell_id"] in initially_rerun_cells or any(
                event.get("event_type") == "infrastructure_rerun_authorized"
                and event.get("payload", {}).get("cell_id") == last_finished["cell_id"]
                for event in events
            )
            if (
                consumed >= budget["allowance"]
                or last_finished["trajectory_attempt"] >= budget["maximum_attempts_per_cell"]
                or already_rerun
            ):
                return {
                    "action": "record_rerun_budget_stop",
                    "receipt": last_finished,
                    "consumed": consumed,
                }
            state = _infrastructure_rerun_state_with_initial(
                contract, events, last_finished,
                initial_reruns_consumed, initially_rerun_cells,
            )
            return {
                "action": "authorize_infrastructure_rerun",
                "receipt": last_finished,
                "state": state,
            }
    if position == len(cells):
        return {"action": "complete"}
    return {"action": "launch", "cell": cells[position], "trajectory_attempt": attempt}


def _infrastructure_rerun_state_with_initial(
    contract: dict[str, Any],
    events: list[dict[str, Any]],
    receipt: dict[str, Any],
    initial_consumed: int,
    initially_rerun_cells: frozenset[str],
) -> dict[str, int]:
    if initial_consumed == 0 and not initially_rerun_cells:
        return infrastructure_rerun_state(contract, events, receipt)
    classification = classify_receipt(contract, receipt)
    if not classification["same_cell_rerun_permitted"]:
        raise ExperimentConfigurationError(
            "termination cannot consume infrastructure rerun budget"
        )
    consumed = initial_consumed + sum(
        event.get("event_type") == "infrastructure_rerun_authorized" for event in events
    )
    budget = contract["trajectory_infrastructure_rerun_budget"]
    if consumed >= budget["allowance"]:
        raise ExperimentConfigurationError("trajectory infrastructure rerun budget exhausted")
    if receipt["trajectory_attempt"] >= budget["maximum_attempts_per_cell"]:
        raise ExperimentConfigurationError("same cell has exhausted its attempt allowance")
    if receipt["cell_id"] in initially_rerun_cells or any(
        event.get("event_type") == "infrastructure_rerun_authorized"
        and event.get("payload", {}).get("cell_id") == receipt["cell_id"]
        for event in events
    ):
        raise ExperimentConfigurationError(
            "same cell already consumed its infrastructure rerun"
        )
    return {
        "consumed": consumed + 1,
        "remaining": budget["allowance"] - consumed - 1,
        "next_attempt": receipt["trajectory_attempt"] + 1,
    }


def normalize_receipt_timestamp(value: object, field: str) -> str:
    """Return one faithful timezone-aware ISO timestamp or fail closed."""

    observed = value() if isinstance(value, Callable) else value
    if not isinstance(observed, str):
        raise ExperimentConfigurationError(f"{field} timestamp has an unsupported type")
    try:
        parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExperimentConfigurationError(f"{field} timestamp is malformed") from error
    if parsed.tzinfo is None:
        raise ExperimentConfigurationError(f"{field} timestamp is timezone-naive")
    return observed


def _sum_usage(results: list[SubjectResult]) -> dict[str, int]:
    provider_fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    if any(
        any(
            not isinstance(item.usage.get(field), int)
            or isinstance(item.usage.get(field), bool)
            or item.usage[field] < 0
            for field in provider_fields
        )
        for item in results
    ):
        return {}
    usage = {
        field: sum(item.usage[field] for item in results)
        for field in provider_fields
    }
    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage


def _evaluator_receipt(results: list[EvaluatorResult]) -> dict[str, Any]:
    final = results[-1] if results else None
    return {
        "official": True,
        "rounds": len(results),
        "exit_status": None if final is None else final.exit_code,
        "resolved": None if final is None else final.resolved,
        "failing_checks": [] if final is None else list(final.failing_checks),
        "report_reference": None if final is None else final.report_reference,
        "results_reference": None if final is None else final.results_reference,
        "report_sha256": None if final is None else final.report_sha256,
        "results_sha256": None if final is None else final.results_sha256,
        "official_disposition": (
            None if final is None else final.official_disposition
        ),
        "feedback_status": None if final is None else final.feedback_status,
    }


def execute_attempt(
    contract: dict[str, Any], request: dict[str, Any], backend: RunnerBackend
) -> dict[str, Any]:
    """Run one attempt, applying only the frozen one-round corrective rule."""

    validate_preflight(contract, request)
    prepared = backend.prepare(request)
    try:
        return _execute_prepared_attempt(contract, request, backend, prepared)
    finally:
        backend.cleanup(prepared)


def _execute_prepared_attempt(
    contract: dict[str, Any],
    request: dict[str, Any],
    backend: RunnerBackend,
    prepared: dict[str, Any],
) -> dict[str, Any]:
    subjects: list[SubjectResult] = []
    evaluations: list[EvaluatorResult] = []
    termination: str

    first = backend.run_subject(request, prepared, None, None)
    subjects.append(first)
    if first.timed_out:
        termination = "trajectory_timeout"
    elif first.provider_infrastructure_failure:
        termination = "provider_api_infrastructure_failure"
    elif first.exit_code != 0 or not first.session_id:
        termination = "agent_subject_failure"
    else:
        prediction = backend.create_prediction(request, prepared)
        evaluation = backend.evaluate(request, prepared, prediction, 0)
        evaluations.append(evaluation)
        if evaluation.timed_out or evaluation.infrastructure_failure:
            termination = "local_docker_runtime_infrastructure_failure"
        elif evaluation.malformed:
            termination = "malformed_incomplete_measurement"
        elif evaluation.exit_code != 0 or evaluation.resolved is None:
            termination = "local_docker_runtime_infrastructure_failure"
        elif evaluation.resolved:
            termination = "accepted_completed"
        elif not evaluation.failing_checks:
            termination = "malformed_incomplete_measurement"
        else:
            correction = backend.run_subject(
                request, prepared, evaluation.failing_checks, first.session_id
            )
            subjects.append(correction)
            if correction.timed_out:
                termination = "trajectory_timeout"
            elif correction.provider_infrastructure_failure:
                termination = "provider_api_infrastructure_failure"
            elif correction.session_id != first.session_id:
                termination = "isolation_contract_violation"
            elif correction.exit_code != 0:
                termination = "agent_subject_failure"
            else:
                prediction = backend.create_prediction(request, prepared)
                final = backend.evaluate(request, prepared, prediction, 1)
                evaluations.append(final)
                if final.timed_out or final.infrastructure_failure or final.exit_code != 0:
                    termination = "local_docker_runtime_infrastructure_failure"
                elif final.malformed:
                    termination = "malformed_incomplete_measurement"
                elif final.resolved is True:
                    termination = "accepted_completed"
                elif final.resolved is False:
                    termination = "evaluator_test_failure"
                else:
                    termination = "malformed_incomplete_measurement"

    usage = _sum_usage(subjects)
    required = contract["usage"]["required_provider_reported_fields"]
    usage_complete = bool(usage) and all(
        isinstance(usage.get(field), int) and usage[field] >= 0 for field in required
    ) and isinstance(usage.get("total_tokens"), int)
    if termination in EXPERIMENTAL_OUTCOMES and not usage_complete:
        termination = "malformed_incomplete_measurement"
    evaluator_result = _evaluator_receipt(evaluations)
    receipt = {
        **request,
        "started_at": normalize_receipt_timestamp(prepared.get("started_at"), "started_at"),
        "ended_at": normalize_receipt_timestamp(prepared.get("ended_at"), "ended_at"),
        "termination": termination,
        "evaluator_result": evaluator_result,
        "usage": usage,
        "usage_complete": usage_complete,
        "admissible_under_contract": termination in EXPERIMENTAL_OUTCOMES and usage_complete,
        "deviations": [],
    }
    classify_receipt(contract, receipt)
    return receipt


def dry_run_receipt(
    contract: dict[str, Any],
    root: Path,
    state_root: Path,
    resolved_tasks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve all frozen cells without creating state or launching processes."""

    validate_contract(contract, root)
    cells = []
    prior: list[dict[str, Any]] = []
    for cell in contract["schedule"]["cells"]:
        task = resolved_tasks.get(cell["actual_task_id"])
        if task is None:
            raise ExperimentConfigurationError(f"task input is unresolved: {cell['actual_task_id']}")
        slot = next(
            item for item in contract["final_pool"]["slots"]
            if item["slot"] == cell["requested_task_slot"]
        )
        if (
            task.get("instance_id") != cell["actual_task_id"]
            or task.get("repo") != slot["repo"]
            or task.get("language") != slot["language"]
            or task.get("docker_image") is None
            or task.get("base_commit") is None
            or task.get("problem_statement_sha256") is None
        ):
            raise ExperimentConfigurationError(f"task immutable input mismatch: {cell['cell_id']}")
        request = build_launch_request(contract, cell, state_root, 1)
        validate_preflight(contract, request, tuple(prior))
        prior.append(request)
        cells.append(
            {
                "position": cell["position"],
                "cell_id": cell["cell_id"],
                "task_snapshot_sha256": slot["task_snapshot_sha256"],
                "problem_statement_sha256": task["problem_statement_sha256"],
                "base_commit": task["base_commit"],
                "docker_image": task["docker_image"],
                "arm": cell["arm"],
                "intervention_sha256": request["intervention_sha256"],
                "subject_sha256": hashlib.sha256(
                    json.dumps(contract["subject"], sort_keys=True).encode()
                ).hexdigest(),
            }
        )
    return {
        "schema_name": DRY_RUN_SCHEMA,
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "cells_resolved": len(cells),
        "codex_invocations": 0,
        "evaluator_invocations": 0,
        "ledger_modified": False,
        "pilot_cells_executed": 0,
        "policy_comparisons_executed": 0,
        "cells": cells,
    }
