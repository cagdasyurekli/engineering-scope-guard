from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from engineering_scope_guard.evaluator_stable_qualification import (
    seal_receipt,
    sha256_value,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v1 import USAGE_FIELDS
from scripts import reasoning_effort_v2_freeze as freeze_layer
from scripts import reasoning_effort_v2_runner as durable
from engineering_scope_guard.reasoning_effort_v2_terminal import _safe_runtime_projection
from tests.test_reasoning_effort_v2_runner import qualification as qualification_fixture


def _canonical(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cursor = path.parent
    while cursor.name != ".local":
        cursor.chmod(0o700)
        cursor = cursor.parent
    cursor.chmod(0o700)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


class ReasoningEffortV2FreezeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.local = self.root / ".local"
        self.local.mkdir(mode=0o700)
        self.execution_root = self.local / "execution"
        self.receipt_path = self.local / "qualification" / "receipt.json"
        self.raw_root = self.local / "qualification" / "raw"
        self.codex_binary = self.root / "codex"
        self.codex_binary.write_bytes(b"fixture codex binary\n")
        self.codex_binary.chmod(0o700)
        self.model_catalog = self.root / "models.json"
        self.model_catalog.write_text("{}\n", encoding="utf-8")
        self.evaluator_python = self.root / "python"
        self.evaluator_python.write_bytes(b"fixture evaluator python\n")
        self.evaluator_python.chmod(0o700)
        self.dataset_root = self.root / "dataset"
        self.dataset_root.mkdir()
        self.runtime = {
            "codex_version": "codex-cli 0.151.0",
            "codex_executable_sha256": hashlib.sha256(
                self.codex_binary.read_bytes()
            ).hexdigest(),
            "model_catalog_sha256": hashlib.sha256(
                self.model_catalog.read_bytes()
            ).hexdigest(),
            "model": "gpt-5.6-sol",
            "supported_reasoning_efforts": ["low", "medium"],
            "docker_client_server": {"Client": {"Version": "fixture"}},
        }
        self.qualification = self._terminal_qualification()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _terminal_qualification(self) -> dict:
        receipt = qualification_fixture()
        receipt["runtime_observation"] = deepcopy(self.runtime)
        seal_receipt(receipt)
        _canonical(self.receipt_path, receipt)
        candidates = {item["slot"]: item for item in receipt["candidates"]}
        selected = [*receipt["selection"]["primary"], *receipt["selection"]["alternates"]]
        for item in selected:
            candidate = candidates[item["slot"]]
            for stage in candidate["stages"]:
                body = {
                    "schema_name": "engineering-scope-guard.evaluator-stable-stage-receipt",
                    "schema_version": 2,
                    "slot": candidate["slot"],
                    "stage": stage["stage"],
                    "outcome": "pass",
                    "classification": None,
                    "details": {},
                    "artifact_sha256": {},
                }
                stage_receipt = {
                    **body,
                    "stage_receipt_sha256": sha256_value(body),
                }
                _canonical(
                    self.raw_root / f"slot-{candidate['slot']:02d}"
                    / stage["stage"] / "stage-receipt.json",
                    stage_receipt,
                )
        return receipt

    def _task_freezer(self, **kwargs: object) -> dict[str, str]:
        slot = int(kwargs["candidate_slot"])
        candidate = self.qualification["candidates"][slot - 1]
        return {
            "task_id": candidate["instance_id"],
            "repository": candidate["repo"],
            "language": candidate["language"],
            "base_commit": f"base-{slot}",
            "docker_image": candidate["docker_image"],
            "resolved_image": candidate["resolved_image"],
            "problem_statement_sha256": f"{slot % 16:x}" * 64,
            "task_snapshot_sha256": candidate["manifest_sha256"],
            "source_row_identity_sha256": digest({"slot": slot}),
        }

    def _freeze(
        self, *, runtime: dict | None = None,
        reliability_investigation_path: Path | None = None,
    ) -> dict:
        return freeze_layer.freeze(
            qualification_receipt_path=self.receipt_path,
            qualification_raw_root=self.raw_root,
            execution_root=self.execution_root,
            root=self.root,
            evaluator_python=self.evaluator_python,
            dataset_root=self.dataset_root,
            codex_binary=self.codex_binary,
            model_catalog=self.model_catalog,
            reliability_investigation_path=reliability_investigation_path,
            runtime_observer=lambda _binary, _catalog: deepcopy(runtime or self.runtime),
            task_freezer=self._task_freezer,
        )

    def _authority(self) -> dict:
        return json.loads((self.execution_root / "canary-authority.json").read_text())

    def _canary(self, *, events: list[dict] | None = None) -> dict:
        authority = self._authority()
        lifecycle_path = self.execution_root / "canary-ledger.jsonl"
        lifecycle = durable.replay_canary_lifecycle(lifecycle_path, authority)
        if lifecycle["reservation"] is None:
            durable.reserve_canary_start(
                lifecycle_path, authority, ownership_nonce_sha256="9" * 64
            )
            durable.attach_canary_process(
                lifecycle_path,
                authority,
                pid=12345,
                os_start_identity="fixture-process-start",
                process_identity_sha256="8" * 64,
            )
            lifecycle = durable.replay_canary_lifecycle(lifecycle_path, authority)
        if events is None:
            usage = {
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "cache_write_input_tokens": 5,
                "output_tokens": 20,
                "reasoning_output_tokens": 4,
            }
            events = [
                {"type": "thread.started", "thread_id": "contentless-canary-thread"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "CANARY"},
                },
                {"type": "turn.completed", "usage": usage},
            ]
        body = {
            "schema_name": freeze_layer.CANARY_RECEIPT_SCHEMA,
            "schema_version": freeze_layer.SCHEMA_VERSION,
            "canary_authority_sha256": authority["canary_authority_sha256"],
            "contract_sha256": authority["contract_sha256"],
            "subject_invocation_starts": 1,
            "command_sha256": authority["command_sha256"],
            "codex_binary_sha256": authority["codex_binary_sha256"],
            "codex_version": authority["codex_version"],
            "model": authority["model"],
            "reasoning_effort": authority["reasoning_effort"],
            "runtime_identity": authority["runtime_identity"],
            "reservation_event_sha256": lifecycle["reservation"]["event_sha256"],
            "ownership_nonce_sha256": lifecycle["reservation"]["payload"][
                "ownership_nonce_sha256"
            ],
            "process_event_sha256": lifecycle["process"]["event_sha256"],
            "process_identity_sha256": lifecycle["process"]["payload"][
                "process_identity_sha256"
            ],
            "prompt_sha256": authority["prompt_sha256"],
            "exit_code": 0,
            "timed_out": False,
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "events": events,
        }
        receipt = {**body, "canary_receipt_sha256": digest(body)}
        if lifecycle["terminal"] is None:
            durable.finish_canary_lifecycle(
                lifecycle_path,
                authority,
                status="success",
                canary_receipt_sha256=receipt["canary_receipt_sha256"],
            )
        return receipt

    def _verify(self, canary_path: Path) -> dict:
        return freeze_layer.verify(
            qualification_receipt_path=self.receipt_path,
            qualification_raw_root=self.raw_root,
            execution_root=self.execution_root,
            canary_receipt_path=canary_path,
            codex_binary=self.codex_binary,
            model_catalog=self.model_catalog,
            runtime_observer=lambda _binary, _catalog: deepcopy(self.runtime),
        )

    def test_terminal_receipt_freezes_deterministically_without_cell_authority(self) -> None:
        first = self._freeze()
        second = self._freeze()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "awaiting_contentless_canary")
        self.assertEqual((first["primary_count"], first["alternate_count"]), (12, 4))
        contract = json.loads((self.execution_root / "contract.json").read_text())
        self.assertEqual(contract["runtime"]["codex_version"], "codex-cli 0.151.0")
        self.assertEqual(
            contract["runtime"]["codex_version"],
            _safe_runtime_projection(self.qualification)["codex_version"],
        )
        self.assertTrue((self.execution_root / "pool-reliability-audit.json").is_file())
        self.assertEqual(
            first["pool_reliability_audit_sha256"],
            contract["source"]["qualification_reliability_audit_sha256"],
        )
        self.assertEqual(first["cell_count"], 48)
        self.assertIsNone(first["live_seal_sha256"])
        self.assertFalse((self.execution_root / "live-seal.json").exists())
        authority = self._authority()
        self.assertFalse(authority["cell_execution_authorized"])
        contract = json.loads((self.execution_root / "contract.json").read_text())
        self.assertEqual(
            contract["runtime"]["tool_configuration_identity"],
            freeze_layer._tool_configuration_identity(contract),
        )
        self.assertEqual(authority["sandbox"], "workspace-write")
        self.assertEqual(authority["prompt_utf8"].encode(), freeze_layer.CANARY_PROMPT)
        self.assertEqual(authority["maximum_subject_invocation_starts"], 1)
        self.assertTrue(authority["counts_toward_goal_maximum_56"])
        self.assertEqual(authority["remaining_subject_start_capacity"], 55)
        for path in self.execution_root.rglob("*"):
            expected = 0o700 if path.is_dir() else 0o600
            self.assertEqual(path.stat().st_mode & 0o777, expected)
        safe_bytes = json.dumps(first, sort_keys=True).encode()
        for candidate in self.qualification["candidates"][:16]:
            self.assertNotIn(candidate["instance_id"].encode(), safe_bytes)
            self.assertNotIn(candidate["repo"].encode(), safe_bytes)

    def test_clustered_reliability_failures_require_exact_private_investigation(self) -> None:
        for slot in (17, 25):
            candidate = self.qualification["candidates"][slot - 1]
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
        seal_receipt(self.qualification)
        _canonical(self.receipt_path, self.qualification)
        blocked = durable.build_pool_reliability_audit(self.qualification)
        self.assertEqual(blocked["status"], "blocked")
        with self.assertRaisesRegex(
            ExperimentConfigurationError, "clusters require a complete private investigation"
        ):
            self._freeze()

        resolutions = [
            {
                "finding_sha256": digest(finding),
                "disposition": "deterministic_cause_identified",
                "deterministic_cause": "shared frozen qualification infrastructure",
                "action": "retain and bind the terminal infrastructure evidence",
            }
            for finding in blocked["investigation"]["findings"]
        ]
        investigation = durable.build_pool_reliability_investigation(
            self.qualification, resolutions
        )
        investigation_path = self.local / "phase-7-investigation.json"
        _canonical(investigation_path, investigation)
        summary = self._freeze(reliability_investigation_path=investigation_path)
        persisted = json.loads(
            (self.execution_root / "pool-reliability-audit.json").read_text()
        )
        self.assertEqual(persisted["status"], "pass")
        self.assertEqual(persisted["investigation"]["status"], "complete")
        self.assertEqual(
            persisted["investigation"]["artifact_sha256"],
            investigation["investigation_sha256"],
        )
        self.assertEqual(
            summary["pool_reliability_audit_sha256"],
            persisted["pool_reliability_audit_sha256"],
        )

        tampered = deepcopy(investigation)
        tampered["records"][0]["terminal_stage_evidence"][0][
            "artifact_set_sha256"
        ] = "0" * 64
        tampered["investigation_sha256"] = digest(
            {key: value for key, value in tampered.items()
             if key != "investigation_sha256"}
        )
        tampered_path = self.local / "phase-7-investigation-tampered.json"
        _canonical(tampered_path, tampered)
        with self.assertRaisesRegex(ExperimentConfigurationError, "evidence-unbound"):
            freeze_layer.freeze(
                qualification_receipt_path=self.receipt_path,
                qualification_raw_root=self.raw_root,
                execution_root=self.local / "tampered-execution",
                root=self.root,
                evaluator_python=self.evaluator_python,
                dataset_root=self.dataset_root,
                codex_binary=self.codex_binary,
                model_catalog=self.model_catalog,
                reliability_investigation_path=tampered_path,
                runtime_observer=lambda _binary, _catalog: deepcopy(self.runtime),
                task_freezer=self._task_freezer,
            )

    def test_rejects_in_progress_and_insufficient_qualification(self) -> None:
        for status in ("in_progress", "insufficient"):
            with self.subTest(status=status):
                receipt = deepcopy(self.qualification)
                receipt["status"] = status
                receipt["selection"] = None
                for candidate in receipt["candidates"][9:]:
                    candidate["resolved_image"] = None
                    candidate["classification"] = None
                    candidate["stages"] = []
                    candidate["status"] = "pending"
                    candidate["next_stage"] = "q1_environment"
                if status == "insufficient":
                    for candidate in receipt["candidates"][9:]:
                        candidate["classification"] = "build_environment_failure"
                        candidate["stages"] = [{
                            "stage": "q1_environment",
                            "outcome": "fail",
                            "classification": "build_environment_failure",
                            "evidence": {"stage_receipt_sha256": "f" * 64},
                        }]
                        candidate["status"] = "not_qualified"
                        candidate["next_stage"] = None
                seal_receipt(receipt)
                _canonical(self.receipt_path, receipt)
                with self.assertRaisesRegex(
                    ExperimentConfigurationError, "not stable_pool_ready"
                ):
                    self._freeze()
        _canonical(self.receipt_path, self.qualification)

    def test_rejects_current_runtime_mismatch(self) -> None:
        changed = deepcopy(self.runtime)
        changed["codex_version"] = "codex-cli 0.152.0"
        with self.assertRaisesRegex(ExperimentConfigurationError, "runtime differs"):
            self._freeze(runtime=changed)
        self.codex_binary.write_bytes(b"different fixture codex binary\n")
        with self.assertRaisesRegex(ExperimentConfigurationError, "binary.*hash"):
            self._freeze()

    def test_valid_canary_grants_live_seal_and_counts_one_start(self) -> None:
        self._freeze()
        incoming = self.execution_root / "incoming-canary.json"
        _canonical(incoming, self._canary())
        result = self._verify(incoming)
        self.assertEqual(result["status"], "live_authorized")
        self.assertEqual(result["canary_subject_invocation_starts"], 1)
        self.assertIsNotNone(result["live_seal_sha256"])
        contract = json.loads((self.execution_root / "contract.json").read_text())
        events = durable.read_ledger(self.execution_root / "ledger.jsonl", contract)
        self.assertEqual([item["event_type"] for item in events], [
            "canary_lifecycle_imported"
        ])
        self.assertEqual(self._verify(incoming), result)

    def test_rejects_a_different_second_canary(self) -> None:
        self._freeze()
        first = self.execution_root / "incoming-one.json"
        _canonical(first, self._canary())
        self._verify(first)
        second_value = self._canary()
        second_value["events"][0]["thread_id"] = "different-thread"
        body = {key: value for key, value in second_value.items()
                if key != "canary_receipt_sha256"}
        second_value["canary_receipt_sha256"] = digest(body)
        second = self.execution_root / "incoming-two.json"
        _canonical(second, second_value)
        with self.assertRaisesRegex(
            ExperimentConfigurationError, "different second|exactly-once durable"
        ):
            self._verify(second)

    def test_rejects_malformed_event_and_usage_evidence(self) -> None:
        self._freeze()
        private_pool = json.loads((self.execution_root / "private-pool.json").read_text())
        authority = self._authority()
        bad_tool = self._canary()
        bad_tool["events"].insert(-1, {
            "type": "item.completed",
            "item": {"type": "command_execution", "command": "pwd"},
        })
        body = {key: value for key, value in bad_tool.items()
                if key != "canary_receipt_sha256"}
        bad_tool["canary_receipt_sha256"] = digest(body)
        with self.assertRaisesRegex(ExperimentConfigurationError, "command, tool"):
            freeze_layer.validate_canary_receipt(bad_tool, authority, private_pool)
        bad_usage = self._canary()
        del bad_usage["events"][-1]["usage"][USAGE_FIELDS[-1]]
        body = {key: value for key, value in bad_usage.items()
                if key != "canary_receipt_sha256"}
        bad_usage["canary_receipt_sha256"] = digest(body)
        with self.assertRaises(ExperimentConfigurationError):
            freeze_layer.validate_canary_receipt(bad_usage, authority, private_pool)

    def test_rejects_private_task_identity_in_canary(self) -> None:
        self._freeze()
        private_pool = json.loads((self.execution_root / "private-pool.json").read_text())
        authority = self._authority()
        canary = self._canary()
        canary["events"][2]["item"]["text"] = private_pool["primaries"][0]["task_id"]
        body = {key: value for key, value in canary.items()
                if key != "canary_receipt_sha256"}
        canary["canary_receipt_sha256"] = digest(body)
        with self.assertRaisesRegex(ExperimentConfigurationError, "private task"):
            freeze_layer.validate_canary_receipt(canary, authority, private_pool)

    def test_rejects_symlinked_candidate_receipt(self) -> None:
        self._freeze()
        target = self.execution_root / "target.json"
        _canonical(target, self._canary())
        link = self.execution_root / "incoming-link.json"
        link.symlink_to(target)
        with self.assertRaises(ExperimentConfigurationError):
            self._verify(link)

    def test_canary_crash_boundaries_are_terminal_and_never_relaunch(self) -> None:
        self._freeze()
        authority = self._authority()
        ledger = self.execution_root / "canary-ledger.jsonl"
        reservation = durable.reserve_canary_start(
            ledger, authority, ownership_nonce_sha256="6" * 64
        )
        durable.finish_canary_lifecycle(
            ledger, authority, status="failure", failure_code="crash_before_spawn"
        )
        state = durable.replay_canary_lifecycle(ledger, authority)
        self.assertEqual(state["terminal_status"], "failure")
        self.assertFalse(state["may_launch"])
        self.assertEqual(state["reservation"]["event_sha256"], reservation["event_sha256"])
        with self.assertRaisesRegex(ExperimentConfigurationError, "second canary"):
            durable.reserve_canary_start(
                ledger, authority, ownership_nonce_sha256="5" * 64
            )

    def test_canary_attached_timeout_is_terminal_failure(self) -> None:
        self._freeze()
        authority = self._authority()
        ledger = self.execution_root / "canary-ledger.jsonl"
        durable.reserve_canary_start(ledger, authority, ownership_nonce_sha256="4" * 64)
        durable.attach_canary_process(
            ledger, authority, pid=44, os_start_identity="start-44",
            process_identity_sha256="3" * 64,
        )
        durable.finish_canary_lifecycle(
            ledger, authority, status="failure", failure_code="timeout"
        )
        self.assertEqual(
            durable.replay_canary_lifecycle(ledger, authority)["terminal_status"],
            "failure",
        )

    def test_canary_crash_reconciliation_uses_exact_process_identity(self) -> None:
        self._freeze()
        authority = self._authority()
        ledger = self.execution_root / "canary-ledger.jsonl"
        durable.reserve_canary_start(ledger, authority, ownership_nonce_sha256="2" * 64)
        durable.attach_canary_process(
            ledger, authority, pid=22, os_start_identity="start-22",
            process_identity_sha256="1" * 64,
        )
        running = durable.reconcile_canary_process(
            ledger,
            authority,
            process_observer=lambda _pid: {
                "pid": 22,
                "os_start_identity": "start-22",
                "process_identity_sha256": "1" * 64,
                "status": "running",
            },
        )
        self.assertIsNone(running["terminal_status"])
        stopped = durable.reconcile_canary_process(
            ledger,
            authority,
            process_observer=lambda _pid: {
                "pid": 22,
                "os_start_identity": "start-22",
                "process_identity_sha256": "1" * 64,
                "status": "not_running",
            },
        )
        self.assertEqual(stopped["terminal_status"], "failure")


if __name__ == "__main__":
    unittest.main()
