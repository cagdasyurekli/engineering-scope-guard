from __future__ import annotations

import hashlib
import json
import unittest

from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v1 import validate_contract
from scripts.reasoning_effort_v1_freeze import build_artifacts
from scripts.reasoning_effort_v1_runner import EXECUTION_CODE_CLOSURE


def execution_integrity() -> dict:
    return {
        "codex_executable_identity": {
            "resolved_path_sha256": "e" * 64,
            "file_sha256": "f" * 64,
        },
        "execution_code_files_sha256": {
            relative: "a" * 64 for relative in EXECUTION_CODE_CLOSURE
        },
        "evaluator_python_environment_identity": {
            "path_sha256": "1" * 64,
            "resolved_executable_sha256": "2" * 64,
            "version_sha256": "3" * 64,
            "package_set_sha256": "4" * 64,
        },
    }


def reserve() -> dict:
    selected = []
    languages = ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
    seed = "fixture-seed"
    revision = "revision"
    for language_index, language in enumerate(languages):
        language_tasks = []
        for ordinal in range(6):
            index = language_index * 6 + ordinal
            task_id = f"task-{language}-{ordinal}"
            rank = hashlib.sha256(
                "\0".join((seed, revision, language, task_id)).encode()
            ).hexdigest()
            language_tasks.append(
                {
                    "instance_id": task_id,
                    "repo": f"owner/repo-{index}",
                    "language": language,
                    "docker_image": f"image-{index}",
                    "manifest_sha256": hashlib.sha256(f"manifest-{index}".encode()).hexdigest(),
                    "rank_commitment": rank,
                }
            )
        selected.extend(language_tasks)
    selected_ids = sorted(item["instance_id"] for item in selected)
    selected_ids_sha256 = hashlib.sha256(
        json.dumps(selected_ids, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": "engineering-scope-guard.private-current-runtime-reserve-v1",
        "source": {"dataset": "dataset", "revision": "revision"},
        "selection": {
            "seed": seed,
            "selected": selected,
            "selection_uses_task_bodies_or_outcomes": False,
            "manifest_checks_passed": True,
            "eligible_fresh_task_count": 80,
            "eligible_fresh_repository_count": 70,
            "selected_count": 48,
            "selected_repository_count": 48,
            "selected_by_language": {language: 6 for language in languages},
            "selected_ids_sha256": selected_ids_sha256,
            "overflow_count": 20,
            "overflow_repository_count": 18,
            "overflow_ids_sha256": "b" * 64,
        },
    }


def gold() -> dict:
    frozen = reserve()
    first = {
        language: min(
            (item for item in frozen["selection"]["selected"] if item["language"] == language),
            key=lambda item: (item["rank_commitment"], item["instance_id"]),
        )
        for language in ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
    }
    return {
        "schema": "engineering-scope-guard.private-current-evaluator-qualification-v1",
        "status": "complete",
        "source": {
            "dataset_revision": "revision",
            "reserve_selected_ids_sha256": frozen["selection"]["selected_ids_sha256"],
            "evaluator_revision": "evaluator",
            "embedded_repolaunch_revision": "repolaunch",
            "dataset_files": {f"part-{index}.parquet": "c" * 64 for index in range(8)},
        },
        "design": {
            "selection": "first manifest-qualified SHA-256-ranked reserve task per language",
            "task_body_or_model_outcome_used": False,
            "languages": ["c", "cpp", "cs", "go", "java", "js", "rust", "ts"],
            "tasks": 8,
            "gold_repetitions_per_task": 2,
            "workers": 1,
            "timeout_seconds": 3600,
        },
        "tasks": [
            {
                "instance_id": first[language]["instance_id"],
                "repo": first[language]["repo"],
                "language": language,
                "docker_image": first[language]["docker_image"],
                "runs": [
                    {"classification": "official_gold_success"},
                    {"classification": "official_gold_success"},
                ],
            }
            for language in ("c", "cpp", "cs", "go", "java", "js", "rust", "ts")
        ],
    }


def inputs() -> tuple[dict, dict, dict]:
    frozen = reserve()
    receipt = gold()
    selected = {item["instance_id"]: item for item in frozen["selection"]["selected"]}
    resolved = {
        task["instance_id"]: {
            "instance_id": task["instance_id"],
            "repo": task["repo"],
            "language": task["language"],
            "base_commit": hashlib.sha1(task["instance_id"].encode()).hexdigest(),
            "docker_image": task["docker_image"],
            "problem_statement_sha256": hashlib.sha256(task["instance_id"].encode()).hexdigest(),
        }
        for task in receipt["tasks"]
    }
    image_ids = {
        task_id: "sha256:" + item["manifest_sha256"]
        for task_id, item in selected.items()
        if task_id in resolved
    }
    return frozen, receipt, {"resolved": resolved, "image_ids": image_ids}


class ReasoningEffortV1FreezeTest(unittest.TestCase):
    def test_builds_self_consistent_public_safe_artifacts(self) -> None:
        frozen, receipt, fixture = inputs()
        pool, contract, authorization, qualification = build_artifacts(
            reserve=frozen,
            gold=receipt,
            resolved_tasks=fixture["resolved"],
            image_ids=fixture["image_ids"],
            dataset_hashes={f"part-{index}.parquet": "c" * 64 for index in range(8)},
            evaluator_interface={"interface": "fixture"},
            docker_environment={"fixture": True},
            model_catalog_sha256="d" * 64,
            codex_version="0.151.0",
            evaluator_revision="evaluator",
            repolaunch_revision="repolaunch",
            **execution_integrity(),
        )
        validate_contract(contract)
        self.assertEqual(pool["pool_sha256"], contract["schedule"]["pool_sha256"])
        self.assertEqual(len(pool["tasks"]), 8)
        self.assertEqual(
            set(pool["tasks"][0]),
            {
                "task_id",
                "repository",
                "language",
                "base_commit",
                "docker_image",
                "image_id",
                "problem_statement_sha256",
                "manifest_sha256",
            },
        )
        self.assertFalse(pool["selection_uses_task_bodies_or_model_outcomes"])
        self.assertEqual(contract["attempt_accounting"]["qualification_subject_executions"], 1)
        self.assertEqual(qualification["gold"]["official_gold_successes"], 16)
        self.assertTrue(qualification["gold"]["deterministic_selection_verified"])
        self.assertEqual(
            pool["selection_integrity_sha256"],
            digest(authorization["source"]["selection_integrity"]),
        )
        self.assertNotIn(receipt["tasks"][0]["instance_id"], json.dumps(qualification))
        self.assertEqual(authorization["runtime"]["runtime_identity"], digest({
            key: value for key, value in authorization["runtime"].items() if key != "runtime_identity"
        }))

    def test_rejects_incomplete_gold_qualification(self) -> None:
        frozen, failed, fixture = inputs()
        failed["tasks"][0]["runs"][1]["classification"] = "official_gold_test_failure"
        with self.assertRaisesRegex(RuntimeError, "two current-evaluator gold successes"):
            build_artifacts(
                reserve=frozen,
                gold=failed,
                resolved_tasks=fixture["resolved"],
                image_ids=fixture["image_ids"],
                dataset_hashes=failed["source"]["dataset_files"],
                evaluator_interface={},
                docker_environment={},
                model_catalog_sha256="d" * 64,
                codex_version="0.151.0",
                evaluator_revision="evaluator",
                repolaunch_revision="repolaunch",
                **execution_integrity(),
            )

    def test_rejects_tampered_reserve_selected_id_commitment(self) -> None:
        frozen, receipt, fixture = inputs()
        frozen["selection"]["selected_ids_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "selected-ID commitment mismatch"):
            build_artifacts(
                reserve=frozen,
                gold=receipt,
                resolved_tasks=fixture["resolved"],
                image_ids=fixture["image_ids"],
                dataset_hashes=receipt["source"]["dataset_files"],
                evaluator_interface={},
                docker_environment={},
                model_catalog_sha256="d" * 64,
                codex_version="0.151.0",
                evaluator_revision="evaluator",
                repolaunch_revision="repolaunch",
                **execution_integrity(),
            )

    def test_rejects_arbitrary_successful_subset(self) -> None:
        frozen, receipt, fixture = inputs()
        ranked_c = sorted(
            (item for item in frozen["selection"]["selected"] if item["language"] == "c"),
            key=lambda item: (item["rank_commitment"], item["instance_id"]),
        )
        receipt["tasks"][0].update(
            instance_id=ranked_c[1]["instance_id"],
            repo=ranked_c[1]["repo"],
            docker_image=ranked_c[1]["docker_image"],
        )
        with self.assertRaisesRegex(RuntimeError, "deterministic first qualified"):
            build_artifacts(
                reserve=frozen,
                gold=receipt,
                resolved_tasks=fixture["resolved"],
                image_ids=fixture["image_ids"],
                dataset_hashes=receipt["source"]["dataset_files"],
                evaluator_interface={},
                docker_environment={},
                model_catalog_sha256="d" * 64,
                codex_version="0.151.0",
                evaluator_revision="evaluator",
                repolaunch_revision="repolaunch",
                **execution_integrity(),
            )

    def test_accepts_audited_deterministic_replacement(self) -> None:
        frozen, receipt, fixture = inputs()
        ranked_c = sorted(
            (item for item in frozen["selection"]["selected"] if item["language"] == "c"),
            key=lambda item: (item["rank_commitment"], item["instance_id"]),
        )
        receipt["replacement_audit"] = [
            {
                "language": "c",
                "instance_id": ranked_c[0]["instance_id"],
                "repo": ranked_c[0]["repo"],
                "reserve_ordinal": 0,
                "classifications": ["evaluator_runtime_failure"],
            }
        ]
        receipt["tasks"][0].update(
            instance_id=ranked_c[1]["instance_id"],
            repo=ranked_c[1]["repo"],
            docker_image=ranked_c[1]["docker_image"],
        )
        replacement = receipt["tasks"][0]
        fixture["resolved"][replacement["instance_id"]] = {
            "instance_id": replacement["instance_id"],
            "repo": replacement["repo"],
            "language": replacement["language"],
            "base_commit": hashlib.sha1(replacement["instance_id"].encode()).hexdigest(),
            "docker_image": replacement["docker_image"],
            "problem_statement_sha256": hashlib.sha256(
                replacement["instance_id"].encode()
            ).hexdigest(),
        }
        fixture["image_ids"][replacement["instance_id"]] = (
            "sha256:" + ranked_c[1]["manifest_sha256"]
        )
        pool, _, authorization, qualification = build_artifacts(
            reserve=frozen,
            gold=receipt,
            resolved_tasks=fixture["resolved"],
            image_ids=fixture["image_ids"],
            dataset_hashes=receipt["source"]["dataset_files"],
            evaluator_interface={},
            docker_environment={},
            model_catalog_sha256="d" * 64,
            codex_version="0.151.0",
            evaluator_revision="evaluator",
            repolaunch_revision="repolaunch",
            **execution_integrity(),
        )
        self.assertIn(replacement["instance_id"], {item["task_id"] for item in pool["tasks"]})
        self.assertEqual(authorization["source"]["selection_integrity"]["replacement_count"], 1)
        self.assertEqual(qualification["gold"]["replacement_count"], 1)

    def test_rejects_gold_source_commitment_drift(self) -> None:
        frozen, receipt, fixture = inputs()
        receipt["source"]["evaluator_revision"] = "different"
        with self.assertRaisesRegex(RuntimeError, "identity/commitment mismatch"):
            build_artifacts(
                reserve=frozen,
                gold=receipt,
                resolved_tasks=fixture["resolved"],
                image_ids=fixture["image_ids"],
                dataset_hashes={f"part-{index}.parquet": "c" * 64 for index in range(8)},
                evaluator_interface={},
                docker_environment={},
                model_catalog_sha256="d" * 64,
                codex_version="0.151.0",
                evaluator_revision="evaluator",
                repolaunch_revision="repolaunch",
                **execution_integrity(),
            )


if __name__ == "__main__":
    unittest.main()
