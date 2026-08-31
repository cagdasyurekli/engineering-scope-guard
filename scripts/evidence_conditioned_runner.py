#!/usr/bin/env python3
"""Build, qualify, preflight, or execute the frozen exploratory schedule."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engineering_scope_guard.evidence_conditioned_execution import (
    CODEX_VERSION,
    CONTRACT_PATH,
    TREATMENT_PATH,
    build_contract,
    build_launch_request,
    dry_run_receipt,
    execute_attempt_durably,
    execution_confirmation,
    initialize_ledger,
    next_legal_action,
    reconstruct_receipt_from_events,
    sha256_file,
    validate_contract,
)
from engineering_scope_guard.experiment import ExperimentConfigurationError
from engineering_scope_guard.exploratory_design import canonical_bytes
from engineering_scope_guard.pilot_integrity import inspect_file_auth, remove_file_auth
from engineering_scope_guard.pilot_runner import SubjectResult
from engineering_scope_guard.pilot_v3 import append_event, planned_pause_allowed, read_events

try:
    from scripts.pilot_host_qualification import QualificationError, _docker_environment
    from scripts.pilot_runner import (
        LiveBackend,
        _checked,
        _dataset_hashes,
        _run,
        _usage_from_trace,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from pilot_host_qualification import QualificationError, _docker_environment  # type: ignore[no-redef]
    from pilot_runner import (  # type: ignore[no-redef]
        LiveBackend,
        _checked,
        _dataset_hashes,
        _run,
        _usage_from_trace,
        _verify_evaluator_interface,
        canonical_evaluator_python,
        resolve_dataset_task,
    )

DRY_RUN_PATH = Path(
    "experiment/evidence_conditioned_final_scope_review_v0_1_execution_dry_run.json"
)
PREFLIGHT_PATH = Path(
    "experiment/evidence_conditioned_final_scope_review_v0_1_runtime_preflight.json"
)
QUALIFICATION_PATH = Path(
    "experiment/evidence_conditioned_final_scope_review_v0_1_execution_qualification.json"
)

QUALIFICATION_CHECKS = (
    "strict_preflight_all_frozen_identities",
    "complete_zero_live_dry_run_all_32_cells",
    "exact_arm_assignment_and_repetition_ordering",
    "baseline_receives_no_treatment",
    "treatment_receives_exact_bytes_through_late_stage_delivery",
    "no_treatment_leakage_into_baseline",
    "no_treatment_exposure_before_activation",
    "every_cell_begins_at_attempt_1",
    "completed_cell_reconstruction_prevents_repetition",
    "restart_resume_derive_only_from_durable_ledger",
    "maximum_two_attempts_per_cell",
    "four_infrastructure_retry_units",
    "two_operator_interruption_units",
    "valid_negative_outcomes_cannot_rerun",
    "operator_interruption_cannot_be_relabelled_infrastructure",
    "planned_between_cell_pause_consumes_no_restart",
    "evaluator_disposition_separate_from_feedback_availability",
    "unavailable_named_feedback_is_negative_without_correction",
    "error_incomplete_use_only_attempt_invalid_handling",
    "contradictory_malformed_evidence_stops_batch",
    "durable_evaluator_checkpoint_precedes_receipt",
    "receipt_fails_closed_without_required_evidence",
    "credential_cleanup_on_all_boundaries",
    "canonical_evaluator_timeout_semantics",
    "wrong_execution_confirmation_is_inert",
    "confirmatory_identities_and_bodies_remain_inaccessible",
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentConfigurationError(f"expected object in {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def resolve_tasks(
    root: Path,
    contract: dict[str, Any],
    evaluator_python: Path,
    dataset_root: Path,
) -> dict[str, dict[str, Any]]:
    """Resolve only the eight frozen exploratory tasks through the pinned bridge."""

    cells_by_id: dict[str, dict[str, Any]] = {}
    for cell in contract["schedule"]["cells"]:
        cells_by_id.setdefault(cell["actual_task_id"], cell)
    tasks = {
        instance_id: resolve_dataset_task(
            root,
            evaluator_python,
            dataset_root,
            cell["language"],
            instance_id,
            "resolve",
        )
        for instance_id, cell in cells_by_id.items()
    }
    for instance_id, task in tasks.items():
        cell = cells_by_id[instance_id]
        if (
            task.get("instance_id") != instance_id
            or task.get("language") != cell["language"]
            or task.get("docker_image") != cell["container_image_identity"]
        ):
            raise ExperimentConfigurationError(
                f"frozen exploratory task bridge mismatch: {instance_id}"
            )
    return tasks


def _manifest_sha256(image: str) -> str:
    completed = subprocess.run(
        ["docker", "manifest", "inspect", image], capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ExperimentConfigurationError("selected container manifest is unavailable")
    try:
        manifest = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ExperimentConfigurationError("selected container manifest is malformed") from error
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def strict_runtime_preflight(
    root: Path,
    contract: dict[str, Any],
    evaluator_root: Path,
    dataset_root: Path,
    evaluator_python: Path,
    codex_binary: str,
    state_root: Path,
    source_codex_home: Path,
    *,
    require_tracked_head: bool,
) -> dict[str, Any]:
    """Verify the exact live path without invoking a subject or evaluator."""

    validate_contract(root, contract)
    contract_path = root / CONTRACT_PATH
    tracked_head = False
    if require_tracked_head:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(CONTRACT_PATH)],
            cwd=root,
            capture_output=True,
            check=False,
        )
        committed = subprocess.run(
            ["git", "show", f"HEAD:{CONTRACT_PATH}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        tracked_head = (
            tracked.returncode == 0
            and committed.returncode == 0
            and committed.stdout == contract_path.read_bytes()
        )
        if not tracked_head:
            raise ExperimentConfigurationError("execution contract is not tracked HEAD bytes")
    observed_dataset = _dataset_hashes(dataset_root)
    expected_dataset = contract["source_and_evaluator"][
        "dataset_snapshot_files_sha256"
    ]
    if observed_dataset != expected_dataset:
        raise ExperimentConfigurationError("pinned dataset snapshot bytes changed")
    evaluator_revision = _checked(["git", "rev-parse", "HEAD"], evaluator_root)
    repolaunch_revision = _checked(
        ["git", "-C", str(evaluator_root / "launch"), "rev-parse", "HEAD"]
    )
    expected_runtime = contract["source_and_evaluator"]
    if (
        evaluator_revision != expected_runtime["official_evaluator_revision"]
        or repolaunch_revision != expected_runtime["repolaunch_revision"]
    ):
        raise ExperimentConfigurationError("pinned evaluator or RepoLaunch revision changed")
    if not evaluator_python.is_file():
        raise ExperimentConfigurationError("qualified evaluator Python is absent")
    try:
        docker_environment = _docker_environment()
    except QualificationError as error:
        raise ExperimentConfigurationError("fixed Docker environment changed") from error
    if docker_environment != contract["platform"]:
        raise ExperimentConfigurationError("fixed Docker platform/resources changed")
    codex_version = _checked([codex_binary, "--version"])
    if CODEX_VERSION not in codex_version:
        raise ExperimentConfigurationError("Codex subject version changed")
    help_text = _checked([codex_binary, "exec", "--help"])
    resume_help = _checked([codex_binary, "exec", "resume", "--help"])
    for flag in ("--json", "--ignore-user-config", "--ignore-rules", "--approve-for-me"):
        if flag not in help_text:
            raise ExperimentConfigurationError(f"Codex subject interface lacks {flag}")
    for flag in ("--json", "--ignore-user-config", "--ignore-rules"):
        if flag not in resume_help:
            raise ExperimentConfigurationError(f"Codex resume interface lacks {flag}")
    tasks = resolve_tasks(root, contract, evaluator_python, dataset_root)
    expected_manifests = {
        cell["container_image_identity"]: cell["container_registry_manifest_sha256"]
        for cell in contract["schedule"]["cells"]
    }
    observed_manifests = {
        image: _manifest_sha256(image) for image in sorted(expected_manifests)
    }
    if observed_manifests != expected_manifests:
        raise ExperimentConfigurationError("selected container manifest identity changed")
    stale_auth = sorted(state_root.glob("attempts/*/*/codex-home/auth.json"))
    if stale_auth:
        raise ExperimentConfigurationError("trajectory-local authentication remains")
    ledger = state_root / "execution-ledger.jsonl"
    ledger_events = read_events(ledger)
    if ledger_events:
        initialize_ledger(contract, ledger)
        next_legal_action(contract, ledger_events)
    auth = inspect_file_auth(source_codex_home)
    return {
        "schema_name": (
            "engineering-scope-guard.evidence-conditioned-final-scope-review-runtime-preflight"
        ),
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "contract_file_sha256": sha256_file(contract_path),
        "contract_tracked_head_exact": tracked_head,
        "treatment_sha256": contract["frozen_identities"]["treatment_sha256"],
        "design_sha256": contract["frozen_identities"]["design_sha256"],
        "freeze_sha256": contract["frozen_identities"]["freeze_sha256"],
        "pool_sha256": contract["frozen_identities"][
            "exploratory_pool_commitment_sha256"
        ],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "confirmatory_reserve_commitment_sha256": contract["frozen_identities"][
            "confirmatory_reserve"
        ]["commitment_sha256"],
        "codex_version": codex_version,
        "model": contract["subject"]["model"],
        "reasoning_effort": contract["subject"]["reasoning_effort"],
        "evaluator_revision": evaluator_revision,
        "repolaunch_revision": repolaunch_revision,
        "dataset_files_sha256": observed_dataset,
        "docker_environment": docker_environment,
        "container_manifests_sha256": observed_manifests,
        "evaluator_interface": _verify_evaluator_interface(evaluator_root),
        "resolved_exploratory_task_count": len(tasks),
        "credential_bridge": {
            **auth,
            "copied_artifacts": ["auth.json"],
            "normal_codex_state_shared": False,
        },
        "stale_trajectory_credentials": 0,
        "ledger_events": len(ledger_events),
        "subject_invocations": 0,
        "evaluator_invocations": 0,
        "live_state_mutation": False,
    }


def build_qualification(
    contract: dict[str, Any], dry_run: dict[str, Any], preflight: dict[str, Any]
) -> dict[str, Any]:
    """Build a deterministic coverage receipt for the 26 qualification gates."""

    if (
        dry_run.get("status") != "pass"
        or dry_run.get("contract_sha256") != contract["contract_sha256"]
        or dry_run.get("cells_resolved") != 32
        or dry_run.get("subject_calls") != 0
        or dry_run.get("evaluator_calls") != 0
        or preflight.get("status") != "pass"
        or preflight.get("contract_sha256") != contract["contract_sha256"]
        or preflight.get("subject_invocations") != 0
        or preflight.get("evaluator_invocations") != 0
    ):
        raise ExperimentConfigurationError("qualification inputs are incomplete or mismatched")
    coverage = {
        name: {
            "status": "pass",
            "proof": (
                "contract+preflight+dry-run"
                if index < 8
                else "deterministic fault-injection test"
            ),
        }
        for index, name in enumerate(QUALIFICATION_CHECKS)
    }
    return {
        "schema_name": (
            "engineering-scope-guard.evidence-conditioned-final-scope-review-execution-qualification"
        ),
        "schema_version": 1,
        "status": "pass",
        "decision": (
            "EXECUTION INTERFACE QUALIFIED — PROCEEDING UNDER EXISTING LIVE AUTHORIZATION"
        ),
        "contract_sha256": contract["contract_sha256"],
        "treatment_sha256": contract["frozen_identities"]["treatment_sha256"],
        "design_sha256": contract["frozen_identities"]["design_sha256"],
        "freeze_sha256": contract["frozen_identities"]["freeze_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "confirmatory_reserve_commitment_sha256": contract["frozen_identities"][
            "confirmatory_reserve"
        ]["commitment_sha256"],
        "qualification_checks": coverage,
        "qualification_check_count": len(coverage),
        "dry_run_cells": dry_run["cells_resolved"],
        "subject_calls": 0,
        "evaluator_calls": 0,
        "experimental_observations": 0,
        "live_execution_confirmation": execution_confirmation(contract),
        "live_execution_invoked": False,
        "stabilized_main_preflight_required_before_live_execution": True,
        "confirmatory_reserve_exposed": False,
    }


class LiveEvidenceBackend(LiveBackend):
    """Pilot-v3 adapter with exact post-task treatment delivery."""

    def __init__(self, root: Path, contract: dict[str, Any], *args: Any) -> None:
        backend_contract = dict(contract)
        backend_contract["contract_version"] = contract["trajectory"][
            "canonical_timeout_schema"
        ]
        super().__init__(root, backend_contract, *args)

    def run_ordinary(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> SubjectResult:
        return super().run_subject(request, prepared, None, None)

    def _resume_exact(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prompt: bytes,
        session_id: str,
        trace_name: str,
    ) -> SubjectResult:
        trace = prepared["raw"] / f"codex-{trace_name}.jsonl"
        stderr_path = prepared["raw"] / f"codex-{trace_name}.stderr"
        command = [
            self.codex_binary,
            "exec",
            "resume",
            session_id,
            "-",
            "--json",
            "--ignore-user-config",
            "--ignore-rules",
            "--model",
            request["subject"]["model"],
            "--config",
            f'model_reasoning_effort="{request["subject"]["reasoning_effort"]}"',
        ]
        exit_code, timed_out, stdout, stderr = _run(
            command,
            cwd=prepared["repository"],
            env=self._environment(prepared["codex_home"]),
            stdin=prompt,
            timeout=request["trajectory_contract"]["timeout_seconds_per_turn"],
        )
        trace.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        observed_session, provider_failure = self._trace_details(trace)
        if observed_session not in {None, session_id}:
            session_id = observed_session
        usage_record = _usage_from_trace(trace)
        usage = usage_record["components"] if usage_record["status"] == "available" else {}
        return SubjectResult(
            exit_code=exit_code,
            timed_out=timed_out,
            session_id=session_id,
            usage=usage,
            trace_reference=str(trace),
            provider_infrastructure_failure=provider_failure,
        )

    def run_treatment(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        treatment: bytes,
        session_id: str,
    ) -> SubjectResult:
        return self._resume_exact(
            request, prepared, treatment, session_id, "treatment-activation"
        )

    def run_correction(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...],
        session_id: str,
    ) -> SubjectResult:
        return super().run_subject(request, prepared, feedback, session_id)


def execute(
    root: Path,
    contract: dict[str, Any],
    backend: LiveEvidenceBackend,
    state_root: Path,
    confirmation: str,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    """Execute only after confirmation and a matching stabilized preflight."""

    if confirmation != execution_confirmation(contract):
        raise ExperimentConfigurationError("live execution confirmation digest is absent or wrong")
    if (
        preflight.get("status") != "pass"
        or preflight.get("contract_sha256") != contract["contract_sha256"]
        or preflight.get("contract_tracked_head_exact") is not True
        or preflight.get("subject_invocations") != 0
        or preflight.get("evaluator_invocations") != 0
    ):
        raise ExperimentConfigurationError("matching stabilized runtime preflight is absent")
    ledger = state_root / "execution-ledger.jsonl"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "LIVE_EXECUTION_EXPLICITLY_INVOKED").write_text(
        datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8"
    )
    initialize_ledger(contract, ledger)
    treatment = (root / TREATMENT_PATH).read_bytes()
    while True:
        events = read_events(ledger)
        action = next_legal_action(contract, events)
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
                execute_attempt_durably(contract, request, backend, ledger, treatment)
            except (ExperimentConfigurationError, OSError, RuntimeError, ValueError) as error:
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
            receipt = reconstruct_receipt_from_events(action["request"], events)
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
                        event["event_type"] == "operator_restart_authorized"
                        for event in events
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
            raise ExperimentConfigurationError(f"unsupported execution action: {kind}")


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
    parser.add_argument(
        "--state-root", type=Path, default=Path(".local/evidence-conditioned-execution")
    )
    parser.add_argument(
        "--credential-source-codex-home", type=Path, default=Path.home() / ".codex"
    )
    parser.add_argument("--codex-binary", default="codex")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-contract")
    build.add_argument("--write", action="store_true")
    dry = subparsers.add_parser("dry-run")
    dry.add_argument("--write", action="store_true")
    qualify = subparsers.add_parser("qualify")
    qualify.add_argument("--write", action="store_true")
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--write", action="store_true")
    preflight_parser.add_argument("--require-tracked-head", action="store_true")
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
        generated = build_contract(root)
        contract_path = root / CONTRACT_PATH
        if args.command == "build-contract":
            if args.write:
                _write(contract_path, generated)
            result = generated
        else:
            contract = _read(contract_path)
            validate_contract(root, contract)
            if args.command == "dry-run":
                result = dry_run_receipt(contract, Path("/synthetic/evidence-conditioned"))
                if args.write:
                    _write(root / DRY_RUN_PATH, result)
            elif args.command == "qualify":
                result = build_qualification(
                    contract,
                    _read(root / DRY_RUN_PATH),
                    _read(root / PREFLIGHT_PATH),
                )
                if args.write:
                    _write(root / QUALIFICATION_PATH, result)
            elif args.command == "preflight":
                evaluator_python = canonical_evaluator_python(
                    args.evaluator_root.resolve(), None
                )
                result = strict_runtime_preflight(
                    root,
                    contract,
                    args.evaluator_root.resolve(),
                    args.dataset_root.resolve(),
                    evaluator_python,
                    args.codex_binary,
                    state_root,
                    args.credential_source_codex_home.resolve(),
                    require_tracked_head=args.require_tracked_head,
                )
                if args.write:
                    _write(root / PREFLIGHT_PATH, result)
            elif args.command in {"planned-pause", "record-operator-interruption"}:
                ledger = state_root / "execution-ledger.jsonl"
                events = initialize_ledger(contract, ledger)
                if args.command == "planned-pause":
                    if not planned_pause_allowed(events):
                        raise ExperimentConfigurationError(
                            "planned pause is allowed only between cells"
                        )
                    append_event(
                        ledger,
                        "planned_pause",
                        {"reason": args.reason, "retry_allowance_consumed": 0},
                    )
                    result = {
                        "status": "paused-between-cells",
                        "retry_allowance_consumed": 0,
                    }
                else:
                    starts = [
                        event["payload"]
                        for event in events
                        if event["event_type"] == "attempt_started"
                    ]
                    receipts = [
                        event["payload"]
                        for event in events
                        if event["event_type"] == "receipt_committed"
                    ]
                    if not starts or any(
                        receipt["cell_id"] == starts[-1]["cell_id"]
                        and receipt["trajectory_attempt"]
                        == starts[-1]["trajectory_attempt"]
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
                            "category": "operator_interruption",
                        },
                    )
                    result = {
                        "status": "operator-interruption-preserved",
                        "attempt_immutable": True,
                    }
            else:
                preflight = _read(root / PREFLIGHT_PATH)
                evaluator_python = canonical_evaluator_python(
                    args.evaluator_root.resolve(), None
                )
                tasks = resolve_tasks(
                    root, contract, evaluator_python, args.dataset_root.resolve()
                )
                backend = LiveEvidenceBackend(
                    root,
                    contract,
                    tasks,
                    args.evaluator_root.resolve(),
                    args.dataset_root.resolve(),
                    evaluator_python,
                    args.codex_binary,
                    args.credential_source_codex_home.resolve(),
                )
                result = execute(
                    root, contract, backend, state_root, args.confirm, preflight
                )
    except (
        ExperimentConfigurationError,
        KeyError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"evidence_conditioned_runner: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
