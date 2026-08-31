from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from engineering_scope_guard.doctor import inspect_codex


def completed(arguments: tuple[str, ...], stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(arguments, returncode, stdout=stdout, stderr="")


class DoctorTests(unittest.TestCase):
    @patch("engineering_scope_guard.doctor._run_command")
    def test_healthy_static_capabilities(self, run_command):
        run_command.side_effect = [
            completed(("codex", "--version"), "codex-cli 0.150.1\n"),
            completed(("codex", "exec", "--help"), "  --json  Print events\n"),
            completed(("codex", "features", "list"), "hooks stable true\n"),
        ]

        result = inspect_codex()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["codex"]["version"], "0.150.1")
        self.assertTrue(result["codex"]["exec_json"])
        self.assertEqual(result["codex"]["hooks"], {"maturity": "stable", "enabled": True})
        self.assertEqual(
            [call.args[0] for call in run_command.call_args_list],
            [
                ("codex", "--version"),
                ("codex", "exec", "--help"),
                ("codex", "features", "list"),
            ],
        )

    @patch("engineering_scope_guard.doctor._run_command")
    def test_feature_inspection_failure_is_degraded(self, run_command):
        run_command.side_effect = [
            completed(("codex", "--version"), "codex-cli 0.150.1\n"),
            completed(("codex", "exec", "--help"), "  --json  Print events\n"),
            completed(("codex", "features", "list"), "", returncode=1),
        ]
        self.assertEqual(inspect_codex()["status"], "degraded")

    @patch("engineering_scope_guard.doctor._run_command", side_effect=FileNotFoundError)
    def test_missing_codex_is_unsupported(self, _run_command):
        self.assertEqual(inspect_codex()["status"], "unsupported")

    @patch("engineering_scope_guard.doctor._run_command")
    def test_missing_json_interface_is_unsupported(self, run_command):
        run_command.side_effect = [
            completed(("codex", "--version"), "codex-cli 0.150.1\n"),
            completed(("codex", "exec", "--help"), "no machine output\n"),
        ]
        self.assertEqual(inspect_codex()["status"], "unsupported")

    @patch("engineering_scope_guard.doctor._run_command")
    def test_unrecognized_version_is_degraded(self, run_command):
        run_command.side_effect = [
            completed(("codex", "--version"), "unexpected version output\n"),
            completed(("codex", "exec", "--help"), "  --json  Print events\n"),
            completed(("codex", "features", "list"), "hooks stable true\n"),
        ]
        result = inspect_codex()
        self.assertEqual(result["status"], "degraded")
        self.assertIsNone(result["codex"]["version"])


if __name__ == "__main__":
    unittest.main()
