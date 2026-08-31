#!/usr/bin/env python3
"""Build or audit the Pilot-v2 preparation-only freeze artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import canonical_bytes, read_object
from engineering_scope_guard.pilot_v2 import build_contract, build_qualification, validate_contract


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--contract", type=Path, default=Path("experiment/pilot_v2_execution_contract.json"))
    qualify = subparsers.add_parser("qualify")
    qualify.add_argument("--contract", type=Path, default=Path("experiment/pilot_v2_execution_contract.json"))
    qualify.add_argument("--output", type=Path, default=Path("experiment/pilot_v2_freeze_qualification.json"))
    audit = subparsers.add_parser("audit")
    audit.add_argument("--contract", type=Path, default=Path("experiment/pilot_v2_execution_contract.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    contract_path = args.contract if args.contract.is_absolute() else root / args.contract
    try:
        if args.command == "build":
            result = build_contract(root)
            _write(contract_path, result)
        else:
            contract = read_object(contract_path)
            validate_contract(contract, root)
            result = build_qualification(root, contract)
            if args.command == "qualify":
                output = args.output if args.output.is_absolute() else root / args.output
                _write(output, result)
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_v2_freeze: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
