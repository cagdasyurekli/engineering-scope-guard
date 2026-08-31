"""Public-safe, provider-free analysis for the frozen reasoning-effort v2 contract."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from fractions import Fraction
import hashlib
import math
import re
from typing import Any

from .pilot_contract import digest
from .reasoning_effort_v2 import (
    ARMS,
    REPETITIONS,
    validate_analysis_terminal_envelope,
    validate_contract,
)


SCHEMA_NAME = "engineering-scope-guard.reasoning-effort-v2-analysis"
SCHEMA_VERSION = 1
DISPOSITIONS = (
    "LOW FAVORED",
    "MEDIUM FAVORED",
    "WORK DIFFERENCE WITHOUT ACCEPTANCE EVIDENCE",
    "NO MATERIAL EXPLORATORY DIFFERENCE DETECTED",
    "INCONCLUSIVE",
    "EXPERIMENT INVALID / TERMINATED",
)
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
DERIVED_WORK_FIELDS = ("fresh_input_tokens",)
WORK_FIELDS = (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS, *DERIVED_WORK_FIELDS)
_CODE = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")


class AnalysisInputError(ValueError):
    """Raised when public-safe analysis input is not frozen or canonical."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisInputError(message)


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _exact_keys(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == keys, f"{field} fields drifted")
    return value


def _number(value: Fraction | int | float) -> float:
    return round(float(value), 9)


def _validate_analysis_policy(contract: dict[str, Any]) -> dict[str, Any]:
    policy = _exact_keys(
        contract.get("analysis_policy"),
        {
            "schema_version",
            "bootstrap",
            "termination_taxonomy",
            "work_policy",
            "disposition_policy",
        },
        "analysis policy",
    )
    _require(policy["schema_version"] == 1, "analysis policy version drifted")
    bootstrap = _exact_keys(policy["bootstrap"], {"seed", "resamples"}, "bootstrap")
    _require(
        isinstance(bootstrap["seed"], str)
        and bool(bootstrap["seed"])
        and type(bootstrap["resamples"]) is int
        and bootstrap["resamples"] > 0,
        "bootstrap policy is invalid",
    )
    taxonomy = _exact_keys(
        policy["termination_taxonomy"],
        {"accepted", "admissible_failures", "inadmissible", "timeout"},
        "termination taxonomy",
    )
    _require(
        isinstance(taxonomy["accepted"], str)
        and isinstance(taxonomy["timeout"], str)
        and isinstance(taxonomy["admissible_failures"], list)
        and isinstance(taxonomy["inadmissible"], list),
        "termination taxonomy is malformed",
    )
    codes = [
        taxonomy["accepted"],
        *taxonomy["admissible_failures"],
        *taxonomy["inadmissible"],
    ]
    _require(
        all(isinstance(code, str) and _CODE.fullmatch(code) for code in codes)
        and len(set(codes)) == len(codes)
        and taxonomy["timeout"] in taxonomy["admissible_failures"],
        "termination taxonomy is overlapping or invalid",
    )
    work = _exact_keys(
        policy["work_policy"],
        {
            "integer_fields",
            "float_fields",
            "record_completeness",
            "fresh_input_formula",
            "accepted_conditional_denominator",
            "accepted_conditional_is_descriptive_post_outcome_subset",
        },
        "work policy",
    )
    _require(
        work["integer_fields"] == list(INTEGER_WORK_FIELDS)
        and work["float_fields"] == list(FLOAT_WORK_FIELDS)
        and work["record_completeness"]
        == "all declared work fields present or all absent"
        and work["fresh_input_formula"]
        == "input_tokens - cached_input_tokens - cache_write_input_tokens"
        and work["accepted_conditional_denominator"]
        == "accepted admissible cells with complete work measurements"
        and work["accepted_conditional_is_descriptive_post_outcome_subset"] is True,
        "work policy drifted",
    )
    disposition = _exact_keys(
        policy["disposition_policy"],
        {
            "precedence",
            "favored_interval_rule",
            "missing_or_inadmissible",
            "no_material_abs_point_max",
            "no_material_interval_lower_min",
            "no_material_interval_upper_max",
            "work_metric",
        },
        "disposition policy",
    )
    _require(
        disposition["precedence"]
        == [DISPOSITIONS[5], *DISPOSITIONS[:5]]
        and disposition["favored_interval_rule"]
        == "cluster bootstrap interval strictly excludes zero"
        and disposition["missing_or_inadmissible"] == "INCONCLUSIVE"
        and disposition["work_metric"] == "fresh_input_tokens"
        and isinstance(disposition["no_material_abs_point_max"], (int, float))
        and not isinstance(disposition["no_material_abs_point_max"], bool)
        and math.isfinite(disposition["no_material_abs_point_max"])
        and disposition["no_material_abs_point_max"] >= 0
        and all(
            isinstance(disposition[field], (int, float))
            and not isinstance(disposition[field], bool)
            and math.isfinite(disposition[field])
            for field in (
                "no_material_interval_lower_min",
                "no_material_interval_upper_max",
            )
        ),
        "disposition policy drifted",
    )
    return policy


