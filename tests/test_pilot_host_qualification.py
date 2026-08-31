from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pilot_host_qualification.py"
SPEC = importlib.util.spec_from_file_location("pilot_host_qualification", SCRIPT)
assert SPEC and SPEC.loader
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


class PilotHostQualificationTests(unittest.TestCase):
    def test_classifies_verified_gold_success(self) -> None:
        outcome = qualification.classify(
            0,
            False,
            {"instance_id": "task", "resolved": True},
            {"success_ids": ["task"], "error": 0, "incomplete": 0},
            "Evaluation ended successfully.",
            [],
        )

        self.assertEqual(outcome, ("PASS", "official-gold-success", False, []))

    def test_exit_zero_with_runtime_error_is_not_a_pass(self) -> None:
        outcome = qualification.classify(
            0,
            False,
            None,
            {"success_ids": [], "error": 1, "incomplete": 0},
            "Error processing instance",
            [],
        )

        self.assertEqual(outcome[0:3], ("FAIL", "evaluator-runtime-failure", False))

    def test_oom_state_takes_precedence(self) -> None:
        outcome = qualification.classify(
            0,
            False,
            None,
            None,
            "",
            [{"OOMKilled": True, "ExitCode": 137}],
        )

        self.assertEqual(outcome[0:3], ("FAIL", "resource-oom", True))

    def test_timeout_is_explicit(self) -> None:
        outcome = qualification.classify(None, True, None, None, "", [])

        self.assertEqual(outcome[0:3], ("FAIL", "timeout", False))

    def test_architecture_warning_is_retained(self) -> None:
        outcome = qualification.classify(
            1,
            False,
            None,
            None,
            "requested image platform does not match host platform",
            [],
        )

        self.assertEqual(outcome[1], "evaluator-process-failure")
        self.assertEqual(len(outcome[3]), 1)

    def test_replacement_eligibility_uses_only_frozen_metadata(self) -> None:
        record = {
            "instance_id": "owner__repo-1",
            "repo": "owner/repo",
            "created_at": "2026-03-01T00:00:00Z",
            "docker_image": "official/image",
            "FAIL_TO_PASS": ["target"],
            "PASS_TO_PASS": ["regression"],
            "rebuild_cmds": ["build"],
            "test_cmds": ["test"],
        }

        self.assertTrue(qualification._eligible_replacement_metadata(record, set()))
        self.assertFalse(
            qualification._eligible_replacement_metadata(record, {"owner__repo-1"})
        )

    def test_replacement_rank_is_deterministic(self) -> None:
        self.assertEqual(
            qualification._rank("owner__repo-1"),
            qualification._rank("owner__repo-1"),
        )

    def test_distribution_is_descriptive_and_rounded(self) -> None:
        self.assertEqual(
            qualification._distribution([4.0004, 1.0, 2.0, 3.0]),
            {"count": 4, "min": 1.0, "median": 2.5, "max": 4.0, "sum": 10.0},
        )

    def test_complete_receipt_cannot_be_refinalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            receipt.write_text(json.dumps({"status": "complete"}), encoding="utf-8")

            with self.assertRaisesRegex(
                qualification.QualificationError, "not in progress"
            ):
                qualification.finalize(receipt)

    def test_repository_qualification_receipt_passes_complete_audit(self) -> None:
        result = qualification.audit(
            ROOT / "experiment" / "pilot_host_qualification.json",
            ROOT,
            require_complete=True,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["recorded_runs"], 48)
        self.assertEqual(result["host_valid_tasks"], 12)
        self.assertFalse(result["pilot_authorized"])


if __name__ == "__main__":
    unittest.main()
