"""Privacy-bounded ingestion of supported Codex JSON records."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

KNOWN_TOP_LEVEL_EVENTS = {
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
    "item.updated",
    "item.completed",
    "error",
}
KNOWN_ITEM_TYPES = {
    "agent_message",
    "reasoning",
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "web_search",
    "plan_update",
}
KNOWN_HOOK_EVENTS = {
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}
TURN_SCOPED_HOOKS = KNOWN_HOOK_EVENTS - {"SessionStart", "SessionEnd"}
KNOWN_COMMAND_STATUSES = {"in_progress", "completed", "failed"}
MAX_UNKNOWN_IDENTIFIERS = 20

HOOK_LIMITATIONS = [
    "hook-only input cannot prove complete task coverage",
    "hosted tools are not emitted through local tool hooks",
    "specialized local tool paths may opt out of hooks",
    "SessionEnd is not an immediate turn boundary",
]


_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _effective_tokens(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    while tokens and _ASSIGNMENT.match(tokens[0]):
        tokens.pop(0)
    if tokens and PurePosixPath(tokens[0]).name == "env":
        tokens.pop(0)
        while tokens and (tokens[0].startswith("-") or _ASSIGNMENT.match(tokens[0])):
            tokens.pop(0)
    if (
        len(tokens) >= 3
        and PurePosixPath(tokens[0]).name in {"bash", "sh", "zsh"}
        and tokens[1] in {"-c", "-lc"}
    ):
        return _effective_tokens(tokens[2])
    return tokens


def _verification_kind(command: str) -> str:
    tokens = _effective_tokens(command)
    if not tokens:
        return "other"
    program = PurePosixPath(tokens[0]).name.lower()
    arguments = [value.lower() for value in tokens[1:]]

    if program in {"pytest", "py.test", "unittest"}:
        return "test"
    if program.startswith("python") and len(arguments) >= 2 and arguments[0] == "-m":
        if arguments[1] in {"pytest", "unittest"}:
            return "test"
        if arguments[1] == "build":
            return "build"
    if program in {"npm", "pnpm", "yarn"} and arguments:
        script = arguments[1] if arguments[0] == "run" and len(arguments) > 1 else arguments[0]
        if script == "test" or script.startswith("test:"):
            return "test"
        if script == "lint" or script.startswith("lint:"):
            return "lint"
        if script in {"type", "typecheck", "type-check"} or script.startswith("typecheck:"):
            return "type"
        if script == "build" or script.startswith("build:"):
            return "build"
    if program == "cargo" and arguments:
        return {"test": "test", "build": "build", "clippy": "lint"}.get(
            arguments[0], "other"
        )
    if program == "go" and arguments:
        return {"test": "test", "build": "build"}.get(arguments[0], "other")
    if program in {"ruff", "eslint"}:
        return "lint"
    if program in {"mypy", "pyright", "tsc"}:
        return "type"
    if program == "make" and arguments:
        return {"test": "test", "lint": "lint", "build": "build"}.get(
            arguments[0], "other"
        )
    return "other"


def _program(command: str) -> str | None:
    tokens = _effective_tokens(command)
    if not tokens:
        return None
    return PurePosixPath(tokens[0]).name


def _bounded_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_unknown(value: str, hashes: list[str]) -> None:
    identifier = _bounded_identifier(value)
    if identifier not in hashes and len(hashes) < MAX_UNKNOWN_IDENTIFIERS:
        hashes.append(identifier)


def _command_summary(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw_command = item.get("command", "")
    if isinstance(raw_command, list):
        command = " ".join(str(part) for part in raw_command)
    else:
        command = str(raw_command)
    invalid_fields: list[str] = []
    raw_status = item.get("status")
    status = (
        raw_status
        if isinstance(raw_status, str) and raw_status in KNOWN_COMMAND_STATUSES
        else None
    )
    if raw_status is not None and status is None:
        invalid_fields.append("item.status")
    raw_exit_code = item.get("exit_code")
    exit_code = (
        raw_exit_code
        if raw_exit_code is None
        or (isinstance(raw_exit_code, int) and not isinstance(raw_exit_code, bool))
        else None
    )
    if raw_exit_code is not None and exit_code is None:
        invalid_fields.append("item.exit_code")
    return {
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "program": _program(command),
        "verification_kind": _verification_kind(command),
        "status": status,
        "exit_code": exit_code,
    }, invalid_fields


def parse_trace(path: Path) -> dict[str, Any]:
    """Parse supported JSONL without retaining model or tool payload content."""

    malformed_lines: list[int] = []
    unknown_event_hashes: list[str] = []
    unknown_item_type_hashes: list[str] = []
    unknown_event_count = 0
    unknown_item_type_count = 0
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    command_observation_problems: list[str] = []
    command_summaries: list[dict[str, Any]] = []
    record_counts: dict[str, int] = {}
    item_starts: set[str] = set()
    adapter_types: set[str] = set()
    thread_starts = turn_starts = turn_terminals = error_count = file_change_items = 0
    completed_turns = failed_turns = completed_turns_with_usage = 0
    invalid_usage_records = 0
    recognized_records = 0
    turn_open = False
    sequence_diagnostics: set[str] = set()

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"cannot read trace: {error}") from error

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            malformed_lines.append(line_number)
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines.append(line_number)
            continue
        if not isinstance(record, dict):
            malformed_lines.append(line_number)
            continue

        event_type = record.get("type")
        hook_event = record.get("hook_event_name")
        if isinstance(event_type, str):
            adapter_types.add("codex-exec-json")
            if event_type not in KNOWN_TOP_LEVEL_EVENTS:
                unknown_event_count += 1
                _record_unknown(event_type, unknown_event_hashes)
                continue
            recognized_records += 1
            record_counts[event_type] = record_counts.get(event_type, 0) + 1
            if event_type == "thread.started":
                if "thread_id" not in record:
                    missing_fields.append(f"line {line_number}: thread_id")
                elif not isinstance(record["thread_id"], str) or not record["thread_id"]:
                    invalid_fields.append(f"line {line_number}: thread_id")
                if thread_starts:
                    sequence_diagnostics.add("multiple thread.started records")
                if turn_starts:
                    sequence_diagnostics.add("thread.started occurred after turn activity")
                thread_starts += 1
            elif event_type == "turn.started":
                if thread_starts == 0:
                    sequence_diagnostics.add("turn.started occurred before thread.started")
                if turn_open:
                    sequence_diagnostics.add("turn.started occurred before the prior turn ended")
                turn_starts += 1
                turn_open = True
            elif event_type in {"turn.completed", "turn.failed"}:
                if event_type == "turn.completed":
                    completed_turns += 1
                    if isinstance(record.get("usage"), dict):
                        completed_turns_with_usage += 1
                    else:
                        invalid_usage_records += 1
                else:
                    failed_turns += 1
                if not turn_open:
                    sequence_diagnostics.add("terminal turn event occurred without an open turn")
                else:
                    turn_open = False
                turn_terminals += 1
            elif event_type == "error":
                error_count += 1
            elif event_type.startswith("item."):
                if not turn_open:
                    sequence_diagnostics.add("item event occurred outside an open turn")
                item = record.get("item")
                if not isinstance(item, dict):
                    missing_fields.append(f"line {line_number}: item object")
                    continue
                item_type = item.get("type")
                if not isinstance(item_type, str):
                    missing_fields.append(f"line {line_number}: item.type")
                    continue
                if item_type not in KNOWN_ITEM_TYPES:
                    unknown_item_type_count += 1
                    _record_unknown(item_type, unknown_item_type_hashes)
                item_id = item.get("id")
                if "id" not in item:
                    missing_fields.append(f"line {line_number}: item.id")
                elif not isinstance(item_id, str) or not item_id:
                    invalid_fields.append(f"line {line_number}: item.id")
                if event_type == "item.started" and isinstance(item_id, str):
                    item_starts.add(item_id)
                elif event_type == "item.completed" and isinstance(item_id, str):
                    item_starts.discard(item_id)
                if event_type == "item.completed" and item_type == "command_execution":
                    if "command" not in item:
                        problem = f"line {line_number}: item.command"
                        missing_fields.append(problem)
                        command_observation_problems.append(problem)
                    else:
                        raw_command = item["command"]
                    if "command" in item and not (
                        isinstance(raw_command, str)
                        or (
                            isinstance(raw_command, list)
                            and all(isinstance(value, str) for value in raw_command)
                        )
                    ):
                        problem = f"line {line_number}: item.command"
                        invalid_fields.append(problem)
                        command_observation_problems.append(problem)
                    elif "command" in item:
                        summary, command_invalid_fields = _command_summary(item)
                        command_summaries.append(summary)
                        problems = [
                            f"line {line_number}: {field}" for field in command_invalid_fields
                        ]
                        invalid_fields.extend(problems)
                        command_observation_problems.extend(problems)
                elif event_type == "item.completed" and item_type == "file_change":
                    file_change_items += 1
        elif isinstance(hook_event, str):
            adapter_types.add("codex-hook-json")
            if hook_event not in KNOWN_HOOK_EVENTS:
                unknown_event_count += 1
                _record_unknown(hook_event, unknown_event_hashes)
                continue
            recognized_records += 1
            record_counts[hook_event] = record_counts.get(hook_event, 0) + 1
            for required in ("session_id", "cwd"):
                if required not in record:
                    missing_fields.append(f"line {line_number}: {required}")
                elif not isinstance(record[required], str) or not record[required]:
                    invalid_fields.append(f"line {line_number}: {required}")
            if hook_event in TURN_SCOPED_HOOKS:
                if "turn_id" not in record:
                    missing_fields.append(f"line {line_number}: turn_id")
                elif not isinstance(record["turn_id"], str) or not record["turn_id"]:
                    invalid_fields.append(f"line {line_number}: turn_id")
            if hook_event in {"PreToolUse", "PostToolUse"}:
                for required in ("tool_name", "tool_use_id"):
                    if required not in record:
                        missing_fields.append(f"line {line_number}: {required}")
                    elif not isinstance(record[required], str) or not record[required]:
                        invalid_fields.append(f"line {line_number}: {required}")
                if "tool_input" not in record:
                    missing_fields.append(f"line {line_number}: tool_input")
                elif not isinstance(record["tool_input"], dict):
                    invalid_fields.append(f"line {line_number}: tool_input")
            elif hook_event == "PermissionRequest":
                if "tool_name" not in record:
                    missing_fields.append(f"line {line_number}: tool_name")
                elif not isinstance(record["tool_name"], str) or not record["tool_name"]:
                    invalid_fields.append(f"line {line_number}: tool_name")
                if "tool_input" not in record:
                    missing_fields.append(f"line {line_number}: tool_input")
                elif not isinstance(record["tool_input"], dict):
                    invalid_fields.append(f"line {line_number}: tool_input")
            if hook_event == "PostToolUse":
                tool_name = record.get("tool_name")
                if not isinstance(tool_name, str) or not tool_name:
                    command_observation_problems.append(
                        f"line {line_number}: tool_name"
                    )
                elif tool_name == "Bash":
                    for required in ("tool_use_id", "tool_input"):
                        value = record.get(required)
                        if (
                            required not in record
                            or (required == "tool_use_id" and not (
                                isinstance(value, str) and value
                            ))
                            or (required == "tool_input" and not isinstance(value, dict))
                        ):
                            command_observation_problems.append(
                                f"line {line_number}: {required}"
                            )

            if hook_event == "PostToolUse" and record.get("tool_name") == "Bash":
                tool_input = record.get("tool_input")
                if isinstance(tool_input, dict) and "command" not in tool_input:
                    problem = f"line {line_number}: tool_input.command"
                    missing_fields.append(problem)
                    command_observation_problems.append(problem)
                elif isinstance(tool_input, dict):
                    hook_command = tool_input["command"]
                    if not (
                        isinstance(hook_command, str)
                        or (
                            isinstance(hook_command, list)
                            and all(isinstance(value, str) for value in hook_command)
                        )
                    ):
                        problem = f"line {line_number}: tool_input.command"
                        invalid_fields.append(problem)
                        command_observation_problems.append(problem)
                    else:
                        summary, command_invalid_fields = _command_summary(
                            {
                                "command": hook_command,
                                "status": "completed",
                                "exit_code": None,
                            }
                        )
                        command_summaries.append(summary)
                        invalid_fields.extend(
                            f"line {line_number}: {field}"
                            for field in command_invalid_fields
                        )
        else:
            malformed_lines.append(line_number)

    limitations: list[str] = []
    diagnostics: list[str] = sorted(sequence_diagnostics)
    if len(adapter_types) > 1:
        diagnostics.append("trace mixes exec JSONL and hook JSON records")
    if "codex-hook-json" in adapter_types:
        limitations.extend(HOOK_LIMITATIONS)
    if "codex-exec-json" in adapter_types:
        if thread_starts == 0:
            diagnostics.append("missing thread.started")
        if turn_starts == 0:
            diagnostics.append("missing turn.started")
        if turn_starts != turn_terminals:
            diagnostics.append("turn start/terminal counts are unbalanced")
        if turn_open:
            diagnostics.append("trace ended with an open turn")
    if malformed_lines:
        diagnostics.append("malformed JSONL records were skipped")
    if unknown_event_count:
        diagnostics.append("unknown event types were skipped")
    if unknown_item_type_count:
        diagnostics.append("unknown item types were not measured")
    if item_starts:
        diagnostics.append("item starts without matching completion remain")
    if missing_fields:
        diagnostics.append("recognized records were missing required fields")
    if invalid_fields:
        diagnostics.append("recognized records contained invalid fields")

    if recognized_records == 0:
        status = "unsupported"
    elif diagnostics or "codex-hook-json" in adapter_types:
        status = "degraded"
    else:
        status = "healthy"

    if "codex-exec-json" not in adapter_types or completed_turns == 0:
        usage_status = "unavailable"
    elif (
        completed_turns_with_usage == completed_turns
        and failed_turns == 0
        and "codex-hook-json" not in adapter_types
    ):
        usage_status = "healthy"
    else:
        usage_status = "degraded"

    return {
        "status": status,
        "adapter": sorted(adapter_types),
        "recognized_records": recognized_records,
        "record_counts": dict(sorted(record_counts.items())),
        "malformed_lines": malformed_lines,
        "unknown_events": {
            "count": unknown_event_count,
            "sha256": sorted(unknown_event_hashes),
        },
        "unknown_item_types": {
            "count": unknown_item_type_count,
            "sha256": sorted(unknown_item_type_hashes),
        },
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
        "unmatched_item_ids": sorted(item_starts),
        "commands": command_summaries,
        "command_observation_problems": command_observation_problems,
        "file_change_items": file_change_items,
        "runtime_errors": error_count,
        "turn_outcomes": {
            "completed": completed_turns,
            "failed": failed_turns,
        },
        "usage_coverage": {
            "status": usage_status,
            "completed_turns": completed_turns,
            "completed_turns_with_usage": completed_turns_with_usage,
            "failed_turns_without_usage": failed_turns,
            "invalid_or_missing_usage_records": invalid_usage_records,
        },
        "diagnostics": sorted(set(diagnostics)),
        "limitations": sorted(set(limitations)),
    }
