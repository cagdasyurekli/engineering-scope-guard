from __future__ import annotations

import unittest
from copy import deepcopy

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.reasoning_effort_v1 import generate_schedule
from engineering_scope_guard.reasoning_effort_v1_analysis import analyze


def frozen_schedule() -> dict:
    return generate_schedule(
        [
            {
                "task_id": f"task-{number}",
                "repository": f"owner/repo-{number}",
                "task_snapshot_sha256": f"{number:x}" * 64,
            }
            for number in range(1, 9)
        ]
    )


def records(schedule: dict) -> list[dict]:
    result = []
    for frozen in schedule["cells"]:
        task_number = int(frozen["task_id"].removeprefix("task-"))
        if task_number == 1:
            accepted = frozen["arm"] == "medium"
        elif task_number == 2:
            accepted = frozen["arm"] == "low"
        else:
            accepted = task_number % 2 == 0
        input_tokens = 100 + task_number + (20 if frozen["arm"] == "medium" else 0)
        output_tokens = 10 + (5 if frozen["arm"] == "medium" else 0)
        result.append(
            {
                "task_id": frozen["task_id"],
                "repository": frozen["repository"],
                "arm": frozen["arm"],
                "repetition": frozen["repetition"],
                "admissible": True,
                "accepted": accepted,
                "termination": "accepted_completed" if accepted else "evaluator_test_failure",
                "input_tokens": input_tokens,
                "cached_input_tokens": 30,
                "cache_write_input_tokens": 20,
                "output_tokens": output_tokens,
                "reasoning_output_tokens": 4 + (3 if frozen["arm"] == "medium" else 0),
                "subject_wall_seconds": 12.5 + task_number,
                "subject_turns": 1,
                "command_count": 3 + (frozen["arm"] == "medium"),
                "search_count": 2,
                "item_counts": {"agent_messages": 2, "file_changes": task_number % 3},
            }
        )
    return result


