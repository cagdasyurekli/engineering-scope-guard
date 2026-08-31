from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import read_ledger, read_object
from engineering_scope_guard.pilot_runner import (
    append_runner_event,
    build_launch_request,
    initialize_ledger,
    sha256_file,
)
from engineering_scope_guard.pilot_v2_continuation import (
    DECISION,
    INTERFACE_DECISION,
    append_continuation_event,
    build_authorization,
    build_qualification,
    continuation_dry_run_receipt,
    continuation_execution_confirmation,
    initialize_continuation_ledger,
    next_continuation_legal_action,
    read_continuation_ledger,
    strict_continuation_preflight,
    validate_authorization,
)
from scripts.pilot_v2_continuation import execute_continuation_batch

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "experiment/pilot_v2_execution_contract.json"
TERMINAL = ROOT / "experiment/pilot_v2_terminal_result.json"
PREDECESSOR = ROOT / ".local/pilot-v2-runner/pilot-ledger.jsonl"
RECORDED_AT = "2026-08-28T19:00:00Z"


class PilotV2ContinuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.predecessor = self.state / "pilot-ledger.jsonl"
        self.terminal = self.state / "terminal.json"
        contract = read_object(CONTRACT)
        initialize_ledger(contract, self.predecessor)
        for cell in contract["schedule"]["cells"][:6]:
            request = build_launch_request(contract, cell, self.state / "attempts", 1)
            append_runner_event(self.predecessor, "attempt_started", request)
            append_runner_event(
                self.predecessor,
                "attempt_finished",
                {
                    **request,
                    "started_at": "2026-08-28T00:00:00+00:00",
                    "ended_at": "2026-08-28T00:00:01+00:00",
                    "termination": "accepted_completed",
                    "evaluator_result": {"resolved": True, "rounds": 1},
                    "usage": {
                        "input_tokens": 1,
                        "cached_input_tokens": 0,
                        "output_tokens": 1,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 2,
                    },
                    "usage_complete": True,
                    "admissible_under_contract": True,
                    "deviations": [],
                },
            )
        seventh = contract["schedule"]["cells"][6]
        append_runner_event(
            self.predecessor,
            "attempt_started",
            build_launch_request(contract, seventh, self.state / "attempts", 1),
        )
        events = self.predecessor.read_text(encoding="utf-8").splitlines()
        last = json.loads(events[-1])
        terminal = {
            "status": "externally_interrupted_unresolved_partial",
            "ledger": {
                "events": 15,
                "sha256": sha256_file(self.predecessor),
                "last_event_sha256": last["event_sha256"],
                "last_event_type": "attempt_started",
                "modified_for_terminal_reporting": False,
            },
            "schedule": {
                "admissible_completed_cells": 6,
                "cells_started": 7,
                "unstarted_cells": 37,
                "infrastructure_reruns_consumed": 0,
            },
            "analysis": {
                "arm_effect_analysis_performed": False,
                "interim_baseline_vs_short_comparisons": 0,
            },
            "interruption": {
                "cause_classification": "external_user_requested_operational_interruption",
                "provider_infrastructure_failure_observed": False,
                "runtime_infrastructure_failure_observed": False,
                "operator_context_authorizes_continuation": False,
                "interrupted_cell": seventh["cell_id"],
                "interrupted_trajectory_attempt": 1,
                "evaluator_result_present": False,
            },
        }
        self.terminal.write_text(json.dumps(terminal), encoding="utf-8")
        self.continuation = self.state / "continuation" / "pilot-v2-continuation-ledger.jsonl"
        initialize_continuation_ledger(self._authorization(), self.continuation)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _authorization(self) -> dict:
        return build_authorization(
            ROOT,
            CONTRACT,
            self.terminal,
            self.predecessor,
            recorded_at=RECORDED_AT,
        )

    def _finished(self, request: dict, termination: str = "accepted_completed") -> dict:
        accepted = termination == "accepted_completed"
        usage = {
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "output_tokens": 1,
            "reasoning_output_tokens": 0,
            "total_tokens": 2,
        } if accepted else {}
        return {
            **request,
            "started_at": "2026-08-28T00:00:00+00:00",
            "ended_at": "2026-08-28T00:00:01+00:00",
            "termination": termination,
            "evaluator_result": {"resolved": True if accepted else None, "rounds": 1 if accepted else 0},
            "usage": usage,
            "usage_complete": accepted,
            "admissible_under_contract": accepted,
            "deviations": [],
        }

    def test_authorization_preserves_schedule_and_uses_distinct_accounting(self) -> None:
        before_contract = CONTRACT.read_bytes()
        before_ledger = self.predecessor.read_bytes()
        authorization = self._authorization()
        self.assertEqual(authorization["decision"], DECISION)
        self.assertEqual(authorization["continuation"]["starting_schedule_position"], 7)
        self.assertEqual(authorization["continuation"]["starting_trajectory_attempt"], 2)
        self.assertEqual(
            authorization["continuation"]["positions_1_through_6"],
            "incorporate predecessor observations without copying or rerun",
        )
        accounting = authorization["accounting"]
        self.assertEqual(accounting["category"], "operator_interruption_restart")
        self.assertFalse(accounting["infrastructure_failure_class"])
        self.assertFalse(accounting["existing_infrastructure_budget_changed"])
        self.assertEqual(accounting["existing_infrastructure_rerun_allowance"], 8)
        self.assertEqual(accounting["existing_infrastructure_reruns_remaining_at_continuation_start"], 8)
        self.assertEqual(accounting["operator_restart_units_remaining"], 0)
        self.assertFalse(accounting["cell_7_additional_rerun_after_attempt_2_permitted"])
        self.assertEqual(CONTRACT.read_bytes(), before_contract)
        self.assertEqual(self.predecessor.read_bytes(), before_ledger)

    def test_authorization_is_deterministic_and_rejects_drift(self) -> None:
        authorization = self._authorization()
        self.assertEqual(authorization, self._authorization())
        validate_authorization(
            ROOT, CONTRACT, self.terminal, self.predecessor, authorization
        )
        for section, key in (
            ("original_contract", "schedule_sha256"),
            ("predecessor", "terminal_event_sha256"),
            ("continuation", "starting_trajectory_attempt"),
            ("accounting", "existing_infrastructure_rerun_allowance"),
            ("scientific_basis", "interim_arm_effect_analysis_performed"),
        ):
            with self.subTest(section=section, key=key):
                changed = copy.deepcopy(authorization)
                changed[section][key] = "wrong"
                with self.assertRaisesRegex(
                    ExperimentConfigurationError, "authorization mismatch"
                ):
                    validate_authorization(
                        ROOT, CONTRACT, self.terminal, self.predecessor, changed
                    )

    def test_terminal_evidence_must_remain_noncomparative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed_path = Path(directory) / "terminal.json"
            changed = json.loads(self.terminal.read_text(encoding="utf-8"))
            changed["analysis"]["arm_effect_analysis_performed"] = True
            changed_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "terminal interruption evidence mismatch"
            ):
                build_authorization(
                    ROOT,
                    CONTRACT,
                    changed_path,
                    self.predecessor,
                    recorded_at=RECORDED_AT,
                )

    def test_separate_ledger_is_unstarted_and_single_creation(self) -> None:
        authorization = self._authorization()
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "continuation.jsonl"
            event = initialize_continuation_ledger(authorization, ledger)
            self.assertEqual(event["event_type"], "operator_continuation_genesis")
            self.assertFalse(event["payload"]["execution_authorized"])
            self.assertEqual(event["payload"]["starting_schedule_position"], 7)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "already exists"
            ):
                initialize_continuation_ledger(authorization, ledger)

    def test_qualification_is_zero_call_and_retains_original_identities(self) -> None:
        authorization = self._authorization()
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "continuation.jsonl"
            initialize_continuation_ledger(authorization, ledger)
            result = build_qualification(
                ROOT,
                CONTRACT,
                self.terminal,
                self.predecessor,
                ledger,
                authorization,
            )
            self.assertEqual(result["decision"], DECISION)
            self.assertEqual(result["schedule"]["completed_positions_retained"], list(range(1, 7)))
            self.assertEqual(result["schedule"]["restart"]["position"], 7)
            self.assertEqual(result["schedule"]["restart"]["trajectory_attempt"], 2)
            self.assertEqual(len(result["schedule"]["unstarted_positions_retained"]), 37)
            self.assertEqual(
                [item["position"] for item in result["schedule"]["unstarted_positions_retained"]],
                list(range(8, 45)),
            )
            self.assertTrue(all(value == 0 for value in result["activity"].values()))
            self.assertTrue(all(result["checks"].values()))

    def test_strict_execution_preflight_binds_all_frozen_lineage(self) -> None:
        authorization = self._authorization()
        result = strict_continuation_preflight(
            ROOT,
            CONTRACT,
            self.terminal,
            self.predecessor,
            self.continuation,
            authorization,
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            (result["next_position"], result["next_trajectory_attempt"]), (7, 2)
        )
        self.assertEqual(result["completed_predecessor_positions"], list(range(1, 7)))
        self.assertEqual(result["operator_restart_units_remaining"], 0)
        self.assertEqual(result["infrastructure_reruns_consumed"], 0)
        self.assertEqual((result["subject_invocations"], result["evaluator_invocations"]), (0, 0))

    def test_complete_execution_dry_run_is_position_7_through_44_only(self) -> None:
        authorization = self._authorization()
        attempt_root = self.state / "dry-run-attempts"
        ledger_before = self.continuation.read_bytes()
        result = continuation_dry_run_receipt(
            ROOT,
            CONTRACT,
            self.terminal,
            self.predecessor,
            self.continuation,
            authorization,
            attempt_root,
        )
        self.assertEqual(result["decision"], INTERFACE_DECISION)
        self.assertEqual(result["positions_resolved"], 38)
        self.assertEqual([item["position"] for item in result["cells"]], list(range(7, 45)))
        self.assertEqual(result["cells"][0]["trajectory_attempt"], 2)
        self.assertEqual(result["cells"][0]["attempt_kind"], "operator_interruption_restart")
        self.assertTrue(all(item["trajectory_attempt"] == 1 for item in result["cells"][1:]))
        self.assertTrue(all(item["attempt_kind"] == "first_attempt" for item in result["cells"][1:]))
        self.assertFalse(result["positions_1_through_6_executable"])
        self.assertEqual(self.continuation.read_bytes(), ledger_before)
        self.assertFalse(attempt_root.exists())
        self.assertEqual((result["codex_invocations"], result["evaluator_invocations"]), (0, 0))

    def test_predecessor_cells_and_attempt_three_are_rejected(self) -> None:
        authorization = self._authorization()
        contract = read_object(CONTRACT)
        predecessor_request = build_launch_request(
            contract, contract["schedule"]["cells"][0], self.state / "illegal", 1
        )
        append_continuation_event(self.continuation, "attempt_started", predecessor_request)
        with self.assertRaisesRegex(ExperimentConfigurationError, "next frozen cell"):
            next_continuation_legal_action(
                contract, authorization, read_continuation_ledger(authorization, self.continuation)
            )

        second_ledger = self.state / "attempt-three" / "ledger.jsonl"
        initialize_continuation_ledger(authorization, second_ledger)
        cell7 = contract["schedule"]["cells"][6]
        request = build_launch_request(contract, cell7, self.state / "attempt-three-roots", 2)
        append_continuation_event(second_ledger, "attempt_started", request)
        append_continuation_event(
            second_ledger,
            "attempt_finished",
            self._finished(request, "provider_api_infrastructure_failure"),
        )
        action = next_continuation_legal_action(
            contract, authorization, read_continuation_ledger(authorization, second_ledger)
        )
        self.assertEqual(action["action"], "record_rerun_budget_stop")
        self.assertEqual(action["consumed"], 0)
        append_continuation_event(
            second_ledger,
            "infrastructure_rerun_authorized",
            {"cell_id": cell7["cell_id"], "consumed": 1, "remaining": 7, "next_attempt": 3},
        )
        with self.assertRaisesRegex(
            ExperimentConfigurationError,
            "exhausted its attempt allowance|already consumed",
        ):
            next_continuation_legal_action(
                contract, authorization, read_continuation_ledger(authorization, second_ledger)
            )

    def test_durable_resume_skips_completed_continuation_cell(self) -> None:
        authorization = self._authorization()
        contract = read_object(CONTRACT)
        cell7 = contract["schedule"]["cells"][6]
        request = build_launch_request(contract, cell7, self.state / "resume-roots", 2)
        append_continuation_event(self.continuation, "attempt_started", request)
        append_continuation_event(self.continuation, "attempt_finished", self._finished(request))
        del request
        events_after_process_restart = read_continuation_ledger(
            authorization, self.continuation
        )
        action = next_continuation_legal_action(
            contract, authorization, events_after_process_restart
        )
        self.assertEqual(action["action"], "launch")
        self.assertEqual((action["cell"]["position"], action["trajectory_attempt"]), (8, 1))

    def test_infrastructure_budget_remains_separate_after_cell_7(self) -> None:
        authorization = self._authorization()
        contract = read_object(CONTRACT)
        cell7, cell8 = contract["schedule"]["cells"][6:8]
        request7 = build_launch_request(contract, cell7, self.state / "budget-roots", 2)
        append_continuation_event(self.continuation, "attempt_started", request7)
        append_continuation_event(self.continuation, "attempt_finished", self._finished(request7))
        request8 = build_launch_request(contract, cell8, self.state / "budget-roots", 1)
        append_continuation_event(self.continuation, "attempt_started", request8)
        append_continuation_event(
            self.continuation,
            "attempt_finished",
            self._finished(request8, "provider_api_infrastructure_failure"),
        )
        action = next_continuation_legal_action(
            contract, authorization, read_continuation_ledger(authorization, self.continuation)
        )
        self.assertEqual(action["action"], "authorize_infrastructure_rerun")
        self.assertEqual(action["state"], {"consumed": 1, "remaining": 7, "next_attempt": 2})
        self.assertEqual(authorization["accounting"]["operator_restart_units_remaining"], 0)

    def test_authorization_contract_schedule_and_ledger_drift_fail_closed(self) -> None:
        authorization = self._authorization()
        changed_authorization = copy.deepcopy(authorization)
        changed_authorization["authorization_sha256"] = "0" * 64
        with self.assertRaisesRegex(ExperimentConfigurationError, "authorization mismatch"):
            strict_continuation_preflight(
                ROOT, CONTRACT, self.terminal, self.predecessor, self.continuation,
                changed_authorization,
            )

        changed_contract = self.state / "changed-contract.json"
        contract_value = read_object(CONTRACT)
        contract_value["schedule"]["cells"][7]["actual_task_id"] = "unauthorized"
        changed_contract.write_text(json.dumps(contract_value), encoding="utf-8")
        with self.assertRaisesRegex(ExperimentConfigurationError, "frozen Pilot-v2 contract mismatch"):
            strict_continuation_preflight(
                ROOT, changed_contract, self.terminal, self.predecessor, self.continuation,
                authorization,
            )

        lines = self.continuation.read_text(encoding="utf-8").splitlines()
        genesis = json.loads(lines[0])
        genesis["payload"]["starting_schedule_position"] = 8
        self.continuation.write_text(json.dumps(genesis) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ExperimentConfigurationError, "digest mismatch"):
            strict_continuation_preflight(
                ROOT, CONTRACT, self.terminal, self.predecessor, self.continuation,
                authorization,
            )

    def test_frozen_stop_semantics_remain_enforceable(self) -> None:
        authorization = self._authorization()
        contract = read_object(CONTRACT)
        cell7 = contract["schedule"]["cells"][6]
        request = build_launch_request(contract, cell7, self.state / "stop-roots", 2)
        append_continuation_event(self.continuation, "attempt_started", request)
        append_continuation_event(
            self.continuation, "attempt_finished", self._finished(request, "harness_failure")
        )
        action = next_continuation_legal_action(
            contract, authorization, read_continuation_ledger(authorization, self.continuation)
        )
        self.assertEqual(action["action"], "record_batch_stop")
        append_continuation_event(
            self.continuation,
            "batch_stopped",
            {"cell_id": cell7["cell_id"], "termination": "harness_failure"},
        )
        terminal = next_continuation_legal_action(
            contract, authorization, read_continuation_ledger(authorization, self.continuation)
        )
        self.assertEqual(terminal["action"], "batch_stopped")

    def test_fault_injection_cleans_credentials_and_checkpoints_before_return(self) -> None:
        authorization = self._authorization()
        contract = read_object(CONTRACT)

        class RaisingBackend:
            cleaned = False

            def prepare(inner_self, request: dict) -> dict:
                roots = {name: Path(value) for name, value in request["isolation_roots"].items()}
                for path in roots.values():
                    path.mkdir(parents=True, exist_ok=False)
                auth = roots["codex_home"] / "auth.json"
                auth.write_text("fixture", encoding="utf-8")
                os.chmod(auth, 0o600)
                return {
                    **roots,
                    "started_at": "2026-08-28T00:00:00+00:00",
                    "ended_at": "2026-08-28T00:00:01+00:00",
                }

            def cleanup(inner_self, prepared: dict) -> None:
                (prepared["codex_home"] / "auth.json").unlink(missing_ok=True)
                inner_self.cleaned = True

            def run_subject(inner_self, *args: object) -> object:
                raise OSError("fault injection before provider boundary")

        backend = RaisingBackend()
        result = execute_continuation_batch(
            contract,
            authorization,
            backend,  # type: ignore[arg-type]
            self.continuation.parent,
            self.continuation,
            continuation_execution_confirmation(authorization),
            None,
        )
        self.assertEqual(result["status"], "batch_stopped")
        self.assertTrue(backend.cleaned)
        self.assertEqual(
            list(self.continuation.parent.glob("attempts/*/*/codex-home/auth.json")), []
        )
        events = read_ledger(self.continuation)
        self.assertEqual(
            [event["event_type"] for event in events[-3:]],
            ["attempt_started", "attempt_finished", "batch_stopped"],
        )
        self.assertEqual(events[-2]["payload"]["termination"], "harness_failure")

    def test_live_entry_point_rejects_missing_separate_confirmation_before_writes(self) -> None:
        authorization = self._authorization()
        contract = read_object(CONTRACT)
        before = self.continuation.read_bytes()
        with self.assertRaisesRegex(ExperimentConfigurationError, "confirmation digest"):
            execute_continuation_batch(
                contract,
                authorization,
                object(),  # type: ignore[arg-type]
                self.continuation.parent,
                self.continuation,
                "not-authorized",
                None,
            )
        self.assertEqual(self.continuation.read_bytes(), before)
        self.assertFalse(
            (self.continuation.parent / "REAL_CONTINUATION_EXECUTE_INVOKED").exists()
        )

    def test_confirmatory_rule_requires_predeclared_bounded_accounting(self) -> None:
        rule = self._authorization()["future_confirmatory_predeclaration"]
        self.assertTrue(rule["operator_restart_allowance_must_be_fixed_before_execution"])
        self.assertTrue(rule["operator_restart_accounting_separate_from_infrastructure"])
        self.assertEqual(rule["maximum_total_attempts_per_cell_across_all_categories"], 2)
        self.assertEqual(rule["exhausted_allowance_disposition"], "stop and preserve incomplete state")
        self.assertFalse(rule["interim_effect_review_before_restart_permitted"])

    @unittest.skipUnless(PREDECESSOR.is_file(), "preserved local Pilot-v2 ledger absent")
    def test_repository_authorization_matches_preserved_local_evidence(self) -> None:
        authorization = json.loads(
            (ROOT / "experiment/pilot_v2_continuation_authorization.json").read_text(
                encoding="utf-8"
            )
        )
        validate_authorization(ROOT, CONTRACT, TERMINAL, PREDECESSOR, authorization)


if __name__ == "__main__":
    unittest.main()
