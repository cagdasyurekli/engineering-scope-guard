from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "experiment/evidence_conditioned_final_scope_review_v0_1_execution_preflight.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExploratoryExecutionPreflightTests(unittest.TestCase):
    def test_failure_receipt_is_canonical_and_bound_to_frozen_artifacts(self) -> None:
        raw = RECEIPT.read_bytes()
        receipt = json.loads(raw)
        self.assertEqual(
            raw,
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        )
        self.assertEqual(receipt["status"], "fail")
        self.assertEqual(
            receipt["frozen_identities"]["treatment_sha256"],
            sha256(
                ROOT
                / "experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt"
            ),
        )
        self.assertEqual(
            receipt["frozen_identities"]["design_sha256"],
            sha256(
                ROOT
                / "experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json"
            ),
        )
        self.assertEqual(
            receipt["frozen_identities"]["freeze_sha256"],
            sha256(
                ROOT
                / "experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_freeze.json"
            ),
        )

    def test_failure_stopped_before_any_experimental_state(self) -> None:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        accounting = receipt["execution_accounting"]
        self.assertEqual(accounting["attempt_started_events"], 0)
        self.assertFalse(accounting["execution_ledger_created"])
        self.assertEqual(accounting["experimental_subject_calls"], 0)
        self.assertEqual(accounting["experimental_evaluator_calls"], 0)
        self.assertEqual(accounting["experimental_observations"], 0)
        self.assertFalse(
            receipt["checks"]["experiment_specific_execution_contract_present"]
        )
        self.assertFalse(
            receipt["checks"][
                "experiment_specific_runner_and_strict_preflight_present"
            ]
        )
        self.assertFalse(receipt["stop_boundary"]["task_body_loaded_for_subject"])
        self.assertFalse(receipt["stop_boundary"]["confirmatory_reserve_exposed"])


if __name__ == "__main__":
    unittest.main()
