from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from types import ModuleType

from engineering_scope_guard.disk_safety import DEFAULT_POLICY
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.evaluator_stable_qualification import seal_receipt, sha256_value
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v2 import (
    build_contract, build_private_pool, subject_command_identity,
)
from scripts import reasoning_effort_v2_execution_adapter as adapter
from scripts import reasoning_effort_v2_runner as durable
from tests.test_reasoning_effort_v2_runner import State, frozen, live, qualification


def _trace(*, prohibited: bool = False) -> bytes:
    events = [
        {"type": "thread.started", "thread_id": "thread-fixture"},
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call" if prohibited else "command_execution",
                "command": "rg -n fixture src",
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "cache_write_input_tokens": 5,
                "output_tokens": 20,
                "reasoning_output_tokens": 4,
            },
        },
    ]
    return b"".join(
        (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for event in events
    )


class FakeBackend:
    def __init__(
        self, *, drift: bool = False, crash: bool = False,
        prohibited: bool = False, timeout: bool = False,
        evaluator_crash: bool = False, cleanup_failure: bool = False,
        prepare_crash: bool = False, evaluator_timeout: bool = False,
    ):
        self.drift = drift
        self.crash = crash
        self.prohibited = prohibited
        self.timeout = timeout
        self.evaluator_crash = evaluator_crash
        self.cleanup_failure = cleanup_failure
        self.prepare_crash = prepare_crash
        self.evaluator_timeout = evaluator_timeout
        self.calls: list[str] = []

    def prepare(self, request: adapter.AttemptRequest) -> adapter.PreparedAttempt:
        self.calls.append("prepare")
        if self.prepare_crash:
            raise RuntimeError("injected preparation crash")
        contract = self.contract
        cell = next(item for item in contract["schedule"]["cells"] if item["cell_id"] == request.cell_id)
        attestation = {
            "runtime_identity": "drift" if self.drift else contract["runtime"]["runtime_identity"],
            "source_identity": contract["source"]["source_identity"],
            "evaluator_identity": contract["source"]["evaluator_identity"],
            "image_pool_identity": contract["source"]["image_pool_identity"],
            "codex_version": contract["runtime"]["codex_version"],
            "model": contract["runtime"]["model"],
            "reasoning_effort": cell["reasoning_effort"],
            "resolved_image": request.task["resolved_image"],
            "command_sha256": subject_command_identity(contract, request.cell_id),
            "process_identity_sha256": digest({"pid": 1234, "ownership": request.ownership_token_sha256}),
            "container_identity_sha256": digest({"resolved_image": request.task["resolved_image"]}),
            "prompt_sha256": "a" * 64,
            "credential_isolated": True,
            "fresh_worktree": True,
            "gated_before_exec": True,
            "sandbox": "workspace-write",
            "network_access": False,
            "user_config_loaded": False,
            "external_tools_enabled": False,
        }
        return adapter.PreparedAttempt(state={"gated": True}, attestation=attestation)

    def run_subject(self, request: adapter.AttemptRequest, prepared: object) -> adapter.SubjectInvocation:
        self.calls.append("run_subject")
        if self.crash:
            raise RuntimeError("injected crash after durable start")
        return adapter.SubjectInvocation(
            exit_code=None if self.timeout else 0,
            timed_out=self.timeout,
            stdout=_trace(prohibited=self.prohibited),
            stderr=b"", wall_seconds=2.0,
        )

    def evaluate(
        self, request: adapter.AttemptRequest, prepared: object,
        subject: adapter.SubjectInvocation,
    ) -> adapter.EvaluatorInvocation:
        self.calls.append("evaluate")
        if self.evaluator_crash:
            raise RuntimeError("injected evaluator crash")
        task_id = request.task["task_id"]
        return adapter.EvaluatorInvocation(
            exit_code=None if self.evaluator_timeout else 0,
            timed_out=self.evaluator_timeout,
            report={
                "instance_id": task_id,
                "resolved": True,
                "PASS_TO_PASS": {"success": ["regression"], "failure": []},
                "FAIL_TO_PASS": {"success": ["fix"], "failure": []},
            },
            results={
                "submitted": 1, "submitted_ids": [task_id],
                "success": 1, "success_ids": [task_id],
                "failure": 0, "failure_ids": [],
                "error": 0, "error_ids": [],
                "incomplete": 0, "incomplete_ids": [],
                "empty_patch": 0, "empty_patch_ids": [],
            },
            wall_seconds=3.0,
        )

    def prepare_evaluator(
        self, request: adapter.AttemptRequest, prepared: object,
        subject: adapter.SubjectInvocation,
    ) -> adapter.GatedProcess:
        process = MagicMock()
        process.pid = 4321
        return adapter.GatedProcess(
            process, 99, "d" * 64, "e" * 64, "f" * 64,
        )

    def run_evaluator(
        self, request: adapter.AttemptRequest, prepared: object,
        gated: adapter.GatedProcess,
    ) -> adapter.EvaluatorInvocation:
        return self.evaluate(request, prepared, adapter.SubjectInvocation(0, False, b"", b"", 0.0))

    def cleanup(self, request: adapter.AttemptRequest, prepared: object) -> None:
        self.calls.append("cleanup")
        if self.cleanup_failure:
            raise RuntimeError("injected cleanup failure")

    def prove_not_running(
        self, request: adapter.AttemptRequest, prepared: object, phase: str,
    ) -> dict:
        if phase == "subject":
            command = request.command_sha256
            ownership = request.ownership_token_sha256
            process = request.process_identity_sha256
        else:
            command, ownership, process = "d" * 64, "e" * 64, "f" * 64
        body = {
            "schema_name": durable.OWNERSHIP_RECEIPT_SCHEMA,
            "schema_version": 1,
            "contract_sha256": self.contract["contract_sha256"],
            "schedule_sha256": self.contract["schedule"]["schedule_sha256"],
            "cell_id": request.cell_id, "attempt": request.attempt,
            "command_sha256": command,
            "ownership_token_sha256": ownership,
            "process_identity_sha256": process,
            "container_identity_sha256": digest([]),
            "container_observations": [],
            "status": "not_running",
        }
        return {**body, "receipt_sha256": digest(body)}


class ReasoningEffortV2ExecutionAdapterTests(unittest.TestCase):
    def test_evaluator_executable_preserves_virtualenv_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "python-target"
            target.write_bytes(b"python")
            target.chmod(0o700)
            entry = root / "venv" / "bin" / "python"
            entry.parent.mkdir(parents=True)
            entry.symlink_to(target)
            self.assertEqual(adapter.evaluator_executable(entry), entry.absolute())
            self.assertNotEqual(adapter.evaluator_executable(entry), entry.resolve())

    def setUp(self) -> None:
        """Keep adapter behavior tests independent of the CI host's free disk."""

        snapshot = {
            "schema_name": "engineering-scope-guard.experiment-disk-safety",
            "schema_version": 1,
            "status": "pass",
            "available_bytes": DEFAULT_POLICY.required_free_bytes,
            "required_free_bytes": DEFAULT_POLICY.required_free_bytes,
            "minimum_free_bytes": DEFAULT_POLICY.minimum_free_bytes,
            "execution_headroom_bytes": DEFAULT_POLICY.execution_headroom_bytes,
            "maximum_retained_repository_bytes": (
                DEFAULT_POLICY.maximum_retained_repository_bytes
            ),
            "retained_repository_count": 0,
            "retained_repository_allocated_bytes": 0,
            "retained_repository_target_set_sha256": "0" * 64,
            "failures": [],
        }
        disk_safety = patch.object(
            adapter, "disk_safety_snapshot", return_value=snapshot
        )
        disk_safety.start()
        self.addCleanup(disk_safety.stop)

    def fixture(self, root: Path) -> tuple[State, FakeBackend]:
        contract, private_pool = frozen()
        _gate, seal = live(contract, private_pool)
        state = State(root, contract, private_pool, seal)
        backend = FakeBackend()
        backend.contract = contract
        return state, backend

    def execute(self, state: State, backend: FakeBackend) -> dict:
        cell = state.contract["schedule"]["cells"][0]
        return adapter.execute_one_attempt(
            backend=backend,
            contract=state.contract,
            private_pool=state.private_pool,
            live_seal=state.seal,
            execution_root=state.root,
            cell_id=cell["cell_id"],
            attempt=1,
            codex_binary="/fixture/codex",
        )

    def start_pre_subject(self, state: State) -> dict:
        cell = state.contract["schedule"]["cells"][0]
        state.disk_pass(cell)
        durable.record_attempt_started(
            state.ledger, state.checkpoint, state.contract, state.seal,
            state.private_pool, cell_id=cell["cell_id"], attempt=1,
        )
        return cell

    def test_status_derives_interrupted_phase_without_mutating_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            cell = self.start_pre_subject(state)
            before = state.ledger.read_bytes()

            status = adapter.execution_status(
                contract=state.contract, private_pool=state.private_pool,
                live_seal=state.seal, execution_root=state.root,
            )

            self.assertEqual(status["action"], "interrupted_attempt")
            self.assertEqual(status["unfinished_attempt"]["cell_id"], cell["cell_id"])
            self.assertEqual(status["unfinished_attempt"]["attempt"], 1)
            self.assertEqual(status["unfinished_attempt"]["phase"], "pre_subject")
            self.assertEqual(status["subject_starts"], 0)
            self.assertEqual(state.ledger.read_bytes(), before)

    def test_status_cli_does_not_require_or_touch_live_execution_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            arguments = SimpleNamespace(
                command="status", root=Path(directory), execution_root=state.root,
                contract=state.root / "contract.json",
                private_pool=state.root / "private-pool.json",
                live_seal=state.root / "live-seal.json",
                evaluator_root=None, dataset_root=None, evaluator_python=None,
                codex_binary=None, credential_source_codex_home=None,
                model_catalog=None, reserve_receipt=None,
            )
            with (
                patch.object(adapter, "_arguments", return_value=arguments),
                patch.object(
                    adapter, "_read_private_cli_input",
                    side_effect=[state.contract, state.private_pool, state.seal],
                ),
                patch.object(
                    adapter, "execution_status", return_value={"action": "stable_state"},
                ) as status,
                patch.object(adapter, "_resolve_private_reserve_receipt") as reserve,
                patch("builtins.print"),
            ):
                self.assertEqual(adapter.main(), 0)
            status.assert_called_once()
            reserve.assert_not_called()

    def test_terminalize_pre_subject_stops_without_consuming_subject_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            cell = self.start_pre_subject(state)

            result = adapter.terminalize_pre_subject(
                contract=state.contract, private_pool=state.private_pool,
                live_seal=state.seal, execution_root=state.root,
            )

            self.assertEqual(result["action"], "batch_stopped")
            self.assertEqual(result["classification"], "durable_evidence_incomplete")
            self.assertEqual(result["subject_status"], "subject_not_started")
            events = durable.read_ledger(state.ledger, state.contract)
            self.assertNotIn(
                "subject_invocation_started", [event["event_type"] for event in events]
            )
            receipt = json.loads(
                (state.receipts / cell["cell_id"] / "attempt-1.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(receipt["subject_invocation_started"])
            self.assertEqual(receipt["classification"], "durable_evidence_incomplete")
            self.assertEqual(
                receipt["evaluator_artifact"]["anomaly_codes"], ["subject_not_started"]
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "no unfinished"):
                adapter.terminalize_pre_subject(
                    contract=state.contract, private_pool=state.private_pool,
                    live_seal=state.seal, execution_root=state.root,
                )

    def test_reconcile_proven_dead_never_invents_missing_death_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            cell = self.start_pre_subject(state)
            durable.record_subject_invocation_started(
                state.ledger, state.checkpoint, state.contract, state.seal,
                state.private_pool, cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(state.contract, cell["cell_id"]),
                ownership_token_sha256="a" * 64,
                process_identity_sha256="b" * 64,
            )

            with self.assertRaisesRegex(ExperimentConfigurationError, "cannot be inferred"):
                adapter.reconcile_proven_dead(
                    contract=state.contract, private_pool=state.private_pool,
                    live_seal=state.seal, execution_root=state.root,
                )

            events = durable.read_ledger(state.ledger, state.contract)
            self.assertNotIn("attempt_finished", [event["event_type"] for event in events])
            self.assertFalse(list(state.receipts.rglob("*.json")))

    def test_reconcile_proven_dead_derives_subject_identity_and_receipt_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            cell = self.start_pre_subject(state)
            durable.record_subject_invocation_started(
                state.ledger, state.checkpoint, state.contract, state.seal,
                state.private_pool, cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(state.contract, cell["cell_id"]),
                ownership_token_sha256="a" * 64,
                process_identity_sha256="b" * 64,
            )
            expected = (
                state.root / "artifacts" / cell["cell_id"] / "attempt-1"
                / "subject-ownership-not-running.json"
            )
            adapter._write_artifact(expected, {"proof_fixture": True})

            with patch.object(
                adapter,
                "reconcile_proven_dead_attempt",
                return_value={
                    "action": "batch_stopped",
                    "classification": "durable_evidence_incomplete",
                },
            ) as reconcile:
                result = adapter.reconcile_proven_dead(
                    contract=state.contract, private_pool=state.private_pool,
                    live_seal=state.seal, execution_root=state.root,
                )

            self.assertEqual(result["phase"], "subject")
            reconcile.assert_called_once_with(
                contract=state.contract, private_pool=state.private_pool,
                live_seal=state.seal, execution_root=state.root.resolve(),
                cell_id=cell["cell_id"], attempt=1,
                ownership_receipt_path=expected.resolve(),
            )

    def test_accepted_attempt_is_single_gated_launch_and_durable_artifact_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            result = self.execute(state, backend)
            self.assertEqual(result["receipt"]["classification"], "accepted_completed")
            self.assertEqual(result["transition"]["action"], "cell_completed")
            self.assertEqual(backend.calls, ["prepare", "run_subject", "evaluate", "cleanup"])
            events = durable.read_ledger(state.ledger, state.contract)
            event_types = [event["event_type"] for event in events]
            self.assertEqual(event_types.count("subject_invocation_started"), 1)
            self.assertLess(
                event_types.index("subject_invocation_started"),
                event_types.index("attempt_finished"),
            )
            raw = state.root / "artifacts" / state.contract["schedule"]["cells"][0]["cell_id"] / "attempt-1" / "raw"
            self.assertTrue((raw / "codex.jsonl").is_file())
            self.assertTrue((raw / "evaluator-results.json").is_file())
            self.assertTrue((state.root / "runtime-revalidation.json").is_file())
            self.assertTrue((state.root / "source-revalidation.json").is_file())

    def test_real_gated_helper_executes_only_after_explicit_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            command = (
                sys.executable,
                "-c",
                "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data.upper())",
            )
            with patch.object(adapter, "_process_start_time", return_value="fixture-start"):
                gated = adapter.prepare_gated_process(
                    command,
                    cwd=Path(directory),
                    env={"PATH": str(Path(sys.executable).parent)},
                    command_sha256=digest(list(command)),
                    ownership_token_sha256="a" * 64,
                )
                self.assertIsNone(gated.process.poll())
                result = adapter.run_gated_process(
                    gated, stdin=b"fixture", timeout_seconds=5
                )
            self.assertFalse(result.timed_out)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, b"FIXTURE")

    def test_prelaunch_identity_drift_terminalizes_without_subject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.drift = True
            result = self.execute(state, backend)
            self.assertEqual(result["receipt"]["classification"], "runtime_or_source_identity_drift")
            self.assertEqual(result["transition"]["action"], "batch_stopped")
            self.assertNotIn("run_subject", backend.calls)
            self.assertEqual(backend.calls[-1], "cleanup")

    def test_unclassified_preparation_crash_terminalizes_fail_closed(self) -> None:
        """A post-attempt-start preparation error cannot leave an unrecoverable orphan."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.prepare_crash = True
            with self.assertRaisesRegex(RuntimeError, "preparation crash"):
                self.execute(state, backend)
            events = durable.read_ledger(state.ledger, state.contract)
            kinds = [event["event_type"] for event in events]
            self.assertEqual(kinds.count("attempt_started"), 1)
            self.assertNotIn("subject_invocation_started", kinds)
            self.assertIn(
                "batch_stopped",
                kinds,
                "unexpected preparation failures must terminalize the durable attempt",
            )
            with self.assertRaises(ExperimentConfigurationError):
                self.execute(state, backend)
            self.assertEqual(backend.calls.count("prepare"), 1)

    def test_post_start_crash_never_fabricates_receipt_or_duplicates_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.crash = True
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                self.execute(state, backend)
            events = durable.read_ledger(state.ledger, state.contract)
            self.assertEqual(
                [event["event_type"] for event in events].count("subject_invocation_started"), 1
            )
            with self.assertRaises(ExperimentConfigurationError):
                self.execute(state, backend)
            receipt_paths = list(state.receipts.rglob("attempt-1.json"))
            self.assertEqual(len(receipt_paths), 1)
            self.assertEqual(
                json.loads(receipt_paths[0].read_text(encoding="utf-8"))["classification"],
                "durable_evidence_incomplete",
            )
            self.assertEqual(backend.calls.count("run_subject"), 1)

    def test_prohibited_tool_trace_stops_without_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.prohibited = True
            result = self.execute(state, backend)
            self.assertEqual(result["receipt"]["classification"], "malformed_inconsistent_measurement")
            self.assertEqual(result["transition"]["action"], "batch_stopped")
            self.assertNotIn("evaluate", backend.calls)

    def test_timeout_consumes_one_start_and_never_runs_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.timeout = True
            result = self.execute(state, backend)
            self.assertEqual(result["receipt"]["classification"], "trajectory_timeout")
            self.assertEqual(result["transition"]["action"], "cell_completed")
            self.assertNotIn("evaluate", backend.calls)
            events = durable.read_ledger(state.ledger, state.contract)
            self.assertEqual(
                [event["event_type"] for event in events].count("subject_invocation_started"), 1
            )

    def test_evaluator_timeout_retains_started_incomplete_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.evaluator_timeout = True
            result = self.execute(state, backend)
            self.assertEqual(
                result["receipt"]["classification"],
                "local_docker_runtime_infrastructure_failure",
            )
            self.assertTrue(result["receipt"]["evaluator_artifact"]["invocation_started"])
            self.assertEqual(
                result["receipt"]["evaluator_artifact"]["disposition"], "incomplete"
            )

    def test_attempt_2_retryable_exhaustion_is_replay_safe_terminal_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.evaluator_timeout = True
            first = self.execute(state, backend)
            self.assertEqual(first["transition"]["action"], "await_attempt_2_authorization")
            authorization = durable.advance_outcome_blind_attempt_authorization(
                state.ledger, state.checkpoint, state.contract,
                state.seal, state.private_pool,
            )
            self.assertEqual(authorization["event_type"], "attempt_2_authorized")
            cell = state.contract["schedule"]["cells"][0]
            second_backend = FakeBackend(evaluator_timeout=True)
            second_backend.contract = state.contract
            second = adapter.execute_one_attempt(
                backend=second_backend, contract=state.contract,
                private_pool=state.private_pool, live_seal=state.seal,
                execution_root=state.root, cell_id=cell["cell_id"], attempt=2,
                codex_binary="/fixture/codex",
            )
            self.assertEqual(
                second["transition"]["action"],
                "batch_stopped_attempt_2_exhausted",
            )
            replay = durable.replay_attempt_state(
                state.contract,
                durable._semantic(durable.read_ledger(state.ledger, state.contract)),
            )
            self.assertEqual(
                replay["batch_stop_classification"], "durable_evidence_incomplete"
            )
            with self.assertRaises(ExperimentConfigurationError):
                adapter.execute_one_attempt(
                    backend=FakeBackend(), contract=state.contract,
                    private_pool=state.private_pool, live_seal=state.seal,
                    execution_root=state.root, cell_id=cell["cell_id"], attempt=2,
                    codex_binary="/fixture/codex",
                )

    def test_capacity_stop_occurs_before_attempt_or_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            backend = MagicMock()
            cell = state.contract["schedule"]["cells"][0]
            with (
                patch.object(
                    durable, "reserve_attempt_capacity_or_stop", return_value=False,
                ) as reserve,
                patch.object(durable, "record_attempt_started") as record_attempt,
            ):
                result = adapter.execute_one_attempt(
                    backend=backend, contract=state.contract,
                    private_pool=state.private_pool, live_seal=state.seal,
                    execution_root=state.root, cell_id=cell["cell_id"], attempt=1,
                    codex_binary="/fixture/codex",
                )
            self.assertEqual(
                result["transition"]["action"], "batch_stopped_capacity_exhausted"
            )
            reserve.assert_called_once()
            record_attempt.assert_not_called()
            backend.prepare.assert_not_called()

    def test_disk_safety_failure_is_durable_before_capacity_or_preparation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            backend = MagicMock()
            cell = state.contract["schedule"]["cells"][0]
            snapshot = {
                "schema_name": "engineering-scope-guard.experiment-disk-safety",
                "schema_version": 1,
                "status": "fail",
                "available_bytes": 1,
                "required_free_bytes": 2,
                "minimum_free_bytes": 1,
                "execution_headroom_bytes": 1,
                "maximum_retained_repository_bytes": 3,
                "retained_repository_count": 0,
                "retained_repository_allocated_bytes": 0,
                "retained_repository_target_set_sha256": "0" * 64,
                "failures": ["free_space_below_execution_reserve"],
            }
            with (
                patch.object(adapter, "disk_safety_snapshot", return_value=snapshot),
                patch.object(durable, "reserve_attempt_capacity_or_stop") as reserve,
                patch.object(durable, "record_attempt_started") as record_attempt,
            ):
                result = adapter.execute_one_attempt(
                    backend=backend, contract=state.contract,
                    private_pool=state.private_pool, live_seal=state.seal,
                    execution_root=state.root, cell_id=cell["cell_id"], attempt=1,
                    codex_binary="/fixture/codex",
                )
            self.assertEqual(
                result["transition"]["action"], "batch_stopped_disk_safety_failed"
            )
            reserve.assert_not_called()
            record_attempt.assert_not_called()
            backend.prepare.assert_not_called()
            self.assertEqual(
                [event["event_type"] for event in durable.read_ledger(
                    state.ledger, state.contract
                )],
                ["disk_safety_checked"],
            )

    def test_cell_1_requires_a_concrete_local_backend(self) -> None:
        """The public adapter must be executable without an invented host implementation."""

        backend = getattr(adapter, "LocalExecutionBackend", None)
        self.assertTrue(
            isinstance(backend, type),
            "cell 1 is blocked until a concrete LocalExecutionBackend exists",
        )
        self.assertTrue(
            callable(getattr(adapter, "build_local_execution_backend", None)),
            "cell 1 needs a project-wired backend factory, not injected callbacks",
        )
        self.assertTrue(
            callable(getattr(adapter, "main", None)),
            "execute-next must be reachable through a fail-closed CLI entrypoint",
        )

    def test_shared_reserve_receipt_is_private_local_and_source_hash_bound(self) -> None:
        qualified = qualification()
        reserve = {"schema": "fixture-reserve", "selection": {"selected": []}}
        qualified["source"]["reserve_receipt_sha256"] = sha256_value(reserve)
        seal_receipt(qualified)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / ".local"
            shared = local / "autonomous-sprint"
            shared.mkdir(parents=True, mode=0o700)
            local.chmod(0o700)
            shared.chmod(0o700)
            receipt = shared / "current-runtime-reserve.json"
            receipt.write_text(json.dumps(reserve) + "\n", encoding="utf-8")
            receipt.chmod(0o600)

            resolved = adapter._resolve_private_reserve_receipt(
                root, Path(".local/autonomous-sprint/current-runtime-reserve.json"),
                qualified,
            )
            self.assertEqual(resolved, receipt.resolve())
            self.assertFalse(resolved.is_relative_to(local / "execution"))

            changed = dict(reserve)
            changed["drift"] = True
            receipt.write_text(json.dumps(changed) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "frozen qualification"):
                adapter._resolve_private_reserve_receipt(root, receipt, qualified)

    def test_shared_reserve_receipt_rejects_unsafe_path_or_mode(self) -> None:
        qualified = qualification()
        reserve = {"schema": "fixture-reserve"}
        qualified["source"]["reserve_receipt_sha256"] = sha256_value(reserve)
        seal_receipt(qualified)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / ".local"
            local.mkdir(mode=0o700)
            receipt = local / "reserve.json"
            receipt.write_text(json.dumps(reserve) + "\n", encoding="utf-8")
            receipt.chmod(0o644)
            with self.assertRaisesRegex(ExperimentConfigurationError, "mode 0600"):
                adapter._resolve_private_reserve_receipt(root, receipt, qualified)

            outside = root / "reserve.json"
            outside.write_text(json.dumps(reserve) + "\n", encoding="utf-8")
            outside.chmod(0o600)
            with self.assertRaisesRegex(ExperimentConfigurationError, "outside"):
                adapter._resolve_private_reserve_receipt(root, outside, qualified)

            receipt.chmod(0o600)
            alias = local / "reserve-link.json"
            alias.symlink_to(receipt)
            with self.assertRaisesRegex(ExperimentConfigurationError, "symlink"):
                adapter._resolve_private_reserve_receipt(root, alias, qualified)

    def test_execute_next_uses_attempt_2_after_alternate_activation(self) -> None:
        """Alternate replacement is a second attempt even without retry authorization."""

        contract, private_pool = frozen()
        _gate, seal = live(contract, private_pool)
        cell_id = contract["schedule"]["cells"][0]["cell_id"]
        events = [
            {
                "event_type": "alternate_activated",
                "payload": {"cell_id": cell_id},
            }
        ]
        args = MagicMock(
            contract=Path("contract.json"), private_pool=Path("pool.json"),
            live_seal=Path("seal.json"), execution_root=Path("execution"),
            root=Path("."), evaluator_root=Path("evaluator"),
            dataset_root=Path("dataset"), evaluator_python=Path("python"),
            codex_binary="codex", credential_source_codex_home=Path("codex-home"),
            model_catalog=Path("models.json"), reserve_receipt=Path("reserve.json"),
        )
        replay = {
            "next_cell_id": cell_id,
            "batch_stop_classification": None,
        }
        with (
            patch.object(adapter, "_arguments", return_value=args),
            patch.object(durable, "_execution_storage_root", return_value=Path("execution")),
            patch.object(
                adapter, "_read_private_cli_input",
                side_effect=[contract, private_pool, seal],
            ),
            patch.object(
                adapter, "_resolve_private_reserve_receipt",
                return_value=Path("/resolved/private-reserve.json"),
            ),
            patch.object(
                adapter, "_advance_automatic_control_transitions",
                return_value={"authorization": None, "audit": None, "state": replay},
            ),
            patch.object(durable, "read_ledger", return_value=events),
            patch.object(durable, "replay_attempt_state", return_value=replay),
            patch.object(
                adapter, "build_local_execution_backend", return_value=MagicMock()
            ) as backend_factory,
            patch.object(adapter.shutil, "which", return_value=sys.executable),
            patch.object(
                adapter,
                "execute_one_attempt",
                return_value={"transition": {"action": "fixture"}},
            ) as execute,
            patch("builtins.print"),
        ):
            self.assertEqual(adapter.main(), 0)
        self.assertEqual(
            execute.call_args.kwargs["attempt"],
            2,
            "alternate_activated must select attempt 2, not duplicate attempt 1",
        )
        self.assertEqual(
            backend_factory.call_args.kwargs["reserve_receipt"],
            Path("/resolved/private-reserve.json"),
        )

    def test_automatic_control_transition_runs_stage_1_before_cell_5(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _backend = self.fixture(Path(directory))
            for cell in state.contract["schedule"]["cells"][:4]:
                state.complete(cell)
            state.identity_receipts()
            automatic = adapter._advance_automatic_control_transitions(
                state.root, state.contract, state.private_pool, state.seal
            )
            self.assertEqual(automatic["audit"]["status"], "pass")
            self.assertEqual(automatic["state"]["completed_cells"], 4)
            self.assertEqual(automatic["state"]["stage_1_audit_status"], "pass")
            events = durable.read_ledger(state.ledger, state.contract)
            self.assertEqual(
                [event["event_type"] for event in events].count("stage_1_audit_passed"),
                1,
            )

    def test_evaluator_has_a_durable_gated_start_before_release(self) -> None:
        """Evaluator work needs the same durable ownership boundary as subject work."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            result = self.execute(state, backend)
            events = durable.read_ledger(state.ledger, state.contract)
            kinds = [event["event_type"] for event in events]
            self.assertEqual(kinds.count("evaluator_invocation_started"), 1)
            self.assertLess(
                kinds.index("evaluator_invocation_started"),
                kinds.index("attempt_finished"),
            )
            evaluator_start = next(
                event for event in events
                if event["event_type"] == "evaluator_invocation_started"
            )
            self.assertEqual(
                evaluator_start["payload"]["cell_id"], result["receipt"]["cell_id"]
            )

    def test_evaluator_crash_reconciles_proven_dead_without_duplicate(self) -> None:
        """A crash after evaluator release cannot rerun either subject or evaluator."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.evaluator_crash = True
            with self.assertRaisesRegex(RuntimeError, "evaluator crash"):
                self.execute(state, backend)
            events = durable.read_ledger(state.ledger, state.contract)
            self.assertEqual(
                [event["event_type"] for event in events].count(
                    "evaluator_invocation_started"
                ),
                1,
            )
            reconcile = getattr(adapter, "reconcile_proven_dead_evaluator", None)
            self.assertTrue(
                callable(reconcile),
                "adapter must expose evaluator-specific proven-dead reconciliation",
            )
            start = next(
                event["payload"] for event in events
                if event["event_type"] == "evaluator_invocation_started"
            )
            ownership_path = state.root / "evaluator-ownership.json"
            adapter._write_artifact(
                ownership_path,
                {
                    "schema_name": durable.OWNERSHIP_RECEIPT_SCHEMA,
                    "schema_version": durable.SCHEMA_VERSION,
                    "contract_sha256": state.contract["contract_sha256"],
                    "schedule_sha256": state.contract["schedule"]["schedule_sha256"],
                    "cell_id": start["cell_id"],
                    "attempt": start["attempt"],
                    "command_sha256": start["evaluator_command_sha256"],
                    "ownership_token_sha256": start["ownership_token_sha256"],
                    "process_identity_sha256": start["process_identity_sha256"],
                    "container_identity_sha256": digest([]),
                    "container_observations": [],
                    "status": "not_running",
                },
            )
            reconciled = reconcile(
                contract=state.contract,
                private_pool=state.private_pool,
                live_seal=state.seal,
                execution_root=state.root,
                cell_id=start["cell_id"],
                attempt=start["attempt"],
                ownership_receipt_path=ownership_path,
            )
            self.assertIn(reconciled["action"], {"batch_stopped", "already_reconciled"})
            self.assertEqual(
                reconciled["classification"], "durable_evidence_incomplete"
            )
            with self.assertRaises(ExperimentConfigurationError):
                self.execute(state, backend)
            self.assertEqual(backend.calls.count("evaluate"), 1)

    def test_raw_subject_and_evaluator_bytes_are_terminally_bound(self) -> None:
        """Re-hashing derived JSON cannot hide mutation of authoritative raw evidence."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            result = self.execute(state, backend)
            raw = (
                state.root / "artifacts" / result["receipt"]["cell_id"]
                / "attempt-1" / "raw"
            )
            trace = raw / "codex.jsonl"
            trace.write_bytes(trace.read_bytes() + b"{}\n")
            trace.chmod(0o600)
            with self.assertRaises(ExperimentConfigurationError):
                durable.validate_terminal_receipt_artifacts(
                    state.contract,
                    state.private_pool,
                    state.ledger,
                    state.root,
                    result["receipt"],
                )

    def test_stage_1_reopens_raw_evidence_instead_of_trusting_derived_receipts(self) -> None:
        """Stage 1 must fail when a retained cell's raw trace changes after export."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            for cell in state.contract["schedule"]["cells"][:4]:
                adapter.execute_one_attempt(
                    backend=backend,
                    contract=state.contract,
                    private_pool=state.private_pool,
                    live_seal=state.seal,
                    execution_root=state.root,
                    cell_id=cell["cell_id"],
                    attempt=1,
                    codex_binary="/fixture/codex",
                )
            first_cell = state.contract["schedule"]["cells"][0]["cell_id"]
            trace = (
                state.root / "artifacts" / first_cell / "attempt-1" / "raw"
                / "codex.jsonl"
            )
            trace.write_bytes(trace.read_bytes() + b"{}\n")
            trace.chmod(0o600)
            audit = durable.record_stage_1_audit(
                state.ledger,
                state.checkpoint,
                state.receipts,
                state.contract,
                state.private_pool,
                state.seal,
                execution_root=state.root,
                runtime_revalidation_receipt_path=(
                    state.root / "runtime-revalidation.json"
                ),
                source_revalidation_receipt_path=(
                    state.root / "source-revalidation.json"
                ),
            )
            self.assertEqual(audit["status"], "fail")
            self.assertFalse(audit["criteria"]["receipt_hashes_valid"])

    def test_cleanup_failure_stops_before_cell_completion(self) -> None:
        """Credential cleanup must be proven before a scientific cell is committed."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            backend.cleanup_failure = True
            with self.assertRaisesRegex(RuntimeError, "cleanup failure"):
                self.execute(state, backend)
            events = durable.read_ledger(state.ledger, state.contract)
            kinds = [event["event_type"] for event in events]
            self.assertNotIn("cell_completed", kinds)
            self.assertIn("batch_stopped", kinds)

    def test_cleanup_receipt_is_terminally_bound_and_revalidated(self) -> None:
        """Deleting cleanup proof must invalidate the already-exported terminal receipt."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            result = self.execute(state, backend)
            cleanup = (
                state.root / "artifacts" / result["receipt"]["cell_id"]
                / "attempt-1" / "cleanup.json"
            )
            self.assertTrue(cleanup.is_file())
            cleanup.unlink()
            with self.assertRaises(ExperimentConfigurationError):
                durable.validate_terminal_receipt_artifacts(
                    state.contract,
                    state.private_pool,
                    state.ledger,
                    state.root,
                    result["receipt"],
                )

    def test_gated_abort_and_exception_paths_kill_and_wait(self) -> None:
        """No unreleased or interrupted gated child may survive its adapter call."""

        abort = getattr(adapter, "abort_gated_process", None)
        self.assertTrue(callable(abort), "adapter must expose gated-process abort")
        process = MagicMock()
        process.pid = 4321
        process.poll.return_value = None
        identity = {
            "pid": 4321,
            "start_time": "fixture-start",
            "launcher_executable": {},
            "target_executable": {"resolved_path": "/fixture/codex"},
            "command_sha256": "a" * 64,
            "ownership_token_sha256": "b" * 64,
            "nonce_sha256": "d" * 64,
            "gated_before_exec": True,
        }
        gated = adapter.GatedProcess(
            process, -1, "a" * 64, "b" * 64, digest(identity), identity, True
        )
        with (
            patch.object(adapter, "verify_process_identity", return_value=True),
            patch.object(os, "killpg") as killpg,
        ):
            abort(gated)
        killpg.assert_called()
        process.communicate.assert_called()

    def test_gated_identity_observer_failure_reaps_the_spawned_child(self) -> None:
        """Failure after Popen but before attestation cannot leak a waiting child."""

        process = MagicMock()
        process.pid = 4321
        process.poll.return_value = None
        with (
            patch.object(adapter.subprocess, "Popen", return_value=process),
            patch.object(adapter.shutil, "which", return_value="/fixture/codex"),
            patch.object(
                adapter, "_process_start_time", side_effect=PermissionError("blocked")
            ),
            patch.object(os, "pipe", return_value=(50, 51)),
            patch.object(os, "close"),
            patch.object(os, "killpg") as killpg,
        ):
            with self.assertRaises(PermissionError):
                adapter.prepare_gated_process(
                    ("/fixture/codex", "exec"),
                    cwd=Path("/fixture"),
                    env={},
                    command_sha256="a" * 64,
                    ownership_token_sha256="b" * 64,
                )
        killpg.assert_called()
        process.communicate.assert_called()

    def test_process_identity_rejects_pid_reuse(self) -> None:
        """PID alone is not proof that the originally owned process is alive or dead."""

        identity = {
            "pid": 4321,
            "start_time": "start-a",
            "launcher_executable": {},
            "target_executable": {"resolved_path": "/fixture/codex"},
            "command_sha256": "a" * 64,
            "ownership_token_sha256": "b" * 64,
            "nonce_sha256": "c" * 64,
            "gated_before_exec": True,
        }
        process = MagicMock()
        process.pid = 4321
        process.poll.return_value = None
        gated = adapter.GatedProcess(
            process, -1, "a" * 64, "b" * 64, digest(identity), identity
        )
        changed = {**identity, "start_time": "start-b"}
        with patch.object(adapter, "_process_identity", return_value=changed):
            self.assertFalse(
                adapter.verify_process_identity(gated),
                "a reused PID must never match the frozen process identity",
            )

    def test_raw_evidence_rejects_symlinks_modes_and_unsafe_ancestors(self) -> None:
        """Every private evidence path must enforce containment and 0700/0600 modes."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ".local" / "execution"
            durable.initialize_execution_storage(root)
            unsafe = root / "artifacts" / "cell" / "attempt-1" / "raw"
            unsafe.mkdir(parents=True)
            (root / "artifacts").chmod(0o755)
            with self.assertRaises(ExperimentConfigurationError):
                adapter._write_private_bytes(unsafe / "trace.jsonl", b"safe\n")

            (root / "artifacts").chmod(0o700)
            target = root / "target.jsonl"
            target.write_bytes(b"safe\n")
            target.chmod(0o600)
            symlink = unsafe / "trace.jsonl"
            symlink.symlink_to(target)
            with self.assertRaises(ExperimentConfigurationError):
                adapter._write_private_bytes(symlink, b"safe\n")

    def test_public_durable_surfaces_do_not_leak_private_task_values(self) -> None:
        """Ledger and terminal receipt expose commitments, never private pool identities."""

        with tempfile.TemporaryDirectory() as directory:
            state, backend = self.fixture(Path(directory))
            result = self.execute(state, backend)
            public_text = json.dumps(
                {
                    "ledger": durable.read_ledger(state.ledger, state.contract),
                    "receipt": result["receipt"],
                },
                sort_keys=True,
            )
            for task in [
                *state.private_pool["primaries"], *state.private_pool["alternates"]
            ]:
                self.assertNotIn(task["task_id"], public_text)
                self.assertNotIn(task["repository"], public_text)
                self.assertNotIn(task["resolved_image"], public_text)

    def test_evaluator_container_capture_rejects_unrelated_same_image(self) -> None:
        backend = object.__new__(adapter.LocalExecutionBackend)
        request = MagicMock()
        request.task = {"task_id": "owner-task", "resolved_image": "image@sha256:fixture"}
        request.ownership_token_sha256 = "a" * 64
        state = MagicMock()
        state.evaluator_containers_before = set()
        state.evaluator_docker_event_since_ns = 1
        state.evaluator_ownership_marker = "b" * 64
        state.evaluator = MagicMock(ownership_token_sha256="b" * 64)
        with (
            patch.object(adapter, "_docker_lifecycle_events", return_value=[{
                "action": "create", "container_id": "foreign", "time_nano": 2,
                "image": "image", "name": "sweb-owner-task-concurrent",
                "ownership_marker_sha256": None,
            }]),
            patch.object(adapter, "_docker_container_ids", return_value={"foreign"}),
            patch.object(
                adapter, "_docker_observations",
                return_value=[],
            ),
        ):
            with self.assertRaisesRegex(ExperimentConfigurationError, "lacks the invocation"):
                backend._capture_evaluator_containers(request, state)

    def test_evaluator_container_capture_accepts_exact_invocation_label(self) -> None:
        backend = object.__new__(adapter.LocalExecutionBackend)
        request = MagicMock()
        request.task = {"task_id": "owner-task", "resolved_image": "image@sha256:fixture"}
        request.ownership_token_sha256 = "a" * 64
        state = MagicMock()
        state.evaluator_containers_before = {"old"}
        state.evaluator_docker_event_since_ns = 1
        state.evaluator_ownership_marker = "b" * 64
        state.evaluator = MagicMock(ownership_token_sha256="b" * 64)
        with (
            patch.object(adapter, "_docker_lifecycle_events", return_value=[{
                "action": "create", "container_id": "owned", "time_nano": 2,
                "image": "image", "name": "arbitrary",
                "ownership_marker_sha256": "b" * 64,
            }]),
            patch.object(adapter, "_docker_container_ids", return_value={"old", "owned"}),
            patch.object(
                adapter, "_docker_observations",
                return_value=[{
                    "id": "owned", "name": "/arbitrary", "image": "image",
                    "labels": {"engineering-scope-guard.ownership": "b" * 64},
                    "running": False,
                }],
            ),
        ):
            self.assertEqual(backend._capture_evaluator_containers(request, state), {"owned"})

    def test_preexisting_unmarked_same_image_container_is_not_owned_or_stopped(self) -> None:
        backend = object.__new__(adapter.LocalExecutionBackend)
        request = MagicMock()
        request.task = {"resolved_image": "image@sha256:fixture"}
        state = MagicMock()
        state.evaluator_containers_before = {"foreign"}
        state.evaluator_docker_event_since_ns = 1
        state.evaluator_ownership_marker = "b" * 64
        with (
            patch.object(adapter, "_docker_lifecycle_events", return_value=[]),
            patch.object(adapter, "_docker_container_ids", return_value={"foreign"}),
            patch.object(adapter, "_docker_observations", return_value=[]) as inspect_owned,
        ):
            self.assertEqual(backend._capture_evaluator_containers(request, state), set())
        inspect_owned.assert_called_once_with(set())

    def test_sdk_owned_container_created_and_destroyed_before_capture_is_retained(self) -> None:
        backend = object.__new__(adapter.LocalExecutionBackend)
        request = MagicMock()
        request.task = {"resolved_image": "image@sha256:fixture"}
        state = MagicMock()
        state.evaluator_containers_before = {"baseline"}
        state.evaluator_docker_event_since_ns = 1
        state.evaluator_ownership_marker = "b" * 64
        lifecycle = [
            {
                "action": "create", "container_id": "removed", "time_nano": 2,
                "image": request.task["resolved_image"], "name": "sdk-runtime",
                "ownership_marker_sha256": "b" * 64,
            },
            {
                "action": "destroy", "container_id": "removed", "time_nano": 3,
                "image": request.task["resolved_image"], "name": "sdk-runtime",
                "ownership_marker_sha256": "b" * 64,
            },
        ]
        with (
            patch.object(adapter, "_docker_lifecycle_events", return_value=lifecycle),
            patch.object(adapter, "_docker_container_ids", return_value={"baseline"}),
            patch.object(adapter, "_docker_observations", return_value=[]),
        ):
            self.assertEqual(backend._capture_evaluator_containers(request, state), {"removed"})
            terminal = adapter._terminal_evaluator_container_observations(
                request.task["resolved_image"], {"removed"}, lifecycle,
            )
        self.assertEqual(terminal[0]["id"], "removed")
        self.assertTrue(terminal[0]["removed"])
        self.assertFalse(terminal[0]["running"])

    def test_sdk_owned_lifecycle_rejects_destroy_with_forged_marker(self) -> None:
        backend = object.__new__(adapter.LocalExecutionBackend)
        request = MagicMock()
        request.task = {"resolved_image": "image@sha256:fixture"}
        state = MagicMock()
        state.evaluator_containers_before = set()
        state.evaluator_docker_event_since_ns = 1
        state.evaluator_ownership_marker = "b" * 64
        with patch.object(adapter, "_docker_lifecycle_events", return_value=[
            {
                "action": "create", "container_id": "owned", "time_nano": 2,
                "image": request.task["resolved_image"], "name": "sdk-runtime",
                "ownership_marker_sha256": "b" * 64,
            },
            {
                "action": "destroy", "container_id": "owned", "time_nano": 3,
                "image": request.task["resolved_image"], "name": "sdk-runtime",
                "ownership_marker_sha256": "c" * 64,
            },
        ]):
            with self.assertRaisesRegex(ExperimentConfigurationError, "label or cardinality"):
                backend._capture_evaluator_containers(request, state)

    def test_attempt_scoped_sitecustomize_labels_sdk_run_and_create(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ".local" / "execution"
            durable.initialize_execution_storage(root)
            injection_dir = root / "attempts" / "cell" / "attempt-1" / "injection"
            marker = "b" * 64
            path, source_sha = adapter._write_evaluator_docker_sdk_injection(
                injection_dir, ownership_marker=marker,
            )

            class ContainerCollection:
                def run(self, *_args: object, **kwargs: object) -> dict:
                    return kwargs

                def create(self, *_args: object, **kwargs: object) -> dict:
                    return kwargs

            class ImageCollection:
                def prune(self, **_kwargs: object) -> dict:
                    raise AssertionError("global prune implementation must never run")

            docker = ModuleType("docker")
            models = ModuleType("docker.models")
            containers = ModuleType("docker.models.containers")
            images = ModuleType("docker.models.images")
            containers.ContainerCollection = ContainerCollection
            images.ImageCollection = ImageCollection
            with patch.dict(
                sys.modules,
                {
                    "docker": docker,
                    "docker.models": models,
                    "docker.models.containers": containers,
                    "docker.models.images": images,
                },
            ):
                exec(compile(path.read_bytes(), str(path), "exec"), {})
            collection = ContainerCollection()
            self.assertEqual(
                collection.run("image")["labels"]["engineering-scope-guard.ownership"],
                marker,
            )
            self.assertEqual(
                collection.create("image", labels={"existing": "yes"})["labels"],
                {"existing": "yes", "engineering-scope-guard.ownership": marker},
            )
            self.assertEqual(adapter.hashlib.sha256(path.read_bytes()).hexdigest(), source_sha)
            self.assertEqual(
                ImageCollection().prune(filters={"dangling": True}),
                {"ImagesDeleted": [], "SpaceReclaimed": 0},
            )
            with self.assertRaisesRegex(RuntimeError, "unscoped"):
                ImageCollection().prune(filters={"until": "24h"})

    def test_partial_preparation_failures_always_run_registered_cleanup(self) -> None:
        for stage in ("after_container_create", "after_repo_copy", "after_auth"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / ".local" / "execution"
                durable.initialize_execution_storage(root)
                cleaned: list[str] = []

                def fail(_request: object, attempt_root: Path) -> object:
                    marker = attempt_root / f"{stage}.marker"
                    marker.write_text("owned", encoding="utf-8")
                    raise ExperimentConfigurationError(stage)

                backend = adapter.LocalExecutionBackend(
                    contract=frozen()[0], live_seal={}, work_root=root / "attempts",
                    task_callback=fail,
                    command_callback=lambda *_: (), evaluator_callback=lambda *_: None,
                    partial_cleanup_callback=lambda _request, attempt_root: cleaned.append(
                        (attempt_root / f"{stage}.marker").read_text(encoding="utf-8")
                    ),
                )
                request = MagicMock()
                request.cell_id = "cell"
                request.attempt = 1
                request.command = ("fixture",)
                request.command_sha256 = "a" * 64
                request.effective_task_commitment_sha256 = "b" * 64
                request.ownership_token_sha256 = "c" * 64
                with self.assertRaisesRegex(ExperimentConfigurationError, stage):
                    backend.prepare(request)
                self.assertEqual(cleaned, ["owned"])

    def test_partial_cleanup_ownership_filter_never_selects_unmarked_container(self) -> None:
        with (
            patch.object(adapter, "_docker_container_ids", return_value={"owned", "foreign"}),
            patch.object(adapter, "_docker_observations", return_value=[
                {
                    "id": "owned", "labels": {
                        "engineering-scope-guard.ownership": "a" * 64
                    },
                },
                {
                    "id": "foreign", "labels": {
                        "engineering-scope-guard.ownership": "b" * 64
                    },
                },
            ]),
        ):
            self.assertEqual(
                adapter._docker_ids_with_exact_ownership("image", "a" * 64),
                {"owned"},
            )

    def test_post_task_prelaunch_validation_failures_always_cleanup(self) -> None:
        for failure in ("validation", "command", "attestation", "gated_spawn"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / ".local" / "execution"
                durable.initialize_execution_storage(root)
                contract, _pool = frozen()
                cleaned: list[str] = []
                request = MagicMock()
                request.cell_id = "cell"
                request.attempt = 1
                request.command = ("fixture",)
                request.command_sha256 = "a" * 64
                request.effective_task_commitment_sha256 = "b" * 64
                request.ownership_token_sha256 = "c" * 64
                request.task = {"resolved_image": "image"}
                attestation = {
                    "runtime_identity": "runtime", "source_identity": "source",
                    "evaluator_identity": "evaluator", "image_pool_identity": "pool",
                    "codex_version": "version", "model": "model",
                    "reasoning_effort": "low", "resolved_image": "image",
                    "credential_isolated": True, "fresh_worktree": True,
                    "sandbox": "workspace-write", "network_access": False,
                    "user_config_loaded": False, "external_tools_enabled": False,
                }

                def task_callback(_request: object, attempt_root: Path) -> adapter.LocalTaskPreparation:
                    workspace = attempt_root / "repository"
                    workspace.mkdir(mode=0o700)
                    return adapter.LocalTaskPreparation(
                        workspace=workspace,
                        prompt="invalid" if failure == "validation" else b"prompt",
                        environment={},
                        attestation={**attestation, **({"extra": True} if failure == "attestation" else {})},
                    )

                backend = adapter.LocalExecutionBackend(
                    contract=contract, live_seal={}, work_root=root / "attempts",
                    task_callback=task_callback,
                    command_callback=(
                        (lambda *_: ("drift",))
                        if failure == "command" else (lambda *_: request.command)
                    ),
                    evaluator_callback=lambda *_: None,
                    partial_cleanup_callback=lambda *_: (
                        cleaned.append(failure) or {}
                    ),
                )
                gated_effect = (
                    ExperimentConfigurationError("spawn failed")
                    if failure == "gated_spawn" else MagicMock(
                        process_identity_sha256="d" * 64
                    )
                )
                with (
                    patch.object(adapter, "prepare_gated_process", side_effect=(
                        gated_effect if isinstance(gated_effect, BaseException) else None
                    ), return_value=(
                        None if isinstance(gated_effect, BaseException) else gated_effect
                    )),
                    self.assertRaises(ExperimentConfigurationError),
                ):
                    backend.prepare(request)
                self.assertEqual(cleaned, [failure])

    def test_gated_spawn_failure_persists_prelaunch_cleanup_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state, _fake = self.fixture(Path(directory))

            def task_callback(
                request: adapter.AttemptRequest, attempt_root: Path,
            ) -> adapter.LocalTaskPreparation:
                workspace = attempt_root / "repository"
                workspace.mkdir(mode=0o700)
                cell = next(
                    item for item in state.contract["schedule"]["cells"]
                    if item["cell_id"] == request.cell_id
                )
                return adapter.LocalTaskPreparation(
                    workspace=workspace, prompt=b"prompt", environment={},
                    attestation={
                        "runtime_identity": state.contract["runtime"]["runtime_identity"],
                        "source_identity": state.contract["source"]["source_identity"],
                        "evaluator_identity": state.contract["source"]["evaluator_identity"],
                        "image_pool_identity": state.contract["source"]["image_pool_identity"],
                        "codex_version": state.contract["runtime"]["codex_version"],
                        "model": state.contract["runtime"]["model"],
                        "reasoning_effort": cell["reasoning_effort"],
                        "resolved_image": request.task["resolved_image"],
                        "credential_isolated": True, "fresh_worktree": True,
                        "sandbox": "workspace-write", "network_access": False,
                        "user_config_loaded": False, "external_tools_enabled": False,
                    },
                )

            def partial(
                request: adapter.AttemptRequest, _attempt_root: Path,
            ) -> dict:
                return {
                    "schema_name": "engineering-scope-guard.reasoning-effort-v2-docker-ownership",
                    "schema_version": 1,
                    "contract_sha256": state.contract["contract_sha256"],
                    "cell_id": request.cell_id, "attempt": request.attempt,
                    "resolved_image": request.task["resolved_image"],
                    "materialization_container_id": None,
                    "prelaunch_ownership_token_sha256": request.ownership_token_sha256,
                    "baseline_container_ids": [], "create_event_container_ids": [],
                    "event_window_start_ns": None, "event_window_end_ns": None,
                    "attribution_mode": None, "ownership_marker_sha256": None,
                    "injection_sha256": None, "injection_relative_path": None,
                    "evaluator_dataset_sha256": None,
                    "evaluator_dataset_relative_path": None,
                    "source_row_identity_sha256": None,
                    "lifecycle_events": [], "final_observations": [],
                }

            backend = adapter.LocalExecutionBackend(
                contract=state.contract, live_seal=state.seal,
                work_root=state.root / "attempts", task_callback=task_callback,
                command_callback=lambda request, _task: request.command,
                evaluator_callback=lambda *_: None,
                partial_cleanup_callback=partial,
            )
            cell = state.contract["schedule"]["cells"][0]
            with (
                patch.object(
                    adapter, "prepare_gated_process",
                    side_effect=ExperimentConfigurationError("gated spawn failed"),
                ),
                self.assertRaisesRegex(ExperimentConfigurationError, "gated spawn failed"),
            ):
                adapter.execute_one_attempt(
                    backend=backend, contract=state.contract,
                    private_pool=state.private_pool, live_seal=state.seal,
                    execution_root=state.root, cell_id=cell["cell_id"], attempt=1,
                    codex_binary="/fixture/codex",
                )
            receipt = durable._load_receipt(
                state.receipts, state.contract, cell["cell_id"], 1
            )
            self.assertIsNotNone(receipt)
            self.assertEqual(receipt["classification"], "harness_failure")
            self.assertIsNotNone(
                receipt["execution_artifact"]["cleanup_receipt_sha256"]
            )
            durable.validate_terminal_receipt_artifacts(
                state.contract, state.private_pool, state.ledger, state.root, receipt
            )

    def test_cleanup_proves_docker_before_credential_failure_and_keeps_state_reconcilable(self) -> None:
        backend = object.__new__(adapter.LocalExecutionBackend)
        backend.contract = {"contract_sha256": "a" * 64}
        order: list[str] = []
        def fail_credentials(_request: object, _task: object) -> None:
            order.append("credentials")
            raise RuntimeError("credential failure")
        backend.cleanup_callback = fail_credentials
        backend.abort = lambda _request, _state: order.append("abort")
        backend._capture_evaluator_containers = lambda _request, _state: (
            order.append("capture"), {"owned"}
        )[-1]
        state = MagicMock()
        state.cleaned = False
        state.evaluator = MagicMock()
        state.evaluator_container_ids = {"owned"}
        state.task.context = {"materialization_container_id": "materialized"}
        backend._state = lambda _request, _prepared: state
        request = MagicMock()
        request.cell_id = "cell"
        request.attempt = 1
        request.task = {"resolved_image": "image@sha256:fixture"}
        observations = [
            {"id": "materialized", "name": "/m", "image": "image", "labels": {}, "running": False},
            {"id": "owned", "name": "/owner-task", "image": "image", "labels": {}, "running": False},
        ]
        with (
            patch.object(
                adapter, "_terminal_evaluator_container_observations",
                side_effect=lambda *_args: (order.append("docker"), observations[1:])[1],
            ),
            patch.object(adapter, "_stop_owned_docker_containers", return_value=observations[:1]),
        ):
            with self.assertRaises(adapter.CleanupFailure) as caught:
                backend.cleanup(request, state)
        self.assertEqual(order, ["abort", "capture", "docker", "credentials"])
        self.assertFalse(state.cleaned)
        self.assertIsNotNone(caught.exception.docker_ownership)

    def test_project_factory_freeze_prepare_evaluate_cleanup_is_provider_free(self) -> None:
        """Exercise the concrete project wiring while every external launch is mocked."""

        qualified = qualification()
        old_contract, private_pool = frozen()
        contract = build_contract(
            private_pool,
            model="fixture-model", codex_version="fixture",
            runtime_identity=digest(qualified["runtime_observation"]),
            source_identity=old_contract["source"]["source_identity"],
            qualification_receipt_sha256=qualified["state_sha256"],
            evaluator_identity=old_contract["source"]["evaluator_identity"],
            image_pool_identity=old_contract["source"]["image_pool_identity"],
            tool_configuration_identity="fixture-tools",
            qualification_reliability_audit_sha256=(
                durable.build_pool_reliability_audit(qualified)[
                    "pool_reliability_audit_sha256"
                ]
            ),
        )
        _gate, seal = live(contract, private_pool)
        selected = qualified["selection"]["primary"][0]
        candidate = next(
            value for value in qualified["candidates"]
            if value["slot"] == selected["slot"]
        )
        resolved_row = {
            "instance_id": candidate["instance_id"],
            "language": candidate["language"],
            "repo": candidate["repo"],
            "base_commit": "1" * 40,
            "docker_image": candidate["docker_image"],
            "problem_statement_sha256": "2" * 64,
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evaluator_root = root / "external-evaluator"
            dataset_root = root / "dataset"
            source_home = root / "source-codex-home"
            for path in (evaluator_root, dataset_root, source_home):
                path.mkdir()
            evaluator_python = root / "evaluator-python"
            codex_binary = root / "codex"
            docker_binary = root / "docker"
            model_catalog = root / "models.json"
            reserve_receipt = root / "reserve.json"
            for path in (
                evaluator_python, codex_binary, docker_binary,
                model_catalog, reserve_receipt,
            ):
                path.write_bytes(b"fixture")
                path.chmod(0o700 if path in {evaluator_python, codex_binary, docker_binary} else 0o600)
            work_root = root / ".local" / "execution"
            durable.initialize_execution_storage(work_root)

            with patch.object(
                adapter, "resolve_dataset_task", return_value=resolved_row,
            ):
                frozen_task = adapter.freeze_private_pool_task_from_dataset(
                    root=root, evaluator_python=evaluator_python,
                    dataset_root=dataset_root,
                    qualification_receipt=qualified,
                    candidate_slot=selected["slot"],
                )
            self.assertEqual(frozen_task["docker_image"], candidate["docker_image"])
            self.assertEqual(frozen_task["resolved_image"], selected["resolved_image"])
            self.assertEqual(frozen_task["base_commit"], resolved_row["base_commit"])

            order: list[str] = []

            def resolve_task(*args: object) -> dict:
                mode = args[5]
                order.append(f"dataset:{mode}")
                return resolved_row if mode == "resolve" else {"prompt": "fixture"}

            def run_command(command: list[str], **kwargs: object) -> SimpleNamespace:
                if command[:2] == [str(adapter.evaluator_executable(evaluator_python)), "-c"]:
                    output_path = Path(command[-1])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    row = {**resolved_row, "docker_image": frozen_task["resolved_image"]}
                    encoded = (
                        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode()
                    output_path.write_bytes(encoded)
                    output_path.chmod(0o600)
                    metadata = {
                        "dataset_sha256": adapter.hashlib.sha256(encoded).hexdigest(),
                        "source_row_identity_sha256": frozen_task[
                            "source_row_identity_sha256"
                        ],
                    }
                    return SimpleNamespace(
                        returncode=0, stdout=json.dumps(metadata), stderr="",
                    )
                if command[:3] == [str(codex_binary.resolve()), "exec", "--help"]:
                    flags = " ".join(
                        [
                            "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                            "--approve-for-me", "--skip-git-repo-check", "--color", "--model",
                            "--config", "--disable",
                        ]
                    )
                    return SimpleNamespace(returncode=0, stdout=flags, stderr="")
                if command[:3] == ["docker", "image", "inspect"]:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=json.dumps([frozen_task["resolved_image"]]), stderr="",
                    )
                if command[:2] == ["docker", "create"]:
                    return SimpleNamespace(returncode=0, stdout="materialized\n", stderr="")
                if command[:2] == ["docker", "cp"]:
                    return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return SimpleNamespace(
                        returncode=0, stdout=frozen_task["base_commit"] + "\n", stderr="",
                    )
                raise AssertionError(f"unexpected external command: {command!r}")

            def gated(
                command: tuple[str, ...], *, command_sha256: str,
                ownership_token_sha256: str, **_kwargs: object,
            ) -> adapter.GatedProcess:
                process = MagicMock()
                process.pid = 1234
                process.poll.return_value = 0
                return adapter.GatedProcess(
                    process=process, release_fd=99,
                    command_sha256=command_sha256,
                    ownership_token_sha256=ownership_token_sha256,
                    process_identity_sha256=digest({"command": list(command)}),
                )

            def provision(_source: Path, destination: Path) -> None:
                order.append("auth:provision")
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "auth.json").write_text("fixture", encoding="utf-8")

            def remove(destination: Path) -> None:
                order.append("auth:remove")
                (destination / "auth.json").unlink()

            with (
                patch.object(adapter.qualifier_live, "_revalidate_sources", side_effect=lambda *_: order.append("sources:revalidate")),
                patch.object(adapter.qualifier_live, "_codex_runtime", return_value=qualified["runtime_observation"]),
                patch.object(adapter, "resolve_dataset_task", side_effect=resolve_task),
                patch.object(adapter, "_validate_prompt_bytes", return_value=b"frozen prompt"),
                patch.object(adapter, "capture_repository_baseline", return_value={"baseline": "fixture"}),
                patch.object(adapter, "subject_patch_from_baseline", return_value=b"diff --git fixture\n"),
                patch.object(adapter, "provision_file_auth", side_effect=provision),
                patch.object(adapter, "remove_file_auth", side_effect=remove),
                patch.object(adapter.subprocess, "run", side_effect=run_command),
                patch.object(adapter, "prepare_gated_process", side_effect=gated),
                patch.object(adapter.shutil, "which", side_effect=lambda value: str(docker_binary) if value == "docker" else str(codex_binary)),
            ):
                backend = adapter.build_local_execution_backend(
                    root=root, contract=contract, live_seal=seal,
                    work_root=work_root / "attempts", evaluator_root=evaluator_root,
                    dataset_root=dataset_root, evaluator_python=evaluator_python,
                    codex_binary=str(codex_binary), source_codex_home=source_home,
                    model_catalog=model_catalog, reserve_receipt=reserve_receipt,
                )
                request = adapter.AttemptRequest(
                    cell_id=contract["schedule"]["cells"][0]["cell_id"], attempt=1,
                    task=frozen_task, command=(str(codex_binary.resolve()), "exec"),
                    command_sha256="3" * 64,
                    effective_task_commitment_sha256="4" * 64,
                    ownership_token_sha256="5" * 64,
                    process_identity_sha256="6" * 64,
                    subject_timeout_seconds=1, evaluator_timeout_seconds=1,
                )
                prepared = backend.prepare(request)
                self.assertLess(order.index("sources:revalidate"), order.index("dataset:resolve"))
                subject = adapter.SubjectInvocation(0, False, _trace(), b"", 1.0)
                with patch.object(adapter, "run_gated_process", return_value=subject):
                    actual_subject = backend.run_subject(request, prepared.state)
                with patch.object(adapter, "_docker_container_ids", return_value={"baseline"}):
                    gated_evaluator = backend.prepare_evaluator(request, prepared.state, actual_subject)
                state = prepared.state
                self.assertEqual(state.evaluator_plan.cwd, evaluator_root.resolve())
                self.assertEqual(
                    Path(state.evaluator_plan.environment["PYTHONPATH"].split(os.pathsep)[0]),
                    state.attempt_root / "evaluator-python-injection",
                )
                injection = state.attempt_root / "evaluator-python-injection" / "sitecustomize.py"
                self.assertIn(state.evaluator_ownership_marker, injection.read_text(encoding="utf-8"))
                frozen_dataset_path = state.attempt_root / "evaluator-dataset" / "task.jsonl"
                self.assertIn(str(frozen_dataset_path), state.evaluator_plan.command)
                self.assertEqual(
                    json.loads(frozen_dataset_path.read_text(encoding="utf-8"))[
                        "docker_image"
                    ],
                    frozen_task["resolved_image"],
                )
                official = state.attempt_root / "evaluator" / "official"
                report_path = official / frozen_task["task_id"] / "report.json"
                report_path.parent.mkdir(parents=True)
                report_path.write_text(json.dumps({"resolved": True}), encoding="utf-8")
                (official / "results.json").write_text(json.dumps({"success": 1}), encoding="utf-8")
                evaluator_raw = adapter.SubjectInvocation(0, False, b"eval", b"", 1.0)
                observations = [{
                    "id": "eval-owned", "name": "/opaque", "image": "image",
                    "labels": {"engineering-scope-guard.ownership": state.evaluator_ownership_marker},
                    "running": False,
                }]
                with (
                    patch.object(adapter, "_docker_container_ids", return_value={"baseline", "eval-owned"}),
                    patch.object(adapter, "_docker_lifecycle_events", return_value=[{
                        "action": "create", "container_id": "eval-owned",
                        "time_nano": state.evaluator_docker_event_since_ns,
                        "image": frozen_task["resolved_image"], "name": "opaque",
                        "ownership_marker_sha256": state.evaluator_ownership_marker,
                    }]),
                    patch.object(adapter, "_docker_observations", return_value=observations),
                    patch.object(adapter, "run_gated_process", return_value=evaluator_raw),
                ):
                    evaluator = backend.run_evaluator(request, prepared.state, gated_evaluator)
                self.assertEqual(evaluator.report, {"resolved": True})
                final_observations = [
                    {
                        "id": "materialized", "name": "/materialized", "image": "image",
                        "labels": {"engineering-scope-guard.ownership": request.ownership_token_sha256},
                        "running": False,
                    },
                    *observations,
                ]
                with (
                    patch.object(adapter, "_docker_container_ids", return_value={"baseline", "eval-owned"}),
                    patch.object(adapter, "_docker_lifecycle_events", return_value=[{
                        "action": "create", "container_id": "eval-owned",
                        "time_nano": state.evaluator_docker_event_since_ns,
                        "image": frozen_task["resolved_image"], "name": "opaque",
                        "ownership_marker_sha256": state.evaluator_ownership_marker,
                    }]),
                    patch.object(adapter, "_docker_observations", return_value=observations),
                    patch.object(adapter, "_terminal_evaluator_container_observations", return_value=observations),
                    patch.object(adapter, "_stop_owned_docker_containers", return_value=final_observations[:1]),
                    patch.object(adapter, "abort_gated_process"),
                ):
                    docker_receipt = backend.cleanup(request, prepared.state)
                self.assertEqual(docker_receipt["baseline_container_ids"], ["baseline"])
                self.assertEqual(docker_receipt["create_event_container_ids"], ["eval-owned"])
                self.assertEqual(
                    docker_receipt["attribution_mode"],
                    "python_sitecustomize_docker_sdk_label_and_prune_suppression",
                )
                self.assertEqual(docker_receipt["ownership_marker_sha256"], state.evaluator_ownership_marker)
                self.assertEqual(order[-1], "auth:remove")

    def test_exporter_rederives_full_docker_attribution_relationship(self) -> None:
        class DockerEvidenceBackend(FakeBackend):
            def prepare_evaluator(
                self, request: adapter.AttemptRequest, prepared: object,
                subject: adapter.SubjectInvocation,
            ) -> adapter.GatedProcess:
                gated = super().prepare_evaluator(request, prepared, subject)
                gated.container_identity_sha256 = digest({
                    "resolved_image": request.task["resolved_image"],
                    "baseline_container_ids": ["baseline"],
                    "injection_mechanism": (
                        "python_sitecustomize_docker_sdk_label_and_prune_suppression"
                    ),
                    "injection_sha256": self.injection_sha256,
                    "evaluator_dataset_sha256": self.evaluator_dataset_sha256,
                    "source_row_identity_sha256": request.task[
                        "source_row_identity_sha256"
                    ],
                })
                return gated

            def cleanup(
                self, request: adapter.AttemptRequest, prepared: object,
            ) -> dict:
                self.calls.append("cleanup")
                return {
                    "schema_name": "engineering-scope-guard.reasoning-effort-v2-docker-ownership",
                    "schema_version": 1,
                    "contract_sha256": self.contract["contract_sha256"],
                    "cell_id": request.cell_id, "attempt": request.attempt,
                    "resolved_image": request.task["resolved_image"],
                    "materialization_container_id": None,
                    "prelaunch_ownership_token_sha256": request.ownership_token_sha256,
                    "baseline_container_ids": ["baseline"],
                    "create_event_container_ids": ["eval-owned"],
                    "event_window_start_ns": 1,
                    "event_window_end_ns": 2,
                    "attribution_mode": (
                        "python_sitecustomize_docker_sdk_label_and_prune_suppression"
                    ),
                    "ownership_marker_sha256": "e" * 64,
                    "injection_sha256": self.injection_sha256,
                    "injection_relative_path": (
                        f"attempts/{request.cell_id}/attempt-{request.attempt}/"
                        "evaluator-python-injection/sitecustomize.py"
                    ),
                    "evaluator_dataset_sha256": self.evaluator_dataset_sha256,
                    "evaluator_dataset_relative_path": (
                        f"attempts/{request.cell_id}/attempt-{request.attempt}/"
                        "evaluator-dataset/task.jsonl"
                    ),
                    "source_row_identity_sha256": request.task[
                        "source_row_identity_sha256"
                    ],
                    "lifecycle_events": [{
                        "action": "create", "container_id": "eval-owned", "time_nano": 1,
                        "image": request.task["resolved_image"], "name": "opaque",
                        "ownership_marker_sha256": "e" * 64,
                    }],
                    "final_observations": [{
                        "id": "eval-owned", "name": "/opaque", "image": "image",
                        "labels": {"engineering-scope-guard.ownership": "e" * 64},
                        "running": False,
                    }],
                }

        def reseal(path: Path, updates: dict) -> dict:
            value = json.loads(path.read_text(encoding="utf-8"))
            body = {key: item for key, item in value.items() if key != "receipt_sha256"}
            body.update(updates)
            value = {**body, "receipt_sha256": digest(body)}
            path.write_text(
                json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            return value

        with tempfile.TemporaryDirectory() as directory:
            old_contract, old_pool = frozen()
            def enrich(task: dict) -> dict:
                task = {
                    key: value for key, value in task.items()
                    if key not in {"population_slot", "alternate_ordinal"}
                }
                projection = {
                    "instance_id": task["task_id"], "language": "python",
                    "repo": task["repository"], "base_commit": "1" * 40,
                    "docker_image": "source-tag",
                    "problem_statement_sha256": "2" * 64,
                }
                return {
                    **task, "language": "python", "base_commit": "1" * 40,
                    "docker_image": "source-tag",
                    "problem_statement_sha256": "2" * 64,
                    "source_row_identity_sha256": digest(projection),
                }
            private_pool = build_private_pool(
                [enrich(task) for task in old_pool["primaries"]],
                [enrich(task) for task in old_pool["alternates"]],
            )
            contract = build_contract(
                private_pool,
                model=old_contract["runtime"]["model"],
                codex_version=old_contract["runtime"]["codex_version"],
                runtime_identity=old_contract["runtime"]["runtime_identity"],
                source_identity=old_contract["source"]["source_identity"],
                qualification_receipt_sha256=old_contract["source"]["qualification_receipt_sha256"],
                evaluator_identity=old_contract["source"]["evaluator_identity"],
                image_pool_identity=old_contract["source"]["image_pool_identity"],
                tool_configuration_identity=old_contract["runtime"]["tool_configuration_identity"],
                qualification_reliability_audit_sha256=old_contract["source"][
                    "qualification_reliability_audit_sha256"
                ],
            )
            _gate, seal = live(contract, private_pool)
            state = State(Path(directory), contract, private_pool, seal)
            backend = DockerEvidenceBackend()
            backend.contract = state.contract
            cell_id = state.contract["schedule"]["cells"][0]["cell_id"]
            injection_path = (
                state.root / "attempts" / cell_id / "attempt-1"
                / "evaluator-python-injection" / "sitecustomize.py"
            )
            injection_path.parent.mkdir(parents=True)
            cursor = injection_path.parent
            while cursor != state.root:
                cursor.chmod(0o700)
                cursor = cursor.parent
            injection_path.write_bytes(b"fixture-injection")
            injection_path.chmod(0o600)
            backend.injection_sha256 = adapter.hashlib.sha256(
                injection_path.read_bytes()
            ).hexdigest()
            dataset_path = (
                state.root / "attempts" / cell_id / "attempt-1"
                / "evaluator-dataset" / "task.jsonl"
            )
            dataset_path.parent.mkdir(parents=True)
            dataset_path.parent.chmod(0o700)
            dataset_path.write_bytes(b'{"docker_image":"resolved"}\n')
            dataset_path.chmod(0o600)
            backend.evaluator_dataset_sha256 = adapter.hashlib.sha256(
                dataset_path.read_bytes()
            ).hexdigest()
            result = self.execute(state, backend)
            durable.validate_terminal_receipt_artifacts(
                state.contract, state.private_pool, state.ledger, state.root,
                result["receipt"],
            )
            artifact_root = state.root / "artifacts" / cell_id / "attempt-1"
            docker_receipt = reseal(
                artifact_root / "docker-ownership.json",
                {"baseline_container_ids": ["forged-baseline"]},
            )
            cleanup = reseal(
                artifact_root / "cleanup.json",
                {"docker_ownership_receipt_sha256": docker_receipt["receipt_sha256"]},
            )
            reseal(
                artifact_root / "execution.json",
                {"cleanup_receipt_sha256": cleanup["receipt_sha256"]},
            )
            with self.assertRaisesRegex(
                ExperimentConfigurationError,
                "attribution does not match the durable evaluator start",
            ):
                durable.build_terminal_receipt_from_artifact_root(
                    state.contract, state.private_pool, state.ledger, state.root,
                    cell_id=cell_id, attempt=1,
                )


if __name__ == "__main__":
    unittest.main()
