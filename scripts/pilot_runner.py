#!/usr/bin/env python3
"""Preflight, dry-run, or execute the frozen sequential Pilot schedule."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from engineering_scope_guard.experiment import ExperimentConfigurationError, _usage_from_trace
from engineering_scope_guard.pilot_contract import (
    BATCH_STOP_FAILURES,
    RERUNNABLE_INFRASTRUCTURE,
    classify_receipt,
    read_ledger,
    read_object,
    validate_contract,
)
from engineering_scope_guard.pilot_integrity import (
    assess_ledger_resume,
    capture_repository_baseline,
    classify_provider_event,
    inspect_file_auth,
    parse_provider_trace,
    provision_file_auth,
    remove_file_auth,
    repository_state,
    subject_patch_from_baseline,
)
from engineering_scope_guard.pilot_runner import (
    DRY_RUN_SCHEMA,
    PREFLIGHT_SCHEMA,
    EvaluatorResult,
    SubjectResult,
    append_runner_event,
    build_launch_request,
    canonical_attempt_timeout,
    dry_run_receipt,
    execute_attempt,
    execution_confirmation,
    initialize_ledger,
    next_legal_action,
    official_evaluator_command,
    parse_official_evaluator_artifacts,
    sha256_file,
)
try:
    from scripts.pilot_host_qualification import QualificationError, _docker_environment
except ModuleNotFoundError:  # Direct ``python scripts/pilot_runner.py`` execution.
    from pilot_host_qualification import QualificationError, _docker_environment

DEFAULT_EVALUATOR_ROOT = Path("/private/tmp/engineering-scope-guard-swe-bench-live-qualification")
DEFAULT_STATE_ROOT = Path(".local/pilot-runner")
DEFAULT_SOURCE_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
DEFAULT_INTEGRITY_OUTPUT = Path("experiment/pilot_execution_integrity_qualification.json")
ALLOWED_ENVIRONMENT = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
)


def canonical_evaluator_python(
    evaluator_root: Path, evaluator_python: Path | None = None
) -> Path:
    """Return an absolute evaluator interpreter path without dereferencing it.

    Virtual environments commonly expose ``bin/python`` as a symlink. Resolving
    that symlink selects the base interpreter and loses the environment's
    installed packages.
    """

    return Path(os.path.abspath(evaluator_python or evaluator_root / ".venv/bin/python"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    temporary.replace(path)


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin: bytes | None = None,
    timeout: int | None = None,
) -> tuple[int | None, bool, bytes, bytes]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
        return process.returncode, False, stdout, stderr
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return None, True, stdout, stderr


def _checked(command: list[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ExperimentConfigurationError(
            f"immutable-input command failed ({command[0]} exit {completed.returncode})"
        )
    return completed.stdout.strip()


def _dataset_hashes(dataset_root: Path) -> dict[str, str]:
    return {
        path.name: sha256_file(path)
        for path in sorted((dataset_root / "data").glob("*.parquet"))
    }


def _verify_evaluator_interface(evaluator_root: Path) -> dict[str, Any]:
    path = evaluator_root / "evaluation/evaluation.py"
    text = path.read_text(encoding="utf-8")
    required = (
        'preds[instance["instance_id"]]["model_patch"]',
        'os.path.join(instance_output_dir, "report.json")',
        'os.path.join(output_dir, "results.json")',
        'parser.add_argument("--patch_dir"',
        'parser.add_argument("--instance_ids"',
    )
    missing = [fragment for fragment in required if fragment not in text]
    if missing:
        raise ExperimentConfigurationError("pinned evaluator prediction/result interface changed")
    return {
        "source_sha256": sha256_file(path),
        "prediction_mapping": "{instance_id: {model_patch: git diff}}",
        "structured_report": "<output>/<instance_id>/report.json",
        "structured_results": "<output>/results.json",
    }


def _image_id(image: str) -> str:
    output = _checked(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    if not output:
        raise ExperimentConfigurationError(f"qualified image is absent: {image}")
    return output


def strict_preflight(
    root: Path,
    contract: dict[str, Any],
    evaluator_root: Path,
    dataset_root: Path,
    evaluator_python: Path,
    codex_binary: str,
    state_root: Path,
    source_codex_home: Path,
    contract_path: Path | None = None,
    contract_validator: Any = validate_contract,
) -> dict[str, Any]:
    """Verify all immutable live inputs without a subject/evaluator call."""

    contract_validator(contract, root)
    contract_path = contract_path or root / "experiment/pilot_execution_contract.json"
    try:
        tracked_contract_path = contract_path.relative_to(root).as_posix()
    except ValueError as error:
        raise ExperimentConfigurationError("frozen contract must be inside the repository") from error
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", tracked_contract_path],
        cwd=root,
        capture_output=True,
        check=False,
    )
    committed = subprocess.run(
        ["git", "show", f"HEAD:{tracked_contract_path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if (
        tracked.returncode != 0
        or committed.returncode != 0
        or committed.stdout != contract_path.read_bytes()
    ):
        raise ExperimentConfigurationError("frozen contract is not the tracked HEAD bytes")
    host = read_object(root / "experiment/pilot_host_qualification.json")
    expected_dataset = host["source"]["dataset_snapshot_files_sha256"]
    dataset_hashes = _dataset_hashes(dataset_root)
    if dataset_hashes != expected_dataset:
        raise ExperimentConfigurationError("pinned dataset snapshot bytes changed")
    evaluator_revision = _checked(["git", "rev-parse", "HEAD"], evaluator_root)
    repolaunch_revision = _checked(
        ["git", "-C", str(evaluator_root / "launch"), "rev-parse", "HEAD"]
    )
    if (
        evaluator_revision != contract["source_and_evaluator"]["evaluator_revision"]
        or repolaunch_revision != contract["source_and_evaluator"]["repolaunch_revision"]
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
    if contract["subject"]["codex_version"] not in codex_version:
        raise ExperimentConfigurationError("Codex subject version changed")
    help_text = _checked([codex_binary, "exec", "--help"])
    resume_help = _checked([codex_binary, "exec", "resume", "--help"])
    for flag in (
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--approve-for-me",
    ):
        if flag not in help_text:
            raise ExperimentConfigurationError(f"Codex subject interface lacks {flag}")
    if "--json" not in resume_help:
        raise ExperimentConfigurationError("Codex corrective-resume interface changed")
    images = {}
    for slot in contract["final_pool"]["slots"]:
        task = next(
            item for item in host["tasks"]
            if item["instance_id"] == slot["actual_task_id"]
        )
        image_id = _image_id(task["official_image"])
        if image_id != task["runs"][-1]["official_image"]["id"]:
            raise ExperimentConfigurationError(
                f"qualified image identity changed: {slot['actual_task_id']}"
            )
        images[slot["actual_task_id"]] = image_id
    ledger_path = state_root / "pilot-ledger.jsonl"
    events = read_ledger(ledger_path)
    action = None
    ledger_resume = None
    completed_cells = 0
    if events:
        ledger_resume = assess_ledger_resume(contract, events)
        action = ledger_resume["next_legal_action"]
        completed_cells = sum(
            event.get("event_type") == "attempt_finished"
            and classify_receipt(contract, event["payload"])["counts_as_experimental_outcome"]
            for event in events
        )
    elif (state_root / "attempts").exists():
        raise ExperimentConfigurationError("attempt roots exist without a Pilot ledger")
    stale_auth = sorted(state_root.glob("attempts/*/*/codex-home/auth.json"))
    if stale_auth:
        raise ExperimentConfigurationError("trajectory-local authentication remains in Pilot state")
    auth = inspect_file_auth(source_codex_home)
    blocked = read_object(root / "experiment/pilot_preflight.json")
    if (
        blocked.get("pilot_cells_executed") != 0
        or blocked.get("policy_comparisons_executed") != 0
    ):
        raise ExperimentConfigurationError("prior zero-execution evidence changed")
    return {
        "schema_name": PREFLIGHT_SCHEMA,
        "schema_version": 1,
        "status": "pass",
        "contract_sha256": contract["contract_sha256"],
        "final_pool_sha256": contract["final_pool"]["final_pool_sha256"],
        "schedule_sha256": contract["schedule"]["schedule_sha256"],
        "short_policy_sha256": contract["arms"]["short_policy_sha256"],
        "codex_version": codex_version,
        "evaluator_revision": evaluator_revision,
        "repolaunch_revision": repolaunch_revision,
        "dataset_files_sha256": dataset_hashes,
        "docker_environment": docker_environment,
        "contract_file_sha256": sha256_file(contract_path),
        "contract_tracked_unchanged": True,
        "evaluator_interface": _verify_evaluator_interface(evaluator_root),
        "qualified_image_ids": images,
        "ledger_present": bool(events),
        "next_legal_action": action,
        "ledger_resume": ledger_resume,
        "credential_bridge": {
            **auth,
            "copied_artifacts": ["auth.json"],
            "normal_codex_state_shared": False,
        },
        "stale_trajectory_credentials": 0,
        "execute_marker_present": (state_root / "REAL_EXECUTE_INVOKED").exists(),
        "pilot_cells_executed": completed_cells,
        "policy_comparisons_executed": completed_cells,
        "subject_invocations": 0,
        "evaluator_invocations": 0,
    }


def resolve_dataset_task(
    root: Path,
    evaluator_python: Path,
    dataset_root: Path,
    language: str,
    instance_id: str,
    command: str,
    output: Path | None = None,
) -> dict[str, Any]:
    args = [
        str(evaluator_python),
        str(root / "scripts/pilot_dataset_bridge.py"),
        "--dataset-root",
        str(dataset_root),
        "--language",
        language,
        "--instance-id",
        instance_id,
        command,
    ]
    if output is not None:
        args.extend(("--output", str(output)))
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ExperimentConfigurationError(f"dataset bridge failed for {instance_id}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ExperimentConfigurationError("dataset bridge returned malformed metadata") from error
    if not isinstance(value, dict):
        raise ExperimentConfigurationError("dataset bridge result is not an object")
    return value


def resolve_tasks(
    root: Path,
    contract: dict[str, Any],
    evaluator_python: Path,
    dataset_root: Path,
) -> dict[str, dict[str, Any]]:
    resolved = {}
    for slot in contract["final_pool"]["slots"]:
        resolved[slot["actual_task_id"]] = resolve_dataset_task(
            root,
            evaluator_python,
            dataset_root,
            slot["language"],
            slot["actual_task_id"],
            "resolve",
        )
    return resolved


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveBackend:
    """Qualified Codex/Docker/evaluator process adapter for one attempt."""

    def __init__(
        self,
        root: Path,
        contract: dict[str, Any],
        tasks: dict[str, dict[str, Any]],
        evaluator_root: Path,
        dataset_root: Path,
        evaluator_python: Path,
        codex_binary: str,
        source_codex_home: Path,
    ) -> None:
        self.root = root
        self.contract = contract
        self.tasks = tasks
        self.evaluator_root = evaluator_root
        self.dataset_root = dataset_root
        self.evaluator_python = evaluator_python
        self.codex_binary = codex_binary
        self.source_codex_home = source_codex_home

    def materialize_task_repository(
        self, task: dict[str, Any], repository: Path, derived: Path
    ) -> dict[str, Any]:
        """Copy the authoritative task image and capture its exact baseline."""

        image = task["docker_image"]
        container = _checked(["docker", "create", "--platform", "linux/amd64", image, "true"])
        try:
            copy = subprocess.run(
                ["docker", "cp", f"{container}:/testbed/.", str(repository)],
                capture_output=True,
                check=False,
            )
            if copy.returncode != 0:
                raise ExperimentConfigurationError("cannot materialize official task repository")
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
        head = _checked(["git", "rev-parse", "HEAD"], repository)
        if head != task["base_commit"]:
            raise ExperimentConfigurationError("official image repository is not at frozen base commit")
        return capture_repository_baseline(repository, derived)

    def prepare(self, request: dict[str, Any]) -> dict[str, Any]:
        roots = {name: Path(value) for name, value in request["isolation_roots"].items()}
        if any(path.exists() for path in roots.values()):
            raise ExperimentConfigurationError("attempt isolation root already exists")
        for path in roots.values():
            path.mkdir(parents=True, exist_ok=False)
        try:
            auth = provision_file_auth(self.source_codex_home, roots["codex_home"])
            task = self.tasks[request["actual_task_id"]]
            prompt_path = roots["raw"] / "task-prompt.txt"
            resolve_dataset_task(
                self.root,
                self.evaluator_python,
                self.dataset_root,
                task["language"],
                task["instance_id"],
                "prompt",
                prompt_path,
            )
            baseline = self.materialize_task_repository(
                task, roots["repository"], roots["derived"]
            )
            policy = None
            if request["arm"] == "short":
                policy = (self.root / "experiment/arms/short.txt").read_bytes()
                if hashlib.sha256(policy).hexdigest() != request["intervention_sha256"]:
                    raise ExperimentConfigurationError("short intervention bytes changed")
        except Exception:
            remove_file_auth(roots["codex_home"])
            raise
        return {
            "started_at": _now(),
            "ended_at": _now,
            "prompt_path": prompt_path,
            "policy": policy,
            "repository": roots["repository"],
            "codex_home": roots["codex_home"],
            "raw": roots["raw"],
            "derived": roots["derived"],
            "evaluator": roots.get("evaluator", roots["raw"]),
            "task": task,
            "auth": auth,
            "baseline": baseline,
        }

    def cleanup(self, prepared: dict[str, Any]) -> None:
        remove_file_auth(prepared["codex_home"])

    def _environment(self, codex_home: Path) -> dict[str, str]:
        environment = {name: os.environ[name] for name in ALLOWED_ENVIRONMENT if name in os.environ}
        environment["CODEX_HOME"] = str(codex_home)
        environment["HF_DATASETS_CACHE"] = str(self.evaluator_root / "hf-cache")
        return environment

    @staticmethod
    def _trace_details(path: Path) -> tuple[str | None, bool]:
        session_id = None
        provider_failure = False
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
                session_id = event["thread_id"]
            provider_failure = provider_failure or classify_provider_event(event)
        return session_id, provider_failure

    def run_subject(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        feedback: tuple[str, ...] | None,
        session_id: str | None,
    ) -> SubjectResult:
        round_number = 0 if feedback is None else 1
        trace = prepared["raw"] / f"codex-round-{round_number}.jsonl"
        stderr_path = prepared["raw"] / f"codex-round-{round_number}.stderr"
        if feedback is None:
            task = prepared["prompt_path"].read_bytes()
            policy = prepared["policy"]
            prompt = task if policy is None else policy + b"\n--- Task ---\n\n" + task
            command = [
                self.codex_binary,
                "exec",
                "-",
                "--json",
                "--ignore-user-config",
                "--ignore-rules",
                "--approve-for-me",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--model",
                request["subject"]["model"],
                "--config",
                f'model_reasoning_effort="{request["subject"]["reasoning_effort"]}"',
            ]
        else:
            if session_id is None:
                raise ExperimentConfigurationError("corrective round lacks trajectory session")
            prompt = (
                "The official evaluator still reports these failing check names. Fix only what "
                "is required, then stop:\n" + "\n".join(f"- {name}" for name in feedback)
            ).encode()
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
        usage_record = _usage_from_trace(trace)
        usage = usage_record["components"] if usage_record["status"] == "available" else {}
        return SubjectResult(
            exit_code=exit_code,
            timed_out=timed_out,
            session_id=session_id or observed_session,
            usage=usage,
            trace_reference=str(trace),
            provider_infrastructure_failure=provider_failure,
        )

    def create_prediction(
        self, request: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]:
        patch = subject_patch_from_baseline(
            prepared["repository"], prepared["derived"], prepared["baseline"]
        )
        patch_path = prepared["derived"] / "prediction.patch"
        patch_path.write_bytes(patch)
        prediction_path = prepared["derived"] / "prediction.json"
        _write_json(
            prediction_path,
            {request["actual_task_id"]: {"model_patch": patch.decode("utf-8")}},
        )
        return {
            "path": prediction_path,
            "patch_reference": str(patch_path),
            "patch_sha256": sha256_file(patch_path),
        }

    def evaluate(
        self,
        request: dict[str, Any],
        prepared: dict[str, Any],
        prediction: dict[str, Any],
        round_number: int,
    ) -> EvaluatorResult:
        output = prepared["evaluator"] / f"evaluator-round-{round_number}"
        output.mkdir(exist_ok=False)
        command = official_evaluator_command(
            self.evaluator_python,
            self.dataset_root,
            prepared["task"]["language"],
            prediction["path"],
            output,
            request["source_and_evaluator"]["workers"],
            request["actual_task_id"],
        )
        exit_code, timed_out, stdout, stderr = _run(
            command,
            cwd=self.evaluator_root,
            env=self._environment(prepared["codex_home"]),
            timeout=canonical_attempt_timeout(
                self.contract["contract_version"], request["trajectory_contract"]
            ),
        )
        (output / "command.stdout").write_bytes(stdout)
        (output / "command.stderr").write_bytes(stderr)
        report_path = output / request["actual_task_id"] / "report.json"
        results_path = output / "results.json"
        malformed = not results_path.is_file()
        report: dict[str, Any] = {}
        results: dict[str, Any] = {}
        artifacts = None
        if not malformed:
            try:
                report = read_object(report_path) if report_path.is_file() else {}
                results = read_object(results_path)
                artifacts = parse_official_evaluator_artifacts(
                    request["actual_task_id"], report, results
                )
            except ExperimentConfigurationError:
                malformed = True
        resolved = None if artifacts is None else artifacts.resolved
        failures = () if artifacts is None else artifacts.failing_checks
        infrastructure = artifacts is not None and artifacts.disposition in {
            "error",
            "incomplete",
        }
        return EvaluatorResult(
            exit_code=exit_code,
            timed_out=timed_out,
            resolved=resolved,
            failing_checks=tuple(failures),
            report_reference=str(report_path),
            results_reference=str(results_path),
            report_sha256=sha256_file(report_path) if report_path.is_file() else None,
            results_sha256=sha256_file(results_path) if results_path.is_file() else None,
            infrastructure_failure=infrastructure,
            malformed=malformed,
            official_disposition=(
                None if artifacts is None else artifacts.disposition
            ),
            feedback_status=None if artifacts is None else artifacts.feedback_status,
        )


def run_auth_canary(
    backend: LiveBackend,
    ordinal: int,
    *,
    runner: Any = _run,
) -> dict[str, Any]:
    """Make one content-free non-Pilot provider request from a fresh auth home."""

    with tempfile.TemporaryDirectory(prefix="engineering-scope-guard-auth-canary-") as directory:
        root = Path(directory)
        codex_home = root / "codex-home"
        workspace = root / "non-pilot-workspace"
        workspace.mkdir()
        auth = provision_file_auth(backend.source_codex_home, codex_home)
        trace_path = root / "canary.jsonl"
        provider_request_succeeded = False
        details: dict[str, Any] = {"terminal_event": None}
        usage: dict[str, int] = {}
        try:
            command = [
                backend.codex_binary,
                "exec",
                "-",
                "--json",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--approve-for-me",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--model",
                backend.contract["subject"]["model"],
                "--config",
                f'model_reasoning_effort="{backend.contract["subject"]["reasoning_effort"]}"',
            ]
            exit_code, timed_out, stdout, _stderr = runner(
                command,
                cwd=workspace,
                env=backend._environment(codex_home),
                stdin=b"Reply with exactly AUTHENTICATED.\n",
                timeout=120,
            )
            trace_path.write_bytes(stdout)
            details = parse_provider_trace(stdout)
            usage_record = _usage_from_trace(trace_path)
            provider_request_succeeded = (
                exit_code == 0
                and not timed_out
                and not details["provider_infrastructure_failure"]
                and details["terminal_event"] == "turn.completed"
                and usage_record["status"] == "available"
            )
            usage = (
                usage_record["components"] if usage_record["status"] == "available" else {}
            )
        finally:
            remove_file_auth(codex_home)
        return {
            "canary": ordinal,
            "status": "pass" if provider_request_succeeded else "fail",
            "non_pilot_workspace": True,
            "treatment": None,
            "pilot_task": False,
            "fresh_isolated_home": True,
            "auth_bridge": auth,
            "provider_request_completed": provider_request_succeeded,
            "terminal_event": details["terminal_event"],
            "usage": usage,
            "credential_material_removed": not (codex_home / "auth.json").exists(),
            "response_content_persisted": False,
            "trace_persisted": False,
        }


def qualify_materializations(
    root: Path,
    contract: dict[str, Any],
    backend: LiveBackend,
    historical_attempt_repository: Path,
) -> dict[str, Any]:
    """Materialize all frozen slots without subject, treatment, or evaluator work."""

    slots = []
    first_cell = contract["schedule"]["cells"][0]
    fresh_first_state = None
    for slot in contract["final_pool"]["slots"]:
        task = backend.tasks[slot["actual_task_id"]]
        with tempfile.TemporaryDirectory(
            prefix=f"engineering-scope-guard-slot-{slot['slot']:02d}-"
        ) as directory:
            materialization_root = Path(directory)
            repository = materialization_root / "repository"
            derived = materialization_root / "derived"
            repository.mkdir()
            derived.mkdir()
            baseline = backend.materialize_task_repository(task, repository, derived)
            no_subject_patch = subject_patch_from_baseline(repository, derived, baseline)
            state = baseline["state"]
            if slot["actual_task_id"] == first_cell["actual_task_id"]:
                fresh_first_state = state
            slots.append(
                {
                    "slot": slot["slot"],
                    "actual_task_id": slot["actual_task_id"],
                    "repository_root": f"<temporary>/slot-{slot['slot']:02d}/repository",
                    "expected_base_revision": task["base_commit"],
                    "actual_head": state["head"],
                    "staged_paths": state["staged"],
                    "tracked_worktree_paths": state["tracked_worktree"],
                    "untracked_paths": state["untracked"],
                    "ignored_paths": state["ignored"],
                    "pre_subject_baseline_tree": baseline["tree"],
                    "no_subject_patch_bytes": len(no_subject_patch),
                    "no_subject_patch_sha256": hashlib.sha256(no_subject_patch).hexdigest(),
                    "authoritative_image_state_clean": not any(
                        state[name]
                        for name in ("staged", "tracked_worktree", "untracked", "ignored")
                    ),
                    "baseline_invariant_pass": (
                        state["head"] == task["base_commit"] and no_subject_patch == b""
                    ),
                }
            )
    historical_state = repository_state(historical_attempt_repository)
    return {
        "status": "pass" if all(item["baseline_invariant_pass"] for item in slots) else "fail",
        "slots_checked": len(slots),
        "codex_invocations": 0,
        "evaluator_invocations": 0,
        "policy_treatments": 0,
        "pilot_ledger_mutations": 0,
        "slots": slots,
        "failed_cell_1_diagnosis": {
            "historical_repository_root": ".local/pilot-runner/attempts/slot-04-baseline-rep-1/attempt-1/repository",
            "historical_state": historical_state,
            "fresh_materialization_state": fresh_first_state,
            "matches_fresh_authoritative_image": historical_state == fresh_first_state,
            "origin": (
                "official benchmark image/materialization"
                if historical_state == fresh_first_state
                else "unresolved state difference"
            ),
        },
    }


def qualify_execution_integrity(
    root: Path,
    contract: dict[str, Any],
    backend: LiveBackend,
    state_root: Path,
    *,
    canary_runs: int,
) -> dict[str, Any]:
    """Qualify repaired infrastructure without launching a Pilot subject."""

    contract_path = root / "experiment/pilot_execution_contract.json"
    ledger_path = state_root / "pilot-ledger.jsonl"
    contract_before = sha256_file(contract_path)
    ledger_before = sha256_file(ledger_path)
    events = read_ledger(ledger_path)
    canaries = [run_auth_canary(backend, ordinal) for ordinal in range(1, canary_runs + 1)]
    observed_provider_event = {
        "type": "turn.failed",
        "error": {"message": "unexpected status 401 Unauthorized"},
    }
    observed_schema_classified = classify_provider_event(observed_provider_event)
    parser_qualification = {
        "status": "pass" if observed_schema_classified else "fail",
        "input": "content-free observed event schema; no provider trace persisted",
        "observed_message_only_401_classified_as_provider_infrastructure": (
            observed_schema_classified
        ),
    }
    materializations = qualify_materializations(
        root,
        contract,
        backend,
        state_root
        / "attempts/slot-04-baseline-rep-1/attempt-1/repository",
    )
    ledger_resume = assess_ledger_resume(contract, events)
    contract_after = sha256_file(contract_path)
    ledger_after = sha256_file(ledger_path)
    repairs_pass = (
        all(item["status"] == "pass" for item in canaries)
        and parser_qualification["status"] == "pass"
        and materializations["status"] == "pass"
        and contract_before == contract_after
        and ledger_before == ledger_after
    )
    if repairs_pass and ledger_resume["legal_resume"]:
        decision = "EXECUTION-INTEGRITY QUALIFIED — GO TO RESUME PILOT"
        status = "pass"
    elif repairs_pass:
        decision = "REDESIGN REQUIRED"
        status = "redesign_required"
    else:
        decision = "REDESIGN REQUIRED"
        status = "fail"
    return {
        "schema_name": "engineering-scope-guard.pilot-execution-integrity-qualification",
        "schema_version": 1,
        "recorded_at": _now(),
        "status": status,
        "decision": decision,
        "contract_sha256": contract["contract_sha256"],
        "contract_file_sha256_before": contract_before,
        "contract_file_sha256_after": contract_after,
        "frozen_contract_unchanged": contract_before == contract_after,
        "credential_mode": inspect_file_auth(backend.source_codex_home),
        "auth_canaries": canaries,
        "provider_parser": parser_qualification,
        "materialization": materializations,
        "ledger": {
            "path": ".local/pilot-runner/pilot-ledger.jsonl",
            "sha256_before": ledger_before,
            "sha256_after": ledger_after,
            "unchanged": ledger_before == ledger_after,
            "events": len(events),
            "terminal_event_sha256": events[-1]["event_sha256"],
            "resume_assessment": ledger_resume,
        },
        "experimental_activity": {
            "pilot_execute_invocations": 0,
            "pilot_subject_invocations": 0,
            "pilot_evaluator_invocations": 0,
            "policy_comparisons": 0,
            "infrastructure_reruns_recorded": 0,
            "task_replacements": 0,
            "ledger_mutations": 0,
            "non_pilot_auth_canary_invocations": canary_runs,
        },
        "repairs_qualified": repairs_pass,
        "resume_blocker": (
            None
            if ledger_resume["legal_resume"]
            else "preserved terminal batch_stopped ledger has no legal resume transition"
        ),
    }


@contextmanager
def runner_lock(state_root: Path) -> Iterator[None]:
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / "runner.lock"
    with path.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExperimentConfigurationError("another Pilot runner owns the state lock") from error
        yield


def _resolve_partial(
    contract: dict[str, Any], ledger_path: Path, request: dict[str, Any], termination: str
) -> None:
    if termination not in RERUNNABLE_INFRASTRUCTURE | BATCH_STOP_FAILURES:
        raise ExperimentConfigurationError("partial attempts may only receive a frozen infrastructure class")
    receipt = {
        **request,
        "started_at": request.get("attempt_started_at", _now()),
        "ended_at": _now(),
        "termination": termination,
        "evaluator_result": {"resolved": None, "partial_attempt": True},
        "usage": {},
        "usage_complete": False,
        "admissible_under_contract": False,
        "deviations": [{"class": "explicit_partial_attempt_classification"}],
    }
    append_runner_event(ledger_path, "attempt_finished", receipt)


def execute_batch(
    root: Path,
    contract: dict[str, Any],
    backend: LiveBackend,
    state_root: Path,
    confirmation: str,
    resolve_partial_as: str | None,
) -> dict[str, Any]:
    if confirmation != execution_confirmation(contract):
        raise ExperimentConfigurationError("live execute confirmation digest is absent or wrong")
    marker = state_root / "REAL_EXECUTE_INVOKED"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_now() + "\n", encoding="utf-8")
    ledger_path = state_root / "pilot-ledger.jsonl"
    with runner_lock(state_root):
        events = initialize_ledger(contract, ledger_path)
        while True:
            action = next_legal_action(contract, events)
            kind = action["action"]
            if kind == "complete":
                return {"status": "complete", "cells": len(contract["schedule"]["cells"])}
            if kind == "batch_stopped":
                return {"status": "batch_stopped", "payload": action["payload"]}
            if kind == "resolve_partial":
                if resolve_partial_as is None:
                    raise ExperimentConfigurationError(
                        "partial attempt requires explicit --resolve-partial-as classification"
                    )
                _resolve_partial(contract, ledger_path, action["request"], resolve_partial_as)
                resolve_partial_as = None
            elif kind == "record_batch_stop":
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
                raise ExperimentConfigurationError(f"unsupported durable action: {kind}")
            events = read_ledger(ledger_path)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--contract", type=Path, default=Path("experiment/pilot_execution_contract.json")
    )
    parser.add_argument("--evaluator-root", type=Path, default=DEFAULT_EVALUATOR_ROOT)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--evaluator-python", type=Path)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument(
        "--credential-source-codex-home",
        type=Path,
        default=DEFAULT_SOURCE_CODEX_HOME,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument(
        "--output", type=Path, default=Path("experiment/pilot_runner_preflight.json")
    )
    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument(
        "--output", type=Path, default=Path("experiment/pilot_runner_dry_run.json")
    )
    qualify = subparsers.add_parser("qualify-integrity")
    qualify.add_argument("--output", type=Path, default=DEFAULT_INTEGRITY_OUTPUT)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--confirm", required=True)
    execute.add_argument(
        "--resolve-partial-as", choices=sorted(RERUNNABLE_INFRASTRUCTURE | BATCH_STOP_FAILURES)
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    root = args.root.resolve()
    evaluator_root = args.evaluator_root.resolve()
    host = read_object(root / "experiment/pilot_host_qualification.json")
    dataset_root = (args.dataset_root or Path(host["procedure"]["dataset_snapshot_path"])).resolve()
    evaluator_python = canonical_evaluator_python(evaluator_root, args.evaluator_python)
    contract_path = args.contract if args.contract.is_absolute() else root / args.contract
    default_state_root = (
        Path(".local/pilot-v2-runner")
        if contract_path.name == "pilot_v2_execution_contract.json"
        else DEFAULT_STATE_ROOT
    )
    requested_state_root = args.state_root or default_state_root
    state_root = requested_state_root if requested_state_root.is_absolute() else root / requested_state_root
    source_codex_home = args.credential_source_codex_home.resolve()
    exit_status = 0
    try:
        contract = read_object(contract_path)
        contract_validator = validate_contract
        if contract.get("contract_version") == "pilot-v2.0":
            from engineering_scope_guard.pilot_v2 import validate_contract as validate_v2

            contract_validator = validate_v2
        base_preflight = strict_preflight(
            root,
            contract,
            evaluator_root,
            dataset_root,
            evaluator_python,
            args.codex_binary,
            state_root,
            source_codex_home,
            contract_path,
            contract_validator,
        )
        tasks = resolve_tasks(root, contract, evaluator_python, dataset_root)
        if args.command == "dry-run":
            if contract.get("contract_version") == "pilot-v2.0":
                from engineering_scope_guard.pilot_v2 import build_dry_run

                result = build_dry_run(root, contract)
            else:
                result = dry_run_receipt(contract, root, state_root, tasks)
            _write_json(args.output if args.output.is_absolute() else root / args.output, result)
        elif contract.get("contract_version") == "pilot-v2.0":
            if args.command == "qualify-integrity":
                raise ExperimentConfigurationError(
                    "Pilot-v2 reuses the frozen final live canary; no new canary is authorized"
                )
            if args.command == "preflight":
                result = {
                    **base_preflight,
                    "status": "pass",
                    "execution_integrity": {
                        "source": "experiment/pilot_v2_canary_qualification.json",
                        "reused_final_live_canary": True,
                        "new_canary_invocations": 0,
                    },
                }
                _write_json(
                    args.output if args.output.is_absolute() else root / args.output,
                    result,
                )
            else:
                result = execute_batch(
                    root,
                    contract,
                    backend=LiveBackend(
                        root,
                        contract,
                        tasks,
                        evaluator_root,
                        dataset_root,
                        evaluator_python,
                        args.codex_binary,
                        source_codex_home,
                    ),
                    state_root=state_root,
                    confirmation=args.confirm,
                    resolve_partial_as=args.resolve_partial_as,
                )
        else:
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
            integrity = qualify_execution_integrity(
                root, contract, backend, state_root, canary_runs=2
            )
            if args.command == "preflight":
                result = {
                    **base_preflight,
                    "status": (
                        "pass"
                        if integrity["decision"]
                        == "EXECUTION-INTEGRITY QUALIFIED — GO TO RESUME PILOT"
                        else "fail"
                    ),
                    "execution_integrity": integrity,
                }
                _write_json(
                    args.output if args.output.is_absolute() else root / args.output,
                    result,
                )
                exit_status = 0 if result["status"] == "pass" else 1
            elif args.command == "qualify-integrity":
                result = integrity
                _write_json(
                    args.output if args.output.is_absolute() else root / args.output,
                    result,
                )
            else:
                if integrity["decision"] != (
                    "EXECUTION-INTEGRITY QUALIFIED — GO TO RESUME PILOT"
                ):
                    raise ExperimentConfigurationError(
                        "execution-integrity qualification does not authorize Pilot resume"
                    )
                result = execute_batch(
                    root,
                    contract,
                    backend,
                    state_root,
                    args.confirm,
                    args.resolve_partial_as,
                )
    except (ExperimentConfigurationError, KeyError, OSError, ValueError) as error:
        print(f"pilot_runner: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
