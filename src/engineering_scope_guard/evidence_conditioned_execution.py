"""Frozen execution contract and state machine for the exploratory review.

This module is deterministic and performs no provider, evaluator, Docker, or
network calls. Process adapters live in ``scripts/evidence_conditioned_runner.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from .experiment import ExperimentConfigurationError
from .pilot_contract import canonical_bytes, digest, read_object
from .pilot_runner import EvaluatorResult, SubjectResult, canonical_attempt_timeout
from .pilot_v3 import (
    append_event,
    classify_termination,
    evaluator_transition,
    next_scheduler_action,
    read_events,
    usage_summary,
)

CONTRACT_VERSION = "evidence-conditioned-final-scope-review-execution-v0.1"
CONTRACT_SCHEMA = (
    "engineering-scope-guard.evidence-conditioned-final-scope-review-execution-contract"
)
CONTRACT_PATH = Path(
    "experiment/evidence_conditioned_final_scope_review_v0_1_execution_contract.json"
)
DESIGN_PATH = Path(
    "experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json"
)
FREEZE_PATH = Path(
    "experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_freeze.json"
)
TREATMENT_PATH = Path(
    "experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt"
)
TREATMENT_SHA256 = "d9ac9e18716428e9cd6d038388b01ec668ade47df8bac014658897752166b8cb"
MODEL = "gpt-5.6-terra"
REASONING_EFFORT = "medium"
CODEX_VERSION = "0.151.0"
EVALUATOR_REVISION = "bc09878a5d192d0804dbd647dc6e650372fcb0ac"
REPOLAUNCH_REVISION = "c4b623d930f3728e5338664bb634021b98492cbf"
MAXIMUM_ATTEMPTS_PER_CELL = 2
INFRASTRUCTURE_RETRY_ALLOWANCE = 4
OPERATOR_INTERRUPTION_ALLOWANCE = 2

RUNNER_COMPONENT_PATHS = (
    Path("src/engineering_scope_guard/evidence_conditioned_execution.py"),
    Path("src/engineering_scope_guard/evidence_conditioned_analysis.py"),
    Path("scripts/evidence_conditioned_runner.py"),
    Path("scripts/evidence_conditioned_analysis.py"),
    Path("src/engineering_scope_guard/pilot_runner.py"),
    Path("src/engineering_scope_guard/pilot_v3.py"),
    Path("src/engineering_scope_guard/pilot_v3_analysis.py"),
    Path("scripts/pilot_runner.py"),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _expanded_cells(freeze: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {
        item["opaque_task_commitment"]: item
        for item in freeze["selection"]["selected"]
    }
    cells = []
    for cell in freeze["schedule"]["cells"]:
        task = selected.get(cell["opaque_task_commitment"])
        _require(task is not None, "schedule references an unknown frozen task")
        cells.append(
            {
                **cell,
                "actual_task_id": task["opaque_instance_identity"],
                "language": task["language"],
                "repository_identity": task["repository_identity"],
                "container_image_identity": task["container_image_identity"],
                "container_registry_manifest_sha256": task[
                    "container_registry_manifest_sha256"
                ],
            }
        )
    return cells


def build_contract(root: Path) -> dict[str, Any]:
    """Build the execution contract without changing any frozen design bytes."""

    design = read_object(root / DESIGN_PATH)
    freeze = read_object(root / FREEZE_PATH)
    treatment_sha256 = sha256_file(root / TREATMENT_PATH)
    _require(treatment_sha256 == TREATMENT_SHA256, "treatment bytes changed")
    _require(
        freeze["design"]["sha256"] == sha256_file(root / DESIGN_PATH),
        "frozen design identity changed",
    )
    _require(
        freeze["treatment"]["sha256"] == treatment_sha256,
        "freeze treatment identity changed",
    )
    _require(freeze["schedule"]["cell_count"] == 32, "schedule is not 32 cells")
    _require(
        freeze["confirmatory_reserve"]["remaining_ids_or_bodies_emitted"] is False,
        "confirmatory reserve is no longer opaque",
    )
    pilot_v3 = read_object(root / "experiment/pilot_v3_execution_contract.json")
    environment = pilot_v3["environment"]
    _require(
        environment["official_evaluator_revision"] == EVALUATOR_REVISION,
        "qualified evaluator identity changed",
    )
    _require(
        environment["repolaunch_revision"] == REPOLAUNCH_REVISION,
        "qualified RepoLaunch identity changed",
    )
    components = {
        str(path): sha256_file(root / path) for path in RUNNER_COMPONENT_PATHS
    }
    value: dict[str, Any] = {
        "schema_name": CONTRACT_SCHEMA,
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "status": "qualified-zero-live-execution-interface",
        "frozen_identities": {
            "design_path": str(DESIGN_PATH),
            "design_sha256": sha256_file(root / DESIGN_PATH),
            "design_version": freeze["design"]["version"],
            "freeze_path": str(FREEZE_PATH),
            "freeze_sha256": sha256_file(root / FREEZE_PATH),
            "exploratory_pool_commitment_sha256": freeze["selection"][
                "exploratory_pool_commitment_sha256"
            ],
            "schedule_sha256": freeze["schedule"]["schedule_sha256"],
            "confirmatory_reserve": freeze["confirmatory_reserve"],
            "treatment_path": str(TREATMENT_PATH),
            "treatment_sha256": treatment_sha256,
            "analysis_sha256": digest(design["analysis"]),
            "retirement_gates_sha256": digest(design["retirement_gates"]),
        },
        "arms": {
            "ids": ["baseline", "treatment"],
            "baseline_intervention": None,
            "treatment_sha256": treatment_sha256,
            "other_arms_permitted": False,
        },
        "delivery": {
            "mechanism": "same-session post-task resume",
            "ordinary_task_turn": "task bytes only in both arms",
            "activation_boundary": (
                "after the ordinary task turn terminates successfully with a durable "
                "session identity and before prediction/evaluator construction"
            ),
            "baseline_resume": False,
            "treatment_resume": True,
            "treatment_resume_stdin": "exact treatment bytes only",
            "pre_activation_treatment_exposure": False,
            "activation_count_per_treatment_attempt": 1,
            "second_review_agent": False,
        },
        "subject": {
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "codex_version": CODEX_VERSION,
            "ignore_user_config": True,
            "ignore_rules": True,
            "hooks": [],
            "mcp_servers": [],
            "plugins": [],
            "network_or_browser_tools": [],
        },
        "source_and_evaluator": {
            "dataset": freeze["source"]["dataset"],
            "dataset_revision": freeze["source"]["revision"],
            "dataset_snapshot_files_sha256": freeze["source"][
                "dataset_snapshot_files_sha256"
            ],
            "official_evaluator_revision": EVALUATOR_REVISION,
            "repolaunch_revision": REPOLAUNCH_REVISION,
            "workers": 1,
        },
        "platform": environment["docker"],
        "attempt_accounting": {
            "maximum_attempts_per_cell": MAXIMUM_ATTEMPTS_PER_CELL,
            "infrastructure_retry_allowance": INFRASTRUCTURE_RETRY_ALLOWANCE,
            "operator_interruption_allowance": OPERATOR_INTERRUPTION_ALLOWANCE,
            "all_categories_share_per_cell_maximum": True,
            "allowances_are_separate": True,
            "valid_negative_outcomes_are_never_rerun": True,
        },
        "corrective_round": {
            "maximum": design["corrective_round"]["maximum"],
            "rules": design["corrective_round"]["rules"],
            "same_session": True,
        },
        "trajectory": {
            "canonical_timeout_schema": "pilot-v3.0",
            "timeout_seconds_per_attempt": 1800,
            "timeout_seconds_per_turn": 900,
            "maximum_corrective_rounds": 1,
        },
        "durability": {
            "ledger": "fsynced canonical JSONL SHA-256 hash chain",
            "restart_source": "durable ledger only",
            "completed_cells_never_repeat": True,
            "evaluator_checkpoint_precedes_receipt": True,
            "credential_cleanup_precedes_receipt": True,
        },
        "isolation": {
            "fresh_per_attempt": design["isolation_and_durability"][
                "fresh_per_attempt"
            ],
            "inheritance_between_attempts_permitted": False,
        },
        "runner_components_sha256": components,
        "schedule": {
            "schedule_sha256": freeze["schedule"]["schedule_sha256"],
            "cells": _expanded_cells(freeze),
            "manual_or_adaptive_reordering_permitted": False,
        },
        "qualification": {
            "subject_calls": 0,
            "evaluator_calls": 0,
            "experimental_observations": 0,
            "live_state_mutation": False,
        },
    }
    value["contract_sha256"] = digest(value)
    return value


def validate_contract(root: Path, contract: dict[str, Any]) -> None:
    _require(
        canonical_bytes(contract) == canonical_bytes(build_contract(root)),
        "execution contract drifted from frozen authorities",
    )
    trajectory = dict(contract["trajectory"])
    timeout_schema = trajectory.pop("canonical_timeout_schema")
    canonical_attempt_timeout(timeout_schema, trajectory)


def execution_confirmation(contract: dict[str, Any]) -> str:
    return f"execute-{CONTRACT_VERSION}:{contract['contract_sha256']}"


def build_launch_request(
    contract: dict[str, Any], cell: dict[str, Any], state_root: Path, attempt: int
) -> dict[str, Any]:
    if attempt < 1 or attempt > MAXIMUM_ATTEMPTS_PER_CELL:
        raise ExperimentConfigurationError("attempt is outside the frozen maximum")
    root = state_root / "attempts" / cell["cell_id"] / f"attempt-{attempt}"
    isolation_roots = {
        "repository": str(root / "repository"),
        "codex_home": str(root / "codex-home"),
        "raw": str(root / "raw"),
        "derived": str(root / "derived"),
        "evaluator": str(root / "evaluator"),
    }
    treatment = None if cell["arm"] == "baseline" else contract["arms"]["treatment_sha256"]
    return {
        **cell,
        "trajectory_attempt": attempt,
        "contract_sha256": contract["contract_sha256"],
        "pool_sha256": contract["frozen_identities"][
            "exploratory_pool_commitment_sha256"
        ],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "confirmatory_reserve_commitment_sha256": contract["frozen_identities"][
            "confirmatory_reserve"
        ]["commitment_sha256"],
        "isolation_roots": isolation_roots,
        "credential_copy_identity": str(
            Path(isolation_roots["codex_home"]) / "auth.json"
        ),
        "session_identity": f"fresh-unassigned:{cell['cell_id']}:attempt-{attempt}",
        "intervention_sha256": treatment,
        "delivery": contract["delivery"],
        "subject": contract["subject"],
        "source_and_evaluator": contract["source_and_evaluator"],
        "platform": contract["platform"],
        "trajectory_contract": contract["trajectory"],
    }


def dry_run_receipt(contract: dict[str, Any], state_root: Path) -> dict[str, Any]:
    requests = [
        build_launch_request(contract, cell, state_root, 1)
        for cell in contract["schedule"]["cells"]
    ]
    roots = [
        root
        for request in requests
        for root in request["isolation_roots"].values()
    ]
    baseline = [request for request in requests if request["arm"] == "baseline"]
    treatment = [request for request in requests if request["arm"] == "treatment"]
    plans = [
        {
            "position": request["position"],
            "cell_id": request["cell_id"],
            "arm": request["arm"],
            "trajectory_attempt": request["trajectory_attempt"],
            "ordinary_task_treatment_exposure": False,
            "late_stage_resume": request["arm"] == "treatment",
            "late_stage_stdin_sha256": request["intervention_sha256"],
        }
        for request in requests
    ]
    _require(len(requests) == 32, "dry-run did not resolve all cells")
    _require(len(roots) == len(set(roots)), "dry-run isolation roots overlap")
    _require(
        all(item["intervention_sha256"] is None for item in baseline),
        "baseline treatment leakage detected",
    )
    _require(
        all(item["intervention_sha256"] == TREATMENT_SHA256 for item in treatment),
        "treatment delivery identity changed",
    )
    return {
        "schema_name": (
            "engineering-scope-guard.evidence-conditioned-final-scope-review-execution-dry-run"
        ),
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "cells_resolved": len(requests),
        "positions": [item["position"] for item in requests],
        "all_cells_begin_at_attempt": 1,
        "all_isolation_roots_unique": True,
        "baseline_cells": len(baseline),
        "treatment_cells": len(treatment),
        "delivery_plans": plans,
        "subject_calls": 0,
        "evaluator_calls": 0,
        "experimental_observations": 0,
        "ledger_written": False,
    }


def initialize_ledger(contract: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    events = read_events(path)
    expected = (
        ("contract_frozen", {"contract_sha256": contract["contract_sha256"]}),
        (
            "pool_frozen",
            {
                "pool_sha256": contract["frozen_identities"][
                    "exploratory_pool_commitment_sha256"
                ]
            },
        ),
        (
            "schedule_frozen",
            {
                "schedule_sha256": contract["schedule"]["schedule_sha256"],
                "cells": len(contract["schedule"]["cells"]),
            },
        ),
    )
    if events:
        _require(len(events) >= 3, "execution ledger prefix is incomplete")
        _require(
            all(
                event["event_type"] == kind and event["payload"] == payload
                for event, (kind, payload) in zip(
                    events[: len(expected)], expected, strict=True
                )
            ),
            "execution ledger prefix mismatch",
        )
        return events
    for kind, payload in expected:
        append_event(path, kind, payload)
    return read_events(path)


class ExecutionBackend(Protocol):
    def prepare(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def cleanup(self, prepared: dict[str, Any]) -> None: ...
    def run_ordinary(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> SubjectResult: ...
    def run_treatment(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        treatment: bytes,
        session_id: str,
    ) -> SubjectResult: ...
    def run_correction(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...],
        session_id: str,
    ) -> SubjectResult: ...
    def create_prediction(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]: ...
    def evaluate(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prediction: dict[str, Any],
        round_number: int,
    ) -> EvaluatorResult: ...


def _subject_checkpoint(
    result: SubjectResult, request: dict[str, Any], phase: str, turn_index: int
) -> dict[str, Any]:
    terminal = None
    if result.timed_out:
        terminal = "trajectory_timeout"
    elif result.provider_infrastructure_failure:
        terminal = "provider_api_infrastructure_failure"
    elif result.exit_code != 0 or not result.session_id:
        terminal = "agent_subject_failure"
    return {
        "cell_id": request["cell_id"],
        "trajectory_attempt": request["trajectory_attempt"],
        "phase": phase,
        "turn_index": turn_index,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "session_id": result.session_id,
        "usage": result.usage,
        "trace_reference": result.trace_reference,
        "provider_infrastructure_failure": result.provider_infrastructure_failure,
        "terminal_if_any": terminal,
    }


def _evaluator_checkpoint(
    result: EvaluatorResult, request: dict[str, Any], round_number: int
) -> dict[str, Any]:
    disposition = result.official_disposition
    feedback_status = result.feedback_status
    feedback_shape_valid = (
        disposition == "failure"
        and feedback_status in {"available", "unavailable"}
        and ((feedback_status == "available") == bool(result.failing_checks))
    ) or (
        disposition in {"success", "error", "incomplete", "empty_patch"}
        and feedback_status == "not_applicable"
        and not result.failing_checks
    )
    if result.timed_out:
        terminal = "local_docker_runtime_infrastructure_failure"
    elif (
        result.malformed
        or disposition is None
        or feedback_status is None
        or not feedback_shape_valid
    ):
        terminal = "malformed_inconsistent_measurement"
    elif result.exit_code != 0 and disposition not in {"error", "incomplete"}:
        terminal = "local_docker_runtime_infrastructure_failure"
    else:
        terminal = evaluator_transition(disposition, feedback_status, round_number).get(
            "termination"
        )
    return {
        "cell_id": request["cell_id"],
        "trajectory_attempt": request["trajectory_attempt"],
        "round": round_number,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "official_disposition": disposition,
        "feedback_status": feedback_status,
        "failing_checks": list(result.failing_checks),
        "report_reference": result.report_reference,
        "results_reference": result.results_reference,
        "report_sha256": result.report_sha256,
        "results_sha256": result.results_sha256,
        "infrastructure_failure": result.infrastructure_failure,
        "malformed": result.malformed,
        "terminal_if_any": terminal,
    }


def _receipt_from_checkpoints(
    request: dict[str, Any],
    subjects: list[dict[str, Any]],
    evaluators: list[dict[str, Any]],
    cleanup: dict[str, Any],
    activations: list[dict[str, Any]],
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    _require(cleanup.get("credential_removed") is True, "credential cleanup is absent")
    terminals = [
        item["terminal_if_any"]
        for item in subjects + evaluators
        if item.get("terminal_if_any")
    ]
    _require(len(terminals) == 1, "terminal evidence is missing or contradictory")
    terminal = terminals[0]
    classification = classify_termination(terminal)
    subject_terminal = any(item.get("terminal_if_any") for item in subjects)
    if not subject_terminal:
        _require(bool(evaluators), "durable evaluator checkpoint is absent")
    if request["arm"] == "baseline":
        _require(not activations, "baseline contains treatment activation")
    else:
        ordinary_terminal = any(
            item.get("phase") == "ordinary" and item.get("terminal_if_any")
            for item in subjects
        )
        _require(
            len(activations) == 1 or (not activations and ordinary_terminal),
            "treatment activation evidence is not singular",
        )
        if activations:
            _require(
                activations[0].get("treatment_sha256")
                == request["intervention_sha256"],
                "treatment activation identity changed",
            )
    return {
        **request,
        "started_at": started_at,
        "ended_at": ended_at,
        "termination": terminal,
        "admissible": classification["admissible"],
        "usage": usage_summary([item["usage"] for item in subjects]),
        "usage_complete": True,
        "subject_turns": len(subjects),
        "corrective_rounds": sum(item["phase"] == "corrective" for item in subjects),
        "treatment_activation": {
            "activated": bool(activations),
            "pre_activation_subject_turns": sum(
                item["phase"] == "ordinary" for item in subjects
            ),
            "post_activation_subject_turns": sum(
                item["phase"] in {"treatment", "corrective"} for item in subjects
            ),
            "evidence": activations,
        },
        "subject_checkpoints": subjects,
        "evaluator_checkpoints": evaluators,
        "credential_cleanup": cleanup,
        "deviations": [],
    }


def execute_attempt_durably(
    contract: dict[str, Any],
    request: dict[str, Any],
    backend: ExecutionBackend,
    ledger_path: Path,
    treatment_bytes: bytes,
) -> dict[str, Any]:
    """Execute one attempt with auditable post-task treatment activation."""

    _require(
        hashlib.sha256(treatment_bytes).hexdigest() == TREATMENT_SHA256,
        "treatment bytes changed at execution boundary",
    )
    prepared = backend.prepare(request)
    subjects: list[dict[str, Any]] = []
    evaluators: list[dict[str, Any]] = []
    activations: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {}
    append_event(
        ledger_path,
        "isolation_verified",
        {
            "cell_id": request["cell_id"],
            "trajectory_attempt": request["trajectory_attempt"],
            "isolation_identities_sha256": digest(request["isolation_roots"]),
            "credential_copy_identity": request["credential_copy_identity"],
        },
    )
    try:
        ordinary_result = backend.run_ordinary(request, prepared)
        ordinary = _subject_checkpoint(ordinary_result, request, "ordinary", 1)
        subjects.append(ordinary)
        append_event(ledger_path, "subject_terminated", ordinary)
        active_session = ordinary_result.session_id
        if ordinary["terminal_if_any"] is None and request["arm"] == "treatment":
            activation = {
                "cell_id": request["cell_id"],
                "trajectory_attempt": request["trajectory_attempt"],
                "activation_index": 1,
                "after_phase": "ordinary",
                "pre_activation_subject_turns": 1,
                "treatment_sha256": TREATMENT_SHA256,
                "delivery": "same-session post-task resume",
            }
            activations.append(activation)
            append_event(ledger_path, "treatment_activation_started", activation)
            treatment_result = backend.run_treatment(
                request, prepared, treatment_bytes, active_session
            )
            treatment = _subject_checkpoint(treatment_result, request, "treatment", 2)
            if treatment_result.session_id != active_session:
                treatment["terminal_if_any"] = "isolation_contract_violation"
            subjects.append(treatment)
            append_event(ledger_path, "subject_terminated", treatment)
            active_session = treatment_result.session_id
        if not any(item["terminal_if_any"] for item in subjects):
            prediction = backend.create_prediction(request, prepared)
            append_event(
                ledger_path,
                "evaluator_invoked",
                {
                    "cell_id": request["cell_id"],
                    "trajectory_attempt": request["trajectory_attempt"],
                    "round": 0,
                    "prediction_sha256": prediction["patch_sha256"],
                    "official_evaluator_revision": contract["source_and_evaluator"][
                        "official_evaluator_revision"
                    ],
                },
            )
            first_result = backend.evaluate(request, prepared, prediction, 0)
            first = _evaluator_checkpoint(first_result, request, 0)
            evaluators.append(first)
            append_event(ledger_path, "evaluator_finished", first)
            if (
                first["official_disposition"] == "failure"
                and first["feedback_status"] == "available"
                and first["terminal_if_any"] is None
            ):
                correction_result = backend.run_correction(
                    request,
                    prepared,
                    tuple(first["failing_checks"]),
                    active_session,
                )
                correction = _subject_checkpoint(
                    correction_result, request, "corrective", len(subjects) + 1
                )
                if correction_result.session_id != active_session:
                    correction["terminal_if_any"] = "isolation_contract_violation"
                subjects.append(correction)
                append_event(ledger_path, "subject_terminated", correction)
                if correction["terminal_if_any"] is None:
                    prediction = backend.create_prediction(request, prepared)
                    append_event(
                        ledger_path,
                        "evaluator_invoked",
                        {
                            "cell_id": request["cell_id"],
                            "trajectory_attempt": request["trajectory_attempt"],
                            "round": 1,
                            "prediction_sha256": prediction["patch_sha256"],
                            "official_evaluator_revision": contract[
                                "source_and_evaluator"
                            ]["official_evaluator_revision"],
                        },
                    )
                    final_result = backend.evaluate(request, prepared, prediction, 1)
                    final = _evaluator_checkpoint(final_result, request, 1)
                    evaluators.append(final)
                    append_event(ledger_path, "evaluator_finished", final)
    finally:
        backend.cleanup(prepared)
        cleanup = {
            "cell_id": request["cell_id"],
            "trajectory_attempt": request["trajectory_attempt"],
            "credential_removed": not Path(
                request["credential_copy_identity"]
            ).exists(),
        }
        append_event(ledger_path, "credential_cleanup_verified", cleanup)
        _require(cleanup["credential_removed"], "trajectory credential cleanup failed")
    receipt = _receipt_from_checkpoints(
        request,
        subjects,
        evaluators,
        cleanup,
        activations,
        prepared["started_at"],
        prepared["ended_at"]() if callable(prepared["ended_at"]) else prepared["ended_at"],
    )
    append_event(ledger_path, "receipt_committed", receipt)
    return receipt


def reconstruct_receipt_from_events(
    request: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    relevant = [
        event
        for event in events
        if event["payload"].get("cell_id") == request["cell_id"]
        and event["payload"].get("trajectory_attempt")
        == request["trajectory_attempt"]
    ]
    subjects = [
        event["payload"] for event in relevant if event["event_type"] == "subject_terminated"
    ]
    evaluators = [
        event["payload"] for event in relevant if event["event_type"] == "evaluator_finished"
    ]
    activations = [
        event["payload"]
        for event in relevant
        if event["event_type"] == "treatment_activation_started"
    ]
    cleanup = [
        event["payload"]
        for event in relevant
        if event["event_type"] == "credential_cleanup_verified"
    ]
    _require(bool(cleanup), "durable credential cleanup evidence is absent")
    started_at = request.get("attempt_started_at")
    _require(isinstance(started_at, str), "durable attempt start time is absent")
    ended_at = relevant[-1]["recorded_at"] if relevant else started_at
    return _receipt_from_checkpoints(
        request,
        subjects,
        evaluators,
        cleanup[-1],
        activations,
        started_at,
        ended_at,
    )


def next_legal_action(
    contract: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Use the already-qualified Pilot-v3 ledger scheduler without new policy."""

    _validate_execution_ledger(contract, events)
    return next_scheduler_action(contract, events)


