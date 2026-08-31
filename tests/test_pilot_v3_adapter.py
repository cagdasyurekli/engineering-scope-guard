from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_scope_guard.pilot_v3 import build_launch_request
from scripts.pilot_runner import LiveBackend

ROOT = Path(__file__).resolve().parents[1]


class PilotV3AdapterBoundaryTest(unittest.TestCase):
    def test_canonical_timeout_reaches_evaluator_process_boundary(self) -> None:
        contract = json.loads(
            (ROOT / "experiment/pilot_v3_execution_contract.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evaluator_root = root / "evaluator-source"
            dataset_root = root / "dataset"
            prepared_output = root / "attempt-evaluator"
            codex_home = root / "codex-home"
            for path in (evaluator_root, dataset_root, prepared_output, codex_home):
                path.mkdir()
            prediction_path = root / "prediction.json"
            prediction_path.write_text("{}\n", encoding="utf-8")
            request = build_launch_request(
                contract, contract["schedule"]["cells"][0], root / "state", 2
            )
            observed: dict[str, object] = {}

            def fake_run(command, *, cwd, env, timeout, stdin=None):
                observed.update(command=command, cwd=cwd, timeout=timeout, stdin=stdin)
                return 0, False, b"", b""

            backend = LiveBackend(
                ROOT,
                contract,
                {},
                evaluator_root,
                dataset_root,
                Path("/fixture/evaluator-python"),
                "codex",
                root / "credential-source",
            )
            prepared = {
                "evaluator": prepared_output,
                "task": {"language": "go"},
                "codex_home": codex_home,
            }
            with patch("scripts.pilot_runner._run", side_effect=fake_run) as run:
                result = backend.evaluate(
                    request,
                    prepared,
                    {"path": prediction_path, "patch_sha256": "a" * 64},
                    0,
                )

            self.assertEqual(run.call_count, 1)
            self.assertEqual(observed["timeout"], 1800)
            self.assertEqual(observed["cwd"], evaluator_root)
            self.assertIn("--instance_ids", observed["command"])
            self.assertTrue(result.malformed)


if __name__ == "__main__":
    unittest.main()
