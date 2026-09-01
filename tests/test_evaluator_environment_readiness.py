from __future__ import annotations

import unittest

from engineering_scope_guard.evaluator_environment_readiness import (
    GATE_NAMES,
    build_readiness,
    validate_readiness,
)


class EvaluatorEnvironmentReadinessTests(unittest.TestCase):
    def gates(self, status: str = "pass") -> dict:
        return {
            name: {"status": status, "evidence_sha256": "a" * 64}
            for name in GATE_NAMES
        }

    def test_all_gates_are_required_for_freeze(self) -> None:
        receipt = build_readiness(self.gates())
        validate_readiness(receipt)
        self.assertTrue(receipt["subject_freeze_authorized"])

    def test_one_failed_gate_blocks_freeze(self) -> None:
        gates = self.gates()
        gates["sufficient_subject_quota"]["status"] = "fail"
        receipt = build_readiness(gates)
        self.assertFalse(receipt["subject_freeze_authorized"])
        self.assertEqual(receipt["failed_gates"], ["sufficient_subject_quota"])

    def test_gate_set_drift_is_rejected(self) -> None:
        gates = self.gates()
        gates.pop("public_canonical_healthy")
        with self.assertRaisesRegex(ValueError, "gate set drifted"):
            build_readiness(gates)


if __name__ == "__main__":
    unittest.main()