def _bootstrap_interval(
    values: list[Fraction], *, seed: str, resamples: int
) -> dict[str, float]:
    _require(bool(values), "cluster bootstrap requires complete clusters")
    sampled = []
    for sample in range(resamples):
        indices = _unbiased_bootstrap_indices(
            seed=seed,
            sample=sample,
            draws=len(values),
            population_size=len(values),
        )
        total = sum((values[index] for index in indices), Fraction(0))
        sampled.append(total / len(values))
    sampled.sort()
    lower_rank = max(1, math.ceil(Fraction(25, 1000) * len(sampled)))
    upper_rank = max(1, math.ceil(Fraction(975, 1000) * len(sampled)))
    return {
        "lower": _number(sampled[lower_rank - 1]),
        "upper": _number(sampled[upper_rank - 1]),
    }


def _unbiased_bootstrap_indices(
    *, seed: str, sample: int, draws: int, population_size: int
) -> tuple[int, ...]:
    """Derive stable uniform indices using SHA-256 rejection sampling."""

    _require(
        isinstance(seed, str)
        and bool(seed)
        and type(sample) is int
        and sample >= 0
        and type(draws) is int
        and draws >= 0
        and type(population_size) is int
        and 1 <= population_size <= 256,
        "bootstrap index request is invalid",
    )
    acceptance_limit = 256 - (256 % population_size)
    indices: list[int] = []
    block = 0
    while len(indices) < draws:
        stream = hashlib.sha256(f"{seed}|{sample}|{block}".encode()).digest()
        block += 1
        for byte in stream:
            if byte < acceptance_limit:
                indices.append(byte % population_size)
                if len(indices) == draws:
                    break
    return tuple(indices)


def _paired_summary(
    slot_values: list[tuple[int, str, Fraction]], *, seed: str, resamples: int
) -> dict[str, Any] | None:
    if not slot_values:
        return None
    by_repository: dict[str, list[Fraction]] = defaultdict(list)
    for _, repository_commitment, value in slot_values:
        by_repository[repository_commitment].append(value)
    independent_values = [
        sum(values, Fraction(0)) / len(values)
        for _, values in sorted(by_repository.items())
    ]
    return {
        "complete_slots": len(slot_values),
        "independent_repository_clusters": len(independent_values),
        "medium_minus_low": _number(
            sum(independent_values, Fraction(0)) / len(independent_values)
        ),
        "repository_cluster_bootstrap_95_interval": _bootstrap_interval(
            independent_values, seed=seed, resamples=resamples
        ),
    }


