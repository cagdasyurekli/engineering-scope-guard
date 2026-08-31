#!/usr/bin/env python3
"""Inspect experiment disk headroom or emit a non-destructive cleanup plan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from engineering_scope_guard.disk_safety import (
    DiskSafetyError,
    cleanup_plan,
    disk_safety_snapshot,
    public_disk_safety_receipt,
    render_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "plan-cleanup"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--evidence-root", type=Path, default=Path(".local"))
    args = parser.parse_args()
    root = args.root.resolve()
    evidence_root = args.evidence_root if args.evidence_root.is_absolute() else root / args.evidence_root
    try:
        if args.command == "plan-cleanup":
            result = cleanup_plan(evidence_root)
            output = evidence_root / "disk-cleanup-plan.json"
            public_result = {
                "schema_name": "engineering-scope-guard.experiment-disk-cleanup-public",
                "schema_version": 1,
                "status": "plan_written",
                "private_plan_written": True,
                "deletion_authorized": False,
                "dynamic_host_metadata_withheld": True,
            }
        else:
            result = disk_safety_snapshot(evidence_root, filesystem_path=evidence_root)
            output = evidence_root / "disk-safety-check.json"
            public_result = public_disk_safety_receipt(result)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(render_json(result), encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(output)
    except (DiskSafetyError, OSError) as error:
        print(f"experiment_disk_safety: {error}", file=sys.stderr)
        return 2
    print(json.dumps(public_result, sort_keys=True) + "\n", end="")
    return 0 if result.get("status", "pass") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
