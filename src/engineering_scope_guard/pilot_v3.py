"""Prospective Pilot-v3 pool, contract, and durable scheduler.

This module contains no provider or evaluator invocation. Dataset loading and
Docker materialization live at the script boundary so the core remains testable
with deterministic fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError
from .pilot_contract import canonical_bytes, digest, read_object

CONTRACT_VERSION = "pilot-v3.0"
POOL_SEED = "engineering-scope-guard-pilot-v3-pool-2026-08-28"
SCHEDULE_SEED = "engineering-scope-guard-pilot-v3-order-2026-08-28"
RESERVE_COMMITMENT_DOMAIN = "engineering-scope-guard-confirmatory-reserve-post-pilot-v3"
ARMS = ("baseline", "short")
LANGUAGES = ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
REPETITIONS = 2
INFRASTRUCTURE_RERUN_ALLOWANCE = 4
OPERATOR_INTERRUPTION_ALLOWANCE = 2
MAXIMUM_ATTEMPTS_PER_CELL = 2

EXPERIMENTAL_OUTCOMES = {
    "accepted_completed",
    "evaluator_test_failure",
    "empty_patch_failure",
    "agent_subject_failure",
    "trajectory_timeout",
}
INFRASTRUCTURE_INVALID = {
    "provider_api_infrastructure_failure",
    "local_docker_runtime_infrastructure_failure",
    "official_evaluator_error",
    "official_evaluator_incomplete",
}
BATCH_STOP = {
    "harness_failure",
    "isolation_contract_violation",
    "malformed_inconsistent_measurement",
    "durable_evidence_incomplete",
}

SELECTION_FIELDS = {
    "instance_id",
    "repo",
    "created_at",
    "docker_image",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
    "rebuild_cmds",
    "test_cmds",
    "language",
}


def _rank(seed: str, revision: str, *parts: str) -> str:
    return hashlib.sha256("\0".join((seed, revision, *parts)).encode()).hexdigest()


def _created_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _nonempty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def eligible_rows(rows: list[dict[str, Any]], cutoff: str) -> list[dict[str, Any]]:
    """Apply the frozen v1 eligibility frame to a metadata-only projection."""

    boundary = _created_at(cutoff)
    if boundary is None:
        raise ExperimentConfigurationError("eligibility cutoff is malformed")
    eligible: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if set(row) != SELECTION_FIELDS:
            raise ExperimentConfigurationError("selection input contains non-metadata fields")
        instance_id = row.get("instance_id")
        created = _created_at(row.get("created_at"))
        if not isinstance(instance_id, str) or not instance_id or instance_id in seen:
            raise ExperimentConfigurationError("selection instance identities are invalid")
        seen.add(instance_id)
        if (
            created is not None
            and created > boundary
            and row.get("language") in LANGUAGES
            and isinstance(row.get("repo"), str)
            and bool(row["repo"])
            and isinstance(row.get("docker_image"), str)
            and bool(row["docker_image"])
            and all(
                _nonempty_strings(row.get(field))
                for field in ("FAIL_TO_PASS", "PASS_TO_PASS", "rebuild_cmds", "test_cmds")
            )
        ):
            eligible.append(row)
    return eligible


def historical_exposure(root: Path) -> dict[str, Any]:
    """Return task/repository exclusions from tracked historical evidence."""

    partition = read_object(root / "experiment/external_task_partition.json")
    host = read_object(root / "experiment/pilot_host_qualification.json")
    canary = read_object(root / "experiment/pilot_v2_canary_selection.json")
    pilot_tasks = partition["partition"]["pilot_tasks"]
    host_tasks = host["tasks"]
    canary_task = canary["task"]
    task_ids = {
        *(item["instance_id"] for item in pilot_tasks),
        *(item["instance_id"] for item in host_tasks),
        canary_task["instance_id"],
    }
    repositories = {
        *(item["repo"] for item in pilot_tasks),
        *(item["repo"] for item in host_tasks),
        canary_task["repo"],
    }
    return {
        "task_ids": task_ids,
        "repositories": repositories,
        "task_ids_sha256": digest(sorted(task_ids)),
        "repositories_sha256": digest(sorted(repositories)),
    }


def build_pool(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Select one repository-distinct task per language from the current reserve."""

    partition = read_object(root / "experiment/external_task_partition.json")
    host = read_object(root / "experiment/pilot_host_qualification.json")
    cutoff = partition["eligibility"]["subject_knowledge_cutoff_exclusive"]
    revision = partition["source"]["revision"]
    eligible = eligible_rows(rows, cutoff)
    if len(eligible) != partition["eligibility"]["eligible_distinct_tasks"]:
        raise ExperimentConfigurationError("eligible source frame no longer matches its commitment")

    original_tasks = partition["partition"]["pilot_tasks"]
    original_ids = {item["instance_id"] for item in original_tasks}
    original_repositories = {item["repo"] for item in original_tasks}
    replacement_repositories = set(
        host["summary"]["effective_confirmatory_reserve"][
            "replacement_repositories_now_excluded"
        ]
    )
    current_reserve = [
        row
        for row in eligible
        if row["instance_id"] not in original_ids
        and row["repo"] not in original_repositories
        and row["repo"] not in replacement_repositories
    ]
    expected_reserve = host["summary"]["effective_confirmatory_reserve"]
    if (
        len(current_reserve) != expected_reserve["effective_confirmatory_reserve_count"]
        or len({row["repo"] for row in current_reserve})
        != expected_reserve["effective_confirmatory_reserve_repositories"]
    ):
        raise ExperimentConfigurationError("pre-Pilot-v3 reserve does not reconstruct")

    exposure = historical_exposure(root)
    candidates = [
        row
        for row in current_reserve
        if row["instance_id"] not in exposure["task_ids"]
        and row["repo"] not in exposure["repositories"]
    ]
    selected: list[dict[str, Any]] = []
    used_repositories: set[str] = set()
    for language in LANGUAGES:
        ranked = sorted(
            (row for row in candidates if row["language"] == language),
            key=lambda row: (
                _rank(POOL_SEED, revision, row["instance_id"]),
                row["instance_id"],
            ),
        )
        task = next((row for row in ranked if row["repo"] not in used_repositories), None)
        if task is None:
            raise ExperimentConfigurationError(f"fresh supply cannot cover {language}")
        selected.append(task)
        used_repositories.add(task["repo"])

    remaining = [row for row in current_reserve if row["repo"] not in used_repositories]
    reserve_ids = [
        row["instance_id"]
        for row in sorted(
            remaining,
            key=lambda row: (
                _rank(RESERVE_COMMITMENT_DOMAIN, revision, row["instance_id"]),
                row["instance_id"],
            ),
        )
    ]
    slots = [
        {
            "slot": number,
            "actual_task_id": row["instance_id"],
            "repo": row["repo"],
            "language": row["language"],
            "created_at": row["created_at"],
            "docker_image": row["docker_image"],
            "fail_to_pass_count": len(row["FAIL_TO_PASS"]),
            "pass_to_pass_count": len(row["PASS_TO_PASS"]),
            "selection_rank_commitment": _rank(POOL_SEED, revision, row["instance_id"]),
            "task_snapshot_sha256": digest(
                {
                    "dataset_revision": revision,
                    "instance_id": row["instance_id"],
                    "docker_image": row["docker_image"],
                }
            ),
        }
        for number, row in enumerate(selected, start=1)
    ]
    pool: dict[str, Any] = {
        "schema_name": "engineering-scope-guard.pilot-v3-pool",
        "schema_version": 1,
        "selection": {
            "algorithm": "one task per language by SHA-256 rank; repository-distinct",
            "seed": POOL_SEED,
            "source_revision": revision,
            "selection_fields": sorted(SELECTION_FIELDS),
            "task_bodies_or_prior_outcomes_used": False,
            "historical_task_ids_sha256": exposure["task_ids_sha256"],
            "historical_repositories_sha256": exposure["repositories_sha256"],
            "selected_from_pre_v3_opaque_reserve": True,
            "post_freeze_replacement_allowance": 0,
        },
        "slots": slots,
        "confirmatory_reserve": {
            "pre_v3_count": len(current_reserve),
            "pre_v3_repositories": len({row["repo"] for row in current_reserve}),
            "pilot_v3_repositories_excluded": len(used_repositories),
            "tasks_removed_by_repository_exclusion": len(current_reserve) - len(remaining),
            "remaining_count": len(remaining),
            "remaining_repositories": len({row["repo"] for row in remaining}),
            "opaque_ids_commitment_sha256": digest(
                {
                    "domain": RESERVE_COMMITMENT_DOMAIN,
                    "source_revision": revision,
                    "ranked_ids": reserve_ids,
                }
            ),
            "ids_or_bodies_emitted": False,
            "pilot_and_reserve_repositories_disjoint": True,
        },
    }
    pool["pool_sha256"] = digest(slots)
    return pool


