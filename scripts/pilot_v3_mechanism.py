#!/usr/bin/env python3
"""Build the body-safe Pilot-v3 C-short mechanism diagnostic."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_v3_analysis import (
    build_mechanism_diagnostic,
    canonical_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(".local/pilot-v3-successor/pilot-v3-successor-ledger.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    ledger = args.ledger if args.ledger.is_absolute() else root / args.ledger
    try:
        result = build_mechanism_diagnostic(root, ledger)
        rendered = canonical_json(result)
        if args.output is None:
            print(rendered, end="")
        else:
            output = args.output if args.output.is_absolute() else root / args.output
            output.write_text(rendered, encoding="utf-8")
    except (ExperimentConfigurationError, OSError, ValueError) as error:
        print(f"pilot_v3_mechanism: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
