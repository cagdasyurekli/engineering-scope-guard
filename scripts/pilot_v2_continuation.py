#!/usr/bin/env python3
"""Freeze or audit the unstarted Pilot-v2 operator-interruption continuation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_contract import (
    BATCH_STOP_FAILURES,
    RERUNNABLE_INFRASTRUCTURE,
    canonical_bytes,
    read_object,
)
from engineering_scope_guard.pilot_runner import (
    build_launch_request,
    execute_attempt,
)
from engineering_scope_guard.pilot_v2 import validate_contract as validate_v2_contract
from engineering_scope_guard.pilot_v2_continuation import (
    CONTINUATION_LEDGER_NAME,
    append_continuation_event,
    build_authorization,
    build_qualification,
    continuation_dry_run_receipt,
    continuation_execution_confirmation,
    initialize_continuation_ledger,
    next_continuation_legal_action,
    read_authorization,
    read_continuation_ledger,
    strict_continuation_preflight,
    validate_authorization,
)
try:
    from scripts.pilot_runner import (
        DEFAULT_EVALUATOR_ROOT,
        DEFAULT_SOURCE_CODEX_HOME,
        LiveBackend,
        _now,
        canonical_evaluator_python,
        resolve_tasks,
        runner_lock,
        strict_preflight,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_runner import (  # type: ignore[no-redef]
        DEFAULT_EVALUATOR_ROOT,
        DEFAULT_SOURCE_CODEX_HOME,
        LiveBackend,
        _now,
        canonical_evaluator_python,
        resolve_tasks,
        runner_lock,
        strict_preflight,
    )


def _path(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def execute_continuation_batch(
    contract: dict[str, Any],
    authorization: dict[str, Any],
    backend: LiveBackend,
    state_root: Path,
    ledger_path: Path,
    confirmation: str,
    resolve_partial_as: str | None,
) -> dict[str, Any]:
    """Execute only durable continuation actions after separate confirmation."""

    if confirmation != continuation_execution_confirmation(authorization):
        raise ExperimentConfigurationError(
            "live continuation confirmation digest is absent or wrong"
        )
    marker = state_root / "REAL_CONTINUATION_EXECUTE_INVOKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_now() + "\n", encoding="utf-8")
    with runner_lock(state_root):
        while True:
            events = read_continuation_ledger(authorization, ledger_path)
            action = next_continuation_legal_action(contract, authorization, events)
            kind = action["action"]
            if kind == "complete":
                return {"status": "complete", "continuation_cells": 38}
            if kind == "batch_stopped":
                return {"status": "batch_stopped", "payload": action["payload"]}
            if kind == "resolve_partial":
                if resolve_partial_as is None:
                    raise ExperimentConfigurationError(
                        "partial continuation attempt requires explicit frozen classification"
                    )
                if resolve_partial_as not in RERUNNABLE_INFRASTRUCTURE | BATCH_STOP_FAILURES:
                    raise ExperimentConfigurationError(
                        "partial continuation classification is outside frozen taxonomy"
                    )
                request = action["request"]
                append_continuation_event(
                    ledger_path,
                    "attempt_finished",
                    {
                        **request,
                        "started_at": request.get("attempt_started_at", _now()),
                        "ended_at": _now(),
                        "termination": resolve_partial_as,
                        "evaluator_result": {"resolved": None, "partial_attempt": True},
                        "usage": {},
                        "usage_complete": False,
                        "admissible_under_contract": False,
                        "deviations": [
                            {"class": "explicit_partial_attempt_classification"}
                        ],
                    },
                )
                resolve_partial_as = None
            elif kind == "record_batch_stop":
                receipt = action["receipt"]
                append_continuation_event(
                    ledger_path,
                    "batch_stopped",
                    {
                        "cell_id": receipt["cell_id"],
                        "termination": receipt["termination"],
                    },
                )
            elif kind == "authorize_infrastructure_rerun":
                append_continuation_event(
                    ledger_path,
                    "infrastructure_rerun_authorized",
                    {"cell_id": action["receipt"]["cell_id"], **action["state"]},
                )
            elif kind == "record_rerun_budget_stop":
                receipt = action["receipt"]
                append_continuation_event(
                    ledger_path,
                    "batch_stopped",
                    {
                        "cell_id": receipt["cell_id"],
                        "termination": receipt["termination"],
                        "reason": "trajectory_attempt_or_infrastructure_budget_exhausted",
                        "infrastructure_reruns_consumed": action["consumed"],
                    },
                )
            elif kind == "launch":
                request = build_launch_request(
                    contract,
                    action["cell"],
                    state_root,
                    action["trajectory_attempt"],
                )
                request["attempt_started_at"] = _now()
                append_continuation_event(ledger_path, "attempt_started", request)
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
                        "deviations": [
                            {"class": "runner_process_boundary_failure"}
                        ],
                    }
                append_continuation_event(ledger_path, "attempt_finished", receipt)
            else:
                raise ExperimentConfigurationError(
                    f"unsupported durable continuation action: {kind}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--contract", type=Path,
        default=Path("experiment/pilot_v2_execution_contract.json"),
    )
    parser.add_argument(
        "--terminal-result", type=Path,
        default=Path("experiment/pilot_v2_terminal_result.json"),
    )
    parser.add_argument(
        "--predecessor-ledger", type=Path,
        default=Path(".local/pilot-v2-runner/pilot-ledger.jsonl"),
    )
    parser.add_argument(
        "--authorization", type=Path,
        default=Path("experiment/pilot_v2_continuation_authorization.json"),
    )
    parser.add_argument(
        "--continuation-ledger", type=Path,
        default=Path(".local/pilot-v2-continuation") / CONTINUATION_LEDGER_NAME,
    )
    parser.add_argument(
        "--state-root", type=Path, default=Path(".local/pilot-v2-continuation")
    )
    parser.add_argument("--evaluator-root", type=Path, default=DEFAULT_EVALUATOR_ROOT)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument(
        "--credential-source-codex-home",
        type=Path,
        default=DEFAULT_SOURCE_CODEX_HOME,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--recorded-at", required=True)
    subparsers.add_parser("initialize-ledger")
    qualify = subparsers.add_parser("qualify")
    qualify.add_argument(
        "--output", type=Path,
        default=Path("experiment/pilot_v2_continuation_qualification.json"),
    )
    subparsers.add_parser("audit")
    preflight = subparsers.add_parser("execution-preflight")
    preflight.add_argument(
        "--output",
        type=Path,
        default=Path("experiment/pilot_v2_continuation_execution_preflight.json"),
    )
    dry_run = subparsers.add_parser("execution-dry-run")
    dry_run.add_argument(
        "--output",
        type=Path,
        default=Path("experiment/pilot_v2_continuation_execution_dry_run.json"),
    )
    execute = subparsers.add_parser("execute")
    execute.add_argument("--confirm", required=True)
    execute.add_argument(
        "--resolve-partial-as",
        choices=sorted(RERUNNABLE_INFRASTRUCTURE | BATCH_STOP_FAILURES),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    contract = _path(root, args.contract)
    terminal = _path(root, args.terminal_result)
    predecessor = _path(root, args.predecessor_ledger)
    authorization_path = _path(root, args.authorization)
    continuation_ledger = _path(root, args.continuation_ledger)
    state_root = _path(root, args.state_root)
    try:
        if args.command == "build":
            result = build_authorization(
                root, contract, terminal, predecessor, recorded_at=args.recorded_at
            )
            _write(authorization_path, result)
        else:
            authorization = read_authorization(authorization_path)
            validate_authorization(root, contract, terminal, predecessor, authorization)
            if args.command == "initialize-ledger":
                result = initialize_continuation_ledger(
                    authorization, continuation_ledger
                )
            elif args.command in {"qualify", "audit"}:
                result = build_qualification(
                    root,
                    contract,
                    terminal,
                    predecessor,
                    continuation_ledger,
                    authorization,
                )
                if args.command == "qualify":
                    _write(_path(root, args.output), result)
            elif args.command == "execution-dry-run":
                result = continuation_dry_run_receipt(
                    root,
                    contract,
                    terminal,
                    predecessor,
                    continuation_ledger,
                    authorization,
                    state_root,
                )
                _write(_path(root, args.output), result)
            else:
                contract_value = read_object(contract)
                evaluator_root = args.evaluator_root.resolve()
                host = read_object(root / "experiment/pilot_host_qualification.json")
                dataset_root = (
                    args.dataset_root
                    or Path(host["procedure"]["dataset_snapshot_path"])
                ).resolve()
                evaluator_python = canonical_evaluator_python(
                    evaluator_root, args.evaluator_python
                )
                source_codex_home = args.credential_source_codex_home.resolve()
                base = strict_preflight(
                    root,
                    contract_value,
                    evaluator_root,
                    dataset_root,
                    evaluator_python,
                    args.codex_binary,
                    state_root / ".qualified-runner-preflight-view",
                    source_codex_home,
                    contract,
                    validate_v2_contract,
                )
                continuation = strict_continuation_preflight(
                    root,
                    contract,
                    terminal,
                    predecessor,
                    continuation_ledger,
                    authorization,
                )
                if args.command == "execution-preflight":
                    result = {**continuation, "qualified_runner_preflight": base}
                    _write(_path(root, args.output), result)
                else:
                    tasks = resolve_tasks(
                        root, contract_value, evaluator_python, dataset_root
                    )
                    backend = LiveBackend(
                        root,
                        contract_value,
                        tasks,
                        evaluator_root,
                        dataset_root,
                        evaluator_python,
                        args.codex_binary,
                        source_codex_home,
                    )
                    result = execute_continuation_batch(
                        contract_value,
                        authorization,
                        backend,
                        state_root,
                        continuation_ledger,
                        args.confirm,
                        args.resolve_partial_as,
                    )
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_v2_continuation: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
