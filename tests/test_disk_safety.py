from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from engineering_scope_guard.disk_safety import (
    DiskSafetyError,
    DiskSafetyPolicy,
    cleanup_plan,
    discover_attempt_repositories,
    disk_safety_snapshot,
    require_disk_safety,
    public_disk_safety_receipt,
    validate_write_target,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from scripts.reasoning_effort_v1_runner import (
    _enforce_disk_safety,
    _state_root_path,
    execute_next,
)
from scripts.experiment_disk_safety import main as disk_safety_main


def statvfs_with_available(value: int) -> SimpleNamespace:
    return SimpleNamespace(f_bavail=value, f_frsize=1)


class DiskSafetyTests(unittest.TestCase):
    def test_only_execution_paths_enforce_the_disk_gate(self) -> None:
        for command in ("preflight", "dry-run", "execute-next"):
            self.assertTrue(_enforce_disk_safety(command))
        for command in ("status", "reconcile", "authorize-stage-2"):
            self.assertFalse(_enforce_disk_safety(command))

    def test_discovers_only_exact_real_repository_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / ".local"
            expected = root / "run-a" / "attempts" / "cell-a" / "attempt-1" / "repository"
            expected.mkdir(parents=True)
            (root / "run-a" / "attempts" / "cell-a" / "attempt-1" / "raw").mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            candidate = root / "run-b" / "attempts" / "cell-b" / "attempt-1"
            candidate.mkdir(parents=True)
            (candidate / "repository").symlink_to(outside, target_is_directory=True)

            self.assertEqual(discover_attempt_repositories(root), (expected,))

    def test_rejects_symlinked_evidence_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            target = parent / "target"
            target.mkdir()
            link = parent / "evidence"
            link.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(DiskSafetyError, "real director"):
                discover_attempt_repositories(link)

    def test_rejects_symlinked_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            target = parent / "target"
            target.mkdir()
            link = parent / "state"
            link.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(DiskSafetyError, "state root"):
                validate_write_target(link)

    def test_rejects_nonexistent_state_root_below_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outside = root / "outside"
            outside.mkdir()
            link = root / "state-link"
            link.symlink_to(outside, target_is_directory=True)
            lexical = _state_root_path(root, Path("state-link/new-run"))

            self.assertEqual(lexical, root / "state-link" / "new-run")
            with self.assertRaisesRegex(DiskSafetyError, "ancestors"):
                validate_write_target(lexical)

    def test_cleanup_plan_is_deterministic_sparse_aware_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / ".local"
            first = root / "b" / "attempts" / "cell" / "attempt-1" / "repository"
            second = root / "a" / "attempts" / "cell" / "attempt-1" / "repository"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            sparse = first / "sparse.bin"
            with sparse.open("wb") as handle:
                handle.truncate(16 * 1024 * 1024)
            (second / "small.txt").write_text("safe", encoding="utf-8")
            before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

            with patch.object(Path, "unlink", side_effect=AssertionError("must not delete")):
                plan = cleanup_plan(root)

            after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertEqual(plan["mode"], "read-only")
            self.assertFalse(plan["automatic_deletion_permitted"])
            self.assertEqual(plan["repository_count"], 2)
            self.assertEqual(
                plan["targets_relative_to_evidence_root"],
                [
                    "a/attempts/cell/attempt-1/repository",
                    "b/attempts/cell/attempt-1/repository",
                ],
            )
            self.assertLess(plan["repository_allocated_bytes"], sparse.stat().st_size)
            self.assertEqual(plan, cleanup_plan(root))

    def test_threshold_equality_passes_and_below_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            evidence = root / ".local"
            evidence.mkdir()
            policy = DiskSafetyPolicy(50, 50, 1_000_000)
            with patch(
                "engineering_scope_guard.disk_safety.os.statvfs",
                return_value=statvfs_with_available(100),
            ):
                self.assertEqual(
                    disk_safety_snapshot(evidence, filesystem_path=root, policy=policy)["status"],
                    "pass",
                )
            with patch(
                "engineering_scope_guard.disk_safety.os.statvfs",
                return_value=statvfs_with_available(99),
            ):
                snapshot = disk_safety_snapshot(evidence, filesystem_path=root, policy=policy)
                self.assertEqual(snapshot["status"], "fail")
                self.assertEqual(snapshot["failures"], ["free_space_below_execution_reserve"])
                with self.assertRaisesRegex(DiskSafetyError, "free_space"):
                    require_disk_safety(evidence, filesystem_path=root, policy=policy)

    def test_retained_repository_budget_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository = root / ".local" / "run" / "attempts" / "cell" / "attempt-1" / "repository"
            repository.mkdir(parents=True)
            (repository / "data.bin").write_bytes(b"x")
            policy = DiskSafetyPolicy(1, 1, 1)
            with patch(
                "engineering_scope_guard.disk_safety.os.statvfs",
                return_value=statvfs_with_available(10_000),
            ):
                snapshot = disk_safety_snapshot(root / ".local", filesystem_path=root, policy=policy)
            self.assertEqual(snapshot["status"], "fail")
            self.assertIn("retained_attempt_repositories_over_budget", snapshot["failures"])

    def test_invalid_policy_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DiskSafetyError, "positive integer"):
                disk_safety_snapshot(
                    Path(directory).resolve() / ".local",
                    filesystem_path=Path(directory).resolve(),
                    policy=DiskSafetyPolicy(0, 1, 1),
                )

    def test_public_receipt_withholds_dynamic_host_metadata(self) -> None:
        receipt = public_disk_safety_receipt(
            {
                "status": "pass",
                "minimum_free_bytes": 1,
                "execution_headroom_bytes": 2,
                "required_free_bytes": 3,
                "maximum_retained_repository_bytes": 4,
                "available_bytes": 999,
                "retained_repository_count": 7,
                "retained_repository_allocated_bytes": 888,
                "retained_repository_target_set_sha256": "private",
                "failures": [],
            }
        )
        self.assertEqual(receipt["status"], "pass")
        self.assertTrue(receipt["dynamic_host_metadata_withheld"])
        self.assertNotIn("available_bytes", receipt)
        self.assertNotIn("retained_repository_count", receipt)
        self.assertNotIn("retained_repository_target_set_sha256", receipt)

    def test_cleanup_cli_withholds_private_inventory_from_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["experiment_disk_safety", "plan-cleanup", "--root", str(root)]),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(disk_safety_main(), 0)
            public = json.loads(output.getvalue())
            private = json.loads((root / ".local" / "disk-cleanup-plan.json").read_text())
            self.assertTrue(public["dynamic_host_metadata_withheld"])
            self.assertNotIn("target_set_sha256", public)
            self.assertNotIn("repository_count", public)
            self.assertIn("target_set_sha256", private)
            self.assertFalse(private["deletion_authorized"])

    def test_runner_rechecks_before_attempt_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state_root = root / ".local" / "reasoning-effort-v1"
            with (
                patch(
                    "scripts.reasoning_effort_v1_runner.require_disk_safety",
                    side_effect=DiskSafetyError("disk-safety gate failed"),
                ) as guard,
                patch("scripts.reasoning_effort_v1_runner.record_attempt_start") as start,
            ):
                with self.assertRaisesRegex(ExperimentConfigurationError, "disk-safety gate"):
                    execute_next(
                        root=root,
                        contract={},
                        pool={},
                        authorization={},
                        evaluator_root=root,
                        dataset_root=root,
                        evaluator_python=root / "python",
                        codex_binary="codex",
                        source_codex_home=root,
                        state_root=state_root,
                    )
            start.assert_not_called()
            guard.assert_called_once_with(state_root.parent, filesystem_path=state_root)
            self.assertFalse((state_root / "ledger.jsonl").exists())
            self.assertFalse((state_root / "attempts").exists())


if __name__ == "__main__":
    unittest.main()
