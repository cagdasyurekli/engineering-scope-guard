import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engineering_scope_guard import azure_evaluator
from engineering_scope_guard.azure_evaluator import (
    DATASET_REVISION,
    EVALUATOR_REVISION,
    POOL_IMAGE,
    POOL_VM_SIZE,
    failure_receipt,
    occupancy,
    patch_environment,
    pool_spec,
    remote_task_file,
    task_payload,
)


class AzureEvaluatorTests(unittest.TestCase):
    def test_pool_is_single_slot_and_fully_pinned(self) -> None:
        value = pool_spec()
        self.assertEqual(value["vmSize"], POOL_VM_SIZE)
        self.assertEqual(value["targetDedicatedNodes"], 1)
        self.assertEqual(value["taskSlotsPerNode"], 1)
        self.assertNotEqual(POOL_IMAGE["version"], "latest")
        start = value["startTask"]["commandLine"]
        self.assertIn(EVALUATOR_REVISION, start)
        self.assertIn(DATASET_REVISION, start)

    def test_patch_transport_is_deterministic_and_bounded(self) -> None:
        patch = b"diff --git a/a b/a\n+line\n"
        first = patch_environment(patch, chunk_bytes=5)
        second = patch_environment(patch, chunk_bytes=5)
        self.assertEqual(first, second)
        self.assertEqual(first["ESG_PATCH_CHUNK_COUNT"], second["ESG_PATCH_CHUNK_COUNT"])

    def test_task_has_zero_azure_retries_and_no_container_override(self) -> None:
        task = {
            "task_id": "owner__repo-1",
            "repository": "owner/repo",
            "language": "go",
            "docker_image": "mutable:image",
            "resolved_image": "mutable:image@sha256:" + "a" * 64,
        }
        payload = task_payload(
            job_id="esgrr002-cell-1",
            task_id="eval-1",
            task=task,
            patch=b"patch",
            worker=b"print('worker')\n",
            evaluator_timeout_seconds=1800,
        )
        self.assertEqual(payload["constraints"]["maxTaskRetryCount"], 0)
        self.assertNotIn("containerSettings", payload)
        self.assertIn("sudo -n -E", payload["commandLine"])
        self.assertEqual(
            payload["userIdentity"],
            {"autoUser": {"scope": "task", "elevationLevel": "admin"}},
        )
        names = {item["name"] for item in payload["environmentSettings"]}
        self.assertIn("ESG_TASK_RESOLVED_IMAGE", names)

    def test_task_working_directory_artifact_paths_are_explicit(self) -> None:
        self.assertEqual(remote_task_file("stdout.txt"), "stdout.txt")
        self.assertEqual(
            remote_task_file("azure-evaluator/worker-receipt.json"),
            "wd/azure-evaluator/worker-receipt.json",
        )
        with self.assertRaisesRegex(Exception, "unsafe"):
            remote_task_file("../outside")

    def test_occupancy_allows_only_own_idle_program_resources(self) -> None:
        responses = [
            [{"id": azure_evaluator.POOL_ID, "currentDedicatedNodes": 1}],
            [{"id": "esgrr002-readiness"}],
        ]
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory) / ".local" / "azure"
            with patch.object(azure_evaluator, "_az", side_effect=responses), patch.object(
                azure_evaluator,
                "_task_status",
                return_value=[{"id": "eval-1", "state": "completed"}],
            ):
                receipt = occupancy(state_root)
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["conflicting_pools"], [])
        self.assertEqual(receipt["own_active_tasks"], [])

    def test_occupancy_fails_closed_for_another_workstream(self) -> None:
        responses = [
            [
                {"id": azure_evaluator.POOL_ID, "currentDedicatedNodes": 1},
                {"id": "future-work", "currentDedicatedNodes": 1},
            ],
            [{"id": "esgrr002-readiness"}, {"id": "future-job"}],
        ]
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory) / ".local" / "azure"
            with patch.object(azure_evaluator, "_az", side_effect=responses), patch.object(
                azure_evaluator, "_task_status", return_value=[]
            ):
                receipt = occupancy(state_root)
        self.assertEqual(receipt["status"], "fail")
        self.assertEqual(receipt["conflicting_active_nodes"], 1)

    def test_orchestrator_failure_is_persisted_as_terminal_infrastructure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory) / ".local" / "azure"
            receipt = failure_receipt(
                state_root=state_root,
                job_id="esgrr002-cell-1",
                task_id="eval-1",
                error=RuntimeError("fixture failure"),
            )
            persisted = state_root / "receipts" / "esgrr002-cell-1-eval-1.json"
            self.assertTrue(persisted.is_file())
        self.assertEqual(receipt["status"], "evaluator_infrastructure_failure")
        self.assertFalse(receipt["timed_out"])


if __name__ == "__main__":
    unittest.main()
