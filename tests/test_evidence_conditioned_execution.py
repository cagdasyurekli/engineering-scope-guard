from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from engineering_scope_guard.evidence_conditioned_execution import (
    CODEX_VERSION,
    INFRASTRUCTURE_RETRY_ALLOWANCE,
    MAXIMUM_ATTEMPTS_PER_CELL,
    OPERATOR_INTERRUPTION_ALLOWANCE,
    TREATMENT_PATH,
    TREATMENT_SHA256,
    build_contract,
    build_launch_request,
    dry_run_receipt,
    execute_attempt_durably,
    execution_confirmation,
    initialize_ledger,
    next_legal_action,
    reconstruct_receipt_from_events,
    validate_contract,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.exploratory_design import canonical_bytes
from engineering_scope_guard.pilot_runner import (
    EvaluatorResult,
    SubjectResult,
    canonical_attempt_timeout,
)
from engineering_scope_guard.pilot_v3 import append_event, planned_pause_allowed, read_events

ROOT = Path(__file__).resolve().parents[1]
USAGE = {
    "input_tokens": 100,
    "cached_input_tokens": 40,
    "output_tokens": 20,
    "reasoning_output_tokens": 5,
}


class FakeBackend:
    def __init__(
        self,
        dispositions: list[tuple[str, str, tuple[str, ...]]] | None = None,
        *,
        ordinary_exit: int = 0,
        treatment_exit: int = 0,
        correction_session: str = "session-1",
        raise_during: str | None = None,
    ) -> None:
        self.dispositions = dispositions or [("success", "not_applicable", ())]
        self.ordinary_exit = ordinary_exit
        self.treatment_exit = treatment_exit
        self.correction_session = correction_session
        self.raise_during = raise_during
        self.calls: list[tuple[Any, ...]] = []

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        roots = {name: Path(value) for name, value in request["isolation_roots"].items()}
        for path in roots.values():
            path.mkdir(parents=True, exist_ok=False)
        credential = Path(request["credential_copy_identity"])
        credential.write_text("fixture", encoding="utf-8")
        self.calls.append(("prepare", request["arm"]))
        return {
            "started_at": "2026-08-29T00:00:00+00:00",
            "ended_at": "2026-08-29T00:01:00+00:00",
            "credential": credential,
        }

    def cleanup(self, prepared: dict[str, Any]) -> None:
        prepared["credential"].unlink(missing_ok=True)
        self.calls.append(("cleanup",))

    def _subject(self, phase: str, exit_code: int, session: str) -> SubjectResult:
        if self.raise_during == phase:
            raise RuntimeError(f"fixture {phase} boundary failure")
        self.calls.append((phase, session))
        return SubjectResult(
            exit_code=exit_code,
            timed_out=False,
            session_id=session if exit_code == 0 else None,
            usage=USAGE,
            trace_reference=f"fixture-{phase}.jsonl",
        )

    def run_ordinary(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> SubjectResult:
        return self._subject("ordinary", self.ordinary_exit, "session-1")

    def run_treatment(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        treatment: bytes,
        session_id: str,
    ) -> SubjectResult:
        self.calls.append(("treatment-bytes", treatment, session_id))
        return self._subject("treatment", self.treatment_exit, session_id)

    def run_correction(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...],
        session_id: str,
    ) -> SubjectResult:
        self.calls.append(("feedback", feedback, session_id))
        return self._subject("corrective", 0, self.correction_session)

    def create_prediction(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("prediction",))
        return {"patch_sha256": "a" * 64}

    def evaluate(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prediction: dict[str, Any],
        round_number: int,
    ) -> EvaluatorResult:
        if self.raise_during == "evaluator":
            raise RuntimeError("fixture evaluator boundary failure")
        disposition, feedback, checks = self.dispositions[round_number]
        self.calls.append(("evaluate", round_number, disposition, feedback))
        return EvaluatorResult(
            exit_code=0,
            timed_out=False,
            resolved={"success": True, "failure": False}.get(disposition),
            failing_checks=checks,
            report_reference=f"report-{round_number}.json",
            results_reference=f"results-{round_number}.json",
            report_sha256="b" * 64,
            results_sha256="c" * 64,
            infrastructure_failure=disposition in {"error", "incomplete"},
            official_disposition=disposition,
            feedback_status=feedback,
        )


class EvidenceConditionedExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = build_contract(ROOT)
        cls.treatment = (ROOT / TREATMENT_PATH).read_bytes()

    def request(
        self, state: Path, arm: str = "treatment", position: int | None = None
    ) -> dict[str, Any]:
        cell = next(
            item
            for item in self.contract["schedule"]["cells"]
            if item["arm"] == arm and (position is None or item["position"] == position)
        )
        return build_launch_request(self.contract, cell, state, 1)

    def execute(
        self, state: Path, backend: FakeBackend, arm: str = "treatment"
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        ledger = state / "ledger.jsonl"
        initialize_ledger(self.contract, ledger)
        request = self.request(state, arm)
        request["attempt_started_at"] = "2026-08-29T00:00:00+00:00"
        append_event(ledger, "attempt_started", request)
        receipt = execute_attempt_durably(
            self.contract, request, backend, ledger, self.treatment
        )
        return receipt, read_events(ledger)

    def test_contract_binds_all_frozen_and_runtime_identities(self) -> None:
        validate_contract(ROOT, self.contract)
        identities = self.contract["frozen_identities"]
        self.assertEqual(identities["treatment_sha256"], TREATMENT_SHA256)
        self.assertEqual(
            identities["confirmatory_reserve"]["commitment_sha256"],
            "05624992aee92836b04bdf0b76ad18690e152ced8f21bc9b807efbefc2b52af8",
        )
        self.assertFalse(
            identities["confirmatory_reserve"]["remaining_ids_or_bodies_emitted"]
        )
        self.assertEqual(self.contract["subject"]["codex_version"], CODEX_VERSION)
        self.assertEqual(self.contract["subject"]["model"], "gpt-5.6-terra")
        self.assertEqual(self.contract["subject"]["reasoning_effort"], "medium")
        self.assertEqual(
            self.contract["attempt_accounting"]["infrastructure_retry_allowance"],
            INFRASTRUCTURE_RETRY_ALLOWANCE,
        )
        self.assertEqual(
            self.contract["attempt_accounting"]["operator_interruption_allowance"],
            OPERATOR_INTERRUPTION_ALLOWANCE,
        )

    def test_contract_drift_and_timeout_schema_fail_closed(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["subject"]["model"] = "different"
        with self.assertRaisesRegex(ExperimentConfigurationError, "contract drifted"):
            validate_contract(ROOT, changed)
        self.assertEqual(
            canonical_attempt_timeout(
                self.contract["trajectory"]["canonical_timeout_schema"],
                {
                    key: value
                    for key, value in self.contract["trajectory"].items()
                    if key != "canonical_timeout_schema"
                },
            ),
            1800,
        )
        malformed = dict(self.contract["trajectory"])
        timeout_schema = malformed.pop("canonical_timeout_schema")
        malformed["timeout_seconds_per_trajectory_attempt"] = 1800
        with self.assertRaisesRegex(ExperimentConfigurationError, "ambiguous"):
            canonical_attempt_timeout(timeout_schema, malformed)

    def test_zero_live_dry_run_resolves_exact_32_cell_schedule(self) -> None:
        receipt = dry_run_receipt(self.contract, Path("/synthetic/exploratory"))
        self.assertEqual(receipt["positions"], list(range(1, 33)))
        self.assertEqual(receipt["cells_resolved"], 32)
        self.assertEqual(receipt["baseline_cells"], 16)
        self.assertEqual(receipt["treatment_cells"], 16)
        self.assertTrue(receipt["all_cells_begin_at_attempt"])
        self.assertTrue(receipt["all_isolation_roots_unique"])
        self.assertEqual(receipt["subject_calls"], 0)
        self.assertEqual(receipt["evaluator_calls"], 0)
        self.assertFalse(receipt["ledger_written"])
        for plan in receipt["delivery_plans"]:
            self.assertFalse(plan["ordinary_task_treatment_exposure"])
            expected = TREATMENT_SHA256 if plan["arm"] == "treatment" else None
            self.assertEqual(plan["late_stage_stdin_sha256"], expected)

    def test_attempt_three_and_wrong_confirmation_are_inert(self) -> None:
        cell = self.contract["schedule"]["cells"][0]
        with self.assertRaisesRegex(ExperimentConfigurationError, "frozen maximum"):
            build_launch_request(self.contract, cell, Path("/state"), 3)
        confirmation = execution_confirmation(self.contract)
        self.assertEqual(
            confirmation,
            f"execute-{self.contract['contract_version']}:{self.contract['contract_sha256']}",
        )
        self.assertNotEqual("execute", confirmation)

    def test_baseline_never_receives_treatment_or_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            receipt, events = self.execute(Path(directory), backend, "baseline")
        self.assertEqual(receipt["termination"], "accepted_completed")
        self.assertFalse(receipt["treatment_activation"]["activated"])
        self.assertEqual(receipt["subject_turns"], 1)
        self.assertFalse(any(call[0] == "treatment-bytes" for call in backend.calls))
        self.assertFalse(
            any(event["event_type"] == "treatment_activation_started" for event in events)
        )

    def test_treatment_activates_once_after_ordinary_turn_with_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            receipt, events = self.execute(Path(directory), backend)
        self.assertEqual(receipt["termination"], "accepted_completed")
        self.assertEqual(
            [call[0] for call in backend.calls],
            [
                "prepare",
                "ordinary",
                "treatment-bytes",
                "treatment",
                "prediction",
                "evaluate",
                "cleanup",
            ],
        )
        treatment_call = next(call for call in backend.calls if call[0] == "treatment-bytes")
        self.assertEqual(treatment_call[1], self.treatment)
        activation_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "treatment_activation_started"
        )
        ordinary_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "subject_terminated"
            and event["payload"]["phase"] == "ordinary"
        )
        evaluator_index = next(
            index
            for index, event in enumerate(events)
            if event["event_type"] == "evaluator_invoked"
        )
        self.assertLess(ordinary_index, activation_index)
        self.assertLess(activation_index, evaluator_index)
        self.assertEqual(receipt["treatment_activation"]["pre_activation_subject_turns"], 1)

    def test_preactivation_subject_failure_is_valid_negative_without_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend(ordinary_exit=1)
            receipt, _events = self.execute(Path(directory), backend)
        self.assertEqual(receipt["termination"], "agent_subject_failure")
        self.assertFalse(receipt["treatment_activation"]["activated"])
        self.assertFalse(any(call[0] == "treatment-bytes" for call in backend.calls))

    def test_named_feedback_gets_one_same_session_correction(self) -> None:
        backend = FakeBackend(
            [
                ("failure", "available", ("named-check",)),
                ("success", "not_applicable", ()),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            receipt, _events = self.execute(Path(directory), backend)
        self.assertEqual(receipt["termination"], "accepted_completed")
        self.assertEqual(receipt["corrective_rounds"], 1)
        feedback = next(call for call in backend.calls if call[0] == "feedback")
        self.assertEqual(feedback[1], ("named-check",))
        self.assertEqual(feedback[2], "session-1")

    def test_unavailable_feedback_is_negative_without_invented_correction(self) -> None:
        backend = FakeBackend([("failure", "unavailable", ())])
        with tempfile.TemporaryDirectory() as directory:
            receipt, _events = self.execute(Path(directory), backend)
        self.assertEqual(receipt["termination"], "evaluator_test_failure")
        self.assertEqual(receipt["corrective_rounds"], 0)
        self.assertFalse(any(call[0] == "feedback" for call in backend.calls))

    def test_error_incomplete_empty_patch_and_malformed_keep_frozen_meanings(self) -> None:
        cases = {
            "error": "official_evaluator_error",
            "incomplete": "official_evaluator_incomplete",
            "empty_patch": "empty_patch_failure",
            "unknown": "malformed_inconsistent_measurement",
        }
        for disposition, expected in cases.items():
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as directory:
                backend = FakeBackend([(disposition, "not_applicable", ())])
                receipt, _events = self.execute(Path(directory), backend, "baseline")
                self.assertEqual(receipt["termination"], expected)

    def test_cleanup_runs_on_subject_evaluator_and_treatment_boundary_failures(self) -> None:
        for boundary in ("ordinary", "treatment", "evaluator"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                state = Path(directory)
                backend = FakeBackend(raise_during=boundary)
                ledger = state / "ledger.jsonl"
                initialize_ledger(self.contract, ledger)
                request = self.request(state)
                request["attempt_started_at"] = "2026-08-29T00:00:00+00:00"
                append_event(ledger, "attempt_started", request)
                with self.assertRaises(RuntimeError):
                    execute_attempt_durably(
                        self.contract, request, backend, ledger, self.treatment
                    )
                self.assertFalse(Path(request["credential_copy_identity"]).exists())
                self.assertEqual(read_events(ledger)[-1]["event_type"], "credential_cleanup_verified")

    def test_receipt_requires_cleanup_and_evaluator_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            receipt, events = self.execute(state, FakeBackend(), "baseline")
            request = next(
                event["payload"] for event in events if event["event_type"] == "attempt_started"
            )
            rebuilt = reconstruct_receipt_from_events(request, events)
            self.assertEqual(rebuilt["termination"], receipt["termination"])
            without_cleanup = [
                event for event in events if event["event_type"] != "credential_cleanup_verified"
            ]
            with self.assertRaisesRegex(ExperimentConfigurationError, "cleanup"):
                reconstruct_receipt_from_events(request, without_cleanup)
            without_evaluator = [
                event for event in events if event["event_type"] != "evaluator_finished"
            ]
            with self.assertRaisesRegex(ExperimentConfigurationError, "terminal evidence"):
                reconstruct_receipt_from_events(request, without_evaluator)

    def test_completed_cell_reconstruction_prevents_repetition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _receipt, events = self.execute(state, FakeBackend(), "baseline")
            action = next_legal_action(self.contract, events)
            self.assertEqual(action["action"], "launch")
            self.assertEqual(action["cell"]["position"], 2)
            self.assertEqual(action["trajectory_attempt"], 1)
            duplicate = next(
                event["payload"] for event in events if event["event_type"] == "receipt_committed"
            )
            append_event(state / "ledger.jsonl", "receipt_committed", duplicate)
            with self.assertRaisesRegex(ExperimentConfigurationError, "duplicated|repeated"):
                next_legal_action(self.contract, read_events(state / "ledger.jsonl"))

    def test_infrastructure_and_operator_restarts_are_ledger_derived_and_separate(self) -> None:
        cell = self.contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            events = initialize_ledger(self.contract, ledger)
            request = build_launch_request(self.contract, cell, state, 1)
            request["attempt_started_at"] = "2026-08-29T00:00:00+00:00"
            append_event(ledger, "attempt_started", request)
            append_event(
                ledger,
                "operator_interruption_recorded",
                {
                    "cell_id": cell["cell_id"],
                    "trajectory_attempt": 1,
                    "category": "operator_interruption",
                },
            )
            action = next_legal_action(self.contract, read_events(ledger))
            self.assertEqual(action["action"], "authorize_operator_restart")
            self.assertEqual(action["next_attempt"], 2)
            self.assertFalse(any(event["event_type"] == "infrastructure_rerun_authorized" for event in events))

    def test_valid_negative_never_reruns_and_infrastructure_invalid_may_only_attempt_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _receipt, events = self.execute(
                state, FakeBackend([("failure", "unavailable", ())]), "baseline"
            )
            action = next_legal_action(self.contract, events)
            self.assertEqual(action["action"], "launch")
            self.assertEqual(action["cell"]["position"], 2)
            self.assertEqual(action["trajectory_attempt"], 1)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            _receipt, events = self.execute(
                state, FakeBackend([("error", "not_applicable", ())]), "baseline"
            )
            action = next_legal_action(self.contract, events)
            self.assertEqual(action["action"], "authorize_infrastructure_rerun")
            self.assertEqual(action["next_attempt"], 2)

    def test_operator_relabel_and_mid_attempt_planned_pause_fail_closed(self) -> None:
        cell = self.contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            events = initialize_ledger(self.contract, ledger)
            self.assertTrue(planned_pause_allowed(events))
            request = build_launch_request(self.contract, cell, state, 1)
            request["attempt_started_at"] = "2026-08-29T00:00:00+00:00"
            append_event(ledger, "attempt_started", request)
            self.assertFalse(planned_pause_allowed(read_events(ledger)))
            append_event(
                ledger,
                "operator_interruption_recorded",
                {
                    "cell_id": cell["cell_id"],
                    "trajectory_attempt": 1,
                    "category": "infrastructure",
                },
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "relabeled"):
                next_legal_action(self.contract, read_events(ledger))

    def test_confirmatory_reserve_remains_commitment_only(self) -> None:
        reserve = self.contract["frozen_identities"]["confirmatory_reserve"]
        self.assertFalse(reserve["remaining_ids_or_bodies_emitted"])
        encoded = json.dumps(reserve, sort_keys=True)
        self.assertNotIn("instance_id", encoded)
        self.assertNotIn("task_body", encoded)

    def test_persisted_qualification_is_canonical_complete_and_zero_live(self) -> None:
        path = (
            ROOT
            / "experiment/evidence_conditioned_final_scope_review_v0_1_execution_qualification.json"
        )
        raw = path.read_bytes()
        value = json.loads(raw)
        self.assertEqual(
            raw,
            canonical_bytes(value),
        )
        self.assertEqual(value["contract_sha256"], self.contract["contract_sha256"])
        self.assertEqual(value["qualification_check_count"], 26)
        self.assertTrue(
            all(item["status"] == "pass" for item in value["qualification_checks"].values())
        )
        self.assertEqual(value["subject_calls"], 0)
        self.assertEqual(value["evaluator_calls"], 0)
        self.assertEqual(value["experimental_observations"], 0)
        self.assertFalse(value["live_execution_invoked"])

    def test_malformed_or_corrupt_ledger_stops_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            initialize_ledger(self.contract, ledger)
            ledger.write_text(ledger.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "malformed"):
                read_events(ledger)


if __name__ == "__main__":
    unittest.main()
