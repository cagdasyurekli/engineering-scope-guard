"""Provider-free frozen contract and ledger rules for reasoning-effort v2.

Exact task identities live in a separately sealed private pool. The public
contract contains commitments only and cannot authorize live execution.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Iterable, Sequence

from .experiment import ExperimentConfigurationError
from .pilot_contract import canonical_bytes, digest

SCHEMA_NAME = "engineering-scope-guard.reasoning-effort-v2"
SCHEMA_VERSION = 1
CONTRACT_VERSION = "reasoning-effort-v2.0"
SCHEDULE_SEED = "engineering-scope-guard-reasoning-effort-v2-order-2026-08-30"
BOOTSTRAP_SEED = "engineering-scope-guard-reasoning-effort-v2-cluster-bootstrap"
ARMS = ("low", "medium")
REPETITIONS = 2
MINIMUM_PRIMARY_TASKS = 10
MAXIMUM_PRIMARY_TASKS = 12
MAXIMUM_ALTERNATES = 4
STAGE_1_CELL_COUNT = 4
MAXIMUM_ATTEMPTS_PER_CELL = 2
MAXIMUM_SUBJECT_INVOCATION_STARTS = 56
HARNESS_SOURCE_CLOSURE_SCHEMA = (
    "engineering-scope-guard.reasoning-effort-v2-harness-source-closure"
)
HARNESS_ENTRYPOINTS = {
    "analysis": ["python3", "-m", "engineering_scope_guard.reasoning_effort_v2_analysis"],
    "azure_evaluator": ["python3", "scripts/azure_prediction_evaluator.py"],
    "canary_launch": ["python3", "scripts/reasoning_effort_v2_canary.py", "launch"],
    "canary_verify": ["python3", "scripts/reasoning_effort_v2_freeze.py", "verify"],
    "execute_next": ["python3", "scripts/reasoning_effort_v2_execution_adapter.py", "execute-next"],
    "export_analysis": ["python3", "scripts/reasoning_effort_v2_export.py", "build"],
    "freeze": ["python3", "scripts/reasoning_effort_v2_freeze.py", "freeze"],
    "terminal": ["python3", "scripts/reasoning_effort_v2_terminal.py"],
    "verify_analysis_export": [
        "python3", "scripts/reasoning_effort_v2_export.py", "verify",
    ],
}
_HARNESS_CLOSURE_SEEDS = (
    "src/engineering_scope_guard/azure_evaluator.py",
    "src/engineering_scope_guard/launch_surface.py",
    "src/engineering_scope_guard/runtime_lock.py",
    "src/engineering_scope_guard/runtime_soak.py",
    "src/engineering_scope_guard/reasoning_effort_v2.py",
    "src/engineering_scope_guard/reasoning_effort_v2_analysis.py",
    "src/engineering_scope_guard/reasoning_effort_v2_terminal.py",
    "scripts/reasoning_effort_v2_runner.py",
    "scripts/reasoning_effort_v2_execution_adapter.py",
    "scripts/reasoning_effort_v2_export.py",
    "scripts/reasoning_effort_v2_canary.py",
    "scripts/reasoning_effort_v2_freeze.py",
    "scripts/reasoning_effort_v2_terminal.py",
    "scripts/azure_prediction_evaluator.py",
    "scripts/azure_prediction_worker.py",
    "scripts/launch_surface_contract.py",
    "scripts/launch_surface_successor_preflight.py",
    "scripts/runtime_lock.py",
    "scripts/runtime_stability_soak.py",
)
PRIOR_EVIDENCE_PATHS = (
    "docs/reports/ESG-RR-001.manifest.json",
    "docs/PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json",
    "experiment/current_runtime_requalification_terminal.json",
)
BOOTSTRAP_RESAMPLES = 10_000
ANALYSIS_ENVELOPE_SCHEMA = "engineering-scope-guard.reasoning-effort-v2-analysis-envelope"
ANALYSIS_ENVELOPE_RECORD_KEYS = {
    "cell_id", "attempt", "effective_task_commitment_sha256",
    "terminal_receipt_sha256", "evaluator_receipt_sha256", "termination",
    "timed_out", "evaluator_anomalies", "input_tokens", "cached_input_tokens",
    "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens",
    "turns", "tool_actions", "search_actions", "correction_turns", "wall_seconds",
}
TERMINAL_ANALYSIS_RECORD_KEYS = ANALYSIS_ENVELOPE_RECORD_KEYS - {
    "attempt", "effective_task_commitment_sha256", "terminal_receipt_sha256",
    "evaluator_receipt_sha256",
}
INTEGER_WORK_FIELDS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens",
    "reasoning_output_tokens", "turns", "tool_actions", "search_actions",
    "correction_turns",
)
FLOAT_WORK_FIELDS = ("wall_seconds",)
TERMINAL_RECEIPT_KEYS = {
    "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
    "cell_id", "attempt", "effective_task_commitment_sha256",
    "subject_invocation_started", "command_sha256", "classification",
    "execution_receipt_sha256", "evaluator_receipt_sha256",
    "measurement_receipt_sha256", "execution_artifact", "evaluator_artifact",
    "measurement_artifact", "analysis_record", "terminal_receipt_sha256",
}

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
ALTERNATE_ACTIVATION_CLASSES = (
    "task_repository_or_container_unavailable",
    "task_evaluator_infrastructure_unavailable",
    "frozen_task_binding_corrupt",
)
MANDATORY_BATCH_STOP = (
    "harness_failure",
    "isolation_contract_violation",
    "malformed_inconsistent_measurement",
    "durable_evidence_incomplete",
    "runtime_or_source_identity_drift",
    "stage_1_audit_failed",
)
STAGE_1_AUDIT_CRITERIA = (
    "exact_four_retained_cells",
    "terminal_receipts_complete",
    "receipt_hashes_valid",
    "ledger_chain_valid",
    "no_batch_stop",
    "runtime_identity_stable",
    "source_identity_stable",
)

_TASK_REQUIRED_FIELDS = {"task_id", "repository", "task_snapshot_sha256"}
_TASK_RESERVED_FIELDS = {"population_slot", "alternate_ordinal", "private_pool_sha256"}
_SHA_FIELDS = {
    "qualification_receipt_sha256",
    "image_pool_identity",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _require_exact_keys(value: Any, keys: set[str], message: str) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == keys, message)
    return value


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _rank(*parts: str) -> str:
    return hashlib.sha256(
        "\0".join((SCHEDULE_SEED, CONTRACT_VERSION, *parts)).encode()
    ).hexdigest()


def _sealed(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {**value, field: digest(value)}


def _identity_matches(value: dict[str, Any], field: str) -> bool:
    body = {key: item for key, item in value.items() if key != field}
    return _sha256(value.get(field)) and value[field] == digest(body)


def _normalize_task(task: Any) -> dict[str, Any]:
    _require(isinstance(task, dict), "private pool task is not an object")
    _require(_TASK_REQUIRED_FIELDS <= set(task), "private pool task identity is incomplete")
    _require(
        not (_TASK_RESERVED_FIELDS & set(task)),
        "private pool task contains a reserved envelope field",
    )
    _require(
        all(_nonempty(task[field]) for field in _TASK_REQUIRED_FIELDS),
        "private pool task identity is malformed",
    )
    _require(
        _sha256(task["task_snapshot_sha256"]),
        "private pool task snapshot must be lowercase SHA-256",
    )
    try:
        canonical_bytes(task)
    except (TypeError, ValueError) as error:
        raise ExperimentConfigurationError(
            "private pool task contains a non-canonical value"
        ) from error
    return dict(task)


def build_private_pool(
    primaries: Sequence[dict[str, Any]],
    alternates: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Seal exact ordered task identities for private runner consumption."""

    _require(
        MINIMUM_PRIMARY_TASKS <= len(primaries) <= MAXIMUM_PRIMARY_TASKS,
        "reasoning-effort v2 requires 10 to 12 primary tasks",
    )
    _require(
        len(alternates) <= MAXIMUM_ALTERNATES,
        "reasoning-effort v2 permits at most four alternates",
    )
    primary = [
        {**_normalize_task(task), "population_slot": slot}
        for slot, task in enumerate(primaries, start=1)
    ]
    reserve = [
        {**_normalize_task(task), "alternate_ordinal": ordinal}
        for ordinal, task in enumerate(alternates, start=1)
    ]
    tasks = [*primary, *reserve]
    _require(
        len({task["task_id"] for task in tasks}) == len(tasks),
        "primary and alternate task identities must be disjoint",
    )
    _require(
        len({task["repository"] for task in tasks}) == len(tasks),
        "primary and alternate repositories must be globally unique",
    )
    return _sealed(
        {
            "schema_name": f"{SCHEMA_NAME}.private-pool",
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "selection_order_is_outcome_blind": True,
            "repository_uniqueness_rule": (
                "every primary and alternate uses a distinct repository"
            ),
            "primaries": primary,
            "alternates": reserve,
        },
        "private_pool_sha256",
    )


def validate_private_pool(pool: dict[str, Any]) -> None:
    keys = {
        "schema_name",
        "schema_version",
        "contract_version",
        "selection_order_is_outcome_blind",
        "repository_uniqueness_rule",
        "primaries",
        "alternates",
        "private_pool_sha256",
    }
    _require_exact_keys(pool, keys, "private pool fields drifted")
    _require(
        pool["schema_name"] == f"{SCHEMA_NAME}.private-pool"
        and pool["schema_version"] == SCHEMA_VERSION
        and pool["contract_version"] == CONTRACT_VERSION,
        "private pool schema drifted",
    )
    _require(pool["selection_order_is_outcome_blind"] is True, "private pool ordering drifted")
    _require(
        pool["repository_uniqueness_rule"]
        == "every primary and alternate uses a distinct repository",
        "private pool repository rule drifted",
    )
    _require(_identity_matches(pool, "private_pool_sha256"), "private pool identity mismatch")
    _require(
        isinstance(pool["primaries"], list) and isinstance(pool["alternates"], list),
        "private pool populations are malformed",
    )
    rebuilt = build_private_pool(
        [
            {key: value for key, value in task.items() if key != "population_slot"}
            for task in pool["primaries"]
        ],
        [
            {key: value for key, value in task.items() if key != "alternate_ordinal"}
            for task in pool["alternates"]
        ],
    )
    _require(canonical_bytes(rebuilt) == canonical_bytes(pool), "private pool is not canonical")


def _task_commitment(task: dict[str, Any]) -> str:
    return digest(task)


def public_pool_projection(pool: dict[str, Any]) -> dict[str, Any]:
    """Return the only pool representation permitted in tracked artifacts."""

    validate_private_pool(pool)
    return {
        "private_pool_sha256": pool["private_pool_sha256"],
        "primary_count": len(pool["primaries"]),
        "alternate_count": len(pool["alternates"]),
        "primary_slot_commitments": [
            {
                "population_slot": task["population_slot"],
                "task_commitment_sha256": _task_commitment(task),
            }
            for task in pool["primaries"]
        ],
        "alternate_order_commitments": [
            {
                "alternate_ordinal": task["alternate_ordinal"],
                "task_commitment_sha256": _task_commitment(task),
            }
            for task in pool["alternates"]
        ],
        "task_and_repository_identities_withheld": True,
        "repository_distinct_across_primary_and_alternates": True,
    }


