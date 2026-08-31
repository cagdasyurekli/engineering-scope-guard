from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_v2 import (
    EXPOSED_V1_TASK,
    build_contract,
    build_dry_run,
    build_qualification,
    generate_schedule,
    validate_contract,
)
from engineering_scope_guard.pilot_runner import execution_confirmation

ROOT = Path(__file__).resolve().parents[1]


class PilotV2FreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def test_repository_contract_is_exactly_regenerable(self) -> None:
        stored = json.loads((ROOT / "experiment/pilot_v2_execution_contract.json").read_text())
        validate_contract(stored, ROOT)
        self.assertEqual(stored, self.contract)

    def test_pool_excludes_only_exposed_task_and_preserves_reserve(self) -> None:
        pool = self.contract["final_pool"]
        self.assertEqual(len(pool["slots"]), 11)
        self.assertNotIn(EXPOSED_V1_TASK, {item["actual_task_id"] for item in pool["slots"]})
        self.assertEqual(pool["confirmatory_reserve"]["new_tasks_withdrawn_for_pilot_v2"], 0)
        self.assertFalse(pool["confirmatory_reserve"]["ids_or_bodies_emitted"])

    def test_schedule_is_complete_paired_and_pool_bound(self) -> None:
        schedule = self.contract["schedule"]
        self.assertEqual(len(schedule["cells"]), 44)
        self.assertEqual(schedule, generate_schedule(self.contract["final_pool"]))
        for slot in self.contract["final_pool"]["slots"]:
            cells = [cell for cell in schedule["cells"] if cell["requested_task_slot"] == slot["slot"]]
            self.assertEqual(
                {(cell["arm"], cell["repetition"]) for cell in cells},
                {("baseline", 1), ("short", 1), ("baseline", 2), ("short", 2)},
            )
        changed = copy.deepcopy(self.contract["final_pool"])
        changed["slots"][0]["actual_task_id"] = "changed"
        changed["final_pool_sha256"] = "0" * 64
        self.assertNotEqual(schedule["schedule_sha256"], generate_schedule(changed)["schedule_sha256"])

    def test_contract_drift_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["subject"]["reasoning_effort"] = "high"
        with self.assertRaisesRegex(ExperimentConfigurationError, "mismatch"):
            validate_contract(changed, ROOT)

    def test_dry_run_has_no_live_or_experimental_activity(self) -> None:
        receipt = build_dry_run(ROOT, self.contract)
        self.assertEqual(receipt["cells_resolved"], 44)
        for field in (
            "pilot_v2_subject_calls", "pilot_v2_evaluator_calls",
            "pilot_v2_schedule_cells_executed", "policy_comparisons",
        ):
            self.assertEqual(receipt[field], 0)
        self.assertFalse(receipt["ledger_written"])

    def test_qualification_passes_at_execution_authorization_boundary(self) -> None:
        result = build_qualification(ROOT, self.contract)
        self.assertEqual(result["status"], "pass")
        self.assertIn("GIT STABILIZATION", result["decision"])
        self.assertTrue(all(result["checks"].values()))

    def test_shared_runner_confirmation_is_bound_to_v2_contract(self) -> None:
        self.assertEqual(
            execution_confirmation(self.contract),
            f"execute-pilot-v2.0:{self.contract['contract_sha256']}",
        )


if __name__ == "__main__":
    unittest.main()
