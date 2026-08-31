from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.reasoning_effort_v2 import build_harness_source_closure
from engineering_scope_guard.reasoning_effort_v2_analysis import analyze_reasoning_effort_v2
from scripts import reasoning_effort_v2_export as export_cli
from scripts import reasoning_effort_v2_runner as durable
from tests.test_reasoning_effort_v2_runner import State, frozen, live


class ReasoningEffortV2ExportTests(unittest.TestCase):
    def _terminal_state(self, root: Path):
        contract, private_pool = frozen()
        _gate, seal = live(contract, private_pool)
        state = State(root, contract, private_pool, seal)
        for name, value in (
            ("contract.json", state.contract),
            ("private-pool.json", state.private_pool),
            ("live-seal.json", state.seal),
        ):
            durable._atomic_json(state.root / name, value)
        for cell in state.contract["schedule"]["cells"][:4]:
            state.complete(cell)
        state.stage_1_audit(runtime_pass=False)
        return state

    def test_build_and_verify_exact_ledger_derived_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self._terminal_state(root)
            output = root / "public"
            output.mkdir()
            built = export_cli.export_artifacts(
                execution_root=state.root, output_root=output, write=True
            )
            verified = export_cli.export_artifacts(
                execution_root=state.root, output_root=output, write=False
            )
            self.assertEqual(built["status"], "verified")
            self.assertEqual(verified["command"], "verify")
            self.assertEqual(built["terminal_envelope_sha256"], verified["terminal_envelope_sha256"])
            self.assertEqual(built["analysis_sha256"], verified["analysis_sha256"])
            envelope = json.loads((output / export_cli.ENVELOPE_NAME).read_text())
            analysis = json.loads((output / export_cli.ANALYSIS_NAME).read_text())
            self.assertEqual(analysis, analyze_reasoning_effort_v2(state.contract, envelope))
            self.assertEqual(analysis["terminal_envelope_sha256"], envelope["envelope_sha256"])
            self.assertEqual(analysis["terminal_integrity"]["terminal_status"], "invalid_terminated")

    def test_verify_rejects_tamper_private_mode_and_incomplete_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self._terminal_state(root)
            output = root / "public"
            output.mkdir()
            export_cli.export_artifacts(
                execution_root=state.root, output_root=output, write=True
            )
            analysis_path = output / export_cli.ANALYSIS_NAME
            analysis = json.loads(analysis_path.read_text())
            analysis["scientific_disposition"]["label"] = "tampered"
            analysis_path.write_text(
                json.dumps(analysis, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "differ"):
                export_cli.export_artifacts(
                    execution_root=state.root, output_root=output, write=False
                )

            (state.root / "contract.json").chmod(0o644)
            with self.assertRaisesRegex(ExperimentConfigurationError, "0600"):
                export_cli.export_artifacts(
                    execution_root=state.root, output_root=output, write=False
                )

            contract, private_pool = frozen()
            _gate, seal = live(contract, private_pool)
            incomplete = State(root / "other", contract, private_pool, seal)
            for name, value in (
                ("contract.json", incomplete.contract),
                ("private-pool.json", incomplete.private_pool),
                ("live-seal.json", incomplete.seal),
            ):
                durable._atomic_json(incomplete.root / name, value)
            other_output = root / "other-public"
            other_output.mkdir()
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "complete or invalid-terminal"
            ):
                export_cli.export_artifacts(
                    execution_root=incomplete.root,
                    output_root=other_output,
                    write=True,
                )

    def test_wrapper_is_frozen_in_harness_source_authority(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        closure = build_harness_source_closure(repository_root)
        self.assertIn(
            "scripts/reasoning_effort_v2_export.py",
            {item["path"] for item in closure["files"]},
        )
        entrypoint = next(
            item for item in closure["entrypoints"]
            if item["name"] == "export_analysis"
        )
        self.assertEqual(
            entrypoint["argv"],
            ["python3", "scripts/reasoning_effort_v2_export.py", "build"],
        )
        verify_entrypoint = next(
            item for item in closure["entrypoints"]
            if item["name"] == "verify_analysis_export"
        )
        self.assertEqual(
            verify_entrypoint["argv"],
            ["python3", "scripts/reasoning_effort_v2_export.py", "verify"],
        )


if __name__ == "__main__":
    unittest.main()
