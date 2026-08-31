#!/usr/bin/env python3
"""Build or validate the frozen exploratory allocation from pinned metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from engineering_scope_guard.exploratory_design import canonical_bytes
from engineering_scope_guard.exploratory_freeze import (
    ARTIFACT_PATH,
    build_freeze,
    dataset_hashes,
    load_freeze,
)
from engineering_scope_guard.pilot_v3 import SELECTION_FIELDS


def load_rows(dataset_root: Path) -> list[dict[str, Any]]:
    """Load only the frozen metadata projection from the pinned Parquet files."""

    try:
        import pyarrow.parquet as parquet
    except ImportError as error:  # pragma: no cover
        raise RuntimeError("exploratory freeze requires the pinned evaluator pyarrow") from error
    columns = sorted(SELECTION_FIELDS - {"language"})
    rows: list[dict[str, Any]] = []
    for path in sorted((dataset_root / "data").glob("*.parquet")):
        language = path.name.split("-", 1)[0]
        for row in parquet.read_table(path, columns=columns).to_pylist():
            row["language"] = language
            rows.append(row)
    return rows


def verify_container_manifests(artifact: dict[str, Any]) -> None:
    """Bind the selected official registry manifests without pulling or running them."""

    for selected in artifact["selection"]["selected"]:
        completed = subprocess.run(
            ["docker", "manifest", "inspect", selected["container_image_identity"]],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("a selected official container manifest is unavailable")
        try:
            manifest = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("a selected official container manifest is malformed") from error
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        selected["container_registry_manifest_available"] = True
        selected["container_registry_manifest_sha256"] = hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-container-manifests", action="store_true")
    args = parser.parse_args()
    rows = load_rows(args.dataset_root)
    hashes = dataset_hashes(args.dataset_root)
    artifact_path = args.root / ARTIFACT_PATH
    if args.write:
        artifact = build_freeze(args.root, rows, hashes)
        if not args.verify_container_manifests:
            parser.error("--write requires --verify-container-manifests")
        verify_container_manifests(artifact)
        artifact_path.write_bytes(canonical_bytes(artifact))
    else:
        artifact = load_freeze(artifact_path, args.root, rows, hashes)
        if args.verify_container_manifests:
            observed = build_freeze(args.root, rows, hashes)
            verify_container_manifests(observed)
            expected_hashes = [
                item["container_registry_manifest_sha256"]
                for item in artifact["selection"]["selected"]
            ]
            observed_hashes = [
                item["container_registry_manifest_sha256"]
                for item in observed["selection"]["selected"]
            ]
            if observed_hashes != expected_hashes:
                raise RuntimeError("a selected official container manifest changed")
    print(json.dumps({
        "status": "pass",
        "selected_tasks": artifact["selection"]["selected_task_count"],
        "selected_repositories": artifact["selection"]["selected_repository_count"],
        "remaining_tasks": artifact["confirmatory_reserve"]["remaining_task_count"],
        "remaining_repositories": artifact["confirmatory_reserve"]["remaining_repository_count"],
        "blocks": artifact["schedule"]["block_count"],
        "cells": artifact["schedule"]["cell_count"],
        "experimental_subject_calls": 0,
        "experimental_evaluator_calls": 0,
        "experimental_observations": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
