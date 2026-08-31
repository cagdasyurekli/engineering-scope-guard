from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluator_runtime_readiness.py"
SPEC = importlib.util.spec_from_file_location("evaluator_runtime_readiness", SCRIPT)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class EvaluatorRuntimeReadinessTests(unittest.TestCase):
    def test_repository_runtime_readiness_record_is_consistent(self) -> None:
        result = readiness.audit(
            ROOT / "experiment/evaluator_runtime_readiness.json", ROOT
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["gold_runs"], 3)
        self.assertEqual(result["subject_turns"], 2)
        self.assertEqual(result["measured_gold_valid_tasks"], 1)
        self.assertIs(result["pilot_authorized"], False)
        self.assertEqual(result["bounded_conclusion"], "REDESIGN REQUIRED")


if __name__ == "__main__":
    unittest.main()
