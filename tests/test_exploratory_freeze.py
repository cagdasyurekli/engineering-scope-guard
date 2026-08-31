from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.exploratory_freeze import (
    ARTIFACT_PATH,
    EXPECTED_DATASET_SHA256,
    build_freeze,
    validate_freeze,
)
from engineering_scope_guard.pilot_v3 import SELECTION_FIELDS

ROOT = Path(__file__).resolve().parents[1]


def fixture_rows() -> list[dict]:
    rows = []
    for language_index, language in enumerate(("c", "cpp", "cs", "go", "java", "js", "rust", "ts")):
        for candidate in range(2):
            identity = f"fixture-{language}-{candidate}"
            rows.append({
                "instance_id": identity,
                "repo": f"fixture/{language}-{candidate}",
                "created_at": "2026-08-01T00:00:00+00:00",
                "docker_image": f"fixture/{identity}:pinned",
                "FAIL_TO_PASS": ["f2p"],
                "PASS_TO_PASS": ["p2p"],
                "rebuild_cmds": ["rebuild"],
                "test_cmds": ["test"],
                "language": language,
            })
    return rows


class ExploratoryFreezeMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads((ROOT / ARTIFACT_PATH).read_text(encoding="utf-8"))

    def test_repository_artifact_has_exact_partition_schedule_and_zero_execution(self) -> None:
        value = self.value
        self.assertEqual(value["selection"]["selected_task_count"], 8)
        self.assertEqual(value["selection"]["selected_repository_count"], 8)
        self.assertEqual([item["language"] for item in value["selection"]["selected"]], ["c", "cpp", "cs", "go", "java", "js", "rust", "ts"])
        self.assertEqual(value["schedule"]["block_count"], 16)
        self.assertEqual(value["schedule"]["cell_count"], 32)
        self.assertTrue(value["confirmatory_reserve"]["repository_disjoint_from_exploratory"])
        self.assertEqual(value["confirmatory_reserve"]["selected_repository_tasks_remaining"], 0)
        self.assertEqual(value["authority"]["experimental_subject_calls"], 0)
        self.assertEqual(value["authority"]["experimental_evaluator_calls"], 0)
        self.assertEqual(value["authority"]["experimental_observations"], 0)
        self.assertFalse(value["authority"]["execution_ledger_created"])
        self.assertTrue(all(
            item["container_registry_manifest_available"]
            and len(item["container_registry_manifest_sha256"]) == 64
            for item in value["selection"]["selected"]
        ))

    def test_mutations_fail_against_deterministic_regeneration(self) -> None:
        mutations = []
        value = copy.deepcopy(self.value)
        value["selection"]["selection_seed"] = "changed"
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["selection"]["selected"] = value["selection"]["selected"][:-1]
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["confirmatory_reserve"]["commitment_sha256"] = "0" * 64
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["schedule"]["cells"][0]["arm"] = "treatment"
        mutations.append(value)
        value = copy.deepcopy(self.value)
        value["authority"]["execution_authorized"] = True
        mutations.append(value)
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                with mock.patch(
                    "engineering_scope_guard.exploratory_freeze.build_freeze",
                    return_value=self.value,
                ):
                    with self.assertRaisesRegex(
                        ExperimentConfigurationError,
                        "deterministic derivation|container eligibility",
                    ):
                        validate_freeze(mutation, ROOT, [], EXPECTED_DATASET_SHA256)

    def test_selection_input_shape_rejects_task_content(self) -> None:
        rows = fixture_rows()
        self.assertEqual(set(rows[0]), SELECTION_FIELDS)
        rows[0]["problem_statement"] = "forbidden"
        with self.assertRaisesRegex(ExperimentConfigurationError, "non-metadata fields"):
            build_freeze(ROOT, rows, EXPECTED_DATASET_SHA256)


if __name__ == "__main__":
    unittest.main()