class ReasoningEffortV1AnalysisTest(unittest.TestCase):
    def test_complete_analysis_is_paired_deterministic_and_preserves_heterogeneity(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        first = analyze(cells, schedule)
        second = analyze(list(reversed(cells)), schedule)

        self.assertEqual(first, second)
        self.assertEqual(first["analysis_population"]["frozen_cells"], 32)
        self.assertEqual(first["analysis_population"]["complete_task_clusters"], 8)
        self.assertEqual(first["acceptance"]["by_arm"]["low"]["admissible_cells"], 16)
        self.assertEqual(
            first["acceptance"]["paired_complete_tasks"][
                "medium_minus_low_percentage_points"
            ],
            0.0,
        )
        self.assertEqual(
            first["acceptance"]["task_heterogeneity"]["directions"],
            {"medium_higher": 1, "low_higher": 1, "tied": 6},
        )
        self.assertEqual(
            first["acceptance"]["discordant_and_null_repetition_pairs"],
            {
                "both_accepted": 6,
                "neither_accepted": 6,
                "low_only_accepted": 2,
                "medium_only_accepted": 2,
            },
        )
        self.assertTrue(
            first["adversarial_falsification_summary"][
                "opposing_task_acceptance_directions_present"
            ]
        )
        self.assertTrue(
            first["adversarial_falsification_summary"][
                "both_discordance_directions_present"
            ]
        )

    def test_work_components_keep_cache_write_separate_and_derive_fresh_input(self) -> None:
        result = analyze(records(frozen_schedule()), frozen_schedule())
        components = result["work_components"]
        self.assertIn("cached_input_tokens", components)
        self.assertIn("cache_write_input_tokens", components)
        self.assertIn("reasoning_output_tokens", components)
        self.assertIn("item_counts.file_changes", components)
        low_input = components["input_tokens"]["by_arm"]["low"]["total"]
        low_cached = components["cached_input_tokens"]["by_arm"]["low"]["total"]
        low_written = components["cache_write_input_tokens"]["by_arm"]["low"]["total"]
        low_fresh = components["calculated_fresh_input_tokens"]["by_arm"]["low"][
            "total"
        ]
        self.assertEqual(low_fresh, low_input - low_cached - low_written)
        self.assertEqual(
            components["derived_total_tokens"]["by_arm"]["low"]["total"],
            low_input + components["output_tokens"]["by_arm"]["low"]["total"],
        )
        self.assertIsNotNone(
            components["subject_wall_seconds"]["by_arm"]["low"]["per_accepted_outcome"]
        )
        self.assertFalse(any(result["claim_boundaries"].values()))

    def test_terminal_missingness_is_reported_without_imputation(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        missing = cells.pop()
        cells[0]["admissible"] = False
        cells[0]["accepted"] = False
        cells[0]["termination"] = "official_evaluator_incomplete"
        result = analyze(cells, schedule)

        population = result["analysis_population"]
        self.assertEqual(population["observed_cells"], 31)
        self.assertEqual(population["admissible_cells"], 30)
        self.assertEqual(population["inadmissible_cells"], 1)
        self.assertEqual(len(population["missing_frozen_identities"]), 1)
        self.assertEqual(population["missing_frozen_identities"][0]["task_id"], missing["task_id"])
        self.assertEqual(population["complete_task_clusters"], 6)
        self.assertTrue(
            result["adversarial_falsification_summary"][
                "missing_or_inadmissible_cells_present"
            ]
        )

    def test_rejects_non_frozen_duplicate_and_inconsistent_usage(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        unexpected = deepcopy(cells)
        unexpected[0]["task_id"] = "replacement-task"
        with self.assertRaisesRegex(ExperimentConfigurationError, "non-frozen"):
            analyze(unexpected, schedule)

        duplicated = deepcopy(cells)
        duplicated[-1] = deepcopy(duplicated[0])
        with self.assertRaisesRegex(ExperimentConfigurationError, "duplicated"):
            analyze(duplicated, schedule)

        invalid = deepcopy(cells)
        invalid[0]["cache_write_input_tokens"] = invalid[0]["input_tokens"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "exceeds input"):
            analyze(invalid, schedule)
        supplied_derived = deepcopy(cells)
        supplied_derived[0]["total_tokens"] = 111
        with self.assertRaisesRegex(ExperimentConfigurationError, "must not be supplied"):
            analyze(supplied_derived, schedule)
        supplied_derived = deepcopy(cells)
        supplied_derived[0]["derived_total_tokens"] = 111
        with self.assertRaisesRegex(ExperimentConfigurationError, "must not be supplied"):
            analyze(supplied_derived, schedule)

    def test_zero_acceptance_reports_undefined_work_per_accepted_outcome(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        for cell in cells:
            if cell["arm"] == "medium":
                cell["accepted"] = False
                cell["termination"] = "evaluator_test_failure"
        result = analyze(cells, schedule)
        self.assertIsNone(
            result["work_components"]["output_tokens"]["by_arm"]["medium"][
                "per_accepted_outcome"
            ]
        )

    def test_primary_failure_can_remain_admissible_with_wholly_missing_work(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        target = cells[0]
        target["accepted"] = False
        target["termination"] = "trajectory_timeout"
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "subject_wall_seconds",
            "subject_turns",
            "command_count",
            "search_count",
            "item_counts",
        ):
            target.pop(field)
        result = analyze(cells, schedule)

        self.assertEqual(result["analysis_population"]["admissible_cells"], 32)
        self.assertEqual(result["analysis_population"]["complete_task_clusters"], 8)
        self.assertEqual(
            result["work_measurement_missingness"],
            {
                "observed_admissible_cells": 31,
                "missing_admissible_cells": 1,
                "complete_work_task_clusters": 7,
                "by_arm_and_termination": {
                    f"{target['arm']}:trajectory_timeout": 1
                },
                "rule": "no imputation; work summaries use observed work records only",
            },
        )
        input_summary = result["work_components"]["input_tokens"]
        self.assertEqual(input_summary["complete_work_task_clusters"], 7)
        self.assertEqual(
            input_summary["by_arm"][target["arm"]]["missing_work_cells"], 1
        )
        self.assertTrue(
            result["adversarial_falsification_summary"][
                "missing_work_measurements_present"
            ]
        )

    def test_partial_work_or_missing_completed_subject_work_is_rejected(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        cells[0]["termination"] = "agent_subject_failure"
        cells[0]["accepted"] = False
        cells[0].pop("subject_wall_seconds")
        with self.assertRaisesRegex(ExperimentConfigurationError, "all present or all absent"):
            analyze(cells, schedule)

        cells = records(schedule)
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "subject_wall_seconds",
            "subject_turns",
            "command_count",
            "search_count",
            "item_counts",
        ):
            cells[0].pop(field)
        with self.assertRaisesRegex(ExperimentConfigurationError, "completed-subject"):
            analyze(cells, schedule)

    def test_leave_one_task_out_reports_sign_reversal(self) -> None:
        schedule = frozen_schedule()
        cells = records(schedule)
        for cell in cells:
            cell["accepted"] = False
            cell["termination"] = "evaluator_test_failure"
            if cell["task_id"] == "task-1" and cell["arm"] == "medium":
                cell["accepted"] = True
                cell["termination"] = "accepted_completed"
            if (
                cell["task_id"] == "task-2"
                and cell["arm"] == "low"
                and cell["repetition"] == 1
            ):
                cell["accepted"] = True
                cell["termination"] = "accepted_completed"
        result = analyze(cells, schedule)
        leverage = result["leave_one_task_out_task_leverage"]
        self.assertGreater(leverage["full_estimate_percentage_points"], 0)
        self.assertTrue(leverage["any_omission_reverses_sign"])
        self.assertTrue(
            next(
                item["reverses_sign"]
                for item in leverage["omissions"]
                if item["omitted_task_id"] == "task-1"
            )
        )


if __name__ == "__main__":
    unittest.main()
