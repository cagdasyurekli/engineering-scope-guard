from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from engineering_scope_guard.reasoning_effort_v1 import (
    append_event,
    build_contract,
    record_attempt_start,
    read_attempt_ledger,
)
from scripts.reasoning_effort_v1_runner import (
    ATTEMPT_2_INFRASTRUCTURE_CLASSES,
    _classify_and_transition,
    _attempt_roots,
    _codex_executable_identity,
    _environment,
    _record_subject_invocation_start,
    _record_subject_invocation_return,
    _persist_receipt,
    _require_clean_worktree,
    _validate_prompt_bytes,
    _validate_persisted_receipt,
    authorize_stage_2,
    reconcile_interrupted_attempt,
    parse_subject_trace,
    runner_status,
    _task_snapshot,
    classify_evaluator_attempt,
    cleanup_interrupted_attempt_auth,
    docker_manifest_sha256,
    subject_command,
    validate_authorization,
    validate_subject_commands,
)


def fixture_tasks() -> list[dict[str, str]]:
    return [
        {
            "task_id": f"task-{number}",
            "repository": f"owner/repo-{number}",
            "task_snapshot_sha256": f"{number:x}" * 64,
        }
        for number in range(1, 9)
    ]


def fixture_contract() -> dict:
    return build_contract(
        fixture_tasks(),
        model="gpt-5.6-sol",
        codex_version="0.151.0",
        runtime_identity="runtime-fixture",
        source_revision="dataset-fixture",
        evaluator_revision="evaluator-fixture",
        qualification_subject_executions=1,
    )


def fixture_authorization() -> dict:
    runtime = {
        "model": "gpt-5.6-sol",
        "codex_version": "0.151.0",
        "reasoning_efforts": ["low", "medium"],
        "model_catalog_sha256": "1" * 64,
        "codex_executable": {
            "resolved_path_sha256": "3" * 64,
            "file_sha256": "4" * 64,
        },
        "docker_environment": {"fixture": True},
        "subject_interface": {
            "one_fresh_codex_exec_per_cell": True,
            "sandbox": "workspace-write",
            "subject_network_access": False,
            "user_config_loaded": False,
            "user_rules_loaded": False,
            "browser_apps_plugins_multi_agent_disabled": True,
        },
    }
    runtime["runtime_identity"] = digest(runtime)
    value = {
        "schema_name": "engineering-scope-guard.reasoning-effort-v1-execution-authorization",
        "schema_version": 1,
        "status": "frozen-authorized",
        "execution_authorized": True,
        "allowed_attempt_2_classes": sorted(ATTEMPT_2_INFRASTRUCTURE_CLASSES),
        "binding": {},
        "runtime": runtime,
        "source": {"dataset_snapshot_files_sha256": {f"part-{n}.parquet": "2" * 64 for n in range(8)}},
        "execution": {
            "one_codex_exec_per_cell": True,
            "corrective_resume_permitted": False,
            "qualification_subject_executions": 1,
            "subject_timeout_seconds": 900,
            "evaluator_timeout_seconds": 1800,
            "workers": 1,
            "stage_1_cell_count": 4,
            "maximum_subject_executions_including_qualification": 64,
            "maximum_attempts_per_cell": 2,
            "attempt_3_permitted": False,
        },
    }
    value["authorization_sha256"] = digest(value)
    return value


def event(event_type: str, **fields: object) -> bytes:
    return (json.dumps({"type": event_type, **fields}) + "\n").encode()


def record_invocation(
    ledger: Path,
    contract: dict,
    cell_id: str,
    attempt: int = 1,
    command_sha256: str = "2" * 64,
) -> None:
    _record_subject_invocation_start(
        ledger,
        contract,
        cell_id=cell_id,
        attempt=attempt,
        prompt_sha256="1" * 64,
        command_sha256=command_sha256,
        codex_executable_sha256="3" * 64,
    )
    _record_subject_invocation_return(
        ledger,
        contract,
        cell_id=cell_id,
        attempt=attempt,
        exit_code=0,
        timed_out=False,
        stdout_sha256="4" * 64,
        stderr_sha256="5" * 64,
    )


