from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from engineering_scope_guard.trace import parse_trace

FIXTURES = Path(__file__).parent / "fixtures" / "traces"


class TraceTests(unittest.TestCase):
    def test_sanitized_live_hook_shape_is_accepted_as_explicitly_degraded(self):
        trace = parse_trace(
            FIXTURES / "codex-0.150.1-live-hooks-sanitized.jsonl"
        )
        self.assertEqual(trace["status"], "degraded")
        self.assertEqual(trace["adapter"], ["codex-hook-json"])
        self.assertEqual(
            trace["record_counts"],
            {
                "PostToolUse": 1,
                "PreToolUse": 1,
                "SessionEnd": 1,
                "SessionStart": 1,
                "Stop": 1,
                "UserPromptSubmit": 1,
            },
        )
        self.assertEqual(trace["recognized_records"], 6)
        self.assertEqual(trace["missing_fields"], [])
        self.assertEqual(trace["invalid_fields"], [])
        serialized = json.dumps(trace)
        self.assertNotIn("prompt-redacted", serialized)
        self.assertNotIn("pwd", serialized)
        self.assertNotIn("tool-output-redacted", serialized)
        self.assertNotIn("assistant-message-redacted", serialized)

    def test_sanitized_live_exec_command_file_change_shape_is_accepted(self):
        trace = parse_trace(
            FIXTURES
            / "codex-0.150.1-live-exec-command-file-change-sanitized.jsonl"
        )
        self.assertEqual(trace["status"], "healthy")
        self.assertEqual(trace["adapter"], ["codex-exec-json"])
        self.assertEqual(trace["recognized_records"], 9)
        self.assertEqual(
            trace["record_counts"],
            {
                "item.completed": 4,
                "item.started": 2,
                "thread.started": 1,
                "turn.completed": 1,
                "turn.started": 1,
            },
        )
        self.assertEqual(trace["file_change_items"], 1)
        self.assertEqual(len(trace["commands"]), 1)
        self.assertEqual(trace["commands"][0]["program"], "canary-command")
        self.assertEqual(trace["commands"][0]["status"], "completed")
        self.assertEqual(trace["commands"][0]["exit_code"], 0)
        self.assertNotIn("command", trace["commands"][0])
        self.assertEqual(
            trace["usage_coverage"],
            {
                "status": "healthy",
                "completed_turns": 1,
                "completed_turns_with_usage": 1,
                "failed_turns_without_usage": 0,
                "invalid_or_missing_usage_records": 0,
            },
        )
        self.assertEqual(trace["missing_fields"], [])
        self.assertEqual(trace["invalid_fields"], [])
        self.assertEqual(trace["unmatched_item_ids"], [])
        serialized = json.dumps(trace)
        self.assertNotIn("PRIVATE_ARGUMENT_REDACTED", serialized)
        self.assertNotIn("EXEC_OUTPUT_REDACTED", serialized)
        self.assertNotIn("EXEC_MESSAGE_REDACTED", serialized)
        self.assertNotIn("<redacted-command-id>", serialized)
        self.assertNotIn("canary.txt", serialized)

    def test_sanitized_live_minimal_event_family_is_accepted(self):
        trace = parse_trace(
            FIXTURES / "codex-0.150.1-live-minimal-sanitized.jsonl"
        )
        self.assertEqual(trace["status"], "healthy")
        self.assertEqual(
            trace["record_counts"],
            {
                "item.completed": 1,
                "thread.started": 1,
                "turn.completed": 1,
                "turn.started": 1,
            },
        )
        self.assertNotIn("CANARY_OK", json.dumps(trace))

    def test_supported_exec_jsonl_is_healthy_and_content_bounded(self):
        trace = parse_trace(FIXTURES / "codex-0.150.1-exec.jsonl")
        self.assertEqual(trace["status"], "healthy")
        self.assertEqual(trace["adapter"], ["codex-exec-json"])
        self.assertEqual(trace["commands"][0]["verification_kind"], "test")
        self.assertNotIn("command", trace["commands"][0])
        self.assertEqual(trace["file_change_items"], 1)

    def test_hook_only_trace_is_explicitly_degraded(self):
        trace = parse_trace(FIXTURES / "codex-0.150.1-hooks.jsonl")
        self.assertEqual(trace["status"], "degraded")
        self.assertEqual(trace["adapter"], ["codex-hook-json"])
        self.assertTrue(any("hosted tools" in item for item in trace["limitations"]))

    def test_malformed_unknown_and_missing_boundaries_degrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            lines = [
                "not json",
                json.dumps({"type": "thread.started", "thread_id": "x"}),
                json.dumps({"type": "item.started", "item": {"id": "x", "type": "future_item"}}),
                json.dumps({"type": "future.event"}),
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(trace["malformed_lines"], [1])
            self.assertEqual(trace["unknown_events"]["count"], 1)
            self.assertEqual(len(trace["unknown_events"]["sha256"]), 1)
            self.assertEqual(trace["unknown_item_types"]["count"], 1)
            self.assertEqual(len(trace["unknown_item_types"]["sha256"]), 1)
            serialized = json.dumps(trace)
            self.assertNotIn("future.event", serialized)
            self.assertNotIn("future_item", serialized)

    def test_no_recognized_records_is_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            path.write_text('{"unrelated":true}\n', encoding="utf-8")
            self.assertEqual(parse_trace(path)["status"], "unsupported")

    def test_missing_hook_payload_fields_are_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "session_id": "fixture",
                        "cwd": "/fixture",
                        "hook_event_name": "PostToolUse",
                        "turn_id": "turn",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(
                trace["missing_fields"],
                ["line 1: tool_name", "line 1: tool_use_id", "line 1: tool_input"],
            )

    def test_turn_terminal_before_start_is_degraded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.completed", "usage": {}},
                {"type": "turn.started"},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertIn(
                "terminal turn event occurred without an open turn",
                trace["diagnostics"],
            )

    def test_missing_exec_schema_fields_are_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "status": "completed"},
                },
                {"type": "turn.completed"},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(
                trace["missing_fields"],
                [
                    "line 1: thread_id",
                    "line 3: item.id",
                    "line 3: item.command",
                ],
            )
            self.assertEqual(trace["usage_coverage"]["status"], "degraded")

    def test_failed_turn_is_terminal_and_usage_is_unavailable_not_malformed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {"type": "turn.failed"},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "healthy")
            self.assertEqual(trace["turn_outcomes"], {"completed": 0, "failed": 1})
            self.assertEqual(trace["usage_coverage"]["status"], "unavailable")
            self.assertEqual(trace["missing_fields"], [])
            self.assertEqual(trace["invalid_fields"], [])
            self.assertEqual(trace["diagnostics"], [])

    def test_completed_turn_without_usage_keeps_trace_valid_but_degrades_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {"type": "turn.completed"},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "healthy")
            self.assertEqual(trace["usage_coverage"]["status"], "degraded")
            self.assertEqual(
                trace["usage_coverage"]["invalid_or_missing_usage_records"], 1
            )
            self.assertEqual(trace["missing_fields"], [])
            self.assertEqual(trace["diagnostics"], [])

    def test_command_program_does_not_retain_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "command",
                        "type": "command_execution",
                        "command": "/Users/alice/private-client/run-tests --token secret",
                        "status": "completed",
                        "exit_code": 0,
                    },
                },
                {"type": "turn.completed", "usage": {}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "healthy")
            self.assertEqual(trace["commands"][0]["program"], "run-tests")
            self.assertNotIn("alice", json.dumps(trace["commands"]))

    def test_verification_classification_avoids_substring_false_positives(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            commands = ["rg pytest README.md", "cat pytest.ini", 'echo "npm test"']
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                *[
                    {
                        "type": "item.completed",
                        "item": {
                            "id": f"command-{index}",
                            "type": "command_execution",
                            "command": command,
                            "status": "completed",
                            "exit_code": 0,
                        },
                    }
                    for index, command in enumerate(commands)
                ],
                {"type": "turn.completed", "usage": {}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(
                [item["verification_kind"] for item in trace["commands"]],
                ["other", "other", "other"],
            )

    def test_invalid_command_metadata_is_removed_and_degrades_health(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
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
                {"type": "turn.completed", "usage": {}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            serialized = json.dumps(trace)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(trace["commands"][0]["status"], None)
            self.assertEqual(trace["commands"][0]["exit_code"], None)
            self.assertEqual(
                trace["invalid_fields"],
                ["line 3: item.status", "line 3: item.exit_code"],
            )
            self.assertNotIn("STATUS_SENTINEL", serialized)
            self.assertNotIn("EXIT_SENTINEL", serialized)

    def test_boolean_exit_code_is_not_accepted_as_an_integer(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "command",
                        "type": "command_execution",
                        "command": "pytest",
                        "status": "completed",
                        "exit_code": True,
                    },
                },
                {"type": "turn.completed", "usage": {}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertIsNone(trace["commands"][0]["exit_code"])

    def test_malformed_exec_command_list_is_not_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "command",
                        "type": "command_execution",
                        "command": ["pytest", {"private": "EXEC_COMMAND_SENTINEL"}],
                        "status": "completed",
                        "exit_code": 0,
                    },
                },
                {"type": "turn.completed", "usage": {}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(trace["commands"], [])
            self.assertEqual(trace["invalid_fields"], ["line 3: item.command"])
            self.assertNotIn("EXEC_COMMAND_SENTINEL", json.dumps(trace))

    def test_malformed_hook_command_is_not_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            record = {
                "session_id": "fixture",
                "cwd": "/fixture",
                "hook_event_name": "PostToolUse",
                "turn_id": "turn",
                "tool_name": "Bash",
                "tool_use_id": "tool",
                "tool_input": {"command": {"private": "HOOK_COMMAND_SENTINEL"}},
                "tool_response": {},
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            trace = parse_trace(path)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(trace["commands"], [])
            self.assertEqual(
                trace["invalid_fields"], ["line 1: tool_input.command"]
            )
            self.assertNotIn("HOOK_COMMAND_SENTINEL", json.dumps(trace))

    def test_wrong_type_hook_fields_are_invalid_without_copying_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            record = {
                "session_id": {"private": "SESSION_SENTINEL"},
                "cwd": "",
                "hook_event_name": "PostToolUse",
                "turn_id": [],
                "tool_name": "Bash",
                "tool_use_id": "",
                "tool_input": "HOOK_INPUT_SENTINEL",
                "tool_response": {},
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            trace = parse_trace(path)
            serialized = json.dumps(trace)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(
                trace["invalid_fields"],
                [
                    "line 1: session_id",
                    "line 1: cwd",
                    "line 1: turn_id",
                    "line 1: tool_use_id",
                    "line 1: tool_input",
                ],
            )
            self.assertNotIn("SESSION_SENTINEL", serialized)
            self.assertNotIn("HOOK_INPUT_SENTINEL", serialized)

    def test_unknown_type_sentinels_are_hashed_not_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.jsonl"
            records = [
                {"type": "thread.started", "thread_id": "fixture"},
                {"type": "turn.started"},
                {
                    "type": "item.completed",
                    "item": {"id": "item", "type": "UNKNOWN_ITEM_SENTINEL"},
                },
                {"type": "UNKNOWN_EVENT_SENTINEL"},
                {"type": "turn.completed", "usage": {}},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            trace = parse_trace(path)
            serialized = json.dumps(trace)
            self.assertEqual(trace["status"], "degraded")
            self.assertEqual(trace["unknown_events"]["count"], 1)
            self.assertEqual(trace["unknown_item_types"]["count"], 1)
            self.assertNotIn("UNKNOWN_EVENT_SENTINEL", serialized)
            self.assertNotIn("UNKNOWN_ITEM_SENTINEL", serialized)


if __name__ == "__main__":
    unittest.main()
