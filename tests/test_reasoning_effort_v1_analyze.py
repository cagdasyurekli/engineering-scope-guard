from __future__ import annotations

import unittest

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v1 import build_contract
from scripts.reasoning_effort_v1_analyze import build_analysis, records_from_ledger


def contract_fixture() -> dict:
    return build_contract(
        [
            {
                "task_id": f"task-{number}",
                "repository": f"owner/repo-{number}",
                "task_snapshot_sha256": f"{number:x}" * 64,
            }
            for number in range(1, 9)
        ],
        model="gpt-5.6-sol",
        codex_version="0.151.0",
        runtime_identity="runtime-fixture",
        source_revision="dataset-fixture",
        evaluator_revision="evaluator-fixture",
        qualification_subject_executions=1,
    )


def receipt(cell: dict, *, classification: str = "accepted_completed") -> dict:
    return {
        "cell_id": cell["cell_id"],
        "attempt": 1,
        "task_id": cell["task_id"],
        "repository": cell["repository"],
        "arm": cell["arm"],
        "repetition": cell["repetition"],
        "classification": classification,
        "termination": classification,
        "admissible": True,
        "accepted": classification == "accepted_completed",
        "input_tokens": 100,
        "cached_input_tokens": 40,
        "cache_write_input_tokens": 10,
        "output_tokens": 20,
        "reasoning_output_tokens": 5,
        "subject_wall_seconds": 12.5,
        "subject_turns": 1,
        "command_count": 2,
        "search_count": 1,
        "item_counts": {"agent_message": 1, "command_execution": 2},
    }


def complete_events(contract: dict) -> list[dict]:
    events = []
    for position, cell in enumerate(contract["schedule"]["cells"], start=1):
        events.extend(
            (
                {
                    "event_type": "attempt_started",
                    "payload": {"cell_id": cell["cell_id"], "attempt": 1},
                    "event_sha256": f"start-{cell['cell_id']}",
                },
                {
                    "event_type": "subject_invocation_started",
                    "payload": {
                        "cell_id": cell["cell_id"],
                        "attempt": 1,
                        "prompt_sha256": "1" * 64,
                        "command_sha256": "2" * 64,
                        "codex_executable_sha256": "3" * 64,
                    },
                    "event_sha256": f"invoke-{cell['cell_id']}",
                },
                {
                    "event_type": "subject_invocation_returned",
                    "payload": {
                        "cell_id": cell["cell_id"],
                        "attempt": 1,
                        "exit_code": 0,
                        "timed_out": False,
                        "stdout_sha256": "4" * 64,
                        "stderr_sha256": "5" * 64,
                    },
                    "event_sha256": f"returned-{cell['cell_id']}",
                },
                {
                    "event_type": "attempt_finished",
                    "payload": receipt(cell),
                    "event_sha256": f"finish-{cell['cell_id']}",
                },
                {
                    "event_type": "cell_completed",
                    "payload": {"cell_id": cell["cell_id"], "attempt": 1},
                    "event_sha256": f"complete-{cell['cell_id']}",
                },
            )
        )
        if position == contract["staging"]["stage_1_cell_count"]:
            audit = {
                "schema_name": "engineering-scope-guard.reasoning-effort-v1-runner.stage-1-audit",
                "schema_version": 1,
                "status": "pass",
                "criteria": {
                    "awaiting_stage_1_authorization": True,
                    "exact_four_cell_schedule_prefix": True,
                    "both_arms_have_two_final_cells": True,
                    "arm_command_receipts_complete": True,
                    "subject_returns_complete": True,
                    "usage_receipts_complete": True,
                    "subject_work_receipts_complete": True,
                    "tool_policy_receipts_complete": True,
                    "official_evaluator_receipts_complete": True,
                    "durable_receipts_bound": True,
                    "no_batch_stop": True,
                },
                "completed_cells": 4,
                "final_cells_by_arm": {"low": 2, "medium": 2},
                "outcome_direction_inspected": False,
                "outcome_values_emitted": False,
            }
            events.extend(
                (
                    {
                        "event_type": "stage_1_boundary_reached",
                        "payload": {"completed_cell_count": position},
                        "event_sha256": "stage-1-boundary",
                    },
                    {
                        "event_type": "stage_2_authorized",
                        "payload": {
                            "stage_1_completed_cell_count": position,
                            "audit": audit,
                            "audit_sha256": digest(audit),
                        },
                        "event_sha256": "stage-2-authorized",
                    },
                )
            )
    return events


class ReasoningEffortV1AnalyzeTest(unittest.TestCase):
    def test_complete_ledger_maps_frozen_cells_and_builds_analysis(self) -> None:
        contract = contract_fixture()
        events = complete_events(contract)
        result = build_analysis(contract, events)
        self.assertEqual(result["experimental_outcomes"], 32)
        self.assertEqual(result["harness_attempts"], 32)
        self.assertEqual(result["conservative_subject_invocation_starts"], 32)
        self.assertEqual(result["confirmed_returned_subject_invocations"], 32)
        self.assertEqual(result["ambiguous_subject_invocation_starts"], 0)
        self.assertEqual(result["conservative_invocation_starts_including_qualification"], 33)
        self.assertEqual(result["analysis_population"]["complete_task_clusters"], 8)
        self.assertEqual(result["acceptance"]["by_arm"]["low"]["accepted"], 16)
        self.assertEqual(result["ledger_terminal_event_sha256"], events[-1]["event_sha256"])

    def test_retryable_infrastructure_attempt_is_not_an_outcome_record(self) -> None:
        contract = contract_fixture()
        cell = contract["schedule"]["cells"][0]
        infrastructure = receipt(
            cell, classification="provider_api_infrastructure_failure"
        )
        infrastructure["admissible"] = False
        infrastructure["accepted"] = False
        events = [
            {
                "event_type": "attempt_finished",
                "payload": infrastructure,
                "event_sha256": "infra",
            }
        ]
        self.assertEqual(records_from_ledger(events, contract["schedule"]), [])

    def test_analysis_rejects_partial_and_unreturned_completed_ledgers(self) -> None:
        contract = contract_fixture()
        events = complete_events(contract)
        first_completion = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "cell_completed"
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "terminal"):
            build_analysis(contract, events[: first_completion + 1])

        without_last_return = list(events)
        last_return = max(
            index
            for index, event in enumerate(without_last_return)
            if event["event_type"] == "subject_invocation_returned"
        )
        without_last_return.pop(last_return)
        with self.assertRaisesRegex(ExperimentConfigurationError, "returned subject"):
            build_analysis(contract, without_last_return)

    def test_identity_drift_and_partial_work_bundle_fail_closed(self) -> None:
        contract = contract_fixture()
        cell = contract["schedule"]["cells"][0]
        changed = receipt(cell)
        changed["repository"] = "different/repository"
        events = [
            {"event_type": "attempt_finished", "payload": changed},
            {
                "event_type": "cell_completed",
                "payload": {"cell_id": cell["cell_id"], "attempt": 1},
            },
        ]
        with self.assertRaisesRegex(ExperimentConfigurationError, "identity"):
            records_from_ledger(events, contract["schedule"])

        partial = receipt(cell)
        partial.pop("search_count")
        events[0]["payload"] = partial
        with self.assertRaisesRegex(ExperimentConfigurationError, "partial"):
            records_from_ledger(events, contract["schedule"])


if __name__ == "__main__":
    unittest.main()
