#!/usr/bin/env python3
"""Run the bounded, resolver-only dataset bridge qualification matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from engineering_scope_guard.pilot_contract import read_object
from engineering_scope_guard.pilot_runner import sha256_file
try:
    from scripts.pilot_runner import (
        DEFAULT_EVALUATOR_ROOT,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_runner import (  # type: ignore[no-redef]
        DEFAULT_EVALUATOR_ROOT,
        canonical_evaluator_python,
        resolve_dataset_task,
    )

INSTANCE_ID = "BYVoid__OpenCC-1096"
LANGUAGE = "cpp"


def _metadata_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _bridge_process(
    root: Path,
    python: Path,
    dataset_root: Path,
    *,
    pythonpath: str | None,
) -> dict[str, Any]:
    environment = os.environ.copy()
    if pythonpath is None:
        environment.pop("PYTHONPATH", None)
    else:
        environment["PYTHONPATH"] = pythonpath
    completed = subprocess.run(
        [
            str(python),
            str(root / "scripts/pilot_dataset_bridge.py"),
            "--dataset-root",
            str(dataset_root),
            "--language",
            LANGUAGE,
            "--instance-id",
            INSTANCE_ID,
            "resolve",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    value = json.loads(completed.stdout) if completed.returncode == 0 else None
    if "qualified evaluator Python lacks pyarrow" in completed.stderr:
        error_code = "missing_pyarrow"
    elif completed.returncode == 0:
        error_code = None
    else:
        error_code = "unclassified_stderr_sha256:" + hashlib.sha256(
            completed.stderr.encode()
        ).hexdigest()
    return {
        "exit_code": completed.returncode,
        "error_code": error_code,
        "metadata_sha256": _metadata_sha256(value) if value is not None else None,
    }


def _same_process_twice(
    root: Path, python: Path, dataset_root: Path
) -> dict[str, Any]:
    program = """
import json
import sys
from pathlib import Path
from scripts.pilot_dataset_bridge import resolve

args = (Path(sys.argv[1]), sys.argv[2], sys.argv[3])
first = resolve(*args)
second = resolve(*args)
print(json.dumps([first, second], sort_keys=True))
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [str(python), "-c", program, str(dataset_root), LANGUAGE, INSTANCE_ID],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {"exit_code": completed.returncode, "identical": False}
    values = json.loads(completed.stdout)
    return {
        "exit_code": 0,
        "identical": values[0] == values[1],
        "metadata_sha256": _metadata_sha256(values[0]),
        "resolutions": len(values),
    }


def _python_fingerprint(python: Path) -> dict[str, Any]:
    program = """
import importlib.util
import json
import sys

spec = importlib.util.find_spec("pyarrow")
version = None
if spec is not None:
    import pyarrow
    version = pyarrow.__version__
print(json.dumps({
    "python_version": sys.version.split()[0],
    "virtual_environment_active": sys.prefix != sys.base_prefix,
    "pyarrow_available": spec is not None,
    "pyarrow_version": version,
}, sort_keys=True))
"""
    completed = subprocess.run(
        [str(python), "-c", program], capture_output=True, text=True, check=True
    )
    return json.loads(completed.stdout)


