#!/usr/bin/env python3
"""Authorize, qualify, or later execute the single Pilot successor batch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import (
    canonical_bytes,
    read_ledger,
    read_object,
    validate_contract,
)
from engineering_scope_guard.pilot_runner import (
    append_runner_event,
    build_launch_request,
    execute_attempt,
    sha256_file,
)
from engineering_scope_guard.pilot_successor import (
    SUCCESSOR_LEDGER_NAME,
    build_successor_authorization,
    initialize_successor_ledger,
    next_successor_legal_action,
    predecessor_file_identity,
    read_authorization,
    successor_dry_run_receipt,
    validate_successor_start,
)
try:
    from scripts.pilot_runner import (
        DEFAULT_EVALUATOR_ROOT,
        DEFAULT_SOURCE_CODEX_HOME,
        LiveBackend,
        _now,
        _write_json,
        resolve_tasks,
        runner_lock,
        strict_preflight,
    )
except ModuleNotFoundError:  # Direct ``python scripts/pilot_successor_batch.py`` execution.
    from pilot_runner import (
        DEFAULT_EVALUATOR_ROOT,
        DEFAULT_SOURCE_CODEX_HOME,
        LiveBackend,
        _now,
        _write_json,
        resolve_tasks,
        runner_lock,
        strict_preflight,
    )

DEFAULT_PREDECESSOR = Path(".local/pilot-runner/pilot-ledger.jsonl")
DEFAULT_SUCCESSOR_STATE = Path(".local/pilot-successor-runner")
DEFAULT_AUTHORIZATION = Path("experiment/pilot_successor_batch_authorization.json")
DEFAULT_QUALIFICATION = Path("experiment/pilot_successor_batch_qualification.json")
DEFAULT_INTEGRITY = Path("experiment/pilot_execution_integrity_qualification.json")
EXECUTION_CONFIRMATION_PREFIX = "execute-successor-pilot-v1.0:"


def execution_confirmation(authorization: dict[str, Any]) -> str:
    return EXECUTION_CONFIRMATION_PREFIX + authorization["authorization_sha256"]


def execute_successor_batch(
    contract: dict[str, Any],
    authorization: dict[str, Any],
    integrity: dict[str, Any],
    predecessor_path: Path,
    backend: LiveBackend,
    state_root: Path,
    confirmation: str,
) -> dict[str, Any]:
    """Execute only after a separately supplied digest-bound authorization token."""

    if confirmation != execution_confirmation(authorization):
        raise ExperimentConfigurationError("successor execute confirmation is absent or wrong")
    ledger_path = state_root / SUCCESSOR_LEDGER_NAME
    validate_successor_start(
        contract, predecessor_path, integrity, authorization, ledger_path
    )
    marker = state_root / "REAL_SUCCESSOR_EXECUTE_INVOKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_now() + "\n", encoding="utf-8")
    with runner_lock(state_root):
        events = initialize_successor_ledger(contract, authorization, ledger_path)
        while True:
            action = next_successor_legal_action(contract, authorization, events)
            kind = action["action"]
            if kind == "complete":
                return {"status": "complete", "cells": len(contract["schedule"]["cells"])}
            if kind == "batch_stopped":
                return {"status": "batch_stopped", "payload": action["payload"]}
            if kind == "resolve_partial":
                raise ExperimentConfigurationError(
                    "successor partial attempt requires a new explicit authorization decision"
                )
            if kind == "record_batch_stop":
                receipt = action["receipt"]
                append_runner_event(
                    ledger_path,
                    "batch_stopped",
                    {"cell_id": receipt["cell_id"], "termination": receipt["termination"]},
                )
            elif kind == "authorize_infrastructure_rerun":
                append_runner_event(
                    ledger_path,
                    "infrastructure_rerun_authorized",
                    {"cell_id": action["receipt"]["cell_id"], **action["state"]},
                )
            elif kind == "record_rerun_budget_stop":
                receipt = action["receipt"]
                append_runner_event(
                    ledger_path,
                    "batch_stopped",
                    {
                        "cell_id": receipt["cell_id"],
                        "termination": receipt["termination"],
                        "reason": "trajectory_infrastructure_rerun_budget_exhausted",
                        "reruns_consumed": action["consumed"],
                    },
                )
            elif kind == "launch":
                request = build_launch_request(
                    contract, action["cell"], state_root, action["trajectory_attempt"]
                )
                request["attempt_started_at"] = _now()
                append_runner_event(ledger_path, "attempt_started", request)
                try:
                    receipt = execute_attempt(contract, request, backend)
                except (ExperimentConfigurationError, OSError, ValueError):
                    receipt = {
                        **request,
                        "started_at": request["attempt_started_at"],
                        "ended_at": _now(),
                        "termination": "harness_failure",
                        "evaluator_result": {"resolved": None},
                        "usage": {},
                        "usage_complete": False,
                        "admissible_under_contract": False,
                        "deviations": [{"class": "runner_process_boundary_failure"}],
                    }
                append_runner_event(ledger_path, "attempt_finished", receipt)
            else:
                raise ExperimentConfigurationError(f"unsupported successor action: {kind}")
            events = read_ledger(ledger_path)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--contract", type=Path, default=Path("experiment/pilot_execution_contract.json")
    )
    parser.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument("--integrity", type=Path, default=DEFAULT_INTEGRITY)
    parser.add_argument("--predecessor-ledger", type=Path, default=DEFAULT_PREDECESSOR)
    parser.add_argument("--successor-state-root", type=Path, default=DEFAULT_SUCCESSOR_STATE)
    parser.add_argument("--evaluator-root", type=Path, default=DEFAULT_EVALUATOR_ROOT)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument(
        "--credential-source-codex-home", type=Path, default=DEFAULT_SOURCE_CODEX_HOME
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("authorize")
    qualify = commands.add_parser("qualify")
    qualify.add_argument("--output", type=Path, default=DEFAULT_QUALIFICATION)
    execute = commands.add_parser("execute")
    execute.add_argument("--confirm", required=True)
    return parser.parse_args()


def _path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    contract_path = _path(root, args.contract)
    authorization_path = _path(root, args.authorization)
    integrity_path = _path(root, args.integrity)
    predecessor_path = _path(root, args.predecessor_ledger)
    successor_state = _path(root, args.successor_state_root)
    try:
        contract = read_object(contract_path)
        validate_contract(contract, root)
        integrity = read_object(integrity_path)
        predecessor_before = predecessor_file_identity(predecessor_path)
        if args.command == "authorize":
            authorization = build_successor_authorization(
                contract, read_ledger(predecessor_path), integrity
            )
            if authorization_path.exists():
                if canonical_bytes(read_authorization(authorization_path)) != canonical_bytes(
                    authorization
                ):
                    raise ExperimentConfigurationError(
                        "immutable successor authorization already exists with different bytes"
                    )
            else:
                _write_json(authorization_path, authorization)
            result = authorization
        else:
            authorization = read_authorization(authorization_path)
            validate_successor_start(
                contract,
                predecessor_path,
                integrity,
                authorization,
                successor_state / SUCCESSOR_LEDGER_NAME,
            )
            host = read_object(root / "experiment/pilot_host_qualification.json")
            evaluator_root = args.evaluator_root.resolve()
            dataset_root = (
                args.dataset_root or Path(host["procedure"]["dataset_snapshot_path"])
            ).resolve()
            evaluator_python = Path(
                os.path.abspath(args.evaluator_python or evaluator_root / ".venv/bin/python")
            )
            source_codex_home = args.credential_source_codex_home.resolve()
            preflight = strict_preflight(
                root,
                contract,
                evaluator_root,
                dataset_root,
                evaluator_python,
                args.codex_binary,
                successor_state,
                source_codex_home,
            )
            tasks = resolve_tasks(root, contract, evaluator_python, dataset_root)
            backend = LiveBackend(
                root,
                contract,
                tasks,
                evaluator_root,
                dataset_root,
                evaluator_python,
                args.codex_binary,
                source_codex_home,
            )
            if args.command == "qualify":
                dry_run = successor_dry_run_receipt(
                    contract,
                    root,
                    predecessor_path,
                    integrity,
                    authorization,
                    successor_state,
                    tasks,
                )
                predecessor_after = predecessor_file_identity(predecessor_path)
                result = {
                    "schema_name": "engineering-scope-guard.pilot-successor-batch-qualification",
                    "schema_version": 1,
                    "status": "pass",
                    "decision": "SUCCESSOR-BATCH QUALIFIED — GO TO EXECUTE SUCCESSOR PILOT",
                    "authorization_sha256": authorization["authorization_sha256"],
                    "strict_preflight": preflight,
                    "dry_run": dry_run,
                    "predecessor_before": predecessor_before,
                    "predecessor_after": predecessor_after,
                    "predecessor_unchanged": predecessor_before == predecessor_after,
                    "frozen_contract_file_sha256": preflight["contract_file_sha256"],
                    "audited_source_sha256": {
                        path: sha256_file(root / path)
                        for path in (
                            "src/engineering_scope_guard/pilot_runner.py",
                            "src/engineering_scope_guard/pilot_successor.py",
                            "scripts/pilot_runner.py",
                            "scripts/pilot_successor_batch.py",
                        )
                    },
                    "experimental_activity": {
                        "pilot_subject_invocations": 0,
                        "pilot_evaluator_invocations": 0,
                        "policy_comparisons": 0,
                        "experimental_observations_written": 0,
                    },
                    "reused_integrity_evidence": True,
                    "authenticated_non_pilot_canary_runs": 0,
                }
                _write_json(_path(root, args.output), result)
            else:
                result = execute_successor_batch(
                    contract,
                    authorization,
                    integrity,
                    predecessor_path,
                    backend,
                    successor_state,
                    args.confirm,
                )
        if predecessor_file_identity(predecessor_path) != predecessor_before:
            raise ExperimentConfigurationError("predecessor ledger changed")
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_successor_batch: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
