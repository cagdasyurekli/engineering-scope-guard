from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.evaluator_stable_qualification import (
    LANGUAGES, STAGES, build_receipt as build_qualification_receipt,
    next_qualification_stage, qualification_rank, record_stage, sha256_value,
    seal_receipt,
)
from engineering_scope_guard.reasoning_effort_v2 import (
    build_contract,
    build_private_pool,
    subject_command_identity,
    validate_analysis_terminal_envelope,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reasoning_effort_v2_runner", ROOT / "scripts/reasoning_effort_v2_runner.py"
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def tasks(count: int, *, offset: int = 0) -> list[dict[str, str]]:
    return [
        {
            "task_id": f"private-{number}",
            "repository": f"private/repository-{number}",
            "task_snapshot_sha256": f"{number % 16:x}" * 64,
            "resolved_image": f"private-image-{number}",
        }
        for number in range(offset + 1, offset + count + 1)
    ]


def qualification() -> dict:
    seed = "fixture-seed"
    revision = "d" * 40
    selected = []
    for language in LANGUAGES:
        for ordinal in range(6):
            instance_id = f"private-{language}-{ordinal}"
            selected.append({
                "instance_id": instance_id,
                "repo": f"private/repo-{language}-{ordinal}",
                "language": language,
                "docker_image": f"private/image-{language}-{ordinal}",
                "rank_commitment": qualification_rank(seed, revision, language, instance_id),
                "manifest_sha256": sha256_value({"image": instance_id}),
            })
    reserve = {
        "schema": "private-fixture",
        "source": {"dataset": "SWE-bench-Live/MultiLang", "revision": revision},
        "selection": {
            "seed": seed,
            "selected": selected,
            "selected_ids_sha256": sha256_value(sorted(item["instance_id"] for item in selected)),
        },
    }
    value = build_qualification_receipt(
        reserve, evaluator_revision="e" * 40, repolaunch_revision="r" * 40,
        dataset_file_sha256={"c.parquet": "f" * 64},
        evaluator_python={"python": "3.12", "executable_sha256": "a" * 64},
        codex_runtime={
            "codex_version": "fixture", "model": "fixture-model",
            "supported_reasoning_efforts": ["low", "medium"],
            "docker_client_server": {"Client": {"Version": "fixture"}},
        },
        execution_code_sha256={"qualifier.py": "b" * 64},
        evaluator_tree_sha256="c" * 64, repolaunch_tree_sha256="d" * 64,
    )
    for _ in range(16):
        candidate, _stage = next_qualification_stage(value)
        for stage in STAGES:
            stage_body = {
                "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
                "schema_version": 2, "slot": candidate["slot"], "stage": stage,
                "outcome": "pass", "classification": None, "details": {},
                "artifact_sha256": {},
            }
            stage_sha = sha256_value(stage_body)
            evidence = {
                "stage_receipt_sha256": stage_sha,
                "artifact_set_sha256": sha256_value({}), "wall_seconds": 1.0,
            }
            if stage == "q1_environment":
                evidence["resolved_image_ref"] = f"private/image-{candidate['slot']}@sha256:{candidate['slot']:064x}"
            record_stage(value, slot=candidate["slot"], stage=stage, outcome="pass", classification=None, evidence=evidence)
    return value


def frozen(*, canary_starts: int = 0) -> tuple[dict, dict]:
    qualified = qualification()
    candidates = {candidate["slot"]: candidate for candidate in qualified["candidates"]}
    selected = qualified["selection"]
    def pool_task(item: dict) -> dict[str, str]:
        candidate = candidates[item["slot"]]
        return {
            "task_id": item["instance_id"], "repository": item["repo"],
            "task_snapshot_sha256": candidate["manifest_sha256"],
            "resolved_image": item["resolved_image"],
        }
    private_pool = build_private_pool(
        [pool_task(item) for item in selected["primary"]],
        [pool_task(item) for item in selected["alternates"]],
    )
    source = qualified["source"]
    runtime_identity = digest(qualified["runtime_observation"])
    evaluator_identity = digest({
        key: source[key]
        for key in (
            "evaluator_revision", "evaluator_tree_sha256", "evaluator_python",
            "embedded_repolaunch_revision", "repolaunch_tree_sha256",
        )
    })
    source_identity = digest(source)
    image_pool_identity = digest([
        {"slot": item["slot"], "resolved_image": candidates[item["slot"]]["resolved_image"]}
        for item in [*selected["primary"], *selected["alternates"]]
    ])
    contract = build_contract(
        private_pool,
        model="fixture-model",
        codex_version="fixture-version",
        runtime_identity=runtime_identity,
        source_identity=source_identity,
        qualification_receipt_sha256=qualified["state_sha256"],
        evaluator_identity=evaluator_identity,
        image_pool_identity=image_pool_identity,
        tool_configuration_identity="fixture-tools",
        qualification_reliability_audit_sha256=(
            runner.build_pool_reliability_audit(qualified)[
                "pool_reliability_audit_sha256"
            ]
        ),
        maximum_contentless_canary_subject_invocation_starts=canary_starts,
    )
    return contract, private_pool


def live(contract: dict, private_pool: dict) -> tuple[dict, dict]:
    qualified = qualification()
    self_hash = qualified["state_sha256"]
    if self_hash != contract["source"]["qualification_receipt_sha256"]:
        raise AssertionError("qualification fixture drifted")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / ".local"
        root.mkdir(mode=0o700)
        receipt_path = root / "qualification.json"
        receipt_path.write_text(json.dumps(qualified, sort_keys=True) + "\n", encoding="utf-8")
        receipt_path.chmod(0o600)
        candidates = {candidate["slot"]: candidate for candidate in qualified["candidates"]}
        for item in [*qualified["selection"]["primary"], *qualified["selection"]["alternates"]]:
            candidate = candidates[item["slot"]]
            for stage in candidate["stages"]:
                body = {
                    "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
                    "schema_version": 2, "slot": candidate["slot"], "stage": stage["stage"],
                    "outcome": "pass", "classification": None, "details": {},
                    "artifact_sha256": {},
                }
                stage_receipt = {**body, "stage_receipt_sha256": sha256_value(body)}
                path = root / "raw" / f"slot-{candidate['slot']:02d}" / stage["stage"] / "stage-receipt.json"
                path.parent.mkdir(parents=True)
                for parent in (root / "raw", root / "raw" / f"slot-{candidate['slot']:02d}", path.parent):
                    parent.chmod(0o700)
                path.write_text(json.dumps(stage_receipt, sort_keys=True) + "\n", encoding="utf-8")
                path.chmod(0o600)
        gate = runner.build_qualification_gate_from_receipt(
            contract, private_pool, receipt_path, root / "raw"
        )
    return gate, runner.build_live_seal(contract, private_pool, gate)


def analysis_record(cell_id: str, classification: str = "accepted_completed") -> dict:
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


def absent_work_record(cell_id: str, classification: str) -> dict:
    record = analysis_record(cell_id, classification)
    for field in (*runner.INTEGER_WORK_FIELDS, *runner.FLOAT_WORK_FIELDS):
        record[field] = None
    return record


class State:
    def __init__(self, root: Path, contract: dict, private_pool: dict, seal: dict):
        self.root = root / ".local" / "execution"
        self.contract = contract
        self.private_pool = private_pool
        self.seal = seal
        runner.initialize_execution_storage(self.root)
        self.ledger = self.root / "ledger.jsonl"
        self.checkpoint = self.root / "checkpoint.json"
        self.receipts = self.root / "receipts"

    def commitment(self, cell: dict) -> str:
        projection = self.contract["source"]["private_pool"]["primary_slot_commitments"]
        return next(
            item["task_commitment_sha256"]
            for item in projection
            if item["population_slot"] == cell["population_slot"]
        )

    def disk_pass(self, cell: dict, *, attempt: int = 1) -> None:
        runner.record_disk_safety_checked(
            self.ledger,
            self.checkpoint,
            self.contract,
            self.seal,
            self.private_pool,
            cell_id=cell["cell_id"],
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

    def identity_receipts(self, *, runtime_pass: bool = True, source_pass: bool = True) -> tuple[Path, Path]:
        runtime_path = self.root / "runtime-revalidation.json"
        source_path = self.root / "source-revalidation.json"
        runtime_body = {
            "schema_name": runner.RUNTIME_REVALIDATION_SCHEMA, "schema_version": 1,
            "contract_sha256": self.contract["contract_sha256"],
            "live_seal_sha256": self.seal["live_seal_sha256"],
            "runtime_identity": self.contract["runtime"]["runtime_identity"],
            "status": "pass" if runtime_pass else "fail",
        }
        source_body = {
            "schema_name": runner.SOURCE_REVALIDATION_SCHEMA, "schema_version": 1,
            "contract_sha256": self.contract["contract_sha256"],
            "live_seal_sha256": self.seal["live_seal_sha256"],
            "source_identity": self.contract["source"]["source_identity"],
            "evaluator_identity": self.contract["source"]["evaluator_identity"],
            "image_pool_identity": self.contract["source"]["image_pool_identity"],
            "status": "pass" if source_pass else "fail",
        }
        for path, body in ((runtime_path, runtime_body), (source_path, source_body)):
            path.write_text(json.dumps({**body, "receipt_sha256": digest(body)}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            path.chmod(0o600)
        return runtime_path, source_path

    def stage_1_audit(self, *, runtime_pass: bool = True, source_pass: bool = True) -> dict:
        runtime_path, source_path = self.identity_receipts(
            runtime_pass=runtime_pass, source_pass=source_pass
        )
        return runner.record_stage_1_audit(
            self.ledger, self.checkpoint, self.receipts, self.contract,
            self.private_pool, self.seal, execution_root=self.root,
            runtime_revalidation_receipt_path=runtime_path,
            source_revalidation_receipt_path=source_path,
        )

    def complete(
        self, cell: dict, *, persist_before_start: bool = False,
        prestart_classification: str = "provider_api_infrastructure_failure",
        start_attempt: bool = True, start_subject: bool = True,
    ) -> dict:
        commitment = self.commitment(cell)
        command_identity = subject_command_identity(self.contract, cell["cell_id"])
        if start_attempt:
            self.disk_pass(cell)
            runner.record_attempt_started(
                self.ledger,
                self.checkpoint,
                self.contract,
                self.seal,
                self.private_pool,
                cell_id=cell["cell_id"],
                attempt=1,
            )
        if not persist_before_start and start_subject:
            runner.record_subject_invocation_started(
                self.ledger,
                self.checkpoint,
                self.contract,
                self.seal,
                self.private_pool,
                cell_id=cell["cell_id"],
                attempt=1,
                command_sha256=command_identity,
                ownership_token_sha256="a" * 64,
                process_identity_sha256="b" * 64,
            )
            runner.record_evaluator_invocation_started(
                self.ledger, self.checkpoint, self.contract, self.seal,
                self.private_pool, cell_id=cell["cell_id"], attempt=1,
                evaluator_command_sha256="d" * 64,
                ownership_token_sha256="e" * 64,
                process_identity_sha256="f" * 64,
                container_identity_sha256="9" * 64,
            )
        elif not persist_before_start:
            runner.record_evaluator_invocation_started(
                self.ledger, self.checkpoint, self.contract, self.seal,
                self.private_pool, cell_id=cell["cell_id"], attempt=1,
                evaluator_command_sha256="d" * 64,
                ownership_token_sha256="e" * 64,
                process_identity_sha256="f" * 64,
                container_identity_sha256="9" * 64,
            )
        status = prestart_classification if persist_before_start else "returned"
        classification = prestart_classification if persist_before_start else "accepted_completed"
        record = absent_work_record(cell["cell_id"], classification) if persist_before_start else analysis_record(cell["cell_id"])
        common = {
            "schema_version": 1, "contract_sha256": self.contract["contract_sha256"],
            "schedule_sha256": self.contract["schedule"]["schedule_sha256"],
            "cell_id": cell["cell_id"], "attempt": 1,
            "effective_task_commitment_sha256": commitment,
        }
        artifact_root = self.root / "artifacts" / cell["cell_id"] / "attempt-1"
        artifact_root.mkdir(parents=True, mode=0o700)
        for directory in (self.root / "artifacts", self.root / "artifacts" / cell["cell_id"], artifact_root):
            directory.chmod(0o700)
        task = next(task for task in [*self.private_pool["primaries"], *self.private_pool["alternates"]] if digest(task) == commitment)
        raw_hashes = {
            "subject_stdout_sha256": None, "subject_stderr_sha256": None,
            "prediction_sha256": None, "patch_sha256": None,
            "evaluator_stdout_sha256": None, "evaluator_stderr_sha256": None,
            "report_sha256": None, "results_sha256": None,
        }
        if not persist_before_start:
            raw_root = artifact_root / "raw"
            raw_root.mkdir(mode=0o700)
            contents = {
                "codex.jsonl": b"{}\n", "codex.stderr": b"",
                "prediction.json": b"{}\n", "patch.diff": b"",
                "evaluator.stdout": b"", "evaluator.stderr": b"",
                "evaluator-report.json": b"{}\n", "evaluator-results.json": b"{}\n",
            }
            field_by_name = {
                "codex.jsonl": "subject_stdout_sha256", "codex.stderr": "subject_stderr_sha256",
                "prediction.json": "prediction_sha256", "patch.diff": "patch_sha256",
                "evaluator.stdout": "evaluator_stdout_sha256",
                "evaluator.stderr": "evaluator_stderr_sha256",
                "evaluator-report.json": "report_sha256",
                "evaluator-results.json": "results_sha256",
            }
            for name, content in contents.items():
                path = raw_root / name
                path.write_bytes(content)
                path.chmod(0o600)
                raw_hashes[field_by_name[name]] = hashlib.sha256(content).hexdigest()
        bodies = {
            "execution.json": {
                **common, "schema_name": runner.EXECUTION_ARTIFACT_SCHEMA,
                "subject_invocation_started": not persist_before_start,
                "command_sha256": None if persist_before_start else command_identity,
                "status": status, "timed_out": False, "subject_exit_code": None if persist_before_start else 0,
                "ownership_token_sha256": None if persist_before_start else "a" * 64,
                "process_identity_sha256": None if persist_before_start else "b" * 64,
                "container_identity_sha256": None if persist_before_start else digest({"resolved_image": task["resolved_image"]}),
                **{field: raw_hashes[field] for field in (
                    "subject_stdout_sha256", "subject_stderr_sha256",
                    "prediction_sha256", "patch_sha256",
                )},
                "cleanup_receipt_sha256": None,
            },
            "evaluator.json": {
                **common, "schema_name": runner.EVALUATOR_ARTIFACT_SCHEMA,
                "evaluator_identity": self.contract["source"]["evaluator_identity"],
                "disposition": "not_run" if persist_before_start else "accepted", "anomaly_codes": [],
                **{field: raw_hashes[field] for field in (
                    "evaluator_stdout_sha256", "evaluator_stderr_sha256",
                    "report_sha256", "results_sha256",
                )},
                "invocation_started": not persist_before_start,
                "evaluator_command_sha256": None if persist_before_start else "d" * 64,
                "ownership_token_sha256": None if persist_before_start else "e" * 64,
                "process_identity_sha256": None if persist_before_start else "f" * 64,
                "container_identity_sha256": None if persist_before_start else "9" * 64,
            },
            "measurement.json": {
                **common, "schema_name": runner.MEASUREMENT_ARTIFACT_SCHEMA,
                "record_completeness": "absent" if persist_before_start else "complete",
                **{field: record[field] for field in (*runner.INTEGER_WORK_FIELDS, *runner.FLOAT_WORK_FIELDS)},
            },
        }
        for name, body in bodies.items():
            artifact = {**body, "receipt_sha256": digest(body)}
            (artifact_root / name).write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            (artifact_root / name).chmod(0o600)
        receipt = runner.build_terminal_receipt_from_artifact_root(
            self.contract, self.private_pool, self.ledger, self.root,
            cell_id=cell["cell_id"], attempt=1,
        )
        runner.persist_terminal_receipt(self.receipts, self.contract, receipt)
        return runner.reconcile_attempt(
            self.ledger,
            self.checkpoint,
            self.receipts,
            self.contract,
            self.private_pool,
            self.seal,
            cell_id=cell["cell_id"],
            attempt=1,
        )


class ReasoningEffortV2RunnerTests(unittest.TestCase):
    def test_phase_7_reliability_audit_is_deterministic_private_and_tamper_closed(self) -> None:
        receipt = qualification()
        for slot in (17, 25):
            candidate = receipt["candidates"][slot - 1]
            stage_body = {
                "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
                "schema_version": 2,
                "slot": slot,
                "stage": "q1_environment",
                "outcome": "fail",
                "classification": "infrastructure_timeout",
                "details": {},
                "artifact_sha256": {},
            }
            candidate.update(
                {
                    "status": "not_qualified",
                    "next_stage": None,
                    "classification": "infrastructure_timeout",
                    "stages": [
                        {
                            "stage": "q1_environment",
                            "outcome": "fail",
                            "classification": "infrastructure_timeout",
                            "evidence": {
                                "stage_receipt_sha256": sha256_value(stage_body),
                                "artifact_set_sha256": sha256_value({}),
                                "wall_seconds": 1.0,
                            },
                        }
                    ],
                }
            )
        seal_receipt(receipt)
        blocked = runner.build_pool_reliability_audit(receipt)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["investigation"]["status"], "required")
        self.assertTrue(blocked["investigation"]["cluster_presence_blocks_freeze"])
        resolutions = [
            {
                "finding_sha256": digest(finding),
                "disposition": "deterministic_cause_identified",
                "deterministic_cause": "shared frozen qualification infrastructure",
                "action": "retain evidence and freeze the shared dependency",
            }
            for finding in blocked["investigation"]["findings"]
        ]
        investigation = runner.build_pool_reliability_investigation(receipt, resolutions)
        audit = runner.build_pool_reliability_audit(receipt, investigation)
        runner.validate_pool_reliability_audit(receipt, audit)
        self.assertEqual(audit, runner.build_pool_reliability_audit(receipt, investigation))
        self.assertEqual(audit["aggregate_counts"]["not_qualified_candidates"], 2)
        self.assertEqual(audit["investigation"]["status"], "complete")
        self.assertFalse(audit["investigation"]["cluster_presence_blocks_freeze"])
        self.assertFalse(audit["infrastructure_findings_are_experiment_results"])
        self.assertTrue(any(
            finding["dimension"] in {"language", "platform", "evaluator_path"}
            and finding["count"] == 2
            for finding in audit["investigation"]["findings"]
        ))
        incomplete = resolutions[:-1]
        with self.assertRaisesRegex(ExperimentConfigurationError, "every finding"):
            runner.build_pool_reliability_investigation(receipt, incomplete)
        inconclusive = deepcopy(resolutions)
        inconclusive[0]["disposition"] = "inconclusive"
        with self.assertRaisesRegex(ExperimentConfigurationError, "inconclusive"):
            runner.build_pool_reliability_investigation(receipt, inconclusive)
        evidence_tamper = deepcopy(investigation)
        evidence_tamper["records"][0]["terminal_stage_evidence"][0][
            "stage_receipt_sha256"
        ] = "0" * 64
        evidence_tamper["investigation_sha256"] = digest(
            {key: value for key, value in evidence_tamper.items()
             if key != "investigation_sha256"}
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "evidence-unbound"):
            runner.build_pool_reliability_audit(receipt, evidence_tamper)
        altered = deepcopy(audit)
        altered["aggregate_counts"]["not_qualified_candidates"] = 1
        altered["pool_reliability_audit_sha256"] = digest(
            {key: value for key, value in altered.items()
             if key != "pool_reliability_audit_sha256"}
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "missing or inconsistent"):
            runner.validate_pool_reliability_audit(receipt, altered)

    def test_disk_safety_failure_stops_before_attempt_and_pass_is_replay_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cell = state.contract["schedule"]["cells"][0]
            failed = {
                "schema_name": "engineering-scope-guard.experiment-disk-safety-public",
                "schema_version": 1,
                "status": "fail",
                "policy_sha256": "6" * 64,
                "failures": ["free_space_below_execution_reserve"],
                "dynamic_host_metadata_withheld": True,
            }
            first = runner.record_disk_safety_checked(
                state.ledger, state.checkpoint, state.contract, state.seal,
                state.private_pool, cell_id=cell["cell_id"], attempt=1,
                receipt=failed,
            )
            self.assertEqual(
                runner.record_disk_safety_checked(
                    state.ledger, state.checkpoint, state.contract, state.seal,
                    state.private_pool, cell_id=cell["cell_id"], attempt=1,
                    receipt=failed,
                )["event_sha256"],
                first["event_sha256"],
            )
            events = runner.read_ledger(state.ledger, state.contract)
            self.assertEqual([event["event_type"] for event in events], ["disk_safety_checked"])
            self.assertEqual(
                runner.replay_attempt_state(
                    state.contract, runner._semantic(events)
                )["batch_stop_classification"],
                "durable_evidence_incomplete",
            )
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cell = state.contract["schedule"]["cells"][0]
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "disk-safety-enforcing"
            ):
                runner.append_ledger_event(
                    state.ledger,
                    state.checkpoint,
                    state.contract,
                    state.seal,
                    state.private_pool,
                    "attempt_started",
                    {
                        "cell_id": cell["cell_id"],
                        "attempt": 1,
                        "effective_task_commitment_sha256": state.commitment(cell),
                    },
                )

    def fixture(self, root: Path, *, canary_starts: int = 0) -> State:
        contract, private_pool = frozen(canary_starts=canary_starts)
        _gate, seal = live(contract, private_pool)
        return State(root, contract, private_pool, seal)

    def test_live_seal_is_separate_qualification_gated_and_drift_closed(self) -> None:
        contract, private_pool = frozen()
        before = deepcopy(contract)
        gate, seal = live(contract, private_pool)
        runner.validate_live_seal(contract, private_pool, seal)
        self.assertEqual(contract, before)
        self.assertFalse(contract["live_execution_authorized"])
        self.assertTrue(seal["execution_authorized"])

        changed_gate = deepcopy(gate)
        changed_gate["checks"]["runtime_identity_verified"] = False
        changed_gate["qualification_gate_sha256"] = digest(
            {
                key: value
                for key, value in changed_gate.items()
                if key != "qualification_gate_sha256"
            }
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "does not authorize"):
            runner.build_live_seal(contract, private_pool, changed_gate)

        changed_seal = deepcopy(seal)
        changed_seal["runtime_identity"] = "different"
        changed_seal["live_seal_sha256"] = digest(
            {key: value for key, value in changed_seal.items() if key != "live_seal_sha256"}
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "differs"):
            runner.validate_live_seal(contract, private_pool, changed_seal)

        forged_gate_binding = deepcopy(seal)
        forged_gate_binding["qualification_gate_sha256"] = "f" * 64
        forged_gate_binding["live_seal_sha256"] = digest(
            {
                key: value
                for key, value in forged_gate_binding.items()
                if key != "live_seal_sha256"
            }
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "differs"):
            runner.validate_live_seal(contract, private_pool, forged_gate_binding)

    def test_hash_chain_corruption_and_checkpoint_repair_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cell = state.contract["schedule"]["cells"][0]
            state.disk_pass(cell)
            runner.record_attempt_started(
                state.ledger,
                state.checkpoint,
                state.contract,
                state.seal,
                state.private_pool,
                cell_id=cell["cell_id"],
                attempt=1,
            )
            state.checkpoint.unlink()
            with self.assertRaisesRegex(ExperimentConfigurationError, "missing"):
                runner.read_checkpoint(state.ledger, state.checkpoint, state.contract)
            repaired = runner.read_checkpoint(
                state.ledger, state.checkpoint, state.contract, repair=True
            )
            self.assertEqual(repaired["event_count"], 2)

            event = json.loads(state.ledger.read_text(encoding="utf-8").splitlines()[-1])
            state.ledger.write_text(json.dumps(event, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "JSONL|hash chain"):
                runner.read_ledger(state.ledger, state.contract)

            event["payload"]["attempt"] = 2
            state.ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "hash chain"):
                runner.read_ledger(state.ledger, state.contract)

    def test_crash_reconciliation_never_duplicates_subject_start_and_rehashes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cell = state.contract["schedule"]["cells"][0]
            state.disk_pass(cell)
            runner.record_attempt_started(
                state.ledger,
                state.checkpoint,
                state.contract,
                state.seal,
                state.private_pool,
                cell_id=cell["cell_id"],
                attempt=1,
            )
            self.assertEqual(
                runner.reconcile_attempt(
                    state.ledger, state.checkpoint, state.receipts, state.contract,
                    state.private_pool, state.seal, cell_id=cell["cell_id"], attempt=1,
                )["action"],
                "start_subject",
            )
            runner.record_subject_invocation_started(
                state.ledger, state.checkpoint, state.contract, state.seal,
                state.private_pool, cell_id=cell["cell_id"], attempt=1,
                command_sha256=subject_command_identity(state.contract, cell["cell_id"]),
                ownership_token_sha256="a" * 64,
                process_identity_sha256="b" * 64,
            )
            self.assertEqual(
                runner.reconcile_attempt(
                    state.ledger, state.checkpoint, state.receipts, state.contract,
                    state.private_pool, state.seal, cell_id=cell["cell_id"], attempt=1,
                )["action"],
                "await_terminal_receipt",
            )
            with self.assertRaises(ExperimentConfigurationError):
                runner.record_subject_invocation_started(
                    state.ledger, state.checkpoint, state.contract, state.seal,
                    state.private_pool, cell_id=cell["cell_id"], attempt=1,
                    command_sha256=subject_command_identity(state.contract, cell["cell_id"]),
                    ownership_token_sha256="a" * 64,
                    process_identity_sha256="b" * 64,
                )
            self.assertEqual(
                state.complete(cell, start_attempt=False, start_subject=False)["action"],
                "cell_completed",
            )
            path = runner._receipt_path(state.receipts, cell["cell_id"], 1)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["analysis_record"]["input_tokens"] += 1
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ExperimentConfigurationError, "receipt"):
                runner.reconcile_attempt(
                    state.ledger, state.checkpoint, state.receipts, state.contract,
                    state.private_pool, state.seal, cell_id=cell["cell_id"], attempt=1,
                )

    def test_receipt_before_subject_start_reconciles_without_a_subject_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cell = state.contract["schedule"]["cells"][0]
            result = state.complete(cell, persist_before_start=True)
            self.assertEqual(result["action"], "await_attempt_2_authorization")
            events = runner.read_ledger(state.ledger, state.contract)
            self.assertNotIn(
                "subject_invocation_started", [event["event_type"] for event in events]
            )

    def test_terminal_attempt_1_gets_exact_outcome_blind_attempt_2_transition(self) -> None:
        for classification, expected_event in (
            ("provider_api_infrastructure_failure", "attempt_2_authorized"),
            ("frozen_task_binding_corrupt", "alternate_activated"),
        ):
            with self.subTest(classification=classification), tempfile.TemporaryDirectory() as directory:
                state = self.fixture(Path(directory))
                cell = state.contract["schedule"]["cells"][0]
                state.complete(
                    cell, persist_before_start=True,
                    prestart_classification=classification,
                )
                transition = runner.advance_outcome_blind_attempt_authorization(
                    state.ledger, state.checkpoint, state.contract,
                    state.seal, state.private_pool,
                )
                self.assertIsNotNone(transition)
                self.assertEqual(transition["event_type"], expected_event)
                self.assertIsNone(
                    runner.advance_outcome_blind_attempt_authorization(
                        state.ledger, state.checkpoint, state.contract,
                        state.seal, state.private_pool,
                    )
                )
                replay = runner.replay_attempt_state(
                    state.contract,
                    runner._semantic(runner.read_ledger(state.ledger, state.contract)),
                )
                self.assertEqual(replay["next_cell_id"], cell["cell_id"])
                if expected_event == "alternate_activated":
                    payload = transition["payload"]
                    self.assertEqual(payload["alternate_ordinal"], 1)
                    self.assertFalse(payload["subject_outcome_used"])
                    self.assertFalse(payload["outcome_direction_inspected"])

    def test_terminal_receipt_rejects_non_public_anomaly_and_nonfinite_work(self) -> None:
        for mutation in ("anomaly", "wall"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                state = self.fixture(Path(directory))
                cell = state.contract["schedule"]["cells"][0]
                state.complete(cell)
                receipt = runner._load_receipt(state.receipts, state.contract, cell["cell_id"], 1)
                assert receipt is not None
                if mutation == "anomaly":
                    receipt["evaluator_artifact"]["anomaly_codes"] = ["raw private evaluator message"]
                    receipt["analysis_record"]["evaluator_anomalies"] = ["raw private evaluator message"]
                    artifact = receipt["evaluator_artifact"]
                    artifact["receipt_sha256"] = digest({key: value for key, value in artifact.items() if key != "receipt_sha256"})
                    receipt["evaluator_receipt_sha256"] = __import__("hashlib").sha256(runner._canonical_artifact_bytes(artifact)).hexdigest()
                else:
                    receipt["measurement_artifact"]["wall_seconds"] = float("inf")
                    receipt["analysis_record"]["wall_seconds"] = float("inf")
                    artifact = receipt["measurement_artifact"]
                    artifact["receipt_sha256"] = digest({key: value for key, value in artifact.items() if key != "receipt_sha256"})
                    receipt["measurement_receipt_sha256"] = __import__("hashlib").sha256(runner._canonical_artifact_bytes(artifact)).hexdigest()
                receipt["terminal_receipt_sha256"] = digest({key: value for key, value in receipt.items() if key != "terminal_receipt_sha256"})
                with self.assertRaises(ExperimentConfigurationError):
                    runner.validate_terminal_receipt(state.contract, receipt)

    def test_stage_1_blocks_cell_5_until_content_free_pass_and_fail_is_terminal(self) -> None:
        for should_pass in (True, False):
            with self.subTest(should_pass=should_pass), tempfile.TemporaryDirectory() as directory:
                state = self.fixture(Path(directory))
                cells = state.contract["schedule"]["cells"]
                for cell in cells[:4]:
                    self.assertEqual(state.complete(cell)["action"], "cell_completed")
                with self.assertRaisesRegex(ExperimentConfigurationError, "Stage-1 boundary"):
                    state.disk_pass(cells[4])
                audit = state.stage_1_audit(runtime_pass=should_pass)
                self.assertEqual(audit["status"], "pass" if should_pass else "fail")
                self.assertFalse(audit["outcome_fields_inspected"])
                self.assertFalse(audit["outcome_values_emitted"])
                if should_pass:
                    state.disk_pass(cells[4])
                    runner.record_attempt_started(
                        state.ledger, state.checkpoint, state.contract, state.seal,
                        state.private_pool, cell_id=cells[4]["cell_id"], attempt=1,
                    )
                else:
                    with self.assertRaisesRegex(ExperimentConfigurationError, "terminal"):
                        state.disk_pass(cells[4])

    def test_terminal_export_is_ledger_derived_and_bridge_forgery_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            for cell in state.contract["schedule"]["cells"][:4]:
                state.complete(cell)
            state.stage_1_audit(runtime_pass=False)
            envelope = runner.export_analysis_terminal_envelope(
                state.contract, state.private_pool, state.ledger, state.receipts, state.seal
            )
            validated = validate_analysis_terminal_envelope(state.contract, envelope)
            self.assertEqual(validated["terminal_status"], "invalid_terminated")
            self.assertFalse(validated["protocol_valid"])
            self.assertEqual(len(validated["records"]), 4)
            self.assertEqual(
                validated["subject_start_accounting"],
                {
                    "canary_subject_invocation_starts": 0,
                    "experiment_subject_invocation_starts": 4,
                    "total_subject_invocation_starts": 4,
                },
            )
            self.assertEqual(
                validated["repository_commitment_source"],
                "task_commitment_sha256_under_frozen_global_repository_uniqueness",
            )

            forged = deepcopy(envelope)
            forged["effective_assignments"][0]["repository_commitment_sha256"] = "f" * 64
            forged["envelope_sha256"] = digest(
                {key: value for key, value in forged.items() if key != "envelope_sha256"}
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "assignment"):
                validate_analysis_terminal_envelope(state.contract, forged)

            outcome_forgery = deepcopy(envelope)
            outcome_forgery["records"][0]["termination"] = "evaluator_test_failure"
            outcome_forgery["records"][0]["terminal_receipt_sha256"] = "1" * 64
            outcome_forgery["records"][0]["evaluator_receipt_sha256"] = "2" * 64
            outcome_forgery["envelope_sha256"] = digest(
                {
                    key: value
                    for key, value in outcome_forgery.items()
                    if key != "envelope_sha256"
                }
            )
            self.assertEqual(
                outcome_forgery["receipt_set_sha256"], envelope["receipt_set_sha256"]
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "analysis record"):
                validate_analysis_terminal_envelope(state.contract, outcome_forgery)

            fully_resealed_receipt = deepcopy(envelope)
            projection = fully_resealed_receipt["receipt_projections"][0]
            projection["classification"] = "evaluator_test_failure"
            projection["analysis_record"]["termination"] = "evaluator_test_failure"
            projection["evaluator_receipt_sha256"] = "2" * 64
            projection["terminal_receipt_sha256"] = digest(
                {
                    key: value
                    for key, value in projection.items()
                    if key != "terminal_receipt_sha256"
                }
            )
            fully_resealed_receipt["records"][0] = runner.terminal_receipt_projection(
                projection
            )
            fully_resealed_receipt["envelope_sha256"] = digest(
                {
                    key: value
                    for key, value in fully_resealed_receipt.items()
                    if key != "envelope_sha256"
                }
            )
            with self.assertRaisesRegex(ExperimentConfigurationError, "receipt"):
                validate_analysis_terminal_envelope(state.contract, fully_resealed_receipt)

    def test_terminal_export_binds_one_actual_ledger_canary_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory), canary_starts=1)
            runner.append_ledger_event(
                state.ledger,
                state.checkpoint,
                state.contract,
                state.seal,
                state.private_pool,
                "canary_subject_invocation_started",
                {"evidence_sha256": "a" * 64},
            )
            for cell in state.contract["schedule"]["cells"][:4]:
                state.complete(cell)
            state.stage_1_audit(runtime_pass=False)
            envelope = runner.export_analysis_terminal_envelope(
                state.contract,
                state.private_pool,
                state.ledger,
                state.receipts,
                state.seal,
            )
            self.assertEqual(
                envelope["subject_start_accounting"],
                {
                    "canary_subject_invocation_starts": 1,
                    "experiment_subject_invocation_starts": 4,
                    "total_subject_invocation_starts": 5,
                },
            )
            forged = deepcopy(envelope)
            forged["subject_start_accounting"][
                "canary_subject_invocation_starts"
            ] = 0
            forged["envelope_sha256"] = digest(
                {
                    key: value
                    for key, value in forged.items()
                    if key != "envelope_sha256"
                }
            )
            with self.assertRaisesRegex(
                ExperimentConfigurationError, "subject-start accounting"
            ):
                validate_analysis_terminal_envelope(state.contract, forged)

    def test_pre_stage_terminal_stop_exports_with_no_stage_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cell = state.contract["schedule"]["cells"][0]
            self.assertEqual(
                state.complete(
                    cell, persist_before_start=True,
                    prestart_classification="harness_failure",
                )["action"],
                "batch_stopped",
            )
            envelope = runner.export_analysis_terminal_envelope(
                state.contract, state.private_pool, state.ledger, state.receipts, state.seal
            )
            self.assertIsNone(envelope["stage_1_audit_sha256"])
            validate_analysis_terminal_envelope(state.contract, envelope)

    def test_complete_terminal_export_covers_every_frozen_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = self.fixture(Path(directory))
            cells = state.contract["schedule"]["cells"]
            for index, cell in enumerate(cells):
                state.complete(cell)
                if index == 3:
                    audit = state.stage_1_audit()
                    self.assertEqual(audit["status"], "pass")
            envelope = runner.export_analysis_terminal_envelope(
                state.contract, state.private_pool, state.ledger, state.receipts, state.seal
            )
            validated = validate_analysis_terminal_envelope(state.contract, envelope)
            self.assertEqual(validated["terminal_status"], "complete")
            self.assertTrue(validated["protocol_valid"])
            self.assertEqual(len(validated["records"]), len(cells))


if __name__ == "__main__":
    unittest.main()
