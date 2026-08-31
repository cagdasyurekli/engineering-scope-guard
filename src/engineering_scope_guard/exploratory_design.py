"""Deterministic validation for the task-free exploratory design freeze."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .experiment import ExperimentConfigurationError

SCHEMA_NAME = (
    "engineering-scope-guard.evidence-conditioned-final-scope-review-exploratory-design"
)
DESIGN_VERSION = "evidence-conditioned-final-scope-review-exploratory-v0.1"
DECISION = (
    "EXPLORATORY DESIGN QUALIFIED — TASK SELECTION AND FREEZE REQUIRE SEPARATE "
    "AUTHORIZATION"
)
TREATMENT_FAMILY = "Evidence-Conditioned Final Scope Review"
TREATMENT_VERSION = "v0.1"
TREATMENT_PATH = Path("experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt")
TREATMENT_SHA256 = "d9ac9e18716428e9cd6d038388b01ec668ade47df8bac014658897752166b8cb"
SOURCE_REVISION = "62dc0745c40f067fc366ae3eb1a26136e5928f85"
STARTING_RESERVE_COMMITMENT = (
    "4e8137ee3a23571546f1fec4831b26fd3d0a93a4bbdf70d90088284c87a05605"
)
TASK_COUNT = 8
REPETITIONS = 2
ARMS = ("baseline", "treatment")
SELECTION_SEED = (
    "engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-selection"
)
SCHEDULE_SEED = (
    "engineering-scope-guard-evidence-conditioned-final-scope-review-v0.1-order"
)
LANGUAGES = ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
RETIREMENT_GATES = {
    "necessary_correctness_suppression",
    "adverse_acceptance",
    "no_accepted_outcome_mechanism",
    "corrective_round_increase",
    "search_increase",
    "cached_context_increase",
    "wall_or_work_increase",
    "structural_proxy_only",
    "pre_activation_effect",
    "c_short_equivalence",
    "broad_minimality_search",
}
TRAJECTORY_MEASURES = {
    "input tokens",
    "cached input tokens",
    "calculated fresh input tokens",
    "output tokens",
    "reasoning-output tokens",
    "wall time",
    "subject turns",
    "corrective rounds",
    "command executions",
    "local read/search interactions",
    "completed web-search interactions",
}
FORBIDDEN_MATERIAL_KEYS = {
    "actual_task_id",
    "task_id",
    "instance_id",
    "task_body",
    "problem_statement",
    "selected_tasks",
    "eligible_ids",
    "reserve_ids",
    "cells",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical repository serialization."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _rank(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def generate_schedule(
    opaque_task_commitments: list[str], future_pool_commitment: str
) -> list[dict[str, Any]]:
    """Generate counterbalanced blocks from opaque commitments only."""

    _require(
        len(opaque_task_commitments) == TASK_COUNT
        and len(set(opaque_task_commitments)) == TASK_COUNT,
        "schedule requires eight unique opaque task commitments",
    )
    _require(
        all(SHA256_RE.fullmatch(value) for value in opaque_task_commitments)
        and bool(SHA256_RE.fullmatch(future_pool_commitment)),
        "schedule inputs must be SHA-256 commitments",
    )
    blocks: list[dict[str, Any]] = []
    for task_commitment in opaque_task_commitments:
        treatment_first = int(
            _rank(SCHEDULE_SEED, future_pool_commitment, task_commitment, "orientation"),
            16,
        ) % 2
        first = ("treatment", "baseline") if treatment_first else ARMS
        for repetition in range(1, REPETITIONS + 1):
            arm_order = first if repetition == 1 else tuple(reversed(first))
            blocks.append(
                {
                    "opaque_task_commitment": task_commitment,
                    "repetition": repetition,
                    "arms": list(arm_order),
                }
            )
    return sorted(
        blocks,
        key=lambda block: (
            _rank(
                SCHEDULE_SEED,
                future_pool_commitment,
                block["opaque_task_commitment"],
                str(block["repetition"]),
            ),
            block["opaque_task_commitment"],
            block["repetition"],
        ),
    )


def select_metadata_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Apply the frozen rank to an already-eligible metadata-only projection."""

    required = {"opaque_instance_identity", "repository_identity", "language"}
    _require(
        all(
            isinstance(row, dict)
            and set(row) == required
            and all(isinstance(row[field], str) and row[field] for field in required)
            for row in rows
        ),
        "selection rows must contain only the frozen nonempty metadata fields",
    )
    identities = [row["opaque_instance_identity"] for row in rows]
    _require(len(identities) == len(set(identities)), "selection identities must be unique")
    selected: list[dict[str, str]] = []
    repositories: set[str] = set()
    for language in LANGUAGES:
        ranked = sorted(
            (row for row in rows if row["language"] == language),
            key=lambda row: (
                _rank(
                    SELECTION_SEED,
                    SOURCE_REVISION,
                    language,
                    row["opaque_instance_identity"],
                ),
                row["opaque_instance_identity"],
            ),
        )
        choice = next(
            (row for row in ranked if row["repository_identity"] not in repositories),
            None,
        )
        _require(choice is not None, f"fresh repository-distinct supply cannot cover {language}")
        selected.append(choice)
        repositories.add(choice["repository_identity"])
    return selected


