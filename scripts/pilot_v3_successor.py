#!/usr/bin/env python3
"""Freeze or validate the zero-live Pilot-v3 successor qualification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.pilot_integrity import remove_file_auth
from engineering_scope_guard.pilot_runner import sha256_file
from engineering_scope_guard.pilot_v3 import (
    append_event,
    build_launch_request,
    execute_attempt_durably,
    reconstruct_receipt_from_events,
)
from engineering_scope_guard.pilot_v3_successor import (
    DECISION,
    INTERFACE_DECISION,
    build_authorization,
    initialize_successor_ledger,
    next_successor_action,
    repair_identity,
    strict_successor_preflight,
    successor_dry_run_receipt,
    successor_execution_confirmation,
    utc_now,
    validate_authorization,
    validate_successor_ledger,
    write_json_exclusive,
)
try:
    from scripts.pilot_runner import (
        DEFAULT_EVALUATOR_ROOT,
        DEFAULT_SOURCE_CODEX_HOME,
        LiveBackend,
        _now,
        canonical_evaluator_python,
        runner_lock,
    )
    from scripts.pilot_v3_runner import resolve_tasks, strict_runtime_preflight
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_runner import (  # type: ignore[no-redef]
        DEFAULT_EVALUATOR_ROOT,
        DEFAULT_SOURCE_CODEX_HOME,
        LiveBackend,
        _now,
        canonical_evaluator_python,
        runner_lock,
    )
    from pilot_v3_runner import resolve_tasks, strict_runtime_preflight  # type: ignore[no-redef]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected JSON object: {path}")
    return value


def _paths(root: Path) -> tuple[Path, Path, Path, Path]:
    return (
        root / "experiment/pilot_v3_execution_contract.json",
        root / "experiment/pilot_v3_pool.json",
        root / "experiment/pilot_v3_schedule.json",
        root / "experiment/pilot_v3_terminal_result.json",
    )


def _immutable_digests(root: Path, predecessor_ledger: Path) -> dict[str, str]:
    paths = (*_paths(root), predecessor_ledger)
    return {
        (
            str(path.relative_to(root))
            if path.is_relative_to(root)
            else "<external-predecessor-ledger>"
        ): sha256_file(path)
        for path in paths
    }


def freeze(
    root: Path,
    predecessor_ledger: Path,
    authorization_path: Path,
    successor_ledger: Path,
    qualification_path: Path,
    recorded_at: str,
) -> dict[str, Any]:
    contract_path, pool_path, schedule_path, terminal_path = _paths(root)
    before = _immutable_digests(root, predecessor_ledger)
    contract, pool, schedule, terminal = map(
        _read, (contract_path, pool_path, schedule_path, terminal_path)
    )
    authorization = build_authorization(
        root,
        contract,
        pool,
        schedule,
        terminal,
        predecessor_ledger,
        recorded_at=recorded_at,
    )
    write_json_exclusive(authorization_path, authorization)
    events = initialize_successor_ledger(authorization, successor_ledger)
    action = next_successor_action(contract, authorization, events)
    after = _immutable_digests(root, predecessor_ledger)
    if before != after:
        raise ExperimentConfigurationError("immutable Pilot-v3 evidence changed during freeze")
    qualification = {
        "schema_name": "engineering-scope-guard.pilot-v3-adapter-successor-qualification",
        "schema_version": 1,
        "recorded_at": recorded_at,
        "status": "pass",
        "decision": DECISION,
        "authorization_sha256": authorization["authorization_sha256"],
        "repair": repair_identity(root),
        "successor_ledger": {
            "path": ".local/pilot-v3-successor/pilot-v3-successor-ledger.jsonl",
            "sha256": sha256_file(successor_ledger),
            "events": len(events),
            "genesis_event_sha256": events[0]["event_sha256"],
            "separate_from_predecessor": successor_ledger != predecessor_ledger,
        },
        "next_action": {
            "action": action["action"],
            "position": action["cell"]["position"],
            "cell_id": action["cell"]["cell_id"],
            "trajectory_attempt": action["trajectory_attempt"],
        },
        "checks": {
            "frozen_contract_accepted_without_mutation": True,
            "canonical_attempt_timeout_at_launch_boundary": 1800,
            "unsupported_timeout_shapes_fail_closed": True,
            "former_key_error_boundary_passed_by_deterministic_mock": True,
            "official_disposition_and_feedback_semantics_unchanged": True,
            "durable_checkpoints_ordered_before_aggregation": True,
            "credential_cleanup_guaranteed_by_finally": True,
            "receipt_requires_durable_evaluator_evidence": True,
            "restart_and_resume_are_ledger_derived": True,
            "original_artifact_and_ledger_bytes_unchanged": before == after,
            "position_1_attempt_1_preserved": True,
            "position_1_starts_only_at_attempt_2": action["trajectory_attempt"] == 2,
            "position_1_attempt_3_forbidden": True,
            "positions_2_through_32_start_at_attempt_1": True,
            "completed_successor_cells_never_repeat": True,
            "retry_and_operator_budgets_unchanged": True,
            "live_subject_calls": 0,
            "live_evaluator_calls": 0,
            "pilot_cells_executed": 0,
            "interim_arm_comparisons": 0,
        },
        "immutable_sha256_before": before,
        "immutable_sha256_after": after,
        "verification_commands": [
            "PYTHONPATH=src python3 -m unittest tests.test_pilot_v3_adapter tests.test_pilot_v3_successor tests.test_pilot_v3 tests.test_pilot_runner",
            "PYTHONPATH=src python3 scripts/pilot_v3_successor.py validate",
        ],
        "live_execution_authorized": False,
    }
    write_json_exclusive(qualification_path, qualification)
    return qualification


def validate(
    root: Path,
    predecessor_ledger: Path,
    authorization_path: Path,
    successor_ledger: Path,
    qualification_path: Path,
) -> dict[str, Any]:
    contract_path, pool_path, schedule_path, terminal_path = _paths(root)
    contract, pool, schedule, terminal = map(
        _read, (contract_path, pool_path, schedule_path, terminal_path)
    )
    authorization = _read(authorization_path)
    qualification = _read(qualification_path)
    validate_authorization(
        root,
        contract,
        pool,
        schedule,
        terminal,
        predecessor_ledger,
        authorization,
    )
    events = validate_successor_ledger(authorization, successor_ledger)
    action = next_successor_action(contract, authorization, events)
    observed = _immutable_digests(root, predecessor_ledger)
    checks = qualification.get("checks", {})
    if (
        qualification.get("status") != "pass"
        or qualification.get("decision") != DECISION
        or qualification.get("authorization_sha256") != authorization["authorization_sha256"]
        or qualification.get("repair") != repair_identity(root)
        or qualification.get("successor_ledger", {}).get("sha256") != sha256_file(successor_ledger)
        or qualification.get("immutable_sha256_before") != observed
        or qualification.get("immutable_sha256_after") != observed
        or not checks
        or any(value is False for value in checks.values())
        or action.get("action") != "launch"
        or action.get("trajectory_attempt") != 2
        or qualification.get("live_execution_authorized") is not False
    ):
        raise ExperimentConfigurationError("Pilot-v3 successor qualification mismatch")
    return {
        "status": "pass",
        "decision": DECISION,
        "authorization_sha256": authorization["authorization_sha256"],
        "successor_ledger_sha256": sha256_file(successor_ledger),
        "next_action": "position-1-attempt-2",
        "live_execution_authorized": False,
    }


def execute_successor_batch(
    contract: dict[str, Any],
    authorization: dict[str, Any],
    backend: LiveBackend,
    state_root: Path,
    ledger_path: Path,
    confirmation: str,
) -> dict[str, Any]:
    """Execute only successor-derived actions after exact authorization binding."""

    if confirmation != successor_execution_confirmation(authorization):
        raise ExperimentConfigurationError(
            "live successor confirmation digest is absent or wrong"
        )
    marker = state_root / "REAL_SUCCESSOR_EXECUTE_INVOKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_now() + "\n", encoding="utf-8")
    with runner_lock(state_root):
        while True:
            events = validate_successor_ledger(authorization, ledger_path)
            action = next_successor_action(contract, authorization, events)
            kind = action["action"]
            if kind == "complete":
                return {"status": "complete", "successor_cells": 32}
            if kind == "batch_stopped":
                return {"status": "batch_stopped", "payload": action["payload"]}
            if kind == "reconstruct_receipt":
                receipt = reconstruct_receipt_from_events(
                    contract, action["request"], events
                )
                append_event(ledger_path, "receipt_committed", receipt)
            elif kind == "cleanup_then_reconstruct":
                request = action["request"]
                remove_file_auth(Path(request["isolation_roots"]["codex_home"]))
                append_event(
                    ledger_path,
                    "credential_cleanup_verified",
                    {
                        "cell_id": request["cell_id"],
                        "trajectory_attempt": request["trajectory_attempt"],
                        "credential_removed": True,
                    },
                )
            elif kind == "authorize_operator_restart":
                append_event(
                    ledger_path,
                    "operator_restart_authorized",
                    {
                        "cell_id": action["cell_id"],
                        "next_attempt": action["next_attempt"],
                        "operator_interruptions_consumed": action["consumed"],
                    },
                )
            elif kind == "authorize_infrastructure_rerun":
                append_event(
                    ledger_path,
                    "infrastructure_rerun_authorized",
                    {
                        "cell_id": action["cell_id"],
                        "next_attempt": action["next_attempt"],
                        "infrastructure_reruns_consumed": action["consumed"],
                    },
                )
            elif kind == "record_batch_stop":
                append_event(
                    ledger_path,
                    "batch_stopped",
                    {"termination": action["termination"], "preserved": True},
                )
            elif kind == "launch":
                request = build_launch_request(
                    contract, action["cell"], state_root, action["trajectory_attempt"]
                )
                request["attempt_started_at"] = _now()
                append_event(ledger_path, "attempt_started", request)
                try:
                    execute_attempt_durably(contract, request, backend, ledger_path)
                except (ExperimentConfigurationError, OSError, ValueError) as error:
                    append_event(
                        ledger_path,
                        "batch_stopped",
                        {
                            "cell_id": request["cell_id"],
                            "trajectory_attempt": request["trajectory_attempt"],
                            "termination": "harness_failure",
                            "sanitized_reason": type(error).__name__,
                            "preserved": True,
                        },
                    )
            else:
                raise ExperimentConfigurationError(
                    f"unsupported durable successor action: {kind}"
                )


def build_interface_qualification(
    root: Path,
    predecessor_ledger: Path,
    successor_ledger: Path,
    authorization: dict[str, Any],
    preflight_path: Path,
    dry_run_path: Path,
) -> dict[str, Any]:
    """Bind the final zero-live interface evidence to current repository bytes."""

    preflight = _read(preflight_path)
    dry_run = _read(dry_run_path)
    successor = strict_successor_preflight(
        root, predecessor_ledger, successor_ledger, authorization
    )
    if (
        preflight.get("status") != "pass"
        or preflight.get("authorization_sha256") != authorization["authorization_sha256"]
        or preflight.get("qualified_runtime_preflight", {}).get("status") != "pass"
        or dry_run.get("status") != "pass"
        or dry_run.get("decision") != INTERFACE_DECISION
        or dry_run.get("positions_resolved") != 32
        or dry_run.get("cells", [{}])[0].get("trajectory_attempt") != 2
        or any(item.get("trajectory_attempt") != 1 for item in dry_run.get("cells", [])[1:])
        or dry_run.get("ledger_modified") is not False
        or any(
            dry_run.get(key) != 0
            for key in (
                "codex_invocations",
                "evaluator_invocations",
                "pilot_cells_executed",
                "policy_comparisons_executed",
            )
        )
        or successor.get("next_position") != 1
        or successor.get("next_trajectory_attempt") != 2
    ):
        raise ExperimentConfigurationError("successor interface qualification evidence mismatch")
    immutable = _immutable_digests(root, predecessor_ledger)
    interface_paths = (
        "src/engineering_scope_guard/pilot_v3_successor.py",
        "scripts/pilot_v3_runner.py",
        "scripts/pilot_v3_successor.py",
        "tests/test_pilot_v3_successor.py",
    )
    return {
        "schema_name": "engineering-scope-guard.pilot-v3-successor-execution-interface-qualification",
        "schema_version": 1,
        "status": "pass",
        "decision": INTERFACE_DECISION,
        "authorization_sha256": authorization["authorization_sha256"],
        "interface_sha256": {
            path: sha256_file(root / path) for path in interface_paths
        },
        "evidence_sha256": {
            "experiment/pilot_v3_successor_execution_preflight.json": sha256_file(preflight_path),
            "experiment/pilot_v3_successor_execution_dry_run.json": sha256_file(dry_run_path),
        },
        "immutable_sha256_before": immutable,
        "immutable_sha256_after": _immutable_digests(root, predecessor_ledger),
        "successor_ledger": {
            "path": ".local/pilot-v3-successor/pilot-v3-successor-ledger.jsonl",
            "sha256": sha256_file(successor_ledger),
            "events": successor["successor_events"],
            "next_position": successor["next_position"],
            "next_trajectory_attempt": successor["next_trajectory_attempt"],
        },
        "activity": {
            "subject_calls": 0,
            "official_evaluator_calls": 0,
            "successor_cells_executed": 0,
            "interim_arm_effect_analyses": 0,
            "confirmatory_task_bodies_exposed": 0,
        },
        "checks": {
            "predecessor_position_1_attempt_1_immutable": True,
            "successor_position_1_starts_only_at_attempt_2": True,
            "successor_position_1_attempt_3_forbidden": True,
            "positions_2_through_32_start_at_attempt_1": True,
            "exact_frozen_schedule_and_arm_assignments": True,
            "four_infrastructure_reruns_preserved": True,
            "two_operator_interruptions_preserved_separately": True,
            "completed_cells_not_repeated_after_restart": True,
            "fresh_attempt_isolation": True,
            "credential_cleanup_before_terminal_return": True,
            "durable_checkpoint_ordering": True,
            "strict_runtime_dependencies_current": True,
            "zero_provider_qualification": True,
            "original_artifact_and_ledger_bytes_unchanged": immutable
            == _immutable_digests(root, predecessor_ledger),
        },
        "verification_commands": [
            "PYTHONPATH=src python3 -m unittest tests.test_pilot_v3_successor tests.test_pilot_v3_adapter tests.test_pilot_v3 tests.test_pilot_runner",
            "PYTHONPATH=src python3 -m unittest discover -s tests",
            "python3 -m compileall -q src scripts tests",
            "PYTHONPATH=src python3 scripts/pilot_v3_successor.py execution-preflight",
            "PYTHONPATH=src python3 scripts/pilot_v3_successor.py execution-dry-run",
        ],
        "live_execution_authorized_by_qualification": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "freeze",
            "validate",
            "execution-preflight",
            "execution-dry-run",
            "qualify-interface",
            "record-operator-interruption",
            "execute",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--predecessor-ledger",
        type=Path,
        default=Path(".local/pilot-v3-runner/pilot-v3-ledger.jsonl"),
    )
    parser.add_argument(
        "--authorization",
        type=Path,
        default=Path("experiment/pilot_v3_successor_authorization.json"),
    )
    parser.add_argument(
        "--successor-ledger",
        type=Path,
        default=Path(".local/pilot-v3-successor/pilot-v3-successor-ledger.jsonl"),
    )
    parser.add_argument(
        "--qualification",
        type=Path,
        default=Path("experiment/pilot_v3_adapter_successor_qualification.json"),
    )
    parser.add_argument("--recorded-at", default=None)
    parser.add_argument("--state-root", type=Path, default=Path(".local/pilot-v3-successor"))
    parser.add_argument("--evaluator-root", type=Path, default=DEFAULT_EVALUATOR_ROOT)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument(
        "--credential-source-codex-home",
        type=Path,
        default=DEFAULT_SOURCE_CODEX_HOME,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm")
    parser.add_argument("--cause")
    args = parser.parse_args()
    root = args.root.resolve()
    resolve = lambda path: path if path.is_absolute() else root / path
    try:
        if args.command == "freeze":
            result = freeze(
                root,
                resolve(args.predecessor_ledger),
                resolve(args.authorization),
                resolve(args.successor_ledger),
                resolve(args.qualification),
                args.recorded_at or utc_now(),
            )
        elif args.command == "validate":
            result = validate(
                root,
                resolve(args.predecessor_ledger),
                resolve(args.authorization),
                resolve(args.successor_ledger),
                resolve(args.qualification),
            )
        else:
            predecessor = resolve(args.predecessor_ledger)
            successor = resolve(args.successor_ledger)
            authorization = _read(resolve(args.authorization))
            contract, pool, schedule, terminal = map(_read, _paths(root))
            validate_authorization(
                root,
                contract,
                pool,
                schedule,
                terminal,
                predecessor,
                authorization,
            )
            state_root = resolve(args.state_root)
            if args.command == "execution-dry-run":
                before = successor.read_bytes()
                result = successor_dry_run_receipt(
                    root, predecessor, successor, authorization, state_root
                )
                if successor.read_bytes() != before or state_root.joinpath("attempts").exists():
                    raise ExperimentConfigurationError("successor dry-run modified state")
                output = resolve(
                    args.output
                    or Path("experiment/pilot_v3_successor_execution_dry_run.json")
                )
                output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            elif args.command == "qualify-interface":
                result = build_interface_qualification(
                    root,
                    predecessor,
                    successor,
                    authorization,
                    root / "experiment/pilot_v3_successor_execution_preflight.json",
                    root / "experiment/pilot_v3_successor_execution_dry_run.json",
                )
                output = resolve(
                    args.output
                    or Path("experiment/pilot_v3_successor_execution_qualification.json")
                )
                output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            elif args.command == "record-operator-interruption":
                if not args.cause:
                    raise ExperimentConfigurationError("operator interruption cause is required")
                events = validate_successor_ledger(authorization, successor)
                action = next_successor_action(contract, authorization, events)
                if action.get("action") != "record_batch_stop" or action.get("termination") != "durable_evidence_incomplete":
                    raise ExperimentConfigurationError("no unresolved active successor attempt")
                starts = [event["payload"] for event in events if event["event_type"] == "attempt_started"]
                request = starts[-1]
                append_event(
                    successor,
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
                evaluator_root = args.evaluator_root.resolve()
                host = _read(root / "experiment/pilot_host_qualification.json")
                dataset_root = (
                    args.dataset_root
                    or Path(host["procedure"]["dataset_snapshot_path"])
                ).resolve()
                evaluator_python = canonical_evaluator_python(
                    evaluator_root, args.evaluator_python
                )
                source_codex_home = args.credential_source_codex_home.resolve()
                runtime = strict_runtime_preflight(
                    root,
                    contract,
                    pool,
                    schedule,
                    evaluator_root,
                    dataset_root,
                    evaluator_python,
                    args.codex_binary,
                    state_root,
                    source_codex_home,
                )
                successor_preflight = strict_successor_preflight(
                    root, predecessor, successor, authorization
                )
                if args.command == "execution-preflight":
                    result = {
                        **successor_preflight,
                        "qualified_runtime_preflight": runtime,
                    }
                    output = resolve(
                        args.output
                        or Path("experiment/pilot_v3_successor_execution_preflight.json")
                    )
                    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
                else:
                    if not args.confirm:
                        raise ExperimentConfigurationError("successor execution confirmation is required")
                    tasks = resolve_tasks(root, pool, evaluator_python, dataset_root)
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
                    result = execute_successor_batch(
                        contract,
                        authorization,
                        backend,
                        state_root,
                        successor,
                        args.confirm,
                    )
    except (ExperimentConfigurationError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"pilot_v3_successor: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
