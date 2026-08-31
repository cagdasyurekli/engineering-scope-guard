from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_scope_guard.evidence_conditioned_execution import (
    TREATMENT_PATH,
    build_contract,
    build_launch_request,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from scripts.evidence_conditioned_runner import LiveEvidenceBackend, execute

ROOT = Path(__file__).resolve().parents[1]


class EvidenceConditionedAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def test_late_stage_process_boundary_uses_exact_stdin_and_resume_session(self) -> None:
        backend = object.__new__(LiveEvidenceBackend)
        backend.codex_binary = "codex"
        backend.contract = {"contract_version": "pilot-v3.0"}
        backend.evaluator_root = Path("/evaluator")
        backend._environment = lambda _home: {"CODEX_HOME": "/isolated"}  # type: ignore[method-assign]
        backend._trace_details = lambda _path: ("session-1", False)  # type: ignore[method-assign]
        cell = next(
            item
            for item in self.contract["schedule"]["cells"]
            if item["arm"] == "treatment"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_launch_request(self.contract, cell, root, 1)
            prepared = {
                "raw": root,
                "repository": root,
                "codex_home": root / "codex-home",
            }
            treatment = (ROOT / TREATMENT_PATH).read_bytes()
            with (
                patch(
                    "scripts.evidence_conditioned_runner._run",
                    return_value=(0, False, b'{}\n', b""),
                ) as runner,
                patch(
                    "scripts.evidence_conditioned_runner._usage_from_trace",
                    return_value={
                        "status": "available",
                        "components": {
                            "input_tokens": 1,
                            "cached_input_tokens": 0,
                            "output_tokens": 1,
                            "reasoning_output_tokens": 0,
                        },
                    },
                ),
            ):
                result = backend.run_treatment(
                    request, prepared, treatment, "session-1"
                )
        command = runner.call_args.args[0]
        self.assertEqual(command[:5], ["codex", "exec", "resume", "session-1", "-"])
        self.assertEqual(runner.call_args.kwargs["stdin"], treatment)
        self.assertEqual(result.session_id, "session-1")

    def test_wrong_execution_confirmation_fails_before_state_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            with self.assertRaisesRegex(ExperimentConfigurationError, "confirmation"):
                execute(
                    ROOT,
                    self.contract,
                    None,  # type: ignore[arg-type]
                    state,
                    "wrong",
                    {},
                )
            self.assertFalse(state.exists())

    def test_matching_confirmation_still_requires_stabilized_preflight(self) -> None:
        from engineering_scope_guard.evidence_conditioned_execution import (
            execution_confirmation,
        )

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            with self.assertRaisesRegex(ExperimentConfigurationError, "preflight"):
                execute(
                    ROOT,
                    self.contract,
                    None,  # type: ignore[arg-type]
                    state,
                    execution_confirmation(self.contract),
                    {"status": "pass"},
                )
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
