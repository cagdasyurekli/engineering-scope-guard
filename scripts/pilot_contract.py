#!/usr/bin/env python3
"""Build or audit the frozen Pilot contract without executing Pilot cells."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import build_contract, read_object, validate_contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "audit"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--contract", type=Path, default=Path("experiment/pilot_execution_contract.json"))
    parser.add_argument("--write", action="store_true", help="write a newly built contract")
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_contract(args.root.resolve())
            if args.write:
                if args.contract.exists():
                    raise ExperimentConfigurationError(
                        f"refusing to overwrite existing contract: {args.contract}"
                    )
                args.contract.parent.mkdir(parents=True, exist_ok=True)
                args.contract.write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
        else:
            result = read_object(args.contract)
            validate_contract(result, args.root.resolve())
    except (ExperimentConfigurationError, OSError, ValueError) as error:
        print(f"pilot_contract: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
