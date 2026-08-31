#!/usr/bin/env python3
"""Internal, non-confirmatory development experiment helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engineering_scope_guard.experiment import (
    ExperimentConfigurationError,
    capture_run_record,
    prepare_cells,
    run_isolation_canary,
    run_pilot_readiness_isolation_canary,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    for name in ("prepare", "canary", "pilot-readiness-canary"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True, type=Path)
        command.add_argument("--state-dir", required=True, type=Path)
        command.add_argument("--policies-dir", required=True, type=Path)
    record = commands.add_parser("record")
    record.add_argument("--trace", required=True, type=Path)
    record.add_argument("--execution", required=True, type=Path)
    record.add_argument("--verification", required=True, type=Path)
    record.add_argument("--v0-events", required=True, type=Path)
    record.add_argument("--billing", type=Path)
    record.add_argument("--output", required=True, type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "prepare":
            result = prepare_cells(arguments.source, arguments.state_dir, arguments.policies_dir)
        elif arguments.command == "canary":
            result = run_isolation_canary(arguments.source, arguments.state_dir, arguments.policies_dir)
        elif arguments.command == "pilot-readiness-canary":
            result = run_pilot_readiness_isolation_canary(
                arguments.source, arguments.state_dir, arguments.policies_dir
            )
        else:
            capture_run_record(
                arguments.trace,
                arguments.execution,
                arguments.verification,
                arguments.v0_events,
                arguments.output,
                arguments.billing,
            )
            return 0
    except (ExperimentConfigurationError, OSError, ValueError) as error:
        print(f"development_experiment: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