def generate_schedule(pool: dict[str, Any]) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    revision = pool["selection"]["source_revision"]
    for repetition in range(1, REPETITIONS + 1):
        tasks = sorted(
            pool["slots"],
            key=lambda slot: _rank(
                SCHEDULE_SEED,
                revision,
                pool["pool_sha256"],
                str(repetition),
                str(slot["slot"]),
            ),
        )
        for slot in tasks:
            arms = sorted(
                ARMS,
                key=lambda arm: _rank(
                    SCHEDULE_SEED,
                    revision,
                    pool["pool_sha256"],
                    str(repetition),
                    str(slot["slot"]),
                    arm,
                ),
            )
            for arm in arms:
                cells.append(
                    {
                        "position": len(cells) + 1,
                        "cell_id": f"v3-slot-{slot['slot']:02d}-{arm}-rep-{repetition}",
                        "requested_task_slot": slot["slot"],
                        "actual_task_id": slot["actual_task_id"],
                        "arm": arm,
                        "repetition": repetition,
                    }
                )
    schedule: dict[str, Any] = {
        "schema_name": "engineering-scope-guard.pilot-v3-schedule",
        "schema_version": 1,
        "algorithm": "SHA-256-ranked repetition blocks with per-task arm counterbalancing",
        "seed": SCHEDULE_SEED,
        "contract_version": CONTRACT_VERSION,
        "pool_sha256": pool["pool_sha256"],
        "arms": list(ARMS),
        "repetitions_per_task_arm": REPETITIONS,
        "manual_edits_permitted": False,
        "cells": cells,
    }
    schedule["schedule_sha256"] = digest(cells)
    return schedule


