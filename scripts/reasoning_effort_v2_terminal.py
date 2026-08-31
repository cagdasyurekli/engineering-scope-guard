#!/usr/bin/env python3
"""Build or verify the provider-free Reasoning Effort v2 terminal package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from engineering_scope_guard.reasoning_effort_v2_terminal import (
    TerminalPackageError,
    build_terminal_package,
    verify_terminal_package,
    write_terminal_package,
)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TerminalPackageError(f"cannot read {label}: {path}") from error
    if not isinstance(value, dict):
        raise TerminalPackageError(f"{label} is not a JSON object")
    return value


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("command", choices=("build", "verify"))
    value.add_argument(
        "--terminal-path",
        required=True,
        choices=(
            "insufficient_population",
            "pre_subject_integrity_stop",
            "experiment_terminal",
        ),
    )
    value.add_argument("--qualification-receipt", type=Path, required=True)
    value.add_argument("--integrity-stop", type=Path)
    value.add_argument("--contract", type=Path)
    value.add_argument("--terminal-envelope", type=Path)
    value.add_argument("--analysis", type=Path)
    value.add_argument("--output-root", type=Path, default=Path("."))
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        qualification = _read_object(args.qualification_receipt, "qualification receipt")
        supplied = (args.contract, args.terminal_envelope, args.analysis)
        if args.terminal_path == "insufficient_population" and any(supplied):
            raise TerminalPackageError(
                "insufficient_population forbids --contract, --terminal-envelope, and --analysis"
            )
        if args.terminal_path == "experiment_terminal" and not all(supplied):
            raise TerminalPackageError(
                "experiment_terminal requires --contract, --terminal-envelope, and --analysis"
            )
        if args.terminal_path == "pre_subject_integrity_stop":
            if any(supplied) or args.integrity_stop is None:
                raise TerminalPackageError(
                    "pre_subject_integrity_stop requires --integrity-stop and forbids "
                    "--contract, --terminal-envelope, and --analysis"
                )
        elif args.integrity_stop is not None:
            raise TerminalPackageError(
                "--integrity-stop is valid only for pre_subject_integrity_stop"
            )
        contract = _read_object(args.contract, "contract") if args.contract else None
        envelope = (
            _read_object(args.terminal_envelope, "terminal envelope")
            if args.terminal_envelope
            else None
        )
        analysis = _read_object(args.analysis, "analysis") if args.analysis else None
        integrity_stop = (
            _read_object(args.integrity_stop, "integrity stop")
            if args.integrity_stop
            else None
        )
        package = build_terminal_package(
            terminal_path=args.terminal_path,
            qualification_receipt=qualification,
            contract=contract,
            terminal_envelope=envelope,
            analysis=analysis,
            integrity_stop=integrity_stop,
        )
        root = args.output_root.resolve()
        if args.command == "build":
            write_terminal_package(root, package)
        verify_terminal_package(root, package)
    except TerminalPackageError as error:
        print(f"reasoning_effort_v2_terminal: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "artifact_count": len(package),
                "command": args.command,
                "status": "verified",
                "terminal_path": args.terminal_path,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
