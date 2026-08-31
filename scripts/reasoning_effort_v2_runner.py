#!/usr/bin/env python3
"""Provider-free durable runner state for reasoning-effort v2.

This module never invokes a provider or evaluator.  It owns the separate live
seal, canonical ledger, crash reconciliation, Stage-1 transition, and the
public-safe terminal bridge consumed by analysis.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterator
from contextlib import contextmanager

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.evaluator_stable_qualification import (
    sha256_file as qualification_sha256_file,
    sha256_value as qualification_sha256_value,
    validate_receipt as validate_qualifier_receipt,
)
from engineering_scope_guard.pilot_contract import canonical_bytes, digest
from engineering_scope_guard.reasoning_effort_v2 import (
    ALTERNATE_ACTIVATION_CLASSES,
    EXPERIMENTAL_OUTCOMES,
    MANDATORY_BATCH_STOP,
    RETRYABLE_INFRASTRUCTURE,
    STAGE_1_AUDIT_CRITERIA,
    public_pool_projection,
    replay_attempt_state,
    validate_analysis_terminal_envelope,
    validate_contract,
    validate_harness_source_closure,
    validate_prior_evidence_identity,
    validate_private_pool,
    validate_private_pool_binding,
)

LEDGER_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-ledger"
CHECKPOINT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-checkpoint"
QUALIFICATION_GATE_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-qualification-gate"
POOL_RELIABILITY_AUDIT_SCHEMA = (
    "engineering-scope-guard.reasoning-effort-v2-pool-reliability-audit"
)
POOL_RELIABILITY_INVESTIGATION_SCHEMA = (
    "engineering-scope-guard.reasoning-effort-v2-pool-reliability-investigation"
)
LIVE_SEAL_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-live-seal"
TERMINAL_RECEIPT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-terminal-receipt"
EXECUTION_ARTIFACT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-execution-artifact"
EVALUATOR_ARTIFACT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-evaluator-artifact"
MEASUREMENT_ARTIFACT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-measurement-artifact"
OWNERSHIP_RECEIPT_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-ownership-receipt"
RUNTIME_REVALIDATION_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-runtime-revalidation"
SOURCE_REVALIDATION_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-source-revalidation"
ANALYSIS_ENVELOPE_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-analysis-envelope"
CANARY_LEDGER_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-canary-ledger"
SCHEMA_VERSION = 1

INTEGER_WORK_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "turns",
    "tool_actions",
    "search_actions",
    "correction_turns",
)
FLOAT_WORK_FIELDS = ("wall_seconds",)
ANALYSIS_RECORD_KEYS = {
    "cell_id",
    "termination",
    "timed_out",
    "evaluator_anomalies",
    *INTEGER_WORK_FIELDS,
    *FLOAT_WORK_FIELDS,
}
EXECUTION_ARTIFACT_KEYS = {
    "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
    "cell_id", "attempt", "effective_task_commitment_sha256",
    "subject_invocation_started", "command_sha256", "status", "timed_out",
    "subject_exit_code", "ownership_token_sha256", "process_identity_sha256",
    "container_identity_sha256", "subject_stdout_sha256", "subject_stderr_sha256",
    "prediction_sha256", "patch_sha256", "cleanup_receipt_sha256", "receipt_sha256",
}
ENVELOPE_RECORD_KEYS = {
    *ANALYSIS_RECORD_KEYS,
    "attempt",
    "effective_task_commitment_sha256",
    "terminal_receipt_sha256",
    "evaluator_receipt_sha256",
}
QUALIFICATION_CHECKS = {
    "outcome_blind_pool_ready",
    "provider_free_preflight_passed",
    "runtime_identity_verified",
    "source_identity_verified",
    "evaluator_and_image_bindings_verified",
}
_PUBLIC_CODE = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")
_ATTEMPT_START_CAPABILITY = object()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _exact(value: Any, keys: set[str], message: str) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == keys, message)
    return value


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finding_terminal_evidence(
    receipt: dict[str, Any], finding: dict[str, Any]
) -> list[dict[str, Any]]:
    candidates = {candidate["slot"]: candidate for candidate in receipt["candidates"]}
    evidence = []
    for slot in finding["candidate_slots"]:
        terminal = candidates[slot]["stages"][-1]
        evidence.append(
            {
                "candidate_slot": slot,
                "stage": terminal["stage"],
                "classification": candidates[slot]["classification"],
                "stage_receipt_sha256": terminal["evidence"]["stage_receipt_sha256"],
                "artifact_set_sha256": terminal["evidence"]["artifact_set_sha256"],
            }
        )
    return evidence


def build_pool_reliability_investigation(
    receipt: dict[str, Any], resolutions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Seal explicit private resolutions for every clustered Phase-7 finding."""

    audit = build_pool_reliability_audit(receipt)
    findings = audit["investigation"]["findings"]
    _require(findings, "no clustered reliability findings require investigation")
    resolution_by_finding: dict[str, dict[str, Any]] = {}
    for resolution in resolutions:
        _exact(
            resolution,
            {"finding_sha256", "disposition", "deterministic_cause", "action"},
            "reliability investigation resolution fields drifted",
        )
        finding_sha256 = resolution["finding_sha256"]
        _require(
            _sha256(finding_sha256)
            and finding_sha256 not in resolution_by_finding
            and resolution["disposition"] == "deterministic_cause_identified"
            and isinstance(resolution["deterministic_cause"], str)
            and bool(resolution["deterministic_cause"].strip())
            and isinstance(resolution["action"], str)
            and bool(resolution["action"].strip()),
            "reliability investigation resolution is inconclusive or malformed",
        )
        resolution_by_finding[finding_sha256] = resolution
    records = []
    for finding in findings:
        finding_sha256 = digest(finding)
        resolution = resolution_by_finding.pop(finding_sha256, None)
        _require(resolution is not None, "reliability investigation does not address every finding")
        records.append(
            {
                "finding_sha256": finding_sha256,
                "dimension": finding["dimension"],
                "classification": finding["classification"],
                "private_key_sha256": finding["private_key_sha256"],
                "candidate_slots": finding["candidate_slots"],
                "evidence_set_sha256": finding["evidence_set_sha256"],
                "terminal_stage_evidence": _finding_terminal_evidence(receipt, finding),
                "disposition": resolution["disposition"],
                "deterministic_cause": resolution["deterministic_cause"].strip(),
                "action": resolution["action"].strip(),
            }
        )
    _require(not resolution_by_finding, "reliability investigation contains an unknown finding")
    body = {
        "schema_name": POOL_RELIABILITY_INVESTIGATION_SCHEMA,
        "schema_version": 1,
        "qualification_receipt_sha256": receipt["state_sha256"],
        "finding_set_sha256": digest(findings),
        "records": records,
        "upstream_tests_modified": False,
        "task_bodies_or_subject_outcomes_inspected": False,
        "infrastructure_findings_are_experiment_results": False,
    }
    return {**body, "investigation_sha256": digest(body)}


