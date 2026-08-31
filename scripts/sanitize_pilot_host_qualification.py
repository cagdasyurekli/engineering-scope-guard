#!/usr/bin/env python3
"""Create or verify the public-safe Pilot host qualification receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


PUBLIC_RUN_FIELDS = frozenset(
    {
        "architecture_or_emulation_warnings",
        "classification",
        "command_log_sha256",
        "docker_limits",
        "exit_code",
        "official_image",
        "oom_or_resource_failure",
        "outcome",
        "repetition",
        "report_sha256",
        "requested_platform",
        "results_sha256",
        "timed_out",
        "timeout_seconds",
        "wall_seconds",
        "workers",
    }
)
REMOVED_RUN_FIELDS = (
    "command",
    "container_states_after_run",
    "raw_output_dir",
    "report",
    "resolved",
    "results",
)
LOCAL_REFERENCE_RE = re.compile(
    r"file://[^\s\"'<>]+|/Users/[^\s\"'<>]+|/private/tmp/[^\s\"'<>]+|"
    r"(?<![A-Za-z0-9_.-])\.local/[^\s\"'<>]+"
)
PUBLIC_MARKER = {
    "local_references_redacted": True,
    "raw_run_fields_removed": list(REMOVED_RUN_FIELDS),
    "scientific_outcomes_changed": False,
    "status": "public-safe-derived-receipt",
}


class SanitizationError(ValueError):
    """Raised when the receipt cannot be sanitized deterministically."""


def _sanitize_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_strings(child)
            for key, child in value.items()
            if key != "raw_output_dir"
        }
    if isinstance(value, list):
        return [_sanitize_strings(child) for child in value]
    if isinstance(value, str):
        return LOCAL_REFERENCE_RE.sub("<redacted-local-reference>", value)
    return value


def sanitize(value: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic public projection of a completed receipt."""

    if value.get("status") != "complete" or not isinstance(value.get("tasks"), list):
        raise SanitizationError("only a completed host qualification can be sanitized")
    sanitized = _sanitize_strings(value)
    for task in sanitized["tasks"]:
        runs = task.get("runs")
        if not isinstance(runs, list):
            raise SanitizationError("task runs are malformed")
        task["runs"] = [
            {key: run[key] for key in run if key in PUBLIC_RUN_FIELDS}
            for run in runs
        ]
    sanitized["public_sanitization"] = PUBLIC_MARKER
    return sanitized


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def sanitized_bytes(path: Path) -> bytes:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SanitizationError(f"cannot read receipt: {path}") from error
    if not isinstance(value, dict):
        raise SanitizationError("receipt must be a JSON object")
    result = canonical_bytes(sanitize(value))
    lowered = result.lower()
    for forbidden in (b"/users/", b"file://", b"/.codex/", b"/.local/"):
        if forbidden in lowered:
            raise SanitizationError("public receipt still contains a local reference")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("write", "verify"))
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = sanitized_bytes(args.receipt)
    if args.command == "write":
        args.receipt.write_bytes(result)
    elif args.receipt.read_bytes() != result:
        raise SanitizationError("receipt is not the canonical public-safe projection")
    print(json.dumps({"status": "verified", "receipt": args.receipt.as_posix()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