def generate_schedule(primary_count: int, private_pool_sha256: str) -> dict[str, Any]:
    """Build deterministic 4N cells with AB/BA and a 2/2 Stage-1 prefix."""

    _require(
        type(primary_count) is int
        and MINIMUM_PRIMARY_TASKS <= primary_count <= MAXIMUM_PRIMARY_TASKS,
        "schedule primary count must be between 10 and 12",
    )
    _require(_sha256(private_pool_sha256), "schedule private-pool identity is invalid")
    first_arm = {
        slot: min(
            ARMS,
            key=lambda arm: _rank(private_pool_sha256, "first-arm", str(slot), arm),
        )
        for slot in range(1, primary_count + 1)
    }
    cells: list[dict[str, Any]] = []
    for repetition in range(1, REPETITIONS + 1):
        ordered_slots = sorted(
            range(1, primary_count + 1),
            key=lambda slot: (
                _rank(private_pool_sha256, "repetition", str(repetition), str(slot)),
                slot,
            ),
        )
        for slot in ordered_slots:
            arms = [first_arm[slot], next(arm for arm in ARMS if arm != first_arm[slot])]
            if repetition == 2:
                arms.reverse()
            for arm in arms:
                cells.append(
                    {
                        "position": len(cells) + 1,
                        "cell_id": f"effort-v2-slot-{slot:02d}-{arm}-rep-{repetition}",
                        "population_slot": slot,
                        "arm": arm,
                        "reasoning_effort": arm,
                        "repetition": repetition,
                    }
                )
    schedule = {
        "schema_name": f"{SCHEMA_NAME}.schedule",
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "algorithm": "SHA-256-ranked repetition blocks; per-slot AB/BA counterbalancing",
        "seed": SCHEDULE_SEED,
        "private_pool_sha256": private_pool_sha256,
        "primary_count": primary_count,
        "arms": list(ARMS),
        "repetitions_per_task_arm": REPETITIONS,
        "cells": cells,
        "manual_edits_permitted": False,
    }
    return _sealed(schedule, "schedule_sha256")


