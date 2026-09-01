"""Provider-free terminal packaging for Evaluator-Stable Reasoning Effort v2.

The packager accepts only already-terminal, validated evidence.  It never runs a
subject or evaluator and never copies private task material into tracked output.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import tempfile
from typing import Any, Mapping

from engineering_scope_guard.evaluator_stable_qualification import (
    public_summary,
    validate_receipt as validate_qualification_receipt,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import canonical_bytes, digest
from engineering_scope_guard.reasoning_effort_v2 import (
    validate_analysis_terminal_envelope,
    validate_contract,
)
from engineering_scope_guard.reasoning_effort_v2_analysis import (
    AnalysisInputError,
    analyze_reasoning_effort_v2,
)
from engineering_scope_guard.reasoning_effort_v2_pre_freeze_terminal import (
    validate_pre_freeze_terminal_receipt,
)


SCHEMA_NAME = "engineering-scope-guard.evaluator-stable-reasoning-effort-terminal"
SCHEMA_VERSION = 1
INSUFFICIENT_DISPOSITION = (
    "TASK/EVALUATOR POPULATION STILL INSUFFICIENT — LIVE EXPERIMENT NOT STARTED"
)
INTEGRITY_STOP_DISPOSITION = "EXPERIMENT INVALID / TERMINATED"
ESG_RR_002_GATE_VERSION = "esg-rr-002-contract-policy-evaluation-v1"

QUALIFICATION_SUMMARY_PATH = Path(
    "experiment/evaluator_stable_reasoning_effort_qualification_summary.json"
)
TERMINAL_RESULT_PATH = Path(
    "experiment/evaluator_stable_reasoning_effort_terminal_result.json"
)
TERMINAL_REPORT_PATH = Path(
    "docs/EVALUATOR_STABLE_REASONING_EFFORT_TERMINAL_REPORT.md"
)
CONTRACT_PATH = Path("experiment/reasoning_effort_v2_contract.json")
TERMINAL_ENVELOPE_PATH = Path(
    "experiment/reasoning_effort_v2_terminal_envelope.json"
)
ANALYSIS_PATH = Path("experiment/reasoning_effort_v2_analysis.json")

COMMON_PATHS = (
    QUALIFICATION_SUMMARY_PATH,
    TERMINAL_RESULT_PATH,
    TERMINAL_REPORT_PATH,
)
EXPERIMENT_PATHS = (CONTRACT_PATH, TERMINAL_ENVELOPE_PATH, ANALYSIS_PATH)
TERMINAL_PATHS = frozenset(
    {"insufficient_population", "pre_subject_integrity_stop", "experiment_terminal"}
)
NEXT_BOUNDARIES = frozenset(
    {"authorize_private_canonical_branch_push", "authorize_second_experiment"}
)
EXPERIMENT_DISPOSITIONS = frozenset(
    {
        "LOW FAVORED",
        "MEDIUM FAVORED",
        "WORK DIFFERENCE WITHOUT ACCEPTANCE EVIDENCE",
        "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED",
        "INCONCLUSIVE",
        "EXPERIMENT INVALID / TERMINATED",
    }
)

_FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "task_id",
        "task",
        "instance_id",
        "repo",
        "repository",
        "image",
        "resolved_image",
        "docker_image",
        "body",
        "problem_statement",
        "task_body",
        "prompt",
        "patch",
        "raw_output",
        "raw_provider_trace",
        "credentials",
        "credential",
        "token",
        "api_key",
        "secret",
        "auth_token",
        "access_token",
        "codex_home",
        "worktree_path",
        "task_text",
        "task_content",
        "task_payload",
        "repo_url",
        "repo_path",
        "repository_url",
        "repository_path",
        "image_ref",
        "image_name",
        "image_path",
        "body_text",
        "prompt_text",
        "prompt_content",
        "prompt_payload",
        "patch_text",
        "patch_content",
        "patch_diff",
        "raw_trace",
        "raw_log",
        "raw_logs",
        "provider_output",
        "provider_response",
        "api_token",
        "password",
        "private_key",
        "client_secret",
    }
)
_FORBIDDEN_VALUE_FRAGMENTS = (
    "/Users/",
    "/home/",
    "/private/tmp/",
    "-----BEGIN PRIVATE KEY-----",
    "ghp_",
    "github_pat_",
)
_CREDENTIAL_KEY_SUFFIXES = (
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_private_key",
)


class TerminalPackageError(ValueError):
    """Raised when terminal evidence is incomplete, inconsistent, or unsafe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TerminalPackageError(message)


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == fields, f"{label} fields drifted")
    return value


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def canonical_artifact_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the one deterministic tracked-JSON representation."""

    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _byte_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_artifact_bytes(value)).hexdigest()


def _public_safety_scan(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _require(isinstance(key, str), f"public artifact key is not text at {path}")
            lowered = key.lower()
            _require(
                lowered not in _FORBIDDEN_EXACT_KEYS
                and not (
                    lowered.endswith(_CREDENTIAL_KEY_SUFFIXES)
                    and not lowered.endswith("_sha256")
                ),
                f"public artifact contains forbidden field {key!r} at {path}",
            )
            if lowered in {"stdout", "stderr", "raw"} or (
                (lowered.endswith("_stdout") or lowered.endswith("_stderr"))
                and not lowered.endswith("_sha256")
            ):
                raise TerminalPackageError(
                    f"public artifact contains raw-output field {key!r} at {path}"
                )
            _public_safety_scan(child, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _public_safety_scan(child, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        components = normalized.split("/")
        lowered = value.lower()
        _require(
            not value.startswith("/")
            and not PureWindowsPath(value).is_absolute()
            and not lowered.startswith("file:")
            and value != "~"
            and not value.startswith(("~/", "~\\"))
            and ".." not in components
            and ".local" not in components
            and not any(fragment in value for fragment in _FORBIDDEN_VALUE_FRAGMENTS),
            f"public artifact contains a private path or credential-like value at {path}",
        )


def _safe_runtime_projection(receipt: dict[str, Any]) -> dict[str, Any]:
    runtime = receipt.get("runtime_observation")
    _require(isinstance(runtime, dict), "qualification runtime observation is absent")
    codex_version = runtime.get("codex_version")
    model = runtime.get("model")
    efforts = runtime.get("supported_reasoning_efforts")
    _require(
        isinstance(codex_version, str)
        and bool(codex_version)
        and isinstance(model, str)
        and bool(model)
        and isinstance(efforts, list)
        and all(isinstance(item, str) and bool(item) for item in efforts)
        and {"low", "medium"} <= set(efforts),
        "qualification runtime cannot safely prove LOW and MEDIUM availability",
    )
    return {
        "codex_version": codex_version,
        "model": model,
        "supported_reasoning_efforts": list(efforts),
    }


def _qualification_projection(receipt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        validate_qualification_receipt(receipt)
    except ExperimentConfigurationError as error:
        raise TerminalPackageError(f"qualification receipt is invalid: {error}") from error
    _require(
        receipt["status"] in {"insufficient", "stable_pool_ready"},
        "terminal packaging rejects an in-progress qualification receipt",
    )
    summary = public_summary(receipt)
    _public_safety_scan(summary)
    projection = {
        "summary_sha256": _byte_sha256(summary),
        "private_receipt_state_sha256": receipt["state_sha256"],
        "status": summary["status"],
        "attempted_candidates": summary["attempted_candidates"],
        "validation_failures": summary["flaky_validation_failures"],
        "gold_failures": summary["gold_patch_evaluation_failures"],
        "infrastructure_failures": (
            summary["build_environment_failures"]
            + summary["evaluator_runtime_failures"]
            + summary["infrastructure_timeouts"]
        ),
        "qualified_independent_clusters": summary[
            "qualified_independent_clusters"
        ],
        "primary_cluster_count": summary["primary_cluster_count"],
        "alternate_cluster_count": summary["alternate_cluster_count"],
        "minimum_gate_passed": summary["minimum_gate_passed"],
        "subject_invocation_starts": summary["subject_invocation_starts"],
    }
    return summary, projection


def _empty_esg_gate(
    basis: str = "no experiment completed because the stable-population gate failed",
) -> dict[str, Any]:
    return {
        "criteria_version": ESG_RR_002_GATE_VERSION,
        "status": "not_applicable",
        "policy_sha256": None,
        "criteria": None,
        "candidate_justified": False,
        "decision": "not_applicable",
        "basis": basis,
    }


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _derive_esg_gate(
    analysis: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    population = analysis["analysis_population"]
    integrity = analysis["terminal_integrity"]
    paired = analysis["acceptance"]["paired_repository_clusters"]
    interval = paired.get("repository_cluster_bootstrap_95_interval") if paired else None
    interval_informative = bool(
        isinstance(interval, dict)
        and _finite_number(interval.get("lower"))
        and _finite_number(interval.get("upper"))
        and interval["lower"] <= interval["upper"]
        and interval["upper"] - interval["lower"]
        <= policy["maximum_finite_primary_interval_width"]
    )
    complete_clusters = paired.get("independent_repository_clusters", 0) if paired else 0
    anomaly = analysis["falsification"]["evaluator_anomalies"]
    trajectory = analysis.get("attempt_trajectory")
    expected_usefulness = None
    if isinstance(trajectory, dict) and paired is not None:
        retry_work_payload = {
            "final_record_work": analysis["work"],
            "all_attempt_work": trajectory["work"],
        }
        retry_falsification_payload = {
            "final_record_falsification": analysis["falsification"],
            "attempt_transitions": trajectory[
                "attempt_1_to_attempt_2_transitions"
            ],
            "attempt_diagnostics": trajectory["diagnostics_by_arm"],
        }
        expected_usefulness = {
            "primary_acceptance_point_estimate": paired["medium_minus_low"],
            "primary_acceptance_interval": interval,
            "retry_inclusive_work_result": {
                "sha256": digest(retry_work_payload),
                "attempts_by_arm": {
                    arm: trajectory["attempt_counts_by_arm"][arm]["attempts"]
                    for arm in ("low", "medium")
                },
            },
            "retry_inclusive_falsification_result": {
                "sha256": digest(retry_falsification_payload),
                "attempt_2_activations": sum(
                    item["attempt_2_activated"]
                    for item in trajectory["attempt_1_to_attempt_2_transitions"]
                ),
            },
        }
    required_usefulness = policy["usefulness_requires"]
    usefulness_complete = (
        isinstance(required_usefulness, list)
        and expected_usefulness is not None
        and set(required_usefulness) == set(expected_usefulness)
        and analysis.get("esg_rr_002_usefulness") == expected_usefulness
        and _finite_number(expected_usefulness["primary_acceptance_point_estimate"])
        and interval_informative
        and _sha256(expected_usefulness["retry_inclusive_work_result"]["sha256"])
        and _sha256(
            expected_usefulness["retry_inclusive_falsification_result"]["sha256"]
        )
    )
    prior_evidence_bound = analysis.get("prior_evidence_comparison") == {
        "prior_evidence_sha256": policy.get("prior_evidence_sha256"),
        "prior_evidence_gap": policy.get("prior_evidence_gap"),
        "prospective_direct_addition": policy.get("prospective_direct_addition"),
        "gate_policy_matches_prior_evidence": True,
    }
    base_criteria = {
        "methodological_integrity": (
            not policy["protocol_valid_and_stage_1_pass_required"]
            or (
                integrity["protocol_valid"] is True
                and integrity["terminal_status"] == "complete"
                and (
                    policy["protocol_invalid_batch_stop_permitted"]
                    or integrity["batch_stop_classification"] is None
                )
                and _sha256(integrity["stage_1_audit_sha256"])
            )
        ),
        "sufficient_admissible_data": (
            population["complete_admissible_slots"]
            >= policy["minimum_independent_admissible_clusters"]
            and (
                not policy["complete_mandatory_schedule_required"]
                or (
                    population["admissible_cells"] == population["frozen_cells"]
                    and population["missing_cells"] == 0
                    and not population["inadmissible_by_arm_and_termination"]
                )
            )
        ),
        "independence_adequate": (
            complete_clusters >= policy["minimum_independent_admissible_clusters"]
            and "repository clusters" in population["rule"]
        ),
        "uncertainty_informative": interval_informative,
        "evaluator_valid": (
            not policy["evaluator_validity_required_for_every_admissible_record"]
            or (
                anomaly["cells_with_anomalies"] == 0
                and not anomaly["counts_by_code"]
            )
        ),
        "usefulness_threshold_met": usefulness_complete,
        "disposition_permitted": (
            analysis["scientific_disposition"]["label"]
            not in policy["prohibited_dispositions"]
        ),
        "significance_or_equivalence_test_not_used": (
            policy["significance_or_equivalence_test"] is False
        ),
    }
    material_addition = bool(
        prior_evidence_bound
        and all(base_criteria.values())
        and policy["materially_adds_derivation"]
        == (
            "prior_gap_and_direct_addition_match AND protocol_integrity AND "
            "admissibility AND evaluator_validity AND finite_uncertainty AND "
            "actual_usefulness_outputs"
        )
    )
    criteria = {
        **base_criteria,
        "materially_adds_to_existing_evidence": material_addition,
    }
    justified = bool(
        policy["candidate_justified_requires_materially_adds"]
        and material_addition
    )
    return {
        "criteria_version": ESG_RR_002_GATE_VERSION,
        "status": "evaluated",
        "policy_sha256": policy["policy_sha256"],
        "criteria": criteria,
        "candidate_justified": justified,
        "decision": "candidate_justified" if justified else "not_justified",
        "basis": (
            "all contract-bound ESG-RR-002 publication-candidate criteria passed"
            if justified
            else "one or more contract-bound ESG-RR-002 publication-candidate criteria failed"
        ),
    }


def _experiment_projection(
    receipt: dict[str, Any],
    summary: dict[str, Any],
    contract: dict[str, Any],
    envelope: dict[str, Any],
    analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        validate_contract(contract)
        safe_envelope = validate_analysis_terminal_envelope(contract, envelope)
        recomputed = analyze_reasoning_effort_v2(contract, safe_envelope)
    except (ExperimentConfigurationError, AnalysisInputError, KeyError, TypeError) as error:
        raise TerminalPackageError(
            f"experiment terminal evidence is invalid: {error}"
        ) from error
    _require(
        canonical_bytes(recomputed) == canonical_bytes(analysis),
        "analysis does not regenerate from the validated terminal envelope",
    )
    _require(
        receipt["status"] == "stable_pool_ready"
        and summary["minimum_gate_passed"] is True
        and contract["source"]["qualification_receipt_sha256"]
        == receipt["state_sha256"]
        and safe_envelope["qualification_receipt_sha256"]
        == receipt["state_sha256"],
        "experiment artifacts are not bound to the terminal qualified population",
    )
    runtime = _safe_runtime_projection(receipt)
    _require(
        contract["runtime"]["model"] == runtime["model"]
        and contract["runtime"]["codex_version"] == runtime["codex_version"],
        "experiment contract runtime differs from qualification",
    )
    pool = contract["source"]["private_pool"]
    _require(
        10 <= pool["primary_count"] <= summary["primary_cluster_count"]
        and 0 <= pool["alternate_count"] <= summary["alternate_cluster_count"],
        "experiment contract population exceeds or falls outside qualification",
    )
    receipts = safe_envelope["receipt_projections"]
    subject_start_accounting = deepcopy(safe_envelope["subject_start_accounting"])
    subject_starts = subject_start_accounting[
        "experiment_subject_invocation_starts"
    ]
    evaluator_starts = sum(
        item["evaluator_artifact"]["invocation_started"] is True
        for item in receipts
    )
    cap = contract["attempt_accounting"]["maximum_subject_invocation_starts"]
    _require(
        subject_start_accounting["total_subject_invocation_starts"] <= cap <= 56,
        "derived experimental subject starts exceed or drift from the frozen cap",
    )
    population = recomputed["analysis_population"]
    assignments = safe_envelope["effective_assignments"]
    experiment = {
        "started": subject_starts > 0,
        "runtime": {
            **runtime,
            "runtime_identity": contract["runtime"]["runtime_identity"],
            "tool_configuration_identity": contract["runtime"][
                "tool_configuration_identity"
            ],
        },
        "frozen_primary_clusters": pool["primary_count"],
        "frozen_alternate_clusters": pool["alternate_count"],
        "frozen_cells": population["frozen_cells"],
        "attempt_records": len(receipts),
        "subject_start_accounting": subject_start_accounting,
        "evaluator_invocation_starts": evaluator_starts,
        "subject_invocation_start_cap": cap,
        "observed_cells": population["observed_cells"],
        "admissible_cells": population["admissible_cells"],
        "missing_cells": population["missing_cells"],
        "alternates_activated": sum(
            item["alternate_activated"] is True for item in assignments
        ),
        "terminal_status": recomputed["terminal_integrity"]["terminal_status"],
        "batch_stop_classification": recomputed["terminal_integrity"][
            "batch_stop_classification"
        ],
    }
    paired = recomputed["acceptance"]["paired_repository_clusters"]
    primary = {
        "low": deepcopy(recomputed["acceptance"]["by_arm"]["low"]),
        "medium": deepcopy(recomputed["acceptance"]["by_arm"]["medium"]),
        "paired_repository_clusters": deepcopy(paired),
        "discordant_repetitions": recomputed["acceptance"][
            "discordant_repetitions"
        ]["total"],
    }
    return experiment, primary, recomputed


def _artifact_binding(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"byte_sha256": _byte_sha256(value)}


def _insufficient_experiment(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "started": False,
        "runtime": runtime,
        "frozen_primary_clusters": 0,
        "frozen_alternate_clusters": 0,
        "frozen_cells": 0,
        "attempt_records": 0,
        "subject_start_accounting": {
            "canary_subject_invocation_starts": 0,
            "experiment_subject_invocation_starts": 0,
            "total_subject_invocation_starts": 0,
        },
        "evaluator_invocation_starts": 0,
        "subject_invocation_start_cap": 56,
        "observed_cells": 0,
        "admissible_cells": 0,
        "missing_cells": 0,
        "alternates_activated": 0,
        "terminal_status": "not_started",
        "batch_stop_classification": None,
    }


def _pre_subject_integrity_experiment(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        **_insufficient_experiment(runtime),
        "terminal_status": "pre_subject_integrity_stop",
        "batch_stop_classification": (
            "runtime_identity_mismatch_before_contract_freeze"
        ),
    }


def _integrity_stop_projection(
    stop: dict[str, Any], qualification_receipt: dict[str, Any]
) -> dict[str, Any]:
    try:
        validate_pre_freeze_terminal_receipt(stop, qualification_receipt)
    except ExperimentConfigurationError as error:
        raise TerminalPackageError(
            f"private integrity stop is incomplete or inconsistent: {error}"
        ) from error
    return {
        "stage": "pre_contract_freeze",
        "stop_condition": "scientific_protocol_integrity_compromised",
        "classification": stop["classification"],
        "reason": "exact_qualified_model_catalog_identity_unavailable",
        "qualification_runtime_identity_sha256": stop["expected_runtime_sha256"],
        "observed_runtime_identity_sha256": stop["observed_runtime_sha256"],
        "qualification_model_catalog_sha256": stop[
            "expected_model_catalog_sha256"
        ],
        "observed_model_catalog_sha256": stop[
            "observed_model_catalog_sha256"
        ],
        "model_catalog_identity_match": False,
        "contract_frozen": False,
        "subject_outcome_exposed": False,
        "private_stop_receipt_sha256": stop["receipt_sha256"],
    }


def validate_terminal_result(result: dict[str, Any]) -> None:
    fields = {
        "schema_name",
        "schema_version",
        "terminal_path",
        "terminal_disposition",
        "qualification",
        "experiment",
        "primary_outcome",
        "work_sha256",
        "falsification_sha256",
        "integrity_stop",
        "scientific_disposition",
        "esg_rr_002_candidate_gate",
        "artifacts",
        "claim_boundaries",
        "next_boundary",
        "terminal_result_sha256",
    }
    _exact(result, fields, "terminal result")
    body = {
        key: value for key, value in result.items() if key != "terminal_result_sha256"
    }
    _require(
        result["schema_name"] == SCHEMA_NAME
        and result["schema_version"] == SCHEMA_VERSION
        and result["terminal_path"] in TERMINAL_PATHS
        and result["terminal_result_sha256"] == digest(body),
        "terminal result schema or self-hash drifted",
    )
    qualification = result["qualification"]
    experiment = result["experiment"]
    artifacts = result["artifacts"]
    gate = result["esg_rr_002_candidate_gate"]
    qualification_fields = {
        "summary_sha256",
        "private_receipt_state_sha256",
        "status",
        "attempted_candidates",
        "validation_failures",
        "gold_failures",
        "infrastructure_failures",
        "qualified_independent_clusters",
        "primary_cluster_count",
        "alternate_cluster_count",
        "minimum_gate_passed",
        "subject_invocation_starts",
    }
    experiment_fields = {
        "started",
        "runtime",
        "frozen_primary_clusters",
        "frozen_alternate_clusters",
        "frozen_cells",
        "attempt_records",
        "subject_start_accounting",
        "evaluator_invocation_starts",
        "subject_invocation_start_cap",
        "observed_cells",
        "admissible_cells",
        "missing_cells",
        "alternates_activated",
        "terminal_status",
        "batch_stop_classification",
    }
    criteria_fields = {
        "methodological_integrity",
        "sufficient_admissible_data",
        "independence_adequate",
        "uncertainty_informative",
        "evaluator_valid",
        "usefulness_threshold_met",
        "disposition_permitted",
        "significance_or_equivalence_test_not_used",
        "materially_adds_to_existing_evidence",
    }
    _exact(qualification, qualification_fields, "qualification projection")
    _exact(experiment, experiment_fields, "experiment projection")
    subject_starts = _exact(
        experiment["subject_start_accounting"],
        {
            "canary_subject_invocation_starts",
            "experiment_subject_invocation_starts",
            "total_subject_invocation_starts",
        },
        "terminal subject-start accounting",
    )
    _exact(
        artifacts,
        {"qualification_summary", "contract", "terminal_envelope", "analysis"},
        "artifact bindings",
    )
    _exact(
        gate,
        {
            "criteria_version",
            "status",
            "policy_sha256",
            "criteria",
            "candidate_justified",
            "decision",
            "basis",
        },
        "ESG-RR-002 gate",
    )
    qualification_binding = _exact(
        artifacts["qualification_summary"], {"byte_sha256"}, "qualification binding"
    )
    _require(
        _sha256(qualification["summary_sha256"])
        and _sha256(qualification["private_receipt_state_sha256"])
        and qualification_binding["byte_sha256"] == qualification["summary_sha256"]
        and qualification["status"] in {"insufficient", "stable_pool_ready"}
        and type(qualification["minimum_gate_passed"]) is bool
        and all(
            type(qualification[field]) is int and qualification[field] >= 0
            for field in qualification_fields
            - {
                "summary_sha256",
                "private_receipt_state_sha256",
                "status",
                "minimum_gate_passed",
            }
        )
        and gate["criteria_version"] == ESG_RR_002_GATE_VERSION
        and isinstance(gate["basis"], str)
        and bool(gate["basis"])
        and type(gate["candidate_justified"]) is bool,
        "terminal result bindings or ESG-RR-002 gate are malformed",
    )
    runtime_fields = {"codex_version", "model", "supported_reasoning_efforts"}
    if result["terminal_path"] == "experiment_terminal":
        runtime_fields |= {"runtime_identity", "tool_configuration_identity"}
    runtime = _exact(experiment["runtime"], runtime_fields, "runtime projection")
    _require(
        all(
            isinstance(runtime[field], str) and runtime[field]
            for field in runtime_fields - {"supported_reasoning_efforts"}
        )
        and isinstance(runtime["supported_reasoning_efforts"], list)
        and {"low", "medium"} <= set(runtime["supported_reasoning_efforts"])
        and type(experiment["started"]) is bool
        and isinstance(experiment["terminal_status"], str)
        and bool(experiment["terminal_status"])
        and (
            experiment["batch_stop_classification"] is None
            or (
                isinstance(experiment["batch_stop_classification"], str)
                and bool(experiment["batch_stop_classification"])
            )
        )
        and all(
            type(experiment[field]) is int and experiment[field] >= 0
            for field in experiment_fields
            - {
                "started",
                "runtime",
                "subject_start_accounting",
                "terminal_status",
                "batch_stop_classification",
            }
        ),
        "terminal runtime or invocation accounting is malformed",
    )
    _require(
        experiment["frozen_cells"]
        <= experiment["subject_invocation_start_cap"]
        <= 56
        and all(type(value) is int and value >= 0 for value in subject_starts.values())
        and subject_starts["canary_subject_invocation_starts"] in {0, 1}
        and subject_starts["total_subject_invocation_starts"]
        == subject_starts["canary_subject_invocation_starts"]
        + subject_starts["experiment_subject_invocation_starts"]
        and subject_starts["total_subject_invocation_starts"] <= 56
        and subject_starts["experiment_subject_invocation_starts"]
        <= experiment["attempt_records"]
        and experiment["evaluator_invocation_starts"]
        <= subject_starts["experiment_subject_invocation_starts"]
        and experiment["admissible_cells"] <= experiment["observed_cells"]
        <= experiment["frozen_cells"]
        and experiment["missing_cells"]
        == experiment["frozen_cells"] - experiment["observed_cells"],
        "terminal experiment counts are inconsistent",
    )
    if result["terminal_path"] == "insufficient_population":
        _require(
            result["terminal_disposition"] == INSUFFICIENT_DISPOSITION
            and result["scientific_disposition"] == INSUFFICIENT_DISPOSITION
            and qualification.get("status") == "insufficient"
            and qualification.get("minimum_gate_passed") is False
            and qualification.get("qualified_independent_clusters", 10) < 10
            and qualification.get("subject_invocation_starts") == 0
            and experiment.get("started") is False
            and subject_starts
            == {
                "canary_subject_invocation_starts": 0,
                "experiment_subject_invocation_starts": 0,
                "total_subject_invocation_starts": 0,
            }
            and experiment.get("evaluator_invocation_starts") == 0
            and result["primary_outcome"] is None
            and result["work_sha256"] is None
            and result["falsification_sha256"] is None
            and result["integrity_stop"] is None
            and artifacts.get("contract") is None
            and artifacts.get("terminal_envelope") is None
            and artifacts.get("analysis") is None
            and gate == _empty_esg_gate(),
            "insufficient-population result claims experimental evidence",
        )
    elif result["terminal_path"] == "pre_subject_integrity_stop":
        stop = _exact(
            result["integrity_stop"],
            {
                "stage",
                "stop_condition",
                "classification",
                "reason",
                "qualification_runtime_identity_sha256",
                "observed_runtime_identity_sha256",
                "qualification_model_catalog_sha256",
                "observed_model_catalog_sha256",
                "model_catalog_identity_match",
                "contract_frozen",
                "subject_outcome_exposed",
                "private_stop_receipt_sha256",
            },
            "integrity stop projection",
        )
        expected_gate = _empty_esg_gate(
            "no experiment completed because exact runtime identity drifted "
            "before contract freeze"
        )
        _require(
            qualification.get("status") == "stable_pool_ready"
            and qualification.get("minimum_gate_passed") is True
            and qualification.get("subject_invocation_starts") == 0
            and experiment.get("started") is False
            and all(
                experiment[field] == 0
                for field in experiment_fields
                - {
                    "started",
                    "runtime",
                    "subject_start_accounting",
                    "subject_invocation_start_cap",
                    "terminal_status",
                    "batch_stop_classification",
                }
            )
            and subject_starts
            == {
                "canary_subject_invocation_starts": 0,
                "experiment_subject_invocation_starts": 0,
                "total_subject_invocation_starts": 0,
            }
            and experiment["terminal_status"] == "pre_subject_integrity_stop"
            and experiment["batch_stop_classification"]
            == "runtime_identity_mismatch_before_contract_freeze"
            and result["terminal_disposition"] == INTEGRITY_STOP_DISPOSITION
            and result["scientific_disposition"] == INTEGRITY_STOP_DISPOSITION
            and result["primary_outcome"] is None
            and result["work_sha256"] is None
            and result["falsification_sha256"] is None
            and artifacts.get("contract") is None
            and artifacts.get("terminal_envelope") is None
            and artifacts.get("analysis") is None
            and gate == expected_gate
            and stop["stage"] == "pre_contract_freeze"
            and stop["stop_condition"]
            == "scientific_protocol_integrity_compromised"
            and stop["classification"]
            == "runtime_identity_mismatch_before_contract_freeze"
            and stop["reason"]
            == "exact_qualified_model_catalog_identity_unavailable"
            and _sha256(stop["qualification_runtime_identity_sha256"])
            and _sha256(stop["observed_runtime_identity_sha256"])
            and stop["qualification_runtime_identity_sha256"]
            != stop["observed_runtime_identity_sha256"]
            and _sha256(stop["qualification_model_catalog_sha256"])
            and _sha256(stop["observed_model_catalog_sha256"])
            and stop["qualification_model_catalog_sha256"]
            != stop["observed_model_catalog_sha256"]
            and stop["model_catalog_identity_match"] is False
            and stop["contract_frozen"] is False
            and stop["subject_outcome_exposed"] is False
            and _sha256(stop["private_stop_receipt_sha256"]),
            "pre-subject integrity-stop result is incomplete or inconsistent",
        )
    else:
        criteria = _exact(gate["criteria"], criteria_fields, "ESG-RR-002 criteria")
        _require(
            qualification.get("status") == "stable_pool_ready"
            and qualification.get("minimum_gate_passed") is True
            and isinstance(experiment.get("started"), bool)
            and experiment.get("started")
            is (subject_starts["experiment_subject_invocation_starts"] > 0)
            and result["scientific_disposition"] in EXPERIMENT_DISPOSITIONS
            and result["terminal_disposition"]
            == result["scientific_disposition"]
            and isinstance(result["primary_outcome"], dict)
            and _sha256(result["work_sha256"])
            and _sha256(result["falsification_sha256"])
            and result["integrity_stop"] is None
            and gate["status"] == "evaluated"
            and _sha256(gate["policy_sha256"])
            and all(type(value) is bool for value in criteria.values())
            and gate["candidate_justified"] is all(criteria.values())
            and gate["decision"]
            == ("candidate_justified" if all(criteria.values()) else "not_justified")
            and all(
                isinstance(artifacts.get(field), dict)
                and set(artifacts[field]) == {"byte_sha256"}
                and _sha256(artifacts[field]["byte_sha256"])
                for field in ("contract", "terminal_envelope", "analysis")
            ),
            "experiment-terminal result is incomplete or inconsistent",
        )
        _require(
            experiment["started"]
            or result["scientific_disposition"] == "EXPERIMENT INVALID / TERMINATED",
            "zero-start experiment terminal must be protocol-invalid",
        )
    claims = result["claim_boundaries"]
    _require(
        set(claims)
        == {
            "exploratory_only",
            "equivalence_or_noninferiority_claim_permitted",
            "billing_claim_permitted",
            "publication_authorized",
            "pull_request_authorized",
            "merge_authorized",
            "repository_visibility_change_authorized",
        }
        and claims["exploratory_only"] is True
        and claims["equivalence_or_noninferiority_claim_permitted"] is False
        and claims["billing_claim_permitted"] is False
        and claims["publication_authorized"] is False
        and type(claims["pull_request_authorized"]) is bool
        and claims["merge_authorized"] is claims["pull_request_authorized"]
        and claims["repository_visibility_change_authorized"] is False
        and result["next_boundary"] in NEXT_BOUNDARIES,
        "terminal claim or next-action boundary drifted",
    )
    _public_safety_scan(result)


def _format_number(value: Any) -> str:
    if value is None:
        return "not available"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _work_table(analysis: dict[str, Any]) -> list[str]:
    fields = (
        ("input_tokens", "Input"),
        ("cached_input_tokens", "Cached input"),
        ("fresh_input_tokens", "Fresh input"),
        ("output_tokens", "Output"),
        ("reasoning_output_tokens", "Reasoning output"),
        ("wall_seconds", "Wall seconds"),
        ("turns", "Turns"),
    )
    lines = [
        "| Diagnostic | LOW total | MEDIUM total | LOW per accepted | MEDIUM per accepted |",
        "|---|---:|---:|---:|---:|",
    ]
    for field, label in fields:
        item = analysis["work"][field]["by_arm"]
        lines.append(
            "| "
            + " | ".join(
                (
                    label,
                    _format_number(item["low"]["unconditional"]["total"]),
                    _format_number(item["medium"]["unconditional"]["total"]),
                    _format_number(
                        item["low"]["accepted_conditional"]["per_accepted_outcome"]
                    ),
                    _format_number(
                        item["medium"]["accepted_conditional"]["per_accepted_outcome"]
                    ),
                )
            )
            + " |"
        )
    return lines


def _loto_range(analysis: dict[str, Any]) -> str:
    values = []
    for item in analysis["falsification"]["leave_one_slot_out"]:
        paired = item
        if paired is not None:
            values.append(paired["medium_minus_low"])
    if not values:
        return "not available"
    return f"{_format_number(min(values))} to {_format_number(max(values))}"


def render_terminal_report(
    result: dict[str, Any], analysis: dict[str, Any] | None
) -> str:
    """Render the mandated content-safe terminal report deterministically."""

    validate_terminal_result(result)
    qualification = result["qualification"]
    experiment = result["experiment"]
    subject_starts = experiment["subject_start_accounting"]
    lines = [
        "# Evaluator-Stable Reasoning-Effort Terminal Report",
        "",
        "## Evaluator qualification",
        "",
        f"- Attempted candidates: {qualification['attempted_candidates']}",
        f"- Validation failures: {qualification['validation_failures']}",
        f"- Gold failures: {qualification['gold_failures']}",
        f"- Infrastructure failures: {qualification['infrastructure_failures']}",
        "- Final qualified pool: "
        f"{qualification['qualified_independent_clusters']} independent clusters",
        "- Task and repository identities: withheld",
        "",
        "## Experiment",
        "",
        f"- Started: {'yes' if experiment['started'] else 'no'}",
        f"- Codex: {experiment['runtime']['codex_version']}",
        f"- Model: {experiment['runtime']['model']}",
        f"- Frozen primary tasks: {experiment['frozen_primary_clusters']}",
        f"- Attempt records: {experiment['attempt_records']}",
        "- Actual contentless-canary subject invocation starts: "
        f"{subject_starts['canary_subject_invocation_starts']}",
        "- Actual experimental-cell subject invocation starts: "
        f"{subject_starts['experiment_subject_invocation_starts']}",
        "- Actual total subject invocation starts: "
        f"{subject_starts['total_subject_invocation_starts']}",
        f"- Missing cells: {experiment['missing_cells']}",
        f"- Alternates activated: {experiment['alternates_activated']}",
        "",
        "## Primary outcome",
        "",
    ]
    if result["terminal_path"] == "insufficient_population":
        lines.extend(
            [
                "Not applicable. No subject experiment started; this terminal state is "
                "task/evaluator infrastructure evidence, not a LOW-versus-MEDIUM result.",
                "",
                "## Work",
                "",
                "Not applicable. No subject work was observed.",
                "",
                "## Falsification",
                "",
                "The decisive contradictory evidence is the sub-minimum stable population. "
                "Outcome sensitivity analyses are not applicable because no treatment outcome exists.",
            ]
        )
    elif result["terminal_path"] == "pre_subject_integrity_stop":
        stop = result["integrity_stop"]
        lines.extend(
            [
                "Not applicable. The stable qualification gate passed, but exact runtime "
                "identity drifted before population and contract freeze. No LOW-versus-MEDIUM "
                "outcome exists.",
                "",
                "- Qualification selection: "
                f"{qualification['primary_cluster_count']} primary candidates and "
                f"{qualification['alternate_cluster_count']} alternates; this was not a "
                "frozen experimental population.",
                f"- Integrity stop: {stop['classification']}",
                "- Contract frozen: no",
                "- Subject outcome exposed: no",
                "",
                "## Work",
                "",
                "Not applicable. No subject work was observed.",
                "",
                "## Falsification",
                "",
                "The decisive contradictory evidence is the mismatch between the qualified "
                "runtime identity and the runtime observed at the exact pre-contract freeze "
                "gate. Outcome sensitivity analyses are not applicable because no treatment "
                "outcome exists.",
            ]
        )
    else:
        _require(analysis is not None, "experiment report requires analysis")
        primary = result["primary_outcome"]
        paired = primary["paired_repository_clusters"]
        interval = paired["repository_cluster_bootstrap_95_interval"] if paired else None
        lines.extend(
            [
                f"- LOW acceptance: {primary['low']['accepted']}/{primary['low']['admissible_cells']} "
                f"({_format_number(primary['low']['rate'])})",
                f"- MEDIUM acceptance: {primary['medium']['accepted']}/{primary['medium']['admissible_cells']} "
                f"({_format_number(primary['medium']['rate'])})",
                "- Paired MEDIUM-minus-LOW difference: "
                + (_format_number(paired["medium_minus_low"]) if paired else "not available"),
                "- Repository-cluster bootstrap 95% interval: "
                + (
                    f"{_format_number(interval['lower'])} to {_format_number(interval['upper'])}"
                    if interval
                    else "not available"
                ),
                f"- Discordant repetitions: {primary['discordant_repetitions']}",
                "",
                "## Work",
                "",
                *_work_table(analysis),
                "",
                "Accepted-conditional work is a descriptive post-outcome subset; unconditional "
                "work remains visible.",
                "All-attempt work, discarded or infrastructure-invalid work, retry "
                "transitions, and final-record sensitivity remain visible in the "
                "hash-bound analysis.",
                "",
                "## Falsification",
                "",
                "- Strongest contradictory evidence: opposite-arm-only wins were "
                f"{analysis['falsification']['opposite_arm_wins']}",
                f"- Leave-one-task-out paired-difference range: {_loto_range(analysis)}",
                "- Heterogeneity: repetition disagreement in "
                f"{analysis['falsification']['repetition_disagreement']['total']} task-arm strata; "
                f"evaluator anomalies in {analysis['falsification']['evaluator_anomalies']['cells_with_anomalies']} cells.",
                "- Timeout, cache, correction-turn, missingness, alternate-use, and evaluator "
                "sensitivity remain in the hash-bound analysis artifact.",
            ]
        )
    gate = result["esg_rr_002_candidate_gate"]
    repository_workflow_authorized = result["claim_boundaries"][
        "pull_request_authorized"
    ]
    next_boundary = result["next_boundary"]
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Scientific disposition: **{result['scientific_disposition']}**",
            f"- ESG-RR-002 candidate: **{gate['decision']}**",
            f"- Basis: {gate['basis']}",
            "- This is exploratory evidence and authorizes neither equivalence, "
            "noninferiority, billing, ESG-RR-002 publication, nor repository visibility "
            "claims or actions.",
            "",
            "## Repository",
            "",
            "- Branch, commit, test, CI, and CodeQL state are recorded in the canonical "
            "terminal handoff after local Git stabilization.",
            "- Raw task, patch, trace, evaluator, and qualification working material is "
            "excluded from tracked artifacts.",
            (
                "- The terminal-record pull request and merge are separately authorized; "
                "ESG-RR-002 publication and release are not justified."
                if repository_workflow_authorized
                else "- Publication, pull request, merge, and repository visibility remain "
                "separately blocked by authorization."
            ),
            "",
            "## Next boundary",
            "",
            "Exactly one action requires user authorization:",
            "",
            f"> {next_boundary}",
            "",
            (
                "Do not start another experiment."
                if next_boundary == "authorize_second_experiment"
                else "Do not start another experiment, publish, or make the repository public."
            ),
            "",
            f"Terminal result SHA-256: `{result['terminal_result_sha256']}`",
            "",
        ]
    )
    rendered = "\n".join(lines)
    _public_safety_scan(rendered)
    return rendered


def build_terminal_package(
    *,
    terminal_path: str,
    qualification_receipt: dict[str, Any],
    contract: dict[str, Any] | None = None,
    terminal_envelope: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
    integrity_stop: dict[str, Any] | None = None,
    repository_workflow_authorized: bool = False,
    next_boundary: str = "authorize_private_canonical_branch_push",
) -> dict[Path, bytes]:
    """Build, but do not persist, one deterministic public-safe terminal package."""

    _require(terminal_path in TERMINAL_PATHS, "unknown terminal path")
    _require(
        type(repository_workflow_authorized) is bool
        and next_boundary in NEXT_BOUNDARIES,
        "terminal repository authority or next boundary is invalid",
    )
    receipt = deepcopy(qualification_receipt)
    summary, qualification = _qualification_projection(receipt)
    runtime = _safe_runtime_projection(receipt)
    if terminal_path == "insufficient_population":
        _require(
            receipt["status"] == "insufficient"
            and qualification["qualified_independent_clusters"] < 10
            and qualification["subject_invocation_starts"] == 0,
            "insufficient path requires a terminal sub-minimum zero-subject receipt",
        )
        _require(
            contract is None
            and terminal_envelope is None
            and analysis is None
            and integrity_stop is None,
            "insufficient path forbids experiment artifacts",
        )
        experiment = _insufficient_experiment(runtime)
        primary = None
        disposition = INSUFFICIENT_DISPOSITION
        esg_gate = _empty_esg_gate()
        verified_analysis = None
        integrity_projection = None
    elif terminal_path == "pre_subject_integrity_stop":
        _require(
            receipt["status"] == "stable_pool_ready"
            and qualification["minimum_gate_passed"] is True
            and qualification["subject_invocation_starts"] == 0,
            "pre-subject integrity stop requires a stable zero-subject qualification",
        )
        _require(
            contract is None
            and terminal_envelope is None
            and analysis is None
            and integrity_stop is not None,
            "pre-subject integrity stop requires only its private stop receipt",
        )
        integrity_projection = _integrity_stop_projection(integrity_stop, receipt)
        experiment = _pre_subject_integrity_experiment(runtime)
        primary = None
        disposition = INTEGRITY_STOP_DISPOSITION
        esg_gate = _empty_esg_gate(
            "no experiment completed because exact runtime identity drifted "
            "before contract freeze"
        )
        verified_analysis = None
    else:
        _require(
            contract is not None
            and terminal_envelope is not None
            and analysis is not None
            and integrity_stop is None,
            "experiment terminal requires contract, terminal envelope, and analysis",
        )
        experiment, primary, verified_analysis = _experiment_projection(
            receipt, summary, contract, terminal_envelope, analysis
        )
        disposition = verified_analysis["scientific_disposition"]["label"]
        _require(
            disposition in EXPERIMENT_DISPOSITIONS,
            "analysis emitted an unsupported scientific disposition",
        )
        esg_gate = _derive_esg_gate(
            verified_analysis, contract["esg_rr_002_gate_policy"]
        )
        integrity_projection = None
    artifacts = {
        "qualification_summary": _artifact_binding(summary),
        "contract": _artifact_binding(contract),
        "terminal_envelope": _artifact_binding(terminal_envelope),
        "analysis": _artifact_binding(verified_analysis),
    }
    body = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "terminal_path": terminal_path,
        "terminal_disposition": disposition,
        "qualification": qualification,
        "experiment": experiment,
        "primary_outcome": primary,
        "work_sha256": (
            verified_analysis["esg_rr_002_usefulness"][
                "retry_inclusive_work_result"
            ]["sha256"]
            if verified_analysis
            else None
        ),
        "falsification_sha256": (
            verified_analysis["esg_rr_002_usefulness"][
                "retry_inclusive_falsification_result"
            ]["sha256"]
            if verified_analysis
            else None
        ),
        "integrity_stop": integrity_projection,
        "scientific_disposition": disposition,
        "esg_rr_002_candidate_gate": esg_gate,
        "artifacts": artifacts,
        "claim_boundaries": {
            "exploratory_only": True,
            "equivalence_or_noninferiority_claim_permitted": False,
            "billing_claim_permitted": False,
            "publication_authorized": False,
            "pull_request_authorized": repository_workflow_authorized,
            "merge_authorized": repository_workflow_authorized,
            "repository_visibility_change_authorized": False,
        },
        "next_boundary": next_boundary,
    }
    result = {**body, "terminal_result_sha256": digest(body)}
    validate_terminal_result(result)
    report = render_terminal_report(result, verified_analysis)
    package = {
        QUALIFICATION_SUMMARY_PATH: canonical_artifact_bytes(summary),
        TERMINAL_RESULT_PATH: canonical_artifact_bytes(result),
        TERMINAL_REPORT_PATH: report.encode("utf-8"),
    }
    if terminal_path == "experiment_terminal":
        assert contract is not None and terminal_envelope is not None
        package.update(
            {
                CONTRACT_PATH: canonical_artifact_bytes(contract),
                TERMINAL_ENVELOPE_PATH: canonical_artifact_bytes(terminal_envelope),
                ANALYSIS_PATH: canonical_artifact_bytes(verified_analysis),
            }
        )
    for path, content in package.items():
        _require(not path.is_absolute() and ".." not in path.parts, "package path escapes root")
        if path.suffix == ".json":
            parsed = json.loads(content)
            _public_safety_scan(parsed)
            _require(content == canonical_artifact_bytes(parsed), "package JSON is not canonical")
        else:
            _public_safety_scan(content.decode("utf-8"))
    return package


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        _require(path.read_bytes() == content, f"terminal artifact readback failed: {path}")
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_package_paths(package: Mapping[Path, bytes]) -> bool:
    expected = frozenset(package)
    common = frozenset(COMMON_PATHS)
    experiment = common | frozenset(EXPERIMENT_PATHS)
    _require(expected in {common, experiment}, "terminal package file set drifted")
    _require(
        all(
            isinstance(relative, Path)
            and not relative.is_absolute()
            and ".." not in relative.parts
            for relative in expected
        ),
        "terminal package path escapes root",
    )
    return expected == experiment


def _safe_destination(root: Path, relative: Path) -> Path:
    root_resolved = root.resolve()
    destination = root / relative
    _require(
        destination.parent.resolve(strict=False).is_relative_to(root_resolved),
        f"terminal artifact parent escapes root: {relative}",
    )
    _require(
        not destination.is_symlink(),
        f"terminal artifact destination is a symlink: {relative}",
    )
    return destination


def write_terminal_package(root: Path, package: Mapping[Path, bytes]) -> None:
    """Persist one already-built package atomically per file with readback."""

    experiment_expected = _validate_package_paths(package)
    root.mkdir(parents=True, exist_ok=True)
    _require(root.is_dir() and not root.is_symlink(), "terminal output root is unsafe")
    if not experiment_expected:
        _require(
            not any(
                (root / path).exists() or (root / path).is_symlink()
                for path in EXPERIMENT_PATHS
            ),
            "common-only terminal package refuses pre-existing experiment artifacts",
        )
    for relative, content in package.items():
        destination = _safe_destination(root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(destination, content)


def verify_terminal_package(root: Path, expected: Mapping[Path, bytes]) -> None:
    """Require exact deterministic bytes and absence of forbidden path artifacts."""

    experiment_expected = _validate_package_paths(expected)
    _require(root.is_dir() and not root.is_symlink(), "terminal output root is unsafe")
    for relative, content in expected.items():
        path = _safe_destination(root, relative)
        _require(path.is_file() and not path.is_symlink(), f"terminal artifact missing: {relative}")
        _require(path.read_bytes() == content, f"terminal artifact bytes drifted: {relative}")
    if not experiment_expected:
        _require(
            not any(
                (root / path).exists() or (root / path).is_symlink()
                for path in EXPERIMENT_PATHS
            ),
            "common-only terminal package contains experiment artifacts",
        )
