"""Body-free terminalization and exploratory analysis for Pilot-v3."""

from __future__ import annotations

import json
import math
import shlex
from collections import Counter, defaultdict
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

from .experiment import ExperimentConfigurationError
from .pilot_runner import sha256_file
from .pilot_v3_successor import next_successor_action, validate_successor_ledger
from .trace import _verification_kind

USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "calculated_fresh_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
WORK_FIELDS = (*USAGE_FIELDS, "wall_seconds")
TRACE_COUNT_FIELDS = (
    "agent_messages",
    "command_executions",
    "failed_command_executions",
    "read_search_commands",
    "verification_commands",
    "failed_verification_commands",
    "file_changes",
    "web_searches",
)
READ_PROGRAMS = {"cat", "find", "head", "ls", "rg", "sed", "tail", "wc"}
DIAGNOSTIC_WORK_FIELDS = (
    *WORK_FIELDS,
    "subject_turns",
    "evaluator_invocations",
    *TRACE_COUNT_FIELDS,
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected JSON object: {path}")
    return value


def _fraction_number(value: Fraction, digits: int = 6) -> float:
    return round(float(value), digits)


def _median(values: Iterable[Fraction]) -> Fraction:
    ordered = sorted(values)
    if not ordered:
        raise ExperimentConfigurationError("cannot summarize an empty distribution")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _nearest_rank(distribution: Counter[Fraction], probability: Fraction) -> Fraction:
    total = sum(distribution.values())
    rank = math.ceil(probability * total)
    seen = 0
    for value, count in sorted(distribution.items()):
        seen += count
        if seen >= rank:
            return value
    raise ExperimentConfigurationError("bootstrap percentile could not be resolved")


def _bootstrap_distribution(values: list[Fraction]) -> Counter[Fraction]:
    """Return the exact task bootstrap mean distribution with replacement."""

    if not values:
        raise ExperimentConfigurationError("task-level bootstrap requires tasks")
    one_draw = Counter(values)
    sums: Counter[Fraction] = Counter({Fraction(): 1})
    for _ in values:
        updated: Counter[Fraction] = Counter()
        for partial, partial_count in sums.items():
            for value, value_count in one_draw.items():
                updated[partial + value] += partial_count * value_count
        sums = updated
    return Counter({total / len(values): count for total, count in sums.items()})


def _bootstrap_ratio_distribution(
    treatment: list[Fraction], baseline: list[Fraction]
) -> Counter[Fraction]:
    if not treatment or len(treatment) != len(baseline):
        raise ExperimentConfigurationError("paired ratio bootstrap requires equal task vectors")
    one_draw = Counter(zip(treatment, baseline))
    sums: Counter[tuple[Fraction, Fraction]] = Counter({(Fraction(), Fraction()): 1})
    for _ in treatment:
        updated: Counter[tuple[Fraction, Fraction]] = Counter()
        for (short_sum, baseline_sum), partial_count in sums.items():
            for (short_value, baseline_value), value_count in one_draw.items():
                updated[(short_sum + short_value, baseline_sum + baseline_value)] += (
                    partial_count * value_count
                )
        sums = updated
    ratios: Counter[Fraction] = Counter()
    for (short_sum, baseline_sum), count in sums.items():
        if baseline_sum:
            ratios[short_sum / baseline_sum] += count
    return ratios


def _interval(distribution: Counter[Fraction]) -> dict[str, float]:
    return {
        "lower": _fraction_number(_nearest_rank(distribution, Fraction(1, 40))),
        "upper": _fraction_number(_nearest_rank(distribution, Fraction(39, 40))),
    }


def _duration_microseconds(receipt: dict[str, Any]) -> int:
    try:
        started = datetime.fromisoformat(receipt["attempt_started_at"])
        ended = datetime.fromisoformat(receipt["ended_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ExperimentConfigurationError("receipt timestamps are invalid") from error
    delta = ended - started
    value = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if value < 0:
        raise ExperimentConfigurationError("receipt duration is negative")
    return value


def _metric(receipt: dict[str, Any], field: str) -> Fraction:
    if field == "acceptance":
        return Fraction(receipt["termination"] == "accepted_completed")
    if field == "wall_seconds":
        return Fraction(_duration_microseconds(receipt), 1_000_000)
    value = receipt.get("usage", {}).get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExperimentConfigurationError(f"receipt usage is invalid: {field}")
    return Fraction(value)


def _arm_summary(receipts: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [_metric(receipt, field) for receipt in receipts]
    return {
        "cells": len(values),
        "mean": _fraction_number(sum(values, Fraction()) / len(values)),
        "median": _fraction_number(_median(values)),
    }


def _paired_metric(
    complete_tasks: dict[int, dict[str, list[dict[str, Any]]]], field: str
) -> dict[str, Any]:
    short_values: list[Fraction] = []
    baseline_values: list[Fraction] = []
    for slot in sorted(complete_tasks):
        arms = complete_tasks[slot]
        short_values.append(
            sum((_metric(item, field) for item in arms["short"]), Fraction())
            / len(arms["short"])
        )
        baseline_values.append(
            sum((_metric(item, field) for item in arms["baseline"]), Fraction())
            / len(arms["baseline"])
        )
    differences = [short - baseline for short, baseline in zip(short_values, baseline_values)]
    result: dict[str, Any] = {
        "baseline_task_mean": _fraction_number(sum(baseline_values, Fraction()) / len(baseline_values)),
        "baseline_task_median": _fraction_number(_median(baseline_values)),
        "short_task_mean": _fraction_number(sum(short_values, Fraction()) / len(short_values)),
        "short_task_median": _fraction_number(_median(short_values)),
        "short_minus_baseline": _fraction_number(sum(differences, Fraction()) / len(differences)),
        "difference_95_percentile_interval": _interval(_bootstrap_distribution(differences)),
    }
    if field != "acceptance":
        ratio = (sum(short_values, Fraction()) / len(short_values)) / (
            sum(baseline_values, Fraction()) / len(baseline_values)
        )
        result["short_over_baseline_ratio"] = _fraction_number(ratio)
        result["ratio_95_percentile_interval"] = _interval(
            _bootstrap_ratio_distribution(short_values, baseline_values)
        )
    return result


def summarize_receipts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize only admissible outcomes and complete two-repetition task clusters."""

    admissible = [receipt for receipt in receipts if receipt.get("admissible") is True]
    by_arm = {
        arm: [receipt for receipt in admissible if receipt.get("arm") == arm]
        for arm in ("baseline", "short")
    }
    if any(not values for values in by_arm.values()):
        raise ExperimentConfigurationError("both arms require admissible observations")
    clustered: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"baseline": [], "short": []}
    )
    for receipt in admissible:
        slot = receipt.get("requested_task_slot")
        if not isinstance(slot, int) or isinstance(slot, bool):
            raise ExperimentConfigurationError("receipt task slot is invalid")
        clustered[slot][receipt["arm"]].append(receipt)
    complete = {
        slot: arms
        for slot, arms in clustered.items()
        if sorted(item["repetition"] for item in arms["baseline"]) == [1, 2]
        and sorted(item["repetition"] for item in arms["short"]) == [1, 2]
    }
    if len(complete) < 2:
        raise ExperimentConfigurationError("too few complete task clusters for exploration")
    acceptance = _paired_metric(complete, "acceptance")
    acceptance["short_minus_baseline_percentage_points"] = round(
        acceptance.pop("short_minus_baseline") * 100, 6
    )
    acceptance["difference_95_percentile_interval_percentage_points"] = {
        key: round(value * 100, 6)
        for key, value in acceptance.pop("difference_95_percentile_interval").items()
    }
    accepted_counts = {
        arm: sum(item["termination"] == "accepted_completed" for item in values)
        for arm, values in by_arm.items()
    }
    discordance = Counter()
    for arms in complete.values():
        indexed = {
            arm: {item["repetition"]: item for item in values}
            for arm, values in arms.items()
        }
        for repetition in (1, 2):
            baseline_accepted = (
                indexed["baseline"][repetition]["termination"] == "accepted_completed"
            )
            short_accepted = (
                indexed["short"][repetition]["termination"] == "accepted_completed"
            )
            label = {
                (True, True): "both_accepted",
                (False, False): "both_failed",
                (True, False): "baseline_only_accepted",
                (False, True): "short_only_accepted",
            }[(baseline_accepted, short_accepted)]
            discordance[label] += 1
    instability = {
        arm: sum(
            len(
                {
                    item["termination"] == "accepted_completed"
                    for item in arms[arm]
                }
            )
            > 1
            for arms in complete.values()
        )
        for arm in ("baseline", "short")
    }
    return {
        "analysis_population": {
            "admissible_cells": len(admissible),
            "complete_task_clusters": len(complete),
            "complete_paired_cells": len(complete) * 4,
            "excluded_incomplete_task_slots": sorted(set(clustered) - set(complete)),
            "rule": (
                "primary paired estimates use tasks with both frozen repetitions in both arms; "
                "all admissible cells remain in marginal summaries"
            ),
        },
        "marginal_acceptance": {
            arm: {
                "accepted": accepted_counts[arm],
                "cells": len(values),
                "rate": round(accepted_counts[arm] / len(values), 6),
            }
            for arm, values in by_arm.items()
        },
        "paired_acceptance": acceptance,
        "acceptance_diagnostics": {
            "complete_repetition_pairs": len(complete) * 2,
            "discordance": dict(sorted(discordance.items())),
            "tasks_with_between_repetition_acceptance_instability": instability,
        },
        "marginal_work": {
            field: {arm: _arm_summary(values, field) for arm, values in by_arm.items()}
            for field in WORK_FIELDS
        },
        "paired_work": {field: _paired_metric(complete, field) for field in WORK_FIELDS},
        "uncertainty": {
            "method": "exact nonparametric task bootstrap with replacement",
            "resampled_unit": "complete task cluster",
            "draws_per_resample": len(complete),
            "ordered_resamples": len(complete) ** len(complete),
            "interval": "nearest-rank 2.5th and 97.5th percentiles",
        },
    }


def build_terminal_result(root: Path, ledger_path: Path) -> dict[str, Any]:
    """Validate the terminal successor ledger and build a sanitized result."""

    contract = _read_object(root / "experiment/pilot_v3_execution_contract.json")
    authorization = _read_object(root / "experiment/pilot_v3_successor_authorization.json")
    events = validate_successor_ledger(authorization, ledger_path)
    action = next_successor_action(contract, authorization, events)
    if action != {
        "action": "batch_stopped",
        "payload": {"preserved": True, "termination": "attempt_limit_exhausted"},
    }:
        raise ExperimentConfigurationError("successor is not at the expected terminal boundary")
    receipts = [event["payload"] for event in events if event["event_type"] == "receipt_committed"]
    starts = [event for event in events if event["event_type"] == "attempt_started"]
    reruns = [event for event in events if event["event_type"] == "infrastructure_rerun_authorized"]
    stops = [event for event in events if event["event_type"] == "batch_stopped"]
    event_counts = Counter(event["event_type"] for event in events)
    invalid = [receipt for receipt in receipts if receipt.get("admissible") is False]
    if (
        len(events) != 288
        or len(starts) != 33
        or len(receipts) != 33
        or len(reruns) != 1
        or len(stops) != 1
        or len(invalid) != 2
        or any(item.get("position") != 32 for item in invalid)
        or [item.get("trajectory_attempt") for item in invalid] != [1, 2]
        or any(item.get("termination") != "local_docker_runtime_infrastructure_failure" for item in invalid)
    ):
        raise ExperimentConfigurationError("terminal successor ledger shape is unexpected")
    analysis = summarize_receipts(receipts)
    immutable_paths = (
        "experiment/pilot_v3_execution_contract.json",
        "experiment/pilot_v3_pool.json",
        "experiment/pilot_v3_schedule.json",
        "experiment/pilot_v3_terminal_result.json",
        "experiment/pilot_v3_successor_authorization.json",
    )
    terminal_event = stops[0]
    return {
        "schema_name": "engineering-scope-guard.pilot-v3-successor-terminal-result",
        "schema_version": 1,
        "recorded_at": terminal_event["recorded_at"],
        "status": "terminal_partial_schedule_analyzable",
        "decision": "PILOT-V3 SUCCESSOR TERMINAL — EXPLORATORY EVIDENCE ONLY",
        "termination": "attempt_limit_exhausted",
        "schedule": {
            "frozen_cells": 32,
            "attempts_started": len(starts),
            "admissible_cells": analysis["analysis_population"]["admissible_cells"],
            "infrastructure_invalid_attempts": len(invalid),
            "missing_cells": 1,
            "missing_position": 32,
            "missing_cell_id": invalid[0]["cell_id"],
            "complete_task_clusters": analysis["analysis_population"]["complete_task_clusters"],
        },
        "outcomes": dict(sorted(Counter(item["termination"] for item in receipts).items())),
        "retry_accounting": {
            "infrastructure_reruns_consumed": len(reruns),
            "infrastructure_rerun_allowance": authorization["accounting"]["infrastructure_rerun_allowance"],
            "operator_interruptions_consumed": 0,
            "operator_interruption_allowance": authorization["accounting"]["operator_interruption_allowance"],
            "position_32_attempt_3_permitted": False,
        },
        "ledger": {
            "sha256": sha256_file(ledger_path),
            "events": len(events),
            "last_event_sha256": terminal_event["event_sha256"],
            "event_counts": dict(sorted(event_counts.items())),
        },
        "immutable_evidence_sha256": {
            path: sha256_file(root / path) for path in immutable_paths
        },
        "analysis": analysis,
        "billing": {
            "provider_billed_amount": "unavailable",
            "currency": "unavailable",
            "inference_performed": False,
        },
        "claims": {
            "exploratory_only": True,
            "equivalence_or_noninferiority_supported": False,
            "quality_preservation_supported": False,
            "per_language_effect_supported": False,
            "maintainability_or_downstream_work_supported": False,
            "provider_billing_claim_supported": False,
            "confirmatory_execution_authorized": False,
        },
        "repair_or_fallback": {
            "pilot_v4_created": False,
            "reason": (
                "both invalid attempts produced complete coherent receipts and the frozen "
                "state machine enforced its attempt limit; no outcome-independent harness defect was found"
            ),
        },
    }


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _trace_counts(path: Path) -> dict[str, int]:
    counts = Counter({field: 0 for field in TRACE_COUNT_FIELDS})
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ExperimentConfigurationError("subject trace is unavailable") from error
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError("subject trace contains invalid JSON") from error
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            raise ExperimentConfigurationError("completed trace item is invalid")
        item_type = item.get("type")
        field = {
            "agent_message": "agent_messages",
            "command_execution": "command_executions",
            "file_change": "file_changes",
            "web_search": "web_searches",
        }.get(item_type)
        if field is not None:
            counts[field] += 1
        if item_type == "command_execution":
            exit_code = item.get("exit_code")
            if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
                counts["failed_command_executions"] += 1
            raw_command = item.get("command", "")
            command = " ".join(raw_command) if isinstance(raw_command, list) else str(raw_command)
            verification_kind = _verification_kind(command)
            if verification_kind != "other":
                counts["verification_commands"] += 1
                if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
                    counts["failed_verification_commands"] += 1
            try:
                wrapper_tokens = shlex.split(command)
            except ValueError:
                wrapper_tokens = []
            if (
                len(wrapper_tokens) >= 3
                and Path(wrapper_tokens[0]).name in {"bash", "sh", "zsh"}
                and wrapper_tokens[1] in {"-c", "-lc"}
            ):
                try:
                    tokens = shlex.split(wrapper_tokens[2])
                except ValueError:
                    tokens = []
            else:
                tokens = wrapper_tokens
            segments: list[list[str]] = [[]]
            for token in tokens:
                if token in {"&&", "||", ";", "|"}:
                    segments.append([])
                else:
                    segments[-1].append(token)
            for segment in segments:
                while segment and "=" in segment[0] and not segment[0].startswith(("/", "./")):
                    segment = segment[1:]
                if segment and Path(segment[0]).name in READ_PROGRAMS:
                    counts["read_search_commands"] += 1
    return dict(counts)


def _patch_structure(path: Path) -> dict[str, int]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ExperimentConfigurationError("prediction patch is unavailable") from error
    return {
        "files_changed": sum(line.startswith("diff --git ") for line in lines),
        "lines_added": sum(line.startswith("+") and not line.startswith("+++") for line in lines),
        "lines_deleted": sum(line.startswith("-") and not line.startswith("---") for line in lines),
    }


def _evaluator_check_counts(path: Path) -> dict[str, dict[str, int]]:
    report = _read_object(path)
    result: dict[str, dict[str, int]] = {}
    for field, label in (("FAIL_TO_PASS", "fail_to_pass"), ("PASS_TO_PASS", "pass_to_pass")):
        value = report.get(field)
        if not isinstance(value, dict):
            raise ExperimentConfigurationError("evaluator check summary is invalid")
        success = value.get("success")
        failure = value.get("failure")
        if not isinstance(success, list) or not isinstance(failure, list):
            raise ExperimentConfigurationError("evaluator check buckets are invalid")
        result[label] = {"passed": len(success), "failed": len(failure)}
    return result


def _diagnostic_metric(cell: dict[str, Any], field: str) -> Fraction:
    if field == "wall_seconds":
        return Fraction(str(cell[field]))
    if field in USAGE_FIELDS:
        value = cell["usage"][field]
    elif field in TRACE_COUNT_FIELDS:
        value = cell["trace_completed_item_counts"][field]
    else:
        value = cell[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExperimentConfigurationError(f"diagnostic metric is invalid: {field}")
    return Fraction(value)


def _task_arm_mean(task: dict[str, Any], arm: str, field: str) -> Fraction:
    values = [
        _diagnostic_metric(cell, field)
        for cell in task["cells"]
        if cell["arm"] == arm
    ]
    if len(values) != 2:
        raise ExperimentConfigurationError("diagnostic task-arm requires two repetitions")
    return sum(values, Fraction()) / 2


def _diagnostic_decomposition(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in DIAGNOSTIC_WORK_FIELDS:
        baseline = [_task_arm_mean(task, "baseline", field) for task in tasks]
        short = [_task_arm_mean(task, "short", field) for task in tasks]
        baseline_mean = sum(baseline, Fraction()) / len(tasks)
        short_mean = sum(short, Fraction()) / len(tasks)
        entry: dict[str, Any] = {
            "baseline_task_mean": _fraction_number(baseline_mean),
            "short_task_mean": _fraction_number(short_mean),
            "short_minus_baseline": _fraction_number(short_mean - baseline_mean),
            "task_differences": [
                {
                    "public_task_id": task["public_task_id"],
                    "short_minus_baseline": _fraction_number(short_value - baseline_value),
                }
                for task, short_value, baseline_value in zip(tasks, short, baseline)
            ],
        }
        if baseline_mean:
            entry["short_over_baseline_ratio"] = _fraction_number(short_mean / baseline_mean)
        result[field] = entry
    return result


def _acceptance_task_difference(task: dict[str, Any]) -> Fraction:
    values = {
        arm: Fraction(
            sum(cell["accepted"] for cell in task["cells"] if cell["arm"] == arm),
            2,
        )
        for arm in ("baseline", "short")
    }
    return values["short"] - values["baseline"]


def _leave_one_task_out(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for omitted in tasks:
        retained = [task for task in tasks if task is not omitted]
        acceptance = sum((_acceptance_task_difference(task) for task in retained), Fraction())
        acceptance /= len(retained)
        item: dict[str, Any] = {
            "omitted_public_task_id": omitted["public_task_id"],
            "short_minus_baseline_acceptance_percentage_points": _fraction_number(
                acceptance * 100
            ),
        }
        for field in ("input_tokens", "cached_input_tokens", "calculated_fresh_input_tokens", "wall_seconds"):
            baseline = sum(
                (_task_arm_mean(task, "baseline", field) for task in retained), Fraction()
            )
            short = sum(
                (_task_arm_mean(task, "short", field) for task in retained), Fraction()
            )
            item[f"{field}_short_over_baseline_ratio"] = _fraction_number(short / baseline)
        summaries.append(item)
    return summaries


def _outcome_class_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        cells = {
            (cell["arm"], cell["repetition"]): cell for cell in task["cells"]
        }
        for repetition in (1, 2):
            baseline = cells[("baseline", repetition)]
            short = cells[("short", repetition)]
            label = {
                (True, True): "both_accepted",
                (False, False): "both_failed",
                (True, False): "baseline_only_accepted",
                (False, True): "short_only_accepted",
            }[(baseline["accepted"], short["accepted"])]
            grouped[label].append({"baseline": baseline, "short": short})
    result: dict[str, Any] = {}
    for label, pairs in sorted(grouped.items()):
        entry: dict[str, Any] = {"pairs": len(pairs)}
        for field in ("input_tokens", "cached_input_tokens", "calculated_fresh_input_tokens", "wall_seconds", "subject_turns", "command_executions"):
            differences = [
                _diagnostic_metric(pair["short"], field)
                - _diagnostic_metric(pair["baseline"], field)
                for pair in pairs
            ]
            entry[f"{field}_mean_short_minus_baseline"] = _fraction_number(
                sum(differences, Fraction()) / len(differences)
            )
        result[label] = entry
    return result


def _turn_normalized_usage(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    cells = [cell for task in tasks for cell in task["cells"]]
    totals: dict[str, dict[str, int]] = {}
    for arm in ("baseline", "short"):
        arm_cells = [cell for cell in cells if cell["arm"] == arm]
        totals[arm] = {
            "subject_turns": sum(cell["subject_turns"] for cell in arm_cells),
            **{
                field: sum(cell["usage"][field] for cell in arm_cells)
                for field in USAGE_FIELDS
            },
        }
    result: dict[str, Any] = {"arm_totals": totals, "per_subject_turn": {}}
    for field in USAGE_FIELDS:
        baseline = Fraction(totals["baseline"][field], totals["baseline"]["subject_turns"])
        short = Fraction(totals["short"][field], totals["short"]["subject_turns"])
        result["per_subject_turn"][field] = {
            "baseline": _fraction_number(baseline),
            "short": _fraction_number(short),
            "short_over_baseline_ratio": _fraction_number(short / baseline),
        }
    input_difference = totals["short"]["input_tokens"] - totals["baseline"]["input_tokens"]
    cached_difference = (
        totals["short"]["cached_input_tokens"] - totals["baseline"]["cached_input_tokens"]
    )
    fresh_difference = (
        totals["short"]["calculated_fresh_input_tokens"]
        - totals["baseline"]["calculated_fresh_input_tokens"]
    )
    if input_difference != cached_difference + fresh_difference or input_difference <= 0:
        raise ExperimentConfigurationError("turn-normalized input decomposition is inconsistent")
    result["input_difference_decomposition"] = {
        "total_input_tokens": input_difference,
        "cached_input_tokens": cached_difference,
        "calculated_fresh_input_tokens": fresh_difference,
        "cached_share": _fraction_number(Fraction(cached_difference, input_difference)),
        "calculated_fresh_share": _fraction_number(Fraction(fresh_difference, input_difference)),
    }
    return result


def build_mechanism_diagnostic(root: Path, ledger_path: Path) -> dict[str, Any]:
    """Build a body-safe diagnostic from validated durable Pilot-v3 evidence."""

    terminal = build_terminal_result(root, ledger_path)
    persisted_path = root / "experiment/pilot_v3_successor_terminal_result.json"
    if canonical_json(terminal) != persisted_path.read_text(encoding="utf-8"):
        raise ExperimentConfigurationError("persisted Pilot-v3 terminal result does not reproduce")

    authorization = _read_object(root / "experiment/pilot_v3_successor_authorization.json")
    events = validate_successor_ledger(authorization, ledger_path)
    receipts = [event["payload"] for event in events if event["event_type"] == "receipt_committed"]
    subjects: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    evaluators: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        payload = event["payload"]
        key = (payload.get("cell_id"), payload.get("trajectory_attempt"))
        if event["event_type"] == "subject_terminated":
            subjects[key].append(payload)
        elif event["event_type"] == "evaluator_finished":
            evaluators[key].append(payload)

    public_tasks = {
        item["slot"]: item["actual_task_id"]
        for item in _read_object(root / "experiment/pilot_v3_pool.json")["slots"]
    }
    schedule = {
        item["cell_id"]: item
        for item in _read_object(root / "experiment/pilot_v3_schedule.json")["cells"]
    }
    cells: list[dict[str, Any]] = []
    for receipt in receipts:
        if receipt.get("admissible") is not True:
            continue
        key = (receipt["cell_id"], receipt["trajectory_attempt"])
        subject_events = sorted(subjects[key], key=lambda item: item["round"])
        evaluator_events = sorted(evaluators[key], key=lambda item: item["round"])
        if not subject_events or len(subject_events) != len(evaluator_events):
            raise ExperimentConfigurationError("subject/evaluator round accounting is inconsistent")
        usage = {
            field: sum(item["usage"][field] for item in subject_events)
            for field in USAGE_FIELDS
            if field != "calculated_fresh_input_tokens"
        }
        usage["calculated_fresh_input_tokens"] = (
            usage["input_tokens"] - usage["cached_input_tokens"]
        )
        if usage != receipt["usage"]:
            raise ExperimentConfigurationError("receipt usage does not equal subject-round usage")
        if usage["input_tokens"] - usage["cached_input_tokens"] != usage["calculated_fresh_input_tokens"]:
            raise ExperimentConfigurationError("fresh-input arithmetic is inconsistent")
        counts = Counter({field: 0 for field in TRACE_COUNT_FIELDS})
        for subject_event in subject_events:
            for field, value in _trace_counts(Path(subject_event["trace_reference"])).items():
                counts[field] += value
        frozen = schedule[receipt["cell_id"]]
        for field in ("arm", "position", "repetition", "requested_task_slot", "actual_task_id"):
            if receipt[field] != frozen[field]:
                raise ExperimentConfigurationError(f"receipt/schedule assignment mismatch: {field}")
        final_evaluator = evaluator_events[-1]
        cells.append(
            {
                "cell_id": receipt["cell_id"],
                "position": receipt["position"],
                "arm": receipt["arm"],
                "repetition": receipt["repetition"],
                "trajectory_attempt": receipt["trajectory_attempt"],
                "accepted": receipt["termination"] == "accepted_completed",
                "termination": receipt["termination"],
                "official_evaluator_disposition": final_evaluator["official_disposition"],
                "feedback_status": final_evaluator["feedback_status"],
                "corrective_round_used": len(subject_events) == 2,
                "subject_turns": len(subject_events),
                "evaluator_invocations": len(evaluator_events),
                "failing_check_counts_by_round": [
                    len(item["failing_checks"]) for item in evaluator_events
                ],
                "official_evaluator_check_counts": _evaluator_check_counts(
                    Path(final_evaluator["report_reference"])
                ),
                "usage": usage,
                "wall_seconds": _fraction_number(
                    Fraction(_duration_microseconds(receipt), 1_000_000)
                ),
                "trace_completed_item_counts": dict(counts),
                "prediction_patch_structure": _patch_structure(
                    Path(receipt["isolation_roots"]["derived"]) / "prediction.patch"
                ),
            }
        )

    by_slot: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        by_slot[schedule[cell["cell_id"]]["requested_task_slot"]].append(cell)
    tasks: list[dict[str, Any]] = []
    for slot, task_cells in sorted(by_slot.items()):
        if len(task_cells) != 4:
            continue
        task_cells.sort(key=lambda item: (item["repetition"], item["arm"]))
        pairs = []
        for repetition in (1, 2):
            indexed = {cell["arm"]: cell for cell in task_cells if cell["repetition"] == repetition}
            pairs.append(
                {
                    "repetition": repetition,
                    "classification": {
                        (True, True): "both_accepted",
                        (False, False): "both_failed",
                        (True, False): "baseline_only_accepted",
                        (False, True): "short_only_accepted",
                    }[(indexed["baseline"]["accepted"], indexed["short"]["accepted"])],
                }
            )
        tasks.append(
            {
                "task_slot": slot,
                "public_task_id": public_tasks[slot],
                "repetition_pair_classifications": pairs,
                "cells": task_cells,
            }
        )
    if len(tasks) != 7:
        raise ExperimentConfigurationError("expected seven complete diagnostic task clusters")

    decomposition = _diagnostic_decomposition(tasks)
    loo = _leave_one_task_out(tasks)
    return {
        "schema_name": "engineering-scope-guard.pilot-v3-c-short-mechanism-diagnostic",
        "schema_version": 1,
        "body_safe": True,
        "interpretation": "post-hoc exploratory diagnostics; not causal or confirmatory evidence",
        "source_evidence": {
            "successor_ledger_sha256": sha256_file(ledger_path),
            "terminal_result_sha256": sha256_file(persisted_path),
            "contract_sha256": sha256_file(root / "experiment/pilot_v3_execution_contract.json"),
            "pool_sha256": sha256_file(root / "experiment/pilot_v3_pool.json"),
            "schedule_sha256": sha256_file(root / "experiment/pilot_v3_schedule.json"),
            "c_short_v0_1_sha256": sha256_file(root / "experiment/arms/short.txt"),
        },
        "reconciliation": {
            "persisted_terminal_result_reproduced_byte_for_byte": True,
            "validated_successor_ledger_events": len(events),
            "admissible_receipts": len(cells),
            "complete_task_clusters": len(tasks),
            "excluded_incomplete_task_slots": terminal["analysis"]["analysis_population"]["excluded_incomplete_task_slots"],
            "usage_round_sums_match_receipts": True,
            "fresh_input_equals_input_minus_cached_input": True,
            "receipt_assignments_match_frozen_schedule": True,
        },
        "tasks": tasks,
        "work_amplification_decomposition": decomposition,
        "turn_normalized_usage": _turn_normalized_usage(tasks),
        "outcome_class_decomposition": _outcome_class_summary(tasks),
        "leave_one_task_out": loo,
        "leave_one_task_out_ranges": {
            "acceptance_difference_percentage_points": {
                "minimum": min(item["short_minus_baseline_acceptance_percentage_points"] for item in loo),
                "maximum": max(item["short_minus_baseline_acceptance_percentage_points"] for item in loo),
            },
            "input_token_ratio": {
                "minimum": min(item["input_tokens_short_over_baseline_ratio"] for item in loo),
                "maximum": max(item["input_tokens_short_over_baseline_ratio"] for item in loo),
            },
            "wall_time_ratio": {
                "minimum": min(item["wall_seconds_short_over_baseline_ratio"] for item in loo),
                "maximum": max(item["wall_seconds_short_over_baseline_ratio"] for item in loo),
            },
        },
        "billing": {
            "provider_billed_amount": "unavailable",
            "currency": "unavailable",
            "inference_performed": False,
        },
    }
