from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import build_contract, read_ledger
from engineering_scope_guard.pilot_runner import (
    append_runner_event,
    build_launch_request,
    initialize_ledger,
    next_legal_action,
)
from engineering_scope_guard.pilot_successor import (
    SUCCESSOR_LEDGER_NAME,
    build_successor_authorization,
    initialize_successor_ledger,
    next_successor_legal_action,
    predecessor_file_identity,
    successor_dry_run_receipt,
    validate_successor_authorization,
    validate_successor_start,
)
from scripts.pilot_successor_batch import execution_confirmation

ROOT = Path(__file__).resolve().parents[1]


class PilotSuccessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def _terminal_predecessor(self, root: Path) -> Path:
        ledger = root / "predecessor.jsonl"
        initialize_ledger(self.contract, ledger)
        request = build_launch_request(
            self.contract, self.contract["schedule"]["cells"][0], root / "old-state", 1
        )
        append_runner_event(ledger, "attempt_started", request)
        receipt = {
            **request,
            "started_at": "2026-08-28T00:00:00+00:00",
            "ended_at": "2026-08-28T00:00:01+00:00",
            "termination": "malformed_incomplete_measurement",
            "evaluator_result": {"resolved": None, "rounds": 0},
            "usage": {},
            "usage_complete": False,
            "admissible_under_contract": False,
            "deviations": [],
        }
        append_runner_event(ledger, "attempt_finished", receipt)
        append_runner_event(
            ledger,
            "batch_stopped",
            {"cell_id": request["cell_id"], "termination": receipt["termination"]},
        )
        return ledger

    def _qualification(self, ledger: Path) -> dict:
        terminal_hash = read_ledger(ledger)[-1]["event_sha256"]
        return {
            "contract_sha256": self.contract["contract_sha256"],
            "repairs_qualified": True,
            "provider_parser": {
                "observed_message_only_401_classified_as_provider_infrastructure": True
            },
            "materialization": {"status": "pass"},
            "ledger": {"terminal_event_sha256": terminal_hash, "unchanged": True},
            "experimental_activity": {
                "pilot_subject_invocations": 0,
                "pilot_evaluator_invocations": 0,
                "policy_comparisons": 0,
            },
        }

    def _tasks(self) -> dict[str, dict]:
        return {
            slot["actual_task_id"]: {
                "instance_id": slot["actual_task_id"],
                "repo": slot["repo"],
                "language": slot["language"],
                "base_commit": f"base-{slot['slot']}",
                "docker_image": f"image-{slot['slot']}",
                "problem_statement_sha256": f"problem-{slot['slot']}",
            }
            for slot in self.contract["final_pool"]["slots"]
        }

    def test_terminal_zero_outcome_predecessor_builds_deterministic_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._terminal_predecessor(root)
            before = ledger.read_bytes()
            events = read_ledger(ledger)
            qualification = self._qualification(ledger)
            first = build_successor_authorization(self.contract, events, qualification)
            second = build_successor_authorization(self.contract, events, qualification)
            self.assertEqual(first, second)
            self.assertEqual(first["successor"]["starting_schedule_position"], 1)
            self.assertEqual(first["failure_accounting"]["reruns_consumed_at_successor_start"], 1)
            self.assertEqual(first["failure_accounting"]["successor_cell_1_trajectory_attempt"], 2)
            self.assertEqual(first["failure_accounting"]["new_retry_capacity_added"], 0)
            self.assertEqual(
                execution_confirmation(first),
                "execute-successor-pilot-v1.0:" + first["authorization_sha256"],
            )
            self.assertEqual(ledger.read_bytes(), before)

    def test_nonterminal_or_outcome_predecessor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._terminal_predecessor(root)
            events = read_ledger(ledger)
            qualification = self._qualification(ledger)
            with self.assertRaisesRegex(ExperimentConfigurationError, "terminal"):
                build_successor_authorization(self.contract, events[:-1], qualification)
            changed = copy.deepcopy(events)
            changed[-2]["payload"]["termination"] = "accepted_completed"
            changed[-2]["payload"]["usage"] = {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_output_tokens": 0,
                "total_tokens": 2,
            }
            changed[-2]["payload"]["usage_complete"] = True
            changed[-2]["payload"]["admissible_under_contract"] = True
            changed[-2]["payload"]["evaluator_result"] = {"resolved": True, "rounds": 1}
            changed[-1]["payload"]["termination"] = "accepted_completed"
            with self.assertRaisesRegex(ExperimentConfigurationError, "outcomes"):
                build_successor_authorization(self.contract, changed, qualification)

    def test_wrong_bindings_and_modified_treatment_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self._terminal_predecessor(root)
            events = read_ledger(ledger)
            qualification = self._qualification(ledger)
            authorization = build_successor_authorization(
                self.contract, events, qualification
            )
            mutations = (
                ("contract", ("original_contract", "contract_sha256")),
                ("schedule", ("original_contract", "schedule_sha256")),
                ("treatment", ("original_contract", "c_short_sha256")),
                ("predecessor hash", ("predecessor", "terminal_event_sha256")),
                ("starting cell", ("successor", "starting_schedule_position")),
            )
            for label, path in mutations:
                with self.subTest(label=label):
                    changed = copy.deepcopy(authorization)
                    changed[path[0]][path[1]] = "wrong"
                    with self.assertRaisesRegex(
                        ExperimentConfigurationError, "authorization mismatch"
                    ):
                        validate_successor_authorization(
                            self.contract, events, qualification, changed
                        )

    def test_successor_genesis_is_separate_and_starts_cell_1_as_attempt_2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predecessor = self._terminal_predecessor(root)
            predecessor_before = predecessor.read_bytes()
            events = read_ledger(predecessor)
            qualification = self._qualification(predecessor)
            authorization = build_successor_authorization(
                self.contract, events, qualification
            )
            successor = root / SUCCESSOR_LEDGER_NAME
            successor_events = initialize_successor_ledger(
                self.contract, authorization, successor
            )
            action = next_successor_legal_action(
                self.contract, authorization, successor_events
            )
            self.assertEqual(action["action"], "launch")
            self.assertEqual(action["cell"]["position"], 1)
            self.assertEqual(action["trajectory_attempt"], 2)
            self.assertEqual(successor_events[0]["event_type"], "successor_batch_genesis")
            self.assertEqual(predecessor.read_bytes(), predecessor_before)
            with self.assertRaisesRegex(ExperimentConfigurationError, "already exists"):
                initialize_successor_ledger(self.contract, authorization, successor)

    def test_successor_attempt_2_cannot_receive_another_same_cell_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predecessor = self._terminal_predecessor(root)
            qualification = self._qualification(predecessor)
            authorization = build_successor_authorization(
                self.contract, read_ledger(predecessor), qualification
            )
            successor = root / SUCCESSOR_LEDGER_NAME
            events = initialize_successor_ledger(self.contract, authorization, successor)
            action = next_successor_legal_action(self.contract, authorization, events)
            request = build_launch_request(
                self.contract, action["cell"], root / "successor-state", 2
            )
            append_runner_event(successor, "attempt_started", request)
            receipt = {
                **request,
                "started_at": "2026-08-28T00:00:00+00:00",
                "ended_at": "2026-08-28T00:00:01+00:00",
                "termination": "provider_api_infrastructure_failure",
                "evaluator_result": {"resolved": None, "rounds": 0},
                "usage": {},
                "usage_complete": False,
                "admissible_under_contract": False,
                "deviations": [],
            }
            append_runner_event(successor, "attempt_finished", receipt)
            stopped = next_successor_legal_action(
                self.contract, authorization, read_ledger(successor)
            )
            self.assertEqual(stopped["action"], "record_rerun_budget_stop")
            self.assertEqual(stopped["consumed"], 1)

    def test_arbitrary_initial_branching_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            events = initialize_ledger(self.contract, ledger)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "unsupported initial ledger accounting"
            ):
                next_legal_action(
                    self.contract,
                    events,
                    initial_trajectory_attempt=2,
                    initial_reruns_consumed=2,
                    initially_rerun_cells=frozenset(
                        {self.contract["schedule"]["cells"][0]["cell_id"]}
                    ),
                )

    def test_dry_run_resolves_exact_schedule_without_writes_or_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predecessor = self._terminal_predecessor(root)
            predecessor_before = predecessor_file_identity(predecessor)
            qualification = self._qualification(predecessor)
            authorization = build_successor_authorization(
                self.contract, read_ledger(predecessor), qualification
            )
            successor_state = root / "successor-state"
            receipt = successor_dry_run_receipt(
                self.contract,
                ROOT,
                predecessor,
                qualification,
                authorization,
                successor_state,
                self._tasks(),
            )
            self.assertEqual(receipt["cells_resolved"], 48)
            self.assertEqual(receipt["cells"][0]["attempt_kind"], "infrastructure_rerun")
            self.assertTrue(all(
                cell["attempt_kind"] == "first_attempt" for cell in receipt["cells"][1:]
            ))
            self.assertEqual(receipt["codex_invocations"], 0)
            self.assertEqual(receipt["evaluator_invocations"], 0)
            self.assertEqual(receipt["experimental_observations_written"], 0)
            self.assertFalse(successor_state.exists())
            self.assertEqual(predecessor_file_identity(predecessor), predecessor_before)

    def test_start_rejects_duplicate_successor_and_qualification_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predecessor = self._terminal_predecessor(root)
            qualification = self._qualification(predecessor)
            authorization = build_successor_authorization(
                self.contract, read_ledger(predecessor), qualification
            )
            successor = root / SUCCESSOR_LEDGER_NAME
            successor.write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "already exists"):
                validate_successor_start(
                    self.contract,
                    predecessor,
                    qualification,
                    authorization,
                    successor,
                )
            successor.unlink()
            changed = copy.deepcopy(qualification)
            changed["ledger"]["terminal_event_sha256"] = "0" * 64
            with self.assertRaisesRegex(ExperimentConfigurationError, "qualification mismatch"):
                validate_successor_start(
                    self.contract, predecessor, changed, authorization, successor
                )


if __name__ == "__main__":
    unittest.main()
