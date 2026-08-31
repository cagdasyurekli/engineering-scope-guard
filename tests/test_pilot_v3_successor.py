from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_runner import sha256_file
from engineering_scope_guard.pilot_v3 import (
    append_event,
    build_launch_request,
    read_events,
)
from engineering_scope_guard.pilot_v3_successor import (
    build_authorization,
    initialize_successor_ledger,
    next_successor_action,
    strict_successor_preflight,
    successor_dry_run_receipt,
    successor_execution_confirmation,
    validate_authorization,
    validate_successor_ledger,
)
from scripts.pilot_v3_successor import execute_successor_batch
from tests.test_pilot_v3 import FakeBackend, RaisingEvaluatorBackend

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR = ROOT / ".local/pilot-v3-runner/pilot-v3-ledger.jsonl"


class PilotV3SuccessorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiment/pilot_v3_execution_contract.json").read_text())
        cls.pool = json.loads((ROOT / "experiment/pilot_v3_pool.json").read_text())
        cls.schedule = json.loads((ROOT / "experiment/pilot_v3_schedule.json").read_text())
        cls.terminal = copy.deepcopy(
            json.loads((ROOT / "experiment/pilot_v3_terminal_result.json").read_text())
        )
        cls.fixture_directory = tempfile.TemporaryDirectory()
        fixture_root = Path(cls.fixture_directory.name)
        cls.predecessor = fixture_root / "pilot-v3-ledger.jsonl"
        first = cls.schedule["cells"][0]
        request = build_launch_request(cls.contract, first, fixture_root / "state", 1)
        for kind, payload in (
            ("contract_frozen", {"contract_sha256": cls.contract["contract_sha256"]}),
            ("pool_frozen", {"pool_sha256": cls.contract["pool"]["pool_sha256"]}),
            (
                "schedule_frozen",
                {
                    "schedule_sha256": cls.contract["schedule"]["schedule_sha256"],
                    "cells": 32,
                },
            ),
            ("attempt_started", request),
            ("isolation_verified", {"cell_id": first["cell_id"]}),
            ("subject_terminated", {"cell_id": first["cell_id"]}),
            ("evaluator_invoked", {"cell_id": first["cell_id"]}),
            (
                "credential_cleanup_verified",
                {"cell_id": first["cell_id"], "credential_removed": True},
            ),
            (
                "batch_stopped",
                {"cell_id": first["cell_id"], "termination": "durable_evidence_incomplete"},
            ),
        ):
            append_event(cls.predecessor, kind, payload)
        events = read_events(cls.predecessor)
        cls.terminal["ledger"]["sha256"] = sha256_file(cls.predecessor)
        cls.terminal["ledger"]["last_event_sha256"] = events[-1]["event_sha256"]
        cls.authorization = build_authorization(
            ROOT,
            cls.contract,
            cls.pool,
            cls.schedule,
            cls.terminal,
            cls.predecessor,
            recorded_at="2026-08-29T00:00:00+00:00",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture_directory.cleanup()

    def test_authorization_binds_predecessor_repair_and_unchanged_budgets(self) -> None:
        validate_authorization(
            ROOT,
            self.contract,
            self.pool,
            self.schedule,
            self.terminal,
            self.predecessor,
            self.authorization,
        )
        self.assertEqual(self.authorization["predecessor"]["failed_attempt"], 1)
        self.assertEqual(self.authorization["successor"]["starting_trajectory_attempt"], 2)
        self.assertFalse(self.authorization["successor"]["position_1_attempt_3_permitted"])
        self.assertEqual(
            self.authorization["accounting"]["infrastructure_reruns_remaining_at_successor_start"],
            4,
        )
        self.assertEqual(
            self.authorization["accounting"]["operator_interruptions_remaining_at_successor_start"],
            2,
        )
        self.assertFalse(self.authorization["accounting"]["budgets_increased_or_reset"])

    def test_predecessor_or_authorization_drift_fails_closed(self) -> None:
        changed = copy.deepcopy(self.authorization)
        changed["successor"]["starting_trajectory_attempt"] = 1
        with self.assertRaises(ExperimentConfigurationError):
            validate_authorization(
                ROOT,
                self.contract,
                self.pool,
                self.schedule,
                self.terminal,
                self.predecessor,
                changed,
            )

    @unittest.skipUnless(PREDECESSOR.is_file(), "preserved local Pilot-v3 ledger absent")
    def test_repository_authorization_matches_preserved_local_evidence(self) -> None:
        authorization = json.loads(
            (ROOT / "experiment/pilot_v3_successor_authorization.json").read_text()
        )
        terminal = json.loads(
            (ROOT / "experiment/pilot_v3_terminal_result.json").read_text()
        )
        validate_authorization(
            ROOT,
            self.contract,
            self.pool,
            self.schedule,
            terminal,
            PREDECESSOR,
            authorization,
        )

    def test_genesis_starts_position_1_at_attempt_2_and_never_attempt_3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "successor.jsonl"
            events = initialize_successor_ledger(self.authorization, ledger)
            validate_successor_ledger(self.authorization, ledger)
            action = next_successor_action(self.contract, self.authorization, events)
            self.assertEqual(action["cell"]["position"], 1)
            self.assertEqual(action["trajectory_attempt"], 2)
            request = build_launch_request(self.contract, action["cell"], Path(directory), 2)
            request["attempt_started_at"] = "2026-08-29T00:00:01+00:00"
            append_event(ledger, "attempt_started", request)
            append_event(
                ledger,
                "receipt_committed",
                {
                    "cell_id": request["cell_id"],
                    "trajectory_attempt": 2,
                    "termination": "official_evaluator_error",
                },
            )
            action = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual(action["action"], "record_batch_stop")
            self.assertEqual(action["termination"], "attempt_limit_exhausted")

    def test_completed_cell_is_skipped_after_restart_and_position_2_uses_attempt_1(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "successor.jsonl"
            initialize_successor_ledger(self.authorization, ledger)
            first = self.schedule["cells"][0]
            request = build_launch_request(self.contract, first, Path(directory), 2)
            request["attempt_started_at"] = "2026-08-29T00:00:01+00:00"
            append_event(ledger, "attempt_started", request)
            append_event(
                ledger,
                "receipt_committed",
                {
                    "cell_id": first["cell_id"],
                    "trajectory_attempt": 2,
                    "termination": "accepted_completed",
                },
            )
            events = validate_successor_ledger(self.authorization, ledger)
            first_read = next_successor_action(self.contract, self.authorization, events)
            second_read = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual(first_read, second_read)
            self.assertEqual(first_read["cell"]["position"], 2)
            self.assertEqual(first_read["trajectory_attempt"], 1)

    def test_unclassified_incomplete_attempt_stops_from_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "successor.jsonl"
            initialize_successor_ledger(self.authorization, ledger)
            request = build_launch_request(
                self.contract, self.schedule["cells"][0], Path(directory), 2
            )
            request["attempt_started_at"] = "2026-08-29T00:00:01+00:00"
            append_event(ledger, "attempt_started", request)
            action = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual(action["action"], "record_batch_stop")
            self.assertEqual(action["termination"], "durable_evidence_incomplete")

    @unittest.skipUnless(PREDECESSOR.is_file(), "preserved local Pilot-v3 ledger absent")
    def test_strict_preflight_and_complete_dry_run_are_zero_call(self) -> None:
        authorization = json.loads(
            (ROOT / "experiment/pilot_v3_successor_authorization.json").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            successor = Path(directory) / "pilot-v3-successor-ledger.jsonl"
            initialize_successor_ledger(authorization, successor)
            before = successor.read_bytes()
            preflight = strict_successor_preflight(
                ROOT, PREDECESSOR, successor, authorization
            )
            state = Path(directory) / "dry-run-state"
            receipt = successor_dry_run_receipt(
                ROOT, PREDECESSOR, successor, authorization, state
            )
            self.assertFalse(state.exists())
            self.assertEqual(successor.read_bytes(), before)
        self.assertEqual((preflight["next_position"], preflight["next_trajectory_attempt"]), (1, 2))
        self.assertEqual(receipt["positions_resolved"], 32)
        self.assertEqual(receipt["cells"][0]["trajectory_attempt"], 2)
        self.assertTrue(all(item["trajectory_attempt"] == 1 for item in receipt["cells"][1:]))
        self.assertEqual((receipt["codex_invocations"], receipt["evaluator_invocations"]), (0, 0))

    def test_confirmation_is_authorization_digest_bound_and_wrong_value_is_inert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "pilot-v3-successor-ledger.jsonl"
            initialize_successor_ledger(self.authorization, ledger)
            before = ledger.read_bytes()
            with self.assertRaisesRegex(ExperimentConfigurationError, "confirmation digest"):
                execute_successor_batch(
                    self.contract,
                    self.authorization,
                    FakeBackend(),  # type: ignore[arg-type]
                    state,
                    ledger,
                    "wrong",
                )
            self.assertEqual(ledger.read_bytes(), before)
            self.assertFalse((state / "REAL_SUCCESSOR_EXECUTE_INVOKED").exists())
            self.assertTrue(
                successor_execution_confirmation(self.authorization).endswith(
                    self.authorization["authorization_sha256"]
                )
            )

    def test_fixture_execution_completes_exact_schedule_without_repetition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "pilot-v3-successor-ledger.jsonl"
            initialize_successor_ledger(self.authorization, ledger)
            backend = FakeBackend()
            result = execute_successor_batch(
                self.contract,
                self.authorization,
                backend,  # type: ignore[arg-type]
                state,
                ledger,
                successor_execution_confirmation(self.authorization),
            )
            self.assertEqual(result, {"status": "complete", "successor_cells": 32})
            self.assertEqual((backend.subject_calls, backend.evaluator_calls), (32, 32))
            events = validate_successor_ledger(self.authorization, ledger)
            starts = [event["payload"] for event in events if event["event_type"] == "attempt_started"]
            self.assertEqual(len(starts), 32)
            self.assertEqual(starts[0]["trajectory_attempt"], 2)
            self.assertTrue(all(item["trajectory_attempt"] == 1 for item in starts[1:]))
            self.assertEqual(next_successor_action(self.contract, self.authorization, events)["action"], "complete")

    def test_fault_injection_cleans_credentials_and_stops_durably(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "pilot-v3-successor-ledger.jsonl"
            initialize_successor_ledger(self.authorization, ledger)
            backend = RaisingEvaluatorBackend()
            result = execute_successor_batch(
                self.contract,
                self.authorization,
                backend,  # type: ignore[arg-type]
                state,
                ledger,
                successor_execution_confirmation(self.authorization),
            )
            self.assertEqual(result["status"], "batch_stopped")
            events = validate_successor_ledger(self.authorization, ledger)
            kinds = [event["event_type"] for event in events]
            self.assertLess(kinds.index("credential_cleanup_verified"), kinds.index("batch_stopped"))
            self.assertFalse(any(state.glob("attempts/*/*/codex-home/auth.json")))

    def test_operator_interruption_and_infrastructure_allowances_remain_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "pilot-v3-successor-ledger.jsonl"
            initialize_successor_ledger(self.authorization, ledger)
            first = self.schedule["cells"][0]
            first_request = build_launch_request(self.contract, first, state, 2)
            first_request["attempt_started_at"] = "2026-08-29T00:00:01+00:00"
            append_event(ledger, "attempt_started", first_request)
            append_event(
                ledger,
                "receipt_committed",
                {"cell_id": first["cell_id"], "trajectory_attempt": 2, "termination": "accepted_completed"},
            )
            second = self.schedule["cells"][1]
            second_request = build_launch_request(self.contract, second, state, 1)
            second_request["attempt_started_at"] = "2026-08-29T00:00:02+00:00"
            append_event(ledger, "attempt_started", second_request)
            append_event(
                ledger,
                "operator_interruption_recorded",
                {"cell_id": second["cell_id"], "trajectory_attempt": 1, "cause": "fixture", "outcome_reviewed": False},
            )
            action = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual(action["action"], "authorize_operator_restart")
            self.assertEqual(action["consumed"], 1)
            append_event(
                ledger,
                "operator_restart_authorized",
                {"cell_id": second["cell_id"], "next_attempt": 2, "operator_interruptions_consumed": 1},
            )
            restart = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual((restart["action"], restart["trajectory_attempt"]), ("launch", 2))
            second_retry = build_launch_request(self.contract, second, state, 2)
            second_retry["attempt_started_at"] = "2026-08-29T00:00:03+00:00"
            append_event(ledger, "attempt_started", second_retry)
            append_event(
                ledger,
                "receipt_committed",
                {"cell_id": second["cell_id"], "trajectory_attempt": 2, "termination": "accepted_completed"},
            )
            third = self.schedule["cells"][2]
            third_request = build_launch_request(self.contract, third, state, 1)
            third_request["attempt_started_at"] = "2026-08-29T00:00:04+00:00"
            append_event(ledger, "attempt_started", third_request)
            append_event(
                ledger,
                "receipt_committed",
                {"cell_id": third["cell_id"], "trajectory_attempt": 1, "termination": "official_evaluator_error"},
            )
            infrastructure = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual(infrastructure["action"], "authorize_infrastructure_rerun")
            self.assertEqual(infrastructure["consumed"], 1)
            append_event(
                ledger,
                "infrastructure_rerun_authorized",
                {"cell_id": third["cell_id"], "next_attempt": 2, "infrastructure_reruns_consumed": 1},
            )
            infrastructure_restart = next_successor_action(
                self.contract, self.authorization, validate_successor_ledger(self.authorization, ledger)
            )
            self.assertEqual(
                (infrastructure_restart["action"], infrastructure_restart["trajectory_attempt"]),
                ("launch", 2),
            )
            self.assertEqual(
                sum(event["event_type"] == "infrastructure_rerun_authorized" for event in read_events(ledger)),
                1,
            )


if __name__ == "__main__":
    unittest.main()