def _normalize_records(
    contract: dict[str, Any],
    records: Sequence[dict[str, Any]],
    assignments: dict[int, dict[str, Any]],
    policy: dict[str, Any],
    *,
    allow_multiple_attempts: bool = False,
) -> list[dict[str, Any]]:
    _require(isinstance(records, Sequence) and not isinstance(records, (str, bytes)), "records must be a sequence")
    expected = {cell["cell_id"]: cell for cell in contract["schedule"]["cells"]}
    taxonomy = policy["termination_taxonomy"]
    admissible_codes = {taxonomy["accepted"], *taxonomy["admissible_failures"]}
    inadmissible_codes = set(taxonomy["inadmissible"])
    exact_record_keys = {
        "cell_id",
        "attempt",
        "effective_task_commitment_sha256",
        "terminal_receipt_sha256",
        "evaluator_receipt_sha256",
        "termination",
        "timed_out",
        "evaluator_anomalies",
        *INTEGER_WORK_FIELDS,
        *FLOAT_WORK_FIELDS,
    }
    seen: set[str | tuple[str, int]] = set()
    normalized = []
    for record in records:
        _exact_keys(record, exact_record_keys, "analysis record")
        cell_id = record["cell_id"]
        attempt = record["attempt"]
        identity: str | tuple[str, int] = (
            (cell_id, attempt) if allow_multiple_attempts else cell_id
        )
        _require(
            cell_id in expected and identity not in seen,
            "record cell/attempt is unknown or duplicated",
        )
        frozen = expected[cell_id]
        _require(
            type(attempt) is int
            and attempt in (1, 2)
            and record["effective_task_commitment_sha256"]
            == assignments[frozen["population_slot"]]["task_commitment_sha256"]
            and _sha256(record["terminal_receipt_sha256"])
            and _sha256(record["evaluator_receipt_sha256"]),
            "record attempt, effective assignment, or receipt binding drifted",
        )
        termination = record["termination"]
        _require(
            termination in admissible_codes | inadmissible_codes,
            "termination is outside the frozen taxonomy",
        )
        _require(
            type(record["timed_out"]) is bool
            and record["timed_out"] == (termination == taxonomy["timeout"]),
            "timeout flag and frozen timeout termination disagree",
        )
        anomalies = record["evaluator_anomalies"]
        _require(
            isinstance(anomalies, list)
            and all(isinstance(code, str) and _CODE.fullmatch(code) for code in anomalies),
            "evaluator anomaly codes are malformed",
        )
        work_values = [record[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)]
        complete_work = all(value is not None for value in work_values)
        absent_work = all(value is None for value in work_values)
        _require(complete_work or absent_work, "work record is partial under complete-or-absent policy")
        if complete_work:
            _require(
                all(type(record[field]) is int and record[field] >= 0 for field in INTEGER_WORK_FIELDS),
                "count and token work fields must be non-negative integers",
            )
            _require(
                type(record["wall_seconds"]) is float
                and math.isfinite(record["wall_seconds"])
                and record["wall_seconds"] >= 0,
                "wall_seconds must be a finite non-negative float",
            )
            fresh = (
                record["input_tokens"]
                - record["cached_input_tokens"]
                - record["cache_write_input_tokens"]
            )
            _require(fresh >= 0, "derived fresh input is negative")
        else:
            fresh = None
        normalized.append(
            {
                **frozen,
                "attempt": record["attempt"],
                "effective_task_commitment_sha256": record[
                    "effective_task_commitment_sha256"
                ],
                "terminal_receipt_sha256": record["terminal_receipt_sha256"],
                "evaluator_receipt_sha256": record["evaluator_receipt_sha256"],
                "admissible": termination in admissible_codes,
                "accepted": termination == taxonomy["accepted"],
                "termination": termination,
                "timed_out": record["timed_out"],
                "evaluator_anomalies": tuple(anomalies),
                **{field: record[field] for field in (*INTEGER_WORK_FIELDS, *FLOAT_WORK_FIELDS)},
                "fresh_input_tokens": fresh,
                "work_complete": complete_work,
            }
        )
        seen.add(identity)
    return normalized


