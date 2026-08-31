#!/usr/bin/env python3
"""Generate a sanitized, read-only preview of the preserved Pilot partial attempt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_partial_recovery import build_partial_recovery_preview


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--contract", type=Path, default=Path("experiment/pilot_execution_contract.json")
    )
    parser.add_argument(
        "--authorization",
        type=Path,
        default=Path("experiment/pilot_successor_batch_authorization.json"),
    )
    parser.add_argument(
        "--integrity",
        type=Path,
        default=Path("experiment/pilot_execution_integrity_qualification.json"),
    )
    parser.add_argument(
        "--predecessor-ledger",
        type=Path,
        default=Path(".local/pilot-runner/pilot-ledger.jsonl"),
    )
    parser.add_argument(
        "--successor-ledger",
        type=Path,
        default=Path(".local/pilot-successor-runner/pilot-successor-ledger.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    try:
        preview = build_partial_recovery_preview(
            root,
            _path(root, args.contract),
            _path(root, args.authorization),
            _path(root, args.integrity),
            _path(root, args.predecessor_ledger),
            _path(root, args.successor_ledger),
        )
        rendered = json.dumps(preview, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            output = _path(root, args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".tmp")
            temporary.write_text(rendered, encoding="utf-8")
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            temporary.replace(output)
        print(rendered, end="")
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_partial_recovery: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