def build_pool_reliability_audit(
    receipt: dict[str, Any], investigation: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Derive a private, outcome-free Phase-7 infrastructure reliability audit."""

    validate_qualifier_receipt(receipt)
    _require(
        receipt["status"] == "stable_pool_ready",
        "qualification is not stable_pool_ready for reliability audit",
    )
    candidates = receipt["candidates"]
    failures = [candidate for candidate in candidates if candidate["status"] == "not_qualified"]
    for candidate in failures:
        stages = candidate.get("stages")
        _require(
            isinstance(stages, list) and stages
            and isinstance(stages[-1], dict)
            and isinstance(stages[-1].get("stage"), str)
            and isinstance(stages[-1].get("evidence"), dict)
            and _sha256(stages[-1]["evidence"].get("stage_receipt_sha256"))
            and _sha256(stages[-1]["evidence"].get("artifact_set_sha256")),
            "failed qualification candidate lacks deterministic investigation evidence",
        )
    selection = receipt["selection"]
    failure_classes = (
        "build_environment_failure", "flaky_validation",
        "gold_patch_evaluation_failure", "evaluator_runtime_failure",
        "infrastructure_timeout",
    )
    aggregates = {
        "total_candidates": len(candidates),
        "attempted_candidates": sum(candidate["status"] != "pending" for candidate in candidates),
        "pending_candidates": sum(candidate["status"] == "pending" for candidate in candidates),
        "in_progress_candidates": sum(candidate["status"] == "in_progress" for candidate in candidates),
        "not_qualified_candidates": len(failures),
        "qualified_candidates": sum(candidate["status"] == "qualified" for candidate in candidates),
        "primary_candidates": len(selection["primary"]),
        "alternate_candidates": len(selection["alternates"]),
        "failure_counts": {
            classification: sum(candidate["classification"] == classification for candidate in failures)
            for classification in failure_classes
        },
    }
    platform_key = digest(receipt["runtime_observation"].get("docker_client_server"))
    dimensions: dict[str, list[dict[str, Any]]] = {}
    dimension_value = {
        "language": lambda candidate: candidate["language"],
        "platform": lambda _candidate: platform_key,
        "repository": lambda candidate: candidate["repo"],
        "image": lambda candidate: candidate.get("resolved_image") or candidate["docker_image"],
        "evaluator_path": lambda candidate: candidate["stages"][-1]["stage"],
    }
    for dimension, value_for in dimension_value.items():
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for candidate in failures:
            key = str(value_for(candidate))
            grouped.setdefault((candidate["classification"], key), []).append(candidate)
        dimensions[dimension] = [
            {
                "classification": classification,
                "private_key": key,
                "private_key_sha256": digest({"dimension": dimension, "value": key}),
                "candidate_slots": [candidate["slot"] for candidate in members],
                "count": len(members),
                "evidence_set_sha256": digest([
                    {
                        "slot": candidate["slot"],
                        "stage": candidate["stages"][-1]["stage"],
                        "stage_receipt_sha256": candidate["stages"][-1]["evidence"]["stage_receipt_sha256"],
                        "artifact_set_sha256": candidate["stages"][-1]["evidence"]["artifact_set_sha256"],
                    }
                    for candidate in members
                ]),
            }
            for (classification, key), members in sorted(grouped.items())
        ]
    findings = [
        {
            "dimension": dimension,
            "classification": group["classification"],
            "private_key_sha256": group["private_key_sha256"],
            "candidate_slots": group["candidate_slots"],
            "count": group["count"],
            "evidence_set_sha256": group["evidence_set_sha256"],
            "finding": "shared_infrastructure_dependency",
        }
        for dimension in sorted(dimensions)
        for group in dimensions[dimension]
        if group["count"] > 1
    ]
    investigation_projection: dict[str, Any]
    if not findings:
        _require(investigation is None, "reliability investigation is forbidden without findings")
        investigation_projection = {
            "status": "not_required",
            "findings": [],
            "finding_set_sha256": digest([]),
            "artifact": None,
            "artifact_sha256": None,
            "cluster_presence_blocks_freeze": False,
        }
    elif investigation is None:
        investigation_projection = {
            "status": "required",
            "findings": findings,
            "finding_set_sha256": digest(findings),
            "artifact": None,
            "artifact_sha256": None,
            "cluster_presence_blocks_freeze": True,
        }
    else:
        _exact(
            investigation,
            {
                "schema_name", "schema_version", "qualification_receipt_sha256",
                "finding_set_sha256", "records", "upstream_tests_modified",
                "task_bodies_or_subject_outcomes_inspected",
                "infrastructure_findings_are_experiment_results",
                "investigation_sha256",
            },
            "reliability investigation fields drifted",
        )
        _require(
            investigation["schema_name"] == POOL_RELIABILITY_INVESTIGATION_SCHEMA
            and investigation["schema_version"] == 1
            and investigation["qualification_receipt_sha256"] == receipt["state_sha256"]
            and investigation["finding_set_sha256"] == digest(findings)
            and investigation["upstream_tests_modified"] is False
            and investigation["task_bodies_or_subject_outcomes_inspected"] is False
            and investigation["infrastructure_findings_are_experiment_results"] is False
            and investigation["investigation_sha256"]
            == digest({key: value for key, value in investigation.items()
                       if key != "investigation_sha256"}),
            "reliability investigation identity or safety assertions drifted",
        )
        expected_records = []
        for finding in findings:
            record = next(
                (
                    item for item in investigation["records"]
                    if isinstance(item, dict) and item.get("finding_sha256") == digest(finding)
                ),
                None,
            )
            _require(record is not None, "reliability investigation does not address every finding")
            _exact(
                record,
                {
                    "finding_sha256", "dimension", "classification", "private_key_sha256",
                    "candidate_slots", "evidence_set_sha256", "terminal_stage_evidence",
                    "disposition", "deterministic_cause", "action",
                },
                "reliability investigation record fields drifted",
            )
            _require(
                record["dimension"] == finding["dimension"]
                and record["classification"] == finding["classification"]
                and record["private_key_sha256"] == finding["private_key_sha256"]
                and record["candidate_slots"] == finding["candidate_slots"]
                and record["evidence_set_sha256"] == finding["evidence_set_sha256"]
                and record["terminal_stage_evidence"]
                == _finding_terminal_evidence(receipt, finding)
                and record["disposition"] == "deterministic_cause_identified"
                and isinstance(record["deterministic_cause"], str)
                and bool(record["deterministic_cause"].strip())
                and isinstance(record["action"], str)
                and bool(record["action"].strip()),
                "reliability investigation record is inconclusive or evidence-unbound",
            )
            expected_records.append(record)
        _require(
            investigation["records"] == expected_records,
            "reliability investigation is not one-to-one and deterministically ordered",
        )
        investigation_projection = {
            "status": "complete",
            "findings": findings,
            "finding_set_sha256": digest(findings),
            "artifact": deepcopy(investigation),
            "artifact_sha256": investigation["investigation_sha256"],
            "cluster_presence_blocks_freeze": False,
        }
    body = {
        "schema_name": POOL_RELIABILITY_AUDIT_SCHEMA,
        "schema_version": 1,
        "status": "pass" if investigation_projection["status"] != "required" else "blocked",
        "qualification_receipt_sha256": receipt["state_sha256"],
        "qualification_population_sha256": selection["population_sha256"],
        "aggregate_counts": aggregates,
        "failure_clusters": dimensions,
        "investigation": investigation_projection,
        "evidence_complete": True,
        "evidence_consistent": True,
        "infrastructure_findings_are_experiment_results": False,
        "task_bodies_or_subject_outcomes_inspected": False,
        "private_identities_withheld_from_contract": True,
    }
    return {**body, "pool_reliability_audit_sha256": digest(body)}


def validate_pool_reliability_audit(receipt: dict[str, Any], audit: Any) -> None:
    investigation = None
    if isinstance(audit, dict) and isinstance(audit.get("investigation"), dict):
        investigation = audit["investigation"].get("artifact")
    expected = build_pool_reliability_audit(receipt, investigation)
    _require(
        isinstance(audit, dict)
        and canonical_bytes(audit) == canonical_bytes(expected),
        "private pool reliability audit is missing or inconsistent",
    )


def _self_hash(value: dict[str, Any], field: str) -> bool:
    return _sha256(value.get(field)) and value[field] == digest(
        {key: item for key, item in value.items() if key != field}
    )


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    data = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _execution_storage_root(path: Path) -> Path:
    """Resolve an initialized private execution root containing ``path``."""

    candidate = Path(path).absolute()
    for ancestor in (candidate if candidate.is_dir() else candidate.parent, *candidate.parents):
        marker = ancestor / "receipt-state.json"
        lock = ancestor / "runner.lock"
        ledger = ancestor / "ledger.jsonl"
        checkpoint = ancestor / "checkpoint.json"
        if all(item.exists() for item in (marker, lock, ledger, checkpoint)):
            _require(".local" in ancestor.parts, "execution storage must be below .local")
            _require(candidate.resolve().is_relative_to(ancestor.resolve()), "path escapes execution storage")
            _require(not ancestor.is_symlink(), "execution storage root cannot be a symlink")
            _require(
                (ancestor.stat().st_mode & 0o777) == 0o700,
                "execution storage root must have private mode 0700",
            )
            for file_path in (marker, lock, ledger, checkpoint):
                _require(
                    not file_path.is_symlink() and (file_path.stat().st_mode & 0o777) == 0o600,
                    "execution storage authority files must have private mode 0600",
                )
            try:
                marker_raw = marker.read_bytes()
                marker_value = json.loads(marker_raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ExperimentConfigurationError("execution storage authority marker is malformed") from error
            _exact(
                marker_value,
                {
                    "schema_name", "schema_version", "status", "root_identity_sha256",
                    "receipt_sha256",
                },
                "execution storage authority marker fields drifted",
            )
            _require(
                marker_raw == _canonical_artifact_bytes(marker_value)
                and marker_value["schema_name"]
                == "engineering-scope-guard.reasoning-effort-v2-storage-authority"
                and marker_value["schema_version"] == SCHEMA_VERSION
                and marker_value["status"] == "initialized"
                and marker_value["root_identity_sha256"]
                == digest({"resolved_execution_root": str(ancestor.resolve())})
                and _self_hash(marker_value, "receipt_sha256"),
                "execution storage authority marker is not canonical or bound to its root",
            )
            return ancestor
    raise ExperimentConfigurationError("initialized .local execution storage authority marker is missing")


def _require_mutation_paths(ledger_path: Path, checkpoint_path: Path) -> Path:
    root = _execution_storage_root(ledger_path)
    _require(
        ledger_path.resolve() == (root / "ledger.jsonl").resolve()
        and checkpoint_path.resolve() == (root / "checkpoint.json").resolve(),
        "ledger/checkpoint paths differ from initialized execution storage",
    )
    return root


def _require_private_artifact_path(path: Path) -> Path:
    root = _execution_storage_root(path)
    relative = path.absolute().relative_to(root.absolute())
    cursor = root
    for part in relative.parts[:-1]:
        cursor = cursor / part
        _require(
            cursor.is_dir() and not cursor.is_symlink()
            and (cursor.stat().st_mode & 0o777) == 0o700,
            "artifact directories must be non-symlink private mode 0700",
        )
    _require(
        path.is_file() and not path.is_symlink()
        and (path.stat().st_mode & 0o777) == 0o600,
        "artifact receipt must be non-symlink private mode 0600",
    )
    return root


def _require_private_local_file(path: Path, label: str) -> None:
    absolute = path.absolute()
    local_root = next((item for item in absolute.parents if item.name == ".local"), None)
    _require(local_root is not None, f"{label} must be below .local")
    _require(
        local_root.is_dir() and not local_root.is_symlink()
        and (local_root.stat().st_mode & 0o777) == 0o700,
        f"{label} .local root must have private mode 0700",
    )
    cursor = local_root
    for part in absolute.parent.relative_to(local_root).parts:
        cursor = cursor / part
        _require(
            cursor.is_dir() and not cursor.is_symlink()
            and (cursor.stat().st_mode & 0o777) == 0o700,
            f"{label} directories must have private mode 0700",
        )
    _require(
        path.is_file() and not path.is_symlink() and (path.stat().st_mode & 0o777) == 0o600,
        f"{label} must have private mode 0600",
    )


def seal_qualification_gate(body: dict[str, Any]) -> dict[str, Any]:
    """Reject the retired caller-asserted gate construction boundary."""

    raise ExperimentConfigurationError(
        "qualification authority requires a terminal receipt and stage artifacts"
    )


def _canonical_json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"{label} is unreadable or malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def _require_no_symlink_descent(root: Path, relative: Path, label: str) -> Path:
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        f"{label} path escapes its root",
    )
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        _require(not cursor.is_symlink(), f"{label} path traverses a symlink")
    resolved_root = root.resolve()
    resolved = cursor.resolve()
    _require(resolved.is_relative_to(resolved_root), f"{label} path escapes its root")
    return resolved


def build_qualification_gate_from_receipt(
    contract: dict[str, Any],
    private_pool: dict[str, Any],
    qualification_receipt_path: Path,
    qualification_raw_root: Path,
    *,
    pool_reliability_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive live eligibility from the actual terminal qualifier evidence."""

    validate_private_pool_binding(private_pool, contract)
    _require_private_local_file(qualification_receipt_path, "qualification receipt")
    receipt, _raw = _canonical_json_file(qualification_receipt_path, "qualification receipt")
    validate_qualifier_receipt(receipt)
    _require(receipt["status"] == "stable_pool_ready", "qualification receipt is not terminal-ready")
    _require(
        receipt["state_sha256"] == contract["source"]["qualification_receipt_sha256"],
        "qualification receipt identity differs from the frozen contract",
    )
    selection = receipt["selection"]
    _require(isinstance(selection, dict), "qualification terminal selection is absent")
    selected = [*selection["primary"], *selection["alternates"]]
    pool_tasks = [*private_pool["primaries"], *private_pool["alternates"]]
    _require(len(selected) == len(pool_tasks), "qualification selection count differs from private pool")
    candidates = {candidate["slot"]: candidate for candidate in receipt["candidates"]}
    for task, selected_task in zip(pool_tasks, selected, strict=True):
        candidate = candidates[selected_task["slot"]]
        _require(
            task["task_id"] == selected_task["instance_id"]
            and task["repository"] == selected_task["repo"]
            and task["task_snapshot_sha256"] == candidate["manifest_sha256"]
            and task.get("resolved_image") == selected_task["resolved_image"],
            "qualification selection identity or order differs from private pool",
        )
    artifact_root = qualification_raw_root.resolve()
    _require(
        qualification_raw_root.exists()
        and qualification_raw_root.is_dir()
        and not qualification_raw_root.is_symlink(),
        "qualification artifact root is invalid",
    )
    stage_bindings = []
    for selected_task in selected:
        candidate = candidates[selected_task["slot"]]
        _require(candidate["status"] == "qualified", "selected qualification candidate is not qualified")
        _require(len(candidate["stages"]) == 4, "selected candidate lacks Q1-Q4 evidence")
        for stage in candidate["stages"]:
            evidence = stage["evidence"]
            relative_path = Path(f"slot-{candidate['slot']:02d}") / stage["stage"] / "stage-receipt.json"
            unresolved_path = artifact_root / relative_path
            path = _require_no_symlink_descent(
                artifact_root, relative_path, "qualification stage receipt"
            )
            _require(
                path.is_relative_to(artifact_root)
                and path.is_file()
                and not unresolved_path.is_symlink()
                and not path.is_symlink()
                ,
                "qualification stage receipt is missing or escapes its artifact root",
            )
            _require_private_local_file(path, "qualification stage receipt")
            stage_receipt, _stage_raw = _canonical_json_file(path, "qualification stage receipt")
            unsealed = {key: value for key, value in stage_receipt.items() if key != "stage_receipt_sha256"}
            _require(
                stage_receipt.get("slot") == candidate["slot"]
                and stage_receipt.get("stage") == stage["stage"]
                and stage_receipt.get("stage_receipt_sha256") == qualification_sha256_value(unsealed)
                and stage_receipt["stage_receipt_sha256"] == evidence["stage_receipt_sha256"]
                and isinstance(stage_receipt.get("artifact_sha256"), dict)
                and qualification_sha256_value(stage_receipt["artifact_sha256"])
                == evidence["artifact_set_sha256"],
                "qualification stage receipt self-seal or terminal evidence drifted",
            )
            stage_root = path.parent
            actual_artifacts: dict[str, str] = {}
            for artifact_candidate in sorted(stage_root.rglob("*")):
                if not artifact_candidate.is_file() or artifact_candidate.name == "stage-receipt.json":
                    continue
                relative_artifact_path = artifact_candidate.relative_to(stage_root)
                artifact = _require_no_symlink_descent(
                    stage_root, relative_artifact_path, "qualification stage artifact"
                )
                _require_private_local_file(artifact, "qualification stage artifact")
                actual_artifacts[relative_artifact_path.as_posix()] = qualification_sha256_file(artifact)
            _require(
                actual_artifacts == stage_receipt["artifact_sha256"],
                "qualification stage artifact hash drifted",
            )
            stage_bindings.append(
                {
                    "candidate_slot": candidate["slot"],
                    "stage": stage["stage"],
                    "stage_receipt_sha256": evidence["stage_receipt_sha256"],
                    "artifact_set_sha256": evidence["artifact_set_sha256"],
                }
            )
    checks = {key: True for key in QUALIFICATION_CHECKS}
    derived_runtime_identity = digest(receipt["runtime_observation"])
    derived_evaluator_identity = digest(
        {
            key: receipt["source"][key]
            for key in (
                "evaluator_revision", "evaluator_tree_sha256", "evaluator_python",
                "embedded_repolaunch_revision", "repolaunch_tree_sha256",
            )
        }
    )
    derived_source_identity = digest(receipt["source"])
    derived_image_pool_identity = digest(
        [
            {
                "slot": item["slot"],
                "resolved_image": candidates[item["slot"]]["resolved_image"],
            }
            for item in selected
        ]
    )
    _require(
        derived_runtime_identity == contract["runtime"]["runtime_identity"]
        and derived_evaluator_identity == contract["source"]["evaluator_identity"]
        and derived_source_identity == contract["source"]["source_identity"]
        and derived_image_pool_identity == contract["source"]["image_pool_identity"],
        "frozen contract identities differ from the terminal qualifier evidence",
    )
    reliability_audit = (
        build_pool_reliability_audit(receipt)
        if pool_reliability_audit is None
        else pool_reliability_audit
    )
    validate_pool_reliability_audit(receipt, reliability_audit)
    _require(
        reliability_audit["status"] == "pass"
        and reliability_audit["investigation"]["cluster_presence_blocks_freeze"] is False,
        "Phase-7 reliability findings require a complete private investigation",
    )
    body = {
        "schema_name": QUALIFICATION_GATE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "private_pool_sha256": private_pool["private_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "qualification_receipt_sha256": receipt["state_sha256"],
        "qualification_population_sha256": selection["population_sha256"],
        "qualification_stage_receipt_set_sha256": digest(stage_bindings),
        "qualification_stage_receipt_count": len(stage_bindings),
        "qualification_stage_bindings": stage_bindings,
        "qualification_receipt": deepcopy(receipt),
        "pool_reliability_audit": reliability_audit,
        "pool_reliability_audit_sha256": reliability_audit[
            "pool_reliability_audit_sha256"
        ],
        "evaluator_identity": derived_evaluator_identity,
        "image_pool_identity": derived_image_pool_identity,
        "runtime_identity": derived_runtime_identity,
        "source_identity": derived_source_identity,
        "subject_invocation_starts": receipt["subject_accounting"][
            "subject_invocation_starts"
        ],
        "checks": checks,
    }
    return {**body, "qualification_gate_sha256": digest(body)}


def validate_qualification_gate(
    contract: dict[str, Any], private_pool: dict[str, Any], gate: dict[str, Any]
) -> None:
    validate_private_pool_binding(private_pool, contract)
    _exact(
        gate,
        {
            "schema_name", "schema_version", "status", "contract_sha256",
            "private_pool_sha256", "schedule_sha256", "qualification_receipt_sha256",
            "qualification_population_sha256", "qualification_stage_receipt_set_sha256",
            "qualification_stage_receipt_count", "qualification_stage_bindings",
            "qualification_receipt",
            "pool_reliability_audit", "pool_reliability_audit_sha256",
            "evaluator_identity", "image_pool_identity", "runtime_identity",
            "source_identity", "subject_invocation_starts", "checks",
            "qualification_gate_sha256",
        },
        "qualification gate fields drifted",
    )
    checks = _exact(gate["checks"], QUALIFICATION_CHECKS, "qualification checks drifted")
    source = contract["source"]
    receipt = gate["qualification_receipt"]
    validate_qualifier_receipt(receipt)
    validate_pool_reliability_audit(receipt, gate["pool_reliability_audit"])
    selection = receipt.get("selection")
    _require(isinstance(selection, dict), "qualification gate lacks terminal selection")
    selected = [*selection["primary"], *selection["alternates"]]
    pool_tasks = [*private_pool["primaries"], *private_pool["alternates"]]
    candidates = {candidate["slot"]: candidate for candidate in receipt["candidates"]}
    _require(len(selected) == len(pool_tasks), "qualification gate selection count drifted")
    for task, selected_task in zip(pool_tasks, selected, strict=True):
        candidate = candidates[selected_task["slot"]]
        _require(
            task["task_id"] == selected_task["instance_id"]
            and task["repository"] == selected_task["repo"]
            and task["task_snapshot_sha256"] == candidate["manifest_sha256"]
            and task.get("resolved_image") == selected_task["resolved_image"],
            "qualification gate selection differs from private pool",
        )
    derived_bindings = [
        {
            "candidate_slot": selected_task["slot"],
            "stage": stage["stage"],
            "stage_receipt_sha256": stage["evidence"]["stage_receipt_sha256"],
            "artifact_set_sha256": stage["evidence"]["artifact_set_sha256"],
        }
        for selected_task in selected
        for stage in candidates[selected_task["slot"]]["stages"]
    ]
    derived_runtime_identity = digest(receipt["runtime_observation"])
    derived_evaluator_identity = digest({
        key: receipt["source"][key]
        for key in (
            "evaluator_revision", "evaluator_tree_sha256", "evaluator_python",
            "embedded_repolaunch_revision", "repolaunch_tree_sha256",
        )
    })
    derived_source_identity = digest(receipt["source"])
    derived_image_pool_identity = digest([
        {"slot": item["slot"], "resolved_image": candidates[item["slot"]]["resolved_image"]}
        for item in selected
    ])
    _require(
        _self_hash(gate, "qualification_gate_sha256")
        and gate["schema_name"] == QUALIFICATION_GATE_SCHEMA
        and type(gate["schema_version"]) is int
        and gate["schema_version"] == SCHEMA_VERSION
        and gate["status"] == "pass"
        and gate["contract_sha256"] == contract["contract_sha256"]
        and gate["private_pool_sha256"] == private_pool["private_pool_sha256"]
        and gate["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and gate["qualification_receipt_sha256"] == source["qualification_receipt_sha256"]
        and gate["pool_reliability_audit_sha256"]
        == gate["pool_reliability_audit"]["pool_reliability_audit_sha256"]
        == source["qualification_reliability_audit_sha256"]
        and gate["pool_reliability_audit"]["status"] == "pass"
        and gate["pool_reliability_audit"]["investigation"]["status"]
        in {"not_required", "complete"}
        and gate["pool_reliability_audit"]["investigation"][
            "cluster_presence_blocks_freeze"
        ] is False
        and receipt["status"] == "stable_pool_ready"
        and receipt["state_sha256"] == source["qualification_receipt_sha256"]
        and selection["population_sha256"] == gate["qualification_population_sha256"]
        and gate["qualification_stage_bindings"] == derived_bindings
        and gate["qualification_stage_receipt_set_sha256"] == digest(derived_bindings)
        and type(gate["qualification_stage_receipt_count"]) is int
        and gate["qualification_stage_receipt_count"] == len(derived_bindings)
        and len(derived_bindings) == 4 * len(selected)
        and gate["evaluator_identity"] == source["evaluator_identity"] == derived_evaluator_identity
        and gate["image_pool_identity"] == source["image_pool_identity"] == derived_image_pool_identity
        and gate["runtime_identity"] == contract["runtime"]["runtime_identity"] == derived_runtime_identity
        and gate["source_identity"] == source["source_identity"] == derived_source_identity
        and gate["subject_invocation_starts"] == 0
        and all(value is True for value in checks.values()),
        "qualification gate does not authorize the frozen identities",
    )


def build_live_seal(
    contract: dict[str, Any], private_pool: dict[str, Any], qualification_gate: dict[str, Any]
) -> dict[str, Any]:
    """Create separate live authority; the non-authorizing contract is unchanged."""

    validate_qualification_gate(contract, private_pool, qualification_gate)
    body = {
        "schema_name": LIVE_SEAL_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "frozen-authorized",
        "execution_authorized": True,
        "contract_sha256": contract["contract_sha256"],
        "private_pool_sha256": private_pool["private_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "qualification_gate": deepcopy(qualification_gate),
        "qualification_gate_sha256": qualification_gate["qualification_gate_sha256"],
        "qualification_receipt_sha256": contract["source"]["qualification_receipt_sha256"],
        "pool_reliability_audit_sha256": contract["source"][
            "qualification_reliability_audit_sha256"
        ],
        "harness_source_closure_sha256": contract["source"][
            "harness_source_closure"
        ]["closure_sha256"],
        "prior_evidence_sha256": contract["source"]["prior_evidence_identity"][
            "prior_evidence_sha256"
        ],
        "evaluator_identity": contract["source"]["evaluator_identity"],
        "image_pool_identity": contract["source"]["image_pool_identity"],
        "runtime_identity": contract["runtime"]["runtime_identity"],
        "source_identity": contract["source"]["source_identity"],
        "maximum_subject_invocation_starts": contract["attempt_accounting"][
            "maximum_subject_invocation_starts"
        ],
    }
    return {**body, "live_seal_sha256": digest(body)}


def validate_live_seal(
    contract: dict[str, Any],
    private_pool: dict[str, Any],
    live_seal: dict[str, Any],
    *,
    expected_live_seal_sha256: str | None = None,
) -> None:
    validate_private_pool_binding(private_pool, contract)
    _exact(
        live_seal,
        {
            "schema_name", "schema_version", "status", "execution_authorized",
            "contract_sha256", "private_pool_sha256", "schedule_sha256",
            "qualification_gate", "qualification_gate_sha256", "qualification_receipt_sha256",
            "pool_reliability_audit_sha256", "harness_source_closure_sha256",
            "prior_evidence_sha256",
            "evaluator_identity", "image_pool_identity", "runtime_identity",
            "source_identity", "maximum_subject_invocation_starts", "live_seal_sha256",
        },
        "live seal fields drifted",
    )
    source = contract["source"]
    validate_qualification_gate(contract, private_pool, live_seal["qualification_gate"])
    _require(
        _self_hash(live_seal, "live_seal_sha256")
        and live_seal["schema_name"] == LIVE_SEAL_SCHEMA
        and type(live_seal["schema_version"]) is int
        and live_seal["schema_version"] == SCHEMA_VERSION
        and live_seal["status"] == "frozen-authorized"
        and live_seal["execution_authorized"] is True
        and live_seal["contract_sha256"] == contract["contract_sha256"]
        and live_seal["private_pool_sha256"] == private_pool["private_pool_sha256"]
        and live_seal["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and live_seal["qualification_gate_sha256"]
        == live_seal["qualification_gate"]["qualification_gate_sha256"]
        and live_seal["qualification_receipt_sha256"] == source["qualification_receipt_sha256"]
        and live_seal["pool_reliability_audit_sha256"]
        == source["qualification_reliability_audit_sha256"]
        and live_seal["harness_source_closure_sha256"]
        == source["harness_source_closure"]["closure_sha256"]
        and live_seal["prior_evidence_sha256"]
        == source["prior_evidence_identity"]["prior_evidence_sha256"]
        and live_seal["evaluator_identity"] == source["evaluator_identity"]
        and live_seal["image_pool_identity"] == source["image_pool_identity"]
        and live_seal["runtime_identity"] == contract["runtime"]["runtime_identity"]
        and live_seal["source_identity"] == source["source_identity"]
        and live_seal["maximum_subject_invocation_starts"]
        == contract["attempt_accounting"]["maximum_subject_invocation_starts"]
        and (
            expected_live_seal_sha256 is None
            or live_seal["live_seal_sha256"] == expected_live_seal_sha256
        ),
        "live execution seal differs from the frozen qualified authority",
    )


def _semantic(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"event_type": event["event_type"], "payload": deepcopy(event["payload"])}
        for event in events
    ]


def read_ledger(path: Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate canonical JSONL bytes, hash chain, frozen bindings, and core replay."""

    validate_contract(contract)
    if not path.exists():
        return []
    return _parse_ledger_bytes(path.read_bytes(), contract)


def _parse_ledger_bytes(raw: bytes, contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate already-read ledger bytes without mutating recovery state."""

    _require(not raw or raw.endswith(b"\n"), "ledger has a torn final line")
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for sequence, line in enumerate(raw.splitlines(), start=1):
        try:
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExperimentConfigurationError("ledger contains malformed JSONL") from error
        _exact(
            event,
            {
                "schema_name", "schema_version", "sequence", "event_type", "recorded_at",
                "previous_event_sha256", "contract_sha256", "schedule_sha256",
                "payload", "event_sha256",
            },
            "ledger event fields drifted",
        )
        body = {key: item for key, item in event.items() if key != "event_sha256"}
        _require(
            event["schema_name"] == LEDGER_SCHEMA
            and type(event["schema_version"]) is int
            and event["schema_version"] == SCHEMA_VERSION
            and type(event["sequence"]) is int
            and event["sequence"] == sequence
            and isinstance(event["event_type"], str)
            and bool(event["event_type"])
            and isinstance(event["recorded_at"], str)
            and bool(event["recorded_at"])
            and event["previous_event_sha256"] == previous
            and event["contract_sha256"] == contract["contract_sha256"]
            and event["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
            and isinstance(event["payload"], dict)
            and event["event_sha256"] == digest(body)
            and line
            == json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "ledger hash chain or frozen identity binding failed",
        )
        events.append(event)
        previous = event["event_sha256"]
    replay_attempt_state(contract, _semantic(events))
    return events


def initialize_execution_storage(root: Path) -> dict[str, list[Path]]:
    """Create only ignored-style `.local` state with owner-private modes."""

    root = Path(root)
    _require(".local" in root.parts, "execution storage must be contained below .local")
    absolute = root.absolute()
    local_ancestor = next(
        (ancestor for ancestor in (absolute, *absolute.parents) if ancestor.name == ".local"),
        None,
    )
    _require(local_ancestor is not None, "execution storage lacks a literal .local ancestor")
    cursor = local_ancestor
    for part in ("", *absolute.relative_to(local_ancestor).parts):
        if part:
            cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            _require(not cursor.is_symlink(), "execution storage cannot traverse symlinks")
    resolved = root.resolve()
    local_index = resolved.parts.index(".local") if ".local" in resolved.parts else -1
    _require(local_index >= 0, "resolved execution storage escaped .local")
    _require(
        resolved.is_relative_to(local_ancestor.resolve()),
        "resolved execution storage escaped its literal .local root",
    )
    directories = [resolved, resolved / "receipts"]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        _require(not directory.is_symlink(), "execution storage directory cannot be a symlink")
        directory.chmod(0o700)
    files = [
        resolved / "ledger.jsonl",
        resolved / "checkpoint.json",
        resolved / "runner.lock",
        resolved / "receipt-state.json",
    ]
    for path in files:
        descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(descriptor)
        path.chmod(0o600)
    marker_body = {
        "schema_name": "engineering-scope-guard.reasoning-effort-v2-storage-authority",
        "schema_version": SCHEMA_VERSION,
        "status": "initialized",
        "root_identity_sha256": digest({"resolved_execution_root": str(resolved)}),
    }
    _atomic_json(
        resolved / "receipt-state.json",
        {**marker_body, "receipt_sha256": digest(marker_body)},
    )
    return {"directories": directories, "files": files}


def _read_canary_ledger(path: Path, authority: dict[str, Any]) -> list[dict[str, Any]]:
    _require(path.name == "canary-ledger.jsonl", "canary ledger path is not canonical")
    if not path.exists():
        return []
    _require_private_artifact_path(path)
    raw = path.read_bytes()
    _require(not raw or raw.endswith(b"\n"), "canary ledger has a torn final line")
    events: list[dict[str, Any]] = []
    previous = None
    state = "empty"
    reservation_sha = None
    process_sha = None
    for sequence, line in enumerate(raw.splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError("canary ledger is malformed") from error
        _exact(
            event,
            {
                "schema_name", "schema_version", "sequence", "event_type",
                "recorded_at", "previous_event_sha256", "authority_sha256",
                "payload", "event_sha256",
            },
            "canary ledger fields drifted",
        )
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        _require(
            event["schema_name"] == CANARY_LEDGER_SCHEMA
            and event["schema_version"] == 1
            and event["sequence"] == sequence
            and event["previous_event_sha256"] == previous
            and event["authority_sha256"] == authority["canary_authority_sha256"]
            and event["event_sha256"] == digest(body)
            and line == json.dumps(event, sort_keys=True, separators=(",", ":")).encode(),
            "canary ledger hash chain or authority binding failed",
        )
        payload = event["payload"]
        if event["event_type"] == "canary_start_reserved":
            _exact(
                payload,
                {
                    "command_sha256", "codex_binary_sha256",
                    "ownership_nonce_sha256",
                },
                "canary reservation fields drifted",
            )
            _require(
                state == "empty"
                and payload["command_sha256"] == authority["command_sha256"]
                and payload["codex_binary_sha256"] == authority["codex_binary_sha256"]
                and _sha256(payload["ownership_nonce_sha256"]),
                "canary reservation is repeated or unbound",
            )
            state = "reserved"
            reservation_sha = event["event_sha256"]
        elif event["event_type"] == "canary_process_attached":
            _exact(
                payload,
                {
                    "reservation_event_sha256", "pid", "os_start_identity",
                    "codex_binary_sha256", "process_identity_sha256",
                },
                "canary process fields drifted",
            )
            _require(
                state == "reserved"
                and payload["reservation_event_sha256"] == reservation_sha
                and type(payload["pid"]) is int and payload["pid"] > 0
                and isinstance(payload["os_start_identity"], str)
                and bool(payload["os_start_identity"])
                and payload["codex_binary_sha256"] == authority["codex_binary_sha256"]
                and _sha256(payload["process_identity_sha256"]),
                "canary process is repeated, malformed, or unbound",
            )
            state = "attached"
            process_sha = event["event_sha256"]
        elif event["event_type"] == "canary_terminal":
            _exact(
                payload,
                {
                    "status", "reservation_event_sha256", "process_event_sha256",
                    "canary_receipt_sha256", "failure_code",
                },
                "canary terminal fields drifted",
            )
            _require(
                state in {"reserved", "attached"}
                and payload["reservation_event_sha256"] == reservation_sha
                and payload["process_event_sha256"] == process_sha
                and payload["status"] in {"success", "failure"},
                "canary terminal event is out of sequence",
            )
            if payload["status"] == "success":
                _require(
                    state == "attached" and _sha256(payload["canary_receipt_sha256"])
                    and payload["failure_code"] is None,
                    "successful canary lacks attached process or receipt",
                )
            else:
                _require(
                    payload["canary_receipt_sha256"] is None
                    and isinstance(payload["failure_code"], str)
                    and bool(payload["failure_code"]),
                    "failed canary lacks a deterministic failure code",
                )
            state = f"terminal_{payload['status']}"
        else:
            raise ExperimentConfigurationError("unknown canary lifecycle event")
        events.append(event)
        previous = event["event_sha256"]
    return events


def replay_canary_lifecycle(path: Path, authority: dict[str, Any]) -> dict[str, Any]:
    events = _read_canary_ledger(path, authority)
    reservation = next((event for event in events if event["event_type"] == "canary_start_reserved"), None)
    process = next((event for event in events if event["event_type"] == "canary_process_attached"), None)
    terminal = next((event for event in events if event["event_type"] == "canary_terminal"), None)
    return {
        "events": events,
        "reservation": reservation,
        "process": process,
        "terminal": terminal,
        "may_launch": not events,
        "terminal_status": None if terminal is None else terminal["payload"]["status"],
    }


def _append_canary_event(
    path: Path, authority: dict[str, Any], event_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    root = _execution_storage_root(path)
    _require(path.resolve() == (root / "canary-ledger.jsonl").resolve(), "canary ledger escapes execution root")
    lock_path = root / "canary-ledger.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    os.close(descriptor)
    lock_path.chmod(0o600)
    with _lock(lock_path):
        events = _read_canary_ledger(path, authority)
        body = {
            "schema_name": CANARY_LEDGER_SCHEMA,
            "schema_version": 1,
            "sequence": len(events) + 1,
            "event_type": event_type,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "previous_event_sha256": events[-1]["event_sha256"] if events else None,
            "authority_sha256": authority["canary_authority_sha256"],
            "payload": deepcopy(payload),
        }
        event = {**body, "event_sha256": digest(body)}
        ledger_descriptor = os.open(
            path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600
        )
        path.chmod(0o600)
        with os.fdopen(ledger_descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        _read_canary_ledger(path, authority)
        return event


def reserve_canary_start(
    path: Path, authority: dict[str, Any], *, ownership_nonce_sha256: str
) -> dict[str, Any]:
    validate_harness_source_closure(
        authority["harness_source_closure"],
        root=Path(__file__).resolve().parents[1],
    )
    validate_prior_evidence_identity(
        authority["prior_evidence_identity"],
        root=Path(__file__).resolve().parents[1],
    )
    state = replay_canary_lifecycle(path, authority)
    if state["reservation"] is not None:
        _require(
            state["reservation"]["payload"]["ownership_nonce_sha256"]
            == ownership_nonce_sha256,
            "a second canary reservation is forbidden",
        )
        return state["reservation"]
    _require(state["may_launch"], "a second canary launch is forbidden")
    return _append_canary_event(
        path,
        authority,
        "canary_start_reserved",
        {
            "command_sha256": authority["command_sha256"],
            "codex_binary_sha256": authority["codex_binary_sha256"],
            "ownership_nonce_sha256": ownership_nonce_sha256,
        },
    )


def attach_canary_process(
    path: Path, authority: dict[str, Any], *, pid: int,
    os_start_identity: str, process_identity_sha256: str,
) -> dict[str, Any]:
    state = replay_canary_lifecycle(path, authority)
    _require(state["reservation"] is not None and state["process"] is None and state["terminal"] is None, "canary process cannot be attached")
    return _append_canary_event(
        path,
        authority,
        "canary_process_attached",
        {
            "reservation_event_sha256": state["reservation"]["event_sha256"],
            "pid": pid,
            "os_start_identity": os_start_identity,
            "codex_binary_sha256": authority["codex_binary_sha256"],
            "process_identity_sha256": process_identity_sha256,
        },
    )


def finish_canary_lifecycle(
    path: Path, authority: dict[str, Any], *, status: str,
    canary_receipt_sha256: str | None = None, failure_code: str | None = None,
) -> dict[str, Any]:
    state = replay_canary_lifecycle(path, authority)
    _require(state["reservation"] is not None and state["terminal"] is None, "canary is already terminal or unreserved")
    return _append_canary_event(
        path,
        authority,
        "canary_terminal",
        {
            "status": status,
            "reservation_event_sha256": state["reservation"]["event_sha256"],
            "process_event_sha256": (
                None if state["process"] is None else state["process"]["event_sha256"]
            ),
            "canary_receipt_sha256": canary_receipt_sha256,
            "failure_code": failure_code,
        },
    )


def reconcile_canary_process(
    path: Path,
    authority: dict[str, Any],
    *,
    process_observer: Callable[[int], dict[str, Any]],
) -> dict[str, Any]:
    """Reconcile an attached canary by exact PID/start/process identity, never relaunch."""

    state = replay_canary_lifecycle(path, authority)
    _require(state["terminal"] is None, "terminal canary cannot be reconciled or relaunched")
    if state["process"] is None:
        _require(state["reservation"] is not None, "canary has no durable reservation")
        finish_canary_lifecycle(
            path, authority, status="failure", failure_code="crash_before_spawn"
        )
        return replay_canary_lifecycle(path, authority)
    attached = state["process"]["payload"]
    observed = process_observer(attached["pid"])
    _exact(
        observed,
        {"pid", "os_start_identity", "process_identity_sha256", "status"},
        "canary process observation fields drifted",
    )
    _require(
        observed["pid"] == attached["pid"]
        and observed["os_start_identity"] == attached["os_start_identity"]
        and observed["process_identity_sha256"] == attached["process_identity_sha256"]
        and observed["status"] in {"running", "not_running"},
        "canary process observation does not prove the attached process identity",
    )
    if observed["status"] == "not_running":
        finish_canary_lifecycle(
            path,
            authority,
            status="failure",
            failure_code="crash_after_spawn_proven_not_running",
        )
        return replay_canary_lifecycle(path, authority)
    return state


def _checkpoint(contract: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    body = {
        "schema_name": CHECKPOINT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "event_count": len(events),
        "head_event_sha256": events[-1]["event_sha256"] if events else None,
    }
    return {**body, "checkpoint_sha256": digest(body)}


def sync_checkpoint(ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any]) -> dict[str, Any]:
    events = read_ledger(ledger_path, contract)
    value = _checkpoint(contract, events)
    _atomic_json(checkpoint_path, value)
    return value


def read_checkpoint(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any], *, repair: bool = False
) -> dict[str, Any]:
    events = read_ledger(ledger_path, contract)
    expected = _checkpoint(contract, events)
    if not checkpoint_path.exists():
        _require(repair, "ledger checkpoint is missing")
        _atomic_json(checkpoint_path, expected)
        return expected
    try:
        observed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExperimentConfigurationError("ledger checkpoint is malformed") from error
    if canonical_bytes(observed) != canonical_bytes(expected):
        _require(repair, "ledger checkpoint differs from the validated chain")
        _atomic_json(checkpoint_path, expected)
    return expected


def recover_torn_ledger_from_checkpoint(
    ledger_path: Path,
    checkpoint_path: Path,
    contract: dict[str, Any],
    live_seal: dict[str, Any],
    private_pool: dict[str, Any],
) -> dict[str, Any]:
    """Truncate only a suffix excluded by an exact validated checkpoint."""

    validate_live_seal(contract, private_pool, live_seal)
    _require_mutation_paths(ledger_path, checkpoint_path)
    _require(ledger_path.exists() and checkpoint_path.exists(), "recovery evidence is missing")
    with _lock(ledger_path.with_suffix(ledger_path.suffix + ".lock")):
        return _recover_torn_ledger_locked(ledger_path, checkpoint_path, contract)


def _recover_torn_ledger_locked(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    try:
        checkpoint_raw = checkpoint_path.read_bytes()
        checkpoint = json.loads(checkpoint_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError("recovery checkpoint is malformed") from error
    _exact(
        checkpoint,
        {
            "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
            "event_count", "head_event_sha256", "checkpoint_sha256",
        },
        "recovery checkpoint fields drifted",
    )
    checkpoint_body = {
        key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"
    }
    _require(
        checkpoint_raw
        == (json.dumps(checkpoint, sort_keys=True, separators=(",", ":")) + "\n").encode()
        and checkpoint["checkpoint_sha256"] == digest(checkpoint_body)
        and checkpoint["schema_name"] == CHECKPOINT_SCHEMA
        and checkpoint["schema_version"] == SCHEMA_VERSION
        and checkpoint["contract_sha256"] == contract["contract_sha256"]
        and checkpoint["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and type(checkpoint["event_count"]) is int
        and checkpoint["event_count"] >= 0,
        "recovery checkpoint is not canonical or frozen",
    )
    raw = ledger_path.read_bytes()
    _require(
        not raw.endswith(b"\n"),
        "recovery refuses to discard a complete uncheckpointed ledger suffix",
    )
    lines = raw.splitlines(keepends=True)
    count = checkpoint["event_count"]
    _require(len(lines) >= count, "ledger is shorter than its checkpoint")
    prefix = b"".join(lines[:count])
    events = _parse_ledger_bytes(prefix, contract)
    expected_head = events[-1]["event_sha256"] if events else None
    _require(
        len(events) == count and checkpoint["head_event_sha256"] == expected_head,
        "checkpoint does not identify the validated ledger prefix",
    )
    _require(raw != prefix, "ledger has no uncheckpointed suffix to recover")
    temporary = ledger_path.with_name(f".{ledger_path.name}.recover-{os.getpid()}")
    with temporary.open("xb") as handle:
        handle.write(prefix)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, ledger_path)
    directory = os.open(ledger_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    _require(ledger_path.read_bytes() == prefix, "recovered ledger readback differs")
    reread = _parse_ledger_bytes(ledger_path.read_bytes(), contract)
    _require(
        len(reread) == checkpoint["event_count"]
        and (reread[-1]["event_sha256"] if reread else None)
        == checkpoint["head_event_sha256"],
        "recovered ledger no longer matches its validated checkpoint",
    )
    return checkpoint


def append_ledger_event(
    ledger_path: Path,
    checkpoint_path: Path,
    contract: dict[str, Any],
    live_seal: dict[str, Any],
    private_pool: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    *,
    _attempt_start_capability: object | None = None,
) -> dict[str, Any]:
    """Append one fsync'd event and atomically replace its replay checkpoint."""

    _require(
        event_type != "attempt_started"
        or _attempt_start_capability is _ATTEMPT_START_CAPABILITY,
        "attempt_started must pass the disk-safety-enforcing transition API",
    )
    validate_live_seal(contract, private_pool, live_seal)
    _require_mutation_paths(ledger_path, checkpoint_path)
    with _lock(ledger_path.with_suffix(ledger_path.suffix + ".lock")):
        events = read_ledger(ledger_path, contract)
        replay_attempt_state(
            contract,
            [*_semantic(events), {"event_type": event_type, "payload": deepcopy(payload)}],
        )
        body = {
            "schema_name": LEDGER_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "sequence": len(events) + 1,
            "event_type": event_type,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "previous_event_sha256": events[-1]["event_sha256"] if events else None,
            "contract_sha256": contract["contract_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "payload": deepcopy(payload),
        }
        event = {**body, "event_sha256": digest(body)}
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(ledger_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _atomic_json(checkpoint_path, _checkpoint(contract, [*events, event]))
        return event


def record_attempt_started(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any], live_seal: dict[str, Any],
    private_pool: dict[str, Any], *, cell_id: str, attempt: int
) -> dict[str, Any]:
    events = read_ledger(ledger_path, contract)
    state = replay_attempt_state(contract, _semantic(events))
    _require(
        any(
            event["event_type"] == "disk_safety_checked"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
            and event["payload"]["receipt"]["status"] == "pass"
            for event in events
        ),
        "attempt start requires a durable passing D-068 disk-safety receipt",
    )
    cell = next(cell for cell in contract["schedule"]["cells"] if cell["cell_id"] == cell_id)
    commitment = state["effective_task_commitment_by_slot"][cell["population_slot"]]
    return append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool, "attempt_started",
        {"cell_id": cell_id, "attempt": attempt, "effective_task_commitment_sha256": commitment},
        _attempt_start_capability=_ATTEMPT_START_CAPABILITY,
    )


def record_disk_safety_checked(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any],
    live_seal: dict[str, Any], private_pool: dict[str, Any], *,
    cell_id: str, attempt: int, receipt: dict[str, Any],
) -> dict[str, Any]:
    """Persist the sanitized D-068 decision before capacity or preparation."""

    events = read_ledger(ledger_path, contract)
    existing = next(
        (
            event for event in reversed(events)
            if event["event_type"] == "disk_safety_checked"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
        ),
        None,
    )
    if existing is not None:
        _require(
            existing["payload"]["receipt"] == receipt,
            "replayed disk-safety decision differs from durable evidence",
        )
        return existing
    return append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool,
        "disk_safety_checked",
        {
            "cell_id": cell_id,
            "attempt": attempt,
            "receipt": deepcopy(receipt),
            "receipt_sha256": digest(receipt),
        },
    )


def reserve_attempt_capacity_or_stop(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any],
    live_seal: dict[str, Any], private_pool: dict[str, Any], *,
    cell_id: str, attempt: int,
) -> bool:
    """Reserve one prospective subject start before creating an active attempt."""

    events = read_ledger(ledger_path, contract)
    state = replay_attempt_state(contract, _semantic(events))
    _require(state["batch_stop_classification"] is None, "batch is already stopped")
    _require(state["next_cell_id"] == cell_id, "capacity request violates frozen schedule")
    _require(attempt in (1, 2), "capacity request attempt is invalid")
    subject_events = [
        event for event in events if event["event_type"] == "subject_invocation_started"
    ]
    started_cells = {event["payload"]["cell_id"] for event in subject_events}
    never_started = sum(
        cell["cell_id"] not in started_cells for cell in contract["schedule"]["cells"]
    )
    projected_never_started = never_started - (1 if cell_id not in started_cells else 0)
    projected = (
        state["canary_subject_invocation_starts"]
        + len(subject_events) + 1 + projected_never_started
    )
    maximum = contract["attempt_accounting"]["maximum_subject_invocation_starts"]
    if projected <= maximum:
        return True
    append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool,
        "capacity_exhausted",
        {
            "cell_id": cell_id,
            "requested_attempt": attempt,
            "classification": "durable_evidence_incomplete",
            "canary_subject_invocation_starts": state[
                "canary_subject_invocation_starts"
            ],
            "experiment_subject_invocation_starts": len(subject_events),
            "never_started_mandatory_cells": never_started,
            "projected_subject_invocation_starts_with_reservation": projected,
            "maximum_subject_invocation_starts": maximum,
        },
    )
    return False


def record_subject_invocation_started(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any], live_seal: dict[str, Any],
    private_pool: dict[str, Any], *, cell_id: str, attempt: int, command_sha256: str,
    ownership_token_sha256: str, process_identity_sha256: str,
) -> dict[str, Any]:
    state = replay_attempt_state(contract, _semantic(read_ledger(ledger_path, contract)))
    cell = next(cell for cell in contract["schedule"]["cells"] if cell["cell_id"] == cell_id)
    commitment = state["effective_task_commitment_by_slot"][cell["population_slot"]]
    return append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool,
        "subject_invocation_started",
        {
            "cell_id": cell_id, "attempt": attempt,
            "effective_task_commitment_sha256": commitment,
            "command_sha256": command_sha256,
            "ownership_token_sha256": ownership_token_sha256,
            "process_identity_sha256": process_identity_sha256,
        },
    )


def advance_outcome_blind_attempt_authorization(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any],
    live_seal: dict[str, Any], private_pool: dict[str, Any],
) -> dict[str, Any] | None:
    """Append the sole frozen attempt-2 transition after terminal attempt 1."""

    events = read_ledger(ledger_path, contract)
    semantic = _semantic(events)
    state = replay_attempt_state(contract, semantic)
    cell_id = state["next_cell_id"]
    if cell_id is None:
        return None
    if any(
        event["event_type"] in {"attempt_2_authorized", "alternate_activated"}
        and event["payload"]["cell_id"] == cell_id
        for event in events
    ):
        return None
    finish = next(
        (
            event["payload"] for event in reversed(events)
            if event["event_type"] == "attempt_finished"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == 1
        ),
        None,
    )
    if finish is None:
        return None
    classification = finish["classification"]
    if classification in RETRYABLE_INFRASTRUCTURE:
        return append_ledger_event(
            ledger_path, checkpoint_path, contract, live_seal, private_pool,
            "attempt_2_authorized",
            {
                "cell_id": cell_id, "prior_attempt": 1, "next_attempt": 2,
                "classification": classification,
                "evidence_sha256": finish["evidence_sha256"],
                "effective_task_commitment_sha256": finish[
                    "effective_task_commitment_sha256"
                ],
            },
        )
    if classification in ALTERNATE_ACTIVATION_CLASSES:
        cell = next(item for item in contract["schedule"]["cells"] if item["cell_id"] == cell_id)
        projection = public_pool_projection(private_pool)
        used = sum(event["event_type"] == "alternate_activated" for event in events)
        ordinal = used + 1
        alternate = next(
            (
                item for item in projection["alternate_order_commitments"]
                if item["alternate_ordinal"] == ordinal
            ),
            None,
        )
        _require(alternate is not None, "frozen alternate queue is exhausted")
        return append_ledger_event(
            ledger_path, checkpoint_path, contract, live_seal, private_pool,
            "alternate_activated",
            {
                "cell_id": cell_id,
                "population_slot": cell["population_slot"],
                "trigger_attempt": 1,
                "classification": classification,
                "evidence_sha256": finish["evidence_sha256"],
                "replaces_task_commitment_sha256": finish[
                    "effective_task_commitment_sha256"
                ],
                "alternate_ordinal": ordinal,
                "alternate_task_commitment_sha256": alternate[
                    "task_commitment_sha256"
                ],
                "next_attempt": 2,
                "subject_outcome_used": False,
                "outcome_direction_inspected": False,
            },
        )
    return None


def record_evaluator_invocation_started(
    ledger_path: Path, checkpoint_path: Path, contract: dict[str, Any],
    live_seal: dict[str, Any], private_pool: dict[str, Any], *,
    cell_id: str, attempt: int, evaluator_command_sha256: str,
    ownership_token_sha256: str, process_identity_sha256: str,
    container_identity_sha256: str,
) -> dict[str, Any]:
    """Durably own one gated official-evaluator invocation before release."""

    state = replay_attempt_state(contract, _semantic(read_ledger(ledger_path, contract)))
    cell = next(cell for cell in contract["schedule"]["cells"] if cell["cell_id"] == cell_id)
    commitment = state["effective_task_commitment_by_slot"][cell["population_slot"]]
    return append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool,
        "evaluator_invocation_started",
        {
            "cell_id": cell_id, "attempt": attempt,
            "effective_task_commitment_sha256": commitment,
            "evaluator_command_sha256": evaluator_command_sha256,
            "ownership_token_sha256": ownership_token_sha256,
            "process_identity_sha256": process_identity_sha256,
            "container_identity_sha256": container_identity_sha256,
        },
    )


def validate_terminal_receipt(contract: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Validate one provider-free, public-safe terminal receipt and self-seal."""

    validate_contract(contract)
    _exact(
        receipt,
        {
            "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
            "cell_id", "attempt", "effective_task_commitment_sha256",
            "subject_invocation_started", "command_sha256", "classification",
            "execution_receipt_sha256", "evaluator_receipt_sha256",
            "measurement_receipt_sha256", "execution_artifact", "evaluator_artifact",
            "measurement_artifact", "analysis_record", "terminal_receipt_sha256",
        },
        "terminal receipt fields drifted",
    )
    record = _exact(receipt["analysis_record"], ANALYSIS_RECORD_KEYS, "analysis record fields drifted")
    allowed = set(EXPERIMENTAL_OUTCOMES) | set(RETRYABLE_INFRASTRUCTURE) | set(
        ALTERNATE_ACTIVATION_CLASSES
    ) | set(MANDATORY_BATCH_STOP)
    work = [record[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)]
    complete_work = all(value is not None for value in work)
    absent_work = all(value is None for value in work)
    _require(
        _self_hash(receipt, "terminal_receipt_sha256")
        and receipt["schema_name"] == TERMINAL_RECEIPT_SCHEMA
        and type(receipt["schema_version"]) is int
        and receipt["schema_version"] == SCHEMA_VERSION
        and receipt["contract_sha256"] == contract["contract_sha256"]
        and receipt["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and receipt["cell_id"] in {cell["cell_id"] for cell in contract["schedule"]["cells"]}
        and type(receipt["attempt"]) is int
        and receipt["attempt"] in (1, 2)
        and _sha256(receipt["effective_task_commitment_sha256"])
        and type(receipt["subject_invocation_started"]) is bool
        and (
            (_sha256(receipt["command_sha256"]) and receipt["subject_invocation_started"])
            or (receipt["command_sha256"] is None and not receipt["subject_invocation_started"])
        )
        and receipt["classification"] in allowed
        and _sha256(receipt["execution_receipt_sha256"])
        and _sha256(receipt["evaluator_receipt_sha256"])
        and _sha256(receipt["measurement_receipt_sha256"])
        and record["cell_id"] == receipt["cell_id"]
        and record["termination"] == receipt["classification"]
        and type(record["timed_out"]) is bool
        and record["timed_out"] == (receipt["classification"] == "trajectory_timeout")
        and isinstance(record["evaluator_anomalies"], list)
        and all(
            isinstance(item, str) and _PUBLIC_CODE.fullmatch(item)
            for item in record["evaluator_anomalies"]
        )
        and (complete_work or absent_work),
        "terminal receipt is malformed or differs from its analysis projection",
    )
    _require(
        receipt["subject_invocation_started"] or absent_work,
        "receipt without a subject start cannot report subject work",
    )
    _require(
        receipt["classification"] not in EXPERIMENTAL_OUTCOMES
        or receipt["subject_invocation_started"],
        "experimental terminal receipt lacks a subject start",
    )
    if complete_work:
        _require(
            all(type(record[field]) is int and record[field] >= 0 for field in INTEGER_WORK_FIELDS)
            and type(record["wall_seconds"]) is float
            and math.isfinite(record["wall_seconds"])
            and record["wall_seconds"] >= 0.0,
            "terminal receipt work fields are malformed",
        )
        _require(
            record["cached_input_tokens"] + record["cache_write_input_tokens"]
            <= record["input_tokens"]
            and record["reasoning_output_tokens"] <= record["output_tokens"],
            "terminal receipt token components are inconsistent",
        )
    _validate_terminal_artifact_bundle(contract, receipt)


def _canonical_artifact_bytes(artifact: dict[str, Any]) -> bytes:
    return (json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _seal_artifact(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "receipt_sha256": digest(body)}


def _validate_terminal_artifact_bundle(
    contract: dict[str, Any], receipt: dict[str, Any]
) -> None:
    common = {
        "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
        "cell_id", "attempt", "effective_task_commitment_sha256", "receipt_sha256",
    }
    execution = _exact(
        receipt["execution_artifact"],
        common | {
            "subject_invocation_started", "command_sha256", "status", "timed_out",
            "subject_exit_code", "ownership_token_sha256", "process_identity_sha256",
            "container_identity_sha256", "subject_stdout_sha256", "subject_stderr_sha256",
            "prediction_sha256", "patch_sha256", "cleanup_receipt_sha256",
        },
        "embedded execution artifact fields drifted",
    )
    evaluator = _exact(
        receipt["evaluator_artifact"],
        common | {
            "evaluator_identity", "disposition", "anomaly_codes",
            "evaluator_stdout_sha256", "evaluator_stderr_sha256",
            "report_sha256", "results_sha256", "invocation_started",
            "evaluator_command_sha256", "ownership_token_sha256",
            "process_identity_sha256", "container_identity_sha256",
        },
        "embedded evaluator artifact fields drifted",
    )
    measurement = _exact(
        receipt["measurement_artifact"],
        common | {"record_completeness", *INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS},
        "embedded measurement artifact fields drifted",
    )
    for label, artifact, schema, byte_sha in (
        ("execution", execution, EXECUTION_ARTIFACT_SCHEMA, receipt["execution_receipt_sha256"]),
        ("evaluator", evaluator, EVALUATOR_ARTIFACT_SCHEMA, receipt["evaluator_receipt_sha256"]),
        ("measurement", measurement, MEASUREMENT_ARTIFACT_SCHEMA, receipt["measurement_receipt_sha256"]),
    ):
        _require(
            artifact["schema_name"] == schema
            and artifact["schema_version"] == SCHEMA_VERSION
            and _self_hash(artifact, "receipt_sha256")
            and hashlib.sha256(_canonical_artifact_bytes(artifact)).hexdigest() == byte_sha,
            f"embedded {label} artifact seal drifted",
        )
        _validate_artifact_binding(
            artifact, contract, cell_id=receipt["cell_id"], attempt=receipt["attempt"],
            effective_task_commitment_sha256=receipt["effective_task_commitment_sha256"],
            label=f"embedded {label} artifact",
        )
    _require(
        execution["subject_invocation_started"] is receipt["subject_invocation_started"]
        and execution["command_sha256"] == receipt["command_sha256"]
        and evaluator["evaluator_identity"] == contract["source"]["evaluator_identity"]
        and evaluator["anomaly_codes"] == receipt["analysis_record"]["evaluator_anomalies"]
        and all(
            measurement[field] == receipt["analysis_record"][field]
            for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)
        ),
        "terminal receipt projection differs from embedded artifacts",
    )
    disposition_map = {
        "accepted": "accepted_completed", "test_failure": "evaluator_test_failure",
        "empty_patch": "empty_patch_failure", "error": "official_evaluator_error",
        "incomplete": "official_evaluator_incomplete", "not_run": None,
    }
    _require(
        execution["status"] in ({
            "returned", "agent_subject_failure", "trajectory_timeout",
            "provider_api_infrastructure_failure",
            "local_docker_runtime_infrastructure_failure", "durable_evidence_incomplete",
        } | set(ALTERNATE_ACTIVATION_CLASSES) | set(MANDATORY_BATCH_STOP))
        and evaluator["disposition"] in disposition_map,
        "embedded artifact terminal taxonomy is malformed",
    )
    derived = (
        disposition_map[evaluator["disposition"]]
        if execution["status"] == "returned"
        else execution["status"]
    )
    _require(
        derived == receipt["classification"]
        and (
            execution["status"] == "returned"
            and evaluator["disposition"] != "not_run"
            or execution["status"] != "returned"
            and evaluator["disposition"]
            == ("incomplete" if evaluator["invocation_started"] else "not_run")
        ),
        "terminal classification is not derived from embedded artifacts",
    )


def _build_terminal_receipt(
    contract: dict[str, Any], *, cell_id: str, attempt: int,
    effective_task_commitment_sha256: str, subject_invocation_started: bool,
    command_sha256: str | None, classification: str,
    execution_artifact: dict[str, Any], evaluator_artifact: dict[str, Any],
    measurement_artifact: dict[str, Any], analysis_record: dict[str, Any]
) -> dict[str, Any]:
    body = {
        "schema_name": TERMINAL_RECEIPT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "cell_id": cell_id,
        "attempt": attempt,
        "effective_task_commitment_sha256": effective_task_commitment_sha256,
        "subject_invocation_started": subject_invocation_started,
        "command_sha256": command_sha256,
        "classification": classification,
        "execution_receipt_sha256": hashlib.sha256(_canonical_artifact_bytes(execution_artifact)).hexdigest(),
        "evaluator_receipt_sha256": hashlib.sha256(_canonical_artifact_bytes(evaluator_artifact)).hexdigest(),
        "measurement_receipt_sha256": hashlib.sha256(_canonical_artifact_bytes(measurement_artifact)).hexdigest(),
        "execution_artifact": deepcopy(execution_artifact),
        "evaluator_artifact": deepcopy(evaluator_artifact),
        "measurement_artifact": deepcopy(measurement_artifact),
        "analysis_record": deepcopy(analysis_record),
    }
    receipt = {**body, "terminal_receipt_sha256": digest(body)}
    validate_terminal_receipt(contract, receipt)
    return receipt


def build_terminal_receipt(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Reject the retired caller-asserted result construction boundary."""

    raise ExperimentConfigurationError(
        "evaluator artifact evidence is required to build a terminal receipt"
    )


def _load_self_hashed_artifact(
    path: Path, *, schema_name: str, keys: set[str], label: str
) -> tuple[dict[str, Any], bytes]:
    artifact, raw = _canonical_json_file(path, label)
    _exact(artifact, keys, f"{label} fields drifted")
    _require(
        raw == (json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n").encode()
        and artifact["schema_name"] == schema_name
        and type(artifact["schema_version"]) is int
        and artifact["schema_version"] == SCHEMA_VERSION
        and _self_hash(artifact, "receipt_sha256"),
        f"{label} is not canonical and self-hashed",
    )
    return artifact, raw


def _validate_artifact_binding(
    artifact: dict[str, Any], contract: dict[str, Any], *, cell_id: str, attempt: int,
    effective_task_commitment_sha256: str, label: str,
) -> None:
    _require(
        artifact["contract_sha256"] == contract["contract_sha256"]
        and artifact["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and artifact["cell_id"] == cell_id
        and artifact["attempt"] == attempt
        and artifact["effective_task_commitment_sha256"]
        == effective_task_commitment_sha256,
        f"{label} differs from the frozen cell binding",
    )


def _build_terminal_receipt_from_artifacts(
    contract: dict[str, Any], *, cell_id: str, attempt: int,
    effective_task_commitment_sha256: str,
    execution_receipt_path: Path,
    evaluator_receipt_path: Path,
    measurement_receipt_path: Path,
) -> dict[str, Any]:
    """Derive classification and work only from exact persisted artifacts."""

    validate_contract(contract)
    roots = {
        _require_private_artifact_path(Path(path))
        for path in (execution_receipt_path, evaluator_receipt_path, measurement_receipt_path)
    }
    _require(len(roots) == 1, "artifacts do not share one initialized authority root")
    common = {
        "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
        "cell_id", "attempt", "effective_task_commitment_sha256", "receipt_sha256",
    }
    execution, _ = _load_self_hashed_artifact(
        Path(execution_receipt_path),
        schema_name=EXECUTION_ARTIFACT_SCHEMA,
        keys=common
        | {
            "subject_invocation_started", "command_sha256", "status", "timed_out",
            "subject_exit_code", "ownership_token_sha256", "process_identity_sha256",
            "container_identity_sha256", "subject_stdout_sha256", "subject_stderr_sha256",
            "prediction_sha256", "patch_sha256", "cleanup_receipt_sha256",
        },
        label="execution receipt",
    )
    evaluator, _ = _load_self_hashed_artifact(
        Path(evaluator_receipt_path),
        schema_name=EVALUATOR_ARTIFACT_SCHEMA,
        keys=common | {
            "evaluator_identity", "disposition", "anomaly_codes",
            "evaluator_stdout_sha256", "evaluator_stderr_sha256",
            "report_sha256", "results_sha256", "invocation_started",
            "evaluator_command_sha256", "ownership_token_sha256",
            "process_identity_sha256", "container_identity_sha256",
        },
        label="evaluator receipt",
    )
    measurement, _ = _load_self_hashed_artifact(
        Path(measurement_receipt_path),
        schema_name=MEASUREMENT_ARTIFACT_SCHEMA,
        keys=common | {"record_completeness", *INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS},
        label="measurement receipt",
    )
    for label, artifact in (
        ("execution receipt", execution),
        ("evaluator receipt", evaluator),
        ("measurement receipt", measurement),
    ):
        _validate_artifact_binding(
            artifact, contract, cell_id=cell_id, attempt=attempt,
            effective_task_commitment_sha256=effective_task_commitment_sha256,
            label=label,
        )
    started = execution["subject_invocation_started"]
    command = execution["command_sha256"]
    execution_statuses = {
        "returned", "agent_subject_failure", "trajectory_timeout",
        "provider_api_infrastructure_failure",
        "local_docker_runtime_infrastructure_failure", "durable_evidence_incomplete",
    } | set(ALTERNATE_ACTIVATION_CLASSES) | set(MANDATORY_BATCH_STOP)
    _require(
        type(started) is bool
        and execution["status"] in execution_statuses
        and type(execution["timed_out"]) is bool
        and execution["timed_out"] == (execution["status"] == "trajectory_timeout")
        and (execution["subject_exit_code"] is None or type(execution["subject_exit_code"]) is int)
        and (
            started
            and _sha256(command)
            and _sha256(execution["ownership_token_sha256"])
            and _sha256(execution["process_identity_sha256"])
            and _sha256(execution["container_identity_sha256"])
            or not started
            and command is None
            and execution["ownership_token_sha256"] is None
            and execution["process_identity_sha256"] is None
            and execution["container_identity_sha256"] is None
        ),
        "execution receipt launch or termination evidence is malformed",
    )
    dispositions = {
        "accepted": "accepted_completed",
        "test_failure": "evaluator_test_failure",
        "empty_patch": "empty_patch_failure",
        "error": "official_evaluator_error",
        "incomplete": "official_evaluator_incomplete",
        "not_run": None,
    }
    _require(
        evaluator["evaluator_identity"] == contract["source"]["evaluator_identity"]
        and evaluator["disposition"] in dispositions
        and isinstance(evaluator["anomaly_codes"], list)
        and all(isinstance(code, str) and _PUBLIC_CODE.fullmatch(code) for code in evaluator["anomaly_codes"]),
        "evaluator receipt identity, disposition, or anomaly codes are malformed",
    )
    _require(
        type(evaluator["invocation_started"]) is bool
        and (
            evaluator["invocation_started"]
            and all(_sha256(evaluator[field]) for field in (
                "evaluator_command_sha256", "ownership_token_sha256",
                "process_identity_sha256", "container_identity_sha256",
            ))
            or not evaluator["invocation_started"]
            and all(evaluator[field] is None for field in (
                "evaluator_command_sha256", "ownership_token_sha256",
                "process_identity_sha256", "container_identity_sha256",
            ))
        ),
        "evaluator launch evidence is malformed",
    )
    raw_hash_fields = (
        "subject_stdout_sha256", "subject_stderr_sha256", "prediction_sha256",
        "patch_sha256",
    )
    evaluator_hash_fields = (
        "evaluator_stdout_sha256", "evaluator_stderr_sha256", "report_sha256",
        "results_sha256",
    )
    _require(
        all(value is None or _sha256(value) for value in (
            *(execution[field] for field in raw_hash_fields),
            *(evaluator[field] for field in evaluator_hash_fields),
        ))
        and (
            started and execution["status"] != "durable_evidence_incomplete"
            and all(_sha256(execution[field]) for field in ("subject_stdout_sha256", "subject_stderr_sha256"))
            or (not started or execution["status"] == "durable_evidence_incomplete")
            and all(execution[field] is None for field in raw_hash_fields)
        ),
        "raw execution evidence hashes are malformed",
    )
    _require(
        evaluator["invocation_started"] is (evaluator["disposition"] != "not_run")
        and (
            evaluator["invocation_started"]
            and (
                all(_sha256(evaluator[field]) for field in evaluator_hash_fields)
                and _sha256(execution["prediction_sha256"])
                and _sha256(execution["patch_sha256"])
                or execution["status"] == "durable_evidence_incomplete"
                and all(evaluator[field] is None for field in evaluator_hash_fields)
                and execution["prediction_sha256"] is None
                and execution["patch_sha256"] is None
            )
            or not evaluator["invocation_started"]
            and all(evaluator[field] is None for field in evaluator_hash_fields)
            and execution["prediction_sha256"] is None
            and execution["patch_sha256"] is None
        ),
        "evaluator outcome or raw evidence lacks a durable invocation",
    )
    _require(
        execution["cleanup_receipt_sha256"] is None
        or _sha256(execution["cleanup_receipt_sha256"]),
        "cleanup receipt binding is malformed",
    )
    if execution["status"] == "returned":
        classification = dispositions[evaluator["disposition"]]
        _require(classification is not None, "returned execution lacks an evaluator disposition")
    else:
        classification = execution["status"]
        _require(
            evaluator["disposition"]
            == ("incomplete" if evaluator["invocation_started"] else "not_run"),
            "non-returned execution evaluator provenance is inconsistent",
        )
    completeness = measurement["record_completeness"]
    work = [measurement[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)]
    if completeness == "complete":
        _require(
            started
            and all(type(measurement[field]) is int and measurement[field] >= 0 for field in INTEGER_WORK_FIELDS)
            and type(measurement["wall_seconds"]) is float
            and math.isfinite(measurement["wall_seconds"])
            and measurement["wall_seconds"] >= 0.0,
            "measurement receipt complete work is malformed",
        )
    else:
        _require(completeness == "absent" and all(value is None for value in work), "measurement receipt completeness is malformed")
    record = {
        "cell_id": cell_id,
        "termination": classification,
        "timed_out": classification == "trajectory_timeout",
        "evaluator_anomalies": deepcopy(evaluator["anomaly_codes"]),
        **{field: measurement[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)},
    }
    return _build_terminal_receipt(
        contract,
        cell_id=cell_id,
        attempt=attempt,
        effective_task_commitment_sha256=effective_task_commitment_sha256,
        subject_invocation_started=started,
        command_sha256=command,
        classification=classification,
        execution_artifact=execution,
        evaluator_artifact=evaluator,
        measurement_artifact=measurement,
        analysis_record=record,
    )


def build_terminal_receipt_from_artifacts(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Reject loose artifacts; use the ledger-bound artifact-root exporter."""

    raise ExperimentConfigurationError(
        "artifact provenance requires the initialized ledger-bound artifact root exporter"
    )


def _effective_private_task(
    contract: dict[str, Any], private_pool: dict[str, Any], commitment: str
) -> dict[str, Any]:
    for task in [*private_pool["primaries"], *private_pool["alternates"]]:
        if digest(task) == commitment:
            return task
    raise ExperimentConfigurationError("effective task commitment is absent from private pool")


def build_terminal_receipt_from_artifact_root(
    contract: dict[str, Any], private_pool: dict[str, Any], ledger_path: Path,
    execution_root: Path, *, cell_id: str, attempt: int,
) -> dict[str, Any]:
    """Export one result only from initialized, ledger-owned artifact provenance."""

    validate_private_pool_binding(private_pool, contract)
    root = _execution_storage_root(execution_root)
    _require(root.resolve() == execution_root.resolve(), "artifact root differs from execution authority root")
    events = read_ledger(ledger_path, contract)
    attempt_started = next(
        (
            event["payload"] for event in events
            if event["event_type"] == "attempt_started"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
        ),
        None,
    )
    _require(attempt_started is not None, "artifact export lacks a frozen attempt ledger event")
    started = next(
        (
            event["payload"] for event in events
            if event["event_type"] == "subject_invocation_started"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
        ),
        None,
    )
    artifact_root = root / "artifacts" / cell_id / f"attempt-{attempt}"
    commitment = (
        started["effective_task_commitment_sha256"]
        if started is not None
        else attempt_started["effective_task_commitment_sha256"]
    )
    receipt = _build_terminal_receipt_from_artifacts(
        contract, cell_id=cell_id, attempt=attempt,
        effective_task_commitment_sha256=commitment,
        execution_receipt_path=artifact_root / "execution.json",
        evaluator_receipt_path=artifact_root / "evaluator.json",
        measurement_receipt_path=artifact_root / "measurement.json",
    )
    execution = receipt["execution_artifact"]
    evaluator = receipt["evaluator_artifact"]
    task = _effective_private_task(
        contract, private_pool, commitment
    )
    if started is None:
        _require(
            execution["subject_invocation_started"] is False
            and execution["command_sha256"] is None
            and execution["ownership_token_sha256"] is None
            and execution["process_identity_sha256"] is None
            and execution["container_identity_sha256"] is None,
            "pre-launch artifact falsely claims a frozen launch identity",
        )
    else:
        _require(
            execution["command_sha256"] == started["command_sha256"]
            and execution["ownership_token_sha256"] == started["ownership_token_sha256"]
            and execution["process_identity_sha256"] == started["process_identity_sha256"]
            and execution["container_identity_sha256"]
            == digest({"resolved_image": task["resolved_image"]}),
            "execution artifact differs from frozen launch command, ownership, process, or container image",
        )
    evaluator_start = next(
        (
            event["payload"] for event in events
            if event["event_type"] == "evaluator_invocation_started"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
        ),
        None,
    )
    if evaluator_start is None:
        _require(not evaluator["invocation_started"], "evaluator artifact invents an invocation")
    else:
        _require(
            evaluator["invocation_started"]
            and evaluator["evaluator_command_sha256"] == evaluator_start["evaluator_command_sha256"]
            and evaluator["ownership_token_sha256"] == evaluator_start["ownership_token_sha256"]
            and evaluator["process_identity_sha256"] == evaluator_start["process_identity_sha256"]
            and evaluator["container_identity_sha256"] == evaluator_start["container_identity_sha256"],
            "evaluator artifact differs from durable evaluator ownership",
        )
    raw_root = artifact_root / "raw"
    evidence_paths = {
        "subject_stdout_sha256": raw_root / "codex.jsonl",
        "subject_stderr_sha256": raw_root / "codex.stderr",
        "prediction_sha256": raw_root / "prediction.json",
        "patch_sha256": raw_root / "patch.diff",
        "evaluator_stdout_sha256": raw_root / "evaluator.stdout",
        "evaluator_stderr_sha256": raw_root / "evaluator.stderr",
        "report_sha256": raw_root / "evaluator-report.json",
        "results_sha256": raw_root / "evaluator-results.json",
    }
    for field, path in evidence_paths.items():
        artifact = execution if field in {
            "subject_stdout_sha256", "subject_stderr_sha256", "prediction_sha256", "patch_sha256"
        } else receipt["evaluator_artifact"]
        expected = artifact[field]
        if expected is None:
            _require(not path.exists(), f"unbound raw evidence file exists: {path.name}")
            continue
        _require_private_artifact_path(path)
        _require(
            hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            f"raw evidence hash differs: {path.name}",
        )
    cleanup_path = artifact_root / "cleanup.json"
    cleanup_sha = execution["cleanup_receipt_sha256"]
    if cleanup_sha is None:
        _require(not cleanup_path.exists(), "unbound cleanup receipt exists")
    else:
        cleanup, _ = _load_self_hashed_artifact(
            cleanup_path,
            schema_name="engineering-scope-guard.reasoning-effort-v2-cleanup",
            keys={
                "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
                "cell_id", "attempt", "effective_task_commitment_sha256",
                "status", "docker_ownership_receipt_sha256", "receipt_sha256",
            },
            label="cleanup receipt",
        )
        _validate_artifact_binding(
            cleanup, contract, cell_id=cell_id, attempt=attempt,
            effective_task_commitment_sha256=commitment, label="cleanup receipt",
        )
        _require(
            cleanup["receipt_sha256"] == cleanup_sha
            and cleanup["status"]
            == ("failed" if execution["status"] == "isolation_contract_violation" else "pass"),
            "cleanup receipt status or binding differs",
        )
        docker_sha = cleanup["docker_ownership_receipt_sha256"]
        _require(docker_sha is None or _sha256(docker_sha), "Docker ownership binding is malformed")
        docker_path = artifact_root / "docker-ownership.json"
        if docker_sha is None:
            _require(not docker_path.exists(), "unbound Docker ownership receipt exists")
        else:
            docker_value, _ = _canonical_json_file(docker_path, "Docker ownership receipt")
            docker_keys = {
                "schema_name", "schema_version", "contract_sha256", "cell_id", "attempt",
                "resolved_image", "materialization_container_id",
                "prelaunch_ownership_token_sha256", "baseline_container_ids",
                "create_event_container_ids", "event_window_start_ns", "event_window_end_ns",
                "attribution_mode", "ownership_marker_sha256", "injection_sha256",
                "injection_relative_path", "evaluator_dataset_sha256",
                "evaluator_dataset_relative_path", "source_row_identity_sha256",
                "lifecycle_events", "final_observations",
                "receipt_sha256",
            }
            _require(
                isinstance(docker_value, dict)
                and set(docker_value) == docker_keys
                and docker_value["schema_name"]
                == "engineering-scope-guard.reasoning-effort-v2-docker-ownership"
                and docker_value["schema_version"] == SCHEMA_VERSION
                and _self_hash(docker_value, "receipt_sha256")
                and docker_value["receipt_sha256"] == docker_sha
                and docker_value.get("contract_sha256") == contract["contract_sha256"]
                and docker_value.get("cell_id") == cell_id
                and docker_value.get("attempt") == attempt
                and docker_value.get("resolved_image") == task["resolved_image"]
                and isinstance(docker_value.get("baseline_container_ids"), list)
                and isinstance(docker_value.get("create_event_container_ids"), list)
                and docker_value["baseline_container_ids"]
                == sorted(set(docker_value["baseline_container_ids"]))
                and docker_value["create_event_container_ids"]
                == sorted(set(docker_value["create_event_container_ids"]))
                and all(
                    isinstance(value, str) and bool(value)
                    for value in [
                        *docker_value["baseline_container_ids"],
                        *docker_value["create_event_container_ids"],
                    ]
                )
                and not set(docker_value["baseline_container_ids"])
                .intersection(docker_value["create_event_container_ids"])
                and isinstance(docker_value.get("final_observations"), list)
                and isinstance(docker_value.get("lifecycle_events"), list)
                and all(
                    isinstance(item, dict)
                    and item.get("running") is False
                    and isinstance(item.get("id"), str)
                    and isinstance(item.get("labels"), dict)
                    for item in docker_value["final_observations"]
                ),
                "Docker ownership receipt is malformed or nonterminal",
            )
            baseline_ids = set(docker_value["baseline_container_ids"])
            created_ids = set(docker_value["create_event_container_ids"])
            marker = docker_value["ownership_marker_sha256"]
            window_start = docker_value["event_window_start_ns"]
            window_end = docker_value["event_window_end_ns"]
            observations_by_id = {
                item["id"]: item for item in docker_value["final_observations"]
            }
            lifecycle = docker_value["lifecycle_events"]
            materialization_id = docker_value["materialization_container_id"]
            prelaunch_ownership = docker_value["prelaunch_ownership_token_sha256"]
            expected_observed_ids = created_ids | (
                {materialization_id} if isinstance(materialization_id, str) else set()
            )
            _require(
                set(observations_by_id) == expected_observed_ids,
                "Docker ownership final observations differ from attributed IDs",
            )
            if evaluator_start is None:
                _require(
                    baseline_ids == set()
                    and created_ids == set()
                    and window_start is None
                    and window_end is None
                    and marker is None
                    and docker_value["attribution_mode"] is None
                    and docker_value["injection_sha256"] is None
                    and docker_value["injection_relative_path"] is None
                    and docker_value["evaluator_dataset_sha256"] is None
                    and docker_value["evaluator_dataset_relative_path"] is None
                    and docker_value["source_row_identity_sha256"] is None
                    and lifecycle == [],
                    "Docker ownership invents an evaluator attribution window",
                )
            else:
                _require(
                    docker_value["attribution_mode"]
                    == "python_sitecustomize_docker_sdk_label_and_prune_suppression"
                    and _sha256(marker)
                    and marker == evaluator_start["ownership_token_sha256"]
                    and _sha256(docker_value["injection_sha256"])
                    and docker_value["injection_relative_path"]
                    == (
                        f"attempts/{cell_id}/attempt-{attempt}/"
                        "evaluator-python-injection/sitecustomize.py"
                    )
                    and _sha256(docker_value["evaluator_dataset_sha256"])
                    and _sha256(docker_value["source_row_identity_sha256"])
                    and docker_value["source_row_identity_sha256"] == digest({
                        "instance_id": task["task_id"],
                        "language": task["language"],
                        "repo": task["repository"],
                        "base_commit": task["base_commit"],
                        "docker_image": task["docker_image"],
                        "problem_statement_sha256": task["problem_statement_sha256"],
                    })
                    and docker_value["evaluator_dataset_relative_path"]
                    == (
                        f"attempts/{cell_id}/attempt-{attempt}/"
                        "evaluator-dataset/task.jsonl"
                    )
                    and type(window_start) is int
                    and type(window_end) is int
                    and 0 < window_start <= window_end
                    and evaluator_start["container_identity_sha256"]
                    == digest({
                        "resolved_image": task["resolved_image"],
                        "baseline_container_ids": sorted(baseline_ids),
                        "injection_mechanism": (
                            "python_sitecustomize_docker_sdk_label_and_prune_suppression"
                        ),
                        "injection_sha256": docker_value["injection_sha256"],
                        "evaluator_dataset_sha256": docker_value["evaluator_dataset_sha256"],
                        "source_row_identity_sha256": docker_value["source_row_identity_sha256"],
                    })
                    and all(
                        observations_by_id[container_id]["labels"].get(
                            "engineering-scope-guard.ownership"
                        ) == marker
                        for container_id in created_ids
                    ),
                    "Docker ownership attribution does not match the durable evaluator start",
                )
                injection_path = root / docker_value["injection_relative_path"]
                _require_private_artifact_path(injection_path)
                _require(
                    hashlib.sha256(injection_path.read_bytes()).hexdigest()
                    == docker_value["injection_sha256"],
                    "Docker SDK injection bytes differ from their terminal binding",
                )
                evaluator_dataset_path = root / docker_value[
                    "evaluator_dataset_relative_path"
                ]
                _require_private_artifact_path(evaluator_dataset_path)
                _require(
                    hashlib.sha256(evaluator_dataset_path.read_bytes()).hexdigest()
                    == docker_value["evaluator_dataset_sha256"],
                    "frozen evaluator dataset bytes differ from their terminal binding",
                )
                _require(
                    lifecycle == sorted(
                        lifecycle,
                        key=lambda item: (
                            item.get("time_nano"), item.get("container_id"), item.get("action")
                        ),
                    )
                    and all(
                        isinstance(event, dict)
                        and set(event) == {
                            "action", "container_id", "time_nano", "image", "name",
                            "ownership_marker_sha256",
                        }
                        and event["action"] in {"create", "destroy"}
                        and isinstance(event["container_id"], str)
                        and type(event["time_nano"]) is int
                        and window_start <= event["time_nano"] <= window_end
                        for event in lifecycle
                    ),
                    "Docker lifecycle event projection is malformed",
                )
                for container_id in created_ids:
                    owned_events = [
                        event for event in lifecycle
                        if event["container_id"] == container_id
                    ]
                    creates = [event for event in owned_events if event["action"] == "create"]
                    destroys = [event for event in owned_events if event["action"] == "destroy"]
                    observation = observations_by_id[container_id]
                    _require(
                        len(creates) == 1
                        and len(destroys) <= 1
                        and all(
                            event["ownership_marker_sha256"] == marker
                            for event in owned_events
                        )
                        and (
                            (observation.get("removed") is True and len(destroys) == 1)
                            or (observation.get("removed") is not True and len(destroys) == 0)
                        )
                        and (
                            not destroys
                            or destroys[0]["time_nano"] >= creates[0]["time_nano"]
                        ),
                        "Docker create/destroy lifecycle differs from terminal observation",
                    )
                _require(
                    {
                        event["container_id"] for event in lifecycle
                        if event["action"] == "create"
                        and event["ownership_marker_sha256"] == marker
                    } == created_ids,
                    "Docker owned create-event set differs from terminal attribution",
                )
            if isinstance(materialization_id, str):
                _require(
                    _sha256(prelaunch_ownership)
                    and (
                        started is None
                        or prelaunch_ownership == started["ownership_token_sha256"]
                    )
                    and observations_by_id[materialization_id]["labels"].get(
                        "engineering-scope-guard.ownership"
                    ) == prelaunch_ownership,
                    "materialization Docker ownership differs from durable subject start",
                )
    return receipt


def validate_terminal_receipt_artifacts(
    contract: dict[str, Any], private_pool: dict[str, Any], ledger_path: Path,
    execution_root: Path, receipt: dict[str, Any],
) -> None:
    """Re-open the deterministic artifact set and repeat every launch binding."""

    rebuilt = build_terminal_receipt_from_artifact_root(
        contract, private_pool, ledger_path, execution_root,
        cell_id=receipt["cell_id"], attempt=receipt["attempt"],
    )
    _require(
        canonical_bytes(rebuilt) == canonical_bytes(receipt),
        "terminal receipt differs from re-opened artifact provenance",
    )


def _receipt_path(receipt_root: Path, cell_id: str, attempt: int) -> Path:
    _require(cell_id.replace("-", "").isalnum(), "cell id is unsafe for receipt storage")
    _require(type(attempt) is int and attempt in (1, 2), "receipt attempt is invalid")
    return receipt_root / cell_id / f"attempt-{attempt}.json"


def persist_terminal_receipt(receipt_root: Path, contract: dict[str, Any], receipt: dict[str, Any]) -> Path:
    """Atomically persist once; exact idempotent readback is the only overwrite case."""

    validate_terminal_receipt(contract, receipt)
    storage_root = _execution_storage_root(receipt_root)
    _require(receipt_root.resolve().is_relative_to(storage_root.resolve()), "receipt root escapes execution storage")
    path = _receipt_path(receipt_root, receipt["cell_id"], receipt["attempt"])
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with _lock(path.with_suffix(path.suffix + ".lock")):
        if path.exists():
            try:
                raw = path.read_bytes()
                existing = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ExperimentConfigurationError("persisted terminal receipt is malformed") from error
            _require(
                raw
                == (json.dumps(existing, sort_keys=True, separators=(",", ":")) + "\n").encode(),
                "persisted terminal receipt is not canonical JSON",
            )
            _require(
                canonical_bytes(existing) == canonical_bytes(receipt),
                "terminal receipt already differs",
            )
            return path
        _atomic_json(path, receipt)
        path.chmod(0o600)
    return path


def _load_receipt(receipt_root: Path, contract: dict[str, Any], cell_id: str, attempt: int) -> dict[str, Any] | None:
    path = _receipt_path(receipt_root, cell_id, attempt)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError("persisted terminal receipt is malformed") from error
    _require(
        raw
        == (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        "persisted terminal receipt is not canonical JSON",
    )
    validate_terminal_receipt(contract, receipt)
    return receipt


def reconcile_attempt(
    ledger_path: Path, checkpoint_path: Path, receipt_root: Path,
    contract: dict[str, Any], private_pool: dict[str, Any], live_seal: dict[str, Any],
    *, cell_id: str, attempt: int
) -> dict[str, Any]:
    """Reconcile crashes without ever issuing a second subject start."""

    validate_live_seal(contract, private_pool, live_seal)
    events = read_ledger(ledger_path, contract)
    matching = [
        event for event in events
        if event["payload"].get("cell_id") == cell_id
        and event["payload"].get("attempt") == attempt
    ]
    types = [event["event_type"] for event in matching]
    _require("attempt_started" in types, "attempt was not durably started")
    started = "subject_invocation_started" in types
    receipt = _load_receipt(receipt_root, contract, cell_id, attempt)
    finished = next(
        (event for event in matching if event["event_type"] == "attempt_finished"), None
    )
    if finished is not None:
        _require(receipt is not None, "finished attempt lost its durable terminal receipt")
        _require(
            finished["payload"]["evidence_sha256"] == receipt["terminal_receipt_sha256"],
            "finished attempt receipt rehash differs from the ledger",
        )
        return {"action": "already_reconciled", "terminal_receipt_sha256": receipt["terminal_receipt_sha256"]}
    if receipt is None:
        return {"action": "await_terminal_receipt" if started else "start_subject"}
    _require(
        receipt["subject_invocation_started"] is started,
        "terminal receipt disagrees with the durable subject-start boundary",
    )
    if started:
        start_event = next(
            event for event in matching if event["event_type"] == "subject_invocation_started"
        )
        launch = start_event["payload"]
        execution = receipt["execution_artifact"]
        _require(
            execution["command_sha256"] == launch["command_sha256"]
            and execution["ownership_token_sha256"] == launch["ownership_token_sha256"]
            and execution["process_identity_sha256"] == launch["process_identity_sha256"]
            and receipt["effective_task_commitment_sha256"]
            == launch["effective_task_commitment_sha256"],
            "terminal artifact provenance differs from durable launch ownership",
        )
    finish_payload = {
        "cell_id": cell_id,
        "attempt": attempt,
        "classification": receipt["classification"],
        "evidence_sha256": receipt["terminal_receipt_sha256"],
        "effective_task_commitment_sha256": receipt["effective_task_commitment_sha256"],
        "subject_invocation_started": started,
    }
    append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool,
        "attempt_finished", finish_payload,
    )
    if receipt["classification"] in EXPERIMENTAL_OUTCOMES:
        append_ledger_event(
            ledger_path, checkpoint_path, contract, live_seal, private_pool,
            "cell_completed",
            {
                "cell_id": cell_id,
                "attempt": attempt,
                "classification": receipt["classification"],
                "evidence_sha256": receipt["terminal_receipt_sha256"],
                "effective_task_commitment_sha256": receipt[
                    "effective_task_commitment_sha256"
                ],
            },
        )
        action = "cell_completed"
    elif receipt["classification"] in {
        *RETRYABLE_INFRASTRUCTURE, *ALTERNATE_ACTIVATION_CLASSES,
    } and attempt == 2:
        append_ledger_event(
            ledger_path, checkpoint_path, contract, live_seal, private_pool,
            "batch_stopped",
            {
                "cell_id": cell_id,
                "attempt": 2,
                "classification": "durable_evidence_incomplete",
                "evidence_sha256": receipt["terminal_receipt_sha256"],
            },
        )
        action = "batch_stopped_attempt_2_exhausted"
    elif receipt["classification"] in RETRYABLE_INFRASTRUCTURE:
        action = "await_attempt_2_authorization"
    elif receipt["classification"] in ALTERNATE_ACTIVATION_CLASSES:
        action = "await_alternate_activation"
    else:
        append_ledger_event(
            ledger_path, checkpoint_path, contract, live_seal, private_pool,
            "batch_stopped",
            {
                "cell_id": cell_id,
                "attempt": attempt,
                "classification": receipt["classification"],
                "evidence_sha256": receipt["terminal_receipt_sha256"],
            },
        )
        action = "batch_stopped"
    return {"action": action, "terminal_receipt_sha256": receipt["terminal_receipt_sha256"]}


def reconcile_orphaned_invocation(
    ledger_path: Path,
    checkpoint_path: Path,
    receipt_root: Path,
    contract: dict[str, Any],
    private_pool: dict[str, Any],
    live_seal: dict[str, Any],
    *,
    cell_id: str,
    attempt: int,
    ownership_receipt_path: Path,
    _phase: str = "subject",
) -> dict[str, Any]:
    """Fail closed after adapter-proven process death; never restart or delete."""

    validate_live_seal(contract, private_pool, live_seal)
    events = read_ledger(ledger_path, contract)
    _require(_phase in {"subject", "evaluator"}, "orphan reconciliation phase is invalid")
    subject_start = next(
        (
            event
            for event in events
            if event["event_type"] == "subject_invocation_started"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
        ),
        None,
    )
    _require(subject_start is not None, "orphan reconciliation lacks a durable subject start")
    target_start = subject_start if _phase == "subject" else next(
        (
            event for event in events
            if event["event_type"] == "evaluator_invocation_started"
            and event["payload"]["cell_id"] == cell_id
            and event["payload"]["attempt"] == attempt
        ),
        None,
    )
    _require(target_start is not None, "orphan reconciliation lacks the durable phase start")
    ownership, _ = _load_self_hashed_artifact(
        Path(ownership_receipt_path),
        schema_name=OWNERSHIP_RECEIPT_SCHEMA,
        keys={
            "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
            "cell_id", "attempt", "command_sha256", "ownership_token_sha256",
            "process_identity_sha256", "container_identity_sha256",
            "container_observations", "status", "receipt_sha256",
        },
        label="ownership receipt",
    )
    payload = subject_start["payload"]
    target_payload = target_start["payload"]
    target_command = (
        target_payload["command_sha256"]
        if _phase == "subject"
        else target_payload["evaluator_command_sha256"]
    )
    container_observations = ownership["container_observations"]
    _require(
        ownership["contract_sha256"] == contract["contract_sha256"]
        and ownership["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and ownership["cell_id"] == cell_id
        and ownership["attempt"] == attempt
        and ownership["command_sha256"] == target_command
        and ownership["ownership_token_sha256"] == target_payload["ownership_token_sha256"]
        and ownership["process_identity_sha256"] == target_payload["process_identity_sha256"]
        and isinstance(container_observations, list)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("running") is False
            for item in container_observations
        )
        and ownership["container_identity_sha256"] == digest(container_observations)
        and ownership["status"] == "not_running",
        "ownership receipt does not prove the frozen invocation is no longer running",
    )
    existing = _load_receipt(receipt_root, contract, cell_id, attempt)
    if existing is None:
        record = {
            "cell_id": cell_id,
            "termination": "durable_evidence_incomplete",
            "timed_out": False,
            "evaluator_anomalies": [f"orphaned_{_phase}_not_running"],
            **{field: None for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)},
        }
        common = {
            "schema_version": SCHEMA_VERSION,
            "contract_sha256": contract["contract_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "cell_id": cell_id,
            "attempt": attempt,
            "effective_task_commitment_sha256": payload["effective_task_commitment_sha256"],
        }
        execution = _seal_artifact({
            **common, "schema_name": EXECUTION_ARTIFACT_SCHEMA,
            "subject_invocation_started": True,
            "command_sha256": payload["command_sha256"],
            "status": "durable_evidence_incomplete", "timed_out": False,
            "subject_exit_code": None,
            "ownership_token_sha256": payload["ownership_token_sha256"],
            "process_identity_sha256": payload["process_identity_sha256"],
            "container_identity_sha256": digest({
                "resolved_image": _effective_private_task(
                    contract, private_pool, payload["effective_task_commitment_sha256"]
                )["resolved_image"]
            }),
            "subject_stdout_sha256": None, "subject_stderr_sha256": None,
            "prediction_sha256": None, "patch_sha256": None,
            "cleanup_receipt_sha256": None,
        })
        evaluator = _seal_artifact({
            **common, "schema_name": EVALUATOR_ARTIFACT_SCHEMA,
            "evaluator_identity": contract["source"]["evaluator_identity"],
            "disposition": "incomplete" if _phase == "evaluator" else "not_run",
            "anomaly_codes": [f"orphaned_{_phase}_not_running"],
            "evaluator_stdout_sha256": None, "evaluator_stderr_sha256": None,
            "report_sha256": None, "results_sha256": None,
            "invocation_started": _phase == "evaluator",
            "evaluator_command_sha256": target_command if _phase == "evaluator" else None,
            "ownership_token_sha256": target_payload["ownership_token_sha256"] if _phase == "evaluator" else None,
            "process_identity_sha256": target_payload["process_identity_sha256"] if _phase == "evaluator" else None,
            "container_identity_sha256": target_payload["container_identity_sha256"] if _phase == "evaluator" else None,
        })
        measurement = _seal_artifact({
            **common, "schema_name": MEASUREMENT_ARTIFACT_SCHEMA,
            "record_completeness": "absent",
            **{field: None for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)},
        })
        receipt = _build_terminal_receipt(
            contract,
            cell_id=cell_id,
            attempt=attempt,
            effective_task_commitment_sha256=payload["effective_task_commitment_sha256"],
            subject_invocation_started=True,
            command_sha256=payload["command_sha256"],
            classification="durable_evidence_incomplete",
            execution_artifact=execution,
            evaluator_artifact=evaluator,
            measurement_artifact=measurement,
            analysis_record=record,
        )
        persist_terminal_receipt(receipt_root, contract, receipt)
    result = reconcile_attempt(
        ledger_path, checkpoint_path, receipt_root, contract, private_pool, live_seal,
        cell_id=cell_id, attempt=attempt,
    )
    _require(
        result["action"] in {"batch_stopped", "already_reconciled"},
        "orphan reconciliation did not stop the batch",
    )
    return {**result, "classification": "durable_evidence_incomplete"}


def reconcile_orphaned_evaluator(
    ledger_path: Path, checkpoint_path: Path, receipt_root: Path,
    contract: dict[str, Any], private_pool: dict[str, Any], live_seal: dict[str, Any],
    *, cell_id: str, attempt: int, ownership_receipt_path: Path,
) -> dict[str, Any]:
    """Reconcile only the evaluator ownership event after proven process death."""

    return reconcile_orphaned_invocation(
        ledger_path, checkpoint_path, receipt_root, contract, private_pool, live_seal,
        cell_id=cell_id, attempt=attempt,
        ownership_receipt_path=ownership_receipt_path, _phase="evaluator",
    )


def _finished_receipt_entries(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "cell_id": event["payload"]["cell_id"],
            "attempt": event["payload"]["attempt"],
            "terminal_receipt_sha256": event["payload"]["evidence_sha256"],
        }
        for event in events
        if event["event_type"] == "attempt_finished"
    ]


def record_stage_1_audit(
    ledger_path: Path, checkpoint_path: Path, receipt_root: Path,
    contract: dict[str, Any], private_pool: dict[str, Any], live_seal: dict[str, Any],
    *, execution_root: Path, runtime_revalidation_receipt_path: Path,
    source_revalidation_receipt_path: Path,
) -> dict[str, Any]:
    """Record the required content-free Stage-1 pass/fail transition."""

    storage_root = _execution_storage_root(execution_root)
    _require(storage_root.resolve() == execution_root.resolve(), "Stage-1 execution root is not authoritative")
    _require(
        _require_private_artifact_path(runtime_revalidation_receipt_path).resolve() == storage_root.resolve()
        and _require_private_artifact_path(source_revalidation_receipt_path).resolve() == storage_root.resolve(),
        "Stage-1 identity receipts lack execution-root provenance",
    )
    runtime_receipt, _ = _load_self_hashed_artifact(
        runtime_revalidation_receipt_path,
        schema_name=RUNTIME_REVALIDATION_SCHEMA,
        keys={
            "schema_name", "schema_version", "contract_sha256", "live_seal_sha256",
            "runtime_identity", "status", "receipt_sha256",
        },
        label="runtime revalidation receipt",
    )
    source_receipt, _ = _load_self_hashed_artifact(
        source_revalidation_receipt_path,
        schema_name=SOURCE_REVALIDATION_SCHEMA,
        keys={
            "schema_name", "schema_version", "contract_sha256", "live_seal_sha256",
            "source_identity", "evaluator_identity", "image_pool_identity", "status",
            "receipt_sha256",
        },
        label="source revalidation receipt",
    )
    runtime_identity_stable = (
        runtime_receipt["status"] == "pass"
        and runtime_receipt["contract_sha256"] == contract["contract_sha256"]
        and runtime_receipt["live_seal_sha256"] == live_seal["live_seal_sha256"]
        and runtime_receipt["runtime_identity"] == contract["runtime"]["runtime_identity"]
    )
    source_identity_stable = (
        source_receipt["status"] == "pass"
        and source_receipt["contract_sha256"] == contract["contract_sha256"]
        and source_receipt["live_seal_sha256"] == live_seal["live_seal_sha256"]
        and source_receipt["source_identity"] == contract["source"]["source_identity"]
        and source_receipt["evaluator_identity"] == contract["source"]["evaluator_identity"]
        and source_receipt["image_pool_identity"] == contract["source"]["image_pool_identity"]
    )
    events = read_ledger(ledger_path, contract)
    state = replay_attempt_state(contract, _semantic(events))
    _require(state["completed_cells"] == 4, "Stage-1 audit requires exactly four retained cells")
    completed_ids = [cell["cell_id"] for cell in contract["schedule"]["cells"][:4]]
    completed_events = [
        event for event in events
        if event["event_type"] == "cell_completed"
        and event["payload"]["cell_id"] in completed_ids
    ]
    entries = _finished_receipt_entries(events)
    final_entries = [
        next(
            entry for entry in entries
            if entry["cell_id"] == event["payload"]["cell_id"]
            and entry["attempt"] == event["payload"]["attempt"]
        )
        for event in completed_events
    ]
    receipt_set_sha256 = digest(final_entries)
    if not state["stage_1_boundary_reached"]:
        append_ledger_event(
            ledger_path, checkpoint_path, contract, live_seal, private_pool,
            "stage_1_boundary_reached",
            {
                "completed_cell_count": 4,
                "completed_cell_ids": completed_ids,
                "receipt_set_sha256": receipt_set_sha256,
            },
        )
        events = read_ledger(ledger_path, contract)
        state = replay_attempt_state(contract, _semantic(events))
    _require(state["stage_1_audit_status"] is None, "Stage-1 audit is already terminal")
    hashes_valid = True
    for entry in final_entries:
        try:
            persisted = _load_receipt(
                receipt_root, contract, entry["cell_id"], entry["attempt"]
            )
            hashes_valid = (
                hashes_valid
                and persisted is not None
                and persisted["terminal_receipt_sha256"]
                == entry["terminal_receipt_sha256"]
            )
            if persisted is not None:
                validate_terminal_receipt_artifacts(
                    contract, private_pool, ledger_path, execution_root, persisted
                )
        except (OSError, ExperimentConfigurationError):
            hashes_valid = False
    criteria = {
        "exact_four_retained_cells": len(completed_events) == 4,
        "terminal_receipts_complete": len(final_entries) == 4,
        "receipt_hashes_valid": hashes_valid,
        "ledger_chain_valid": True,
        "no_batch_stop": state["batch_stop_classification"] is None,
        "runtime_identity_stable": runtime_identity_stable,
        "source_identity_stable": source_identity_stable,
    }
    _exact(criteria, set(STAGE_1_AUDIT_CRITERIA), "Stage-1 criteria implementation drifted")
    status = "pass" if all(criteria.values()) else "fail"
    audit = {
        "schema_version": 1,
        "status": status,
        "criteria": criteria,
        "completed_cell_count": 4,
        "completed_cell_ids": completed_ids,
        "receipt_set_sha256": receipt_set_sha256,
        "outcome_fields_inspected": False,
        "outcome_values_emitted": False,
    }
    append_ledger_event(
        ledger_path, checkpoint_path, contract, live_seal, private_pool,
        f"stage_1_audit_{'passed' if status == 'pass' else 'failed'}",
        {"audit": audit, "audit_sha256": digest(audit)},
    )
    return audit


def terminal_receipt_projection(receipt: dict[str, Any]) -> dict[str, Any]:
    """Project a validated terminal receipt into one exact analysis record."""

    record = deepcopy(receipt["analysis_record"])
    return {
        **record,
        "attempt": receipt["attempt"],
        "effective_task_commitment_sha256": receipt["effective_task_commitment_sha256"],
        "terminal_receipt_sha256": receipt["terminal_receipt_sha256"],
        "evaluator_receipt_sha256": receipt["evaluator_receipt_sha256"],
    }


def export_analysis_terminal_envelope(
    contract: dict[str, Any], private_pool: dict[str, Any], ledger_path: Path,
    receipt_root: Path, live_seal: dict[str, Any]
) -> dict[str, Any]:
    """Export the only public-safe, ledger-derived terminal analysis input."""

    validate_live_seal(contract, private_pool, live_seal)
    events = read_ledger(ledger_path, contract)
    state = replay_attempt_state(contract, _semantic(events))
    complete = state["completed_cells"] == len(contract["schedule"]["cells"])
    terminated = state["batch_stop_classification"] is not None
    _require(complete or terminated, "analysis envelope requires complete or invalid-terminal state")
    _require(not complete or state["stage_1_audit_status"] == "pass", "complete run lacks Stage-1 pass")
    receipt_entries = []
    receipt_projections = []
    receipts: dict[tuple[str, int], dict[str, Any]] = {}
    for entry in _finished_receipt_entries(events):
        receipt = _load_receipt(receipt_root, contract, entry["cell_id"], entry["attempt"])
        _require(receipt is not None, "terminal ledger finish lacks its durable receipt")
        _require(
            receipt["terminal_receipt_sha256"] == entry["terminal_receipt_sha256"],
            "terminal receipt rehash differs from ledger evidence",
        )
        receipts[(entry["cell_id"], entry["attempt"])] = receipt
        receipt_projections.append(deepcopy(receipt))
        receipt_entries.append(
            {
                **entry,
                "evaluator_receipt_sha256": receipt["evaluator_receipt_sha256"],
            }
        )
    completed_events = [event for event in events if event["event_type"] == "cell_completed"]
    record_keys = [
        (event["payload"]["cell_id"], event["payload"]["attempt"])
        for event in completed_events
    ]
    if terminated and state["next_cell_id"] is not None:
        terminal = next(
            (
                (entry["cell_id"], entry["attempt"])
                for entry in reversed(receipt_entries)
                if entry["cell_id"] == state["next_cell_id"]
            ),
            None,
        )
        if terminal is not None and terminal not in record_keys:
            record_keys.append(terminal)
    records = [terminal_receipt_projection(receipts[key]) for key in record_keys]
    projection = public_pool_projection(private_pool)
    alternate_by_commitment = {
        item["task_commitment_sha256"]: item["alternate_ordinal"]
        for item in projection["alternate_order_commitments"]
    }
    slots = []
    for slot in range(1, projection["primary_count"] + 1):
        commitment = state["effective_task_commitment_by_slot"][slot]
        ordinal = alternate_by_commitment.get(commitment)
        slots.append(
            {
                "population_slot": slot,
                "task_commitment_sha256": commitment,
                "repository_commitment_sha256": commitment,
                "alternate_activated": ordinal is not None,
                "alternate_ordinal": ordinal,
            }
        )
    body = {
        "schema_name": ANALYSIS_ENVELOPE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "private_pool_sha256": private_pool["private_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "live_seal_sha256": live_seal["live_seal_sha256"],
        "ledger_binding": {
            "schema_name": LEDGER_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "event_count": len(events),
            "head_event_sha256": events[-1]["event_sha256"] if events else None,
        },
        "receipt_set_sha256": digest(receipt_entries),
        "qualification_receipt_sha256": contract["source"]["qualification_receipt_sha256"],
        "evaluator_identity": contract["source"]["evaluator_identity"],
        "image_pool_identity": contract["source"]["image_pool_identity"],
        "repository_commitment_source": (
            "task_commitment_sha256_under_frozen_global_repository_uniqueness"
        ),
        "protocol_valid": complete and not terminated,
        "batch_stop_classification": state["batch_stop_classification"],
        "stage_1_audit_sha256": state["stage_1_audit_sha256"],
        "terminal_status": "complete" if complete and not terminated else "invalid_terminated",
        "subject_start_accounting": {
            "canary_subject_invocation_starts": state[
                "canary_subject_invocation_starts"
            ],
            "experiment_subject_invocation_starts": state[
                "experiment_subject_invocation_starts"
            ],
            "total_subject_invocation_starts": state[
                "total_subject_invocation_starts"
            ],
        },
        "effective_assignments": slots,
        "receipt_projections": receipt_projections,
        "records": records,
    }
    envelope = {**body, "envelope_sha256": digest(body)}
    validate_analysis_terminal_envelope(contract, envelope)
    return envelope