def _local_import_paths(root: Path, path: Path) -> set[Path]:
    """Resolve only repository-local Python imports for the frozen closure."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        raise ExperimentConfigurationError(
            f"harness source is unreadable or invalid Python: {path}"
        ) from error
    candidates: set[Path] = set()

    def add_module(module: str) -> None:
        parts = module.split(".")
        choices = [
            root / "src" / Path(*parts).with_suffix(".py"),
            root / "src" / Path(*parts) / "__init__.py",
            root / Path(*parts).with_suffix(".py"),
            root / Path(*parts) / "__init__.py",
            root / "scripts" / f"{parts[-1]}.py",
        ]
        for candidate in choices:
            if candidate.is_file():
                candidates.add(candidate)
                break

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_module(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if path.is_relative_to(root / "src" / "engineering_scope_guard"):
                    base = ["engineering_scope_guard"]
                    parent_parts = list(
                        path.relative_to(root / "src" / "engineering_scope_guard").parent.parts
                    )
                    if node.level > 1:
                        parent_parts = parent_parts[: -(node.level - 1)]
                    module = ".".join([*base, *parent_parts, *module.split(".")])
            if module:
                add_module(module)
            for alias in node.names:
                if alias.name != "*" and module:
                    add_module(f"{module}.{alias.name}")
    return candidates


def build_harness_source_closure(root: Path) -> dict[str, Any]:
    """Commit the exact v2 harness and every repository-local transitive import."""

    root = root.resolve(strict=True)
    pending = [root / relative for relative in _HARNESS_CLOSURE_SEEDS]
    seen: set[Path] = set()
    while pending:
        unresolved = pending.pop()
        _require(
            unresolved.is_file() and not unresolved.is_symlink(),
            "required harness source is missing or a symlink",
        )
        path = unresolved.resolve(strict=True)
        _require(path.is_relative_to(root), "harness source escapes repository root")
        if path in seen:
            continue
        seen.add(path)
        pending.extend(sorted(_local_import_paths(root, path) - seen))
    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(seen, key=lambda item: item.relative_to(root).as_posix())
    ]
    entrypoints = [
        {
            "name": name,
            "argv": argv,
            "command_identity_sha256": digest({"argv": argv}),
        }
        for name, argv in sorted(HARNESS_ENTRYPOINTS.items())
    ]
    body = {
        "schema_name": HARNESS_SOURCE_CLOSURE_SCHEMA,
        "schema_version": 1,
        "files": files,
        "file_set_sha256": digest(files),
        "entrypoints": entrypoints,
        "entrypoint_set_sha256": digest(entrypoints),
        "tests_private_and_raw_paths_included": False,
    }
    return {**body, "closure_sha256": digest(body)}


def validate_harness_source_closure(
    closure: Any, *, root: Path | None = None
) -> dict[str, Any]:
    closure = _require_exact_keys(
        closure,
        {
            "schema_name", "schema_version", "files", "file_set_sha256",
            "entrypoints", "entrypoint_set_sha256",
            "tests_private_and_raw_paths_included", "closure_sha256",
        },
        "harness source closure fields drifted",
    )
    files = closure["files"]
    _require(isinstance(files, list) and files, "harness source closure is empty")
    paths: list[str] = []
    for item in files:
        _require(
            isinstance(item, dict) and set(item) == {"path", "sha256"}
            and isinstance(item["path"], str) and item["path"]
            and not Path(item["path"]).is_absolute()
            and ".." not in Path(item["path"]).parts
            and not item["path"].startswith(("tests/", ".local/"))
            and _sha256(item["sha256"]),
            "harness source file commitment is invalid",
        )
        paths.append(item["path"])
    _require(paths == sorted(paths) and len(paths) == len(set(paths)), "harness source paths drifted")
    expected_entrypoints = [
        {"name": name, "argv": argv, "command_identity_sha256": digest({"argv": argv})}
        for name, argv in sorted(HARNESS_ENTRYPOINTS.items())
    ]
    _require(
        closure["schema_name"] == HARNESS_SOURCE_CLOSURE_SCHEMA
        and closure["schema_version"] == 1
        and closure["file_set_sha256"] == digest(files)
        and closure["entrypoints"] == expected_entrypoints
        and closure["entrypoint_set_sha256"] == digest(expected_entrypoints)
        and closure["tests_private_and_raw_paths_included"] is False
        and closure["closure_sha256"]
        == digest({key: value for key, value in closure.items() if key != "closure_sha256"}),
        "harness source closure identity drifted",
    )
    if root is not None:
        root = root.resolve(strict=True)
        for item in files:
            unresolved = root / item["path"]
            _require(
                unresolved.is_file() and not unresolved.is_symlink(),
                "frozen harness source is missing or a symlink",
            )
            resolved = unresolved.resolve(strict=True)
            _require(
                resolved.is_relative_to(root)
                and hashlib.sha256(resolved.read_bytes()).hexdigest() == item["sha256"],
                "frozen harness source closure drifted",
            )
        _require(
            build_harness_source_closure(root) == closure,
            "repository-local harness import closure drifted",
        )
    return closure


def build_prior_evidence_identity(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    files = []
    for relative in PRIOR_EVIDENCE_PATHS:
        unresolved = root / relative
        _require(
            unresolved.is_file() and not unresolved.is_symlink(),
            "required prior-evidence artifact is missing or a symlink",
        )
        path = unresolved.resolve(strict=True)
        _require(path.is_relative_to(root), "prior-evidence artifact escapes repository")
        files.append(
            {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    body = {
        "schema_version": 1,
        "files": files,
        "file_set_sha256": digest(files),
        "frozen_gap": (
            "prior evidence does not establish a causal LOW-versus-MEDIUM reasoning-"
            "effort effect on externally evaluated accepted outcomes"
        ),
        "prospective_addition": (
            "a protocol-valid complete experiment with at least 10 independent clusters "
            "supplies the direct external-evaluator acceptance and retry-inclusive work "
            "estimate absent from prior evidence"
        ),
        "exploratory_not_significance_or_equivalence": True,
    }
    return {**body, "prior_evidence_sha256": digest(body)}


def validate_prior_evidence_identity(
    value: Any, *, root: Path | None = None
) -> dict[str, Any]:
    value = _require_exact_keys(
        value,
        {
            "schema_version", "files", "file_set_sha256", "frozen_gap",
            "prospective_addition", "exploratory_not_significance_or_equivalence",
            "prior_evidence_sha256",
        },
        "prior-evidence identity fields drifted",
    )
    _require(
        isinstance(value["files"], list)
        and [item.get("path") for item in value["files"]] == list(PRIOR_EVIDENCE_PATHS)
        and all(
            isinstance(item, dict) and set(item) == {"path", "sha256"}
            and _sha256(item["sha256"])
            for item in value["files"]
        )
        and value["file_set_sha256"] == digest(value["files"])
        and isinstance(value["frozen_gap"], str) and bool(value["frozen_gap"])
        and isinstance(value["prospective_addition"], str)
        and bool(value["prospective_addition"])
        and value["exploratory_not_significance_or_equivalence"] is True
        and value["prior_evidence_sha256"]
        == digest({key: item for key, item in value.items() if key != "prior_evidence_sha256"}),
        "prior-evidence identity is malformed",
    )
    if root is not None:
        _require(
            build_prior_evidence_identity(root) == value,
            "frozen prior-evidence artifacts drifted",
        )
    return value


def build_contract(
    private_pool: dict[str, Any],
    *,
    model: str,
    codex_version: str,
    runtime_identity: str,
    source_identity: str,
    qualification_receipt_sha256: str,
    evaluator_identity: str,
    image_pool_identity: str,
    tool_configuration_identity: str,
    harness_source_closure: dict[str, Any] | None = None,
    prior_evidence_identity: dict[str, Any] | None = None,
    qualification_reliability_audit_sha256: str | None = None,
    research_question: str = (
        "Under one fixed current Codex model/runtime and heterogeneous externally "
        "evaluated coding tasks, how does native reasoning effort affect accepted "
        "outcome and agent work?"
    ),
    directional_hypothesis: str = (
        "Medium reasoning may change acceptance and measured work relative to low; "
        "neither direction is presumed."
    ),
    maximum_contentless_canary_subject_invocation_starts: int = 0,
    maximum_subject_invocation_starts: int = MAXIMUM_SUBJECT_INVOCATION_STARTS,
    subject_timeout_seconds: int = 900,
    evaluator_timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Freeze all pre-cell-1 fields without granting execution authority."""

    validate_private_pool(private_pool)
    for value in (
        model,
        codex_version,
        runtime_identity,
        source_identity,
        evaluator_identity,
        tool_configuration_identity,
        research_question,
        directional_hypothesis,
    ):
        _require(_nonempty(value), "frozen contract identity or question is empty")
    for field, value in (
        ("qualification_receipt_sha256", qualification_receipt_sha256),
        ("image_pool_identity", image_pool_identity),
    ):
        _require(_sha256(value), f"{field} must be lowercase SHA-256")
    _require(
        type(maximum_contentless_canary_subject_invocation_starts) is int
        and maximum_contentless_canary_subject_invocation_starts in (0, 1),
        "contentless canary maximum must be zero or one",
    )
    _require(
        type(subject_timeout_seconds) is int and subject_timeout_seconds > 0
        and type(evaluator_timeout_seconds) is int and evaluator_timeout_seconds > 0,
        "trajectory timeouts must be positive integers",
    )
    projection = public_pool_projection(private_pool)
    mandatory_starts = projection["primary_count"] * len(ARMS) * REPETITIONS
    _require(
        type(maximum_subject_invocation_starts) is int
        and mandatory_starts + maximum_contentless_canary_subject_invocation_starts
        <= maximum_subject_invocation_starts
        <= MAXIMUM_SUBJECT_INVOCATION_STARTS,
        "subject invocation cap cannot cover mandatory cells or exceeds the protocol maximum",
    )
    if harness_source_closure is None:
        harness_source_closure = build_harness_source_closure(
            Path(__file__).resolve().parents[2]
        )
    validate_harness_source_closure(harness_source_closure)
    if prior_evidence_identity is None:
        prior_evidence_identity = build_prior_evidence_identity(
            Path(__file__).resolve().parents[2]
        )
    validate_prior_evidence_identity(prior_evidence_identity)
    if qualification_reliability_audit_sha256 is None:
        qualification_reliability_audit_sha256 = digest(
            {"status": "provider-free-contract-fixture-not-live-authority"}
        )
    _require(
        _sha256(qualification_reliability_audit_sha256),
        "qualification reliability audit identity must be SHA-256",
    )
    schedule = generate_schedule(projection["primary_count"], pool_sha := projection["private_pool_sha256"])
    gate_policy_body = {
        "schema_version": 1,
        "status": "exploratory-publication-candidate-gate",
        "protocol_valid_and_stage_1_pass_required": True,
        "minimum_independent_admissible_clusters": 10,
        "complete_mandatory_schedule_required": True,
        "protocol_invalid_batch_stop_permitted": False,
        "evaluator_validity_required_for_every_admissible_record": True,
        "maximum_finite_primary_interval_width": 0.50,
        "prohibited_dispositions": [
            "INCONCLUSIVE", "EXPERIMENT INVALID / TERMINATED",
        ],
        "prior_evidence_sha256": prior_evidence_identity["prior_evidence_sha256"],
        "prior_evidence_gap": prior_evidence_identity["frozen_gap"],
        "prospective_direct_addition": prior_evidence_identity["prospective_addition"],
        "usefulness_requires": [
            "primary_acceptance_point_estimate",
            "primary_acceptance_interval",
            "retry_inclusive_work_result",
            "retry_inclusive_falsification_result",
        ],
        "materially_adds_derivation": (
            "prior_gap_and_direct_addition_match AND protocol_integrity AND admissibility "
            "AND evaluator_validity AND finite_uncertainty AND actual_usefulness_outputs"
        ),
        "candidate_justified_requires_materially_adds": True,
        "significance_or_equivalence_test": False,
    }
    gate_policy = {
        **gate_policy_body, "policy_sha256": digest(gate_policy_body)
    }
    contract = {
        "schema_name": f"{SCHEMA_NAME}.contract",
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": "frozen-provider-free-live-execution-not-authorized",
        "live_execution_authorized": False,
        "scientific_question": {
            "question": research_question,
            "directional_hypothesis": directional_hypothesis,
            "frozen_before_subject_outcomes": True,
        },
        "treatment": {
            "only_variable": "reasoning_effort",
            "arms": {arm: {"reasoning_effort": arm} for arm in ARMS},
            "low_is_not_assumed_better": True,
            "configuration_change_within_arm_permitted": False,
        },
        "runtime": {
            "model": model,
            "codex_version": codex_version,
            "runtime_identity": runtime_identity,
            "tool_configuration_identity": tool_configuration_identity,
            "sandbox": "workspace-write",
            "subject_network_access": False,
            "user_config_and_rules_loaded": False,
            "external_tools_disabled": True,
            "multi_agent_disabled": True,
        },
        "source": {
            "source_identity": source_identity,
            "qualification_receipt_sha256": qualification_receipt_sha256,
            "qualification_reliability_audit_sha256": (
                qualification_reliability_audit_sha256
            ),
            "evaluator_identity": evaluator_identity,
            "image_pool_identity": image_pool_identity,
            "harness_source_closure": deepcopy(harness_source_closure),
            "prior_evidence_identity": deepcopy(prior_evidence_identity),
            "private_pool": projection,
        },
        "schedule": schedule,
        "design": {
            "primary_task_count": projection["primary_count"],
            "alternate_task_count": projection["alternate_count"],
            "cell_count": projection["primary_count"] * len(ARMS) * REPETITIONS,
            "repository_distinct_across_primary_and_alternates": True,
            "repository_uniqueness_is_stricter_than_minimum_protocol": True,
            "repetitions_per_task_arm": REPETITIONS,
            "deterministic_population_and_order": True,
        },
        "trajectory": {
            "subject_invocations_per_attempt": 1,
            "prompt_delivery": "exact UTF-8 problem_statement bytes plus one LF on stdin",
            "fresh_subject_session_per_attempt": True,
            "subject_timeout_seconds": subject_timeout_seconds,
            "evaluator_timeout_seconds": evaluator_timeout_seconds,
        },
        "failure_taxonomy": {
            "experimental_outcomes": list(EXPERIMENTAL_OUTCOMES),
            "retryable_infrastructure": list(RETRYABLE_INFRASTRUCTURE),
            "alternate_activation_infrastructure_invalid": list(
                ALTERNATE_ACTIVATION_CLASSES
            ),
            "mandatory_batch_stop": list(MANDATORY_BATCH_STOP),
            "post_outcome_reclassification_permitted": False,
        },
        "alternate_activation": {
            "queue_order": "frozen alternate ordinal ascending",
            "maximum_activations": projection["alternate_count"],
            "maximum_activations_per_population_slot": 1,
            "requires_attempt_1_terminal_infrastructure_invalid": True,
            "requires_matching_durable_evidence_sha256": True,
            "requires_zero_completed_cells_for_population_slot": True,
            "subject_outcome_or_direction_may_trigger_activation": False,
            "activation_authorizes_attempt_2_not_attempt_3": True,
            "activation_resets_global_capacity": False,
        },
        "attempt_accounting": {
            "capacity_unit": "subject_invocation_started",
            "maximum_subject_invocation_starts": maximum_subject_invocation_starts,
            "maximum_contentless_canary_subject_invocation_starts": (
                maximum_contentless_canary_subject_invocation_starts
            ),
            "qualification_subject_invocation_starts": 0,
            "maximum_attempts_per_cell": MAXIMUM_ATTEMPTS_PER_CELL,
            "attempt_3_permitted": False,
            "attempt_2_requires_frozen_infrastructure_authorization": True,
            "never_started_mandatory_cells_retain_first_start_capacity": True,
            "completed_cells_never_repeat": True,
        },
        "outcomes": {
            "primary": "official evaluator acceptance",
            "missingness": "report by frozen arm and reason; no imputation",
            "experimental_failures_retained_in_assigned_arm": True,
            "secondary": [
                "input_tokens",
                "cached_input_tokens",
                "calculated_fresh_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
                "wall_time",
                "turns",
                "tool_actions",
                "search_actions",
                "correction_trajectory",
            ],
        },
        "analysis_policy": {
            "schema_version": 1,
            "bootstrap": {
                "seed": BOOTSTRAP_SEED,
                "resamples": BOOTSTRAP_RESAMPLES,
            },
            "termination_taxonomy": {
                "accepted": "accepted_completed",
                "admissible_failures": [
                    value for value in EXPERIMENTAL_OUTCOMES
                    if value != "accepted_completed"
                ],
                "inadmissible": [
                    *RETRYABLE_INFRASTRUCTURE,
                    *ALTERNATE_ACTIVATION_CLASSES,
                    *MANDATORY_BATCH_STOP,
                ],
                "timeout": "trajectory_timeout",
            },
            "work_policy": {
                "integer_fields": [
                    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                    "output_tokens", "reasoning_output_tokens", "turns", "tool_actions",
                    "search_actions", "correction_turns",
                ],
                "float_fields": ["wall_seconds"],
                "record_completeness": "all declared work fields present or all absent",
                "fresh_input_formula": (
                    "input_tokens - cached_input_tokens - cache_write_input_tokens"
                ),
                "accepted_conditional_denominator": (
                    "accepted admissible cells with complete work measurements"
                ),
                "accepted_conditional_is_descriptive_post_outcome_subset": True,
            },
            "disposition_policy": {
                "precedence": [
                    "EXPERIMENT INVALID / TERMINATED",
                    "LOW FAVORED",
                    "MEDIUM FAVORED",
                    "WORK DIFFERENCE WITHOUT ACCEPTANCE EVIDENCE",
                    "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED",
                    "INCONCLUSIVE",
                ],
                "favored_interval_rule": "cluster bootstrap interval strictly excludes zero",
                "missing_or_inadmissible": "INCONCLUSIVE",
                "no_material_abs_point_max": 0.10,
                "no_material_interval_lower_min": -0.25,
                "no_material_interval_upper_max": 0.25,
                "work_metric": "fresh_input_tokens",
            },
        },
        "esg_rr_002_gate_policy": gate_policy,
        "staging": {
            "stage_1_cell_count": STAGE_1_CELL_COUNT,
            "stage_1_cell_ids": [cell["cell_id"] for cell in schedule["cells"][:4]],
            "stage_1_arm_counts": {arm: 2 for arm in ARMS},
            "stage_1_cells_retained_in_analysis": True,
            "outcome_direction_used_for_continuation": False,
            "healthy_gate_continues_automatically": True,
        },
        "stop_rules": {
            "stop_at_global_subject_start_cap": True,
            "stop_on_mandatory_batch_stop": True,
            "attempt_3_permitted": False,
            "nonfrozen_alternate_permitted": False,
            "treatment_tuning_after_outcome_permitted": False,
            "second_or_confirmatory_experiment_permitted": False,
        },
        "claim_boundaries": {
            "exploratory_only": True,
            "equivalence_or_noninferiority_permitted": False,
            "billing_claim_permitted": False,
            "per_language_claim_permitted": False,
            "causal_mechanism_claim_permitted": False,
            "optimization_interpretation": "unnecessary work conditional on accepted outcome",
        },
        "privacy": {
            "private_pool_is_separate": True,
            "task_ids_in_contract": False,
            "repository_names_in_contract": False,
            "raw_tasks_patches_traces_and_logs_tracked": False,
        },
    }
    _require(schedule["private_pool_sha256"] == pool_sha, "schedule pool binding failed")
    return _sealed(contract, "contract_sha256")