def _reject_task_material(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_MATERIAL_KEYS & set(value)
        if forbidden:
            raise ExperimentConfigurationError(
                f"design contains task material key: {sorted(forbidden)[0]}"
            )
        for child in value.values():
            _reject_task_material(child)
    elif isinstance(value, list):
        for child in value:
            _reject_task_material(child)


def validate_design(value: Any, root: Path) -> dict[str, Any]:
    """Validate treatment identity and every material prospective boundary."""

    _require(isinstance(value, dict), "design must be an object")
    _reject_task_material(value)
    required_top = {
        "schema_name",
        "schema_version",
        "design_version",
        "decision",
        "execution_authorized",
        "task_pool_frozen",
        "significance_tests_are_retirement_gates",
        "treatment",
        "arms",
        "experimental_unit",
        "sample_size_rationale",
        "selection",
        "schedule_algorithm",
        "attempts",
        "operator_pause",
        "corrective_round",
        "isolation_and_durability",
        "analysis",
        "retirement_gates",
    }
    _require(set(value) == required_top, "design top-level fields are not frozen")
    _require(value["schema_name"] == SCHEMA_NAME, "design schema name changed")
    _require(value["schema_version"] == 1, "design schema version changed")
    _require(value["design_version"] == DESIGN_VERSION, "design version changed")
    _require(value["decision"] == DECISION, "design decision changed")
    _require(value["execution_authorized"] is False, "design must not authorize execution")
    _require(value["task_pool_frozen"] is False, "design must not freeze a task pool")
    _require(
        value["significance_tests_are_retirement_gates"] is False,
        "retirement gates must not become significance tests",
    )

    treatment = value["treatment"]
    expected_treatment = {
        "family": TREATMENT_FAMILY,
        "version": TREATMENT_VERSION,
        "path": TREATMENT_PATH.as_posix(),
        "sha256": TREATMENT_SHA256,
    }
    _require(treatment == expected_treatment, "frozen treatment identity changed")
    treatment_path = root / TREATMENT_PATH
    _require(treatment_path.is_file(), "frozen treatment file is missing")
    _require(
        hashlib.sha256(treatment_path.read_bytes()).hexdigest() == TREATMENT_SHA256,
        "frozen treatment bytes changed",
    )
    _require(
        value["arms"]
        == [
            {"id": "baseline", "intervention": None},
            {"id": "treatment", **expected_treatment},
        ],
        "the design must contain baseline and the exact treatment only",
    )

    unit = value["experimental_unit"]
    _require(unit["task_count"] == TASK_COUNT, "exploratory task count changed")
    _require(
        unit["task_repetitions_per_arm"] == REPETITIONS,
        "repetition count changed",
    )
    _require(unit["total_cells"] == TASK_COUNT * REPETITIONS * len(ARMS), "cell count changed")
    _require(unit["repetitions_are_independent_n"] is False, "repetitions became independent N")
    _require("task and repository" in unit["independent_unit"], "task clustering is absent")
    rationale = value["sample_size_rationale"]
    _require("not a power calculation" in rationale, "sample-size claim boundary is absent")
    _require("no Pilot-v3 effect size" in rationale, "Pilot-v3 sizing contamination is possible")

    selection = value["selection"]
    _require(selection["source_revision"] == SOURCE_REVISION, "source revision changed")
    _require(selection["selection_seed"] == SELECTION_SEED, "selection seed changed")
    _require(
        selection["starting_opaque_reserve_commitment_sha256"]
        == STARTING_RESERVE_COMMITMENT,
        "starting opaque reserve commitment changed",
    )
    _require(
        selection["task_bodies_or_actual_identities_present"] is False,
        "task bodies or actual identities are present",
    )
    _require(tuple(selection["language_order"]) == LANGUAGES, "language coverage changed")
    prohibited = set(selection["prohibited_inputs"])
    _require(
        {
            "task body",
            "difficulty",
            "expected success",
            "known patch size",
            "outcome history",
            "semantic similarity to Pilot-v3 failures",
            "manual preference",
        }
        <= prohibited,
        "selection contamination controls were weakened",
    )
    _require("SHA-256" in selection["ranking"], "selection is not cryptographically ranked")
    _require("emit no remaining identity or body" in selection["reserve_recommitment"], "reserve opacity weakened")

    schedule = value["schedule_algorithm"]
    _require(schedule["schedule_seed"] == SCHEDULE_SEED, "schedule seed changed")
    _require(schedule["manual_rearrangement_permitted"] is False, "manual scheduling enabled")
    _require(schedule["uses_interim_outcomes"] is False, "adaptive scheduling enabled")
    _require("repetition 2 reverses" in schedule["arm_order"], "within-task counterbalancing changed")
    _require("SHA-256" in schedule["block_order"], "block order is not deterministic")

    attempts = value["attempts"]
    _require(attempts["maximum_total_attempts_per_cell"] == 2, "attempt maximum changed")
    _require(attempts["infrastructure_retry_capacity_batch_total"] == 4, "infrastructure capacity changed")
    _require(attempts["operator_interruption_capacity_batch_total"] == 2, "operator capacity changed")
    _require("timeout" in attempts["experimental_negative_outcomes"], "timeouts left intention to treat")
    _require("official_evaluator_incomplete" in attempts["infrastructure_invalid"], "incomplete handling changed")
    _require("valid negative outcomes are never rerun" in attempts["rules"], "negative outcomes became retryable")

    pause = value["operator_pause"]
    _require(pause["relabel_as_infrastructure_permitted"] is False, "operator interruption can be relabeled")
    _require(pause["stop_when_allowance_exhausted"] is True, "operator exhaustion no longer stops")
    _require("before attempt_started" in pause["planned"], "planned pause boundary changed")
    _require("fresh isolation" in pause["mid_attempt"], "operator restart isolation weakened")

    corrective = value["corrective_round"]
    _require(corrective["maximum"] == 1, "corrective-round maximum changed")
    _require("named failing checks only" in corrective["rules"]["failure_feedback_available"], "corrective feedback broadened")
    _require("no invented feedback" in corrective["rules"]["failure_feedback_unavailable"], "missing feedback can be invented")
    _require(corrective["rules"]["multiple_or_contradictory_terminal_identity"] == "stop batch", "contradictory evaluator evidence no longer stops")

    durability = value["isolation_and_durability"]
    _require(durability["completed_cells_never_repeat"] is True, "completed cells became repeatable")
    _require(len(durability["fresh_per_attempt"]) == 6, "fresh isolation roots changed")
    _require("SHA-256 hash chain" in durability["ledger"], "durable hash chain is absent")
    _require("durable ledger" in durability["restart_source"], "restart source is not durable state")

    analysis = value["analysis"]
    _require(analysis["quality_precedes_work"] is True, "quality no longer precedes work")
    _require("intention-to-treat" in analysis["analysis_population"], "analysis population is not intention to treat")
    _require("subtract baseline from treatment" in analysis["paired_acceptance"], "paired acceptance estimand changed")
    _require("N^N" in analysis["task_uncertainty"], "task-cluster uncertainty method changed")
    _require("without imputation" in analysis["incomplete_task_clusters"], "incomplete clusters can be imputed")
    accepted = analysis["accepted_outcome_work"]
    _require("accepted in both arms" in accepted["primary_comparison"], "accepted-outcome pairing changed")
    _require("conditional descriptive mechanism evidence" in accepted["interpretation"], "conditioning boundary is absent")
    _require("always report unconditional quality" in accepted["selection_warning"], "unconditional quality can be hidden")
    _require(set(analysis["work_measures"]["trajectory"]) == TRAJECTORY_MEASURES, "trajectory work measures changed")
    _require(len(analysis["claim_boundaries"]) == 8, "claim boundaries changed")

    gates = value["retirement_gates"]
    _require(isinstance(gates, list), "retirement gates must be a list")
    _require({gate.get("gate") for gate in gates} == RETIREMENT_GATES, "retirement gates changed")
    _require(all(isinstance(gate.get("trigger"), str) and gate["trigger"] for gate in gates), "retirement trigger is empty")
    return value


def load_design(path: Path, root: Path) -> dict[str, Any]:
    """Load a canonical design specification and validate it."""

    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError("exploratory design is unreadable") from error
    _require(raw == canonical_bytes(value), "exploratory design JSON is not canonical")
    return validate_design(value, root)