def stage_1_receipt(cell: dict, *, evaluator_complete: bool = True) -> dict:
    usage = {
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "cache_write_input_tokens": 1,
        "output_tokens": 4,
        "reasoning_output_tokens": 1,
    }
    receipt = {
        "cell_id": cell["cell_id"],
        "attempt": 1,
        "classification": "evaluator_test_failure",
        "subject_exit_code": 0,
        "subject_timed_out": False,
        "usage": {
            "provider_reported": usage,
            "derived": {"calculated_fresh_input_tokens": 7},
        },
        **usage,
        "activity": {
            "turns": 1,
            "commands": 1,
            "repository_search_commands": 1,
            "completed_items": 1,
            "external_search_items": 0,
            "item_types": {"command_execution": 1},
        },
        "subject_wall_time_seconds": 1.0,
        "subject_wall_seconds": 1.0,
        "subject_turns": 1,
        "command_count": 1,
        "search_count": 1,
        "item_count": 1,
        "item_counts": {"command_execution": 1},
        "external_search_item_count": 0,
        "patch_sha256": "6" * 64,
        "evaluator_exit_code": 0,
        "evaluator_timed_out": False,
        "evaluator_wall_time_seconds": 1.0,
        "official_disposition": "failure",
        "resolved": False,
        "results_sha256": "7" * 64,
    }
    if not evaluator_complete:
        receipt.pop("results_sha256")
    return receipt