def _validate_projection(projection: Any) -> dict[str, Any]:
    keys = {
        "private_pool_sha256",
        "primary_count",
        "alternate_count",
        "primary_slot_commitments",
        "alternate_order_commitments",
        "task_and_repository_identities_withheld",
        "repository_distinct_across_primary_and_alternates",
    }
    projection = _require_exact_keys(projection, keys, "public pool projection fields drifted")
    primary_count = projection["primary_count"]
    alternate_count = projection["alternate_count"]
    _require(
        type(primary_count) is int
        and MINIMUM_PRIMARY_TASKS <= primary_count <= MAXIMUM_PRIMARY_TASKS
        and type(alternate_count) is int
        and 0 <= alternate_count <= MAXIMUM_ALTERNATES,
        "public pool counts are invalid",
    )
    primary = projection["primary_slot_commitments"]
    alternates = projection["alternate_order_commitments"]
    _require(isinstance(primary, list) and isinstance(alternates, list), "pool commitments malformed")
    _require(
        all(
            isinstance(item, dict)
            and set(item) == {"population_slot", "task_commitment_sha256"}
            for item in primary
        )
        and [item["population_slot"] for item in primary]
        == list(range(1, primary_count + 1))
        and all(
            isinstance(item, dict)
            and set(item) == {"alternate_ordinal", "task_commitment_sha256"}
            for item in alternates
        )
        and [item["alternate_ordinal"] for item in alternates]
        == list(range(1, alternate_count + 1)),
        "public pool commitment order drifted",
    )
    commitments = [item["task_commitment_sha256"] for item in [*primary, *alternates]]
    _require(
        len(primary) == primary_count
        and len(alternates) == alternate_count
        and all(_sha256(value) for value in commitments)
        and len(set(commitments)) == len(commitments),
        "public pool commitments are invalid or repeated",
    )
    _require(
        _sha256(projection["private_pool_sha256"])
        and projection["task_and_repository_identities_withheld"] is True
        and projection["repository_distinct_across_primary_and_alternates"] is True,
        "public pool privacy or repository rule drifted",
    )
    return projection


