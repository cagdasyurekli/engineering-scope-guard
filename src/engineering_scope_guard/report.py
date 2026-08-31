"""Deterministic machine-readable and human-readable output."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

_STATUS_ORDER = {"healthy": 0, "degraded": 1, "unsupported": 2}
OUTPUT_SCHEMA_NAME = "engineering-scope-guard.event"
OUTPUT_SCHEMA_VERSION = 1


def combined_status(*statuses: str) -> str:
    return max(statuses, key=lambda value: _STATUS_ORDER[value])


def build_events(
    delta: dict[str, Any],
    trace: dict[str, Any],
    capability: dict[str, Any],
) -> list[dict[str, Any]]:
    snapshot_status = "degraded" if delta["snapshot_warnings"] else "healthy"
    capability_for_analysis = capability["status"]
    if capability_for_analysis == "unsupported" and trace["status"] != "unsupported":
        capability_for_analysis = "degraded"
    status = combined_status(trace["status"], capability_for_analysis, snapshot_status)
    limitations = sorted(
        set(
            capability.get("known_gaps", [])
            + trace.get("limitations", [])
            + delta.get("snapshot_warnings", [])
        )
    )
    command_field_problems = trace.get("command_observation_problems", [])
    if command_field_problems:
        command_status = "degraded"
    elif not trace["commands"]:
        command_status = "unavailable"
    elif "codex-hook-json" in trace["adapter"]:
        command_status = "degraded"
    else:
        command_status = "healthy"
    coverage_dimensions = {
        "trace": {
            "status": trace["status"],
            "recognized_records": trace["recognized_records"],
        },
        "snapshot": {
            "status": snapshot_status,
            "warning_count": len(delta["snapshot_warnings"]),
        },
        "command_verification": {
            "status": command_status,
            "observed_commands": len(trace["commands"]),
            "invalid_or_missing_fields": len(command_field_problems),
        },
        "usage": trace["usage_coverage"],
    }

    def event(name: str, **values: Any) -> dict[str, Any]:
        return {
            "schema_name": OUTPUT_SCHEMA_NAME,
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "event": name,
            **values,
        }

    events: list[dict[str, Any]] = [
        event(
            "coverage_health",
            status=status,
            static_capability_status=capability["status"],
            trace_status=trace["status"],
            codex_version=capability.get("codex", {}).get("version"),
            adapter=trace["adapter"],
            coverage_dimensions=coverage_dimensions,
            output_contract={
                "source": "target bytes and supplied Codex records are read locally and transiently",
                "normalized": "repository-relative POSIX paths, normalized package names, and hashes",
                "derived": "deltas, bounded summaries, health, and candidate review events",
                "path_sensitivity": "repository-relative paths are sensitive local metadata",
            },
            diagnostics=sorted(
                set(capability.get("diagnostics", []) + trace.get("diagnostics", []))
            ),
            limitations=limitations,
        ),
        event("structural_delta", files=delta["files"], loc=delta["loc"]),
        event("dependency_delta", **delta["dependencies"]),
        event("test_file_delta", **delta["tests"]),
        event("instruction_delta", files=delta["instructions"]),
        event("infrastructure_delta", **delta["infrastructure"]),
        event(
            "trace_summary",
            adapter=trace["adapter"],
            recognized_records=trace["recognized_records"],
            record_counts=trace["record_counts"],
            malformed_lines=trace["malformed_lines"],
            unknown_events=trace["unknown_events"],
            unknown_item_types=trace["unknown_item_types"],
            missing_fields=trace["missing_fields"],
            invalid_fields=trace["invalid_fields"],
            commands=trace["commands"],
            command_observation_problems=command_field_problems,
            file_change_items=trace["file_change_items"],
            runtime_errors=trace["runtime_errors"],
            turn_outcomes=trace["turn_outcomes"],
            usage_coverage=trace["usage_coverage"],
        ),
    ]
    events.extend(
        event("candidate_review_event", **signal)
        for signal in delta["candidate_review_events"]
    )
    return events


def _paths(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def render_report(events: list[dict[str, Any]]) -> str:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_name.setdefault(event["event"], []).append(event)

    health = by_name["coverage_health"][0]
    structural = by_name["structural_delta"][0]
    dependencies = by_name["dependency_delta"][0]
    tests = by_name["test_file_delta"][0]
    instructions = by_name["instruction_delta"][0]
    infrastructure = by_name["infrastructure_delta"][0]
    trace = by_name["trace_summary"][0]
    signals = by_name.get("candidate_review_event", [])

    lines = [
        "# Shadow Scope Report",
        "",
        "This report contains deterministic structural facts and candidate review events. "
        "It does not classify the change as overengineered.",
        "",
        "## Coverage",
        "",
        f"- Overall health: **{health['status']}**",
        f"- Static Codex capability: {health['static_capability_status']}",
        f"- Dynamic trace health: {health['trace_status']}",
        f"- Codex version observed locally: {health['codex_version'] or 'unknown'}",
        f"- Adapter: {', '.join(health['adapter']) or 'none'}",
        f"- Recognized trace records: {trace['recognized_records']}",
    ]
    for name, dimension in health["coverage_dimensions"].items():
        lines.append(f"- {name.replace('_', '/')} coverage: {dimension['status']}")
    if health["diagnostics"]:
        lines.append(f"- Diagnostics: {'; '.join(health['diagnostics'])}")

    counts = structural["files"]["counts"]
    lines.extend(
        [
            "",
            "## Structural delta",
            "",
            "- Files: "
            f"{counts['added']} added, {counts['deleted']} deleted, "
            f"{counts['modified']} modified",
            f"- LOC ({structural['loc']['definition_version']}): "
            f"+{structural['loc']['added']} / -{structural['loc']['deleted']}",
            "- Changed entry kinds: "
            + ", ".join(
                f"{kind}={count}"
                for kind, count in structural["loc"]["changed_entry_kinds"].items()
            ),
            f"- Added: {_paths(structural['files']['added'])}",
            f"- Deleted: {_paths(structural['files']['deleted'])}",
            f"- Modified: {_paths(structural['files']['modified'])}",
            "",
            "## Dependencies",
            "",
            f"- Added: {len(dependencies['added'])}",
            f"- Removed: {len(dependencies['removed'])}",
            f"- Specification changes: {len(dependencies['changed'])}",
            "",
            "## Tests, instructions, and infrastructure",
            "",
            f"- Test files added: {_paths(tests['added'])}",
            f"- Test files deleted: {_paths(tests['deleted'])}",
            f"- Test files modified: {_paths(tests['modified'])}",
            f"- Instruction files with size changes: {len(instructions['files'])}",
            "- Candidate infrastructure/config artifacts: "
            + _paths([item["path"] for item in infrastructure["candidates"]]),
            "",
            "## Candidate review events",
            "",
        ]
    )
    if signals:
        for signal in signals:
            detail = signal.get("path") or signal.get("count") or "threshold crossed"
            lines.append(f"- `{signal['rule_id']}`: {detail}")
    else:
        lines.append("None.")

    lines.extend(["", "## Limitations", ""])
    for limitation in health["limitations"]:
        lines.append(f"- {limitation}")
    if not health["limitations"]:
        lines.append("None reported.")
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def write_outputs(state_dir: Path, events: list[dict[str, Any]]) -> tuple[Path, Path]:
    events_path = state_dir / "events.jsonl"
    report_path = state_dir / "report.md"
    jsonl = "".join(
        json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        for event in events
    )
    _atomic_write(events_path, jsonl)
    _atomic_write(report_path, render_report(events))
    return events_path, report_path
