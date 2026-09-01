#!/usr/bin/env python3
"""Run one of at most four contentless pinned-runtime diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engineering_scope_guard.runtime_soak import run_contentless_launch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--effort", choices=("low", "medium"), required=True)
    parser.add_argument("--repair-from-receipt", type=Path)
    parser.add_argument("--launch-contract", type=Path, required=True)
    args = parser.parse_args()
    predecessor = (
        json.loads(args.repair_from_receipt.read_text())
        if args.repair_from_receipt is not None else None
    )
    result = run_contentless_launch(
        json.loads(args.receipt.read_text()), state_path=args.state, effort=args.effort,
        repair_from_receipt=predecessor,
        launch_contract=json.loads(args.launch_contract.read_text()),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
