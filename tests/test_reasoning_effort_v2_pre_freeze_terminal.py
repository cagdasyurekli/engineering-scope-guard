from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.evaluator_stable_qualification import seal_receipt
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.reasoning_effort_v2_pre_freeze_terminal import (
    CLASSIFICATION,
    RECEIPT_NAME,
    read_and_validate_pre_freeze_terminal_receipt,
    terminalize_pre_freeze_runtime_mismatch,
    validate_pre_freeze_terminal_receipt,
)
from scripts import reasoning_effort_v2_runner as durable
from tests.test_reasoning_effort_v2_runner import qualification as qualification_fixture


def _private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    local = next(parent for parent in (path.parent, *path.parents) if parent.name == ".local")
    cursor = local
    cursor.chmod(0o700)
    for part in path.parent.relative_to(local).parts:
        cursor = cursor / part
        cursor.chmod(0o700)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


class ReasoningEffortV2PreFreezeTerminalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.local = self.root / ".local"
        self.local.mkdir(mode=0o700)
        self.execution_root = self.local / "execution-v2"
        durable.initialize_execution_storage(self.execution_root)
        self.qualification_path = self.local / "qualification-v2" / "receipt.json"
        self.codex_binary = self.root / "codex"
        self.codex_binary.write_bytes(b"fixture codex\n")
        self.codex_binary.chmod(0o700)
        self.model_catalog = self.root / "models.json"
        self.model_catalog.write_text("{}\n", encoding="utf-8")
        self.expected_runtime = {
            "codex_version": "codex-cli 0.151.0",
            "codex_executable_sha256": "1" * 64,
            "model_catalog_sha256": "2" * 64,
            "model_catalog_fetched_at": "2026-08-30T00:00:00Z",
            "model": "gpt-5.6-sol",
            "supported_reasoning_efforts": ["low", "medium"],
            "docker_client_server": {"Client": {"Version": "fixture"}},
        }
        self.observed_runtime = {
            **deepcopy(self.expected_runtime),
            "model_catalog_sha256": "3" * 64,
            "model_catalog_fetched_at": "2026-08-31T00:00:00Z",
        }
        self.qualification = qualification_fixture()
        self.qualification["runtime_observation"] = deepcopy(self.expected_runtime)
        seal_receipt(self.qualification)
        _private_json(self.qualification_path, self.qualification)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def terminalize(self, observed: dict | None = None, observer=None) -> dict:
        runtime = deepcopy(observed or self.observed_runtime)
        return terminalize_pre_freeze_runtime_mismatch(
            qualification_receipt_path=self.qualification_path,
            execution_root=self.execution_root,
            codex_binary=self.codex_binary,
            model_catalog=self.model_catalog,
            runtime_observer=observer or (lambda _binary, _catalog: runtime),
        )

    def test_writes_atomic_private_self_hashed_content_free_receipt(self) -> None:
        receipt = self.terminalize()
        path = self.execution_root / RECEIPT_NAME
        authority = json.loads((self.execution_root / "receipt-state.json").read_text())

        self.assertEqual(receipt["classification"], CLASSIFICATION)
        self.assertEqual(receipt["subject_invocation_starts"], 0)
        self.assertEqual(receipt["expected_model_catalog_sha256"], "2" * 64)
        self.assertEqual(receipt["observed_model_catalog_sha256"], "3" * 64)
        self.assertEqual(
            receipt["changed_fields"],
            ["model_catalog_fetched_at", "model_catalog_sha256"],
        )
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.execution_root / "contract.json").exists())
        self.assertEqual((self.execution_root / "ledger.jsonl").read_bytes(), b"")
        self.assertEqual((self.execution_root / "checkpoint.json").read_bytes(), b"")
        validate_pre_freeze_terminal_receipt(receipt, self.qualification)
        validate_pre_freeze_terminal_receipt(receipt, self.qualification, authority)
        self.assertEqual(
            read_and_validate_pre_freeze_terminal_receipt(
                qualification_receipt_path=self.qualification_path,
                execution_root=self.execution_root,
            ),
            receipt,
        )

    def test_write_once_readback_does_not_reobserve_or_overwrite(self) -> None:
        first = self.terminalize()

        def forbidden_observer(_binary: Path, _catalog: Path) -> dict:
            self.fail("write-once readback must not reobserve runtime")

        second = self.terminalize(observer=forbidden_observer)
        self.assertEqual(second, first)

    def test_matching_runtime_refuses_terminal_receipt(self) -> None:
        with self.assertRaisesRegex(ExperimentConfigurationError, "still matches"):
            self.terminalize(self.expected_runtime)
        self.assertFalse((self.execution_root / RECEIPT_NAME).exists())

    def test_requires_catalog_digest_and_fetch_time_to_change(self) -> None:
        cases = (
            {**self.observed_runtime, "model_catalog_sha256": "2" * 64},
            {
                **self.observed_runtime,
                "model_catalog_fetched_at": self.expected_runtime[
                    "model_catalog_fetched_at"
                ],
            },
        )
        for observed in cases:
            with self.subTest(observed=observed), self.assertRaisesRegex(
                ExperimentConfigurationError, "required model-catalog"
            ):
                self.terminalize(observed)
            self.assertFalse((self.execution_root / RECEIPT_NAME).exists())

    def test_rejects_nonterminal_qualification(self) -> None:
        changed = deepcopy(self.qualification)
        changed["status"] = "in_progress"
        changed["selection"] = None
        candidate = changed["candidates"][15]
        candidate["status"] = "pending"
        candidate["classification"] = None
        candidate["next_stage"] = "q1_environment"
        candidate["stages"] = []
        candidate["resolved_image"] = None
        seal_receipt(changed)
        _private_json(self.qualification_path, changed)
        with self.assertRaisesRegex(ExperimentConfigurationError, "stable_pool_ready"):
            self.terminalize()

    def test_refuses_any_existing_execution_authority_or_start_state(self) -> None:
        cases = (
            ("contract.json", b"{}\n"),
            ("private-pool.json", b"{}\n"),
            ("qualification-gate.json", b"{}\n"),
            ("freeze-state.json", b"{}\n"),
            ("canary-ledger.jsonl", b"event\n"),
            ("live-seal.json", b"{}\n"),
            ("ledger.jsonl", b"event\n"),
            ("checkpoint.json", b"{}\n"),
        )
        for name, content in cases:
            with self.subTest(name=name):
                path = self.execution_root / name
                original = path.read_bytes() if path.exists() else None
                path.write_bytes(content)
                path.chmod(0o600)
                try:
                    with self.assertRaises(ExperimentConfigurationError):
                        self.terminalize()
                    self.assertFalse((self.execution_root / RECEIPT_NAME).exists())
                finally:
                    if original is None:
                        path.unlink()
                    else:
                        path.write_bytes(original)
                        path.chmod(0o600)

    def test_refuses_nonempty_receipts_directory(self) -> None:
        unexpected = self.execution_root / "receipts" / "attempt.json"
        unexpected.write_text("{}\n", encoding="utf-8")
        unexpected.chmod(0o600)
        with self.assertRaisesRegex(ExperimentConfigurationError, "not empty"):
            self.terminalize()

    def test_validator_rejects_tampering_and_binding_drift(self) -> None:
        receipt = self.terminalize()
        for mutation in ("classification", "qualification", "storage"):
            with self.subTest(mutation=mutation), self.assertRaises(
                ExperimentConfigurationError
            ):
                changed_receipt = deepcopy(receipt)
                changed_qualification = deepcopy(self.qualification)
                authority = json.loads(
                    (self.execution_root / "receipt-state.json").read_text()
                )
                if mutation == "classification":
                    changed_receipt["classification"] = "other"
                elif mutation == "qualification":
                    changed_qualification["runtime_observation"]["model"] = "other"
                    seal_receipt(changed_qualification)
                else:
                    authority["receipt_sha256"] = "f" * 64
                validate_pre_freeze_terminal_receipt(
                    changed_receipt, changed_qualification, authority
                )


if __name__ == "__main__":
    unittest.main()