def qualify(root: Path, evaluator_root: Path, dataset_root: Path) -> dict[str, Any]:
    host = read_object(root / "experiment/pilot_host_qualification.json")
    canonical_python = canonical_evaluator_python(evaluator_root)
    legacy_resolved_python = canonical_python.resolve(strict=True)
    dataset_files = sorted((dataset_root / "data").glob(f"{LANGUAGE}-*.parquet"))
    if len(dataset_files) != 1:
        raise RuntimeError(f"expected one pinned dataset split for {LANGUAGE}")
    dataset_file = dataset_files[0]
    dataset_file_sha256 = sha256_file(dataset_file)
    expected_dataset_sha256 = host["source"]["dataset_snapshot_files_sha256"].get(
        dataset_file.name
    )

    # This is the exact resolver function imported by the failed canary wrapper.
    canonical_fresh = resolve_dataset_task(
        root, canonical_python, dataset_root, LANGUAGE, INSTANCE_ID, "resolve"
    )
    same_process = _same_process_twice(root, canonical_python, dataset_root)
    canonical_after_success = resolve_dataset_task(
        root, canonical_python, dataset_root, LANGUAGE, INSTANCE_ID, "resolve"
    )
    successful_read_only = _bridge_process(
        root, canonical_python, dataset_root, pythonpath=None
    )
    failed_canary_path = _bridge_process(
        root, legacy_resolved_python, dataset_root, pythonpath="src"
    )

    expected_sha256 = _metadata_sha256(canonical_fresh)
    matrix = {
        "fresh_process_resolution": {
            "status": "pass",
            "metadata_sha256": expected_sha256,
        },
        "repeated_resolution_same_process": same_process,
        "fresh_process_after_prior_success": {
            "status": "pass",
            "metadata_sha256": _metadata_sha256(canonical_after_success),
        },
        "exact_failed_canary_interpreter_path": failed_canary_path,
        "exact_successful_read_only_lookup_path": successful_read_only,
    }
    passing_hashes = (
        matrix["fresh_process_resolution"]["metadata_sha256"],
        matrix["repeated_resolution_same_process"].get("metadata_sha256"),
        matrix["fresh_process_after_prior_success"]["metadata_sha256"],
        matrix["exact_successful_read_only_lookup_path"]["metadata_sha256"],
    )
    qualified = (
        all(value == expected_sha256 for value in passing_hashes)
        and same_process == {
            "exit_code": 0,
            "identical": True,
            "metadata_sha256": expected_sha256,
            "resolutions": 2,
        }
        and failed_canary_path["exit_code"] == 1
        and failed_canary_path["error_code"] == "missing_pyarrow"
        and successful_read_only["exit_code"] == 0
        and canonical_python != legacy_resolved_python
        and dataset_file_sha256 == expected_dataset_sha256
    )
    return {
        "schema_name": "engineering-scope-guard.dataset-bridge-qualification",
        "schema_version": 1,
        "status": "pass" if qualified else "fail",
        "task": {"instance_id": INSTANCE_ID, "language": LANGUAGE},
        "preserved_observations": {
            "failed_one_shot": {
                "command_shape": "PYTHONPATH=src <evaluator-venv-python> scripts/pilot_v2.py run-canary",
                "exit_code": 1,
                "visible_error": "dataset bridge failed for the exact task",
                "child_stderr_preserved_at_time": False,
            },
            "later_read_only_lookup": {
                "command_shape": "<evaluator-venv-python> scripts/pilot_dataset_bridge.py <pinned-local-dataset> cpp <exact-task> resolve",
                "exit_code": 0,
                "metadata_sha256": successful_read_only["metadata_sha256"],
            },
        },
        "environment_fingerprint": {
            "cwd": "repository-root",
            "dataset_revision": host["source"]["dataset_revision"],
            "dataset_file": dataset_file.name,
            "dataset_file_sha256": dataset_file_sha256,
            "dataset_access": "one pinned local parquet split via pyarrow; no network or Hugging Face cache API",
            "task_id_matching": "exact string equality; no normalization",
            "canonical_interpreter": {
                **_python_fingerprint(canonical_python),
                "path_is_symlink": canonical_python.is_symlink(),
            },
            "legacy_resolved_interpreter": {
                **_python_fingerprint(legacy_resolved_python),
                "same_path_as_canonical": legacy_resolved_python == canonical_python,
            },
            "failed_wrapper_pythonpath": "src",
            "successful_lookup_pythonpath": "unset",
        },
        "matrix": matrix,
        "root_cause": {
            "classification": "deterministic implementation defect",
            "explanation": (
                "The failed wrapper dereferenced .venv/bin/python with Path.resolve(). "
                "The resulting base interpreter did not activate the evaluator virtual "
                "environment and could not import pyarrow. The later lookup invoked the "
                "virtual-environment symlink directly and therefore succeeded."
            ),
            "cache_network_or_warm_state_required": False,
        },
        "repair": {
            "canonical_path_helper": "scripts.pilot_runner.canonical_evaluator_python",
            "symlinks_dereferenced": False,
            "canonical_resolver": "scripts.pilot_runner.resolve_dataset_task",
        },
        "prohibited_activity": {
            "codex_invocations": 0,
            "credential_copies": 0,
            "evaluator_invocations": 0,
            "live_canary_invocations": 0,
            "pilot_ledger_or_receipt_writes": 0,
            "pilot_v2_freezes": 0,
        },
        "decision": (
            "DATASET BRIDGE QUALIFIED — GO TO ONE FINAL LIVE CANARY"
            if qualified
            else "SWITCH BENCHMARK PATH"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--evaluator-root", type=Path, default=DEFAULT_EVALUATOR_ROOT)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("experiment/dataset_bridge_qualification.json")
    )
    args = parser.parse_args()
    root = args.root.resolve()
    evaluator_root = args.evaluator_root.resolve()
    host = read_object(root / "experiment/pilot_host_qualification.json")
    dataset_root = (
        args.dataset_root or Path(host["procedure"]["dataset_snapshot_path"])
    ).resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    result = qualify(root, evaluator_root, dataset_root)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "decision": result["decision"]}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
