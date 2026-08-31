#!/usr/bin/env python3
"""Validate and print the body-free Pilot-v3 successor terminal result."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_v3_analysis import build_terminal_result, canonical_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(".local/pilot-v3-successor/pilot-v3-successor-ledger.jsonl"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    ledger = args.ledger if args.ledger.is_absolute() else root / args.ledger
    try:
        result = build_terminal_result(root, ledger)
    except (ExperimentConfigurationError, OSError, ValueError) as error:
        print(f"pilot_v3_analysis: {error}", file=sys.stderr)
        return 1
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
