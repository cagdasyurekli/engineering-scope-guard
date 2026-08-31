from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pilot_execution_readiness.py"
SPEC = importlib.util.spec_from_file_location("pilot_execution_readiness", SCRIPT)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class PilotExecutionReadinessTests(unittest.TestCase):
    def test_repository_decision_passes_complete_audit(self) -> None:
        result = readiness.audit(
            ROOT / "experiment" / "pilot_execution_readiness.json", ROOT
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["decision"], "REDESIGN REQUIRED")
        self.assertFalse(result["pilot_authorized"])
        self.assertEqual(result["pilot_policy_comparison_runs"], 0)

    def test_audit_rejects_silent_pilot_authorization(self) -> None:
        source = json.loads(
            (ROOT / "experiment" / "pilot_execution_readiness.json").read_text(
                encoding="utf-8"
            )
        )
        source["pilot_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.json"
            path.write_text(json.dumps(source), encoding="utf-8")

            with self.assertRaisesRegex(
                readiness.ReadinessDecisionError, "decision_boundary"
            ):
                readiness.audit(path, ROOT)

    def test_audit_rejects_removed_harness_blocker(self) -> None:
        source = json.loads(
            (ROOT / "experiment" / "pilot_execution_readiness.json").read_text(
                encoding="utf-8"
            )
        )
        source["blockers"] = [
            blocker
            for blocker in source["blockers"]
            if blocker["id"] != "batch_harness_enforcement"
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.json"
            path.write_text(json.dumps(source), encoding="utf-8")

            with self.assertRaisesRegex(
                readiness.ReadinessDecisionError, "blockers_are_exact"
            ):
                readiness.audit(path, ROOT)


if __name__ == "__main__":
    unittest.main()
