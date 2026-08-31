from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from engineering_scope_guard.evaluator_stable_qualification import (
    LANGUAGES,
    STAGES,
    build_receipt as build_qualification_receipt,
    next_qualification_stage,
    qualification_rank,
    record_stage,
    sha256_value,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.reasoning_effort_v2 import (
    TERMINAL_RECEIPT_KEYS,
    build_contract,
    build_private_pool,
    subject_command_identity,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reasoning_effort_v2_runner_execution_boundaries",
    ROOT / "scripts/reasoning_effort_v2_runner.py",
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def _tasks(count: int, *, offset: int = 0) -> list[dict[str, str]]:
    return [
        {
            "task_id": f"private-{number}",
            "repository": f"private/repository-{number}",
            "task_snapshot_sha256": f"{number % 16:x}" * 64,
            "resolved_image": f"private-image-{number}",
        }
        for number in range(offset + 1, offset + count + 1)
    ]


def _frozen() -> tuple[dict, dict]:
    private_pool = build_private_pool(_tasks(10), _tasks(2, offset=10))
    contract = build_contract(
        private_pool,
        model="fixture-model",
        codex_version="fixture-version",
        runtime_identity="fixture-runtime",
        source_identity="fixture-source",
        qualification_receipt_sha256="b" * 64,
        evaluator_identity="fixture-evaluator",
        image_pool_identity="c" * 64,
        tool_configuration_identity="fixture-tools",
    )
    return contract, private_pool


def _caller_gate(contract: dict, private_pool: dict) -> dict:
    return runner.seal_qualification_gate(
        {
            "schema_name": runner.QUALIFICATION_GATE_SCHEMA,
            "schema_version": 1,
            "status": "pass",
            "contract_sha256": contract["contract_sha256"],
            "private_pool_sha256": private_pool["private_pool_sha256"],
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "qualification_receipt_sha256": "b" * 64,
            "evaluator_identity": "fixture-evaluator",
            "image_pool_identity": "c" * 64,
            "runtime_identity": "fixture-runtime",
            "source_identity": "fixture-source",
            "checks": {key: True for key in runner.QUALIFICATION_CHECKS},
        }
    )


def _qualified_live(root: Path) -> tuple[dict, dict, dict, dict]:
    seed = "fixture-seed"
    revision = "d" * 40
    selected = []
    for language in LANGUAGES:
        for ordinal in range(6):
            instance_id = f"private-{language}-{ordinal}"
            selected.append(
                {
                    "instance_id": instance_id,
                    "repo": f"private/repo-{language}-{ordinal}",
                    "language": language,
                    "docker_image": f"private/image-{language}-{ordinal}",
                    "rank_commitment": qualification_rank(
                        seed, revision, language, instance_id
                    ),
                    "manifest_sha256": sha256_value({"image": instance_id}),
                }
            )
    reserve = {
        "schema": "private-fixture",
        "source": {"dataset": "fixture", "revision": revision},
        "selection": {
            "seed": seed,
            "selected": selected,
            "selected_ids_sha256": sha256_value(
                sorted(task["instance_id"] for task in selected)
            ),
        },
    }
    qualification = build_qualification_receipt(
        reserve,
        evaluator_revision="fixture-evaluator",
        repolaunch_revision="r" * 40,
        dataset_file_sha256={"fixture.parquet": "f" * 64},
        evaluator_python={"python": "3.14", "executable_sha256": "a" * 64},
        codex_runtime={"codex_version": "fixture-version", "model": "fixture-model"},
        execution_code_sha256={"qualifier.py": "b" * 64},
        evaluator_tree_sha256="c" * 64,
        repolaunch_tree_sha256="d" * 64,
    )
    raw_root = root / ".local" / "qualification-raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    (root / ".local").chmod(0o700)
    raw_root.chmod(0o700)
    while qualification["status"] == "in_progress":
        candidate, _stage = next_qualification_stage(qualification)
        slot = candidate["slot"]
        for stage in STAGES:
            stage_root = raw_root / f"slot-{slot:02d}" / stage
            stage_root.mkdir(parents=True, exist_ok=True)
            stage_root.parent.chmod(0o700)
            stage_root.chmod(0o700)
            stage_body = {
                "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
                "schema_version": 2,
                "slot": slot,
                "stage": stage,
                "outcome": "pass",
                "classification": None,
                "details": {},
                "artifact_sha256": {},
            }
            stage_receipt = {
                **stage_body,
                "stage_receipt_sha256": sha256_value(stage_body),
            }
            stage_receipt_path = stage_root / "stage-receipt.json"
            stage_receipt_path.write_text(
                json.dumps(stage_receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            stage_receipt_path.chmod(0o600)
            evidence = {
                "stage_receipt_sha256": stage_receipt["stage_receipt_sha256"],
                "artifact_set_sha256": sha256_value({}),
                "wall_seconds": 1.0,
            }
            if stage == "q1_environment":
                evidence["resolved_image_ref"] = (
                    f"{candidate['docker_image']}@sha256:{slot:064x}"
                )
            record_stage(
                qualification,
                slot=slot,
                stage=stage,
                outcome="pass",
                classification=None,
                evidence=evidence,
            )
    population = qualification["selection"]
    all_selected = [*population["primary"], *population["alternates"]]
    candidates = {item["slot"]: item for item in qualification["candidates"]}
    pool_tasks = [
        {
            "task_id": item["instance_id"],
            "repository": item["repo"],
            "task_snapshot_sha256": candidates[item["slot"]]["manifest_sha256"],
            "resolved_image": item["resolved_image"],
        }
        for item in all_selected
    ]
    primary_count = len(population["primary"])
    private_pool = build_private_pool(
        pool_tasks[:primary_count], pool_tasks[primary_count:]
    )
    runtime_identity = runner.digest(qualification["runtime_observation"])
    evaluator_identity = runner.digest(
        {
            key: qualification["source"][key]
            for key in (
                "evaluator_revision",
                "evaluator_tree_sha256",
                "evaluator_python",
                "embedded_repolaunch_revision",
                "repolaunch_tree_sha256",
            )
        }
    )
    source_identity = runner.digest(qualification["source"])
    image_pool_identity = runner.digest(
        [
            {
                "slot": item["slot"],
                "resolved_image": candidates[item["slot"]]["resolved_image"],
            }
            for item in all_selected
        ]
    )
    contract = build_contract(
        private_pool,
        model="fixture-model",
        codex_version="fixture-version",
        runtime_identity=runtime_identity,
        source_identity=source_identity,
        qualification_receipt_sha256=qualification["state_sha256"],
        evaluator_identity=evaluator_identity,
        image_pool_identity=image_pool_identity,
        tool_configuration_identity="fixture-tools",
        qualification_reliability_audit_sha256=(
            runner.build_pool_reliability_audit(qualification)[
                "pool_reliability_audit_sha256"
            ]
        ),
    )
    receipt_path = root / ".local" / "qualification.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(qualification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(0o600)
    gate = runner.build_qualification_gate_from_receipt(
        contract, private_pool, receipt_path, raw_root
    )
    return contract, private_pool, gate, runner.build_live_seal(
        contract, private_pool, gate
    )


def _commitment(contract: dict, cell: dict) -> str:
    return next(
        item["task_commitment_sha256"]
        for item in contract["source"]["private_pool"]["primary_slot_commitments"]
        if item["population_slot"] == cell["population_slot"]
    )


def _record_attempt_started(
    ledger: Path, checkpoint: Path, contract: dict, live_seal: dict,
    private_pool: dict, *, cell_id: str, attempt: int,
) -> dict:
    runner.record_disk_safety_checked(
        ledger,
        checkpoint,
        contract,
        live_seal,
        private_pool,
        cell_id=cell_id,
        attempt=attempt,
        receipt={
            "schema_name": "engineering-scope-guard.experiment-disk-safety-public",
            "schema_version": 1,
            "status": "pass",
            "policy_sha256": "7" * 64,
            "failures": [],
            "dynamic_host_metadata_withheld": True,
        },
    )
    return runner.record_attempt_started(
        ledger, checkpoint, contract, live_seal, private_pool,
        cell_id=cell_id, attempt=attempt,
    )


def _record(cell_id: str, classification: str = "accepted_completed") -> dict:
    return {
        "cell_id": cell_id,
        "termination": classification,
        "timed_out": classification == "trajectory_timeout",
        "evaluator_anomalies": [],
        "input_tokens": 100,
        "cached_input_tokens": 10,
        "cache_write_input_tokens": 5,
        "output_tokens": 20,
        "reasoning_output_tokens": 4,
        "turns": 1,
        "tool_actions": 2,
        "search_actions": 1,
        "correction_turns": 0,
        "wall_seconds": 2.0,
    }


def _caller_receipt(
    contract: dict, cell: dict, *, classification: str = "accepted_completed"
) -> dict:
    return runner.build_terminal_receipt(
        contract,
        cell_id=cell["cell_id"],
        attempt=1,
        effective_task_commitment_sha256=_commitment(contract, cell),
        subject_invocation_started=True,
        command_sha256="d" * 64,
        classification=classification,
        evaluator_receipt_sha256="e" * 64,
        analysis_record=_record(cell["cell_id"], classification),
    )


def _write_self_hashed(path: Path, body: dict) -> None:
    artifact = {**body, "receipt_sha256": runner.digest(body)}
    path.parent.mkdir(parents=True, exist_ok=True)
    cursor = path.parent
    while True:
        cursor.chmod(0o700)
        if (cursor / "receipt-state.json").exists() or ".local" not in cursor.parts:
            break
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.write_text(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _artifact_receipt(
    contract: dict,
    cell: dict,
    artifact_root: Path,
    *,
    container_identity_sha256: str = "3" * 64,
) -> None:
    commitment = _commitment(contract, cell)
    command_sha256 = subject_command_identity(contract, cell["cell_id"])
    common = {
        "schema_version": 1,
        "contract_sha256": contract["contract_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "cell_id": cell["cell_id"],
        "attempt": 1,
        "effective_task_commitment_sha256": commitment,
    }
    execution_path = artifact_root / "execution.json"
    evaluator_path = artifact_root / "evaluator.json"
    measurement_path = artifact_root / "measurement.json"
    raw_root = artifact_root / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_root.chmod(0o700)
    raw_files = {
        "codex.jsonl": b'{"type":"turn.completed"}\n',
        "codex.stderr": b"",
        "prediction.json": b"{}\n",
        "patch.diff": b"",
        "evaluator.stdout": b"",
        "evaluator.stderr": b"",
        "evaluator-report.json": b"{}\n",
        "evaluator-results.json": b"{}\n",
    }
    raw_hashes = {}
    for name, content in raw_files.items():
        path = raw_root / name
        path.write_bytes(content)
        path.chmod(0o600)
        raw_hashes[name] = hashlib.sha256(content).hexdigest()
    _write_self_hashed(
        execution_path,
        {
            **common,
            "schema_name": runner.EXECUTION_ARTIFACT_SCHEMA,
            "subject_invocation_started": True,
            "command_sha256": command_sha256,
            "status": "returned",
            "timed_out": False,
            "subject_exit_code": 0,
            "ownership_token_sha256": "1" * 64,
            "process_identity_sha256": "2" * 64,
            "container_identity_sha256": container_identity_sha256,
            "subject_stdout_sha256": raw_hashes["codex.jsonl"],
            "subject_stderr_sha256": raw_hashes["codex.stderr"],
            "prediction_sha256": raw_hashes["prediction.json"],
            "patch_sha256": raw_hashes["patch.diff"],
            "cleanup_receipt_sha256": None,
        },
    )
    _write_self_hashed(
        evaluator_path,
        {
            **common,
            "schema_name": runner.EVALUATOR_ARTIFACT_SCHEMA,
            "evaluator_identity": contract["source"]["evaluator_identity"],
            "invocation_started": True,
            "evaluator_command_sha256": "4" * 64,
            "ownership_token_sha256": "5" * 64,
            "process_identity_sha256": "6" * 64,
            "container_identity_sha256": container_identity_sha256,
            "disposition": "accepted",
            "anomaly_codes": [],
            "evaluator_stdout_sha256": raw_hashes["evaluator.stdout"],
            "evaluator_stderr_sha256": raw_hashes["evaluator.stderr"],
            "report_sha256": raw_hashes["evaluator-report.json"],
            "results_sha256": raw_hashes["evaluator-results.json"],
        },
    )
    record = _record(cell["cell_id"])
    _write_self_hashed(
        measurement_path,
        {
            **common,
            "schema_name": runner.MEASUREMENT_ARTIFACT_SCHEMA,
            "record_completeness": "complete",
            **{
                field: record[field]
                for field in (*runner.INTEGER_WORK_FIELDS, *runner.FLOAT_WORK_FIELDS)
            },
        },
    )


def _selected_container_identity(private_pool: dict, commitment: str) -> str:
    task = next(
        item
        for item in [*private_pool["primaries"], *private_pool["alternates"]]
        if runner.digest(item) == commitment
    )
    return runner.digest({"resolved_image": task["resolved_image"]})


class ReasoningEffortV2ExecutionBoundaryTests(unittest.TestCase):
    def test_caller_cannot_forge_qualification_authority_from_public_hashes(self) -> None:
        """A live seal requires a re-read terminal qualifier receipt, not caller booleans."""

        contract, private_pool = _frozen()
        with self.assertRaisesRegex(
            ExperimentConfigurationError, "qualification.*(receipt|terminal|authority)"
        ):
            _caller_gate(contract, private_pool)

        with tempfile.TemporaryDirectory() as directory:
            contract, private_pool, gate, _live_seal = _qualified_live(Path(directory))
            forged = deepcopy(gate)
            forged["qualification_receipt"]["status"] = "insufficient"
            forged["qualification_gate_sha256"] = runner.digest(
                {
                    key: value
                    for key, value in forged.items()
                    if key != "qualification_gate_sha256"
                }
            )
            with self.assertRaises(ExperimentConfigurationError):
                runner.build_live_seal(contract, private_pool, forged)

    def test_caller_cannot_assert_evaluator_outcome_or_measurement(self) -> None:
        """A syntactic evaluator digest cannot authorize caller-created results/work."""

        contract, _private_pool = _frozen()
        cell = contract["schedule"]["cells"][0]
        with self.assertRaisesRegex(
            ExperimentConfigurationError, "evaluator.*(artifact|receipt|evidence)"
        ):
            _caller_receipt(contract, cell)

    def test_stage_1_full_validates_terminal_receipts_before_passing(self) -> None:
        """Stage 1 must reject even a body whose stored self-hash field was corrupted."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(root)
            execution_root = root / ".local" / "execution"
            runner.initialize_execution_storage(execution_root)
            ledger = execution_root / "ledger.jsonl"
            checkpoint = execution_root / "checkpoint.json"
            receipt_root = execution_root / "receipts"
            cells = contract["schedule"]["cells"]
            for cell in cells[:4]:
                _record_attempt_started(
                    ledger, checkpoint, contract, live_seal, private_pool,
                    cell_id=cell["cell_id"], attempt=1,
                )
                runner.record_subject_invocation_started(
                    ledger, checkpoint, contract, live_seal, private_pool,
                    cell_id=cell["cell_id"], attempt=1,
                    command_sha256=subject_command_identity(contract, cell["cell_id"]),
                    ownership_token_sha256="1" * 64,
                    process_identity_sha256="2" * 64,
                )
                commitment = _commitment(contract, cell)
                task = next(
                    item
                    for item in [*private_pool["primaries"], *private_pool["alternates"]]
                    if runner.digest(item) == commitment
                )
                evaluator_container = runner.digest(
                    {"resolved_image": task["resolved_image"]}
                )
                runner.record_evaluator_invocation_started(
                    ledger, checkpoint, contract, live_seal, private_pool,
                    cell_id=cell["cell_id"], attempt=1,
                    evaluator_command_sha256="4" * 64,
                    ownership_token_sha256="5" * 64,
                    process_identity_sha256="6" * 64,
                    container_identity_sha256=evaluator_container,
                )
                receipt = _artifact_receipt(
                    contract,
                    cell,
                    execution_root
                    / "artifacts"
                    / cell["cell_id"]
                    / "attempt-1",
                    container_identity_sha256=evaluator_container,
                )
                receipt = runner.build_terminal_receipt_from_artifact_root(
                    contract,
                    private_pool,
                    ledger,
                    execution_root,
                    cell_id=cell["cell_id"],
                    attempt=1,
                )
                path = runner.persist_terminal_receipt(receipt_root, contract, receipt)
                runner.reconcile_attempt(
                    ledger, checkpoint, receipt_root, contract, private_pool, live_seal,
                    cell_id=cell["cell_id"], attempt=1,
                )
                persisted = json.loads(path.read_text(encoding="utf-8"))
                persisted["terminal_receipt_sha256"] = "f" * 64
                path.write_text(
                    json.dumps(persisted, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )

            runtime_path = execution_root / "runtime-revalidation.json"
            source_path = execution_root / "source-revalidation.json"
            _write_self_hashed(
                runtime_path,
                {
                    "schema_name": runner.RUNTIME_REVALIDATION_SCHEMA,
                    "schema_version": 1,
                    "contract_sha256": contract["contract_sha256"],
                    "live_seal_sha256": live_seal["live_seal_sha256"],
                    "runtime_identity": contract["runtime"]["runtime_identity"],
                    "status": "pass",
                },
            )
            _write_self_hashed(
                source_path,
                {
                    "schema_name": runner.SOURCE_REVALIDATION_SCHEMA,
                    "schema_version": 1,
                    "contract_sha256": contract["contract_sha256"],
                    "live_seal_sha256": live_seal["live_seal_sha256"],
                    "source_identity": contract["source"]["source_identity"],
                    "evaluator_identity": contract["source"]["evaluator_identity"],
                    "image_pool_identity": contract["source"]["image_pool_identity"],
                    "status": "pass",
                },
            )
            audit = runner.record_stage_1_audit(
                ledger,
                checkpoint,
                receipt_root,
                contract,
                private_pool,
                live_seal,
                execution_root=execution_root,
                runtime_revalidation_receipt_path=runtime_path,
                source_revalidation_receipt_path=source_path,
            )
            self.assertEqual(audit["status"], "fail")
            self.assertFalse(audit["criteria"]["receipt_hashes_valid"])

    def test_concurrent_different_receipts_cannot_both_persist(self) -> None:
        """The immutable receipt check and create must share one lock boundary."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(root)
            cell = contract["schedule"]["cells"][0]
            execution_root = root / ".local" / "execution"
            runner.initialize_execution_storage(execution_root)
            ledger = execution_root / "ledger.jsonl"
            checkpoint = execution_root / "checkpoint.json"
            _record_attempt_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
            )
            runner.record_subject_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(contract, cell["cell_id"]),
                ownership_token_sha256="1" * 64,
                process_identity_sha256="2" * 64,
            )
            evaluator_container = _selected_container_identity(
                private_pool, _commitment(contract, cell)
            )
            runner.record_evaluator_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                evaluator_command_sha256="4" * 64,
                ownership_token_sha256="5" * 64,
                process_identity_sha256="6" * 64,
                container_identity_sha256=evaluator_container,
            )
            receipt_root = execution_root / "receipts"
            artifact_root = execution_root / "artifacts" / cell["cell_id"] / "attempt-1"
            _artifact_receipt(
                contract,
                cell,
                artifact_root,
                container_identity_sha256=evaluator_container,
            )
            first = runner.build_terminal_receipt_from_artifact_root(
                contract, private_pool, ledger, execution_root,
                cell_id=cell["cell_id"], attempt=1,
            )
            second = deepcopy(first)
            second["analysis_record"]["input_tokens"] += 1
            second["terminal_receipt_sha256"] = runner.digest(
                {key: value for key, value in second.items() if key != "terminal_receipt_sha256"}
            )
            original_atomic_json = runner._atomic_json
            first_entered = threading.Event()
            second_completed = threading.Event()
            counter_lock = threading.Lock()
            calls = 0

            def interleaved_atomic_json(path: Path, value: dict) -> None:
                nonlocal calls
                with counter_lock:
                    calls += 1
                    ordinal = calls
                if ordinal == 1:
                    first_entered.set()
                    second_completed.wait(timeout=0.5)
                    original_atomic_json(path, value)
                else:
                    original_atomic_json(path, value)
                    second_completed.set()

            def persist(value: dict) -> Exception | None:
                try:
                    runner.persist_terminal_receipt(receipt_root, contract, value)
                except Exception as error:  # noqa: BLE001 - the assertion inspects both racers
                    return error
                return None

            with patch.object(runner, "_atomic_json", side_effect=interleaved_atomic_json):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first_future = executor.submit(persist, first)
                    self.assertTrue(first_entered.wait(timeout=1.0))
                    second_future = executor.submit(persist, second)
                    errors = [first_future.result(), second_future.result()]

            self.assertEqual(sum(error is None for error in errors), 1)
            rejected = next(error for error in errors if error is not None)
            self.assertIsInstance(rejected, ExperimentConfigurationError)

    def test_orphaned_started_invocation_terminalizes_without_duplicate(self) -> None:
        """A proven-dead launch must stop durably instead of waiting forever or restarting."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(root)
            cell = contract["schedule"]["cells"][0]
            execution_root = root / ".local" / "execution"
            runner.initialize_execution_storage(execution_root)
            ledger = execution_root / "ledger.jsonl"
            checkpoint = execution_root / "checkpoint.json"
            receipts = execution_root / "receipts"
            _record_attempt_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
            )
            runner.record_subject_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(contract, cell["cell_id"]),
                ownership_token_sha256="1" * 64,
                process_identity_sha256="2" * 64,
            )
            reconcile_orphan = getattr(runner, "reconcile_orphaned_invocation", None)
            self.assertTrue(
                callable(reconcile_orphan),
                "runner must expose reconcile_orphaned_invocation with validated process evidence",
            )
            ownership_path = execution_root / "ownership.json"
            _write_self_hashed(
                ownership_path,
                {
                    "schema_name": runner.OWNERSHIP_RECEIPT_SCHEMA,
                    "schema_version": 1,
                    "contract_sha256": contract["contract_sha256"],
                    "schedule_sha256": contract["schedule"]["schedule_sha256"],
                    "cell_id": cell["cell_id"],
                    "attempt": 1,
                    "command_sha256": subject_command_identity(
                        contract, cell["cell_id"]
                    ),
                    "ownership_token_sha256": "1" * 64,
                    "process_identity_sha256": "2" * 64,
                    "container_observations": [],
                    "container_identity_sha256": runner.digest([]),
                    "status": "not_running",
                },
            )
            result = reconcile_orphan(
                ledger,
                checkpoint,
                receipts,
                contract,
                private_pool,
                live_seal,
                cell_id=cell["cell_id"],
                attempt=1,
                ownership_receipt_path=ownership_path,
            )
            self.assertEqual(result["action"], "batch_stopped")
            self.assertEqual(result["classification"], "durable_evidence_incomplete")
            event_types = [event["event_type"] for event in runner.read_ledger(ledger, contract)]
            self.assertEqual(event_types.count("subject_invocation_started"), 1)

    def test_torn_final_line_recovers_only_to_validated_checkpoint(self) -> None:
        """Recovery may truncate only the uncommitted suffix proven by the checkpoint."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(root)
            cell = contract["schedule"]["cells"][0]
            execution_root = root / ".local" / "execution"
            runner.initialize_execution_storage(execution_root)
            ledger = execution_root / "ledger.jsonl"
            checkpoint = execution_root / "checkpoint.json"
            _record_attempt_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
            )
            committed = ledger.read_bytes()
            with ledger.open("ab") as handle:
                handle.write(b'{"schema_name":"torn')
                handle.flush()
                os.fsync(handle.fileno())

            recover = getattr(runner, "recover_torn_ledger_from_checkpoint", None)
            self.assertTrue(
                callable(recover),
                "runner must expose recover_torn_ledger_from_checkpoint",
            )
            recovered = recover(ledger, checkpoint, contract, live_seal, private_pool)
            self.assertEqual(recovered["event_count"], 2)
            self.assertEqual(ledger.read_bytes(), committed)
            self.assertEqual(len(runner.read_ledger(ledger, contract)), 2)

    def test_execution_storage_is_local_contained_and_private_mode(self) -> None:
        """Initialization must reject non-.local roots and force 0700/0600 modes."""

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            initialize = getattr(runner, "initialize_execution_storage", None)
            self.assertTrue(
                callable(initialize),
                "runner must expose initialize_execution_storage",
            )
            with self.assertRaises(ExperimentConfigurationError):
                initialize(base / "public-results")

            root = base / ".local" / "reasoning-effort-v2"
            old_umask = os.umask(0)
            try:
                paths = initialize(root)
            finally:
                os.umask(old_umask)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            for directory_path in paths["directories"]:
                self.assertTrue(Path(directory_path).resolve().is_relative_to(root.resolve()))
                self.assertEqual(stat.S_IMODE(Path(directory_path).stat().st_mode), 0o700)
            for file_path in paths["files"]:
                self.assertTrue(Path(file_path).resolve().is_relative_to(root.resolve()))
                self.assertEqual(stat.S_IMODE(Path(file_path).stat().st_mode), 0o600)

    def test_loose_self_hashed_artifacts_do_not_create_result_authority(self) -> None:
        """Caller-written JSON, even self-hashed, is not an evaluator/exporter receipt."""

        with tempfile.TemporaryDirectory() as directory:
            contract, _private_pool = _frozen()
            cell = contract["schedule"]["cells"][0]
            artifact_root = Path(directory) / "loose-artifacts"
            _artifact_receipt(contract, cell, artifact_root)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(authority|provenance|artifact root|marker)"
            ):
                runner.build_terminal_receipt_from_artifacts(
                    contract,
                    cell_id=cell["cell_id"],
                    attempt=1,
                    effective_task_commitment_sha256=_commitment(contract, cell),
                    execution_receipt_path=artifact_root / "execution.json",
                    evaluator_receipt_path=artifact_root / "evaluator.json",
                    measurement_receipt_path=artifact_root / "measurement.json",
                )

    def test_terminal_receipt_retains_and_revalidates_all_artifact_provenance(self) -> None:
        """Terminal evidence must retain every source digest and launch identity."""

        expected_fields = {
            "execution_receipt_sha256",
            "evaluator_receipt_sha256",
            "measurement_receipt_sha256",
            "execution_artifact",
            "evaluator_artifact",
            "measurement_artifact",
        }
        self.assertTrue(
            expected_fields <= TERMINAL_RECEIPT_KEYS,
            "terminal receipt schema drops artifact or launch provenance",
        )
        validator = getattr(runner, "validate_terminal_receipt_artifacts", None)
        self.assertTrue(
            callable(validator),
            "runner must re-open and re-hash all artifacts behind a terminal receipt",
        )

    def test_stage_1_uses_artifact_and_identity_receipts_not_caller_booleans(self) -> None:
        """Stage-1 stability is derived evidence, not two caller assertions."""

        parameters = inspect.signature(runner.record_stage_1_audit).parameters
        self.assertNotIn("runtime_identity_stable", parameters)
        self.assertNotIn("source_identity_stable", parameters)
        self.assertIn("execution_root", parameters)
        self.assertIn("runtime_revalidation_receipt_path", parameters)
        self.assertIn("source_revalidation_receipt_path", parameters)

    def test_artifact_root_builder_binds_ledger_command_and_selected_image(self) -> None:
        """An artifact cannot report a different launch command or container image."""

        builder = getattr(runner, "build_terminal_receipt_from_artifact_root", None)
        self.assertTrue(
            callable(builder),
            "runner must expose a ledger- and pool-bound artifact-root exporter",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(root)
            cell = contract["schedule"]["cells"][0]
            state_root = root / ".local" / "execution"
            paths = runner.initialize_execution_storage(state_root)
            ledger = state_root / "ledger.jsonl"
            checkpoint = state_root / "checkpoint.json"
            _record_attempt_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
            )
            runner.record_subject_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(contract, cell["cell_id"]),
                ownership_token_sha256="1" * 64,
                process_identity_sha256="2" * 64,
            )
            evaluator_container = _selected_container_identity(
                private_pool, _commitment(contract, cell)
            )
            runner.record_evaluator_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                evaluator_command_sha256="4" * 64,
                ownership_token_sha256="5" * 64,
                process_identity_sha256="6" * 64,
                container_identity_sha256=evaluator_container,
            )
            artifact_root = state_root / "artifacts" / cell["cell_id"] / "attempt-1"
            _artifact_receipt(
                contract, cell, artifact_root,
                container_identity_sha256=evaluator_container,
            )
            execution_path = artifact_root / "execution.json"
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            execution["command_sha256"] = "9" * 64
            execution["container_identity_sha256"] = "8" * 64
            execution["receipt_sha256"] = runner.digest(
                {key: value for key, value in execution.items() if key != "receipt_sha256"}
            )
            execution_path.write_text(
                json.dumps(execution, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(command|container|image|frozen launch)"
            ):
                builder(
                    contract,
                    private_pool,
                    ledger,
                    state_root,
                    cell_id=cell["cell_id"],
                    attempt=1,
                )

            state_root = root / ".local" / "execution"
            runner.initialize_execution_storage(state_root)
            (state_root / "ledger.jsonl").chmod(0o644)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(private mode|0600)"
            ):
                _record_attempt_started(
                    state_root / "ledger.jsonl",
                    state_root / "checkpoint.json",
                    contract,
                    live_seal,
                    private_pool,
                    cell_id=cell["cell_id"],
                    attempt=1,
                )
            self.assertTrue(paths["files"])

    def test_qualification_gate_identities_are_derived_from_qualifier_receipt(self) -> None:
        """Contract strings cannot stand in for pinned source/runtime/image derivation."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _contract, private_pool, gate, _live_seal = _qualified_live(root)
            receipt = gate["qualification_receipt"]
            selection = receipt["selection"]
            candidates = {item["slot"]: item for item in receipt["candidates"]}
            expected_runtime = runner.digest(receipt["runtime_observation"])
            expected_evaluator = runner.digest(
                {
                    key: receipt["source"][key]
                    for key in (
                        "evaluator_revision",
                        "evaluator_tree_sha256",
                        "evaluator_python",
                        "embedded_repolaunch_revision",
                        "repolaunch_tree_sha256",
                    )
                }
            )
            expected_source = runner.digest(receipt["source"])
            expected_images = runner.digest(
                [
                    {
                        "slot": item["slot"],
                        "resolved_image": candidates[item["slot"]]["resolved_image"],
                    }
                    for item in [*selection["primary"], *selection["alternates"]]
                ]
            )
            self.assertEqual(gate["runtime_identity"], expected_runtime)
            self.assertEqual(gate["evaluator_identity"], expected_evaluator)
            self.assertEqual(gate["source_identity"], expected_source)
            self.assertEqual(gate["image_pool_identity"], expected_images)

            mismatched = build_contract(
                private_pool,
                model="fixture-model",
                codex_version="fixture-version",
                runtime_identity="caller-runtime",
                source_identity="caller-source",
                qualification_receipt_sha256=receipt["state_sha256"],
                evaluator_identity="caller-evaluator",
                image_pool_identity="4" * 64,
                tool_configuration_identity="fixture-tools",
            )
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(derived|identity|qualifier)"
            ):
                runner.build_qualification_gate_from_receipt(
                    mismatched,
                    private_pool,
                    root / ".local" / "qualification.json",
                    root / ".local" / "qualification-raw",
                )
            forged_gate = deepcopy(gate)
            forged_gate["contract_sha256"] = mismatched["contract_sha256"]
            forged_gate["schedule_sha256"] = mismatched["schedule"]["schedule_sha256"]
            forged_gate["runtime_identity"] = "caller-runtime"
            forged_gate["source_identity"] = "caller-source"
            forged_gate["evaluator_identity"] = "caller-evaluator"
            forged_gate["image_pool_identity"] = "4" * 64
            forged_gate["qualification_gate_sha256"] = runner.digest(
                {
                    key: value
                    for key, value in forged_gate.items()
                    if key != "qualification_gate_sha256"
                }
            )
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(derived|identity|qualifier|authorize)"
            ):
                runner.build_live_seal(mismatched, private_pool, forged_gate)

    def test_qualification_gate_rejects_unlisted_stage_artifacts(self) -> None:
        """The frozen artifact map is exhaustive, not merely a checked subset."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, gate, _live_seal = _qualified_live(root)
            receipt_path = root / ".local" / "qualification.json"
            raw_root = root / ".local" / "qualification-raw"
            selected_slot = gate["qualification_receipt"]["selection"]["primary"][0][
                "slot"
            ]
            extra = raw_root / f"slot-{selected_slot:02d}" / STAGES[0] / "unlisted.log"
            extra.write_text("unlisted evidence\n", encoding="utf-8")
            extra.chmod(0o600)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(artifact map|artifact hash|unlisted)"
            ):
                runner.build_qualification_gate_from_receipt(
                    contract, private_pool, receipt_path, raw_root
                )

    def test_public_mutation_apis_mandate_local_containment_and_private_modes(self) -> None:
        """Callers cannot bypass initialization by supplying arbitrary writable paths."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(root)
            cell = contract["schedule"]["cells"][0]
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(.local|execution storage|private mode)"
            ):
                _record_attempt_started(
                    root / "public" / "ledger.jsonl",
                    root / "public" / "checkpoint.json",
                    contract,
                    live_seal,
                    private_pool,
                    cell_id=cell["cell_id"],
                    attempt=1,
                )

    def test_artifact_inputs_require_private_file_and_directory_modes(self) -> None:
        """An initialized root does not excuse world-readable raw evidence files."""

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            contract, private_pool, _gate, live_seal = _qualified_live(base)
            root = base / ".local" / "execution"
            runner.initialize_execution_storage(root)
            cell = contract["schedule"]["cells"][0]
            ledger = root / "ledger.jsonl"
            checkpoint = root / "checkpoint.json"
            _record_attempt_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
            )
            runner.record_subject_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(contract, cell["cell_id"]),
                ownership_token_sha256="1" * 64,
                process_identity_sha256="2" * 64,
            )
            evaluator_container = _selected_container_identity(
                private_pool, _commitment(contract, cell)
            )
            runner.record_evaluator_invocation_started(
                ledger, checkpoint, contract, live_seal, private_pool,
                cell_id=cell["cell_id"], attempt=1,
                evaluator_command_sha256="4" * 64,
                ownership_token_sha256="5" * 64,
                process_identity_sha256="6" * 64,
                container_identity_sha256=evaluator_container,
            )
            artifact_root = root / "artifacts" / cell["cell_id"] / "attempt-1"
            _artifact_receipt(
                contract,
                cell,
                artifact_root,
                container_identity_sha256=evaluator_container,
            )
            evaluator_path = artifact_root / "evaluator.json"
            evaluator_path.chmod(0o644)
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "(private mode|0600|artifact permission)"
            ):
                runner.build_terminal_receipt_from_artifact_root(
                    contract, private_pool, ledger, root,
                    cell_id=cell["cell_id"], attempt=1,
                )

if __name__ == "__main__":
    unittest.main()
