#!/usr/bin/env python3
"""Record or verify a provider-free Reasoning Effort v2 pre-freeze stop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.reasoning_effort_v2_pre_freeze_terminal import (
    read_and_validate_pre_freeze_terminal_receipt,
    terminalize_pre_freeze_runtime_mismatch,
)
try:
    from scripts import evaluator_stable_qualification as qualifier_live
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    import evaluator_stable_qualification as qualifier_live


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("terminalize", "verify"))
    parser.add_argument("--qualification-receipt", type=Path, required=True)
    parser.add_argument("--execution-root", type=Path, required=True)
    parser.add_argument("--codex-binary", type=Path)
    parser.add_argument("--model-catalog", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        if arguments.command == "terminalize":
            if arguments.codex_binary is None or arguments.model_catalog is None:
                raise ExperimentConfigurationError(
                    "terminalize requires --codex-binary and --model-catalog"
                )
            receipt = terminalize_pre_freeze_runtime_mismatch(
                qualification_receipt_path=arguments.qualification_receipt,
                execution_root=arguments.execution_root,
                codex_binary=arguments.codex_binary,
                model_catalog=arguments.model_catalog,
                runtime_observer=qualifier_live._codex_runtime,
            )
        else:
            receipt = read_and_validate_pre_freeze_terminal_receipt(
                qualification_receipt_path=arguments.qualification_receipt,
                execution_root=arguments.execution_root,
            )
    except (ExperimentConfigurationError, OSError) as error:
        print(f"reasoning_effort_v2_pre_freeze_terminal: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "classification": receipt["classification"],
                "subject_invocation_starts": receipt["subject_invocation_starts"],
                "receipt_sha256": receipt["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
