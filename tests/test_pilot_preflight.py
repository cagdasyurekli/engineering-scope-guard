from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from scripts.pilot_preflight import audit


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "experiment/pilot_preflight.json"


class PilotPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def _audit_mutation(self, receipt: dict[str, object]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            audit(path, ROOT)

    def test_repository_blocked_receipt_audits(self):
        result = audit(RECEIPT, ROOT)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["conclusion"], "blocked")
        self.assertEqual(result["pilot_cells_executed"], 0)

    def test_nonzero_execution_is_rejected(self):
        changed = copy.deepcopy(self.receipt)
        changed["pilot_cells_executed"] = 1
        with self.assertRaisesRegex(ExperimentConfigurationError, "zero_execution"):
            self._audit_mutation(changed)

    def test_nonfrozen_stop_class_is_rejected(self):
        changed = copy.deepcopy(self.receipt)
        changed["stop"]["class"] = "provider_api_infrastructure_failure"
        with self.assertRaisesRegex(ExperimentConfigurationError, "blocked_before_cell_one"):
            self._audit_mutation(changed)


if __name__ == "__main__":
    unittest.main()
