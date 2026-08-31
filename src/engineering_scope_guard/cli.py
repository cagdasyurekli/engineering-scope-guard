"""Command-line interface for the V0 Shadow Scope Analyzer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .doctor import inspect_codex
from .report import build_events, write_json, write_outputs
from .repository import (
    LOC_DEFINITION_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotError,
    compare_snapshots,
    snapshot_repository,
)
from .trace import parse_trace


class ConfigurationError(RuntimeError):
    """Raised for invalid or unsafe local analyzer configuration."""


def _is_within(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigurationError(f"expected a JSON object in {path}")
    return value


def load_config(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("schema_version") != 1:
        raise ConfigurationError("unsupported config schema_version")
    expected = {"schema_version", "repository_root", "state_dir", "instruction_files"}
    if set(payload) != expected:
        raise ConfigurationError("config fields do not match schema version 1")
    if not isinstance(payload["repository_root"], str) or not isinstance(payload["state_dir"], str):
        raise ConfigurationError("repository_root and state_dir must be strings")
    instruction_files = payload["instruction_files"]
    if not isinstance(instruction_files, list) or not all(
        isinstance(item, str) and item and not Path(item).is_absolute()
        for item in instruction_files
    ):
        raise ConfigurationError("instruction_files must contain relative paths")
    if any(".." in candidate.parts for candidate in map(Path, instruction_files)):
        raise ConfigurationError("instruction_files may not escape the repository")

    repository_root = Path(payload["repository_root"]).resolve(strict=True)
    state_dir = Path(payload["state_dir"]).resolve(strict=True)
    if not repository_root.is_dir() or not state_dir.is_dir():
        raise ConfigurationError("repository_root and state_dir must be directories")
    if _is_within(state_dir, repository_root):
        raise ConfigurationError("state_dir must be outside the target repository")
    payload["repository_root"] = str(repository_root)
    payload["state_dir"] = str(state_dir)
    return payload


def initialize(repository: Path, state_dir: Path) -> Path:
    repository_root = repository.resolve(strict=True)
    if not repository_root.is_dir():
        raise ConfigurationError("--repo must be a directory")
    state_resolved = state_dir.resolve(strict=False)
    if _is_within(state_resolved, repository_root):
        raise ConfigurationError("--state-dir must be outside the target repository")
    state_resolved.mkdir(parents=True, exist_ok=True)
    state_resolved = state_resolved.resolve(strict=True)
    config = {
        "schema_version": 1,
        "repository_root": str(repository_root),
        "state_dir": str(state_resolved),
        "instruction_files": ["AGENTS.md", "AGENTS.override.md"],
    }
    config_path = state_resolved / "config.json"
    if config_path.exists():
        existing = _read_json(config_path)
        if existing != config:
            raise ConfigurationError(f"different configuration already exists: {config_path}")
        return config_path
    write_json(config_path, config)
    return config_path


def take_snapshot(config_path: Path, label: str) -> Path:
    config = load_config(config_path)
    snapshot = snapshot_repository(Path(config["repository_root"]), label)
    output = Path(config["state_dir"]) / "snapshots" / f"{label}.json"
    write_json(output, snapshot)
    return output


def _validate_snapshot(snapshot: dict[str, Any], expected_label: str) -> None:
    if (
        snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION
        or snapshot.get("kind") != "repository_snapshot"
        or snapshot.get("label") != expected_label
        or not isinstance(snapshot.get("entries"), list)
        or not isinstance(snapshot.get("dependencies"), list)
        or not isinstance(snapshot.get("warnings"), list)
        or not all(isinstance(warning, str) for warning in snapshot.get("warnings", []))
        or not isinstance(snapshot.get("measurement_definition"), dict)
        or snapshot["measurement_definition"].get("loc") != LOC_DEFINITION_VERSION
    ):
        raise ConfigurationError(
            f"{expected_label} snapshot does not match schema version "
            f"{SNAPSHOT_SCHEMA_VERSION}"
        )

    paths: set[str] = set()
    for entry in snapshot["entries"]:
        if not isinstance(entry, dict):
            raise ConfigurationError(f"{expected_label} snapshot has an invalid entry")
        path = entry.get("path")
        text = entry.get("text")
        if (
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or entry.get("kind") not in {"file", "symlink", "special"}
            or not isinstance(entry.get("bytes"), int)
            or entry["bytes"] < 0
            or (entry.get("sha256") is not None and not isinstance(entry.get("sha256"), str))
        ):
            raise ConfigurationError(f"{expected_label} snapshot has an invalid entry")
        if path in paths:
            raise ConfigurationError(f"{expected_label} snapshot contains duplicate paths")
        paths.add(path)
        if text is not None and (
            not isinstance(text, dict)
            or not isinstance(text.get("line_count"), int)
            or not isinstance(text.get("line_hashes"), list)
            or text.get("line_count") != len(text.get("line_hashes", []))
            or not all(isinstance(value, str) for value in text.get("line_hashes", []))
        ):
            raise ConfigurationError(f"{expected_label} snapshot has invalid text metadata")

    for manifest in snapshot["dependencies"]:
        if (
            not isinstance(manifest, dict)
            or not isinstance(manifest.get("path"), str)
            or not isinstance(manifest.get("ecosystem"), str)
            or not isinstance(manifest.get("scopes"), dict)
        ):
            raise ConfigurationError(f"{expected_label} snapshot has an invalid manifest")
        for scope, dependencies in manifest["scopes"].items():
            if (
                not isinstance(scope, str)
                or not isinstance(dependencies, dict)
                or not all(
                    isinstance(name, str) and isinstance(fingerprint, str)
                    for name, fingerprint in dependencies.items()
                )
            ):
                raise ConfigurationError(f"{expected_label} snapshot has invalid dependencies")


def run_analysis(
    config_path: Path,
    trace_path: Path,
    capability: dict[str, Any] | None = None,
) -> tuple[int, Path, Path]:
    """Run analysis; injectable capability data keeps offline tests hermetic."""

    config = load_config(config_path)
    state_dir = Path(config["state_dir"])
    before = _read_json(state_dir / "snapshots" / "before.json")
    after = _read_json(state_dir / "snapshots" / "after.json")
    _validate_snapshot(before, "before")
    _validate_snapshot(after, "after")
    delta = compare_snapshots(before, after, config["instruction_files"])
    trace = parse_trace(trace_path)
    capability = capability if capability is not None else inspect_codex()
    events = build_events(delta, trace, capability)
    events_path, report_path = write_outputs(state_dir, events)
    status = events[0]["status"]
    exit_code = {"healthy": 0, "degraded": 2, "unsupported": 3}[status]
    return exit_code, events_path, report_path


def _doctor_text(result: dict[str, Any]) -> str:
    codex = result["codex"]
    hooks = codex["hooks"]
    lines = [
        f"status: {result['status']}",
        f"codex available: {str(codex['available']).lower()}",
        f"codex version: {codex['version'] or 'unknown'}",
        f"codex exec --json: {str(codex['exec_json']).lower()}",
        f"hooks: {hooks['maturity'] or 'unknown'} / enabled={hooks['enabled']}",
        "known coverage gaps:",
    ]
    lines.extend(f"- {gap}" for gap in result["known_gaps"])
    lines.extend(f"diagnostic: {diagnostic}" for diagnostic in result["diagnostics"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engineering_scope_guard")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="inspect local Codex observation capabilities")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    init = subcommands.add_parser("init", help="create local analyzer configuration")
    init.add_argument("--repo", required=True, type=Path)
    init.add_argument("--state-dir", required=True, type=Path)

    snapshot = subcommands.add_parser("snapshot", help="record repository structural state")
    snapshot.add_argument("--config", required=True, type=Path)
    snapshot.add_argument("--label", required=True, choices=("before", "after"))

    analyze = subcommands.add_parser("analyze", help="compare snapshots and ingest a Codex trace")
    analyze.add_argument("--config", required=True, type=Path)
    analyze.add_argument("--trace", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "doctor":
            result = inspect_codex()
            print(json.dumps(result, sort_keys=True) if arguments.as_json else _doctor_text(result))
            return {"healthy": 0, "degraded": 2, "unsupported": 3}[result["status"]]
        if arguments.command == "init":
            print(initialize(arguments.repo, arguments.state_dir))
            return 0
        if arguments.command == "snapshot":
            print(take_snapshot(arguments.config, arguments.label))
            return 0
        if arguments.command == "analyze":
            code, events, report = run_analysis(arguments.config, arguments.trace)
            print(f"events: {events}")
            print(f"report: {report}")
            return code
    except (ConfigurationError, SnapshotError, ValueError, OSError) as error:
        print(f"engineering_scope_guard: {error}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")