def validate_contract(contract: dict[str, Any]) -> None:
    """Validate the canonical exact-field provider-free contract."""

    top_keys = {
        "schema_name", "schema_version", "contract_version", "status",
        "live_execution_authorized", "scientific_question", "treatment", "runtime",
        "source", "schedule", "design", "trajectory", "failure_taxonomy",
        "alternate_activation", "attempt_accounting", "outcomes", "analysis_policy",
        "esg_rr_002_gate_policy", "staging", "stop_rules", "claim_boundaries",
        "privacy", "contract_sha256",
    }
    _require_exact_keys(contract, top_keys, "reasoning-effort v2 contract fields drifted")
    _require(_identity_matches(contract, "contract_sha256"), "reasoning-effort v2 contract identity mismatch")
    _require(
        contract["schema_name"] == f"{SCHEMA_NAME}.contract"
        and contract["schema_version"] == SCHEMA_VERSION
        and contract["contract_version"] == CONTRACT_VERSION
        and contract["status"] == "frozen-provider-free-live-execution-not-authorized"
        and contract["live_execution_authorized"] is False,
        "reasoning-effort v2 status or schema drifted",
    )
    question = _require_exact_keys(
        contract["scientific_question"],
        {"question", "directional_hypothesis", "frozen_before_subject_outcomes"},
        "scientific question fields drifted",
    )
    _require(
        _nonempty(question["question"])
        and _nonempty(question["directional_hypothesis"])
        and question["frozen_before_subject_outcomes"] is True,
        "scientific question drifted",
    )
    _require(
        contract["treatment"]
        == {
            "only_variable": "reasoning_effort",
            "arms": {arm: {"reasoning_effort": arm} for arm in ARMS},
            "low_is_not_assumed_better": True,
            "configuration_change_within_arm_permitted": False,
        },
        "treatment fields drifted",
    )
    expected_gate_body = {
        "schema_version": 1,
        "status": "exploratory-publication-candidate-gate",
        "protocol_valid_and_stage_1_pass_required": True,
        "minimum_independent_admissible_clusters": 10,
        "complete_mandatory_schedule_required": True,
        "protocol_invalid_batch_stop_permitted": False,
        "evaluator_validity_required_for_every_admissible_record": True,
        "maximum_finite_primary_interval_width": 0.50,
        "prohibited_dispositions": [
            "INCONCLUSIVE", "EXPERIMENT INVALID / TERMINATED",
        ],
        "prior_evidence_sha256": contract["source"]["prior_evidence_identity"][
            "prior_evidence_sha256"
        ],
        "prior_evidence_gap": contract["source"]["prior_evidence_identity"]["frozen_gap"],
        "prospective_direct_addition": contract["source"]["prior_evidence_identity"][
            "prospective_addition"
        ],
        "usefulness_requires": [
            "primary_acceptance_point_estimate", "primary_acceptance_interval",
            "retry_inclusive_work_result", "retry_inclusive_falsification_result",
        ],
        "materially_adds_derivation": (
            "prior_gap_and_direct_addition_match AND protocol_integrity AND admissibility "
            "AND evaluator_validity AND finite_uncertainty AND actual_usefulness_outputs"
        ),
        "candidate_justified_requires_materially_adds": True,
        "significance_or_equivalence_test": False,
    }
    _require(
        contract["esg_rr_002_gate_policy"]
        == {**expected_gate_body, "policy_sha256": digest(expected_gate_body)},
        "ESG-RR-002 exploratory publication-candidate gate drifted",
    )
    runtime = _require_exact_keys(
        contract["runtime"],
        {
            "model", "codex_version", "runtime_identity", "tool_configuration_identity", "sandbox",
            "subject_network_access", "user_config_and_rules_loaded",
            "external_tools_disabled", "multi_agent_disabled",
        },
        "runtime fields drifted",
    )
    _require(
        all(
            _nonempty(runtime[key])
            for key in (
                "model", "codex_version", "runtime_identity", "tool_configuration_identity"
            )
        )
        and runtime["sandbox"] == "workspace-write"
        and runtime["subject_network_access"] is False
        and runtime["user_config_and_rules_loaded"] is False
        and runtime["external_tools_disabled"] is True
        and runtime["multi_agent_disabled"] is True,
        "runtime controls drifted",
    )
    source = _require_exact_keys(
        contract["source"],
        {
            "source_identity", "qualification_receipt_sha256", "evaluator_identity",
            "image_pool_identity", "qualification_reliability_audit_sha256",
            "harness_source_closure", "prior_evidence_identity", "private_pool",
        },
        "source fields drifted",
    )
    _require(
        _nonempty(source["source_identity"])
        and _nonempty(source["evaluator_identity"])
        and all(_sha256(source[field]) for field in _SHA_FIELDS)
        and _sha256(source["qualification_reliability_audit_sha256"]),
        "source qualification/evaluator/image binding drifted",
    )
    validate_harness_source_closure(source["harness_source_closure"])
    validate_prior_evidence_identity(source["prior_evidence_identity"])
    projection = _validate_projection(source["private_pool"])
    expected_schedule = generate_schedule(
        projection["primary_count"], projection["private_pool_sha256"]
    )
    _require(
        canonical_bytes(contract["schedule"]) == canonical_bytes(expected_schedule),
        "reasoning-effort v2 schedule is not canonical",
    )
    _require(
        contract["design"]
        == {
            "primary_task_count": projection["primary_count"],
            "alternate_task_count": projection["alternate_count"],
            "cell_count": projection["primary_count"] * 4,
            "repository_distinct_across_primary_and_alternates": True,
            "repository_uniqueness_is_stricter_than_minimum_protocol": True,
            "repetitions_per_task_arm": REPETITIONS,
            "deterministic_population_and_order": True,
        },
        "design fields drifted",
    )
    trajectory = _require_exact_keys(
        contract["trajectory"],
        {
            "subject_invocations_per_attempt", "prompt_delivery",
            "fresh_subject_session_per_attempt", "subject_timeout_seconds",
            "evaluator_timeout_seconds",
        },
        "trajectory fields drifted",
    )
    _require(
        trajectory["subject_invocations_per_attempt"] == 1
        and trajectory["prompt_delivery"]
        == "exact UTF-8 problem_statement bytes plus one LF on stdin"
        and trajectory["fresh_subject_session_per_attempt"] is True
        and type(trajectory["subject_timeout_seconds"]) is int
        and trajectory["subject_timeout_seconds"] > 0
        and type(trajectory["evaluator_timeout_seconds"]) is int
        and trajectory["evaluator_timeout_seconds"] > 0,
        "trajectory controls drifted",
    )
    _require(
        contract["failure_taxonomy"]
        == {
            "experimental_outcomes": list(EXPERIMENTAL_OUTCOMES),
            "retryable_infrastructure": list(RETRYABLE_INFRASTRUCTURE),
            "alternate_activation_infrastructure_invalid": list(ALTERNATE_ACTIVATION_CLASSES),
            "mandatory_batch_stop": list(MANDATORY_BATCH_STOP),
            "post_outcome_reclassification_permitted": False,
        },
        "failure taxonomy drifted",
    )
    _require(
        contract["alternate_activation"]
        == {
            "queue_order": "frozen alternate ordinal ascending",
            "maximum_activations": projection["alternate_count"],
            "maximum_activations_per_population_slot": 1,
            "requires_attempt_1_terminal_infrastructure_invalid": True,
            "requires_matching_durable_evidence_sha256": True,
            "requires_zero_completed_cells_for_population_slot": True,
            "subject_outcome_or_direction_may_trigger_activation": False,
            "activation_authorizes_attempt_2_not_attempt_3": True,
            "activation_resets_global_capacity": False,
        },
        "alternate activation contract drifted",
    )
    accounting = _require_exact_keys(
        contract["attempt_accounting"],
        {
            "capacity_unit", "maximum_subject_invocation_starts",
            "maximum_contentless_canary_subject_invocation_starts",
            "qualification_subject_invocation_starts", "maximum_attempts_per_cell",
            "attempt_3_permitted", "attempt_2_requires_frozen_infrastructure_authorization",
            "never_started_mandatory_cells_retain_first_start_capacity",
            "completed_cells_never_repeat",
        },
        "attempt accounting fields drifted",
    )
    canary_max = accounting["maximum_contentless_canary_subject_invocation_starts"]
    _require(
        accounting["capacity_unit"] == "subject_invocation_started"
        and type(accounting["maximum_subject_invocation_starts"]) is int
        and contract["design"]["cell_count"] + canary_max
        <= accounting["maximum_subject_invocation_starts"]
        <= MAXIMUM_SUBJECT_INVOCATION_STARTS
        and type(canary_max) is int and canary_max in (0, 1)
        and accounting["qualification_subject_invocation_starts"] == 0
        and accounting["maximum_attempts_per_cell"] == 2
        and accounting["attempt_3_permitted"] is False
        and accounting["attempt_2_requires_frozen_infrastructure_authorization"] is True
        and accounting["never_started_mandatory_cells_retain_first_start_capacity"] is True
        and accounting["completed_cells_never_repeat"] is True,
        "attempt accounting controls drifted",
    )
    _require(
        contract["outcomes"]
        == {
            "primary": "official evaluator acceptance",
            "missingness": "report by frozen arm and reason; no imputation",
            "experimental_failures_retained_in_assigned_arm": True,
            "secondary": [
                "input_tokens", "cached_input_tokens", "calculated_fresh_input_tokens",
                "output_tokens", "reasoning_output_tokens", "wall_time", "turns",
                "tool_actions", "search_actions", "correction_trajectory",
            ],
        },
        "outcome fields drifted",
    )
    _require(
        contract["analysis_policy"]
        == {
            "schema_version": 1,
            "bootstrap": {"seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES},
            "termination_taxonomy": {
                "accepted": "accepted_completed",
                "admissible_failures": [
                    value for value in EXPERIMENTAL_OUTCOMES
                    if value != "accepted_completed"
                ],
                "inadmissible": [
                    *RETRYABLE_INFRASTRUCTURE,
                    *ALTERNATE_ACTIVATION_CLASSES,
                    *MANDATORY_BATCH_STOP,
                ],
                "timeout": "trajectory_timeout",
            },
            "work_policy": {
                "integer_fields": [
                    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                    "output_tokens", "reasoning_output_tokens", "turns", "tool_actions",
                    "search_actions", "correction_turns",
                ],
                "float_fields": ["wall_seconds"],
                "record_completeness": "all declared work fields present or all absent",
                "fresh_input_formula": (
                    "input_tokens - cached_input_tokens - cache_write_input_tokens"
                ),
                "accepted_conditional_denominator": (
                    "accepted admissible cells with complete work measurements"
                ),
                "accepted_conditional_is_descriptive_post_outcome_subset": True,
            },
            "disposition_policy": {
                "precedence": [
                    "EXPERIMENT INVALID / TERMINATED", "LOW FAVORED", "MEDIUM FAVORED",
                    "WORK DIFFERENCE WITHOUT ACCEPTANCE EVIDENCE",
                    "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED", "INCONCLUSIVE",
                ],
                "favored_interval_rule": "cluster bootstrap interval strictly excludes zero",
                "missing_or_inadmissible": "INCONCLUSIVE",
                "no_material_abs_point_max": 0.10,
                "no_material_interval_lower_min": -0.25,
                "no_material_interval_upper_max": 0.25,
                "work_metric": "fresh_input_tokens",
            },
        },
        "analysis-policy fields drifted",
    )
    first_four = expected_schedule["cells"][:4]
    _require(
        contract["staging"]
        == {
            "stage_1_cell_count": 4,
            "stage_1_cell_ids": [cell["cell_id"] for cell in first_four],
            "stage_1_arm_counts": {arm: 2 for arm in ARMS},
            "stage_1_cells_retained_in_analysis": True,
            "outcome_direction_used_for_continuation": False,
            "healthy_gate_continues_automatically": True,
        }
        and {arm: sum(cell["arm"] == arm for cell in first_four) for arm in ARMS}
        == {arm: 2 for arm in ARMS},
        "Stage-1 fields drifted",
    )
    _require(
        contract["stop_rules"]
        == {
            "stop_at_global_subject_start_cap": True,
            "stop_on_mandatory_batch_stop": True,
            "attempt_3_permitted": False,
            "nonfrozen_alternate_permitted": False,
            "treatment_tuning_after_outcome_permitted": False,
            "second_or_confirmatory_experiment_permitted": False,
        },
        "stop-rule fields drifted",
    )
    _require(
        contract["claim_boundaries"]
        == {
            "exploratory_only": True,
            "equivalence_or_noninferiority_permitted": False,
            "billing_claim_permitted": False,
            "per_language_claim_permitted": False,
            "causal_mechanism_claim_permitted": False,
            "optimization_interpretation": "unnecessary work conditional on accepted outcome",
        },
        "claim boundaries drifted",
    )
    _require(
        contract["privacy"]
        == {
            "private_pool_is_separate": True,
            "task_ids_in_contract": False,
            "repository_names_in_contract": False,
            "raw_tasks_patches_traces_and_logs_tracked": False,
        },
        "privacy fields drifted",
    )


def validate_private_pool_binding(pool: dict[str, Any], contract: dict[str, Any]) -> None:
    validate_private_pool(pool)
    validate_contract(contract)
    _require(
        public_pool_projection(pool) == contract["source"]["private_pool"],
        "private pool differs from the frozen public commitment",
    )


def validate_frozen_identity(
    contract: dict[str, Any],
    *,
    expected_contract_sha256: str,
    expected_qualification_receipt_sha256: str,
    expected_evaluator_identity: str,
    expected_image_pool_identity: str,
) -> None:
    """Bind strict preflight to identities stored outside the candidate contract."""

    validate_contract(contract)
    _require(
        contract["contract_sha256"] == expected_contract_sha256,
        "frozen reasoning-effort v2 contract was replaced",
    )
    source = contract["source"]
    _require(
        source["qualification_receipt_sha256"]
        == expected_qualification_receipt_sha256,
        "frozen qualification receipt binding changed",
    )
    _require(
        source["evaluator_identity"] == expected_evaluator_identity,
        "frozen evaluator binding changed",
    )
    _require(
        source["image_pool_identity"] == expected_image_pool_identity,
        "frozen image-pool binding changed",
    )


def validate_attempt_number(attempt: int) -> None:
    _require(
        type(attempt) is int and attempt in (1, 2),
        "attempt must be 1 or 2; attempt 3 is forbidden",
    )


def _cell_maps(contract: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cells = contract["schedule"]["cells"]
    return cells, {cell["cell_id"]: cell for cell in cells}


def _replay_attempt_events(
    contract: dict[str, Any], events: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    validate_contract(contract)
    cells, by_id = _cell_maps(contract)
    projection = contract["source"]["private_pool"]
    maximum_subject_starts = contract["attempt_accounting"][
        "maximum_subject_invocation_starts"
    ]
    assignments = {
        item["population_slot"]: item["task_commitment_sha256"]
        for item in projection["primary_slot_commitments"]
    }
    alternates = {
        item["alternate_ordinal"]: item["task_commitment_sha256"]
        for item in projection["alternate_order_commitments"]
    }
    attempts: dict[str, list[int]] = {}
    active: dict[str, int] = {}
    subject_starts: set[tuple[str, int]] = set()
    evaluator_starts: set[tuple[str, int]] = set()
    finishes: dict[tuple[str, int], dict[str, Any]] = {}
    retry_authorized: set[str] = set()
    alternate_authorized: set[str] = set()
    completed: set[str] = set()
    completed_slots: set[int] = set()
    activated_slots: set[int] = set()
    used_alternates: list[int] = []
    canary_starts = 0
    batch_stop_classification: str | None = None
    batch_stop_event_recorded = False
    stage_1_boundary = False
    stage_1_audit_status: str | None = None
    stage_1_audit_sha256: str | None = None
    stage_1_receipt_set_sha256: str | None = None
    disk_safety_authorizations: set[tuple[str, int]] = set()
    disk_safety_protocol_seen = False

    def current_cell_id() -> str | None:
        return next((cell["cell_id"] for cell in cells if cell["cell_id"] not in completed), None)

    for event in events:
        _require_exact_keys(event, {"event_type", "payload"}, "attempt event fields drifted")
        event_type = event["event_type"]
        payload = event["payload"]
        _require(
            batch_stop_classification is None
            or event_type == "batch_stopped" and not batch_stop_event_recorded,
            "event follows a mandatory terminal batch stop",
        )
        if len(completed) == STAGE_1_CELL_COUNT and not stage_1_boundary:
            _require(
                event_type == "stage_1_boundary_reached",
                "Stage-1 boundary must be recorded before any further event",
            )
        if stage_1_boundary and stage_1_audit_status is None:
            _require(
                event_type in {"stage_1_audit_passed", "stage_1_audit_failed"},
                "Stage-1 audit must be recorded before cell 5",
            )
        if event_type in {
            "canary_subject_invocation_started", "canary_lifecycle_imported"
        }:
            expected_canary_keys = (
                {"evidence_sha256"}
                if event_type == "canary_subject_invocation_started"
                else {"lifecycle_terminal_event_sha256", "canary_receipt_sha256"}
            )
            _require_exact_keys(payload, expected_canary_keys, "canary event fields drifted")
            _require(
                not attempts and all(_sha256(value) for value in payload.values()),
                "canary must be contentless and precede all cell attempts",
            )
            canary_starts += 1
            _require(
                canary_starts
                <= contract["attempt_accounting"][
                    "maximum_contentless_canary_subject_invocation_starts"
                ],
                "contentless canary maximum exceeded",
            )
            _require(
                canary_starts + len(cells) <= maximum_subject_starts,
                "canary consumes capacity required by mandatory cells",
            )
            continue

        if event_type == "stage_1_boundary_reached":
            _require_exact_keys(
                payload,
                {"completed_cell_count", "completed_cell_ids", "receipt_set_sha256"},
                "Stage-1 boundary fields drifted",
            )
            expected_ids = [cell["cell_id"] for cell in cells[:STAGE_1_CELL_COUNT]]
            _require(
                not stage_1_boundary
                and len(completed) == STAGE_1_CELL_COUNT
                and payload["completed_cell_count"] == STAGE_1_CELL_COUNT
                and payload["completed_cell_ids"] == expected_ids
                and _sha256(payload["receipt_set_sha256"]),
                "Stage-1 boundary is out of sequence or unbound",
            )
            stage_1_boundary = True
            stage_1_receipt_set_sha256 = payload["receipt_set_sha256"]
            continue

        if event_type in {"stage_1_audit_passed", "stage_1_audit_failed"}:
            _require_exact_keys(
                payload,
                {"audit", "audit_sha256"},
                "Stage-1 audit event fields drifted",
            )
            audit = _require_exact_keys(
                payload["audit"],
                {
                    "schema_version", "status", "criteria", "completed_cell_count",
                    "completed_cell_ids", "receipt_set_sha256",
                    "outcome_fields_inspected", "outcome_values_emitted",
                },
                "Stage-1 audit fields drifted",
            )
            criteria = _require_exact_keys(
                audit["criteria"],
                set(STAGE_1_AUDIT_CRITERIA),
                "Stage-1 audit criteria drifted",
            )
            expected_status = (
                "pass" if event_type == "stage_1_audit_passed" else "fail"
            )
            expected_ids = [cell["cell_id"] for cell in cells[:STAGE_1_CELL_COUNT]]
            _require(
                stage_1_boundary
                and stage_1_audit_status is None
                and type(audit["schema_version"]) is int
                and audit["schema_version"] == 1
                and audit["status"] == expected_status
                and audit["completed_cell_count"] == STAGE_1_CELL_COUNT
                and audit["completed_cell_ids"] == expected_ids
                and audit["receipt_set_sha256"] == stage_1_receipt_set_sha256
                and audit["outcome_fields_inspected"] is False
                and audit["outcome_values_emitted"] is False
                and all(type(value) is bool for value in criteria.values())
                and payload["audit_sha256"] == digest(audit),
                "Stage-1 audit is malformed, outcome-bearing, or unbound",
            )
            _require(
                (expected_status == "pass" and all(criteria.values()))
                or (expected_status == "fail" and not all(criteria.values())),
                "Stage-1 audit status disagrees with its content-free criteria",
            )
            stage_1_audit_status = expected_status
            stage_1_audit_sha256 = payload["audit_sha256"]
            if expected_status == "fail":
                batch_stop_classification = "stage_1_audit_failed"
            continue

        _require(isinstance(payload, dict), "attempt event payload is malformed")
        cell_id = payload.get("cell_id")
        _require(cell_id in by_id, "attempt event references an unknown cell")
        cell = by_id[cell_id]
        slot = cell["population_slot"]
        if event_type == "disk_safety_checked":
            disk_safety_protocol_seen = True
            _require_exact_keys(
                payload,
                {"cell_id", "attempt", "receipt", "receipt_sha256"},
                "disk-safety event fields drifted",
            )
            attempt = payload["attempt"]
            validate_attempt_number(attempt)
            receipt = _require_exact_keys(
                payload["receipt"],
                {
                    "schema_name", "schema_version", "status", "policy_sha256",
                    "failures", "dynamic_host_metadata_withheld",
                },
                "disk-safety receipt fields drifted",
            )
            key = (cell_id, attempt)
            _require(
                cell_id == current_cell_id()
                and cell_id not in active
                and key not in disk_safety_authorizations
                and receipt["schema_name"]
                == "engineering-scope-guard.experiment-disk-safety-public"
                and receipt["schema_version"] == 1
                and receipt["status"] in {"pass", "fail"}
                and _sha256(receipt["policy_sha256"])
                and isinstance(receipt["failures"], list)
                and all(isinstance(value, str) and value for value in receipt["failures"])
                and receipt["dynamic_host_metadata_withheld"] is True
                and payload["receipt_sha256"] == digest(receipt),
                "disk-safety evidence is malformed, repeated, or out of sequence",
            )
            if attempt == 2:
                _require(
                    cell_id in retry_authorized or cell_id in alternate_authorized,
                    "disk-safety attempt 2 lacks frozen authorization",
                )
            if receipt["status"] == "pass":
                _require(not receipt["failures"], "passing disk-safety receipt has failures")
                disk_safety_authorizations.add(key)
            else:
                _require(bool(receipt["failures"]), "failed disk-safety receipt lacks reasons")
                batch_stop_classification = "durable_evidence_incomplete"
                batch_stop_event_recorded = True
        elif event_type == "attempt_started":
            _require_exact_keys(
                payload,
                {"cell_id", "attempt", "effective_task_commitment_sha256"},
                "attempt-start fields drifted",
            )
            attempt = payload["attempt"]
            validate_attempt_number(attempt)
            starts = attempts.setdefault(cell_id, [])
            _require(cell_id == current_cell_id(), "attempt violates frozen schedule order")
            _require(cell_id not in active, "prior attempt is not terminal")
            _require(attempt == len(starts) + 1, "attempt number is repeated or out of sequence")
            _require(
                not disk_safety_protocol_seen
                or (cell_id, attempt) in disk_safety_authorizations,
                "attempt start lacks the frozen D-068 disk-safety check",
            )
            _require(
                payload["effective_task_commitment_sha256"] == assignments[slot],
                "attempt uses the wrong frozen effective task",
            )
            if attempt == 2:
                _require(
                    cell_id in retry_authorized or cell_id in alternate_authorized,
                    "attempt 2 lacks frozen infrastructure authorization",
                )
            starts.append(attempt)
            active[cell_id] = attempt
            disk_safety_authorizations.discard((cell_id, attempt))
        elif event_type == "capacity_exhausted":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "requested_attempt", "classification",
                    "canary_subject_invocation_starts",
                    "experiment_subject_invocation_starts",
                    "never_started_mandatory_cells",
                    "projected_subject_invocation_starts_with_reservation",
                    "maximum_subject_invocation_starts",
                },
                "capacity exhaustion fields drifted",
            )
            requested_attempt = payload["requested_attempt"]
            validate_attempt_number(requested_attempt)
            started_cells = {started_cell for started_cell, _ in subject_starts}
            never_started = sum(
                frozen["cell_id"] not in started_cells for frozen in cells
            )
            projected_never_started = never_started - (
                1 if cell_id not in started_cells else 0
            )
            projected = (
                canary_starts + len(subject_starts) + 1 + projected_never_started
            )
            _require(
                cell_id == current_cell_id()
                and cell_id not in active
                and payload["classification"] == "durable_evidence_incomplete"
                and payload["canary_subject_invocation_starts"] == canary_starts
                and payload["experiment_subject_invocation_starts"] == len(subject_starts)
                and payload["never_started_mandatory_cells"] == never_started
                and payload["projected_subject_invocation_starts_with_reservation"] == projected
                and payload["maximum_subject_invocation_starts"]
                == maximum_subject_starts
                and projected > maximum_subject_starts,
                "capacity exhaustion does not prove the frozen pre-start boundary",
            )
            if requested_attempt == 2:
                _require(
                    cell_id in retry_authorized or cell_id in alternate_authorized,
                    "capacity exhaustion attempt 2 lacks frozen authorization",
                )
            batch_stop_classification = "durable_evidence_incomplete"
            batch_stop_event_recorded = True
        elif event_type == "subject_invocation_started":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "attempt", "effective_task_commitment_sha256",
                    "command_sha256", "ownership_token_sha256", "process_identity_sha256",
                },
                "subject-start fields drifted",
            )
            attempt = payload["attempt"]
            validate_attempt_number(attempt)
            key = (cell_id, attempt)
            _require(
                active.get(cell_id) == attempt
                and key not in subject_starts
                and payload["effective_task_commitment_sha256"] == assignments[slot]
                and payload["command_sha256"] == subject_command_identity(contract, cell_id),
                "subject invocation start is out of sequence or identity",
            )
            _require(
                _sha256(payload["ownership_token_sha256"])
                and _sha256(payload["process_identity_sha256"]),
                "subject invocation ownership binding is malformed",
            )
            subject_starts.add(key)
            never_started = sum(
                not any(start_cell == frozen["cell_id"] for start_cell, _ in subject_starts)
                for frozen in cells
            )
            _require(
                canary_starts + len(subject_starts) + never_started
                <= maximum_subject_starts,
                "subject start would consume capacity reserved for mandatory cells",
            )
        elif event_type == "attempt_finished":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "attempt", "classification", "evidence_sha256",
                    "effective_task_commitment_sha256", "subject_invocation_started",
                },
                "attempt-finish fields drifted",
            )
            attempt = payload["attempt"]
            validate_attempt_number(attempt)
            key = (cell_id, attempt)
            classification = payload["classification"]
            allowed = (
                set(EXPERIMENTAL_OUTCOMES)
                | set(RETRYABLE_INFRASTRUCTURE)
                | set(ALTERNATE_ACTIVATION_CLASSES)
                | set(MANDATORY_BATCH_STOP)
            )
            _require(
                active.get(cell_id) == attempt
                and key not in finishes
                and classification in allowed
                and _sha256(payload["evidence_sha256"])
                and payload["effective_task_commitment_sha256"] == assignments[slot]
                and payload["subject_invocation_started"] is (key in subject_starts),
                "attempt finish is out of sequence or inconsistent",
            )
            _require(
                classification not in EXPERIMENTAL_OUTCOMES or key in subject_starts,
                "experimental outcome lacks a subject invocation start",
            )
            finishes[key] = payload
            del active[cell_id]
            if classification in MANDATORY_BATCH_STOP:
                batch_stop_classification = classification
        elif event_type == "evaluator_invocation_started":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "attempt", "effective_task_commitment_sha256",
                    "evaluator_command_sha256", "ownership_token_sha256",
                    "process_identity_sha256", "container_identity_sha256",
                },
                "evaluator-start fields drifted",
            )
            attempt = payload["attempt"]
            validate_attempt_number(attempt)
            key = (cell_id, attempt)
            _require(
                active.get(cell_id) == attempt
                and key in subject_starts
                and key not in evaluator_starts
                and payload["effective_task_commitment_sha256"] == assignments[slot]
                and all(
                    _sha256(payload[field])
                    for field in (
                        "evaluator_command_sha256", "ownership_token_sha256",
                        "process_identity_sha256", "container_identity_sha256",
                    )
                ),
                "evaluator invocation start is out of sequence or identity",
            )
            evaluator_starts.add(key)
        elif event_type == "batch_stopped":
            _require_exact_keys(
                payload,
                {"cell_id", "attempt", "classification", "evidence_sha256"},
                "batch-stop fields drifted",
            )
            finish = finishes.get((cell_id, payload.get("attempt")))
            exhausted_attempt_2 = (
                finish is not None
                and payload.get("attempt") == 2
                and finish["classification"]
                in {*RETRYABLE_INFRASTRUCTURE, *ALTERNATE_ACTIVATION_CLASSES}
                and payload.get("classification") == "durable_evidence_incomplete"
                and payload.get("evidence_sha256") == finish["evidence_sha256"]
            )
            if exhausted_attempt_2:
                batch_stop_classification = "durable_evidence_incomplete"
            batch_stop_event_recorded = True
            _require(
                payload["cell_id"] == cell_id
                and payload["attempt"] in (1, 2)
                and payload["classification"] == batch_stop_classification
                and payload["classification"] in MANDATORY_BATCH_STOP
                and _sha256(payload["evidence_sha256"]),
                "batch-stop event is inconsistent with terminal attempt",
            )
        elif event_type == "attempt_2_authorized":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "prior_attempt", "next_attempt", "classification",
                    "evidence_sha256", "effective_task_commitment_sha256",
                },
                "attempt-2 authorization fields drifted",
            )
            finish = finishes.get((cell_id, 1))
            _require(
                finish is not None
                and payload["prior_attempt"] == 1
                and payload["next_attempt"] == 2
                and finish["classification"] in RETRYABLE_INFRASTRUCTURE
                and payload["classification"] == finish["classification"]
                and payload["evidence_sha256"] == finish["evidence_sha256"]
                and payload["effective_task_commitment_sha256"] == assignments[slot]
                and cell_id not in retry_authorized
                and cell_id not in alternate_authorized,
                "attempt 2 authorization lacks matching frozen retryable evidence",
            )
            retry_authorized.add(cell_id)
        elif event_type == "alternate_activated":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "population_slot", "trigger_attempt", "classification",
                    "evidence_sha256", "replaces_task_commitment_sha256",
                    "alternate_ordinal", "alternate_task_commitment_sha256",
                    "next_attempt", "subject_outcome_used", "outcome_direction_inspected",
                },
                "alternate activation fields drifted",
            )
            finish = finishes.get((cell_id, 1))
            ordinal = payload["alternate_ordinal"]
            _require(
                finish is not None
                and finish["classification"] in ALTERNATE_ACTIVATION_CLASSES
                and payload["classification"] == finish["classification"]
                and payload["trigger_attempt"] == 1
                and payload["next_attempt"] == 2
                and payload["population_slot"] == slot
                and payload["evidence_sha256"] == finish["evidence_sha256"]
                and payload["replaces_task_commitment_sha256"] == assignments[slot]
                and ordinal == len(used_alternates) + 1
                and alternates.get(ordinal) == payload["alternate_task_commitment_sha256"]
                and slot not in completed_slots
                and slot not in activated_slots
                and cell_id not in retry_authorized
                and cell_id not in alternate_authorized
                and payload["subject_outcome_used"] is False
                and payload["outcome_direction_inspected"] is False,
                "alternate activation is not the next frozen outcome-blind replacement",
            )
            assignments[slot] = alternates[ordinal]
            used_alternates.append(ordinal)
            activated_slots.add(slot)
            alternate_authorized.add(cell_id)
        elif event_type == "cell_completed":
            _require_exact_keys(
                payload,
                {
                    "cell_id", "attempt", "classification", "evidence_sha256",
                    "effective_task_commitment_sha256",
                },
                "cell-completion fields drifted",
            )
            attempt = payload["attempt"]
            validate_attempt_number(attempt)
            finish = finishes.get((cell_id, attempt))
            _require(
                cell_id == current_cell_id()
                and finish is not None
                and finish["classification"] in EXPERIMENTAL_OUTCOMES
                and payload["classification"] == finish["classification"]
                and payload["evidence_sha256"] == finish["evidence_sha256"]
                and payload["effective_task_commitment_sha256"] == assignments[slot]
                and finish["effective_task_commitment_sha256"] == assignments[slot]
                and cell_id not in completed,
                "cell completion lacks matching terminal experimental evidence",
            )
            completed.add(cell_id)
            completed_slots.add(slot)
        else:
            raise ExperimentConfigurationError("unsupported attempt event type")
    return {
        "canary_subject_invocation_starts": canary_starts,
        "experiment_subject_invocation_starts": len(subject_starts),
        "total_subject_invocation_starts": canary_starts + len(subject_starts),
        "completed_cells": len(completed),
        "used_alternate_ordinals": used_alternates,
        "activated_population_slots": sorted(activated_slots),
        "effective_task_commitment_by_slot": assignments,
        "next_cell_id": current_cell_id(),
        "batch_stop_classification": batch_stop_classification,
        "stage_1_boundary_reached": stage_1_boundary,
        "stage_1_audit_status": stage_1_audit_status,
        "stage_1_audit_sha256": stage_1_audit_sha256,
        "stage_1_receipt_set_sha256": stage_1_receipt_set_sha256,
    }


