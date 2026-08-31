from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import (
    append_ledger_event,
    build_contract,
    classify_receipt,
    generate_schedule,
    infrastructure_rerun_state,
    read_ledger,
    validate_contract,
    validate_preflight,
)

ROOT = Path(__file__).resolve().parents[1]


def preflight(contract: dict, cell: dict | None = None) -> dict:
    cell = cell or contract["schedule"]["cells"][0]
    slot = contract["final_pool"]["slots"][cell["requested_task_slot"] - 1]
    return {
        **{key: cell[key] for key in ("cell_id", "requested_task_slot", "actual_task_id", "arm", "repetition")},
        "trajectory_attempt": 1,
        "subject": contract["subject"],
        "contract_sha256": contract["contract_sha256"],
        "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "task_snapshot_sha256": slot["task_snapshot_sha256"],
        "source_and_evaluator": contract["source_and_evaluator"],
        "platform": contract["platform"],
        "trajectory_contract": contract["trajectory"],
        "isolation_contract": contract["isolation"],
        "usage_contract": contract["usage"],
        "isolation_roots": {
            "repository": f"/synthetic/{cell['cell_id']}/repository",
            "codex_home": f"/synthetic/{cell['cell_id']}/codex-home",
            "raw": f"/synthetic/{cell['cell_id']}/raw",
            "derived": f"/synthetic/{cell['cell_id']}/derived",
        },
        "intervention_sha256": (
            None if cell["arm"] == "baseline" else contract["arms"]["short_policy_sha256"]
        ),
    }


def receipt(contract: dict, termination: str, complete_usage: bool = True) -> dict:
    value = preflight(contract)
    value.update(
        {
            "started_at": "2026-08-28T00:00:00+00:00",
            "ended_at": "2026-08-28T00:00:01+00:00",
            "termination": termination,
            "evaluator_result": {"resolved": termination == "accepted_completed"},
            "usage": {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_output_tokens": 0,
                "total_tokens": 2,
            } if complete_usage else {},
            "usage_complete": complete_usage,
            "admissible_under_contract": termination in {
                "accepted_completed", "evaluator_test_failure",
                "agent_subject_failure", "trajectory_timeout",
            } and complete_usage,
            "deviations": [],
        }
    )
    return value


class PilotContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def test_repository_contract_is_exactly_regenerable(self) -> None:
        stored = json.loads((ROOT / "experiment/pilot_execution_contract.json").read_text())
        validate_contract(stored, ROOT)
        self.assertEqual(stored, self.contract)
        self.assertEqual(len(stored["schedule"]["cells"]), 48)

    def test_mismatching_subject_and_arm_contamination_are_rejected(self) -> None:
        request = preflight(self.contract)
        request["subject"] = {**request["subject"], "reasoning_effort": "high"}
        with self.assertRaisesRegex(ExperimentConfigurationError, "subject"):
            validate_preflight(self.contract, request)

        request = preflight(self.contract)
        request["intervention_sha256"] = self.contract["arms"]["short_policy_sha256"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "intervention"):
            validate_preflight(self.contract, request)

    def test_roots_cannot_be_reused_across_cells_or_attempts(self) -> None:
        first = preflight(self.contract)
        second = preflight(self.contract, self.contract["schedule"]["cells"][1])
        second["isolation_roots"] = first["isolation_roots"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "reused_isolation_root"):
            validate_preflight(self.contract, second, (first,))

    def test_schedule_is_deterministic_and_pool_bound(self) -> None:
        pool = self.contract["final_pool"]
        first = generate_schedule(pool["final_pool_sha256"], pool["slots"])
        second = generate_schedule(pool["final_pool_sha256"], pool["slots"])
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(first["schedule_sha256"], self.contract["schedule"]["schedule_sha256"])
        changed = copy.deepcopy(pool["slots"])
        changed[0]["actual_task_id"] = "synthetic-different-task"
        different = generate_schedule("0" * 64, changed)
        self.assertNotEqual(first["schedule_sha256"], different["schedule_sha256"])

    def test_task_slot_and_trajectory_budgets_are_distinct(self) -> None:
        slot = self.contract["final_pool"]["task_slot_replacement_budget"]
        rerun = self.contract["trajectory_infrastructure_rerun_budget"]
        self.assertEqual((slot["consumed"], slot["remaining"]), (4, 4))
        state = infrastructure_rerun_state(
            self.contract, [], receipt(self.contract, "provider_api_infrastructure_failure")
        )
        self.assertEqual(state, {"consumed": 1, "remaining": 7, "next_attempt": 2})
        self.assertEqual(slot["consumed"], 4)

    def test_outcomes_never_trigger_infrastructure_rerun(self) -> None:
        for termination in (
            "accepted_completed", "evaluator_test_failure", "agent_subject_failure",
            "trajectory_timeout",
        ):
            with self.subTest(termination=termination), self.assertRaisesRegex(
                ExperimentConfigurationError, "cannot consume"
            ):
                infrastructure_rerun_state(self.contract, [], receipt(self.contract, termination))

    def test_malformed_measurement_stops_and_cannot_be_admissible(self) -> None:
        value = receipt(self.contract, "malformed_incomplete_measurement", complete_usage=False)
        result = classify_receipt(self.contract, value)
        self.assertTrue(result["stop_batch"])
        self.assertFalse(result["admissible"])

        value = receipt(self.contract, "accepted_completed", complete_usage=False)
        with self.assertRaisesRegex(ExperimentConfigurationError, "must be classified malformed"):
            classify_receipt(self.contract, value)

    def test_ledger_preserves_failed_attempt_before_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "pilot.jsonl"
            failed = receipt(self.contract, "local_docker_runtime_infrastructure_failure")
            append_ledger_event(ledger, "attempt_finished", failed)
            append_ledger_event(
                ledger,
                "infrastructure_rerun_authorized",
                {"cell_id": failed["cell_id"], "next_attempt": 2, "remaining": 7},
            )
            events = read_ledger(ledger)
            self.assertEqual([event["event_type"] for event in events], [
                "attempt_finished", "infrastructure_rerun_authorized"
            ])
            self.assertEqual(events[0]["payload"]["termination"],
                             "local_docker_runtime_infrastructure_failure")

            lines = ledger.read_text().splitlines()
            ledger.write_text("\n".join(lines[1:]) + "\n")
            with self.assertRaisesRegex(ExperimentConfigurationError, "chain mismatch"):
                read_ledger(ledger)


if __name__ == "__main__":
    unittest.main()
