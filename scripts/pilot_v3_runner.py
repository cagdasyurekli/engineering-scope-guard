#!/usr/bin/env python3
"""Preflight, dry-run, pause, or future-authorized Pilot-v3 execution."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_integrity import inspect_file_auth, remove_file_auth
from engineering_scope_guard.pilot_runner import sha256_file
from engineering_scope_guard.pilot_v3 import (
    append_event,
    build_launch_request,
    execute_attempt_durably,
    execution_confirmation,
    next_scheduler_action,
    planned_pause_allowed,
    read_events,
    reconstruct_receipt_from_events,
    validate_contract,
)
try:
    from scripts.pilot_runner import (
        LiveBackend,
        _checked,
        _dataset_hashes,
        _image_id,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
    from scripts.pilot_host_qualification import QualificationError, _docker_environment
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_runner import (  # type: ignore[no-redef]
        LiveBackend,
        _checked,
        _dataset_hashes,
        _image_id,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
    from pilot_host_qualification import (  # type: ignore[no-redef]
        QualificationError,
        _docker_environment,
    )


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected object in {path}")
    return value


def _validate(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pool = _read(root / "experiment/pilot_v3_pool.json")
    schedule = _read(root / "experiment/pilot_v3_schedule.json")
    contract = _read(root / "experiment/pilot_v3_execution_contract.json")
    validate_contract(root, contract, pool, schedule)
    return pool, schedule, contract


def _initialize(contract: dict[str, Any], ledger: Path) -> list[dict[str, Any]]:
    events = read_events(ledger)
    if events:
        expected = (
            ("contract_frozen", {"contract_sha256": contract["contract_sha256"]}),
            ("pool_frozen", {"pool_sha256": contract["pool"]["pool_sha256"]}),
            (
                "schedule_frozen",
                {
                    "schedule_sha256": contract["schedule"]["schedule_sha256"],
                    "cells": len(contract["schedule"]["cells"]),
                },
            ),
        )
        if len(events) < len(expected) or any(
            event["event_type"] != kind or event["payload"] != payload
            for event, (kind, payload) in zip(events, expected, strict=False)
        ):
            raise ExperimentConfigurationError("Pilot-v3 ledger prefix mismatch")
        return events
    append_event(ledger, "contract_frozen", {"contract_sha256": contract["contract_sha256"]})
    append_event(ledger, "pool_frozen", {"pool_sha256": contract["pool"]["pool_sha256"]})
    append_event(
        ledger,
        "schedule_frozen",
        {
            "schedule_sha256": contract["schedule"]["schedule_sha256"],
            "cells": len(contract["schedule"]["cells"]),
        },
    )
    return read_events(ledger)


def dry_run(contract: dict[str, Any]) -> dict[str, Any]:
    requests = [
        build_launch_request(contract, cell, Path("/synthetic/pilot-v3"), 1)
        for cell in contract["schedule"]["cells"]
    ]
    roots = [value for request in requests for value in request["isolation_roots"].values()]
    return {
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "cells_resolved": len(requests),
        "all_isolation_roots_unique": len(roots) == len(set(roots)),
        "pilot_v3_subject_calls": 0,
        "pilot_v3_evaluator_calls": 0,
        "pilot_v3_cells_executed": 0,
        "ledger_written": False,
    }


def resolve_tasks(
    root: Path,
    pool: dict[str, Any],
    evaluator_python: Path,
    dataset_root: Path,
) -> dict[str, dict[str, Any]]:
    """Resolve the exact frozen Pilot-v3 tasks through the qualified bridge."""

    tasks = {
        slot["actual_task_id"]: resolve_dataset_task(
            root,
            evaluator_python,
            dataset_root,
            slot["language"],
            slot["actual_task_id"],
            "resolve",
        )
        for slot in pool["slots"]
    }
    qualification = _read(root / "experiment/pilot_v3_qualification.json")
    materialization = {
        item["instance_id"]: item for item in qualification["materialization"]
    }
    for slot in pool["slots"]:
        task = tasks[slot["actual_task_id"]]
        evidence = materialization.get(slot["actual_task_id"])
        if (
            evidence is None
            or task.get("instance_id") != slot["actual_task_id"]
            or task.get("language") != slot["language"]
            or task.get("docker_image") != slot["docker_image"]
            or task.get("base_commit") != evidence["base_commit"]
            or task.get("problem_statement_sha256")
            != evidence["problem_statement_sha256"]
        ):
            raise ExperimentConfigurationError(
                f"frozen task bridge mismatch: {slot['actual_task_id']}"
            )
    return tasks


def strict_runtime_preflight(
    root: Path,
    contract: dict[str, Any],
    pool: dict[str, Any],
    schedule: dict[str, Any],
    evaluator_root: Path,
    dataset_root: Path,
    evaluator_python: Path,
    codex_binary: str,
    state_root: Path,
    source_codex_home: Path,
) -> dict[str, Any]:
    """Revalidate every current live dependency without a provider/evaluator call."""

    validate_contract(root, contract, pool, schedule)
    contract_path = root / "experiment/pilot_v3_execution_contract.json"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "experiment/pilot_v3_execution_contract.json"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    committed = subprocess.run(
        ["git", "show", "HEAD:experiment/pilot_v3_execution_contract.json"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if tracked.returncode or committed.returncode or committed.stdout != contract_path.read_bytes():
        raise ExperimentConfigurationError("frozen Pilot-v3 contract is not tracked HEAD bytes")
    host = _read(root / "experiment/pilot_host_qualification.json")
    dataset_hashes = _dataset_hashes(dataset_root)
    if dataset_hashes != host["source"]["dataset_snapshot_files_sha256"]:
        raise ExperimentConfigurationError("pinned dataset snapshot bytes changed")
    evaluator_revision = _checked(["git", "rev-parse", "HEAD"], evaluator_root)
    repolaunch_revision = _checked(
        ["git", "-C", str(evaluator_root / "launch"), "rev-parse", "HEAD"]
    )
    environment = contract["environment"]
    if (
        evaluator_revision != environment["official_evaluator_revision"]
        or repolaunch_revision != environment["repolaunch_revision"]
    ):
        raise ExperimentConfigurationError("pinned evaluator or RepoLaunch revision changed")
    if not evaluator_python.is_file():
        raise ExperimentConfigurationError("qualified evaluator Python is absent")
    try:
        docker_environment = _docker_environment()
    except QualificationError as error:
        raise ExperimentConfigurationError("fixed Docker environment changed") from error
    if docker_environment != environment["docker"]:
        raise ExperimentConfigurationError("fixed Docker platform/resources changed")
    codex_version = _checked([codex_binary, "--version"])
    if environment["codex_version"] not in codex_version:
        raise ExperimentConfigurationError("Codex subject version changed")
    help_text = _checked([codex_binary, "exec", "--help"])
    resume_help = _checked([codex_binary, "exec", "resume", "--help"])
    for flag in ("--json", "--ignore-user-config", "--ignore-rules", "--approve-for-me"):
        if flag not in help_text:
            raise ExperimentConfigurationError(f"Codex subject interface lacks {flag}")
    if "--json" not in resume_help:
        raise ExperimentConfigurationError("Codex corrective-resume interface changed")
    qualification = _read(root / "experiment/pilot_v3_qualification.json")
    materialization = {
        item["instance_id"]: item for item in qualification["materialization"]
    }
    image_ids: dict[str, str] = {}
    for slot in pool["slots"]:
        evidence = materialization.get(slot["actual_task_id"])
        if evidence is None or evidence["official_image"] != slot["docker_image"]:
            raise ExperimentConfigurationError("Pilot-v3 image qualification is incomplete")
        image_id = _image_id(slot["docker_image"])
        if image_id != evidence["image_id"]:
            raise ExperimentConfigurationError(
                f"qualified image identity changed: {slot['actual_task_id']}"
            )
        image_ids[slot["actual_task_id"]] = image_id
    tasks = resolve_tasks(root, pool, evaluator_python, dataset_root)
    stale_auth = sorted(state_root.glob("attempts/*/*/codex-home/auth.json"))
    if stale_auth:
        raise ExperimentConfigurationError("trajectory-local authentication remains in Pilot-v3 state")
    return {
        "schema_name": "engineering-scope-guard.pilot-v3-runtime-preflight",
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "pool_sha256": pool["pool_sha256"],
        "schedule_sha256": schedule["schedule_sha256"],
        "short_policy_sha256": contract["arms"]["short_policy_sha256"],
        "codex_version": codex_version,
        "evaluator_revision": evaluator_revision,
        "repolaunch_revision": repolaunch_revision,
        "dataset_files_sha256": dataset_hashes,
        "docker_environment": docker_environment,
        "contract_file_sha256": sha256_file(contract_path),
        "contract_tracked_unchanged": True,
        "evaluator_interface": _verify_evaluator_interface(evaluator_root),
        "qualified_image_ids": image_ids,
        "resolved_problem_statement_sha256": {
            instance_id: task["problem_statement_sha256"]
            for instance_id, task in sorted(tasks.items())
        },
        "credential_bridge": {
            **inspect_file_auth(source_codex_home),
            "copied_artifacts": ["auth.json"],
            "normal_codex_state_shared": False,
        },
        "stale_trajectory_credentials": 0,
        "subject_invocations": 0,
        "evaluator_invocations": 0,
    }


def execute(
    contract: dict[str, Any],
    backend: LiveBackend,
    state_root: Path,
    confirmation: str,
) -> dict[str, Any]:
    if confirmation != execution_confirmation(contract):
        raise ExperimentConfigurationError("Pilot-v3 live confirmation digest is absent or wrong")
    ledger = state_root / "pilot-v3-ledger.jsonl"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "LIVE_EXECUTION_EXPLICITLY_INVOKED").write_text(
        datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8"
    )
    _initialize(contract, ledger)
    while True:
        events = read_events(ledger)
        action = next_scheduler_action(contract, events)
        kind = action["action"]
        if kind in {"complete", "batch_stopped"}:
            return {"status": kind, "ledger_events": len(events)}
        if kind == "launch":
            request = build_launch_request(
                contract, action["cell"], state_root, action["trajectory_attempt"]
            )
            request["attempt_started_at"] = datetime.now(timezone.utc).isoformat()
            append_event(ledger, "attempt_started", request)
            try:
                execute_attempt_durably(contract, request, backend, ledger)
            except (ExperimentConfigurationError, OSError, ValueError) as error:
                append_event(
                    ledger,
                    "batch_stopped",
                    {
                        "cell_id": request["cell_id"],
                        "termination": "harness_failure",
                        "sanitized_reason": type(error).__name__,
                    },
                )
        elif kind == "reconstruct_receipt":
            receipt = reconstruct_receipt_from_events(contract, action["request"], events)
            append_event(ledger, "receipt_committed", receipt)
        elif kind == "cleanup_then_reconstruct":
            request = action["request"]
            remove_file_auth(Path(request["isolation_roots"]["codex_home"]))
            append_event(
                ledger,
                "credential_cleanup_verified",
                {
                    "cell_id": request["cell_id"],
                    "trajectory_attempt": request["trajectory_attempt"],
                    "credential_removed": True,
                },
            )
        elif kind == "authorize_operator_restart":
            append_event(
                ledger,
                "operator_restart_authorized",
                {
                    "cell_id": action["cell_id"],
                    "next_attempt": action["next_attempt"],
                    "operator_restarts_consumed": sum(
                        event["event_type"] == "operator_restart_authorized" for event in events
                    )
                    + 1,
                },
            )
        elif kind == "authorize_infrastructure_rerun":
            append_event(
                ledger,
                "infrastructure_rerun_authorized",
                {
                    "cell_id": action["cell_id"],
                    "next_attempt": action["next_attempt"],
                    "infrastructure_reruns_consumed": sum(
                        event["event_type"] == "infrastructure_rerun_authorized"
                        for event in events
                    )
                    + 1,
                },
            )
        elif kind == "record_batch_stop":
            append_event(
                ledger,
                "batch_stopped",
                {"termination": action["termination"], "preserved": True},
            )
        else:
            raise ExperimentConfigurationError(f"unsupported Pilot-v3 action: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("/private/tmp/engineering-scope-guard-swe-bench-live-qualification/dataset"),
    )
    parser.add_argument(
        "--evaluator-root",
        type=Path,
        default=Path("/private/tmp/engineering-scope-guard-swe-bench-live-qualification"),
    )
    parser.add_argument("--state-root", type=Path, default=Path(".local/pilot-v3-runner"))
    parser.add_argument("--credential-source-codex-home", type=Path, default=Path.home() / ".codex")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    subparsers.add_parser("dry-run")
    pause = subparsers.add_parser("planned-pause")
    pause.add_argument("--reason", required=True)
    interrupt = subparsers.add_parser("record-operator-interruption")
    interrupt.add_argument("--cause", required=True)
    live = subparsers.add_parser("execute")
    live.add_argument("--confirm", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    state_root = args.state_root if args.state_root.is_absolute() else root / args.state_root
    try:
        _, _, contract = _validate(root)
        if args.command == "dry-run":
            result = dry_run(contract)
        elif args.command == "preflight":
            qualification = _read(root / "experiment/pilot_v3_qualification.json")
            result = {
                "status": "pass" if qualification["status"] == "pass" else "fail",
                "contract_sha256": contract["contract_sha256"],
                "qualification_decision": qualification["decision"],
                "live_execution_authorized_by_this_command": False,
            }
        elif args.command in {"planned-pause", "record-operator-interruption"}:
            ledger = state_root / "pilot-v3-ledger.jsonl"
            events = _initialize(contract, ledger)
            if args.command == "planned-pause":
                if not planned_pause_allowed(events):
                    raise ExperimentConfigurationError("planned pause is allowed only between cells")
                append_event(
                    ledger,
                    "planned_pause",
                    {"reason": args.reason, "retry_allowance_consumed": 0},
                )
                result = {"status": "paused-between-cells", "retry_allowance_consumed": 0}
            else:
                starts = [event["payload"] for event in events if event["event_type"] == "attempt_started"]
                receipts = [event["payload"] for event in events if event["event_type"] == "receipt_committed"]
                if not starts or any(
                    receipt["cell_id"] == starts[-1]["cell_id"]
                    and receipt["trajectory_attempt"] == starts[-1]["trajectory_attempt"]
                    for receipt in receipts
                ):
                    raise ExperimentConfigurationError("no active attempt to interrupt")
                request = starts[-1]
                append_event(
                    ledger,
                    "operator_interruption_recorded",
                    {
                        "cell_id": request["cell_id"],
                        "trajectory_attempt": request["trajectory_attempt"],
                        "cause": args.cause,
                        "outcome_reviewed": False,
                    },
                )
                result = {"status": "operator-interruption-preserved", "attempt_immutable": True}
        else:
            evaluator_python = canonical_evaluator_python(args.evaluator_root.resolve(), None)
            tasks = resolve_tasks(
                root, contract["pool"], evaluator_python, args.dataset_root.resolve()
            )
            backend = LiveBackend(
                root,
                contract,
                tasks,
                args.evaluator_root.resolve(),
                args.dataset_root.resolve(),
                evaluator_python,
                "codex",
                args.credential_source_codex_home.resolve(),
            )
            result = execute(contract, backend, state_root, args.confirm)
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_v3_runner: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
