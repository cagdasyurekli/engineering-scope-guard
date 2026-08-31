#!/usr/bin/env python3
"""Export or verify the sealed Reasoning Effort v2 analysis artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.reasoning_effort_v2_analysis import (
    AnalysisInputError,
    analyze_reasoning_effort_v2,
)

try:
    from scripts import reasoning_effort_v2_runner as durable
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    import reasoning_effort_v2_runner as durable


ENVELOPE_NAME = "reasoning-effort-v2-terminal-envelope.json"
ANALYSIS_NAME = "reasoning-effort-v2-analysis.json"


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _read_private(path: Path, label: str) -> dict[str, Any]:
    durable._require_private_artifact_path(path)
    value, raw = durable._canonical_json_file(path, label)
    if raw != _canonical_bytes(value):
        raise ExperimentConfigurationError(f"{label} is not canonical JSON")
    return value


def _read_public(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ExperimentConfigurationError(f"{label} is missing or not a regular file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExperimentConfigurationError(f"{label} is unreadable or malformed") from error
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise ExperimentConfigurationError(f"{label} is not a canonical JSON object")
    return value


def _write_once(path: Path, value: dict[str, Any]) -> None:
    encoded = _canonical_bytes(value)
    if path.exists() or path.is_symlink():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != encoded:
            raise ExperimentConfigurationError(
                f"refusing to overwrite a differing analysis artifact: {path}"
            )
        return
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise


def export_artifacts(
    *, execution_root: Path, output_root: Path, write: bool
) -> dict[str, Any]:
    """Recompute the ledger-derived envelope and deterministic analysis."""

    storage_root = durable._execution_storage_root(execution_root)
    if execution_root.resolve() != storage_root.resolve():
        raise ExperimentConfigurationError("--execution-root must name the initialized root")
    unresolved_output_root = output_root.absolute()
    if not unresolved_output_root.is_dir() or unresolved_output_root.is_symlink():
        raise ExperimentConfigurationError("--output-root must be an existing non-symlink directory")
    output_root = unresolved_output_root.resolve()
    if output_root.is_relative_to(storage_root.resolve()):
        raise ExperimentConfigurationError("public analysis output must be outside private execution storage")

    with durable._lock(storage_root / "runner.lock"):
        contract = _read_private(storage_root / "contract.json", "contract")
        private_pool = _read_private(storage_root / "private-pool.json", "private pool")
        live_seal = _read_private(storage_root / "live-seal.json", "live seal")
        envelope = durable.export_analysis_terminal_envelope(
            contract,
            private_pool,
            storage_root / "ledger.jsonl",
            storage_root / "receipts",
            live_seal,
        )
        analysis = analyze_reasoning_effort_v2(contract, envelope)

    envelope_path = output_root / ENVELOPE_NAME
    analysis_path = output_root / ANALYSIS_NAME
    if write:
        _write_once(envelope_path, envelope)
        _write_once(analysis_path, analysis)
    persisted_envelope = _read_public(envelope_path, "terminal envelope")
    persisted_analysis = _read_public(analysis_path, "analysis")
    if persisted_envelope != envelope or persisted_analysis != analysis:
        raise ExperimentConfigurationError(
            "persisted analysis artifacts differ from current sealed execution evidence"
        )
    return {
        "command": "build" if write else "verify",
        "status": "verified",
        "terminal_envelope_sha256": envelope["envelope_sha256"],
        "analysis_sha256": analysis["analysis_sha256"],
        "terminal_envelope_path": str(envelope_path),
        "analysis_path": str(analysis_path),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("command", choices=("build", "verify"))
    value.add_argument("--execution-root", type=Path, required=True)
    value.add_argument("--output-root", type=Path, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        result = export_artifacts(
            execution_root=args.execution_root,
            output_root=args.output_root,
            write=args.command == "build",
        )
    except (ExperimentConfigurationError, AnalysisInputError, OSError) as error:
        print(f"reasoning_effort_v2_export: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
