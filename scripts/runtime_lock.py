#!/usr/bin/env python3
"""Create or check one private experiment-local runtime receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engineering_scope_guard.runtime_lock import (
    build_runtime_receipt,
    sentinel,
    validate_runtime_receipt,
    write_private_receipt,
)
from engineering_scope_guard.launch_surface import build_launch_profile


COMMAND_TEMPLATE = [
    'model_reasoning_effort="<EFFORT>"'
    if item == 'model_reasoning_effort="low"' else item
    for item in build_launch_profile(
        executable="<CODEX_BINARY>", model="gpt-5.6-sol", reasoning_effort="low"
    )["argv"]
]
TOOL_SURFACE = {
    "external_tools": "disabled",
    "network_access": False,
    "web_search": "disabled",
    "apps": False,
    "plugins": False,
    "browser": False,
    "computer_use": False,
    "image_generation": False,
    "multi_agent": False,
    "skill_search": False,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "check"))
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--model-catalog", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "create":
        receipt = build_runtime_receipt(
            codex_binary=args.binary,
            model_catalog=args.model_catalog,
            model="gpt-5.6-sol",
            command_template=COMMAND_TEMPLATE,
            tool_surface=TOOL_SURFACE,
            sandbox="workspace-write",
        )
        write_private_receipt(args.receipt, receipt)
        result = {"status": "created", "runtime_receipt_sha256": receipt["receipt_sha256"]}
    else:
        receipt = json.loads(args.receipt.read_text())
        validate_runtime_receipt(receipt)
        result = sentinel(receipt)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
