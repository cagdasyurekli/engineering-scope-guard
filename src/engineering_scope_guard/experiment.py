"""Minimal local preparation and evidence capture for development experiments.

This module does not invoke Codex or apply an intervention to normal work. It
prepares isolated cell directories and normalizes evidence supplied by a
separate, explicitly authorized development run.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .report import OUTPUT_SCHEMA_NAME, OUTPUT_SCHEMA_VERSION, write_json
from .repository import EXCLUDED_DIRECTORIES, snapshot_repository
from .trace import parse_trace

ARMS: tuple[str, ...] = ("baseline", "short", "full")
PILOT_ARMS: tuple[str, ...] = ("baseline", "short")
POLICY_FILES = {"baseline": None, "short": "short.txt", "full": "full.txt"}
USAGE_COMPONENTS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


class ExperimentConfigurationError(RuntimeError):
    """Raised when a development experiment cell or record is unsafe/invalid."""


def _is_within(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected a JSON object in {path}")
    return value


def _policy_bytes(policies_dir: Path, arm: str) -> bytes | None:
    filename = POLICY_FILES[arm]
    if filename is None:
        return None
    path = policies_dir / filename
    try:
        value = path.read_bytes()
    except OSError as error:
        raise ExperimentConfigurationError(f"cannot read policy {path}: {error}") from error
    if not value or not value.endswith(b"\n"):
        raise ExperimentConfigurationError(f"policy must be non-empty and newline-terminated: {path}")
    return value


def _snapshot_fingerprint(root: Path) -> str:
    snapshot = snapshot_repository(root, "experiment-start")
    canonical = {
        "schema_version": snapshot["schema_version"],
        "measurement_definition": snapshot["measurement_definition"],
        "entries": snapshot["entries"],
        "dependencies": snapshot["dependencies"],
        "warnings": snapshot["warnings"],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return set(names).intersection(EXCLUDED_DIRECTORIES)


def _prepare_cells(
    source_repository: Path,
    state_dir: Path,
    policies_dir: Path,
    arms: tuple[str, ...],
    schema_name: str,
) -> dict[str, Any]:
    if not arms or len(set(arms)) != len(arms) or any(arm not in POLICY_FILES for arm in arms):
        raise ExperimentConfigurationError("experiment arms are invalid")

    source = source_repository.resolve(strict=True)
    policies = policies_dir.resolve(strict=True)
    state = state_dir.resolve(strict=False)
    if not source.is_dir() or not policies.is_dir():
        raise ExperimentConfigurationError("source repository and policies path must be directories")
    if _is_within(state, source):
        raise ExperimentConfigurationError("experiment state must be outside the source repository")
    if state.exists() and any(state.iterdir()):
        raise ExperimentConfigurationError("experiment state directory must be absent or empty")
    state.mkdir(parents=True, exist_ok=True)

    source_fingerprint = _snapshot_fingerprint(source)
    cells: list[dict[str, Any]] = []
    for arm in arms:
        cell = state / "cells" / arm
        repository = cell / "repository"
        codex_home = cell / "codex-home"
        raw = cell / "raw"
        derived = cell / "derived"
        repository.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, repository, symlinks=True, ignore=_copy_ignore)
        codex_home.mkdir()
        raw.mkdir()
        derived.mkdir()

        policy = _policy_bytes(policies, arm)
        intervention = cell / "intervention.txt"
        if policy is not None:
            intervention.write_bytes(policy)
        fingerprint = _snapshot_fingerprint(repository)
        if fingerprint != source_fingerprint:
            raise ExperimentConfigurationError(f"{arm} repository start differs from the source")
        cells.append(
            {
                "arm": arm,
                "repository": f"cells/{arm}/repository",
                "codex_home": f"cells/{arm}/codex-home",
                "raw_output": f"cells/{arm}/raw",
                "derived_output": f"cells/{arm}/derived",
                "intervention": None if policy is None else f"cells/{arm}/intervention.txt",
                "intervention_sha256": None if policy is None else hashlib.sha256(policy).hexdigest(),
                "repository_fingerprint": fingerprint,
            }
        )

    manifest = {
        "schema_name": schema_name,
        "schema_version": 1,
        "arms": list(arms),
        "source_repository_fingerprint": source_fingerprint,
        "cells": cells,
    }
    write_json(state / "cells.json", manifest)
    return manifest


def prepare_cells(source_repository: Path, state_dir: Path, policies_dir: Path) -> dict[str, Any]:
    """Create exactly three isolated development cells from one source tree."""

    return _prepare_cells(
        source_repository,
        state_dir,
        policies_dir,
        ARMS,
        "engineering-scope-guard.development-cells",
    )


def prepare_pilot_readiness_cells(
    source_repository: Path, state_dir: Path, policies_dir: Path
) -> dict[str, Any]:
    """Create the proposed two-arm envelope without running a Pilot task."""

    return _prepare_cells(
        source_repository,
        state_dir,
        policies_dir,
        PILOT_ARMS,
        "engineering-scope-guard.pilot-readiness-cells",
    )


def _run_isolation_canary(
    source_repository: Path,
    state_dir: Path,
    policies_dir: Path,
    arms: tuple[str, ...],
    manifest: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    state = state_dir.resolve(strict=True)
    sentinels: dict[str, str] = {}
    all_roots: list[Path] = []
    for cell in manifest["cells"]:
        arm = cell["arm"]
        sentinel = f"isolation-canary:{arm}"
        sentinels[arm] = sentinel
        for key in ("codex_home", "raw_output", "derived_output"):
            root = (state / cell[key]).resolve(strict=True)
            all_roots.append(root)
            (root / "canary.txt").write_text(sentinel + "\n", encoding="utf-8")

        repository = (state / cell["repository"]).resolve(strict=True)
        codex_home = (state / cell["codex_home"]).resolve(strict=True)
        raw = (state / cell["raw_output"]).resolve(strict=True)
        environment = os.environ.copy()
        environment.update(
            {
                "CODEX_HOME": str(codex_home),
                "ESG_EXPERIMENT_ARM": arm,
                "ESG_INTERVENTION_SHA256": cell["intervention_sha256"] or "none",
            }
        )
        probe = (
            "import json,os; print(json.dumps({"
            "'arm':os.environ['ESG_EXPERIMENT_ARM'],"
            "'codex_home':os.environ['CODEX_HOME'],"
            "'intervention_sha256':os.environ['ESG_INTERVENTION_SHA256'],"
            "'working_directory':os.getcwd()},sort_keys=True))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        (raw / "envelope.json").write_text(completed.stdout, encoding="utf-8")
        (raw / "envelope.stderr").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise ExperimentConfigurationError(f"{arm} process-envelope probe failed")
        try:
            receipt = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError(f"{arm} process-envelope receipt is invalid") from error
        expected_receipt = {
            "arm": arm,
            "codex_home": str(codex_home),
            "intervention_sha256": cell["intervention_sha256"] or "none",
            "working_directory": str(repository),
        }
        if receipt != expected_receipt:
            raise ExperimentConfigurationError(f"{arm} process envelope is contaminated")

    if len(all_roots) != len(set(all_roots)):
        raise ExperimentConfigurationError("cell state/output roots are not distinct")
    for cell in manifest["cells"]:
        arm = cell["arm"]
        own = sentinels[arm]
        for key in ("codex_home", "raw_output", "derived_output"):
            value = (state / cell[key] / "canary.txt").read_text(encoding="utf-8").strip()
            if value != own:
                raise ExperimentConfigurationError(f"{arm} {key} is contaminated")

        intervention = cell["intervention"]
        if arm == "baseline" and intervention is not None:
            raise ExperimentConfigurationError("baseline unexpectedly has an intervention")
        if arm != "baseline":
            expected = _policy_bytes(policies_dir.resolve(strict=True), arm)
            actual = (state / intervention).read_bytes()
            if actual != expected:
                raise ExperimentConfigurationError(f"{arm} intervention bytes changed")

    source_after = _snapshot_fingerprint(source_repository.resolve(strict=True))
    if source_after != manifest["source_repository_fingerprint"]:
        raise ExperimentConfigurationError("isolation canary modified the source repository")

    result = {
        "schema_name": schema_name,
        "schema_version": 1,
        "status": "pass",
        "arms": list(arms),
        "byte_identical_repository_starts": True,
        "separate_codex_state": True,
        "separate_raw_and_derived_output": True,
        "isolated_process_envelopes": True,
        "no_cross_arm_intervention_contamination": True,
        "source_repository_unchanged": True,
        "repository_fingerprint": manifest["source_repository_fingerprint"],
    }
    write_json(state / "canary.json", result)
    return result


def run_isolation_canary(
    source_repository: Path, state_dir: Path, policies_dir: Path
) -> dict[str, Any]:
    """Prove the three-arm development filesystem/process envelope."""

    manifest = prepare_cells(source_repository, state_dir, policies_dir)
    return _run_isolation_canary(
        source_repository,
        state_dir,
        policies_dir,
        ARMS,
        manifest,
        "engineering-scope-guard.isolation-canary",
    )


def run_pilot_readiness_isolation_canary(
    source_repository: Path, state_dir: Path, policies_dir: Path
) -> dict[str, Any]:
    """Prove the proposed two-arm envelope without running a Pilot task."""

    manifest = prepare_pilot_readiness_cells(source_repository, state_dir, policies_dir)
    return _run_isolation_canary(
        source_repository,
        state_dir,
        policies_dir,
        PILOT_ARMS,
        manifest,
        "engineering-scope-guard.pilot-readiness-isolation-canary",
    )


def _usage_from_trace(path: Path) -> dict[str, Any]:
    totals = {name: 0 for name in USAGE_COMPONENTS}
    observed: set[str] = set()
    invalid: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ExperimentConfigurationError(f"cannot read trace {path}: {error}") from error
    completed = 0
    for line_number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("type") != "turn.completed":
            continue
        completed += 1
        usage = record.get("usage")
        if not isinstance(usage, dict):
            invalid.append(f"line {line_number}: usage")
            continue
        for name in USAGE_COMPONENTS:
            if name not in usage:
                continue
            value = usage[name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                invalid.append(f"line {line_number}: usage.{name}")
                continue
            observed.add(name)
            totals[name] += value
    return {
        "status": "unavailable" if not observed else ("degraded" if invalid else "available"),
        "completed_turns": completed,
        "components": {name: totals[name] for name in sorted(observed)},
        "invalid_or_missing": invalid,
    }


def _billing(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "unavailable", "reason": "no provider billing record supplied"}
    payload = _read_object(path)
    if payload.get("schema_version") != 1 or set(payload) != {
        "schema_version", "currency", "components"
    }:
        raise ExperimentConfigurationError("billing record does not match schema version 1")
    currency = payload["currency"]
    components = payload["components"]
    if not isinstance(currency, str) or not currency or not isinstance(components, dict):
        raise ExperimentConfigurationError("billing currency/components are invalid")
    normalized: dict[str, str] = {}
    for name, value in sorted(components.items()):
        if not isinstance(name, str) or not name or not isinstance(value, str):
            raise ExperimentConfigurationError("billing components must be named decimal strings")
        try:
            amount = Decimal(value)
        except InvalidOperation as error:
            raise ExperimentConfigurationError("billing component is not decimal") from error
        if not amount.is_finite() or amount < 0:
            raise ExperimentConfigurationError("billing component must be finite and non-negative")
        normalized[name] = value
    return {"status": "available", "currency": currency, "components": normalized}


def _verification(path: Path) -> dict[str, Any]:
    payload = _read_object(path)
    if payload.get("schema_version") != 1 or set(payload) != {"schema_version", "results"}:
        raise ExperimentConfigurationError("verification record does not match schema version 1")
    results = payload["results"]
    if not isinstance(results, list):
        raise ExperimentConfigurationError("verification results must be a list")
    normalized: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict) or set(result) != {"name", "kind", "exit_code"}:
            raise ExperimentConfigurationError("verification result fields are invalid")
        name, kind, exit_code = result["name"], result["kind"], result["exit_code"]
        if (
            not isinstance(name, str) or not name
            or kind not in {"test", "lint", "type", "build", "other"}
            or not isinstance(exit_code, int) or isinstance(exit_code, bool)
        ):
            raise ExperimentConfigurationError("verification result values are invalid")
        normalized.append({"name": name, "kind": kind, "exit_code": exit_code, "passed": exit_code == 0})
    return {
        "results": normalized,
        "all_passed": bool(normalized) and all(item["passed"] for item in normalized),
    }


def _v0_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ExperimentConfigurationError(f"cannot read V0 events {path}: {error}") from error
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentConfigurationError(f"invalid V0 event on line {line_number}") from error
        if (
            not isinstance(event, dict)
            or event.get("schema_name") != OUTPUT_SCHEMA_NAME
            or event.get("schema_version") != OUTPUT_SCHEMA_VERSION
            or not isinstance(event.get("event"), str)
        ):
            raise ExperimentConfigurationError(f"unsupported V0 event on line {line_number}")
        events.append(event)
    if not events:
        raise ExperimentConfigurationError("V0 event input is empty")
    return events


def capture_run_record(
    trace_path: Path,
    execution_path: Path,
    verification_path: Path,
    v0_events_path: Path,
    output_path: Path,
    billing_path: Path | None = None,
) -> dict[str, Any]:
    """Normalize a supplied run trace and already-approved V0 diagnostics."""

    execution = _read_object(execution_path)
    expected = {
        "schema_version", "task_id", "run_id", "arm", "wall_time_ms",
        "timed_out", "process_exit_code",
    }
    if execution.get("schema_version") != 1 or set(execution) != expected:
        raise ExperimentConfigurationError("execution record does not match schema version 1")
    if (
        not isinstance(execution["task_id"], str) or not execution["task_id"]
        or not isinstance(execution["run_id"], str) or not execution["run_id"]
        or execution["arm"] not in ARMS
        or not isinstance(execution["wall_time_ms"], int)
        or isinstance(execution["wall_time_ms"], bool)
        or execution["wall_time_ms"] < 0
        or not isinstance(execution["timed_out"], bool)
        or not (
            execution["process_exit_code"] is None
            or (isinstance(execution["process_exit_code"], int) and not isinstance(execution["process_exit_code"], bool))
        )
    ):
        raise ExperimentConfigurationError("execution record values are invalid")
    if execution["timed_out"] and execution["process_exit_code"] is not None:
        raise ExperimentConfigurationError("timed-out execution must not have a process exit code")

    trace = parse_trace(trace_path)
    record = {
        "schema_name": "engineering-scope-guard.development-run",
        "schema_version": 1,
        "identity": {
            "task_id": execution["task_id"],
            "run_id": execution["run_id"],
            "arm": execution["arm"],
        },
        "execution": {
            "wall_time_ms": execution["wall_time_ms"],
            "timed_out": execution["timed_out"],
            "process_exit_code": execution["process_exit_code"],
        },
        "turns": {
            "started": trace["record_counts"].get("turn.started", 0),
            "completed": trace["turn_outcomes"]["completed"],
            "failed": trace["turn_outcomes"]["failed"],
            "balanced": trace["record_counts"].get("turn.started", 0)
            == trace["turn_outcomes"]["completed"] + trace["turn_outcomes"]["failed"],
        },
        "trace_status": trace["status"],
        "usage": _usage_from_trace(trace_path),
        "billing": _billing(billing_path),
        "verification": _verification(verification_path),
        "v0_events": _v0_events(v0_events_path),
    }
    write_json(output_path, record)
    return record
