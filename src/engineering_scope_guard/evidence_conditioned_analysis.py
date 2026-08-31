"""Frozen-order exploratory analysis for Evidence-Conditioned Final Scope Review."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

from .evidence_conditioned_execution import next_legal_action, validate_contract
from .experiment import ExperimentConfigurationError
from .pilot_v3 import read_events
from .pilot_v3_analysis import _patch_structure, _trace_counts

USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "calculated_fresh_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
TRAJECTORY_FIELDS = (
    *USAGE_FIELDS,
    "wall_seconds",
    "subject_turns",
    "corrective_rounds",
    "command_executions",
    "local_read_search_interactions",
    "completed_web_searches",
)
STRUCTURAL_FIELDS = ("files_changed", "lines_added", "lines_deleted")
ANNOTATION_FIELDS = {
    "necessary_correctness_suppression",
    "evidence_supported_optional_removal_or_simplification",
    "apparent_pre_activation_behavioral_effect",
    "c_short_equivalent_behavior",
    "broad_proof_of_minimality_search",
    "evidence_references",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _number(value: Fraction, digits: int = 6) -> float:
    return round(float(value), digits)


def _median(values: Iterable[Fraction]) -> Fraction:
    ordered = sorted(values)
    _require(bool(ordered), "cannot summarize an empty distribution")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _bootstrap(values: list[Fraction]) -> Counter[Fraction]:
    _require(bool(values), "task bootstrap requires complete clusters")
    one_draw = Counter(values)
    sums: Counter[Fraction] = Counter({Fraction(): 1})
    for _ in values:
        updated: Counter[Fraction] = Counter()
        for partial, partial_count in sums.items():
            for value, value_count in one_draw.items():
                updated[partial + value] += partial_count * value_count
        sums = updated
    return Counter({total / len(values): count for total, count in sums.items()})


def _nearest_rank(distribution: Counter[Fraction], probability: Fraction) -> Fraction:
    rank = math.ceil(probability * sum(distribution.values()))
    seen = 0
    for value, count in sorted(distribution.items()):
        seen += count
        if seen >= rank:
            return value
    raise ExperimentConfigurationError("bootstrap percentile could not be resolved")


def _interval(values: list[Fraction]) -> dict[str, float]:
    distribution = _bootstrap(values)
    return {
        "lower": _number(_nearest_rank(distribution, Fraction(1, 40))),
        "upper": _number(_nearest_rank(distribution, Fraction(39, 40))),
    }


def _duration(receipt: dict[str, Any]) -> Fraction:
    try:
        started = datetime.fromisoformat(receipt["attempt_started_at"])
        ended = datetime.fromisoformat(receipt["ended_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ExperimentConfigurationError("receipt timestamps are invalid") from error
    delta = ended - started
    microseconds = (
        (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    )
    _require(microseconds >= 0, "receipt duration is negative")
    return Fraction(microseconds, 1_000_000)


def _metric(cell: dict[str, Any], field: str) -> Fraction:
    if field == "acceptance":
        return Fraction(cell["accepted"])
    value = cell["structural"][field] if field in STRUCTURAL_FIELDS else cell[field]
    if field == "wall_seconds":
        return Fraction(str(value))
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"analysis metric is invalid: {field}",
    )
    return Fraction(value)


def _task_arm_mean(task: dict[str, Any], arm: str, field: str) -> Fraction:
    values = [_metric(cell, field) for cell in task["cells"] if cell["arm"] == arm]
    _require(len(values) == 2, "complete task-arm requires two repetitions")
    return sum(values, Fraction()) / 2


def _paired_summary(tasks: list[dict[str, Any]], field: str) -> dict[str, Any]:
    baseline = [_task_arm_mean(task, "baseline", field) for task in tasks]
    treatment = [_task_arm_mean(task, "treatment", field) for task in tasks]
    differences = [right - left for left, right in zip(baseline, treatment)]
    result: dict[str, Any] = {
        "baseline_task_mean": _number(sum(baseline, Fraction()) / len(baseline)),
        "treatment_task_mean": _number(sum(treatment, Fraction()) / len(treatment)),
        "treatment_minus_baseline": _number(
            sum(differences, Fraction()) / len(differences)
        ),
        "difference_95_percentile_interval": _interval(differences),
        "tasks_increased": sum(value > 0 for value in differences),
        "tasks_decreased": sum(value < 0 for value in differences),
        "tasks_tied": sum(value == 0 for value in differences),
    }
    return result


def validate_annotations(
    contract: dict[str, Any], annotations: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    _require(
        annotations.get("schema_name")
        == "engineering-scope-guard.evidence-conditioned-final-scope-review-mechanism-annotations",
        "mechanism annotation schema changed",
    )
    _require(annotations.get("schema_version") == 1, "annotation version changed")
    _require(
        annotations.get("contract_sha256") == contract["contract_sha256"],
        "annotations are not contract-bound",
    )
    cells = annotations.get("cells")
    _require(isinstance(cells, dict), "mechanism annotations are absent")
    treatment_ids = {
        cell["cell_id"]
        for cell in contract["schedule"]["cells"]
        if cell["arm"] == "treatment"
    }
    _require(set(cells) <= treatment_ids, "annotations reference a non-treatment cell")
    for cell_id, value in cells.items():
        _require(isinstance(value, dict), f"annotation is not an object: {cell_id}")
        _require(set(value) == ANNOTATION_FIELDS, f"annotation fields changed: {cell_id}")
        for field in ANNOTATION_FIELDS - {"evidence_references"}:
            _require(isinstance(value[field], bool), f"annotation flag is invalid: {field}")
        references = value["evidence_references"]
        _require(
            isinstance(references, list)
            and all(isinstance(item, str) and item for item in references),
            "annotation evidence references are invalid",
        )
        if any(value[field] for field in ANNOTATION_FIELDS - {"evidence_references"}):
            _require(bool(references), "positive annotation lacks evidence references")
    return cells


def _analysis_cells(
    contract: dict[str, Any],
    receipts: list[dict[str, Any]],
    annotations: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    schedule = {cell["cell_id"]: cell for cell in contract["schedule"]["cells"]}
    cells: list[dict[str, Any]] = []
    for receipt in receipts:
        if receipt.get("admissible") is not True:
            continue
        frozen = schedule.get(receipt.get("cell_id"))
        _require(frozen is not None, "receipt references an unknown cell")
        for field, value in frozen.items():
            _require(receipt.get(field) == value, f"receipt assignment mismatch: {field}")
        usage = receipt.get("usage")
        _require(isinstance(usage, dict), "receipt usage is absent")
        for field in USAGE_FIELDS:
            _require(
                isinstance(usage.get(field), int)
                and not isinstance(usage[field], bool)
                and usage[field] >= 0,
                f"receipt usage is invalid: {field}",
            )
        counts = Counter()
        phase_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for checkpoint in receipt.get("subject_checkpoints", []):
            trace_counts = _trace_counts(Path(checkpoint["trace_reference"]))
            counts.update(trace_counts)
            phase_counts[checkpoint["phase"]].update(trace_counts)
        patch = _patch_structure(
            Path(receipt["isolation_roots"]["derived"]) / "prediction.patch"
        )
        activation = receipt.get("treatment_activation", {})
        annotation = annotations.get(receipt["cell_id"])
        if receipt["arm"] == "treatment":
            _require(annotation is not None, "treatment mechanism annotation is absent")
        cells.append(
            {
                "cell_id": receipt["cell_id"],
                "task_commitment": receipt["opaque_task_commitment"],
                "arm": receipt["arm"],
                "repetition": receipt["repetition"],
                "accepted": receipt["termination"] == "accepted_completed",
                "termination": receipt["termination"],
                **{field: usage[field] for field in USAGE_FIELDS},
                "wall_seconds": _number(_duration(receipt)),
                "subject_turns": receipt["subject_turns"],
                "corrective_rounds": receipt["corrective_rounds"],
                "command_executions": counts["command_executions"],
                "local_read_search_interactions": counts["read_search_commands"],
                "completed_web_searches": counts["web_searches"],
                "pre_activation_command_executions": phase_counts["ordinary"][
                    "command_executions"
                ],
                "pre_activation_local_read_search_interactions": phase_counts[
                    "ordinary"
                ]["read_search_commands"],
                "post_activation_command_executions": phase_counts["treatment"][
                    "command_executions"
                ],
                "post_activation_local_read_search_interactions": phase_counts[
                    "treatment"
                ]["read_search_commands"],
                "treatment_activated": activation.get("activated") is True,
                "structural": patch,
                "mechanism_annotation": annotation,
            }
        )
    return cells


def _complete_tasks(cells: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    clustered: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        clustered[cell["task_commitment"]].append(cell)
    complete = []
    incomplete = []
    for task_id, task_cells in sorted(clustered.items()):
        keys = sorted((cell["arm"], cell["repetition"]) for cell in task_cells)
        if keys == [
            ("baseline", 1),
            ("baseline", 2),
            ("treatment", 1),
            ("treatment", 2),
        ]:
            complete.append({"task_commitment": task_id, "cells": task_cells})
        else:
            incomplete.append(task_id)
    return complete, incomplete


def _jointly_accepted(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = []
    for task in tasks:
        indexed = {
            (cell["arm"], cell["repetition"]): cell for cell in task["cells"]
        }
        for repetition in (1, 2):
            baseline = indexed[("baseline", repetition)]
            treatment = indexed[("treatment", repetition)]
            if baseline["accepted"] and treatment["accepted"]:
                pairs.append((task["task_commitment"], baseline, treatment))
    metric_differences: dict[str, list[Fraction]] = {}
    for field in TRAJECTORY_FIELDS:
        by_task: dict[str, list[Fraction]] = defaultdict(list)
        for task_id, baseline, treatment in pairs:
            by_task[task_id].append(
                _metric(treatment, field) - _metric(baseline, field)
            )
        metric_differences[field] = [
            sum(values, Fraction()) / len(values)
            for _task_id, values in sorted(by_task.items())
        ]
    evidence_cells = [
        treatment["cell_id"]
        for _, _baseline, treatment in pairs
        if treatment["mechanism_annotation"][
            "evidence_supported_optional_removal_or_simplification"
        ]
    ]
    reduced_fields = [
        field for field, values in metric_differences.items() if values and sum(values) < 0
    ]
    return {
        "matched_pairs": len(pairs),
        "task_clusters_with_matched_pairs": len({item[0] for item in pairs}),
        "evidence_supported_removal_cells": evidence_cells,
        "trajectory_fields_with_mean_reduction": reduced_fields,
        "metric_mean_treatment_minus_baseline": {
            field: _number(sum(values, Fraction()) / len(values))
            for field, values in metric_differences.items()
            if values
        },
        "selection_warning": (
            "conditioning on joint acceptance is descriptive mechanism evidence and "
            "does not replace unconditional intention-to-treat quality"
        ),
    }


def _leave_one_out(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for omitted in tasks:
        retained = [task for task in tasks if task is not omitted]
        item: dict[str, Any] = {"omitted_task_commitment": omitted["task_commitment"]}
        for field in ("acceptance", *TRAJECTORY_FIELDS):
            differences = [
                _task_arm_mean(task, "treatment", field)
                - _task_arm_mean(task, "baseline", field)
                for task in retained
            ]
            item[f"{field}_treatment_minus_baseline"] = _number(
                sum(differences, Fraction()) / len(differences)
            )
        results.append(item)
    return results


def _retirement_gates(
    tasks: list[dict[str, Any]],
    paired: dict[str, dict[str, Any]],
    discordance: dict[str, int],
    jointly_accepted: dict[str, Any],
) -> list[dict[str, Any]]:
    annotations = [
        cell["mechanism_annotation"]
        for task in tasks
        for cell in task["cells"]
        if cell["arm"] == "treatment"
    ]
    suppression_by_task = [
        sum(
            cell["mechanism_annotation"]["necessary_correctness_suppression"]
            for cell in task["cells"]
            if cell["arm"] == "treatment"
        )
        for task in tasks
    ]
    suppression_fired = any(count == 2 for count in suppression_by_task) or sum(
        count > 0 for count in suppression_by_task
    ) >= 2
    accepted_mechanism = bool(
        jointly_accepted["evidence_supported_removal_cells"]
        and jointly_accepted["trajectory_fields_with_mean_reduction"]
    )

    def directional(field: str) -> bool:
        value = paired[field]
        return (
            value["treatment_minus_baseline"] > 0
            and value["tasks_increased"] > value["tasks_decreased"]
        )

    structural_reduction = any(
        paired[field]["treatment_minus_baseline"] < 0 for field in STRUCTURAL_FIELDS
    )
    gates = [
        ("necessary_correctness_suppression", suppression_fired),
        (
            "adverse_acceptance",
            paired["acceptance"]["treatment_minus_baseline"] < 0
            and discordance["baseline_only_task_clusters"]
            > discordance["treatment_only_task_clusters"],
        ),
        ("no_accepted_outcome_mechanism", not accepted_mechanism),
        ("corrective_round_increase", directional("corrective_rounds")),
        (
            "search_increase",
            directional("local_read_search_interactions")
            or directional("completed_web_searches"),
        ),
        ("cached_context_increase", directional("cached_input_tokens")),
        (
            "wall_or_work_increase",
            any(directional(field) for field in TRAJECTORY_FIELDS),
        ),
        ("structural_proxy_only", structural_reduction and not accepted_mechanism),
        (
            "pre_activation_effect",
            any(item["apparent_pre_activation_behavioral_effect"] for item in annotations),
        ),
        ("c_short_equivalence", any(item["c_short_equivalent_behavior"] for item in annotations)),
        (
            "broad_minimality_search",
            any(
                sum(
                    cell["mechanism_annotation"]["broad_proof_of_minimality_search"]
                    for cell in task["cells"]
                    if cell["arm"] == "treatment"
                )
                == 2
                for task in tasks
            )
            or sum(
                any(
                    cell["mechanism_annotation"]["broad_proof_of_minimality_search"]
                    for cell in task["cells"]
                    if cell["arm"] == "treatment"
                )
                for task in tasks
            )
            >= 2,
        ),
    ]
    return [{"gate": name, "fired": fired} for name, fired in gates]


def analyze(
    root: Path,
    contract: dict[str, Any],
    ledger_path: Path,
    annotation_value: dict[str, Any],
) -> dict[str, Any]:
    """Run the predeclared analysis in its frozen reporting order."""

    validate_contract(root, contract)
    events = read_events(ledger_path)
    action = next_legal_action(contract, events)
    _require(
        action["action"] in {"complete", "batch_stopped"},
        "execution has not reached a legitimate terminal boundary",
    )
    annotations = validate_annotations(contract, annotation_value)
    receipts = [event["payload"] for event in events if event["event_type"] == "receipt_committed"]
    cells = _analysis_cells(contract, receipts, annotations)
    complete_tasks, incomplete_tasks = _complete_tasks(cells)
    _require(bool(complete_tasks), "no complete task cluster is analyzable")
    expected_ids = {cell["cell_id"] for cell in contract["schedule"]["cells"]}
    admissible_ids = {cell["cell_id"] for cell in cells}
    missing_ids = sorted(expected_ids - admissible_ids)
    marginal = {
        arm: {
            "accepted": sum(cell["accepted"] for cell in cells if cell["arm"] == arm),
            "admissible": sum(cell["arm"] == arm for cell in cells),
        }
        for arm in ("baseline", "treatment")
    }
    for value in marginal.values():
        value["rate"] = round(value["accepted"] / value["admissible"], 6)
        missing = 16 - value["admissible"]
        value["missing"] = missing
        value["best_case_rate"] = round((value["accepted"] + missing) / 16, 6)
        value["worst_case_rate"] = round(value["accepted"] / 16, 6)
    paired = {
        field: _paired_summary(complete_tasks, field)
        for field in ("acceptance", *TRAJECTORY_FIELDS, *STRUCTURAL_FIELDS)
    }
    pair_counts = Counter()
    cluster_counts = Counter()
    for task in complete_tasks:
        indexed = {(cell["arm"], cell["repetition"]): cell for cell in task["cells"]}
        task_labels = set()
        for repetition in (1, 2):
            pair = (
                indexed[("baseline", repetition)]["accepted"],
                indexed[("treatment", repetition)]["accepted"],
            )
            label = {
                (True, True): "both_accepted",
                (False, False): "both_negative",
                (True, False): "baseline_only",
                (False, True): "treatment_only",
            }[pair]
            pair_counts[label] += 1
            task_labels.add(label)
        if "baseline_only" in task_labels:
            cluster_counts["baseline_only_task_clusters"] += 1
        if "treatment_only" in task_labels:
            cluster_counts["treatment_only_task_clusters"] += 1
    discordance = {
        **{name: pair_counts[name] for name in ("both_accepted", "both_negative", "baseline_only", "treatment_only")},
        "baseline_only_task_clusters": cluster_counts["baseline_only_task_clusters"],
        "treatment_only_task_clusters": cluster_counts["treatment_only_task_clusters"],
    }
    jointly_accepted = _jointly_accepted(complete_tasks)
    gates = _retirement_gates(complete_tasks, paired, discordance, jointly_accepted)
    fired = [item["gate"] for item in gates if item["fired"]]
    disposition = (
        "candidate_retired"
        if fired
        else (
            "bounded_exploratory_evidence_sufficient_to_consider_separately_authorized_next_stage"
            if action["action"] == "complete" and not missing_ids
            else "experiment_stopped_or_inconclusive"
        )
    )
    return {
        "schema_name": (
            "engineering-scope-guard.evidence-conditioned-final-scope-review-exploratory-analysis"
        ),
        "schema_version": 1,
        "contract_sha256": contract["contract_sha256"],
        "reporting_order": [
            "execution_completeness_and_missingness",
            "unconditional_quality",
            "discordance_and_replicated_patterns",
            "unconditional_work",
            "jointly_accepted_work_and_mechanism",
            "corrective_search_context_activation_diagnostics",
            "task_bootstrap_and_leave_one_task_out",
            "retirement_gates",
            "bounded_disposition",
        ],
        "execution_completeness_and_missingness": {
            "terminal_action": action["action"],
            "frozen_cells": len(expected_ids),
            "admissible_cells": len(admissible_ids),
            "missing_cell_ids": missing_ids,
            "complete_task_clusters": len(complete_tasks),
            "incomplete_task_commitments": incomplete_tasks,
            "imputation_performed": False,
        },
        "unconditional_quality": {
            "marginal_acceptance": marginal,
            "paired_acceptance": paired["acceptance"],
        },
        "discordance_and_replicated_patterns": discordance,
        "unconditional_work": {
            field: {
                "paired_task_cluster": paired[field],
                "marginal_by_arm": {
                    arm: {
                        "cells": len(values),
                        "mean": _number(
                            sum((_metric(cell, field) for cell in values), Fraction())
                            / len(values)
                        ),
                        "median": _number(
                            _median(_metric(cell, field) for cell in values)
                        ),
                    }
                    for arm, values in {
                        arm: [cell for cell in cells if cell["arm"] == arm]
                        for arm in ("baseline", "treatment")
                    }.items()
                },
            }
            for field in TRAJECTORY_FIELDS
        },
        "jointly_accepted_work_and_mechanism": jointly_accepted,
        "corrective_search_context_activation_diagnostics": {
            "corrective_rounds": paired["corrective_rounds"],
            "local_read_search_interactions": paired[
                "local_read_search_interactions"
            ],
            "completed_web_searches": paired["completed_web_searches"],
            "cached_input_tokens": paired["cached_input_tokens"],
            "treatment_cells_with_activation": sum(
                cell["arm"] == "treatment" and cell["treatment_activated"]
                for cell in cells
            ),
            "treatment_cells_without_activation": sum(
                cell["arm"] == "treatment" and not cell["treatment_activated"]
                for cell in cells
            ),
            "pre_activation_treatment_exposure": False,
            "treatment_cell_activation_evidence": [
                {
                    "cell_id": cell["cell_id"],
                    "activated": cell["treatment_activated"],
                    "pre_activation_command_executions": cell[
                        "pre_activation_command_executions"
                    ],
                    "pre_activation_local_read_search_interactions": cell[
                        "pre_activation_local_read_search_interactions"
                    ],
                    "post_activation_command_executions": cell[
                        "post_activation_command_executions"
                    ],
                    "post_activation_local_read_search_interactions": cell[
                        "post_activation_local_read_search_interactions"
                    ],
                    "mechanism_annotation": cell["mechanism_annotation"],
                }
                for cell in cells
                if cell["arm"] == "treatment"
            ],
        },
        "task_bootstrap_and_leave_one_task_out": {
            "ordered_bootstrap_resamples": len(complete_tasks) ** len(complete_tasks),
            "cluster_unit": "task/repository",
            "repetitions_are_independent_n": False,
            "leave_one_task_out": _leave_one_out(complete_tasks),
        },
        "structural_diagnostics_only": {
            **{field: paired[field] for field in STRUCTURAL_FIELDS},
            "dependency_delta": {
                "status": "unavailable",
                "reason": "the frozen durable receipt does not encode normalized manifest dependencies",
                "treated_as_zero": False,
            },
        },
        "retirement_gates": gates,
        "bounded_disposition": {
            "class": disposition,
            "fired_gates": fired,
            "exploratory_only": True,
            "confirmatory_claim": False,
            "equivalence_or_noninferiority_claim": False,
            "monetary_savings_claim": False,
        },
    }
