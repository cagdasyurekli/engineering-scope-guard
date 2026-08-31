from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_runner import EvaluatorResult, SubjectResult
from engineering_scope_guard.pilot_v3 import (
    append_event,
    build_contract,
    build_launch_request,
    evaluator_transition,
    execute_attempt_durably,
    execution_confirmation,
    generate_schedule,
    next_scheduler_action,
    read_events,
    reconstruct_receipt_from_events,
    usage_summary,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeBackend:
    def __init__(self, disposition: str = "success", feedback_status: str = "not_applicable") -> None:
        self.disposition = disposition
        self.feedback_status = feedback_status
        self.subject_calls = 0
        self.evaluator_calls = 0

    def prepare(self, request: dict) -> dict:
        codex_home = Path(request["isolation_roots"]["codex_home"])
        codex_home.mkdir(parents=True)
        (codex_home / "auth.json").write_text("fixture", encoding="utf-8")
        return {
            "started_at": "2026-08-28T00:00:00+00:00",
            "ended_at": lambda: "2026-08-28T00:00:01+00:00",
            "codex_home": codex_home,
        }

    def cleanup(self, prepared: dict) -> None:
        (prepared["codex_home"] / "auth.json").unlink()

    def run_subject(self, request: dict, prepared: dict, feedback, session_id):
        self.subject_calls += 1
        return SubjectResult(
            exit_code=0,
            timed_out=False,
            session_id=session_id or "fixture-session",
            usage={
                "input_tokens": 10,
                "cached_input_tokens": 6,
                "output_tokens": 2,
                "reasoning_output_tokens": 1,
            },
            trace_reference="fixture-trace",
        )

    def create_prediction(self, request: dict, prepared: dict) -> dict:
        return {"patch_sha256": "a" * 64}

    def evaluate(self, request: dict, prepared: dict, prediction: dict, round_number: int):
        self.evaluator_calls += 1
        resolved = {"success": True, "failure": False}.get(self.disposition)
        failures = ("test_fix",) if self.feedback_status == "available" else ()
        return EvaluatorResult(
            exit_code=0,
            timed_out=False,
            resolved=resolved,
            failing_checks=failures,
            report_reference="fixture-report",
            results_reference="fixture-results",
            report_sha256="b" * 64,
            results_sha256="c" * 64,
            official_disposition=self.disposition,
            feedback_status=self.feedback_status,
        )


class RaisingEvaluatorBackend(FakeBackend):
    def evaluate(self, request, prepared, prediction, round_number):
        self.evaluator_calls += 1
        raise OSError("synthetic evaluator process-boundary failure")


class PilotV3Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = json.loads((ROOT / "experiment/pilot_v3_pool.json").read_text())
        cls.schedule = json.loads((ROOT / "experiment/pilot_v3_schedule.json").read_text())
        cls.contract = json.loads(
            (ROOT / "experiment/pilot_v3_execution_contract.json").read_text()
        )

    def test_pool_is_fresh_small_and_reserve_is_opaque(self) -> None:
        self.assertEqual(len(self.pool["slots"]), 8)
        self.assertEqual(len({slot["repo"] for slot in self.pool["slots"]}), 8)
        self.assertEqual(self.pool["confirmatory_reserve"]["remaining_count"], 462)
        self.assertEqual(self.pool["confirmatory_reserve"]["remaining_repositories"], 199)
        self.assertFalse(self.pool["confirmatory_reserve"]["ids_or_bodies_emitted"])
        self.assertNotIn("ids", self.pool["confirmatory_reserve"])

    def test_schedule_is_paired_and_reproducible(self) -> None:
        self.assertEqual(generate_schedule(self.pool), self.schedule)
        self.assertEqual(len(self.schedule["cells"]), 32)
        for slot in self.pool["slots"]:
            cells = [
                cell
                for cell in self.schedule["cells"]
                if cell["requested_task_slot"] == slot["slot"]
            ]
            self.assertEqual(
                {(cell["arm"], cell["repetition"]) for cell in cells},
                {
                    ("baseline", 1),
                    ("short", 1),
                    ("baseline", 2),
                    ("short", 2),
                },
            )

    def test_contract_regenerates_and_never_authorizes_execution(self) -> None:
        self.assertEqual(build_contract(ROOT, self.pool, self.schedule), self.contract)
        self.assertFalse(self.contract["live_execution_authorized"])
        self.assertEqual(self.contract["arms"]["ids"], ["baseline", "short"])
        self.assertEqual(
            execution_confirmation(self.contract),
            "execute-pilot-v3.0:" + self.contract["contract_sha256"],
        )

    def test_official_disposition_and_feedback_rules_are_separate(self) -> None:
        self.assertEqual(evaluator_transition("failure", "available", 0)["action"], "correct")
        self.assertEqual(
            evaluator_transition("failure", "unavailable", 0),
            {"action": "terminate", "termination": "evaluator_test_failure"},
        )
        self.assertEqual(
            evaluator_transition("error", "not_applicable", 0)["termination"],
            "official_evaluator_error",
        )
        self.assertEqual(
            evaluator_transition("incomplete", "not_applicable", 0)["termination"],
            "official_evaluator_incomplete",
        )
        self.assertEqual(evaluator_transition("contradictory", "not_applicable", 0)["action"], "stop_batch")

    def test_no_feedback_failure_is_valid_negative_without_correction(self) -> None:
        backend = FakeBackend("failure", "unavailable")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            request = build_launch_request(self.contract, self.schedule["cells"][0], state, 1)
            request["attempt_started_at"] = "2026-08-28T00:00:00+00:00"
            append_event(ledger, "attempt_started", request)
            receipt = execute_attempt_durably(self.contract, request, backend, ledger)
        self.assertEqual(receipt["termination"], "evaluator_test_failure")
        self.assertTrue(receipt["admissible"])
        self.assertEqual(backend.subject_calls, 1)
        self.assertEqual(backend.evaluator_calls, 1)

    def test_named_feedback_gets_exactly_one_corrective_round(self) -> None:
        backend = FakeBackend("failure", "available")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            request = build_launch_request(self.contract, self.schedule["cells"][0], state, 1)
            request["attempt_started_at"] = "2026-08-28T00:00:00+00:00"
            append_event(ledger, "attempt_started", request)
            receipt = execute_attempt_durably(self.contract, request, backend, ledger)
        self.assertEqual(receipt["termination"], "evaluator_test_failure")
        self.assertEqual(backend.subject_calls, 2)
        self.assertEqual(backend.evaluator_calls, 2)

    def test_evaluator_boundary_failure_preserves_order_cleanup_and_no_receipt(self) -> None:
        backend = RaisingEvaluatorBackend()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            request = build_launch_request(self.contract, self.schedule["cells"][0], state, 1)
            request["attempt_started_at"] = "2026-08-28T00:00:00+00:00"
            append_event(ledger, "attempt_started", request)
            with self.assertRaises(OSError):
                execute_attempt_durably(self.contract, request, backend, ledger)
            events = read_events(ledger)
            self.assertEqual(
                [event["event_type"] for event in events],
                [
                    "attempt_started",
                    "isolation_verified",
                    "subject_terminated",
                    "evaluator_invoked",
                    "credential_cleanup_verified",
                ],
            )
            self.assertTrue(events[-1]["payload"]["credential_removed"])
            self.assertFalse(Path(request["credential_copy_identity"]).exists())
            with self.assertRaises(ExperimentConfigurationError):
                reconstruct_receipt_from_events(self.contract, request, events)
            self.assertNotIn("receipt_committed", [event["event_type"] for event in events])

    def test_operator_and_infrastructure_restarts_are_separate(self) -> None:
        cell = self.schedule["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            operator = root / "operator.jsonl"
            request = build_launch_request(self.contract, cell, root / "state", 1)
            append_event(operator, "attempt_started", request)
            append_event(
                operator,
                "operator_interruption_recorded",
                {
                    "cell_id": cell["cell_id"],
                    "trajectory_attempt": 1,
                    "cause": "fixture",
                    "outcome_reviewed": False,
                },
            )
            action = next_scheduler_action(self.contract, read_events(operator))
            self.assertEqual(action["action"], "authorize_operator_restart")
            append_event(
                operator,
                "operator_restart_authorized",
                {"cell_id": cell["cell_id"], "next_attempt": 2},
            )
            self.assertEqual(
                next_scheduler_action(self.contract, read_events(operator))["trajectory_attempt"],
                2,
            )

            infra = root / "infra.jsonl"
            append_event(infra, "attempt_started", request)
            append_event(
                infra,
                "receipt_committed",
                {
                    "cell_id": cell["cell_id"],
                    "trajectory_attempt": 1,
                    "termination": "official_evaluator_error",
                    "admissible": False,
                },
            )
            self.assertEqual(
                next_scheduler_action(self.contract, read_events(infra))["action"],
                "authorize_infrastructure_rerun",
            )

    def test_usage_keeps_provider_components_and_calculates_only_fresh_input(self) -> None:
        value = usage_summary(
            [
                {
                    "input_tokens": 10,
                    "cached_input_tokens": 6,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 1,
                }
            ]
        )
        self.assertEqual(value["calculated_fresh_input_tokens"], 4)
        with self.assertRaises(ExperimentConfigurationError):
            usage_summary(
                [
                    {
                        "input_tokens": 1,
                        "cached_input_tokens": 2,
                        "output_tokens": 0,
                        "reasoning_output_tokens": 0,
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