def _validate_execution_ledger(
    contract: dict[str, Any], events: list[dict[str, Any]]
) -> None:
    """Reject assignment, ordering, attempt, and allowance contradictions."""

    _require(len(events) >= 3, "execution ledger prefix is incomplete")
    expected_prefix = (
        ("contract_frozen", {"contract_sha256": contract["contract_sha256"]}),
        (
            "pool_frozen",
            {
                "pool_sha256": contract["frozen_identities"][
                    "exploratory_pool_commitment_sha256"
                ]
            },
        ),
        (
            "schedule_frozen",
            {
                "schedule_sha256": contract["schedule"]["schedule_sha256"],
                "cells": len(contract["schedule"]["cells"]),
            },
        ),
    )
    _require(
        all(
            event["event_type"] == kind and event["payload"] == payload
            for event, (kind, payload) in zip(
                events[:3], expected_prefix, strict=True
            )
        ),
        "execution ledger prefix mismatch",
    )
    cells = contract["schedule"]["cells"]
    cells_by_id = {cell["cell_id"]: cell for cell in cells}
    starts: dict[tuple[str, int], dict[str, Any]] = {}
    receipts: set[tuple[str, int]] = set()
    completed: list[str] = []
    infrastructure_authorizations = 0
    operator_authorizations = 0
    interrupted: set[tuple[str, int]] = set()
    authorized_restarts: set[tuple[str, int]] = set()
    for event in events[3:]:
        kind = event["event_type"]
        payload = event["payload"]
        if kind == "attempt_started":
            cell_id = payload.get("cell_id")
            attempt = payload.get("trajectory_attempt")
            _require(cell_id in cells_by_id, "attempt references an unknown cell")
            _require(
                isinstance(attempt, int)
                and not isinstance(attempt, bool)
                and 1 <= attempt <= MAXIMUM_ATTEMPTS_PER_CELL,
                "attempt is outside the frozen maximum",
            )
            _require(len(completed) < len(cells), "attempt starts after schedule completion")
            _require(
                cell_id == cells[len(completed)]["cell_id"],
                "attempt starts out of frozen schedule order",
            )
            key = (cell_id, attempt)
            _require(key not in starts, "attempt is duplicated")
            _require(
                all(payload.get(field) == cells_by_id[cell_id][field] for field in cells_by_id[cell_id]),
                "attempt assignment differs from frozen schedule",
            )
            if attempt == 2:
                _require((cell_id, 1) in starts, "attempt 2 lacks immutable attempt 1")
                _require(key in authorized_restarts, "attempt 2 lacks a durable restart authorization")
            starts[key] = payload
        elif kind == "receipt_committed":
            key = (payload.get("cell_id"), payload.get("trajectory_attempt"))
            _require(key in starts, "receipt lacks a durable attempt start")
            _require(key not in receipts, "attempt receipt is duplicated")
            _require(
                all(
                    payload.get(field) == starts[key].get(field)
                    for field in cells_by_id[key[0]]
                ),
                "receipt assignment differs from its attempt start",
            )
            receipts.add(key)
            classification = classify_termination(payload.get("termination"))
            if classification["experimental_outcome"]:
                _require(key[0] not in completed, "completed cell is repeated")
                completed.append(key[0])
        elif kind == "operator_interruption_recorded":
            key = (payload.get("cell_id"), payload.get("trajectory_attempt"))
            _require(key in starts and key not in receipts, "operator interruption has no active attempt")
            _require(
                payload.get("category") == "operator_interruption",
                "operator interruption was relabeled",
            )
            interrupted.add(key)
        elif kind == "operator_restart_authorized":
            operator_authorizations += 1
            _require(
                operator_authorizations <= OPERATOR_INTERRUPTION_ALLOWANCE,
                "operator interruption allowance exceeded",
            )
            _require(
                (payload.get("cell_id"), payload.get("next_attempt", 0) - 1)
                in interrupted,
                "operator restart lacks interruption evidence",
            )
            authorized_restarts.add(
                (payload.get("cell_id"), payload.get("next_attempt"))
            )
        elif kind == "infrastructure_rerun_authorized":
            infrastructure_authorizations += 1
            _require(
                infrastructure_authorizations <= INFRASTRUCTURE_RETRY_ALLOWANCE,
                "infrastructure retry allowance exceeded",
            )
            prior = (payload.get("cell_id"), payload.get("next_attempt", 0) - 1)
            _require(prior in receipts, "infrastructure rerun lacks a receipt")
            prior_receipt = next(
                item["payload"]
                for item in reversed(events)
                if item["event_type"] == "receipt_committed"
                and (
                    item["payload"].get("cell_id"),
                    item["payload"].get("trajectory_attempt"),
                )
                == prior
            )
            _require(
                classify_termination(prior_receipt["termination"])[
                    "infrastructure_invalid"
                ],
                "valid experimental outcome obtained an infrastructure rerun",
            )
            authorized_restarts.add(
                (payload.get("cell_id"), payload.get("next_attempt"))
            )
