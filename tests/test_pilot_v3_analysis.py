from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_v3_analysis import _trace_counts, summarize_receipts

ROOT = Path(__file__).resolve().parents[1]


def receipt(slot: int, arm: str, repetition: int, accepted: bool, tokens: int) -> dict:
    return {
        "requested_task_slot": slot,
        "arm": arm,
        "repetition": repetition,
        "admissible": True,
        "termination": "accepted_completed" if accepted else "evaluator_test_failure",
        "attempt_started_at": "2026-08-29T00:00:00+00:00",
        "ended_at": "2026-08-29T00:00:10+00:00",
        "usage": {
            "input_tokens": tokens,
            "cached_input_tokens": tokens // 2,
            "calculated_fresh_input_tokens": tokens - tokens // 2,
            "output_tokens": tokens // 10,
            "reasoning_output_tokens": tokens // 20,
        },
    }


class PilotV3AnalysisTests(unittest.TestCase):
    def fixture(self) -> list[dict]:
        values = []
        for slot in (1, 2):
            for repetition in (1, 2):
                values.append(receipt(slot, "baseline", repetition, slot == 1, 100))
                values.append(receipt(slot, "short", repetition, False, 80))
        return values

    def test_task_cluster_analysis_is_paired_and_exact(self) -> None:
        result = summarize_receipts(self.fixture())
        self.assertEqual(result["analysis_population"]["complete_task_clusters"], 2)
        self.assertEqual(result["paired_acceptance"]["short_minus_baseline_percentage_points"], -50.0)
        self.assertEqual(result["paired_work"]["input_tokens"]["short_minus_baseline"], -20.0)
        self.assertEqual(result["paired_work"]["input_tokens"]["short_over_baseline_ratio"], 0.8)
        self.assertEqual(result["uncertainty"]["ordered_resamples"], 4)
        self.assertEqual(
            result["acceptance_diagnostics"]["discordance"],
            {"baseline_only_accepted": 2, "both_failed": 2},
        )

    def test_incomplete_task_is_marginal_only(self) -> None:
        values = self.fixture()
        values.append(receipt(3, "short", 1, True, 60))
        result = summarize_receipts(values)
        self.assertEqual(result["analysis_population"]["excluded_incomplete_task_slots"], [3])
        self.assertEqual(result["marginal_acceptance"]["short"]["cells"], 5)
        self.assertEqual(result["analysis_population"]["complete_paired_cells"], 8)

    def test_infrastructure_invalid_attempt_is_excluded(self) -> None:
        values = self.fixture()
        invalid = copy.deepcopy(values[0])
        invalid.update({"admissible": False, "termination": "local_docker_runtime_infrastructure_failure"})
        result = summarize_receipts([*values, invalid])
        self.assertEqual(result["analysis_population"]["admissible_cells"], 8)

    def test_too_few_complete_clusters_fail_closed(self) -> None:
        values = [item for item in self.fixture() if item["requested_task_slot"] == 1]
        with self.assertRaisesRegex(ExperimentConfigurationError, "too few"):
            summarize_receipts(values)

    def test_persisted_terminal_result_preserves_claim_and_retry_boundaries(self) -> None:
        result = json.loads(
            (ROOT / "experiment/pilot_v3_successor_terminal_result.json").read_text()
        )
        self.assertEqual(result["termination"], "attempt_limit_exhausted")
        self.assertEqual(result["schedule"]["admissible_cells"], 31)
        self.assertEqual(result["schedule"]["complete_task_clusters"], 7)
        self.assertFalse(result["retry_accounting"]["position_32_attempt_3_permitted"])
        self.assertFalse(result["claims"]["confirmatory_execution_authorized"])
        self.assertEqual(result["billing"]["provider_billed_amount"], "unavailable")

    def test_trace_counts_are_body_free_and_conservative(self) -> None:
        records = [
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "/bin/zsh -lc 'rg value src'",
                    "exit_code": 1,
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "python -m pytest",
                    "exit_code": 1,
                },
            },
            {"type": "item.completed", "item": {"type": "file_change"}},
            {"type": "item.completed", "item": {"type": "web_search"}},
            {"type": "item.completed", "item": {"type": "agent_message"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("".join(json.dumps(item) + "\n" for item in records))
            result = _trace_counts(path)
        self.assertEqual(result["command_executions"], 2)
        self.assertEqual(result["failed_command_executions"], 2)
        self.assertEqual(result["read_search_commands"], 1)
        self.assertEqual(result["verification_commands"], 1)
        self.assertEqual(result["failed_verification_commands"], 1)
        self.assertEqual(result["file_changes"], 1)
        self.assertEqual(result["web_searches"], 1)
        self.assertEqual(result["agent_messages"], 1)

    def test_persisted_mechanism_diagnostic_is_body_safe_and_adverse(self) -> None:
        path = ROOT / "experiment/pilot_v3_c_short_mechanism_diagnostic.json"
        rendered = path.read_text(encoding="utf-8")
        result = json.loads(rendered)
        self.assertTrue(result["body_safe"])
        self.assertTrue(
            result["reconciliation"]["persisted_terminal_result_reproduced_byte_for_byte"]
        )
        self.assertEqual(len(result["tasks"]), 7)
        self.assertEqual(
            result["leave_one_task_out_ranges"]["acceptance_difference_percentage_points"],
            {"minimum": -25.0, "maximum": 0.0},
        )
        self.assertGreater(
            result["leave_one_task_out_ranges"]["input_token_ratio"]["minimum"], 1.0
        )
        self.assertGreater(
            result["leave_one_task_out_ranges"]["wall_time_ratio"]["minimum"], 1.0
        )
        self.assertGreater(
            result["turn_normalized_usage"]["input_difference_decomposition"]["cached_share"],
            0.95,
        )
        replicated = next(
            task
            for task in result["tasks"]
            if task["public_task_id"] == "GladysAssistant__Gladys-2504"
        )
        self.assertEqual(
            [item["classification"] for item in replicated["repetition_pair_classifications"]],
            ["baseline_only_accepted", "baseline_only_accepted"],
        )
        self.assertNotIn("/Users/", rendered)
        self.assertNotIn(".local/", rendered)
        self.assertNotIn("task-prompt", rendered)


if __name__ == "__main__":
    unittest.main()