def build_contract(root: Path, pool: dict[str, Any], schedule: dict[str, Any]) -> dict[str, Any]:
    host = read_object(root / "experiment/pilot_host_qualification.json")
    runtime = read_object(root / "experiment/evaluator_runtime_readiness.json")
    prior = read_object(root / "experiment/pilot_readiness.json")
    boundary = read_object(root / "experiment/pilot_v2_measurement_boundary_qualification.json")
    short_hash = hashlib.sha256((root / "experiment/arms/short.txt").read_bytes()).hexdigest()
    value: dict[str, Any] = {
        "schema_name": "engineering-scope-guard.pilot-v3-execution-contract",
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "status": "frozen-qualified-live-execution-not-authorized",
        "live_execution_authorized": False,
        "historical_boundary": {
            "pilot_v1_and_v2_efficacy_evidence_reused": False,
            "pilot_v2_permanently_closed": True,
            "pilot_v2_observations_used_for_selection_or_sizing": 0,
            "measurement_boundary_decision": boundary["decision"],
        },
        "pool": pool,
        "schedule": schedule,
        "arms": {
            "ids": list(ARMS),
            "baseline_intervention": None,
            "short_policy_version": "C-short v0.1",
            "short_policy_sha256": short_hash,
            "other_arms_permitted": False,
            "treatment_change_requires_new_experiment_version": True,
        },
        "environment": {
            "codex_version": runtime["fixed_subject"]["codex_version"],
            "model": runtime["fixed_subject"]["model"],
            "reasoning_effort": runtime["fixed_subject"]["reasoning_effort"],
            "permissions": prior["subject_configuration"]["permissions"],
            "required_agent_tools": prior["subject_configuration"]["required_agent_tools"],
            "network_or_browser_tools": [],
            "mcp_servers": [],
            "plugins": [],
            "hooks": [],
            "user_config_loaded": False,
            "user_rules_loaded": False,
            "docker": host["fixed_environment"],
            "dataset": host["source"]["dataset"],
            "dataset_revision": host["source"]["dataset_revision"],
            "official_evaluator_revision": host["source"]["evaluator_revision"],
            "repolaunch_revision": host["source"]["repolaunch_revision"],
            "workers": 1,
            "material_change_from_qualified_v2": False,
            "new_live_canary_required_before_execution": False,
            "basis": "all frozen version/resource identities match the qualified Pilot-v2 infrastructure; selected image materialization is qualified separately",
        },
        "trajectory": {
            "maximum_turns": 2,
            "initial_round": 0,
            "maximum_corrective_rounds": 1,
            "timeout_seconds_per_turn": 900,
            "timeout_seconds_per_attempt": 1800,
            "failure_with_feedback_available": "provide only named failing checks and permit the single corrective round",
            "failure_with_feedback_unavailable": "retain evaluator_test_failure; provide no invented feedback; terminate without corrective round",
            "accepted_failure_timeout_or_empty_patch_rerun_permitted": False,
        },
        "official_evaluator": {
            "valid_terminal_dispositions": [
                "success", "failure", "error", "incomplete", "empty_patch"
            ],
            "disposition_and_feedback_are_separate": True,
            "feedback_statuses": ["available", "unavailable", "not_applicable"],
            "success": "accepted_completed experimental outcome",
            "failure": "evaluator_test_failure experimental outcome",
            "empty_patch": "empty_patch_failure experimental outcome",
            "error": "official_evaluator_error attempt-invalid infrastructure condition",
            "incomplete": "official_evaluator_incomplete attempt-invalid infrastructure condition",
            "contradictory_multiple_or_structurally_inconsistent": "malformed_inconsistent_measurement mandatory batch stop",
        },
        "attempt_accounting": {
            "maximum_attempts_per_cell": MAXIMUM_ATTEMPTS_PER_CELL,
            "infrastructure_rerun_allowance": INFRASTRUCTURE_RERUN_ALLOWANCE,
            "operator_interruption_allowance": OPERATOR_INTERRUPTION_ALLOWANCE,
            "allowances_are_separate": True,
            "all_categories_share_per_cell_maximum": True,
            "operator_allowance_justification": "two batch-level restarts provide bounded resilience to external operator interruption across 32 cells without changing experimental retry capacity",
            "exhaustion": "hash-chain batch_stopped and preserve; no further launch",
            "capacity_never_increased_after_outcome_review": True,
        },
        "operator_pause": {
            "planned": "between cells before the next attempt_started; consumes no allowance",
            "mid_attempt": "cause recorded contemporaneously before outcome review; immutable interrupted attempt; next attempt number and fresh isolation only",
            "operator_and_infrastructure_accounting_separate": True,
            "restart_decision_may_depend_on_interim_arm_effect": False,
        },
        "failure_taxonomy": {
            "experimental_outcomes": sorted(EXPERIMENTAL_OUTCOMES),
            "attempt_invalid_infrastructure": sorted(INFRASTRUCTURE_INVALID),
            "mandatory_batch_stop": sorted(BATCH_STOP),
            "post_outcome_reclassification_permitted": False,
        },
        "isolation": {
            "fresh_per_cell_and_attempt": [
                "repository/worktree", "Codex home", "conversation/session",
                "credential copy", "raw output root", "derived evidence root",
                "evaluator writable output root",
            ],
            "only_immutable_qualified_dependencies_reusable": [
                "pinned evaluator source checkout", "pinned dataset snapshot"
            ],
            "identities_recorded_and_verified": True,
            "inheritance_between_cells_or_attempts_permitted": False,
        },
        "durable_evidence": {
            "format": "fsync JSONL SHA-256 hash chain",
            "required_before_scheduler_transition": [
                "attempt_started", "subject termination", "evaluator invocation and exit",
                "official disposition", "feedback availability", "per-instance report identity",
                "timestamps", "usage components", "isolation identities",
                "termination metadata", "receipt and admissibility decision",
            ],
            "restart_source": "durable evidence only; no in-memory cursor",
            "completed_cells_never_repeated": True,
        },
        "usage": {
            "provider_reported_components": [
                "input_tokens", "cached_input_tokens", "output_tokens",
                "reasoning_output_tokens",
            ],
            "calculated_fresh_input": "input_tokens - cached_input_tokens",
            "provider_billed_amount_and_currency_required_for_billing_claim": True,
            "list_price_inference_permitted": False,
        },
        "analysis": {
            "exploratory_only": True,
            "unit": "paired task-level comparison",
            "repetitions_correlated_within_task": True,
            "uncertainty": "task-level resampling",
            "acceptance_reported_separately_from_cost_and_work": True,
            "null_and_adverse_results_retained": True,
            "intention_to_treat": "timeouts and experimental failures remain assigned to their frozen arm; infrastructure-invalid attempts follow only frozen rerun rules",
            "per_language_efficacy_claims_permitted": False,
            "equivalence_or_non_inferiority_claim_permitted": False,
            "broad_quality_or_maintainability_claim_permitted": False,
            "universal_mcid_or_margin_frozen": False,
        },
        "qualification": {
            "zero_provider_only": True,
            "pilot_v3_subject_calls": 0,
            "pilot_v3_evaluator_calls": 0,
            "pilot_v3_cells_executed": 0,
            "experimental_observations": 0,
            "execution_requires_separate_user_authorization": True,
        },
    }
    value["contract_sha256"] = digest(value)
    return value