def _slot_differences(
    cells: list[dict[str, Any]], assignments: dict[int, dict[str, Any]], field: str
) -> list[tuple[int, str, Fraction]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[cell["population_slot"]].append(cell)
    result = []
    for slot, slot_cells in sorted(grouped.items()):
        if len(slot_cells) != 4 or any(
            not cell["admissible"] or cell[field] is None for cell in slot_cells
        ):
            continue
        means = {
            arm: sum(
                (Fraction(cell[field]) for cell in slot_cells if cell["arm"] == arm),
                Fraction(0),
            )
            / REPETITIONS
            for arm in ARMS
        }
        result.append(
            (
                slot,
                assignments[slot]["repository_commitment_sha256"],
                means["medium"] - means["low"],
            )
        )
    return result


def _accepted_work_differences(
    cells: list[dict[str, Any]], assignments: dict[int, dict[str, Any]], field: str
) -> list[tuple[int, str, Fraction]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[cell["population_slot"]].append(cell)
    result = []
    for slot, slot_cells in sorted(grouped.items()):
        values = {
            arm: [
                Fraction(cell[field])
                for cell in slot_cells
                if cell["arm"] == arm
                and cell["admissible"]
                and cell["accepted"]
                and cell[field] is not None
            ]
            for arm in ARMS
        }
        if values["low"] and values["medium"]:
            result.append(
                (
                    slot,
                    assignments[slot]["repository_commitment_sha256"],
                    sum(values["medium"], Fraction(0)) / len(values["medium"])
                    - sum(values["low"], Fraction(0)) / len(values["low"]),
                )
            )
    return result


def _arm_work(cells: list[dict[str, Any]], arm: str, field: str) -> dict[str, Any]:
    observed = [
        cell
        for cell in cells
        if cell["arm"] == arm and cell["admissible"] and cell[field] is not None
    ]
    accepted = [cell for cell in observed if cell["accepted"]]
    total = sum((Fraction(cell[field]) for cell in observed), Fraction(0))
    accepted_total = sum((Fraction(cell[field]) for cell in accepted), Fraction(0))
    return {
        "unconditional": {
            "complete_work_cells": len(observed),
            "total": _number(total),
            "per_complete_work_cell": _number(total / len(observed)) if observed else None,
        },
        "accepted_conditional": {
            "accepted_admissible_cells_with_complete_work": len(accepted),
            "total": _number(accepted_total),
            "per_accepted_outcome": (
                _number(accepted_total / len(accepted)) if accepted else None
            ),
            "caveat": "descriptive post-outcome subset; not a randomized estimand",
        },
    }


def _work_subset(items: list[dict[str, Any]], field: str) -> dict[str, Any]:
    complete = [item for item in items if item[field] is not None]
    total = sum((Fraction(item[field]) for item in complete), Fraction(0))
    return {
        "complete_work_attempts": len(complete),
        "total": _number(total),
        "per_complete_work_attempt": (
            _number(total / len(complete)) if complete else None
        ),
    }


def _attempt_trajectory(
    attempts: list[dict[str, Any]], final_cells: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate every validated receipt without emitting task/cell identities."""

    final_by_cell = {cell["cell_id"]: cell for cell in final_cells}
    final_receipts = {cell["terminal_receipt_sha256"] for cell in final_cells}
    attempts_by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_cell[attempt["cell_id"]].append(attempt)
    for items in attempts_by_cell.values():
        items.sort(key=lambda item: item["attempt"])

    transitions: dict[str, dict[str, Any]] = {}
    for items in attempts_by_cell.values():
        attempt_1 = next((item for item in items if item["attempt"] == 1), None)
        attempt_2 = next((item for item in items if item["attempt"] == 2), None)
        if attempt_1 is None:
            continue
        classification = attempt_1["termination"]
        entry = transitions.setdefault(
            classification,
            {
                "attempt_1_classification": classification,
                "attempt_1_attempts": 0,
                "attempt_2_activated": 0,
                "attempt_2_outcomes": Counter(),
            },
        )
        entry["attempt_1_attempts"] += 1
        if attempt_2 is not None:
            entry["attempt_2_activated"] += 1
            entry["attempt_2_outcomes"][attempt_2["termination"]] += 1
    transition_rows = []
    for classification in sorted(transitions):
        entry = transitions[classification]
        transition_rows.append(
            {
                **{key: value for key, value in entry.items() if key != "attempt_2_outcomes"},
                "attempt_2_outcomes": dict(sorted(entry["attempt_2_outcomes"].items())),
            }
        )

    attempt_counts = {}
    diagnostics = {}
    work: dict[str, Any] = {}
    for arm in ARMS:
        arm_attempts = [attempt for attempt in attempts if attempt["arm"] == arm]
        attempt_counts[arm] = {
            "attempts": len(arm_attempts),
            "attempt_1": sum(item["attempt"] == 1 for item in arm_attempts),
            "attempt_2": sum(item["attempt"] == 2 for item in arm_attempts),
            "classification_counts": dict(
                sorted(Counter(item["termination"] for item in arm_attempts).items())
            ),
        }
        complete = [item for item in arm_attempts if item["work_complete"]]
        diagnostics[arm] = {
            "timeout_attempts": sum(item["timed_out"] for item in arm_attempts),
            "attempt_2_timeout_attempts": sum(
                item["attempt"] == 2 and item["timed_out"] for item in arm_attempts
            ),
            "complete_work_attempts": len(complete),
            "cache_present_complete_work_attempts": sum(
                item["cached_input_tokens"] + item["cache_write_input_tokens"] > 0
                for item in complete
            ),
            "correction_present_complete_work_attempts": sum(
                item["correction_turns"] > 0 for item in complete
            ),
            "retry_complete_work_attempts": sum(
                item["attempt"] == 2 for item in complete
            ),
            "attempt_2_cache_present_complete_work_attempts": sum(
                item["attempt"] == 2
                and item["cached_input_tokens"] + item["cache_write_input_tokens"] > 0
                for item in complete
            ),
            "attempt_2_correction_present_complete_work_attempts": sum(
                item["attempt"] == 2 and item["correction_turns"] > 0
                for item in complete
            ),
        }

    for field in WORK_FIELDS:
        by_arm = {}
        for arm in ARMS:
            arm_attempts = [attempt for attempt in attempts if attempt["arm"] == arm]
            final_arm = [cell for cell in final_cells if cell["arm"] == arm]
            discarded_or_invalid = [
                attempt
                for attempt in arm_attempts
                if attempt["terminal_receipt_sha256"] not in final_receipts
                or not attempt["admissible"]
            ]
            accepted_final = [cell for cell in final_arm if cell["accepted"]]
            complete_trajectories = []
            trajectory_attempts = []
            for cell in accepted_final:
                items = attempts_by_cell.get(cell["cell_id"], [])
                if items and all(item[field] is not None for item in items):
                    complete_trajectories.append(cell)
                    trajectory_attempts.extend(items)
            trajectory_total = sum(
                (Fraction(item[field]) for item in trajectory_attempts), Fraction(0)
            )
            all_summary = _work_subset(arm_attempts, field)
            final_summary = _work_subset(final_arm, field)
            all_total = sum(
                (Fraction(item[field]) for item in arm_attempts if item[field] is not None),
                Fraction(0),
            )
            final_total = sum(
                (Fraction(item[field]) for item in final_arm if item[field] is not None),
                Fraction(0),
            )
            by_arm[arm] = {
                "all_attempts": all_summary,
                "discarded_or_infrastructure_invalid": _work_subset(
                    discarded_or_invalid, field
                ),
                "final_record_only": final_summary,
                "final_record_vs_all_attempts": {
                    "final_record_total": final_summary["total"],
                    "all_attempt_total": all_summary["total"],
                    "incremental_retry_or_discarded_work": _number(
                        all_total - final_total
                    ),
                },
                "accepted_conditional_trajectory": {
                    "accepted_final_outcomes": len(accepted_final),
                    "accepted_final_outcomes_with_complete_trajectory_work": len(
                        complete_trajectories
                    ),
                    "complete_work_attempts_in_denominator": len(trajectory_attempts),
                    "total": _number(trajectory_total),
                    "per_accepted_final_outcome": (
                        _number(trajectory_total / len(complete_trajectories))
                        if complete_trajectories
                        else None
                    ),
                    "caveat": (
                        "descriptive post-outcome trajectory; denominator is accepted "
                        "final outcomes with complete work across every attempt"
                    ),
                },
            }
        work[field] = {"by_arm": by_arm}

    return {
        "attempt_counts_by_arm": attempt_counts,
        "attempt_1_to_attempt_2_transitions": transition_rows,
        "work": work,
        "diagnostics_by_arm": diagnostics,
    }


def _acceptance_strata(cells: list[dict[str, Any]], predicate: Any) -> dict[str, Any]:
    result = {}
    for label, selected_value in (("without", False), ("with", True)):
        selected = [
            cell
            for cell in cells
            if cell["admissible"] and bool(predicate(cell)) is selected_value
        ]
        result[label] = {}
        for arm in ARMS:
            arm_cells = [cell for cell in selected if cell["arm"] == arm]
            accepted = sum(cell["accepted"] for cell in arm_cells)
            result[label][arm] = {
                "accepted": accepted,
                "cells": len(arm_cells),
                "rate": round(accepted / len(arm_cells), 9) if arm_cells else None,
            }
    return result


def _disposition(
    *,
    protocol_valid: bool,
    complete_population: bool,
    acceptance: dict[str, Any] | None,
    work: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, str]:
    rule = policy["disposition_policy"]
    if not protocol_valid:
        return {"label": DISPOSITIONS[5], "basis": "protocol_valid was false"}
    if not complete_population or acceptance is None:
        return {"label": rule["missing_or_inadmissible"], "basis": "missing or inadmissible frozen cells"}
    interval = acceptance["repository_cluster_bootstrap_95_interval"]
    if interval["upper"] < 0:
        return {"label": DISPOSITIONS[0], "basis": rule["favored_interval_rule"]}
    if interval["lower"] > 0:
        return {"label": DISPOSITIONS[1], "basis": rule["favored_interval_rule"]}
    work_summary = work[rule["work_metric"]]["paired_accepted_conditional"]
    if work_summary is not None:
        work_interval = work_summary["repository_cluster_bootstrap_95_interval"]
        if work_interval["upper"] < 0 or work_interval["lower"] > 0:
            return {
                "label": DISPOSITIONS[2],
                "basis": "acceptance unresolved; frozen accepted-conditional work interval excludes zero",
            }
    point = acceptance["medium_minus_low"]
    if (
        abs(point) <= rule["no_material_abs_point_max"]
        and interval["lower"] >= rule["no_material_interval_lower_min"]
        and interval["upper"] <= rule["no_material_interval_upper_max"]
    ):
        return {
            "label": DISPOSITIONS[3],
            "basis": "frozen exploratory detection rule; not equivalence or noninferiority",
        }
    return {"label": DISPOSITIONS[4], "basis": "frozen uncertainty rule not satisfied"}


def analyze_reasoning_effort_v2(
    contract: dict[str, Any],
    terminal_envelope: dict[str, Any],
) -> dict[str, Any]:
    """Analyze only a core-exported, sealed terminal evidence envelope."""

    validate_contract(contract)
    policy = _validate_analysis_policy(contract)
    envelope = validate_analysis_terminal_envelope(contract, terminal_envelope)
    assignment_list = envelope["effective_assignments"]
    assignments = {item["population_slot"]: item for item in assignment_list}
    cells = _normalize_records(contract, envelope["records"], assignments, policy)
    attempt_records = [
        {
            **receipt["analysis_record"],
            "attempt": receipt["attempt"],
            "effective_task_commitment_sha256": receipt[
                "effective_task_commitment_sha256"
            ],
            "terminal_receipt_sha256": receipt["terminal_receipt_sha256"],
            "evaluator_receipt_sha256": receipt["evaluator_receipt_sha256"],
        }
        for receipt in envelope["receipt_projections"]
    ]
    attempts = _normalize_records(
        contract,
        attempt_records,
        assignments,
        policy,
        allow_multiple_attempts=True,
    )
    attempt_trajectory = _attempt_trajectory(attempts, cells)
    expected_ids = {cell["cell_id"] for cell in contract["schedule"]["cells"]}
    observed_ids = {cell["cell_id"] for cell in cells}
    missing = sorted(expected_ids - observed_ids)
    inadmissible = [cell for cell in cells if not cell["admissible"]]
    bootstrap = policy["bootstrap"]
    acceptance_values = _slot_differences(cells, assignments, "accepted")
    acceptance = _paired_summary(
        acceptance_values,
        seed=f"{bootstrap['seed']}|acceptance",
        resamples=bootstrap["resamples"],
    )
    admissible = [cell for cell in cells if cell["admissible"]]
    by_arm = {}
    for arm in ARMS:
        arm_cells = [cell for cell in admissible if cell["arm"] == arm]
        accepted = sum(cell["accepted"] for cell in arm_cells)
        by_arm[arm] = {
            "accepted": accepted,
            "admissible_cells": len(arm_cells),
            "rate": round(accepted / len(arm_cells), 9) if arm_cells else None,
        }
    work = {}
    for field in WORK_FIELDS:
        work[field] = {
            "by_arm": {arm: _arm_work(cells, arm, field) for arm in ARMS},
            "paired_unconditional": _paired_summary(
                _slot_differences(cells, assignments, field),
                seed=f"{bootstrap['seed']}|work|{field}|all",
                resamples=bootstrap["resamples"],
            ),
            "paired_accepted_conditional": _paired_summary(
                _accepted_work_differences(cells, assignments, field),
                seed=f"{bootstrap['seed']}|work|{field}|accepted",
                resamples=bootstrap["resamples"],
            ),
        }
    slot_differences = [_number(value) for _, _, value in acceptance_values]
    loto = []
    for omitted_slot, _, _ in acceptance_values:
        remaining = [item for item in acceptance_values if item[0] != omitted_slot]
        summary = _paired_summary(
            remaining,
            seed=f"{bootstrap['seed']}|loto|slot-{omitted_slot}",
            resamples=bootstrap["resamples"],
        )
        loto.append(summary)
    repository_loto = []
    for commitment in sorted({item[1] for item in acceptance_values}):
        remaining = [item for item in acceptance_values if item[1] != commitment]
        repository_loto.append(
            _paired_summary(
                remaining,
                seed=f"{bootstrap['seed']}|repo-loto|{commitment}",
                resamples=bootstrap["resamples"],
            )
        )
    by_slot_arm: dict[tuple[int, str], dict[int, dict[str, Any]]] = defaultdict(dict)
    by_slot_repetition: dict[tuple[int, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for cell in admissible:
        by_slot_arm[(cell["population_slot"], cell["arm"])][cell["repetition"]] = cell
        by_slot_repetition[(cell["population_slot"], cell["repetition"])][cell["arm"]] = cell
    repetition_disagreement_counts = Counter({arm: 0 for arm in ARMS})
    for (_, arm), repetitions in sorted(by_slot_arm.items()):
        if (
            set(repetitions) == {1, 2}
            and repetitions[1]["accepted"] != repetitions[2]["accepted"]
        ):
            repetition_disagreement_counts[arm] += 1
    opposite_counts = Counter({"low_only_accepted": 0, "medium_only_accepted": 0})
    for (slot, repetition), arms in sorted(by_slot_repetition.items()):
        if set(arms) != set(ARMS) or arms["low"]["accepted"] == arms["medium"]["accepted"]:
            continue
        winner = "low" if arms["low"]["accepted"] else "medium"
        opposite_counts[f"{winner}_only_accepted"] += 1
    anomaly_counts = Counter(code for cell in cells for code in cell["evaluator_anomalies"])
    alternate_slots = [item["population_slot"] for item in assignment_list if item["alternate_activated"]]
    without_alternates = [item for item in acceptance_values if item[0] not in alternate_slots]
    complete_population = (
        not missing
        and not inadmissible
        and len(acceptance_values) == len(assignment_list)
    )
    timeout_bounds = None
    if any(cell["admissible"] and cell["timed_out"] for cell in cells):
        timeout_bounds = {}
        for name, favored_arm in (("low_favorable", "low"), ("medium_favorable", "medium")):
            scenario = []
            for cell in cells:
                changed = dict(cell)
                if changed["admissible"] and changed["timed_out"]:
                    changed["accepted"] = changed["arm"] == favored_arm
                scenario.append(changed)
            timeout_bounds[name] = _paired_summary(
                _slot_differences(scenario, assignments, "accepted"),
                seed=f"{bootstrap['seed']}|timeout|{name}",
                resamples=bootstrap["resamples"],
            )
    cache_strata = _acceptance_strata(
        cells,
        lambda cell: cell["work_complete"]
        and (cell["cached_input_tokens"] + cell["cache_write_input_tokens"] > 0),
    )
    correction_strata = _acceptance_strata(
        cells,
        lambda cell: cell["work_complete"] and cell["correction_turns"] > 0,
    )
    disposition = _disposition(
        protocol_valid=envelope["protocol_valid"],
        complete_population=complete_population,
        acceptance=acceptance,
        work=work,
        policy=policy,
    )
    records_sha256 = digest(envelope["records"])
    receipt_projections_sha256 = digest(envelope["receipt_projections"])
    input_commitment = digest(
        {
            "contract_sha256": contract["contract_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "envelope_sha256": envelope["envelope_sha256"],
            "ledger_head_event_sha256": envelope["ledger_binding"][
                "head_event_sha256"
            ],
            "receipt_set_sha256": envelope["receipt_set_sha256"],
            "records_sha256": records_sha256,
            "receipt_projections_sha256": receipt_projections_sha256,
        }
    )
    falsification = {
        "leave_one_slot_out": loto,
        "leave_one_repository_cluster_out": repository_loto,
        "repetition_disagreement": {
            "by_arm": dict(repetition_disagreement_counts),
            "total": sum(repetition_disagreement_counts.values()),
        },
        "opposite_arm_wins": dict(opposite_counts),
        "timeout_extreme_case_bounds": timeout_bounds,
        "cache_presence_strata": cache_strata,
        "correction_turn_presence_strata": correction_strata,
        "alternate_use_sensitivity": {
            "activated_slot_count": len(alternate_slots),
            "paired_acceptance_without_activated_slots": _paired_summary(
                without_alternates,
                seed=f"{bootstrap['seed']}|without-alternates",
                resamples=bootstrap["resamples"],
            ),
        },
        "evaluator_anomalies": {
            "cells_with_anomalies": sum(
                bool(cell["evaluator_anomalies"]) for cell in cells
            ),
            "counts_by_code": dict(sorted(anomaly_counts.items())),
        },
    }
    retry_work_payload = {
        "final_record_work": work,
        "all_attempt_work": attempt_trajectory["work"],
    }
    retry_falsification_payload = {
        "final_record_falsification": falsification,
        "attempt_transitions": attempt_trajectory[
            "attempt_1_to_attempt_2_transitions"
        ],
        "attempt_diagnostics": attempt_trajectory["diagnostics_by_arm"],
    }
    prior = contract["source"]["prior_evidence_identity"]
    gate_policy = contract["esg_rr_002_gate_policy"]
    prior_evidence_comparison = {
        "prior_evidence_sha256": prior["prior_evidence_sha256"],
        "prior_evidence_gap": prior["frozen_gap"],
        "prospective_direct_addition": prior["prospective_addition"],
        "gate_policy_matches_prior_evidence": (
            gate_policy["prior_evidence_sha256"] == prior["prior_evidence_sha256"]
            and gate_policy["prior_evidence_gap"] == prior["frozen_gap"]
            and gate_policy["prospective_direct_addition"]
            == prior["prospective_addition"]
        ),
    }
    esg_usefulness = {
        "primary_acceptance_point_estimate": (
            acceptance["medium_minus_low"] if acceptance is not None else None
        ),
        "primary_acceptance_interval": (
            acceptance["repository_cluster_bootstrap_95_interval"]
            if acceptance is not None
            else None
        ),
        "retry_inclusive_work_result": {
            "sha256": digest(retry_work_payload),
            "attempts_by_arm": {
                arm: attempt_trajectory["attempt_counts_by_arm"][arm]["attempts"]
                for arm in ARMS
            },
        },
        "retry_inclusive_falsification_result": {
            "sha256": digest(retry_falsification_payload),
            "attempt_2_activations": sum(
                item["attempt_2_activated"]
                for item in attempt_trajectory[
                    "attempt_1_to_attempt_2_transitions"
                ]
            ),
        },
    }
    result = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "terminal_envelope_sha256": envelope["envelope_sha256"],
        "ledger_head_event_sha256": envelope["ledger_binding"]["head_event_sha256"],
        "receipt_set_sha256": envelope["receipt_set_sha256"],
        "records_sha256": records_sha256,
        "receipt_projections_sha256": receipt_projections_sha256,
        "analysis_input_sha256": input_commitment,
        "analysis_policy_sha256": digest(policy),
        "analysis_population": {
            "frozen_slots": len(assignment_list),
            "frozen_cells": len(expected_ids),
            "observed_cells": len(cells),
            "admissible_cells": len(admissible),
            "complete_admissible_slots": len(acceptance_values),
            "missing_cells": len(missing),
            "inadmissible_by_arm_and_termination": dict(
                sorted(Counter(f"{cell['arm']}:{cell['termination']}" for cell in inadmissible).items())
            ),
            "rule": "no imputation; repository clusters are the independent bootstrap units",
        },
        "acceptance": {
            "by_arm": by_arm,
            "paired_repository_clusters": acceptance,
            "paired_slot_differences": slot_differences,
            "discordant_repetitions": {
                **dict(opposite_counts),
                "total": sum(opposite_counts.values()),
            },
        },
        "work": work,
        "attempt_trajectory": attempt_trajectory,
        "falsification": falsification,
        "esg_rr_002_usefulness": esg_usefulness,
        "prior_evidence_comparison": prior_evidence_comparison,
        "work_policy_caveat": policy["work_policy"][
            "accepted_conditional_denominator"
        ],
        "scientific_disposition": disposition,
        "terminal_integrity": {
            "protocol_valid": envelope["protocol_valid"],
            "batch_stop_classification": envelope["batch_stop_classification"],
            "terminal_status": envelope["terminal_status"],
            "stage_1_audit_sha256": envelope["stage_1_audit_sha256"],
        },
        "claim_boundaries": {
            "exploratory_only": True,
            "equivalence_claim_permitted": False,
            "noninferiority_claim_permitted": False,
            "accepted_conditional_work_is_descriptive": True,
        },
    }
    return {**result, "analysis_sha256": digest(result)}
