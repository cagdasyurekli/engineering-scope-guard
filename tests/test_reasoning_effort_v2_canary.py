from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import stat
import sys
import unittest
from unittest import mock

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import digest
from scripts import reasoning_effort_v2_canary as canary
from scripts import reasoning_effort_v2_execution_adapter as adapter
from scripts import reasoning_effort_v2_runner as durable
from tests import test_reasoning_effort_v2_freeze as freeze_tests


def event_bytes(
    *, tool: bool = False, malformed: bool = False,
    missing_usage: bool = False, agent_text: str = "CANARY",
) -> bytes:
    if malformed:
        return b"not-json\n"
    events = [
        {"type": "thread.started", "thread_id": "contentless-canary"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": (
                {"type": "command_execution", "command": "pwd"}
                if tool else {"type": "agent_message", "text": agent_text}
            ),
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 5,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "output_tokens": 2,
                "reasoning_output_tokens": 1,
            },
        },
    ]
    if missing_usage:
        del events[-1]["usage"]["reasoning_output_tokens"]
    return b"".join(
        (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for item in events
    )


@dataclass
class FakeChild:
    result: adapter.SubjectInvocation
    pid: int = 4242

    def __post_init__(self) -> None:
        self.process_identity = {
            "pid": self.pid,
            "start_time": "fixture-start-4242",
            "launcher_executable": {"resolved_path": "/fixture/python"},
            "target_executable": {"resolved_path": "/fixture/codex"},
            "command_sha256": "a" * 64,
            "ownership_token_sha256": "b" * 64,
            "nonce_sha256": "c" * 64,
            "gated_before_exec": True,
        }
        self.process_identity_sha256 = digest(self.process_identity)
        self.calls: list[tuple[bytes, int]] = []

    def run(self, stdin: bytes, timeout_seconds: int) -> adapter.SubjectInvocation:
        self.calls.append((stdin, timeout_seconds))
        return self.result


class CanaryLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = freeze_tests.ReasoningEffortV2FreezeTests(methodName="runTest")
        self.fixture.setUp()
        self.fixture._freeze()
        self.factories = 0

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def args(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "execution_root": self.fixture.execution_root,
            "qualification_receipt_path": self.fixture.receipt_path,
            "qualification_raw_root": self.fixture.raw_root,
            "codex_binary": self.fixture.codex_binary,
            "model_catalog": self.fixture.model_catalog,
            "runtime_observer": lambda _binary, _catalog: deepcopy(self.fixture.runtime),
        }
        value.update(overrides)
        return value

    def child_factory(
        self, result: adapter.SubjectInvocation
    ) -> tuple[FakeChild, object]:
        child = FakeChild(result)
        def factory(authority: dict, cwd: Path, nonce: str) -> FakeChild:
            self.factories += 1
            self.assertEqual(
                Path(tuple(authority["command"])[0]).resolve(),
                self.fixture.codex_binary.resolve(),
            )
            self.assertEqual(list(cwd.iterdir()), [])
            self.assertEqual(len(nonce), 64)
            child.process_identity["command_sha256"] = authority["command_sha256"]
            child.process_identity["ownership_token_sha256"] = nonce
            child.process_identity["launcher_executable"] = adapter._file_identity(
                sys.executable
            )
            child.process_identity["target_executable"] = adapter._file_identity(
                authority["command"][0]
            )
            child.process_identity_sha256 = digest(child.process_identity)
            return child
        return child, factory

    def invocation(
        self, *, stdout: bytes | None = None, exit_code: int | None = 0,
        timed_out: bool = False,
    ) -> adapter.SubjectInvocation:
        return adapter.SubjectInvocation(
            exit_code=exit_code, timed_out=timed_out,
            stdout=event_bytes() if stdout is None else stdout,
            stderr=b"", wall_seconds=0.1,
        )

    def test_success_is_exactly_once_private_and_idempotent(self) -> None:
        child, factory = self.child_factory(self.invocation())
        result = canary.launch(**self.args(child_factory=factory))
        self.assertTrue(result["live_authorized"])
        self.assertEqual(result["terminal_status"], "success")
        self.assertEqual(self.factories, 1)
        self.assertEqual(child.calls[0][0], canary.freeze_layer.CANARY_PROMPT)
        for path in (
            self.fixture.execution_root / "canary-receipt.json",
            self.fixture.execution_root / "canary-raw" / "codex.jsonl",
            self.fixture.execution_root / "canary-raw" / "codex.stderr",
        ):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        again = canary.launch(**self.args(child_factory=factory))
        self.assertTrue(again["live_authorized"])
        self.assertEqual(self.factories, 1)
        authority = self.fixture._authority()
        lifecycle = durable.replay_canary_lifecycle(
            self.fixture.execution_root / "canary-ledger.jsonl", authority
        )
        self.assertEqual(len(lifecycle["events"]), 3)
        main_events = durable.read_ledger(
            self.fixture.execution_root / "ledger.jsonl",
            json.loads((self.fixture.execution_root / "contract.json").read_text()),
        )
        self.assertEqual([item["event_type"] for item in main_events], ["canary_lifecycle_imported"])

    def test_gate_rebuild_reuses_hash_bound_phase_7_audit(self) -> None:
        child, factory = self.child_factory(self.invocation())
        original = durable.build_qualification_gate_from_receipt
        with mock.patch.object(
            durable, "build_qualification_gate_from_receipt", wraps=original
        ) as rebuilt:
            result = canary.launch(**self.args(child_factory=factory))
        self.assertTrue(result["live_authorized"])
        self.assertIn("pool_reliability_audit", rebuilt.call_args.kwargs)
        persisted_gate = json.loads(
            (self.fixture.execution_root / "qualification-gate.json").read_text()
        )
        self.assertEqual(
            rebuilt.call_args.kwargs["pool_reliability_audit"],
            persisted_gate["pool_reliability_audit"],
        )

    def test_runtime_drift_stops_before_reservation(self) -> None:
        drifted = deepcopy(self.fixture.runtime)
        drifted["codex_version"] = "drifted"
        with self.assertRaisesRegex(ExperimentConfigurationError, "runtime drifted"):
            canary.launch(**self.args(runtime_observer=lambda _b, _c: drifted))
        self.assertFalse((self.fixture.execution_root / "canary-ledger.jsonl").exists())

    def test_process_identity_mismatch_terminalizes(self) -> None:
        _child, factory = self.child_factory(self.invocation())

        def mismatched_factory(
            authority: dict, cwd: Path, nonce: str
        ) -> FakeChild:
            value = factory(authority, cwd, nonce)
            value.process_identity["ownership_token_sha256"] = "0" * 64
            value.process_identity_sha256 = digest(value.process_identity)
            return value

        with self.assertRaisesRegex(
            ExperimentConfigurationError, "process identity"
        ):
            canary.launch(**self.args(child_factory=mismatched_factory))
        authority = self.fixture._authority()
        lifecycle = durable.replay_canary_lifecycle(
            self.fixture.execution_root / "canary-ledger.jsonl", authority
        )
        self.assertEqual(lifecycle["terminal_status"], "failure")
        self.assertEqual(self.factories, 1)

    def test_timeout_terminalizes_and_never_retries(self) -> None:
        _child, factory = self.child_factory(self.invocation(exit_code=None, timed_out=True))
        result = canary.launch(**self.args(child_factory=factory))
        self.assertEqual(result["terminal_status"], "failure")
        self.assertFalse((self.fixture.execution_root / "live-seal.json").exists())
        canary.launch(**self.args(child_factory=factory))
        self.assertEqual(self.factories, 1)

    def test_malformed_and_tool_use_are_terminal_failures(self) -> None:
        for raw in (
            event_bytes(malformed=True),
            event_bytes(tool=True),
            event_bytes(missing_usage=True),
        ):
            with self.subTest(raw=raw[:8]):
                self.tearDown()
                self.setUp()
                _child, factory = self.child_factory(self.invocation(stdout=raw))
                result = canary.launch(**self.args(child_factory=factory))
                self.assertEqual(result["terminal_status"], "failure")
                self.assertFalse((self.fixture.execution_root / "live-seal.json").exists())

    def test_private_task_identity_in_events_is_terminal_failure(self) -> None:
        private_pool = json.loads(
            (self.fixture.execution_root / "private-pool.json").read_text()
        )
        raw = event_bytes(agent_text=private_pool["primaries"][0]["task_id"])
        _child, factory = self.child_factory(self.invocation(stdout=raw))
        result = canary.launch(**self.args(child_factory=factory))
        self.assertEqual(result["terminal_status"], "failure")
        self.assertFalse((self.fixture.execution_root / "live-seal.json").exists())

    def test_crash_after_reservation_terminalizes_without_spawn_on_resume(self) -> None:
        _child, factory = self.child_factory(self.invocation())
        def crash(stage: str) -> None:
            if stage == "after_reservation":
                raise canary.SimulatedCrash()
        with self.assertRaises(canary.SimulatedCrash):
            canary.launch(**self.args(child_factory=factory, boundary_hook=crash))
        result = canary.launch(**self.args(child_factory=factory))
        self.assertEqual(result["terminal_status"], "failure")
        self.assertEqual(self.factories, 0)

    def test_crash_after_spawn_does_not_duplicate(self) -> None:
        _child, factory = self.child_factory(self.invocation())
        def crash(stage: str) -> None:
            if stage == "after_spawn":
                raise canary.SimulatedCrash()
        with self.assertRaises(canary.SimulatedCrash):
            canary.launch(**self.args(child_factory=factory, boundary_hook=crash))
        result = canary.launch(**self.args(child_factory=factory))
        self.assertEqual(result["terminal_status"], "failure")
        self.assertEqual(self.factories, 1)

    def test_attached_crash_reconciles_running_then_not_running(self) -> None:
        child, factory = self.child_factory(self.invocation())
        def crash(stage: str) -> None:
            if stage == "after_attach":
                raise canary.SimulatedCrash()
        with self.assertRaises(canary.SimulatedCrash):
            canary.launch(**self.args(child_factory=factory, boundary_hook=crash))
        attached = {
            "pid": child.pid,
            "os_start_identity": child.process_identity["start_time"],
            "process_identity_sha256": child.process_identity_sha256,
        }
        running = canary.launch(**self.args(
            child_factory=factory,
            process_observer=lambda _pid: {**attached, "status": "running"},
        ))
        self.assertIsNone(running["terminal_status"])
        stopped = canary.launch(**self.args(
            child_factory=factory,
            process_observer=lambda _pid: {**attached, "status": "not_running"},
        ))
        self.assertEqual(stopped["terminal_status"], "failure")
        self.assertEqual(self.factories, 1)


if __name__ == "__main__":
    unittest.main()