def validate_contract(root: Path, contract: dict[str, Any], pool: dict[str, Any], schedule: dict[str, Any]) -> None:
    if canonical_bytes(contract) != canonical_bytes(build_contract(root, pool, schedule)):
        raise ExperimentConfigurationError("frozen Pilot-v3 contract mismatch")


def execution_confirmation(contract: dict[str, Any]) -> str:
    return f"execute-{CONTRACT_VERSION}:" + contract["contract_sha256"]


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
    return {
        **cell,
        "trajectory_attempt": attempt,
        "contract_sha256": contract["contract_sha256"],
        "pool_sha256": contract["pool"]["pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "isolation_roots": isolation_roots,
        "credential_copy_identity": str(Path(isolation_roots["codex_home"]) / "auth.json"),
        "session_identity": f"fresh-unassigned:{cell['cell_id']}:attempt-{attempt}",
        "intervention_sha256": (
            None if cell["arm"] == "baseline" else contract["arms"]["short_policy_sha256"]
        ),
        "subject": {
            "model": contract["environment"]["model"],
            "reasoning_effort": contract["environment"]["reasoning_effort"],
        },
        "source_and_evaluator": {
            "dataset": contract["environment"]["dataset"],
            "dataset_revision": contract["environment"]["dataset_revision"],
            "evaluator_revision": contract["environment"]["official_evaluator_revision"],
            "repolaunch_revision": contract["environment"]["repolaunch_revision"],
            "workers": contract["environment"]["workers"],
        },
        "platform": contract["environment"]["docker"],
        "environment": contract["environment"],
        "trajectory_contract": contract["trajectory"],
    }


def append_event(path: Path, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    events = read_events(path)
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
    previous = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError(f"malformed Pilot-v3 ledger line {number}") from error
        recorded = event.pop("event_sha256", None)
        if event.get("sequence") != number or event.get("previous_event_sha256") != previous:
            raise ExperimentConfigurationError("Pilot-v3 ledger chain mismatch")
        if recorded != digest(event):
            raise ExperimentConfigurationError("Pilot-v3 ledger digest mismatch")
        event["event_sha256"] = recorded
        events.append(event)
        previous = recorded
    return events


def evaluator_transition(disposition: str, feedback_status: str, round_number: int) -> dict[str, Any]:
    if disposition == "success":
        return {"action": "terminate", "termination": "accepted_completed"}
    if disposition == "empty_patch":
        return {"action": "terminate", "termination": "empty_patch_failure"}
    if disposition == "error":
        return {"action": "terminate", "termination": "official_evaluator_error"}
    if disposition == "incomplete":
        return {"action": "terminate", "termination": "official_evaluator_incomplete"}
    if disposition != "failure":
        return {"action": "stop_batch", "termination": "malformed_inconsistent_measurement"}
    if feedback_status == "available" and round_number == 0:
        return {"action": "correct", "allowed_feedback": "named failing checks only"}
    if feedback_status in {"available", "unavailable"}:
        return {"action": "terminate", "termination": "evaluator_test_failure"}
    return {"action": "stop_batch", "termination": "malformed_inconsistent_measurement"}


def planned_pause_allowed(events: list[dict[str, Any]]) -> bool:
    started = sum(event["event_type"] == "attempt_started" for event in events)
    finished = sum(event["event_type"] == "receipt_committed" for event in events)
    interrupted = sum(event["event_type"] == "operator_interruption_recorded" for event in events)
    return started == finished + interrupted


def usage_summary(rounds: list[dict[str, Any]]) -> dict[str, int]:
    fields = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    if any(
        any(not isinstance(item.get(field), int) or isinstance(item.get(field), bool) or item[field] < 0 for field in fields)
        for item in rounds
    ):
        raise ExperimentConfigurationError("provider usage components are incomplete")
    value = {field: sum(item[field] for item in rounds) for field in fields}
    if value["cached_input_tokens"] > value["input_tokens"]:
        raise ExperimentConfigurationError("cached input exceeds provider input")
    value["calculated_fresh_input_tokens"] = value["input_tokens"] - value["cached_input_tokens"]
    return value


def classify_termination(termination: str) -> dict[str, bool]:
    if termination not in EXPERIMENTAL_OUTCOMES | INFRASTRUCTURE_INVALID | BATCH_STOP:
        raise ExperimentConfigurationError("unknown Pilot-v3 termination")
    return {
        "experimental_outcome": termination in EXPERIMENTAL_OUTCOMES,
        "infrastructure_invalid": termination in INFRASTRUCTURE_INVALID,
        "batch_stop": termination in BATCH_STOP,
        "admissible": termination in EXPERIMENTAL_OUTCOMES,
    }


def _subject_checkpoint(result: Any, request: dict[str, Any], round_number: int) -> dict[str, Any]:
    termination = None
    if result.timed_out:
        termination = "trajectory_timeout"
    elif result.provider_infrastructure_failure:
        termination = "provider_api_infrastructure_failure"
    elif result.exit_code != 0 or not result.session_id:
        termination = "agent_subject_failure"
    return {
        "cell_id": request["cell_id"],
        "trajectory_attempt": request["trajectory_attempt"],
        "round": round_number,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "session_id": result.session_id,
        "usage": result.usage,
        "trace_reference": result.trace_reference,
        "provider_infrastructure_failure": result.provider_infrastructure_failure,
        "terminal_if_any": termination,
    }


def _evaluator_checkpoint(result: Any, request: dict[str, Any], round_number: int) -> dict[str, Any]:
    disposition = result.official_disposition
    feedback_status = result.feedback_status
    if result.timed_out:
        termination = "local_docker_runtime_infrastructure_failure"
    elif result.malformed or disposition is None or feedback_status is None:
        termination = "malformed_inconsistent_measurement"
    elif result.exit_code != 0 and disposition not in {"error", "incomplete"}:
        termination = "local_docker_runtime_infrastructure_failure"
    else:
        transition = evaluator_transition(disposition, feedback_status, round_number)
        termination = transition.get("termination")
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
        "terminal_if_any": termination,
    }


def _receipt_from_checkpoints(
    contract: dict[str, Any],
    request: dict[str, Any],
    subject_checkpoints: list[dict[str, Any]],
    evaluator_checkpoints: list[dict[str, Any]],
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    terminal = next(
        (
            item["terminal_if_any"]
            for item in reversed(evaluator_checkpoints + subject_checkpoints)
            if item.get("terminal_if_any")
        ),
        None,
    )
    if terminal is None:
        raise ExperimentConfigurationError("durable checkpoints lack a terminal classification")
    usage = usage_summary([item["usage"] for item in subject_checkpoints])
    classification = classify_termination(terminal)
    evaluator = evaluator_checkpoints[-1] if evaluator_checkpoints else None
    return {
        **request,
        "started_at": started_at,
        "ended_at": ended_at,
        "termination": terminal,
        "evaluator_result": evaluator,
        "usage": usage,
        "usage_complete": True,
        "admissible": classification["admissible"],
        "deviations": [],
    }


def execute_attempt_durably(
    contract: dict[str, Any],
    request: dict[str, Any],
    backend: Any,
    ledger_path: Path,
) -> dict[str, Any]:
    """Execute one future-authorized attempt with durable boundary checkpoints."""

    prepared = backend.prepare(request)
    subjects: list[dict[str, Any]] = []
    evaluators: list[dict[str, Any]] = []
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
        first = backend.run_subject(request, prepared, None, None)
        first_checkpoint = _subject_checkpoint(first, request, 0)
        subjects.append(first_checkpoint)
        append_event(ledger_path, "subject_terminated", first_checkpoint)
        if first_checkpoint["terminal_if_any"] is None:
            prediction = backend.create_prediction(request, prepared)
            append_event(
                ledger_path,
                "evaluator_invoked",
                {
                    "cell_id": request["cell_id"],
                    "trajectory_attempt": request["trajectory_attempt"],
                    "round": 0,
                    "prediction_sha256": prediction["patch_sha256"],
                    "official_evaluator_revision": contract["environment"][
                        "official_evaluator_revision"
                    ],
                },
            )
            first_evaluation = backend.evaluate(request, prepared, prediction, 0)
            first_evaluator = _evaluator_checkpoint(first_evaluation, request, 0)
            evaluators.append(first_evaluator)
            append_event(ledger_path, "evaluator_finished", first_evaluator)
            if (
                first_evaluator["official_disposition"] == "failure"
                and first_evaluator["feedback_status"] == "available"
                and first_evaluator["terminal_if_any"] is None
            ):
                correction = backend.run_subject(
                    request,
                    prepared,
                    tuple(first_evaluator["failing_checks"]),
                    first.session_id,
                )
                correction_checkpoint = _subject_checkpoint(correction, request, 1)
                if correction.session_id != first.session_id:
                    correction_checkpoint["terminal_if_any"] = "isolation_contract_violation"
                subjects.append(correction_checkpoint)
                append_event(ledger_path, "subject_terminated", correction_checkpoint)
                if correction_checkpoint["terminal_if_any"] is None:
                    prediction = backend.create_prediction(request, prepared)
                    append_event(
                        ledger_path,
                        "evaluator_invoked",
                        {
                            "cell_id": request["cell_id"],
                            "trajectory_attempt": request["trajectory_attempt"],
                            "round": 1,
                            "prediction_sha256": prediction["patch_sha256"],
                            "official_evaluator_revision": contract["environment"][
                                "official_evaluator_revision"
                            ],
                        },
                    )
                    final = backend.evaluate(request, prepared, prediction, 1)
                    final_checkpoint = _evaluator_checkpoint(final, request, 1)
                    evaluators.append(final_checkpoint)
                    append_event(ledger_path, "evaluator_finished", final_checkpoint)
    finally:
        backend.cleanup(prepared)
        credential_removed = not Path(request["credential_copy_identity"]).exists()
        append_event(
            ledger_path,
            "credential_cleanup_verified",
            {
                "cell_id": request["cell_id"],
                "trajectory_attempt": request["trajectory_attempt"],
                "credential_removed": credential_removed,
            },
        )
        if not credential_removed:
            raise ExperimentConfigurationError("trajectory credential cleanup failed")
    receipt = _receipt_from_checkpoints(
        contract,
        request,
        subjects,
        evaluators,
        prepared["started_at"],
        prepared["ended_at"]() if callable(prepared["ended_at"]) else prepared["ended_at"],
    )
    append_event(ledger_path, "receipt_committed", receipt)
    return receipt


def reconstruct_receipt_from_events(
    contract: dict[str, Any], request: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Reconstruct a terminal receipt exclusively from durable checkpoints."""

    relevant = [
        event
        for event in events
        if event["payload"].get("cell_id") == request["cell_id"]
        and event["payload"].get("trajectory_attempt") == request["trajectory_attempt"]
    ]
    subjects = [event["payload"] for event in relevant if event["event_type"] == "subject_terminated"]
    evaluators = [event["payload"] for event in relevant if event["event_type"] == "evaluator_finished"]
    cleanup = [event["payload"] for event in relevant if event["event_type"] == "credential_cleanup_verified"]
    if not cleanup or cleanup[-1].get("credential_removed") is not True:
        raise ExperimentConfigurationError("durable credential cleanup evidence is absent")
    started_at = request.get("attempt_started_at")
    if not isinstance(started_at, str):
        raise ExperimentConfigurationError("durable attempt start time is absent")
    ended_at = relevant[-1]["recorded_at"] if relevant else started_at
    return _receipt_from_checkpoints(
        contract, request, subjects, evaluators, started_at, ended_at
    )


def next_scheduler_action(contract: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the next action only from an already validated durable chain."""

    cells = contract["schedule"]["cells"]
    receipts = [event["payload"] for event in events if event["event_type"] == "receipt_committed"]
    completed = {receipt["cell_id"] for receipt in receipts if classify_termination(receipt["termination"])["experimental_outcome"]}
    if len(completed) != len(
        [
            receipt
            for receipt in receipts
            if classify_termination(receipt["termination"])["experimental_outcome"]
        ]
    ):
        raise ExperimentConfigurationError("completed cell is repeated")
    if any(event["event_type"] == "batch_stopped" for event in events):
        return {"action": "batch_stopped"}
    position = len(completed)
    if position == len(cells):
        return {"action": "complete"}
    cell = cells[position]
    cell_starts = [event["payload"] for event in events if event["event_type"] == "attempt_started" and event["payload"]["cell_id"] == cell["cell_id"]]
    cell_receipts = [receipt for receipt in receipts if receipt["cell_id"] == cell["cell_id"]]
    interruptions = [event for event in events if event["event_type"] == "operator_interruption_recorded"]
    operator_restarts = [event for event in events if event["event_type"] == "operator_restart_authorized"]
    infrastructure_restarts = [event for event in events if event["event_type"] == "infrastructure_rerun_authorized"]
    if not cell_starts:
        return {"action": "launch", "cell": cell, "trajectory_attempt": 1}
    latest = cell_starts[-1]
    attempt = latest["trajectory_attempt"]
    latest_receipt = next((item for item in reversed(cell_receipts) if item["trajectory_attempt"] == attempt), None)
    latest_interruption = next((event for event in reversed(interruptions) if event["payload"]["cell_id"] == cell["cell_id"] and event["payload"]["trajectory_attempt"] == attempt), None)
    if latest_receipt is None:
        if latest_interruption is None:
            checkpoints = [
                event
                for event in events
                if event["payload"].get("cell_id") == cell["cell_id"]
                and event["payload"].get("trajectory_attempt") == attempt
            ]
            checkpoint_types = {event["event_type"] for event in checkpoints}
            terminal_checkpoint = any(
                event["event_type"] in {"subject_terminated", "evaluator_finished"}
                and bool(event["payload"].get("terminal_if_any"))
                for event in checkpoints
            )
            if terminal_checkpoint and "credential_cleanup_verified" in checkpoint_types:
                return {"action": "reconstruct_receipt", "request": latest}
            if terminal_checkpoint:
                return {"action": "cleanup_then_reconstruct", "request": latest}
            return {"action": "record_batch_stop", "termination": "durable_evidence_incomplete"}
        authorized = next(
            (
                event
                for event in reversed(operator_restarts)
                if event["payload"].get("cell_id") == cell["cell_id"]
                and event["payload"].get("next_attempt") == attempt + 1
            ),
            None,
        )
        if authorized is not None:
            return {"action": "launch", "cell": cell, "trajectory_attempt": attempt + 1}
        if attempt >= MAXIMUM_ATTEMPTS_PER_CELL or len(operator_restarts) >= OPERATOR_INTERRUPTION_ALLOWANCE:
            return {"action": "record_batch_stop", "termination": "operator_interruption_allowance_exhausted"}
        return {"action": "authorize_operator_restart", "cell_id": cell["cell_id"], "next_attempt": attempt + 1}
    classification = classify_termination(latest_receipt["termination"])
    if classification["batch_stop"]:
        return {"action": "record_batch_stop", "termination": latest_receipt["termination"]}
    if classification["infrastructure_invalid"]:
        authorized = next(
            (
                event
                for event in reversed(infrastructure_restarts)
                if event["payload"].get("cell_id") == cell["cell_id"]
                and event["payload"].get("next_attempt") == attempt + 1
            ),
            None,
        )
        if authorized is not None:
            return {"action": "launch", "cell": cell, "trajectory_attempt": attempt + 1}
        if attempt >= MAXIMUM_ATTEMPTS_PER_CELL or len(infrastructure_restarts) >= INFRASTRUCTURE_RERUN_ALLOWANCE:
            return {"action": "record_batch_stop", "termination": "infrastructure_rerun_allowance_exhausted"}
        return {"action": "authorize_infrastructure_rerun", "cell_id": cell["cell_id"], "next_attempt": attempt + 1}
    raise ExperimentConfigurationError("scheduler could not advance from durable state")
