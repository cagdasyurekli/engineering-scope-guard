from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.exploratory_design import (
    DECISION,
    TASK_COUNT,
    TREATMENT_SHA256,
    canonical_bytes,
    generate_schedule,
    load_design,
    select_metadata_rows,
    validate_design,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = (
    ROOT
    / "experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json"
)


class ExploratoryDesignTests(unittest.TestCase):
    def value(self) -> dict:
        return json.loads(DESIGN.read_text(encoding="utf-8"))

    def test_repository_design_is_canonical_task_free_and_not_executable(self) -> None:
        value = load_design(DESIGN, ROOT)
        self.assertEqual(value["decision"], DECISION)
        self.assertFalse(value["execution_authorized"])
        self.assertFalse(value["task_pool_frozen"])
        self.assertFalse(value["selection"]["task_bodies_or_actual_identities_present"])
        self.assertEqual(value["experimental_unit"]["task_count"], TASK_COUNT)
        self.assertEqual(value["experimental_unit"]["total_cells"], 32)
        self.assertEqual(value["treatment"]["sha256"], TREATMENT_SHA256)

    def test_treatment_bytes_and_exactly_two_arms_are_frozen(self) -> None:
        value = self.value()
        value["treatment"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ExperimentConfigurationError, "treatment identity"):
            validate_design(value, ROOT)

        value = self.value()
        value["arms"].append({"id": "extra", "intervention": "forbidden"})
        with self.assertRaisesRegex(ExperimentConfigurationError, "exact treatment only"):
            validate_design(value, ROOT)

    def test_task_material_and_real_schedule_shapes_are_rejected(self) -> None:
        for key in ("actual_task_id", "task_body", "problem_statement", "cells"):
            with self.subTest(key=key):
                value = self.value()
                value["selection"][key] = "must-not-appear"
                with self.assertRaisesRegex(ExperimentConfigurationError, "task material key"):
                    validate_design(value, ROOT)

    def test_attempt_retry_pause_and_corrective_budgets_cannot_expand(self) -> None:
        mutations = (
            ("attempts", "maximum_total_attempts_per_cell", 3, "attempt maximum"),
            ("attempts", "infrastructure_retry_capacity_batch_total", 5, "infrastructure capacity"),
            ("attempts", "operator_interruption_capacity_batch_total", 3, "operator capacity"),
            ("corrective_round", "maximum", 2, "corrective-round maximum"),
        )
        for section, key, replacement, error in mutations:
            with self.subTest(section=section, key=key):
                value = self.value()
                value[section][key] = replacement
                with self.assertRaisesRegex(ExperimentConfigurationError, error):
                    validate_design(value, ROOT)

        value = self.value()
        value["operator_pause"]["relabel_as_infrastructure_permitted"] = True
        with self.assertRaisesRegex(ExperimentConfigurationError, "can be relabeled"):
            validate_design(value, ROOT)

    def test_quality_accepted_outcome_and_retirement_boundaries_are_required(self) -> None:
        value = self.value()
        value["analysis"]["quality_precedes_work"] = False
        with self.assertRaisesRegex(ExperimentConfigurationError, "quality no longer"):
            validate_design(value, ROOT)

        value = self.value()
        value["analysis"]["accepted_outcome_work"]["primary_comparison"] = (
            "compare different accepted populations"
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "pairing changed"):
            validate_design(value, ROOT)

        value = self.value()
        value["retirement_gates"] = value["retirement_gates"][:-1]
        with self.assertRaisesRegex(ExperimentConfigurationError, "retirement gates changed"):
            validate_design(value, ROOT)

    def test_selection_and_schedule_cannot_be_manual_or_outcome_adaptive(self) -> None:
        value = self.value()
        value["selection"]["prohibited_inputs"].remove("outcome history")
        with self.assertRaisesRegex(ExperimentConfigurationError, "contamination controls"):
            validate_design(value, ROOT)

        value = self.value()
        value["schedule_algorithm"]["manual_rearrangement_permitted"] = True
        with self.assertRaisesRegex(ExperimentConfigurationError, "manual scheduling"):
            validate_design(value, ROOT)

        value = self.value()
        value["schedule_algorithm"]["uses_interim_outcomes"] = True
        with self.assertRaisesRegex(ExperimentConfigurationError, "adaptive scheduling"):
            validate_design(value, ROOT)

    def test_synthetic_schedule_is_deterministic_and_counterbalanced(self) -> None:
        tasks = [hashlib.sha256(f"synthetic-{number}".encode()).hexdigest() for number in range(8)]
        pool = hashlib.sha256(b"synthetic-pool").hexdigest()
        first = generate_schedule(tasks, pool)
        second = generate_schedule(list(reversed(tasks)), pool)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        for task in tasks:
            blocks = sorted(
                (block for block in first if block["opaque_task_commitment"] == task),
                key=lambda block: block["repetition"],
            )
            self.assertEqual(blocks[0]["arms"], list(reversed(blocks[1]["arms"])))
            self.assertEqual(set(blocks[0]["arms"]), {"baseline", "treatment"})
        self.assertEqual(
            sum(block["arms"][0] == "baseline" for block in first),
            sum(block["arms"][0] == "treatment" for block in first),
        )

    def test_synthetic_metadata_selection_is_ranked_and_repository_distinct(self) -> None:
        languages = ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
        rows = [
            {
                "opaque_instance_identity": f"synthetic-{language}-{candidate}",
                "repository_identity": f"synthetic-repository-{language}-{candidate}",
                "language": language,
            }
            for language in languages
            for candidate in range(3)
        ]
        first = select_metadata_rows(rows)
        second = select_metadata_rows(list(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual([row["language"] for row in first], list(languages))
        self.assertEqual(len({row["repository_identity"] for row in first}), 8)

    def test_metadata_selection_fails_closed_on_cross_language_repository_collision(self) -> None:
        rows = [
            {
                "opaque_instance_identity": f"synthetic-{language}",
                "repository_identity": "one-repository",
                "language": language,
            }
            for language in ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
        ]
        with self.assertRaisesRegex(ExperimentConfigurationError, "cannot cover"):
            select_metadata_rows(rows)

    def test_schedule_rejects_noncommitments_duplicates_and_wrong_count(self) -> None:
        tasks = [hashlib.sha256(f"synthetic-{number}".encode()).hexdigest() for number in range(8)]
        pool = hashlib.sha256(b"synthetic-pool").hexdigest()
        with self.assertRaises(ExperimentConfigurationError):
            generate_schedule(tasks[:-1], pool)
        with self.assertRaises(ExperimentConfigurationError):
            generate_schedule(tasks[:-1] + [tasks[0]], pool)
        with self.assertRaises(ExperimentConfigurationError):
            generate_schedule(tasks[:-1] + ["not-a-digest"], pool)

    def test_noncanonical_design_bytes_are_rejected(self) -> None:
        value = self.value()
        self.assertEqual(DESIGN.read_bytes(), canonical_bytes(value))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "design.json"
            path.write_text(json.dumps(copy.deepcopy(value)) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "not canonical"):
                load_design(path, ROOT)


if __name__ == "__main__":
    unittest.main()
