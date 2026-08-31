from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TREATMENT = (
    ROOT / "experiment/arms/evidence_conditioned_final_scope_review_v0_1.txt"
)
FIXTURES = (
    ROOT / "experiment/evidence_conditioned_final_scope_review_v0_1_semantic_fixtures.json"
)
EXPECTED_BYTES = (
    b"Once ordinary interpretation, exploration, implementation, debugging, and "
    b"necessary correctness/integration work have produced a plausibly correct "
    b"implementation, and relevant checks have been considered or run where "
    b"feasible, make one final review of task-introduced additions. Keep anything "
    b"supported by requirements, repository evidence, relevant checks, or necessary "
    b"correctness, integration, safety, or security, and anything uncertain, "
    b"entangled, or risky to remove. Without broad new searching, remove or "
    b"simplify only clearly separable unsupported additions when correctness "
    b"confidence is preserved. If a relevant failure or uncertainty remains, "
    b"continue normal debugging and validation instead; finding nothing to remove "
    b"is valid.\n"
)
EXPECTED_SHA256 = "d9ac9e18716428e9cd6d038388b01ec668ade47df8bac014658897752166b8cb"
EXPECTED_OUTCOMES = {
    "adjacent_correctness_edge_case": "keep",
    "justified_shared_root_cause": "keep",
    "speculative_abstraction": "remove_if_clear_and_safe",
    "unrelated_refactor": "remove_if_clear_and_safe",
    "relevant_failing_test": "suspend_review",
    "uncertain_entangled_support": "keep",
    "known_existing_mechanism": "remove_if_clear_and_safe",
    "broad_search_required": "keep_without_search",
    "nothing_unnecessary": "no_op",
}


class EvidenceConditionedFinalScopeReviewTests(unittest.TestCase):
    def test_treatment_bytes_and_digest_are_frozen(self) -> None:
        loaded = TREATMENT.read_bytes()
        self.assertEqual(loaded, EXPECTED_BYTES)
        self.assertEqual(hashlib.sha256(loaded).hexdigest(), EXPECTED_SHA256)

    def test_treatment_is_canonical_utf8_with_one_terminal_lf(self) -> None:
        loaded = TREATMENT.read_bytes()
        self.assertEqual(loaded.decode("utf-8").encode("utf-8"), loaded)
        self.assertNotIn(b"\r", loaded)
        self.assertTrue(loaded.endswith(b"\n"))
        self.assertFalse(loaded.endswith(b"\n\n"))

    def test_adversarial_semantic_fixture_outcomes_are_frozen(self) -> None:
        value = json.loads(FIXTURES.read_text(encoding="utf-8"))
        self.assertEqual(value["schema_version"], 1)
        self.assertEqual(value["treatment_version"], "v0.1")
        self.assertEqual(value["treatment_sha256"], EXPECTED_SHA256)
        self.assertEqual(
            {item["id"]: item["expected_outcome"] for item in value["fixtures"]},
            EXPECTED_OUTCOMES,
        )
        self.assertTrue(
            all(item["scenario"] and item["expected_behavior"] for item in value["fixtures"])
        )


if __name__ == "__main__":
    unittest.main()
