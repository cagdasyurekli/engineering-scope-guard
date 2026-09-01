import copy
import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.runtime_lock import (
    RuntimeIdentityError,
    build_runtime_receipt,
    sentinel,
    validate_runtime_receipt,
    write_private_receipt,
)
from scripts.runtime_lock import COMMAND_TEMPLATE


class RuntimeLockTests(unittest.TestCase):
    def test_public_command_does_not_combine_automatic_approval_and_sandbox(self) -> None:
        self.assertIn("--approve-for-me", COMMAND_TEMPLATE)
        self.assertNotIn("--sandbox", COMMAND_TEMPLATE)

    def _fixture(self, root: Path):
        binary = root / "codex"
        binary.write_bytes(b"fixed-runtime")
        binary.chmod(0o555)
        catalog = root / "models.json"
        catalog.write_text(json.dumps({
            "client_version": "0.151.0", "fetched_at": "2026-08-31T00:00:00Z",
            "models": [{
                "slug": "gpt-5.6-sol", "default_reasoning_level": "low",
                "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}],
                "context_window": 272000, "effective_context_window_percent": 95,
            }],
        }))
        command = ["exec", 'model_reasoning_effort="<EFFORT>"']
        tools = {"network": False, "apps": False}
        environment = lambda: {"system": "Darwin", "machine": "arm64", "release": "fixture"}
        receipt = build_runtime_receipt(
            codex_binary=binary, model_catalog=catalog, model="gpt-5.6-sol",
            command_template=command, tool_surface=tools, sandbox="workspace-write",
            version_runner=lambda _: "codex-cli 0.151.0", environment_observer=environment,
            created_at="2026-08-31T00:00:00Z",
        )
        return binary, catalog, receipt, environment

    def test_receipt_binds_binary_catalog_config_tools_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, receipt, _ = self._fixture(Path(directory))
        validate_runtime_receipt(receipt)
        self.assertEqual(receipt["supported_reasoning_efforts"], ["low", "medium"])
        self.assertEqual(receipt["codex_binary_mode"], "0o555")

    def test_sentinel_passes_for_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, receipt, environment = self._fixture(Path(directory))
            result = sentinel(
                receipt, version_runner=lambda _: "codex-cli 0.151.0",
                environment_observer=environment,
            )
        self.assertEqual(result["status"], "pass")

    def test_binary_drift_fails_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary, _, receipt, environment = self._fixture(Path(directory))
            binary.chmod(0o755)
            binary.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeIdentityError, "binary"):
                sentinel(receipt, version_runner=lambda _: "codex-cli 0.151.0", environment_observer=environment)

    def test_companion_binary_drift_fails_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, catalog, _, environment = self._fixture(root)
            companion = root / "codex-code-mode-host"
            companion.write_bytes(b"fixed-host")
            companion.chmod(0o555)
            receipt = build_runtime_receipt(
                codex_binary=binary,
                model_catalog=catalog,
                model="gpt-5.6-sol",
                command_template=["exec", 'model_reasoning_effort="<EFFORT>"'],
                tool_surface={"network": False, "apps": False},
                sandbox="workspace-write",
                version_runner=lambda _: "codex-cli 0.151.0",
                environment_observer=environment,
                created_at="2026-08-31T00:00:00Z",
            )
            companion.chmod(0o755)
            companion.write_bytes(b"changed-host")
            with self.assertRaisesRegex(RuntimeIdentityError, "companion"):
                sentinel(
                    receipt,
                    version_runner=lambda _: "codex-cli 0.151.0",
                    environment_observer=environment,
                )

    def test_catalog_drift_fails_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, catalog, receipt, environment = self._fixture(Path(directory))
            catalog.write_text(catalog.read_text() + "\n")
            with self.assertRaisesRegex(RuntimeIdentityError, "catalog"):
                sentinel(receipt, version_runner=lambda _: "codex-cli 0.151.0", environment_observer=environment)

    def test_receipt_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, receipt, _ = self._fixture(Path(directory))
        changed = copy.deepcopy(receipt)
        changed["sandbox"] = "read-only"
        with self.assertRaisesRegex(RuntimeIdentityError, "hash drifted"):
            validate_runtime_receipt(changed)

    def test_low_and_medium_are_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, catalog, _, environment = self._fixture(root)
            value = json.loads(catalog.read_text())
            value["models"][0]["supported_reasoning_levels"] = [{"effort": "low"}]
            catalog.write_text(json.dumps(value))
            with self.assertRaisesRegex(RuntimeIdentityError, "low and medium"):
                build_runtime_receipt(
                    codex_binary=binary, model_catalog=catalog, model="gpt-5.6-sol",
                    command_template=["<EFFORT>"], tool_surface={}, sandbox="workspace-write",
                    version_runner=lambda _: "codex-cli 0.151.0", environment_observer=environment,
                )

    def test_private_writer_requires_local_and_restricts_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, receipt, _ = self._fixture(root)
            with self.assertRaisesRegex(RuntimeIdentityError, "below .local"):
                write_private_receipt(root / "receipt.json", receipt)
            path = root / ".local" / "runtime" / "receipt.json"
            write_private_receipt(path, receipt)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
