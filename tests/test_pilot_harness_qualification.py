from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pilot_harness_qualification.py"
SPEC = importlib.util.spec_from_file_location("pilot_harness_qualification", SCRIPT)
assert SPEC and SPEC.loader
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


class PilotHarnessQualificationTests(unittest.TestCase):
    def test_repository_receipt_passes(self) -> None:
        result = qualification.audit(
            ROOT / "experiment/pilot_harness_qualification.json", ROOT
        )
        self.assertEqual(result["decision"], "GO TO EXPLORATORY PILOT")
        self.assertEqual(result["pilot_cells_executed"], 0)

    def test_cannot_activate_pilot_in_qualification_receipt(self) -> None:
        value = json.loads(
            (ROOT / "experiment/pilot_harness_qualification.json").read_text()
        )
        value["pilot_goal_active"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ExperimentConfigurationError, "pilot_goal_inactive"):
                qualification.audit(path, ROOT)


if __name__ == "__main__":
    unittest.main()