def validate_attempt_events(
    contract: dict[str, Any], events: Iterable[dict[str, Any]]
) -> None:
    """Replay the ordered ledger and reject illegal attempts or replacements."""

    _replay_attempt_events(contract, events)


def replay_attempt_state(
    contract: dict[str, Any], events: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Return content-free replay state after full provider-free validation."""

    return _replay_attempt_events(contract, events)


def validate_subject_start_budget(
    contract: dict[str, Any], events: Iterable[dict[str, Any]]
) -> None:
    """Validate actual canary/cell starts and reserved mandatory-cell capacity."""

    _replay_attempt_events(contract, events)


def subject_command_arguments(
    contract: dict[str, Any], cell_id: str, *, codex_binary: str = "<CODEX_BINARY>"
) -> list[str]:
    """Return the exact closed fresh-session command for one scheduled cell."""

    validate_contract(contract)
    cell = next(
        (item for item in contract["schedule"]["cells"] if item["cell_id"] == cell_id),
        None,
    )
    _require(cell is not None, "subject command cell is absent from frozen schedule")
    from .launch_surface import build_launch_profile, rendered_command

    profile = build_launch_profile(
        executable=codex_binary,
        model=contract["runtime"]["model"],
        reasoning_effort=cell["reasoning_effort"],
    )
    return rendered_command(profile)


def subject_command_identity(contract: dict[str, Any], cell_id: str) -> str:
    """Return the path-independent identity of the exact frozen subject command."""

    return digest(subject_command_arguments(contract, cell_id))


def validate_analysis_terminal_envelope(
    contract: dict[str, Any], envelope: dict[str, Any]
) -> dict[str, Any]:
    """Validate the exact public-safe terminal bridge and return a safe copy."""

    validate_contract(contract)
    _require_exact_keys(
        envelope,
        {
            "schema_name", "schema_version", "contract_sha256", "private_pool_sha256",
            "schedule_sha256", "live_seal_sha256", "ledger_binding",
            "receipt_set_sha256", "qualification_receipt_sha256", "evaluator_identity",
            "image_pool_identity", "repository_commitment_source", "protocol_valid",
            "batch_stop_classification", "stage_1_audit_sha256", "terminal_status",
            "subject_start_accounting", "effective_assignments",
            "receipt_projections", "records",
            "envelope_sha256",
        },
        "analysis terminal envelope fields drifted",
    )
    body = {key: value for key, value in envelope.items() if key != "envelope_sha256"}
    ledger = _require_exact_keys(
        envelope["ledger_binding"],
        {"schema_name", "schema_version", "event_count", "head_event_sha256"},
        "analysis ledger binding fields drifted",
    )
    subject_starts = _require_exact_keys(
        envelope["subject_start_accounting"],
        {
            "canary_subject_invocation_starts",
            "experiment_subject_invocation_starts",
            "total_subject_invocation_starts",
        },
        "analysis subject-start accounting fields drifted",
    )
    canary_starts = subject_starts["canary_subject_invocation_starts"]
    experiment_starts = subject_starts["experiment_subject_invocation_starts"]
    total_starts = subject_starts["total_subject_invocation_starts"]
    accounting = contract["attempt_accounting"]
    projection = contract["source"]["private_pool"]
    complete = envelope["terminal_status"] == "complete"
    invalid = envelope["terminal_status"] == "invalid_terminated"
    _require(
        envelope["schema_name"] == ANALYSIS_ENVELOPE_SCHEMA
        and type(envelope["schema_version"]) is int
        and envelope["schema_version"] == SCHEMA_VERSION
        and envelope["envelope_sha256"] == digest(body)
        and envelope["contract_sha256"] == contract["contract_sha256"]
        and envelope["private_pool_sha256"] == projection["private_pool_sha256"]
        and envelope["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
        and _sha256(envelope["live_seal_sha256"])
        and _sha256(envelope["receipt_set_sha256"])
        and envelope["qualification_receipt_sha256"]
        == contract["source"]["qualification_receipt_sha256"]
        and envelope["evaluator_identity"] == contract["source"]["evaluator_identity"]
        and envelope["image_pool_identity"] == contract["source"]["image_pool_identity"]
        and envelope["repository_commitment_source"]
        == "task_commitment_sha256_under_frozen_global_repository_uniqueness"
        and type(envelope["protocol_valid"]) is bool
        and (
            complete
            and envelope["protocol_valid"] is True
            and envelope["batch_stop_classification"] is None
            or invalid
            and envelope["protocol_valid"] is False
            and envelope["batch_stop_classification"] in MANDATORY_BATCH_STOP
        )
        and (
            complete and _sha256(envelope["stage_1_audit_sha256"])
            or invalid
            and (
                envelope["stage_1_audit_sha256"] is None
                or _sha256(envelope["stage_1_audit_sha256"])
            )
        )
        and (
            envelope["batch_stop_classification"] != "stage_1_audit_failed"
            or _sha256(envelope["stage_1_audit_sha256"])
        )
        and ledger["schema_name"]
        == "engineering-scope-guard.reasoning-effort-v2-ledger"
        and ledger["schema_version"] == SCHEMA_VERSION
        and type(ledger["event_count"]) is int
        and ledger["event_count"] > 0
        and _sha256(ledger["head_event_sha256"]),
        "analysis terminal envelope is unbound or internally inconsistent",
    )
    _require(
        type(canary_starts) is int
        and canary_starts in (0, 1)
        and canary_starts
        <= accounting["maximum_contentless_canary_subject_invocation_starts"]
        and type(experiment_starts) is int
        and experiment_starts >= 0
        and type(total_starts) is int
        and total_starts == canary_starts + experiment_starts
        and total_starts <= accounting["maximum_subject_invocation_starts"]
        <= MAXIMUM_SUBJECT_INVOCATION_STARTS,
        "analysis subject-start accounting exceeds or differs from the frozen budget",
    )
    slots = envelope["effective_assignments"]
    _require(
        isinstance(slots, list) and len(slots) == projection["primary_count"],
        "analysis effective assignment count drifted",
    )
    primary = {
        item["population_slot"]: item["task_commitment_sha256"]
        for item in projection["primary_slot_commitments"]
    }
    alternates = {
        item["alternate_ordinal"]: item["task_commitment_sha256"]
        for item in projection["alternate_order_commitments"]
    }
    used: list[int] = []
    for expected_slot, slot in enumerate(slots, start=1):
        _require_exact_keys(
            slot,
            {
                "population_slot", "task_commitment_sha256", "repository_commitment_sha256",
                "alternate_activated", "alternate_ordinal",
            },
            "analysis effective assignment fields drifted",
        )
        ordinal = slot["alternate_ordinal"]
        expected = alternates.get(ordinal) if slot["alternate_activated"] else primary[expected_slot]
        _require(
            slot["population_slot"] == expected_slot
            and type(slot["alternate_activated"]) is bool
            and slot["task_commitment_sha256"] == expected
            and slot["repository_commitment_sha256"] == expected
            and (
                slot["alternate_activated"] and type(ordinal) is int
                or not slot["alternate_activated"] and ordinal is None
            ),
            "analysis effective assignment is not a frozen primary/alternate mapping",
        )
        if ordinal is not None:
            used.append(ordinal)
    _require(
        sorted(used) == list(range(1, len(used) + 1)),
        "analysis alternate set skipped or reused a frozen ordinal",
    )
    records = envelope["records"]
    _require(isinstance(records, list), "analysis records are malformed")
    cells = {cell["cell_id"]: cell for cell in contract["schedule"]["cells"]}
    assignments = {slot["population_slot"]: slot for slot in slots}
    receipt_projections = envelope["receipt_projections"]
    _require(
        isinstance(receipt_projections, list),
        "analysis receipt projections are malformed",
    )
    receipt_by_attempt: dict[tuple[str, int], dict[str, Any]] = {}
    receipt_bindings: list[dict[str, Any]] = []
    allowed_terminations = (
        set(EXPERIMENTAL_OUTCOMES)
        | set(RETRYABLE_INFRASTRUCTURE)
        | set(ALTERNATE_ACTIVATION_CLASSES)
        | set(MANDATORY_BATCH_STOP)
    )
    for receipt in receipt_projections:
        _require_exact_keys(
            receipt, TERMINAL_RECEIPT_KEYS, "terminal receipt projection fields drifted"
        )
        receipt_record = _require_exact_keys(
            receipt["analysis_record"],
            TERMINAL_ANALYSIS_RECORD_KEYS,
            "terminal receipt analysis fields drifted",
        )
        key = (receipt["cell_id"], receipt["attempt"])
        receipt_body = {
            field: value
            for field, value in receipt.items()
            if field != "terminal_receipt_sha256"
        }
        artifact_common = {
            "schema_name", "schema_version", "contract_sha256", "schedule_sha256",
            "cell_id", "attempt", "effective_task_commitment_sha256", "receipt_sha256",
        }
        execution = _require_exact_keys(
            receipt["execution_artifact"],
            artifact_common | {
                "subject_invocation_started", "command_sha256", "status", "timed_out",
                "subject_exit_code", "ownership_token_sha256", "process_identity_sha256",
                "container_identity_sha256", "subject_stdout_sha256",
                "subject_stderr_sha256", "prediction_sha256", "patch_sha256",
                "cleanup_receipt_sha256",
            },
            "terminal execution artifact fields drifted",
        )
        evaluator = _require_exact_keys(
            receipt["evaluator_artifact"],
            artifact_common | {
                "evaluator_identity", "disposition", "anomaly_codes",
                "evaluator_stdout_sha256", "evaluator_stderr_sha256",
                "report_sha256", "results_sha256", "invocation_started",
                "evaluator_command_sha256", "ownership_token_sha256",
                "process_identity_sha256", "container_identity_sha256",
            },
            "terminal evaluator artifact fields drifted",
        )
        measurement = _require_exact_keys(
            receipt["measurement_artifact"],
            artifact_common | {"record_completeness", *INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS},
            "terminal measurement artifact fields drifted",
        )
        def artifact_bytes(value: dict[str, Any]) -> bytes:
            return canonical_bytes(value)
        artifacts_valid = True
        for artifact, schema, byte_sha in (
            (execution, "engineering-scope-guard.reasoning-effort-v2-execution-artifact", receipt["execution_receipt_sha256"]),
            (evaluator, "engineering-scope-guard.reasoning-effort-v2-evaluator-artifact", receipt["evaluator_receipt_sha256"]),
            (measurement, "engineering-scope-guard.reasoning-effort-v2-measurement-artifact", receipt["measurement_receipt_sha256"]),
        ):
            artifact_body = {field: value for field, value in artifact.items() if field != "receipt_sha256"}
            artifacts_valid = artifacts_valid and (
                artifact["schema_name"] == schema
                and artifact["schema_version"] == SCHEMA_VERSION
                and artifact["contract_sha256"] == contract["contract_sha256"]
                and artifact["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
                and artifact["cell_id"] == receipt["cell_id"]
                and artifact["attempt"] == receipt["attempt"]
                and artifact["effective_task_commitment_sha256"] == receipt["effective_task_commitment_sha256"]
                and artifact["receipt_sha256"] == digest(artifact_body)
                and hashlib.sha256(artifact_bytes(artifact)).hexdigest() == byte_sha
            )
        disposition_map = {
            "accepted": "accepted_completed",
            "test_failure": "evaluator_test_failure",
            "empty_patch": "empty_patch_failure",
            "error": "official_evaluator_error",
            "incomplete": "official_evaluator_incomplete",
            "not_run": None,
        }
        execution_statuses = {
            "returned", "agent_subject_failure", "trajectory_timeout",
            "provider_api_infrastructure_failure",
            "local_docker_runtime_infrastructure_failure",
        } | set(ALTERNATE_ACTIVATION_CLASSES) | set(MANDATORY_BATCH_STOP)
        derived_classification = (
            disposition_map.get(evaluator["disposition"])
            if execution["status"] == "returned"
            else execution["status"]
        )
        measurement_values = [
            measurement[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)
        ]
        measurement_valid = (
            measurement["record_completeness"] == "complete"
            and all(value is not None for value in measurement_values)
            or measurement["record_completeness"] == "absent"
            and all(value is None for value in measurement_values)
        )
        _require(
            receipt["schema_name"]
            == "engineering-scope-guard.reasoning-effort-v2-terminal-receipt"
            and type(receipt["schema_version"]) is int
            and receipt["schema_version"] == SCHEMA_VERSION
            and receipt["contract_sha256"] == contract["contract_sha256"]
            and receipt["schedule_sha256"] == contract["schedule"]["schedule_sha256"]
            and receipt["cell_id"] in cells
            and type(receipt["attempt"]) is int
            and receipt["attempt"] in (1, 2)
            and key not in receipt_by_attempt
            and _sha256(receipt["effective_task_commitment_sha256"])
            and type(receipt["subject_invocation_started"]) is bool
            and (
                receipt["subject_invocation_started"]
                and _sha256(receipt["command_sha256"])
                or not receipt["subject_invocation_started"]
                and receipt["command_sha256"] is None
            )
            and receipt["classification"] in allowed_terminations
            and _sha256(receipt["execution_receipt_sha256"])
            and _sha256(receipt["evaluator_receipt_sha256"])
            and _sha256(receipt["measurement_receipt_sha256"])
            and artifacts_valid
            and execution["subject_invocation_started"] is receipt["subject_invocation_started"]
            and execution["command_sha256"] == receipt["command_sha256"]
            and (
                not receipt["subject_invocation_started"]
                or receipt["command_sha256"] == subject_command_identity(contract, receipt["cell_id"])
            )
            and execution["status"] in execution_statuses
            and evaluator["disposition"] in disposition_map
            and derived_classification == receipt["classification"]
            and (
                execution["status"] == "returned" and evaluator["disposition"] != "not_run"
                or execution["status"] != "returned"
                and evaluator["disposition"]
                == ("incomplete" if evaluator["invocation_started"] else "not_run")
            )
            and execution["timed_out"] is (execution["status"] == "trajectory_timeout")
            and receipt_record["timed_out"] is (receipt["classification"] == "trajectory_timeout")
            and measurement_valid
            and (
                receipt["subject_invocation_started"]
                and _sha256(execution["ownership_token_sha256"])
                and _sha256(execution["process_identity_sha256"])
                and _sha256(execution["container_identity_sha256"])
                or not receipt["subject_invocation_started"]
                and execution["ownership_token_sha256"] is None
                and execution["process_identity_sha256"] is None
                and execution["container_identity_sha256"] is None
            )
            and evaluator["evaluator_identity"] == contract["source"]["evaluator_identity"]
            and type(evaluator["invocation_started"]) is bool
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
            )
            and evaluator["invocation_started"] is (evaluator["disposition"] != "not_run")
            and (
                evaluator["invocation_started"]
                and (
                    all(_sha256(evaluator[field]) for field in (
                        "evaluator_stdout_sha256", "evaluator_stderr_sha256",
                        "report_sha256", "results_sha256",
                    ))
                    and _sha256(execution["prediction_sha256"])
                    and _sha256(execution["patch_sha256"])
                    or execution["status"] == "durable_evidence_incomplete"
                    and all(evaluator[field] is None for field in (
                        "evaluator_stdout_sha256", "evaluator_stderr_sha256",
                        "report_sha256", "results_sha256",
                    ))
                    and execution["prediction_sha256"] is None
                    and execution["patch_sha256"] is None
                )
                or not evaluator["invocation_started"]
                and all(evaluator[field] is None for field in (
                    "evaluator_stdout_sha256", "evaluator_stderr_sha256",
                    "report_sha256", "results_sha256",
                ))
                and execution["prediction_sha256"] is None
                and execution["patch_sha256"] is None
            )
            and (
                execution["cleanup_receipt_sha256"] is None
                or _sha256(execution["cleanup_receipt_sha256"])
            )
            and all(
                value is None or _sha256(value)
                for value in (
                    execution["subject_stdout_sha256"], execution["subject_stderr_sha256"],
                    execution["prediction_sha256"], execution["patch_sha256"],
                    evaluator["evaluator_stdout_sha256"], evaluator["evaluator_stderr_sha256"],
                    evaluator["report_sha256"], evaluator["results_sha256"],
                )
            )
            and (
                receipt["subject_invocation_started"]
                and execution["status"] != "durable_evidence_incomplete"
                and _sha256(execution["subject_stdout_sha256"])
                and _sha256(execution["subject_stderr_sha256"])
                or (
                    not receipt["subject_invocation_started"]
                    or execution["status"] == "durable_evidence_incomplete"
                )
                and execution["subject_stdout_sha256"] is None
                and execution["subject_stderr_sha256"] is None
                and execution["prediction_sha256"] is None
                and execution["patch_sha256"] is None
            )
            and evaluator["anomaly_codes"] == receipt_record["evaluator_anomalies"]
            and all(measurement[field] == receipt_record[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS))
            and receipt_record["cell_id"] == receipt["cell_id"]
            and receipt_record["termination"] == receipt["classification"]
            and receipt["terminal_receipt_sha256"] == digest(receipt_body)
            and (
                receipt["classification"] not in EXPERIMENTAL_OUTCOMES
                or receipt["subject_invocation_started"]
            ),
            "terminal receipt projection is unbound, duplicated, or rehashed incorrectly",
        )
        receipt_by_attempt[key] = receipt
        receipt_bindings.append(
            {
                "cell_id": receipt["cell_id"],
                "attempt": receipt["attempt"],
                "terminal_receipt_sha256": receipt["terminal_receipt_sha256"],
                "evaluator_receipt_sha256": receipt["evaluator_receipt_sha256"],
            }
        )
    _require(
        envelope["receipt_set_sha256"] == digest(receipt_bindings),
        "analysis receipt-set digest differs from its ordered receipt projections",
    )
    _require(
        experiment_starts
        == sum(
            receipt["subject_invocation_started"] is True
            for receipt in receipt_projections
        ),
        "analysis experiment subject-start count differs from receipt projections",
    )
    seen: set[str] = set()
    for record in records:
        _require_exact_keys(record, ANALYSIS_ENVELOPE_RECORD_KEYS, "analysis record fields drifted")
        cell = cells.get(record["cell_id"])
        receipt = receipt_by_attempt.get((record["cell_id"], record["attempt"]))
        expected_record = (
            {
                **receipt["analysis_record"],
                "attempt": receipt["attempt"],
                "effective_task_commitment_sha256": receipt[
                    "effective_task_commitment_sha256"
                ],
                "terminal_receipt_sha256": receipt["terminal_receipt_sha256"],
                "evaluator_receipt_sha256": receipt["evaluator_receipt_sha256"],
            }
            if receipt is not None
            else None
        )
        _require(
            cell is not None
            and record["cell_id"] not in seen
            and type(record["attempt"]) is int
            and record["attempt"] in (1, 2)
            and record["effective_task_commitment_sha256"]
            == assignments[cell["population_slot"]]["task_commitment_sha256"]
            and _sha256(record["terminal_receipt_sha256"])
            and _sha256(record["evaluator_receipt_sha256"])
            and record == expected_record,
            "analysis record is duplicated or differs from its effective assignment",
        )
        seen.add(record["cell_id"])
    _require(
        not complete or len(records) == len(contract["schedule"]["cells"]),
        "complete analysis envelope lacks a record for every frozen cell",
    )
    return deepcopy(envelope)