class ReasoningEffortV1RunnerTest(unittest.TestCase):
    def test_offline_evaluator_cache_uses_qualified_dataset_sibling(self) -> None:
        value = _environment(Path("/tmp/codex-home"), Path("/tmp/qualified/hf-cache"))
        self.assertEqual(value["HF_DATASETS_CACHE"], "/tmp/qualified/hf-cache")
        self.assertEqual(value["HF_DATASETS_OFFLINE"], "1")
        self.assertEqual(value["HF_HUB_OFFLINE"], "1")

    def test_authorization_seals_itself_and_only_allows_frozen_infrastructure_classes(self) -> None:
        value = fixture_authorization()
        validate_authorization(value)
        changed = deepcopy(value)
        changed["execution"]["workers"] = 2
        with self.assertRaisesRegex(ExperimentConfigurationError, "identity mismatch"):
            validate_authorization(changed)
        changed = deepcopy(value)
        changed["allowed_attempt_2_classes"].append("subject_timeout")
        changed["authorization_sha256"] = digest(
            {key: item for key, item in changed.items() if key != "authorization_sha256"}
        )
        with self.assertRaisesRegex(ExperimentConfigurationError, "classes drifted"):
            validate_authorization(changed)

    def test_trace_requires_one_final_five_field_usage_and_counts_activity(self) -> None:
        usage = {
            "input_tokens": 100,
            "cached_input_tokens": 40,
            "cache_write_input_tokens": 10,
            "output_tokens": 25,
            "reasoning_output_tokens": 5,
        }
        trace = b"".join(
            (
                event("thread.started", thread_id="thread-1"),
                event(
                    "item.completed",
                    item={"type": "command_execution", "command": "rg -n needle src"},
                ),
                event("item.completed", item={"type": "agent_message"}),
                event("turn.completed", usage=usage),
            )
        )
        result = parse_subject_trace(trace)
        self.assertEqual(result["usage"]["provider_reported"], usage)
        self.assertEqual(
            result["usage"]["derived"]["calculated_fresh_input_tokens"], 50
        )
        self.assertEqual(result["activity"]["commands"], 1)
        self.assertEqual(result["activity"]["repository_search_commands"], 1)
        self.assertEqual(result["activity"]["external_search_items"], 0)
        self.assertEqual(result["activity"]["turns"], 1)
        self.assertEqual(result["activity"]["completed_items"], 2)
        self.assertNotIn("needle", str(result))

    def test_trace_rejects_malformed_usage_and_prohibited_tools(self) -> None:
        incomplete = {
            "input_tokens": 1,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": 1,
        }
        with self.assertRaises(ExperimentConfigurationError):
            parse_subject_trace(
                event("thread.started", thread_id="thread-1")
                + event("turn.completed", usage=incomplete)
            )
        usage = {**incomplete, "reasoning_output_tokens": 0}
        with self.assertRaisesRegex(ExperimentConfigurationError, "browser/plugin/multi-agent"):
            parse_subject_trace(
                event("thread.started", thread_id="thread-1")
                + event("item.completed", item={"type": "web_search"})
                + event("turn.completed", usage=usage)
            )
        with self.assertRaisesRegex(ExperimentConfigurationError, "malformed Codex JSONL"):
            parse_subject_trace(b"not-json\n")

    def test_status_advances_one_cell_or_authorized_attempt_at_a_time(self) -> None:
        contract = fixture_contract()
        first = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            status = runner_status(contract, [])
            self.assertEqual(status["next_action"]["attempt"], 1)
            self.assertEqual(status["subject_executions_including_qualification"], 1)
            record_attempt_start(ledger, contract, first["cell_id"], 1)
            record_invocation(ledger, contract, first["cell_id"])
            _classify_and_transition(
                ledger,
                contract,
                first["cell_id"],
                1,
                "provider_api_infrastructure_failure",
                {
                    "cell_id": first["cell_id"],
                    "attempt": 1,
                    "classification": "provider_api_infrastructure_failure",
                },
            )
            events = read_attempt_ledger(ledger, contract)
            status = runner_status(contract, events)
            self.assertEqual(status["next_action"]["attempt"], 2)
            self.assertEqual(status["subject_executions_including_qualification"], 2)
            record_attempt_start(ledger, contract, first["cell_id"], 2)
            record_invocation(ledger, contract, first["cell_id"], 2)
            _classify_and_transition(
                ledger,
                contract,
                first["cell_id"],
                2,
                "evaluator_test_failure",
                {
                    "cell_id": first["cell_id"],
                    "attempt": 2,
                    "classification": "evaluator_test_failure",
                },
            )
            events = read_attempt_ledger(ledger, contract)
            status = runner_status(contract, events)
            self.assertEqual(status["next_action"]["attempt"], 1)
            self.assertNotEqual(status["next_action"]["cell"]["cell_id"], first["cell_id"])

    def test_harness_attempt_does_not_consume_subject_capacity_until_invocation_starts(self) -> None:
        contract = fixture_contract()
        cell = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            record_attempt_start(ledger, contract, cell["cell_id"], 1)
            status = runner_status(contract, read_attempt_ledger(ledger, contract))
            self.assertEqual(status["harness_attempts"], 1)
            self.assertEqual(status["subject_executions_including_qualification"], 1)
            self.assertEqual(status["next_action"]["action"], "reconcile")
            record_invocation(ledger, contract, cell["cell_id"])
            status = runner_status(contract, read_attempt_ledger(ledger, contract))
            self.assertEqual(status["subject_executions_including_qualification"], 2)

    def test_malformed_evidence_stop_is_terminal_and_attempt_roots_are_isolated(self) -> None:
        contract = fixture_contract()
        first = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            record_attempt_start(ledger, contract, first["cell_id"], 1)
            append_event(
                ledger,
                "batch_stopped",
                {"cell_id": first["cell_id"], "reason": "malformed_evidence"},
            )
            events = read_attempt_ledger(ledger, contract)
            self.assertEqual(runner_status(contract, events)["next_action"]["action"], "stopped")
            roots = _attempt_roots(state, first["cell_id"], 1)
            self.assertEqual(set(roots), {"repository", "codex-home", "raw", "derived", "evaluator"})
            self.assertEqual(len(set(roots.values())), 5)

    def test_task_snapshot_binds_dataset_task_problem_image_and_manifest(self) -> None:
        task = {
            "task_id": "task-1",
            "repository": "owner/repo",
            "language": "go",
            "base_commit": "a" * 40,
            "docker_image": "example/image:tag",
            "image_id": "sha256:" + "b" * 64,
            "problem_statement_sha256": "c" * 64,
            "manifest_sha256": "d" * 64,
        }
        observed = _task_snapshot("dataset-revision", task)
        for field in tuple(task):
            changed = dict(task)
            changed[field] += "x"
            self.assertNotEqual(_task_snapshot("dataset-revision", changed), observed)
        self.assertNotEqual(_task_snapshot("different-revision", task), observed)

    def test_subject_command_is_fresh_single_invocation_and_disables_external_tools(self) -> None:
        contract = fixture_contract()
        cell = contract["schedule"]["cells"][0]
        command = subject_command("codex", contract, cell)
        self.assertEqual(command[:3], ["codex", "exec", "-"])
        self.assertNotIn("resume", command)
        self.assertIn(f'model_reasoning_effort="{cell["arm"]}"', command)
        self.assertIn('web_search="disabled"', command)
        self.assertIn("sandbox_workspace_write.network_access=false", command)
        disabled = {
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == "--disable"
        }
        self.assertEqual(
            disabled,
            {
                "apps",
                "plugins",
                "browser_use",
                "in_app_browser",
                "computer_use",
                "image_generation",
                "multi_agent",
                "multi_agent_v2",
                "skill_search",
            },
        )
        self.assertEqual(set(validate_subject_commands(contract)), {"low", "medium"})
        changed = dict(cell, reasoning_effort="high", arm="high")
        with self.assertRaisesRegex(ExperimentConfigurationError, "frozen arms"):
            subject_command("codex", contract, changed)

    def test_only_frozen_infrastructure_gets_attempt_2_and_outcomes_never_retry(self) -> None:
        contract = fixture_contract()
        first, second = contract["schedule"]["cells"][:2]
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            record_attempt_start(ledger, contract, first["cell_id"], 1)
            record_invocation(ledger, contract, first["cell_id"])
            _classify_and_transition(
                ledger,
                contract,
                first["cell_id"],
                1,
                "evaluator_test_failure",
                {
                    "cell_id": first["cell_id"],
                    "attempt": 1,
                    "classification": "evaluator_test_failure",
                },
            )
            events = read_attempt_ledger(ledger, contract)
            self.assertEqual(runner_status(contract, events)["next_action"]["attempt"], 1)

            record_attempt_start(ledger, contract, second["cell_id"], 1)
            record_invocation(ledger, contract, second["cell_id"])
            _classify_and_transition(
                ledger,
                contract,
                second["cell_id"],
                1,
                "official_evaluator_incomplete",
                {
                    "cell_id": second["cell_id"],
                    "attempt": 1,
                    "classification": "official_evaluator_incomplete",
                },
            )
            events = read_attempt_ledger(ledger, contract)
            next_action = runner_status(contract, events)["next_action"]
            self.assertEqual(next_action["cell"]["cell_id"], second["cell_id"])
            self.assertEqual(next_action["attempt"], 2)

    def test_evaluator_taxonomy_keeps_timeouts_retryable_and_malformed_terminal(self) -> None:
        self.assertEqual(
            classify_evaluator_attempt(
                timed_out=True, structured_malformed=False, disposition=None
            ),
            "local_docker_runtime_infrastructure_failure",
        )
        self.assertEqual(
            classify_evaluator_attempt(
                timed_out=True, structured_malformed=True, disposition=None
            ),
            "malformed_inconsistent_measurement",
        )
        self.assertEqual(
            classify_evaluator_attempt(
                timed_out=False, structured_malformed=False, disposition=None
            ),
            "official_evaluator_error",
        )
        self.assertEqual(
            classify_evaluator_attempt(
                timed_out=False, structured_malformed=False, disposition="failure"
            ),
            "evaluator_test_failure",
        )

    def test_manifest_identity_hashes_exact_docker_output_bytes(self) -> None:
        output = b'{"schemaVersion":2}\n'
        with patch("scripts.reasoning_effort_v1_runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = output
            self.assertEqual(docker_manifest_sha256("image:tag"), __import__("hashlib").sha256(output).hexdigest())
            run.assert_called_once_with(
                ["docker", "manifest", "inspect", "image:tag"],
                capture_output=True,
                check=False,
            )

    def test_experimental_timeout_with_missing_work_is_completed_without_retry(self) -> None:
        contract = fixture_contract()
        cell = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            record_attempt_start(ledger, contract, cell["cell_id"], 1)
            record_invocation(ledger, contract, cell["cell_id"])
            receipt = {
                "cell_id": cell["cell_id"],
                "attempt": 1,
                "classification": "trajectory_timeout",
                "admissible": True,
            }
            _classify_and_transition(
                ledger, contract, cell["cell_id"], 1, "trajectory_timeout", receipt
            )
            events = read_attempt_ledger(ledger, contract)
            self.assertTrue(events[-2]["payload"]["admissible"])
            self.assertNotIn("usage", events[-2]["payload"])
            self.assertNotEqual(
                runner_status(contract, events)["next_action"]["cell"]["cell_id"],
                cell["cell_id"],
            )

    def test_codex_identity_hashes_path_and_bytes_without_persisting_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex"
            executable.write_bytes(b"exact executable bytes")
            resolved, identity = _codex_executable_identity(str(executable))
            self.assertEqual(resolved, executable.resolve())
            self.assertEqual(identity["file_sha256"], hashlib.sha256(executable.read_bytes()).hexdigest())
            self.assertEqual(
                identity["resolved_path_sha256"],
                hashlib.sha256(str(executable.resolve()).encode("utf-8")).hexdigest(),
            )
            self.assertNotIn(str(executable), json.dumps(identity))

    def test_prompt_validation_binds_the_exact_stdin_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "prompt.txt"
            prompt.write_bytes(b"fix the bug\n")
            identity = {
                "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                "prompt_bytes": len(prompt.read_bytes()),
            }
            problem = hashlib.sha256(b"fix the bug").hexdigest()
            self.assertEqual(_validate_prompt_bytes(prompt, identity, problem), b"fix the bug\n")
            prompt.write_bytes(b"fix a different bug\n")
            with self.assertRaisesRegex(ExperimentConfigurationError, "prompt bytes changed"):
                _validate_prompt_bytes(prompt, identity, problem)

    def test_dirty_evaluator_worktree_fails_closed(self) -> None:
        with patch("scripts.reasoning_effort_v1_runner._checked", return_value="?? stray.txt"):
            with self.assertRaisesRegex(ExperimentConfigurationError, "not clean"):
                _require_clean_worktree(Path("/tmp/evaluator"), "official evaluator")

    def test_stage_1_stops_after_exactly_four_cells_until_provider_free_authorization(self) -> None:
        contract = fixture_contract()
        command_hashes = validate_subject_commands(contract)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            for cell in contract["schedule"]["cells"][:4]:
                record_attempt_start(ledger, contract, cell["cell_id"], 1)
                record_invocation(
                    ledger,
                    contract,
                    cell["cell_id"],
                    command_sha256=command_hashes[cell["arm"]],
                )
                roots = _attempt_roots(state, cell["cell_id"], 1)
                for path in roots.values():
                    path.mkdir(parents=True)
                _classify_and_transition(
                    ledger,
                    contract,
                    cell["cell_id"],
                    1,
                    "evaluator_test_failure",
                    stage_1_receipt(cell),
                    roots,
                )
            events = read_attempt_ledger(ledger, contract)
            status = runner_status(contract, events)
            self.assertEqual(status["completed_cells"], 4)
            self.assertEqual(status["next_action"]["action"], "await_stage_1_authorization")
            continued = authorize_stage_2(state, contract, events, command_hashes)
            self.assertEqual(continued["next_action"]["action"], "execute")
            self.assertEqual(continued["completed_cells"], 4)

    def test_stage_1_gate_fails_terminally_without_complete_evaluator_receipts(self) -> None:
        contract = fixture_contract()
        command_hashes = validate_subject_commands(contract)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            for index, cell in enumerate(contract["schedule"]["cells"][:4]):
                record_attempt_start(ledger, contract, cell["cell_id"], 1)
                record_invocation(
                    ledger,
                    contract,
                    cell["cell_id"],
                    command_sha256=command_hashes[cell["arm"]],
                )
                roots = _attempt_roots(state, cell["cell_id"], 1)
                for path in roots.values():
                    path.mkdir(parents=True)
                _classify_and_transition(
                    ledger,
                    contract,
                    cell["cell_id"],
                    1,
                    "evaluator_test_failure",
                    stage_1_receipt(cell, evaluator_complete=index != 0),
                    roots,
                )
            result = authorize_stage_2(
                state,
                contract,
                read_attempt_ledger(ledger, contract),
                command_hashes,
            )
            self.assertEqual(result["next_action"], {
                "action": "stopped",
                "reason": "stage_1_infrastructure_gate_failed",
            })
            events = read_attempt_ledger(ledger, contract)
            self.assertEqual(events[-1]["event_type"], "stage_1_failed")
            self.assertFalse(events[-1]["payload"]["audit"]["criteria"]["official_evaluator_receipts_complete"])
            self.assertNotIn("accepted", events[-1]["payload"]["audit"])

    def test_stage_1_gate_rejects_incomplete_usage_and_prohibited_tool_receipts(self) -> None:
        mutations = {
            "usage": lambda receipt: receipt.pop("usage"),
            "work": lambda receipt: receipt.pop("subject_wall_seconds"),
            "tool": lambda receipt: receipt["activity"]["item_types"].update(
                {"mcp_tool_call": 1}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                contract = fixture_contract()
                command_hashes = validate_subject_commands(contract)
                state = Path(directory)
                ledger = state / "ledger.jsonl"
                for index, cell in enumerate(contract["schedule"]["cells"][:4]):
                    record_attempt_start(ledger, contract, cell["cell_id"], 1)
                    record_invocation(
                        ledger,
                        contract,
                        cell["cell_id"],
                        command_sha256=command_hashes[cell["arm"]],
                    )
                    roots = _attempt_roots(state, cell["cell_id"], 1)
                    for path in roots.values():
                        path.mkdir(parents=True)
                    receipt = stage_1_receipt(cell)
                    if index == 0:
                        mutate(receipt)
                    _classify_and_transition(
                        ledger,
                        contract,
                        cell["cell_id"],
                        1,
                        "evaluator_test_failure",
                        receipt,
                        roots,
                    )
                result = authorize_stage_2(
                    state,
                    contract,
                    read_attempt_ledger(ledger, contract),
                    command_hashes,
                )
                self.assertEqual(result["next_action"]["action"], "stopped")
                audit = read_attempt_ledger(ledger, contract)[-1]["payload"]["audit"]
                criterion = {
                    "usage": "usage_receipts_complete",
                    "work": "subject_work_receipts_complete",
                    "tool": "tool_policy_receipts_complete",
                }[name]
                self.assertFalse(audit["criteria"][criterion])

    def test_reconcile_uses_only_hash_validated_durable_receipt(self) -> None:
        contract = fixture_contract()
        cell = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            record_attempt_start(ledger, contract, cell["cell_id"], 1)
            record_invocation(ledger, contract, cell["cell_id"])
            roots = _attempt_roots(state, cell["cell_id"], 1)
            for path in roots.values():
                path.mkdir(parents=True)
            (roots["raw"] / "codex.jsonl").write_bytes(b"trace")
            receipt = {
                "cell_id": cell["cell_id"],
                "attempt": 1,
                "classification": "trajectory_timeout",
                "admissible": True,
            }
            durable, _ = _persist_receipt(roots, receipt)
            self.assertEqual(_validate_persisted_receipt(roots)[0], durable)
            result = reconcile_interrupted_attempt(
                state, contract, read_attempt_ledger(ledger, contract)
            )
            self.assertEqual(result["completed_cells"], 1)
            (roots["raw"] / "codex.jsonl").write_bytes(b"tampered")
            with self.assertRaisesRegex(ExperimentConfigurationError, "hashes changed"):
                _validate_persisted_receipt(roots)

    def test_reconcile_finishes_a_crash_between_receipt_and_transition(self) -> None:
        contract = fixture_contract()
        cell = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "ledger.jsonl"
            record_attempt_start(ledger, contract, cell["cell_id"], 1)
            record_invocation(ledger, contract, cell["cell_id"])
            append_event(
                ledger,
                "attempt_finished",
                {
                    "cell_id": cell["cell_id"],
                    "attempt": 1,
                    "classification": "evaluator_test_failure",
                },
            )
            events = read_attempt_ledger(ledger, contract)
            self.assertEqual(runner_status(contract, events)["next_action"]["action"], "reconcile_transition")
            result = reconcile_interrupted_attempt(state, contract, events)
            self.assertEqual(result["completed_cells"], 1)

    def test_reconcile_cleanup_removes_only_ledger_known_attempt_auth(self) -> None:
        contract = fixture_contract()
        cell = contract["schedule"]["cells"][0]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            known = _attempt_roots(state, cell["cell_id"], 1)["codex-home"]
            unknown = state / "attempts" / "unknown" / "attempt-1" / "codex-home"
            known.mkdir(parents=True)
            unknown.mkdir(parents=True)
            (known / "auth.json").write_text("secret", encoding="utf-8")
            (unknown / "auth.json").write_text("leave", encoding="utf-8")
            removed = cleanup_interrupted_attempt_auth(
                state,
                contract,
                [
                    {
                        "event_type": "attempt_started",
                        "payload": {"cell_id": cell["cell_id"], "attempt": 1},
                    }
                ],
            )
            self.assertEqual(removed, 1)
            self.assertFalse((known / "auth.json").exists())
            self.assertTrue((unknown / "auth.json").exists())


if __name__ == "__main__":
    unittest.main()
