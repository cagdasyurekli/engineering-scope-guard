from __future__ import annotations

import copy
import unittest

from engineering_scope_guard.evaluator_environment import (
    EvaluatorEnvironmentError,
    build_receipt,
    normalize_system_packages,
    task_environment_identity,
)


H = "a" * 64
H2 = "b" * 64


def fixture(**overrides: object) -> dict:
    values = {
        "source": {
            "repository": "example/evaluator",
            "revision": "revision-a",
            "tree_sha256": H,
            "lock_config_sha256": H2,
        },
        "images": [
            {"name": "task-a", "resolved_ref": f"registry/task-a@sha256:{H}"},
            {"name": "task-b", "resolved_ref": f"registry/task-b@sha256:{H2}"},
        ],
        "python": {
            "version": "3.12.13",
            "executable_sha256": H,
            "packages": [
                {"name": "Py_Arrow", "version": "25.0.1"},
                {"name": "fire", "version": "0.7.1"},
            ],
        },
        "system_packages": [{"name": "Docker.IO", "version": "29.7.2"}],
        "toolchains": {"docker_server": "29.7.2", "git": "2.51.0"},
        "runner": {
            "source_revision": "runner-a",
            "source_sha256": H,
            "config_sha256": H2,
            "campaign_clock_version": "monotonic-v1",
        },
        "tasks": [
            {"task_identity": H, "image_name": "task-a", "inputs": {"language": "c"}},
            {"task_identity": H2, "image_name": "task-b", "inputs": {"language": "go"}},
        ],
        "observation": {"observed_at": "2026-09-01T00:00:00Z", "worker_id": "one"},
    }
    values.update(overrides)
    return build_receipt(**values)


class EvaluatorEnvironmentTests(unittest.TestCase):
    def test_debian_system_package_name_is_supported(self) -> None:
        self.assertEqual(
            normalize_system_packages([{"name": "libstdc++6", "version": "12.2"}]),
            [{"name": "libstdc++6", "version": "12.2"}],
        )

    def test_same_environment_has_same_semantic_identity(self) -> None:
        self.assertEqual(
            fixture()["global_environment_sha256"],
            fixture()["global_environment_sha256"],
        )

    def test_timestamp_path_and_worker_changes_are_non_semantic(self) -> None:
        first = fixture()
        second = fixture(
            observation={
                "observed_at": "later",
                "temporary_path": "/different/path",
                "worker_id": "two",
                "azure_task_id": "random",
                "hostname": "fresh-host",
                "process_id": 123,
            }
        )
        self.assertEqual(first["global_environment_sha256"], second["global_environment_sha256"])
        self.assertEqual(first["task_environment_sha256s"], second["task_environment_sha256s"])
        self.assertNotEqual(first["receipt_sha256"], second["receipt_sha256"])

    def test_evaluator_revision_change_is_drift(self) -> None:
        changed = copy.deepcopy(fixture()["e1_source"])
        changed["revision"] = "revision-b"
        self.assertNotEqual(fixture()["global_environment_sha256"], fixture(source=changed)["global_environment_sha256"])

    def test_python_package_change_is_drift(self) -> None:
        changed = {
            "version": "3.12.13",
            "executable_sha256": H,
            "packages": [{"name": "fire", "version": "0.7.2"}],
        }
        self.assertNotEqual(fixture()["global_environment_sha256"], fixture(python=changed)["global_environment_sha256"])

    def test_system_package_change_is_drift(self) -> None:
        changed = [{"name": "docker.io", "version": "29.8.0"}]
        self.assertNotEqual(fixture()["global_environment_sha256"], fixture(system_packages=changed)["global_environment_sha256"])

    def test_container_digest_change_is_drift(self) -> None:
        changed = copy.deepcopy(fixture()["e2_images"])
        changed[0]["resolved_ref"] = f"registry/task-a@sha256:{'c' * 64}"
        self.assertNotEqual(fixture()["global_environment_sha256"], fixture(images=changed)["global_environment_sha256"])

    def test_runner_revision_change_is_drift(self) -> None:
        changed = copy.deepcopy(fixture()["e4_runner"])
        changed["source_revision"] = "runner-b"
        self.assertNotEqual(fixture()["global_environment_sha256"], fixture(runner=changed)["global_environment_sha256"])

    def test_expected_task_image_difference_is_not_global_drift(self) -> None:
        receipt = fixture()
        self.assertNotEqual(
            receipt["task_environment_sha256s"][H],
            receipt["task_environment_sha256s"][H2],
        )
        self.assertEqual(receipt["global_environment_sha256"], fixture()["global_environment_sha256"])

    def test_low_and_medium_share_one_task_environment(self) -> None:
        receipt = fixture()
        low = task_environment_identity(receipt, H)
        medium = task_environment_identity(receipt, H)
        self.assertEqual(low, medium)

    def test_restart_preserves_frozen_identity(self) -> None:
        first = fixture(observation={"worker_id": "first"})
        resumed = fixture(observation={"worker_id": "resumed", "process_id": 99})
        self.assertEqual(first["task_environment_sha256s"], resumed["task_environment_sha256s"])

    def test_mutable_image_tag_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvaluatorEnvironmentError, "content-addressed"):
            fixture(images=[{"name": "task-a", "resolved_ref": "registry/task-a:latest"}])


if __name__ == "__main__":
    unittest.main()
