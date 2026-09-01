#!/usr/bin/env python3
"""Create or verify private treatment-clean Codex launch profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from engineering_scope_guard.launch_surface import (
    build_launch_profile,
    canonical_bytes,
    validate_launch_contract,
    validate_treatment_pair,
)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _private_write(path: Path, value: dict[str, Any]) -> None:
    if ".local" not in path.parts:
        raise ValueError("launch contract must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    payload = canonical_bytes(value)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def build_contract(binary: Path) -> dict[str, Any]:
    executable = binary.resolve(strict=True)
    help_result = subprocess.run(
        [str(executable), "exec", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if help_result.returncode != 0:
        raise ValueError("Codex exec help is unavailable")
    profiles = {
        effort: build_launch_profile(
            executable=executable,
            model="gpt-5.6-sol",
            reasoning_effort=effort,
        )
        for effort in ("low", "medium")
    }
    treatment_diff = validate_treatment_pair(
        profiles["low"], profiles["medium"], exec_help=help_result.stdout
    )
    body = {
        "schema_name": "engineering-scope-guard.launch-surface-contract",
        "schema_version": 1,
        "profiles": profiles,
        "profile_sha256s": {
            effort: _digest(profile) for effort, profile in profiles.items()
        },
        "treatment_diff": treatment_diff,
        "treatment_diff_sha256": _digest(treatment_diff),
        "shell": False,
        "diagnostic_launch_cap": 4,
    }
    body["contract_sha256"] = _digest(body)
    return body


def validate_contract(contract: dict[str, Any], binary: Path) -> None:
    help_result = subprocess.run(
        [str(binary.resolve(strict=True)), "exec", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if help_result.returncode != 0:
        raise ValueError("Codex exec help is unavailable")
    validate_launch_contract(contract, exec_help=help_result.stdout)
    if any(
        profile["executable"] != str(binary.resolve(strict=True))
        for profile in contract["profiles"].values()
    ):
        raise ValueError("launch-surface contract differs from current observation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "check"))
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "create":
        contract = build_contract(args.binary)
        _private_write(args.output, contract)
        status = "created"
    else:
        contract = json.loads(args.output.read_text())
        validate_contract(contract, args.binary)
        status = "pass"
    print(
        json.dumps(
            {
                "status": status,
                "contract_sha256": contract["contract_sha256"],
                "profile_sha256s": contract["profile_sha256s"],
                "treatment_only": contract["treatment_diff"]["treatment_only"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
