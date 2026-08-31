"""Provider-free, body-free exploratory analysis for reasoning-effort-v1."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from fractions import Fraction
from typing import Any, Iterable, Sequence

from .experiment import ExperimentConfigurationError
from .reasoning_effort_v1 import ARMS, CELL_COUNT, REPETITIONS, TASK_COUNT

BOOTSTRAP_SEED = "engineering-scope-guard-effort-v1-task-bootstrap-2026-08-30"
BOOTSTRAP_RESAMPLES = 10_000
PROVIDER_USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
BASE_WORK_FIELDS = (
    *PROVIDER_USAGE_FIELDS,
    "derived_total_tokens",
    "calculated_fresh_input_tokens",
    "subject_wall_seconds",
    "subject_turns",
    "command_count",
    "search_count",
)
IDENTITY_FIELDS = ("task_id", "repository", "arm", "repetition")
REQUIRED_COMPLETED_SUBJECT_TERMINATIONS = (
    "accepted_completed",
    "evaluator_test_failure",
    "empty_patch_failure",
)
RAW_WORK_FIELDS = (
    *PROVIDER_USAGE_FIELDS,
    "subject_wall_seconds",
    "subject_turns",
    "command_count",
    "search_count",
    "item_counts",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentConfigurationError(message)


def _identity(cell: dict[str, Any]) -> tuple[str, str, str, int]:
    return tuple(cell.get(field) for field in IDENTITY_FIELDS)  # type: ignore[return-value]


def _number(value: Fraction, digits: int = 6) -> float:
    return round(float(value), digits)


def _mean(values: Iterable[Fraction]) -> Fraction:
    materialized = list(values)
    _require(bool(materialized), "cannot summarize an empty distribution")
    return sum(materialized, Fraction()) / len(materialized)


def _percentile(values: list[Fraction], probability: Fraction) -> Fraction:
    _require(bool(values), "cannot take a percentile of an empty distribution")
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def _bootstrap_interval(values: list[Fraction]) -> dict[str, float]:
    _require(bool(values), "task bootstrap requires complete task clusters")
    distribution = [
        _mean(
            values[
                int.from_bytes(
                    hashlib.sha256(
                        f"{BOOTSTRAP_SEED}\0{resample}\0{draw}".encode()
                    ).digest()[:8],
                    "big",
                )
                % len(values)
            ]
            for draw in range(len(values))
        )
        for resample in range(BOOTSTRAP_RESAMPLES)
    ]
    return {
        "lower": _number(_percentile(distribution, Fraction(1, 40))),
        "upper": _number(_percentile(distribution, Fraction(39, 40))),
    }


def _validate_frozen_schedule(
    frozen_schedule: dict[str, Any] | Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    cells = (
        frozen_schedule.get("cells")
        if isinstance(frozen_schedule, dict)
        else frozen_schedule
    )
    _require(isinstance(cells, Sequence), "frozen schedule cells are absent")
    cells = list(cells)
    _require(len(cells) == CELL_COUNT, "effort-v1 frozen schedule must contain 32 cells")
    identities: list[tuple[str, str, str, int]] = []
    task_repositories: dict[str, str] = {}
    for cell in cells:
        _require(isinstance(cell, dict), "frozen schedule cell is not an object")
        task_id, repository, arm, repetition = _identity(cell)
        _require(
            isinstance(task_id, str) and bool(task_id),
            "frozen task identity is invalid",
        )
        _require(
            isinstance(repository, str) and bool(repository),
            "frozen repository identity is invalid",
        )
        _require(arm in ARMS, "frozen arm identity is invalid")
        _require(repetition in range(1, REPETITIONS + 1), "frozen repetition is invalid")
        previous = task_repositories.setdefault(task_id, repository)
        _require(previous == repository, "a frozen task maps to multiple repositories")
        identities.append((task_id, repository, arm, repetition))
    _require(len(set(identities)) == CELL_COUNT, "frozen cell identities are not unique")
    _require(len(task_repositories) == TASK_COUNT, "frozen schedule must contain eight tasks")
    _require(
        len(set(task_repositories.values())) == TASK_COUNT,
        "frozen tasks must use distinct repositories",
    )
    expected_assignments = {
        (task_id, repository, arm, repetition)
        for task_id, repository in task_repositories.items()
        for arm in ARMS
        for repetition in range(1, REPETITIONS + 1)
    }
    _require(set(identities) == expected_assignments, "frozen 32-cell identities changed")
    return cells


def _non_negative_integer(value: Any, field: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"cell field must be a non-negative integer: {field}",
    )
    return value


def _normalize_cell(cell: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(cell, dict), "analysis cell is not an object")
    task_id, repository, arm, repetition = _identity(cell)
    _require(isinstance(task_id, str) and bool(task_id), "cell task_id is invalid")
    _require(isinstance(repository, str) and bool(repository), "cell repository is invalid")
    _require(arm in ARMS, "cell arm is invalid")
    _require(repetition in range(1, REPETITIONS + 1), "cell repetition is invalid")
    _require(isinstance(cell.get("admissible"), bool), "cell admissible flag is invalid")
    _require(isinstance(cell.get("accepted"), bool), "cell accepted flag is invalid")
    _require(
        isinstance(cell.get("termination"), str) and bool(cell["termination"]),
        "cell termination is invalid",
    )
    _require(
        cell["accepted"] == (cell["termination"] == "accepted_completed"),
        "accepted flag and termination disagree",
    )
    _require(not cell["accepted"] or cell["admissible"], "an inadmissible cell cannot be accepted")

    result = {
        "task_id": task_id,
        "repository": repository,
        "arm": arm,
        "repetition": repetition,
        "admissible": cell["admissible"],
        "accepted": cell["accepted"],
        "termination": cell["termination"],
    }
    _require(
        "total_tokens" not in cell and "derived_total_tokens" not in cell,
        "derived total tokens must not be supplied as analysis input",
    )
    work_presence = [field in cell and cell[field] is not None for field in RAW_WORK_FIELDS]
    _require(
        all(work_presence) or not any(work_presence),
        "work measurements must be all present or all absent/null",
    )
    work_observed = all(work_presence)
    _require(
        work_observed
        or cell["termination"] not in REQUIRED_COMPLETED_SUBJECT_TERMINATIONS,
        "completed-subject outcome requires complete work measurements",
    )
    result["work_observed"] = work_observed
    if not work_observed:
        result["item_counts"] = {}
        return result

    for field in PROVIDER_USAGE_FIELDS:
        result[field] = _non_negative_integer(cell.get(field), field)
    _require(
        result["cached_input_tokens"] + result["cache_write_input_tokens"]
        <= result["input_tokens"],
        "cached plus cache-write input exceeds input tokens",
    )
    result["calculated_fresh_input_tokens"] = (
        result["input_tokens"]
        - result["cached_input_tokens"]
        - result["cache_write_input_tokens"]
    )
    result["derived_total_tokens"] = (
        result["input_tokens"] + result["output_tokens"]
    )
    wall_seconds = cell.get("subject_wall_seconds")
    _require(
        isinstance(wall_seconds, (int, float))
        and not isinstance(wall_seconds, bool)
        and math.isfinite(wall_seconds)
        and wall_seconds >= 0,
        "cell subject_wall_seconds is invalid",
    )
    result["subject_wall_seconds"] = Fraction(str(wall_seconds))
    for field in ("subject_turns", "command_count", "search_count"):
        result[field] = _non_negative_integer(cell.get(field), field)
    item_counts = cell.get("item_counts")
    _require(isinstance(item_counts, dict), "cell item_counts must be an object")
    _require(
        all(isinstance(key, str) and bool(key) for key in item_counts),
        "item-count names must be non-empty strings",
    )
    result["item_counts"] = {
        key: _non_negative_integer(value, f"item_counts.{key}")
        for key, value in sorted(item_counts.items())
    }
    return result


def _metric(cell: dict[str, Any], field: str) -> Fraction:
    if field.startswith("item_counts."):
        return Fraction(cell["item_counts"].get(field.removeprefix("item_counts."), 0))
    return Fraction(cell[field])


def _arm_mean(cells: list[dict[str, Any]], arm: str, field: str) -> Fraction:
    return _mean(_metric(cell, field) for cell in cells if cell["arm"] == arm)


def _paired_summary(tasks: list[list[dict[str, Any]]], field: str) -> dict[str, Any]:
    low = [_arm_mean(cells, "low", field) for cells in tasks]
    medium = [_arm_mean(cells, "medium", field) for cells in tasks]
    differences = [right - left for left, right in zip(low, medium)]
    return {
        "low_task_mean": _number(_mean(low)),
        "medium_task_mean": _number(_mean(medium)),
        "medium_minus_low": _number(_mean(differences)),
        "difference_95_percentile_interval": _bootstrap_interval(differences),
        "tasks_increased": sum(value > 0 for value in differences),
        "tasks_decreased": sum(value < 0 for value in differences),
        "tasks_tied": sum(value == 0 for value in differences),
    }


def _acceptance_difference(cells: list[dict[str, Any]]) -> Fraction:
    return _arm_mean(cells, "medium", "accepted") - _arm_mean(cells, "low", "accepted")


def _leave_one_task_out(tasks: list[list[dict[str, Any]]]) -> dict[str, Any]:
    full = _mean(_acceptance_difference(cells) for cells in tasks)
    entries = []
    if len(tasks) > 1:
        for omitted in tasks:
            retained = [cells for cells in tasks if cells is not omitted]
            estimate = _mean(_acceptance_difference(cells) for cells in retained)
            entries.append(
                {
                    "omitted_task_id": omitted[0]["task_id"],
                    "medium_minus_low_percentage_points": _number(estimate * 100),
                    "change_from_full_percentage_points": _number((estimate - full) * 100),
                    "reverses_sign": (full > 0 and estimate < 0)
                    or (full < 0 and estimate > 0),
                }
            )
    return {
        "full_estimate_percentage_points": _number(full * 100),
        "omissions": entries,
        "any_omission_reverses_sign": any(item["reverses_sign"] for item in entries),
        "maximum_absolute_change_percentage_points": max(
            (abs(item["change_from_full_percentage_points"]) for item in entries),
            default=0.0,
        ),
    }


def _component_summary(
    admissible: list[dict[str, Any]],
    complete_tasks: list[list[dict[str, Any]]],
    field: str,
) -> dict[str, Any]:
    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        assigned = [cell for cell in admissible if cell["arm"] == arm]
        cells = [cell for cell in assigned if cell["work_observed"]]
        accepted = sum(cell["accepted"] for cell in cells)
        total = sum((_metric(cell, field) for cell in cells), Fraction())
        by_arm[arm] = {
            "admissible_cells": len(assigned),
            "observed_work_cells": len(cells),
            "missing_work_cells": len(assigned) - len(cells),
            "accepted_outcomes_with_observed_work": accepted,
            "total": _number(total),
            "mean_per_observed_cell": _number(total / len(cells)) if cells else None,
            "per_accepted_outcome": _number(total / accepted) if accepted else None,
        }
    return {
        "by_arm": by_arm,
        "complete_work_task_clusters": len(complete_tasks),
        "paired_complete_tasks": _paired_summary(complete_tasks, field)
        if complete_tasks
        else None,
    }


def analyze(
    records: Sequence[dict[str, Any]],
    frozen_schedule: dict[str, Any] | Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze normalized cells against the frozen 32-cell identity set.

    Missing or inadmissible cells are never imputed. Paired estimates use only
    tasks with both repetitions in both arms admissible.
    """

    frozen_cells = _validate_frozen_schedule(frozen_schedule)
    expected = {_identity(cell) for cell in frozen_cells}
    cells = [_normalize_cell(cell) for cell in records]
    observed = [_identity(cell) for cell in cells]
    _require(len(observed) == len(set(observed)), "analysis cell identities are duplicated")
    _require(set(observed) <= expected, "analysis contains a non-frozen cell identity")

    missing = sorted(expected - set(observed))
    admissible = [cell for cell in cells if cell["admissible"]]
    inadmissible = [cell for cell in cells if not cell["admissible"]]
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in admissible:
        by_task[cell["task_id"]].append(cell)
    complete_tasks = [
        sorted(task_cells, key=lambda cell: (cell["arm"], cell["repetition"]))
        for _, task_cells in sorted(by_task.items())
        if len(task_cells) == len(ARMS) * REPETITIONS
        and {_identity(cell)[2:] for cell in task_cells}
        == {(arm, repetition) for arm in ARMS for repetition in range(1, REPETITIONS + 1)}
    ]
    complete_work_tasks = [
        task_cells
        for task_cells in complete_tasks
        if all(cell["work_observed"] for cell in task_cells)
    ]

    marginal_acceptance = {}
    for arm in ARMS:
        arm_cells = [cell for cell in admissible if cell["arm"] == arm]
        accepted = sum(cell["accepted"] for cell in arm_cells)
        marginal_acceptance[arm] = {
            "accepted": accepted,
            "admissible_cells": len(arm_cells),
            "rate": round(accepted / len(arm_cells), 6) if arm_cells else None,
        }

    paired_acceptance = _paired_summary(complete_tasks, "accepted") if complete_tasks else None
    if paired_acceptance is not None:
        paired_acceptance["medium_minus_low_percentage_points"] = round(
            paired_acceptance.pop("medium_minus_low") * 100, 6
        )
        paired_acceptance["difference_95_percentile_interval_percentage_points"] = {
            key: round(value * 100, 6)
            for key, value in paired_acceptance.pop(
                "difference_95_percentile_interval"
            ).items()
        }

    pair_counts = Counter(
        {
            "both_accepted": 0,
            "neither_accepted": 0,
            "low_only_accepted": 0,
            "medium_only_accepted": 0,
        }
    )
    repetition_pairs: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for cell in admissible:
        repetition_pairs[(cell["task_id"], cell["repetition"])][cell["arm"]] = cell
    for arms in repetition_pairs.values():
        if set(arms) != set(ARMS):
            continue
        pair_counts[
            {
                (True, True): "both_accepted",
                (False, False): "neither_accepted",
                (True, False): "low_only_accepted",
                (False, True): "medium_only_accepted",
            }[(arms["low"]["accepted"], arms["medium"]["accepted"])]
        ] += 1

    task_differences = [
        {
            "task_id": task[0]["task_id"],
            "repository": task[0]["repository"],
            "medium_minus_low_percentage_points": _number(
                _acceptance_difference(task) * 100
            ),
        }
        for task in complete_tasks
    ]
    item_names = sorted(
        {
            name
            for cell in cells
            if cell["work_observed"]
            for name in cell["item_counts"]
        }
    )
    work_fields = (*BASE_WORK_FIELDS, *(f"item_counts.{name}" for name in item_names))
    work = {
        field: _component_summary(admissible, complete_work_tasks, field)
        for field in work_fields
    }
    missing_work = [cell for cell in admissible if not cell["work_observed"]]

    task_signs = {
        "medium_higher": sum(
            item["medium_minus_low_percentage_points"] > 0
            for item in task_differences
        ),
        "low_higher": sum(
            item["medium_minus_low_percentage_points"] < 0
            for item in task_differences
        ),
        "tied": sum(item["medium_minus_low_percentage_points"] == 0 for item in task_differences),
    }
    work_directions = {
        field: (
            None
            if summary["paired_complete_tasks"] is None
            else (summary["paired_complete_tasks"]["medium_minus_low"] > 0)
            - (summary["paired_complete_tasks"]["medium_minus_low"] < 0)
        )
        for field, summary in work.items()
    }
    leave_one_out = _leave_one_task_out(complete_tasks) if complete_tasks else None
    return {
        "schema_name": "engineering-scope-guard.reasoning-effort-v1-analysis",
        "schema_version": 1,
        "acceptance": {
            "by_arm": marginal_acceptance,
            "paired_complete_tasks": paired_acceptance,
            "discordant_and_null_repetition_pairs": dict(pair_counts),
            "task_heterogeneity": {
                "directions": task_signs,
                "tasks": task_differences,
            },
        },
        "analysis_population": {
            "frozen_cells": len(expected),
            "observed_cells": len(cells),
            "admissible_cells": len(admissible),
            "inadmissible_cells": len(inadmissible),
            "complete_task_clusters": len(complete_tasks),
            "missing_frozen_identities": [
                dict(zip(IDENTITY_FIELDS, identity)) for identity in missing
            ],
            "missing_frozen_cells_by_arm": {
                arm: sum(identity[2] == arm for identity in missing) for arm in ARMS
            },
            "inadmissible_by_arm_and_termination": {
                f"{arm}:{termination}": count
                for (arm, termination), count in sorted(
                    Counter((cell["arm"], cell["termination"]) for cell in inadmissible).items()
                )
            },
            "rule": "no imputation; paired estimates use complete admissible task clusters only",
        },
        "work_components": work,
        "work_measurement_missingness": {
            "observed_admissible_cells": sum(
                cell["work_observed"] for cell in admissible
            ),
            "missing_admissible_cells": len(missing_work),
            "complete_work_task_clusters": len(complete_work_tasks),
            "by_arm_and_termination": {
                f"{arm}:{termination}": count
                for (arm, termination), count in sorted(
                    Counter(
                        (cell["arm"], cell["termination"]) for cell in missing_work
                    ).items()
                )
            },
            "rule": "no imputation; work summaries use observed work records only",
        },
        "work_component_rule": (
            "per_accepted_outcome is total work across observed admissible records in an arm "
            "divided by accepted outcomes in that observed-work subset; every denominator is "
            "reported and the value is null when the accepted denominator is zero"
        ),
        "leave_one_task_out_task_leverage": leave_one_out,
        "uncertainty": {
            "method": "deterministic SHA-256 task-cluster bootstrap with replacement",
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "interval": "nearest-rank 2.5th and 97.5th percentiles",
        },
        "adversarial_falsification_summary": {
            "missing_or_inadmissible_cells_present": bool(missing or inadmissible),
            "missing_work_measurements_present": bool(missing_work),
            "opposing_task_acceptance_directions_present": (
                task_signs["medium_higher"] > 0 and task_signs["low_higher"] > 0
            ),
            "both_discordance_directions_present": (
                pair_counts["low_only_accepted"] > 0
                and pair_counts["medium_only_accepted"] > 0
            ),
            "work_component_directions": work_directions,
            "any_task_omission_reverses_acceptance_sign": (
                leave_one_out["any_omission_reverses_sign"] if leave_one_out else None
            ),
            "interpretation": (
                "Contradictions, missingness, null pairs, heterogeneity, and leverage are "
                "retained; this exploratory summary does not establish billing, equivalence, "
                "noninferiority, preserved quality, per-language efficacy, a causal mechanism, "
                "or an unnecessary-work percentage."
            ),
        },
        "claim_boundaries": {
            "billing_inferred": False,
            "equivalence_or_noninferiority_inferred": False,
            "preserved_quality_inferred": False,
            "per_language_efficacy_inferred": False,
            "causal_mechanism_inferred": False,
            "unnecessary_work_percentage_inferred": False,
        },
    }
