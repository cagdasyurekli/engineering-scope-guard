#!/usr/bin/env python3
"""Read and persist a private, sanitized Codex subject-quota readiness receipt."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
from typing import Any

from engineering_scope_guard.pilot_contract import canonical_bytes, digest


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_rate_limits(binary: Path, *, timeout_seconds: float = 15) -> dict[str, Any]:
    """Use the pinned app-server protocol without starting a Codex turn."""

    executable = binary.resolve(strict=True)
    process = subprocess.Popen(
        [str(executable), "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    requests = (
        {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "esg-subject-quota-gate", "version": "1"},
                "capabilities": {},
            },
        },
        {"method": "initialized", "params": {}},
        {"id": 2, "method": "account/rateLimits/read"},
    )
    process.stdin.write(
        b"".join(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
            for value in requests
        )
    )
    process.stdin.flush()
    deadline = time.monotonic() + timeout_seconds
    response: dict[str, Any] | None = None
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 1)
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("id") == 2:
                response = value
                break
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)
    _require(response is not None and "result" in response, "rate-limit response is absent")
    result = response["result"]
    _require(isinstance(result, dict), "rate-limit result is malformed")
    return result


def build_receipt(binary: Path, response: dict[str, Any]) -> dict[str, Any]:
    """Project only non-secret capacity facts and make the gate fail closed."""

    executable = binary.resolve(strict=True)
    by_id = response.get("rateLimitsByLimitId")
    rate_limits = by_id.get("codex") if isinstance(by_id, dict) else None
    if not isinstance(rate_limits, dict):
        rate_limits = response.get("rateLimits")
    _require(isinstance(rate_limits, dict), "Codex rate-limit bucket is absent")
    primary = rate_limits.get("primary")
    _require(isinstance(primary, dict), "Codex primary rate-limit window is absent")
    used_percent = primary.get("usedPercent")
    _require(
        isinstance(used_percent, int)
        and not isinstance(used_percent, bool)
        and 0 <= used_percent <= 100,
        "Codex used percentage is malformed",
    )
    operational_headroom_percent = 100 - used_percent
    status = (
        "pass"
        if rate_limits.get("rateLimitReachedType") is None
        and rate_limits.get("spendControlReached") is not True
        and operational_headroom_percent >= 75
        else "fail"
    )
    body = {
        "schema_name": "engineering-scope-guard.launch-surface-subject-quota-gate",
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "codex_binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "limit_id": rate_limits.get("limitId"),
        "plan_type": rate_limits.get("planType"),
        "primary_used_percent": used_percent,
        "operational_headroom_percent": operational_headroom_percent,
        "window_duration_minutes": primary.get("windowDurationMins"),
        "window_resets_at": primary.get("resetsAt"),
        "rate_limit_reached_type": rate_limits.get("rateLimitReachedType"),
        "spend_control_reached": rate_limits.get("spendControlReached"),
        "minimum_operational_headroom_percent": 75,
        "planned_subject_cells": 40,
        "maximum_subject_attempts": 48,
        "capacity_semantics": (
            "the API exposes percentage headroom, not a guaranteed number of coding-task starts"
        ),
        "status": status,
    }
    return {**body, "quota_gate_sha256": digest(body)}


def write_private(path: Path, receipt: dict[str, Any]) -> None:
    _require(".local" in path.parts, "quota receipt must remain below .local")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        handle.write(canonical_bytes(receipt))
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(args.binary, read_rate_limits(args.binary))
    write_private(args.output, receipt)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "operational_headroom_percent": receipt[
                    "operational_headroom_percent"
                ],
                "quota_gate_sha256": receipt["quota_gate_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
