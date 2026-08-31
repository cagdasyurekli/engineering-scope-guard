#!/usr/bin/env python3
"""Run the frozen terminal exploratory analysis in its predeclared order."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engineering_scope_guard.evidence_conditioned_analysis import analyze
from engineering_scope_guard.evidence_conditioned_execution import CONTRACT_PATH
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.exploratory_design import canonical_bytes


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected object in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(".local/evidence-conditioned-execution/execution-ledger.jsonl"),
    )
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    ledger = args.ledger if args.ledger.is_absolute() else root / args.ledger
    annotations = (
        args.annotations if args.annotations.is_absolute() else root / args.annotations
    )
    try:
        result = analyze(
            root,
            _read(root / CONTRACT_PATH),
            ledger,
            _read(annotations),
        )
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"evidence_conditioned_analysis: {error}", file=sys.stderr)
        return 1
    encoded = canonical_bytes(result)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(encoded)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
