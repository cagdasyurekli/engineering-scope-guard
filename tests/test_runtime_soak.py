import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from engineering_scope_guard.runtime_lock import RuntimeIdentityError, digest
from engineering_scope_guard.runtime_soak import run_contentless_launch
from tests import test_runtime_lock as runtime_lock_fixtures


class RuntimeSoakTests(unittest.TestCase):
    def _receipt(self, root: Path):
        return runtime_lock_fixtures.RuntimeLockTests()._fixture(root)[2]

    @staticmethod
    def _runner(item_type: str = "agent_message", returncode: int = 0):
        raw = b"\n".join([
            json.dumps({"type": "thread.started"}).encode(),
            json.dumps({"type": "item.completed", "item": {"type": item_type}}).encode(),
            json.dumps({"type": "turn.completed", "usage": {}}).encode(),
        ]) + b"\n"
        return lambda *_: subprocess.CompletedProcess([], returncode, raw, b"")

    def test_two_efforts_pass_once_each_and_third_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = self._receipt(root)
            state = root / ".local" / "soak" / "state.json"
            with patch("engineering_scope_guard.runtime_soak.sentinel", return_value={"observed_identity_sha256": "a" * 64}):
                run_contentless_launch(receipt, state_path=state, effort="low", runner=self._runner())
                run_contentless_launch(receipt, state_path=state, effort="medium", runner=self._runner())
                with self.assertRaisesRegex(RuntimeIdentityError, "maximum"):
                    run_contentless_launch(receipt, state_path=state, effort="low", runner=self._runner())
            self.assertEqual(len(json.loads(state.read_text())["launches"]), 2)

    def test_tool_item_fails_closed_and_consumes_the_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = self._receipt(root)
            state = root / ".local" / "soak" / "state.json"
            with patch("engineering_scope_guard.runtime_soak.sentinel", return_value={"observed_identity_sha256": "a" * 64}):
                with self.assertRaisesRegex(RuntimeIdentityError, "closed-surface"):
                    run_contentless_launch(receipt, state_path=state, effort="low", runner=self._runner("command_execution"))
            saved = json.loads(state.read_text())
        self.assertEqual(saved["launches"][0]["status"], "failed")

    def test_runner_interruption_is_durable_and_never_relaunches_same_effort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = self._receipt(root)
            state = root / ".local" / "soak" / "state.json"
            with patch("engineering_scope_guard.runtime_soak.sentinel", return_value={"observed_identity_sha256": "a" * 64}):
                with self.assertRaises(KeyboardInterrupt):
                    run_contentless_launch(
                        receipt, state_path=state, effort="low",
                        runner=lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()),
                    )
                with self.assertRaisesRegex(RuntimeIdentityError, "already launched"):
                    run_contentless_launch(receipt, state_path=state, effort="low", runner=self._runner())

    def test_failed_prelaunch_allows_one_command_only_receipt_repair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self._receipt(root)
            repaired = dict(original)
            repaired["created_at"] = "2026-08-31T00:00:01+00:00"
            repaired["command_template"] = ["--fixed", "<EFFORT>"]
            repaired["config_sha256"] = digest(repaired["command_template"])
            body = dict(repaired)
            body.pop("receipt_sha256")
            repaired["receipt_sha256"] = digest(body)
            state = root / ".local" / "soak" / "state.json"
            with patch("engineering_scope_guard.runtime_soak.sentinel", return_value={"observed_identity_sha256": "a" * 64}):
                with self.assertRaisesRegex(RuntimeIdentityError, "closed-surface"):
                    run_contentless_launch(
                        original, state_path=state, effort="low",
                        runner=self._runner(returncode=2),
                    )
                run_contentless_launch(
                    repaired, state_path=state, effort="medium", runner=self._runner(),
                    repair_from_receipt=original,
                )
            saved = json.loads(state.read_text())
            self.assertEqual(saved["schema_version"], 2)
            self.assertEqual(saved["runtime_receipt_sha256s"], [
                original["receipt_sha256"], repaired["receipt_sha256"],
            ])

    def test_receipt_repair_rejects_runtime_core_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self._receipt(root)
            repaired = dict(original)
            repaired["codex_binary_sha256"] = "b" * 64
            body = dict(repaired)
            body.pop("receipt_sha256")
            repaired["receipt_sha256"] = digest(body)
            state = root / ".local" / "soak" / "state.json"
            with patch("engineering_scope_guard.runtime_soak.sentinel", return_value={"observed_identity_sha256": "a" * 64}):
                with self.assertRaisesRegex(RuntimeIdentityError, "closed-surface"):
                    run_contentless_launch(
                        original, state_path=state, effort="low",
                        runner=self._runner(returncode=2),
                    )
                with self.assertRaisesRegex(RuntimeIdentityError, "more than command"):
                    run_contentless_launch(
                        repaired, state_path=state, effort="medium", runner=self._runner(),
                        repair_from_receipt=original,
                    )


if __name__ == "__main__":
    unittest.main()
