from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "external_input_readiness.py"
SPEC = importlib.util.spec_from_file_location("external_input_readiness", SCRIPT)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


class ExternalInputReadinessTests(unittest.TestCase):
    def test_repository_readiness_record_is_consistent(self) -> None:
        result = readiness.audit(ROOT / "experiment/external_input_readiness.json", ROOT)

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["eligible_distinct_tasks"], 634)
        self.assertEqual(result["pilot_tasks"], 12)
        self.assertEqual(result["confirmatory_reserve_tasks"], 538)
        self.assertIs(result["pilot_authorized"], False)
        self.assertEqual(result["bounded_conclusion"], "REDESIGN REQUIRED")


if __name__ == "__main__":
    unittest.main()
