#!/usr/bin/env python3
"""Operate the pinned Azure Batch evaluator pool and one prediction task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engineering_scope_guard.azure_evaluator import (
    cleanup,
    evaluate,
    failure_receipt,
    occupancy,
    prepare_pool,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prepare", "evaluate", "occupancy", "cleanup")
    )
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_pool(args.state_root)
    elif args.command == "cleanup":
        result = cleanup(args.state_root)
    elif args.command == "occupancy":
        result = occupancy(args.state_root)
    else:
        if args.worker is None or args.request is None:
            raise ValueError("evaluate requires --worker and --request")
        request = json.loads(args.request.read_text())
        try:
            result = evaluate(
                state_root=args.state_root,
                worker_path=args.worker,
                job_id=request["job_id"],
                task_id=request["azure_task_id"],
                task=request["task"],
                patch=Path(request["patch_path"]).read_bytes(),
                evaluator_timeout_seconds=request["evaluator_timeout_seconds"],
            )
        except Exception as error:
            result = failure_receipt(
                state_root=args.state_root,
                job_id=request["job_id"],
                task_id=request["azure_task_id"],
                error=error,
            )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"ready", "pass"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
