#!/usr/bin/env python3
"""Audit ESG-RR-001 public artifact identities and core analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_v3_analysis import (
    _bootstrap_distribution,
    _bootstrap_ratio_distribution,
    _fraction_number,
    _interval,
    canonical_json,
)

WORK_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "calculated_fresh_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "wall_seconds",
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: Any, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentConfigurationError(f"invalid numeric value for {label}")
    return Fraction(str(value))


def _task_vectors(
    diagnostic: dict[str, Any], field: str
) -> tuple[list[Fraction], list[Fraction]]:
    baseline: list[Fraction] = []
    short: list[Fraction] = []
    tasks = diagnostic.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 7:
        raise ExperimentConfigurationError("diagnostic must contain exactly seven tasks")
    for task in tasks:
        cells = task.get("cells") if isinstance(task, dict) else None
        if not isinstance(cells, list) or len(cells) != 4:
            raise ExperimentConfigurationError("each diagnostic task must contain four cells")
        indexed: dict[tuple[str, int], dict[str, Any]] = {}
        for cell in cells:
            key = (cell.get("arm"), cell.get("repetition"))
            if key in indexed or key[0] not in {"baseline", "short"} or key[1] not in {1, 2}:
                raise ExperimentConfigurationError("diagnostic arm/repetition population drift")
            indexed[key] = cell
        if set(indexed) != {
            ("baseline", 1),
            ("baseline", 2),
            ("short", 1),
            ("short", 2),
        }:
            raise ExperimentConfigurationError("diagnostic arm/repetition population is incomplete")

        def cell_value(arm: str, repetition: int) -> Fraction:
            cell = indexed[(arm, repetition)]
            if field == "acceptance":
                value = cell.get("accepted")
                if not isinstance(value, bool):
                    raise ExperimentConfigurationError("diagnostic acceptance is invalid")
                return Fraction(value)
            if field == "wall_seconds":
                return _number(cell.get(field), field)
            usage = cell.get("usage")
            if not isinstance(usage, dict):
                raise ExperimentConfigurationError("diagnostic usage is invalid")
            return _number(usage.get(field), field)

        baseline.append((cell_value("baseline", 1) + cell_value("baseline", 2)) / 2)
        short.append((cell_value("short", 1) + cell_value("short", 2)) / 2)
    return baseline, short


def _paired_summary(diagnostic: dict[str, Any], field: str) -> dict[str, Any]:
    baseline, short = _task_vectors(diagnostic, field)
    differences = [treatment - control for treatment, control in zip(short, baseline)]
    result: dict[str, Any] = {
        "baseline_task_mean": _fraction_number(sum(baseline, Fraction()) / len(baseline)),
        "short_task_mean": _fraction_number(sum(short, Fraction()) / len(short)),
        "short_minus_baseline": _fraction_number(
            sum(differences, Fraction()) / len(differences)
        ),
        "difference_95_percentile_interval": _interval(
            _bootstrap_distribution(differences)
        ),
    }
    if field != "acceptance":
        result["short_over_baseline_ratio"] = _fraction_number(
            sum(short, Fraction()) / sum(baseline, Fraction())
        )
        result["ratio_95_percentile_interval"] = _interval(
            _bootstrap_ratio_distribution(short, baseline)
        )
    return result


def _discordance(diagnostic: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for task in diagnostic["tasks"]:
        indexed = {
            (cell["arm"], cell["repetition"]): cell["accepted"]
            for cell in task["cells"]
        }
        for repetition in (1, 2):
            label = {
                (True, True): "both_accepted",
                (False, False): "both_failed",
                (True, False): "baseline_only_accepted",
                (False, True): "short_only_accepted",
            }[(indexed[("baseline", repetition)], indexed[("short", repetition)])]
            counts[label] += 1
    return dict(sorted(counts.items()))


def _decomposition(diagnostic: dict[str, Any]) -> dict[str, Any]:
    totals = {
        arm: {field: 0 for field in (*WORK_FIELDS[:-1], "subject_turns")}
        for arm in ("baseline", "short")
    }
    for task in diagnostic["tasks"]:
        for cell in task["cells"]:
            arm = cell["arm"]
            for field in WORK_FIELDS[:-1]:
                totals[arm][field] += cell["usage"][field]
            totals[arm]["subject_turns"] += cell["subject_turns"]
    input_difference = totals["short"]["input_tokens"] - totals["baseline"]["input_tokens"]
    cached_difference = (
        totals["short"]["cached_input_tokens"]
        - totals["baseline"]["cached_input_tokens"]
    )
    fresh_difference = (
        totals["short"]["calculated_fresh_input_tokens"]
        - totals["baseline"]["calculated_fresh_input_tokens"]
    )
    if input_difference <= 0 or cached_difference + fresh_difference != input_difference:
        raise ExperimentConfigurationError("cached/fresh input decomposition is inconsistent")
    return {
        "arm_totals": totals,
        "input_difference_decomposition": {
            "total_input_tokens": input_difference,
            "cached_input_tokens": cached_difference,
            "cached_share": _fraction_number(Fraction(cached_difference, input_difference)),
            "calculated_fresh_input_tokens": fresh_difference,
            "calculated_fresh_share": _fraction_number(
                Fraction(fresh_difference, input_difference)
            ),
        },
    }


def _leave_one_task_out(diagnostic: dict[str, Any]) -> dict[str, dict[str, float]]:
    vectors = {
        field: _task_vectors(diagnostic, field)
        for field in ("acceptance", "input_tokens", "wall_seconds")
    }
    values: dict[str, list[Fraction]] = {
        "acceptance_difference_percentage_points": [],
        "input_token_ratio": [],
        "wall_time_ratio": [],
    }
    for omitted in range(7):
        for field, output_key in (
            ("acceptance", "acceptance_difference_percentage_points"),
            ("input_tokens", "input_token_ratio"),
            ("wall_seconds", "wall_time_ratio"),
        ):
            baseline, short = vectors[field]
            kept_baseline = [value for index, value in enumerate(baseline) if index != omitted]
            kept_short = [value for index, value in enumerate(short) if index != omitted]
            if field == "acceptance":
                estimate = (
                    sum(kept_short, Fraction()) - sum(kept_baseline, Fraction())
                ) / len(kept_short) * 100
            else:
                estimate = sum(kept_short, Fraction()) / sum(kept_baseline, Fraction())
            values[output_key].append(estimate)
    return {
        key: {
            "minimum": _fraction_number(min(estimates)),
            "maximum": _fraction_number(max(estimates)),
        }
        for key, estimates in values.items()
    }


def _level_one(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ExperimentConfigurationError("manifest artifacts are missing")
    verified = []
    for artifact in artifacts:
        relative = artifact.get("path") if isinstance(artifact, dict) else None
        expected = artifact.get("sha256") if isinstance(artifact, dict) else None
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ExperimentConfigurationError("manifest artifact entry is invalid")
        path = root / relative
        actual = _sha256(path)
        if actual != expected:
            raise ExperimentConfigurationError(f"artifact digest mismatch: {relative}")
        verified.append({"path": relative, "sha256": actual})
    return {"status": "pass", "artifacts": verified}


def _level_two(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    diagnostic = _read_object(root / "experiment/pilot_v3_c_short_mechanism_diagnostic.json")
    terminal = _read_object(root / "experiment/pilot_v3_successor_terminal_result.json")
    ledger = _read_object(root / "docs/PUBLIC_RESEARCH_CLAIM_LEDGER_V0_1.json")
    if diagnostic.get("schema_name") != "engineering-scope-guard.pilot-v3-c-short-mechanism-diagnostic":
        raise ExperimentConfigurationError("unexpected mechanism diagnostic schema")
    if diagnostic.get("schema_version") != 1 or diagnostic.get("body_safe") is not True:
        raise ExperimentConfigurationError("mechanism diagnostic is not body-safe schema version 1")
    if ledger.get("report_id") != "ESG-RR-001" or ledger.get("version") != "0.1":
        raise ExperimentConfigurationError("claim ledger report identity mismatch")
    if [claim.get("claim_id") for claim in ledger.get("claims", [])] != [
        f"ESG-RR-001-C0{number}" for number in range(1, 8)
    ]:
        raise ExperimentConfigurationError("claim ledger claim population drift")

    acceptance = _paired_summary(diagnostic, "acceptance")
    acceptance["short_minus_baseline_percentage_points"] = _fraction_number(
        Fraction(str(acceptance.pop("short_minus_baseline"))) * 100
    )
    acceptance["difference_95_percentile_interval_percentage_points"] = {
        key: _fraction_number(Fraction(str(value)) * 100)
        for key, value in acceptance.pop("difference_95_percentile_interval").items()
    }
    work = {field: _paired_summary(diagnostic, field) for field in WORK_FIELDS}
    result = {
        "population": {
            "complete_task_clusters": 7,
            "complete_paired_cells": 28,
            "ordered_task_bootstrap_resamples": 823543,
        },
        "marginal_acceptance": terminal["analysis"]["marginal_acceptance"],
        "paired_acceptance": acceptance,
        "paired_work": work,
        "discordance": _discordance(diagnostic),
        "decomposition": _decomposition(diagnostic),
        "leave_one_task_out_ranges": _leave_one_task_out(diagnostic),
    }
    if result["paired_acceptance"] != {
        key: terminal["analysis"]["paired_acceptance"][key]
        for key in result["paired_acceptance"]
    }:
        raise ExperimentConfigurationError("Level 2 acceptance differs from terminal result")
    for field, summary in work.items():
        for key, value in summary.items():
            if terminal["analysis"]["paired_work"][field][key] != value:
                raise ExperimentConfigurationError(
                    f"Level 2 {field} differs from terminal result"
                )
    if result["leave_one_task_out_ranges"] != diagnostic["leave_one_task_out_ranges"]:
        raise ExperimentConfigurationError("Level 2 leave-one-task-out result differs")
    if result["decomposition"] != {
        "arm_totals": diagnostic["turn_normalized_usage"]["arm_totals"],
        "input_difference_decomposition": diagnostic["turn_normalized_usage"][
            "input_difference_decomposition"
        ],
    }:
        raise ExperimentConfigurationError("Level 2 cached/fresh decomposition differs")
    claims = {claim["claim_id"]: claim for claim in ledger["claims"]}
    acceptance_claim = claims["ESG-RR-001-C01"]
    if acceptance_claim["point_estimate"]["value"] != acceptance[
        "short_minus_baseline_percentage_points"
    ]:
        raise ExperimentConfigurationError("Level 2 acceptance differs from claim C01")
    if (
        acceptance_claim["uncertainty_interval"]["lower"]
        != acceptance["difference_95_percentile_interval_percentage_points"]["lower"]
        or acceptance_claim["uncertainty_interval"]["upper"]
        != acceptance["difference_95_percentile_interval_percentage_points"]["upper"]
    ):
        raise ExperimentConfigurationError("Level 2 acceptance interval differs from claim C01")
    work_claim = claims["ESG-RR-001-C02"]
    if work_claim["point_estimate"] != {
        "input_token_ratio": work["input_tokens"]["short_over_baseline_ratio"],
        "wall_time_ratio": work["wall_seconds"]["short_over_baseline_ratio"],
    }:
        raise ExperimentConfigurationError("Level 2 work ratios differ from claim C02")
    if work_claim["uncertainty_interval"] != {
        "input_token_ratio_95_percentile": [
            work["input_tokens"]["ratio_95_percentile_interval"]["lower"],
            work["input_tokens"]["ratio_95_percentile_interval"]["upper"],
        ],
        "method": "Exact nonparametric task bootstrap with nearest-rank percentiles.",
        "wall_time_ratio_95_percentile": [
            work["wall_seconds"]["ratio_95_percentile_interval"]["lower"],
            work["wall_seconds"]["ratio_95_percentile_interval"]["upper"],
        ],
    }:
        raise ExperimentConfigurationError("Level 2 work intervals differ from claim C02")
    decomposition_claim = claims["ESG-RR-001-C03"]["point_estimate"]
    decomposition = result["decomposition"]["input_difference_decomposition"]
    if decomposition_claim != {
        "cached_input_difference": decomposition["cached_input_tokens"],
        "cached_share": decomposition["cached_share"],
        "calculated_fresh_input_difference": decomposition[
            "calculated_fresh_input_tokens"
        ],
        "calculated_fresh_share": decomposition["calculated_fresh_share"],
        "total_input_difference": decomposition["total_input_tokens"],
    }:
        raise ExperimentConfigurationError("Level 2 decomposition differs from claim C03")
    return {"status": "pass", **result}


def audit(root: Path, level: str) -> dict[str, Any]:
    manifest = _read_object(root / "docs/reports/ESG-RR-001.manifest.json")
    if manifest.get("report_id") != "ESG-RR-001" or manifest.get("version") != "0.6":
        raise ExperimentConfigurationError("manifest report identity mismatch")
    output: dict[str, Any] = {
        "report_id": "ESG-RR-001",
        "version": "0.6",
    }
    if level in {"1", "all"}:
        output["level_1"] = _level_one(root, manifest)
    if level in {"2", "all"}:
        output["level_2"] = _level_two(root, manifest)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--level", choices=("1", "2", "all"), default="all")
    args = parser.parse_args()
    try:
        result = audit(args.root.resolve(), args.level)
    except (ExperimentConfigurationError, OSError, ValueError, KeyError) as error:
        print(f"esg_rr_001_audit: {error}", file=sys.stderr)
        return 1
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
