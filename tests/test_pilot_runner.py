from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import append_ledger_event, build_contract, read_ledger
from engineering_scope_guard.pilot_runner import (
    EvaluatorResult,
    SubjectResult,
    build_launch_request,
    canonical_attempt_timeout,
    dry_run_receipt,
    execute_attempt,
    execution_confirmation,
    initialize_ledger,
    next_legal_action,
    normalize_receipt_timestamp,
    official_evaluator_command,
    parse_official_evaluator_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]


def subject(
    *,
    exit_code: int | None = 0,
    timed_out: bool = False,
    session_id: str | None = "session-1",
    complete_usage: bool = True,
    provider_failure: bool = False,
) -> SubjectResult:
    usage = {
        "input_tokens": 5,
        "cached_input_tokens": 2,
        "output_tokens": 3,
        "reasoning_output_tokens": 1,
        "total_tokens": 9,
    } if complete_usage else {}
    return SubjectResult(
        exit_code=exit_code,
        timed_out=timed_out,
        session_id=session_id,
        usage=usage,
        trace_reference="fixture/trace.jsonl",
        provider_infrastructure_failure=provider_failure,
    )


def evaluator(
    resolved: bool | None,
    *,
    exit_code: int | None = 0,
    timed_out: bool = False,
    infrastructure: bool = False,
    malformed: bool = False,
    failing_checks: tuple[str, ...] | None = None,
    official_disposition: str | None = None,
    feedback_status: str | None = None,
) -> EvaluatorResult:
    return EvaluatorResult(
        exit_code=exit_code,
        timed_out=timed_out,
        resolved=resolved,
        failing_checks=(
            ("test_one",) if resolved is False else ()
        ) if failing_checks is None else failing_checks,
        report_reference="fixture/report.json",
        results_reference="fixture/results.json",
        report_sha256="a" * 64,
        results_sha256="b" * 64,
        infrastructure_failure=infrastructure,
        malformed=malformed,
        official_disposition=official_disposition,
        feedback_status=feedback_status,
    )


class FakeBackend:
    def __init__(
        self,
        subjects: list[SubjectResult] | None = None,
        evaluators: list[EvaluatorResult] | None = None,
    ) -> None:
        self.subjects = subjects or [subject()]
        self.evaluators = evaluators or [evaluator(True)]
        self.subject_calls: list[tuple[tuple[str, ...] | None, str | None]] = []
        self.evaluator_rounds: list[int] = []
        self.cleaned = False

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "started_at": "2026-08-28T00:00:00+00:00",
            "ended_at": lambda: "2026-08-28T00:00:01+00:00",
        }

    def run_subject(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...] | None,
        session_id: str | None,
    ) -> SubjectResult:
        self.subject_calls.append((feedback, session_id))
        return self.subjects[len(self.subject_calls) - 1]

    def cleanup(self, prepared: dict[str, Any]) -> None:
        self.cleaned = True

    def create_prediction(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]:
        return {"path": "fixture/prediction.json", "patch_sha256": "c" * 64}

    def evaluate(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prediction: dict[str, Any],
        round_number: int,
    ) -> EvaluatorResult:
        self.evaluator_rounds.append(round_number)
        return self.evaluators[len(self.evaluator_rounds) - 1]


class RaisingBackend(FakeBackend):
    def run_subject(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...] | None,
        session_id: str | None,
    ) -> SubjectResult:
        raise OSError("synthetic process boundary failure")


class DirectTimestampBackend(FakeBackend):
    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        fixture = json.loads(
            (ROOT / "tests/fixtures/pilot/live-prepared-result-sanitized.json").read_text(
                encoding="utf-8"
            )
        )
        return fixture["prepared"]


class PilotRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = build_contract(ROOT)

    def request(self, state: Path, attempt: int = 1, cell_index: int = 0) -> dict[str, Any]:
        return build_launch_request(
            self.contract,
            self.contract["schedule"]["cells"][cell_index],
            state,
            attempt,
        )

    def tasks(self) -> dict[str, dict[str, Any]]:
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

    def test_official_evaluator_terminal_shape_fixtures(self) -> None:
        fixture = json.loads(
            (
                ROOT
                / "tests/fixtures/pilot/official-evaluator-terminal-shapes.json"
            ).read_text(encoding="utf-8")
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                parsed = parse_official_evaluator_artifacts(
                    "fixture-instance", case["report"], case["results"]
                )
                observed = asdict(parsed)
                observed["failing_checks"] = list(observed["failing_checks"])
                self.assertEqual(observed, case["expected"])

    def test_official_evaluator_artifacts_reject_contradictory_disposition(self) -> None:
        fixture = json.loads(
            (
                ROOT
                / "tests/fixtures/pilot/official-evaluator-terminal-shapes.json"
            ).read_text(encoding="utf-8")
        )
        case = copy.deepcopy(fixture["cases"][0])
        case["results"]["failure"] = 1
        case["results"]["failure_ids"] = ["fixture-instance"]
        with self.assertRaisesRegex(ExperimentConfigurationError, "not unique"):
            parse_official_evaluator_artifacts(
                "fixture-instance", case["report"], case["results"]
            )

    def test_attempt_timeout_is_contract_version_specific_and_fail_closed(self) -> None:
        legacy = {
            "timeout_seconds_per_turn": 900,
            "timeout_seconds_per_trajectory_attempt": 1800,
        }
        canonical_v3 = {
            "timeout_seconds_per_turn": 900,
            "timeout_seconds_per_attempt": 1800,
        }
        self.assertEqual(canonical_attempt_timeout("pilot-v1.0", legacy), 1800)
        self.assertEqual(canonical_attempt_timeout("pilot-v2.0", legacy), 1800)
        self.assertEqual(canonical_attempt_timeout("pilot-v3.0", canonical_v3), 1800)
        rejected = [
            legacy,
            {"timeout_seconds_per_turn": 900},
            {**canonical_v3, "timeout_seconds_per_trajectory_attempt": 1800},
            {**canonical_v3, "timeout_seconds_per_attempt": True},
            {**canonical_v3, "timeout_seconds_per_attempt": 0},
            {**canonical_v3, "timeout_seconds_per_attempt_typo": 1800},
        ]
        for trajectory in rejected:
            with self.subTest(trajectory=trajectory):
                with self.assertRaises(ExperimentConfigurationError):
                    canonical_attempt_timeout("pilot-v3.0", trajectory)
        with self.assertRaises(ExperimentConfigurationError):
            canonical_attempt_timeout("pilot-v4.0", canonical_v3)

    def test_dry_run_resolves_all_48_cells_without_state_or_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            receipt = dry_run_receipt(self.contract, ROOT, state, self.tasks())
            self.assertEqual(receipt["cells_resolved"], 48)
            self.assertEqual(receipt["codex_invocations"], 0)
            self.assertEqual(receipt["evaluator_invocations"], 0)
            self.assertFalse(receipt["ledger_modified"])
            self.assertFalse(state.exists())
            self.assertEqual(
                [cell["cell_id"] for cell in receipt["cells"]],
                [cell["cell_id"] for cell in self.contract["schedule"]["cells"]],
            )

    def test_dry_run_rejects_wrong_task_and_missing_input(self) -> None:
        tasks = self.tasks()
        first_id = self.contract["schedule"]["cells"][0]["actual_task_id"]
        tasks[first_id]["repo"] = "wrong/repository"
        with self.assertRaisesRegex(ExperimentConfigurationError, "immutable input mismatch"):
            dry_run_receipt(self.contract, ROOT, Path("/synthetic/state"), tasks)
        del tasks[first_id]
        with self.assertRaisesRegex(ExperimentConfigurationError, "unresolved"):
            dry_run_receipt(self.contract, ROOT, Path("/synthetic/state"), tasks)

    def test_wrong_model_reasoning_arm_and_task_are_rejected(self) -> None:
        request = self.request(Path("/synthetic/state"))
        request["subject"] = {**request["subject"], "reasoning_effort": "high"}
        with self.assertRaisesRegex(ExperimentConfigurationError, "subject"):
            execute_attempt(self.contract, request, FakeBackend())
        request = self.request(Path("/synthetic/state"))
        request["arm"] = "short" if request["arm"] == "baseline" else "baseline"
        with self.assertRaisesRegex(ExperimentConfigurationError, "arm"):
            execute_attempt(self.contract, request, FakeBackend())
        request = self.request(Path("/synthetic/state"))
        request["actual_task_id"] = "wrong-task"
        with self.assertRaisesRegex(ExperimentConfigurationError, "actual_task_id"):
            execute_attempt(self.contract, request, FakeBackend())

    def test_evaluator_success_constructs_complete_receipt(self) -> None:
        backend = FakeBackend(evaluators=[evaluator(True)])
        receipt = execute_attempt(self.contract, self.request(Path("/synthetic/state")), backend)
        self.assertEqual(receipt["termination"], "accepted_completed")
        self.assertTrue(backend.cleaned)
        self.assertTrue(receipt["usage_complete"])
        self.assertTrue(receipt["admissible_under_contract"])
        self.assertEqual(receipt["evaluator_result"]["rounds"], 1)
        self.assertEqual(receipt["usage"]["total_tokens"], 8)

    def test_live_direct_string_and_callable_timestamps_normalize(self) -> None:
        direct = execute_attempt(
            self.contract,
            self.request(Path("/synthetic/direct-timestamp")),
            DirectTimestampBackend(),
        )
        self.assertEqual(direct["ended_at"], "2026-08-28T00:00:01+00:00")
        self.assertEqual(
            normalize_receipt_timestamp(
                lambda: "2026-08-28T02:00:01+02:00", "ended_at"
            ),
            "2026-08-28T02:00:01+02:00",
        )
        self.assertEqual(
            normalize_receipt_timestamp("2026-08-28T00:00:01Z", "ended_at"),
            "2026-08-28T00:00:01Z",
        )

    def test_timestamp_normalization_rejects_null_malformed_and_unknown_types(self) -> None:
        for value in (None, "not-a-timestamp", "2026-08-28T00:00:01", object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ExperimentConfigurationError):
                    normalize_receipt_timestamp(value, "ended_at")

    def test_attempt_cleanup_runs_when_subject_boundary_raises(self) -> None:
        backend = RaisingBackend()
        with self.assertRaisesRegex(OSError, "synthetic process boundary failure"):
            execute_attempt(self.contract, self.request(Path("/synthetic/raising")), backend)
        self.assertTrue(backend.cleaned)

    def test_evaluator_task_failure_uses_one_same_session_corrective_round(self) -> None:
        backend = FakeBackend(
            subjects=[subject(session_id="trajectory-session"), subject(session_id="trajectory-session")],
            evaluators=[evaluator(False), evaluator(False)],
        )
        receipt = execute_attempt(self.contract, self.request(Path("/synthetic/state")), backend)
        self.assertEqual(receipt["termination"], "evaluator_test_failure")
        self.assertEqual(backend.subject_calls, [(None, None), (("test_one",), "trajectory-session")])
        self.assertEqual(backend.evaluator_rounds, [0, 1])
        self.assertEqual(receipt["usage"]["input_tokens"], 10)

    def test_corrective_round_cannot_switch_sessions(self) -> None:
        receipt = execute_attempt(
            self.contract,
            self.request(Path("/synthetic/session-drift")),
            FakeBackend(
                subjects=[subject(session_id="first"), subject(session_id="different")],
                evaluators=[evaluator(False)],
            ),
        )
        self.assertEqual(receipt["termination"], "isolation_contract_violation")
        self.assertFalse(receipt["admissible_under_contract"])

    def test_subject_failure_timeout_and_provider_failure_are_distinct(self) -> None:
        cases = (
            (subject(exit_code=1, session_id=None), "agent_subject_failure"),
            (subject(exit_code=None, timed_out=True), "trajectory_timeout"),
            (subject(exit_code=1, provider_failure=True), "provider_api_infrastructure_failure"),
        )
        for result, termination in cases:
            with self.subTest(termination=termination):
                receipt = execute_attempt(
                    self.contract,
                    self.request(Path(f"/synthetic/{termination}")),
                    FakeBackend(subjects=[result]),
                )
                self.assertEqual(receipt["termination"], termination)

    def test_evaluator_infrastructure_and_malformed_results_are_distinct(self) -> None:
        cases = (
            (evaluator(None, infrastructure=True), "local_docker_runtime_infrastructure_failure"),
            (evaluator(None, timed_out=True, malformed=True), "local_docker_runtime_infrastructure_failure"),
            (evaluator(None, malformed=True), "malformed_incomplete_measurement"),
        )
        for result, termination in cases:
            with self.subTest(termination=termination):
                receipt = execute_attempt(
                    self.contract,
                    self.request(Path(f"/synthetic/{termination}-{result.timed_out}")),
                    FakeBackend(evaluators=[result]),
                )
                self.assertEqual(receipt["termination"], termination)

    def test_frozen_runner_preserves_position_9_malformed_classification(self) -> None:
        receipt = execute_attempt(
            self.contract,
            self.request(Path("/synthetic/official-failure-no-feedback")),
            FakeBackend(
                evaluators=[
                    evaluator(
                        False,
                        failing_checks=(),
                        official_disposition="failure",
                        feedback_status="unavailable",
                    )
                ]
            ),
        )
        self.assertEqual(receipt["termination"], "malformed_incomplete_measurement")
        self.assertEqual(receipt["evaluator_result"]["official_disposition"], "failure")
        self.assertEqual(receipt["evaluator_result"]["feedback_status"], "unavailable")

    def test_nullable_evaluator_exit_metadata_is_preserved_for_timeout(self) -> None:
        receipt = execute_attempt(
            self.contract,
            self.request(Path("/synthetic/null-evaluator-exit")),
            FakeBackend(evaluators=[evaluator(None, exit_code=None, timed_out=True)]),
        )
        self.assertEqual(
            receipt["termination"], "local_docker_runtime_infrastructure_failure"
        )
        self.assertIsNone(receipt["evaluator_result"]["exit_status"])

    def test_missing_usage_stops_batch_instead_of_becoming_zero(self) -> None:
        receipt = execute_attempt(
            self.contract,
            self.request(Path("/synthetic/missing-usage")),
            FakeBackend(subjects=[subject(complete_usage=False)]),
        )
        self.assertEqual(receipt["termination"], "malformed_incomplete_measurement")
        self.assertEqual(receipt["usage"], {})
        self.assertFalse(receipt["usage_complete"])

    def test_ledger_resume_partial_duplicate_out_of_order_and_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            events = initialize_ledger(self.contract, ledger)
            self.assertEqual(next_legal_action(self.contract, events)["action"], "launch")
            first = self.request(Path(directory) / "state")
            append_ledger_event(ledger, "attempt_started", first)
            self.assertEqual(
                next_legal_action(self.contract, read_ledger(ledger))["action"],
                "resolve_partial",
            )
            receipt = execute_attempt(self.contract, first, FakeBackend())
            append_ledger_event(ledger, "attempt_finished", receipt)
            self.assertEqual(
                next_legal_action(self.contract, read_ledger(ledger))["cell"]["position"], 2
            )
            append_ledger_event(ledger, "attempt_started", first)
            with self.assertRaisesRegex(ExperimentConfigurationError, "next frozen cell"):
                next_legal_action(self.contract, read_ledger(ledger))
            lines = ledger.read_text(encoding="utf-8").splitlines()
            changed = json.loads(lines[0])
            changed["payload"]["contract_sha256"] = "0" * 64
            lines[0] = json.dumps(changed, sort_keys=True, separators=(",", ":"))
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "digest mismatch"):
                read_ledger(ledger)

    def test_infrastructure_rerun_is_same_cell_and_budget_exhaustion_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            initialize_ledger(self.contract, ledger)
            request1 = self.request(Path(directory) / "state", attempt=1)
            failed1 = execute_attempt(
                self.contract,
                request1,
                FakeBackend(subjects=[subject(exit_code=1, provider_failure=True)]),
            )
            append_ledger_event(ledger, "attempt_started", request1)
            append_ledger_event(ledger, "attempt_finished", failed1)
            action = next_legal_action(self.contract, read_ledger(ledger))
            self.assertEqual(action["action"], "authorize_infrastructure_rerun")
            append_ledger_event(
                ledger,
                "infrastructure_rerun_authorized",
                {"cell_id": failed1["cell_id"], **action["state"]},
            )
            launch = next_legal_action(self.contract, read_ledger(ledger))
            self.assertEqual((launch["cell"]["cell_id"], launch["trajectory_attempt"]),
                             (failed1["cell_id"], 2))
            request2 = self.request(Path(directory) / "state", attempt=2)
            failed2 = execute_attempt(
                self.contract,
                request2,
                FakeBackend(subjects=[subject(exit_code=1, provider_failure=True)]),
            )
            append_ledger_event(ledger, "attempt_started", request2)
            append_ledger_event(ledger, "attempt_finished", failed2)
            exhausted = next_legal_action(self.contract, read_ledger(ledger))
            self.assertEqual(exhausted["action"], "record_rerun_budget_stop")
            self.assertEqual(exhausted["receipt"]["cell_id"], failed1["cell_id"])

    def test_task_slot_and_trajectory_budgets_never_merge(self) -> None:
        slot = self.contract["final_pool"]["task_slot_replacement_budget"]
        rerun = self.contract["trajectory_infrastructure_rerun_budget"]
        self.assertEqual((slot["allowance"], slot["consumed"], slot["remaining_authority_after_finalization"]),
                         (8, 4, 0))
        self.assertEqual((rerun["allowance"], rerun["initial_consumed"]), (8, 0))

    def test_official_evaluator_prediction_invocation_is_exact(self) -> None:
        command = official_evaluator_command(
            Path("/evaluator/python"),
            Path("/dataset"),
            "rust",
            Path("/state/prediction.json"),
            Path("/state/output"),
            1,
            "repo__name-1",
        )
        self.assertEqual(command[:3], ["/evaluator/python", "-m", "evaluation.evaluation"])
        self.assertEqual(command[command.index("--patch_dir") + 1], "/state/prediction.json")
        self.assertEqual(command[command.index("--instance_ids") + 1], "repo__name-1")
        self.assertEqual(command[command.index("--workers") + 1], "1")

    def test_execute_confirmation_is_contract_bound(self) -> None:
        self.assertEqual(
            execution_confirmation(self.contract),
            "execute-pilot-v1.0:" + self.contract["contract_sha256"],
        )
        changed = copy.deepcopy(self.contract)
        changed["contract_sha256"] = "0" * 64
        self.assertNotEqual(execution_confirmation(changed), execution_confirmation(self.contract))


if __name__ == "__main__":
    unittest.main()
