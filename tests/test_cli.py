from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.cli import (
    ConfigurationError,
    build_parser,
    initialize,
    main,
    run_analysis,
    take_snapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root, *root.rglob("*")]
    for path in sorted(paths, key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix() or "."
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            entry_type = "symlink"
        elif stat.S_ISDIR(metadata.st_mode):
            entry_type = "directory"
        elif stat.S_ISREG(metadata.st_mode):
            entry_type = "file"
        else:
            entry_type = "other"
        fields = (
            relative,
            entry_type,
            str(stat.S_IMODE(metadata.st_mode)),
            str(metadata.st_mtime_ns),
        )
        for field in fields:
            digest.update(field.encode("utf-8"))
            digest.update(b"\0")
        if entry_type == "symlink":
            digest.update(os.readlink(path).encode("utf-8"))
        elif entry_type == "file":
            data = path.read_bytes()
            digest.update(str(len(data)).encode("ascii"))
            digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def add_immutability_edge_entries(target: Path, external_target: Path) -> None:
    (target / ".hidden").write_text("hidden\n", encoding="utf-8")
    (target / "empty-directory").mkdir()
    (target / "binary.bin").write_bytes(b"\x00\xff\x10")
    os.symlink(external_target, target / "external-link")


def healthy_capability():
    return {
        "schema_version": 1,
        "status": "healthy",
        "codex": {
            "available": True,
            "version": "0.150.1",
            "exec_json": True,
            "hooks": {"maturity": "stable", "enabled": True},
        },
        "known_gaps": ["fixture-known static limitation"],
        "diagnostics": [],
    }


class CliWorkflowTests(unittest.TestCase):
    def _analyze_hook_records(self, records):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            (target / "file.py").write_text("one\n", encoding="utf-8")
            config = initialize(target, base / "state")
            take_snapshot(config, "before")
            take_snapshot(config, "after")
            trace_path = base / "trace.jsonl"
            trace_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            code, events_path, _report_path = run_analysis(
                config, trace_path, healthy_capability()
            )
            return code, json.loads(
                events_path.read_text(encoding="utf-8").splitlines()[0]
            )

    def test_help_advertises_only_the_python_module_invocation(self):
        help_text = build_parser().format_help()
        self.assertIn("usage: python -m engineering_scope_guard", help_text)
        self.assertNotIn("usage: scope-guard", help_text)

    def test_state_inside_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ConfigurationError):
                initialize(root, root / ".scope-guard")

    def test_end_to_end_is_deterministic_and_target_is_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            state = base / "state"
            external_target = base / "external-target"
            external_target.write_text("outside target\n", encoding="utf-8")
            shutil.copytree(FIXTURES / "demo_before", target)
            add_immutability_edge_entries(target, external_target)
            self.assertTrue((target / ".hidden").is_file())
            self.assertTrue((target / "empty-directory").is_dir())
            self.assertEqual((target / "binary.bin").read_bytes(), b"\x00\xff\x10")
            self.assertTrue((target / "external-link").is_symlink())
            initial_target = tree_digest(target)
            config = initialize(target, state)
            self.assertEqual(initial_target, tree_digest(target))
            take_snapshot(config, "before")
            self.assertEqual(initial_target, tree_digest(target))

            shutil.rmtree(target)
            shutil.copytree(FIXTURES / "demo_after", target)
            add_immutability_edge_entries(target, external_target)
            transitioned_target = tree_digest(target)
            take_snapshot(config, "after")
            self.assertEqual(transitioned_target, tree_digest(target))
            before_analysis = tree_digest(target)

            code, events_path, report_path = run_analysis(
                config,
                FIXTURES / "traces" / "codex-0.150.1-exec.jsonl",
                healthy_capability(),
            )
            first_events = events_path.read_bytes()
            first_report = report_path.read_bytes()
            second_code, _, _ = run_analysis(
                config,
                FIXTURES / "traces" / "codex-0.150.1-exec.jsonl",
                healthy_capability(),
            )

            self.assertEqual(code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(first_events, events_path.read_bytes())
            self.assertEqual(first_report, report_path.read_bytes())
            self.assertEqual(before_analysis, tree_digest(target))
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("candidate review events", report.lower())
            self.assertNotIn("the change is overengineered", report.lower())
            events = [json.loads(line) for line in first_events.splitlines()]
            self.assertTrue(
                all(
                    event["schema_name"] == "engineering-scope-guard.event"
                    and event["schema_version"] == 1
                    for event in events
                )
            )
            health = events[0]
            self.assertEqual(
                set(health["coverage_dimensions"]),
                {"trace", "snapshot", "command_verification", "usage"},
            )
            self.assertEqual(
                health["output_contract"]["path_sensitivity"],
                "repository-relative paths are sensitive local metadata",
            )

    def test_network_socket_denial_does_not_break_full_analysis_workflow(self):
        socket_events: list[str] = []

        def deny_socket(event: str, _arguments):
            if event.startswith("socket."):
                socket_events.append(event)
                raise AssertionError(f"network activity attempted: {event}")

        sys.addaudithook(deny_socket)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            state = base / "state"
            shutil.copytree(FIXTURES / "demo_before", target)
            config = initialize(target, state)
            take_snapshot(config, "before")
            (target / "src.py").write_text("changed\n", encoding="utf-8")
            take_snapshot(config, "after")
            code, _, _ = run_analysis(
                config,
                FIXTURES / "traces" / "codex-0.150.1-exec.jsonl",
                healthy_capability(),
            )
            self.assertEqual(code, 0)
            self.assertEqual(socket_events, [])

    def test_machine_events_do_not_copy_raw_command_or_agent_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            (target / "file.py").write_text("one\n", encoding="utf-8")
            config = initialize(target, base / "state")
            take_snapshot(config, "before")
            (target / "file.py").write_text("two\n", encoding="utf-8")
            take_snapshot(config, "after")
            _, events, _ = run_analysis(
                config,
                FIXTURES / "traces" / "codex-0.150.1-exec.jsonl",
                healthy_capability(),
            )
            content = events.read_text(encoding="utf-8")
            self.assertNotIn("python -m unittest", content)
            self.assertNotIn("Sanitized fixture content", content)
            self.assertNotIn('"1.0.0"', content)
            for line in content.splitlines():
                json.loads(line)

    def test_corrupt_nested_snapshot_returns_fatal_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            (target / "file.py").write_text("one\n", encoding="utf-8")
            config = initialize(target, base / "state")
            take_snapshot(config, "before")
            take_snapshot(config, "after")
            before_path = base / "state" / "snapshots" / "before.json"
            payload = json.loads(before_path.read_text(encoding="utf-8"))
            payload["entries"] = [{}]
            before_path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        "analyze",
                        "--config",
                        str(config),
                        "--trace",
                        str(FIXTURES / "traces" / "codex-0.150.1-exec.jsonl"),
                    ]
                ),
                1,
            )

    def test_invalid_command_metadata_never_reaches_derived_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            (target / "file.py").write_text("one\n", encoding="utf-8")
            config = initialize(target, base / "state")
            take_snapshot(config, "before")
            take_snapshot(config, "after")
            trace_path = base / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "command",
                        "type": "command_execution",
                        "command": "pytest",
                        "status": {"private": "STATUS_SENTINEL"},
                        "exit_code": "EXIT_SENTINEL",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {"id": "unknown", "type": "UNKNOWN_ITEM_SENTINEL"},
                },
                {"type": "UNKNOWN_EVENT_SENTINEL"},
                {"type": "turn.completed", "usage": {}},
            ]
            trace_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            code, events_path, report_path = run_analysis(
                config,
                trace_path,
                healthy_capability(),
            )
            derived = events_path.read_text(encoding="utf-8") + report_path.read_text(
                encoding="utf-8"
            )
            self.assertEqual(code, 2)
            self.assertNotIn("STATUS_SENTINEL", derived)
            self.assertNotIn("EXIT_SENTINEL", derived)
            self.assertNotIn("UNKNOWN_ITEM_SENTINEL", derived)
            self.assertNotIn("UNKNOWN_EVENT_SENTINEL", derived)
            self.assertIn("recognized records contained invalid fields", derived)
            health = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                health["coverage_dimensions"]["command_verification"]["status"],
                "degraded",
            )

    def test_wrong_type_posttooluse_bash_input_degrades_command_coverage(self):
        code, health = self._analyze_hook_records(
            [
                {
                    "session_id": "fixture",
                    "cwd": "/fixture",
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn",
                    "tool_name": "Bash",
                    "tool_use_id": "tool",
                    "tool_input": "not-an-object",
                }
            ]
        )
        coverage = health["coverage_dimensions"]["command_verification"]
        self.assertEqual(code, 2)
        self.assertEqual(coverage["status"], "degraded")
        self.assertEqual(coverage["invalid_or_missing_fields"], 1)

    def test_missing_posttooluse_command_fields_are_counted(self):
        code, health = self._analyze_hook_records(
            [
                {
                    "session_id": "fixture",
                    "cwd": "/fixture",
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn",
                    "tool_use_id": "tool",
                    "tool_input": {"command": "pytest"},
                },
                {
                    "session_id": "fixture",
                    "cwd": "/fixture",
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn",
                    "tool_name": "Bash",
                },
            ]
        )
        coverage = health["coverage_dimensions"]["command_verification"]
        self.assertEqual(code, 2)
        self.assertEqual(coverage["status"], "degraded")
        self.assertEqual(coverage["invalid_or_missing_fields"], 3)

    def test_valid_trace_without_commands_reports_command_coverage_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            (target / "file.py").write_text("one\n", encoding="utf-8")
            config = initialize(target, base / "state")
            take_snapshot(config, "before")
            take_snapshot(config, "after")
            code, events_path, _report_path = run_analysis(
                config,
                FIXTURES / "traces" / "codex-0.150.1-live-minimal-sanitized.jsonl",
                healthy_capability(),
            )
            health = json.loads(
                events_path.read_text(encoding="utf-8").splitlines()[0]
            )
        coverage = health["coverage_dimensions"]["command_verification"]
        self.assertEqual(code, 0)
        self.assertEqual(coverage["status"], "unavailable")
        self.assertEqual(coverage["invalid_or_missing_fields"], 0)


if __name__ == "__main__":
    unittest.main()
