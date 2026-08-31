#!/usr/bin/env python3
"""Read only the pinned SWE-bench-Live dataset fields required by the runner.

Run this script with the already-qualified evaluator Python environment. The
``resolve`` command emits identifiers and digests only; task text is written
only into a trajectory-local file by ``prompt``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


class DatasetBridgeError(RuntimeError):
    """Raised when a frozen task cannot be resolved exactly once."""


def _rows(dataset_root: Path, language: str) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as error:  # pragma: no cover - evaluator environment owns this
        raise DatasetBridgeError("qualified evaluator Python lacks pyarrow") from error
    paths = sorted((dataset_root / "data").glob(f"{language}-*.parquet"))
    if len(paths) != 1:
        raise DatasetBridgeError(f"expected one pinned dataset split for {language}")
    return parquet.read_table(
        paths[0],
        columns=["instance_id", "repo", "base_commit", "problem_statement", "docker_image"],
    ).to_pylist()


def _resolve(dataset_root: Path, language: str, instance_id: str) -> dict[str, Any]:
    matches = [row for row in _rows(dataset_root, language) if row["instance_id"] == instance_id]
    if len(matches) != 1:
        raise DatasetBridgeError(f"expected one dataset row for {instance_id}")
    row = matches[0]
    required = ("repo", "base_commit", "problem_statement", "docker_image")
    if any(not isinstance(row.get(name), str) or not row[name] for name in required):
        raise DatasetBridgeError(f"dataset row is incomplete for {instance_id}")
    return row


def resolve(dataset_root: Path, language: str, instance_id: str) -> dict[str, Any]:
    row = _resolve(dataset_root, language, instance_id)
    return {
        "instance_id": instance_id,
        "language": language,
        "repo": row["repo"],
        "base_commit": row["base_commit"],
        "docker_image": row["docker_image"],
        "problem_statement_sha256": hashlib.sha256(
            row["problem_statement"].encode("utf-8")
        ).hexdigest(),
    }


def write_prompt(
    dataset_root: Path, language: str, instance_id: str, output: Path
) -> dict[str, Any]:
    row = _resolve(dataset_root, language, instance_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(row["problem_statement"])
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "instance_id": instance_id,
        "prompt_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "prompt_bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--instance-id", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("resolve")
    prompt = subparsers.add_parser("prompt")
    prompt.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            resolve(args.dataset_root, args.language, args.instance_id)
            if args.command == "resolve"
            else write_prompt(args.dataset_root, args.language, args.instance_id, args.output)
        )
    except (DatasetBridgeError, OSError, ValueError) as error:
        print(f"pilot_dataset_bridge: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
